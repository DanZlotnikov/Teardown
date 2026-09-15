"""Apply one frozen ablation condition to a live Open WebUI runtime."""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).parents[1]
CONDITIONS_PATH = ROOT / "configs" / "conditions.yaml"
TURN_FILTER_PATH = ROOT / "configs" / "optimized" / "context_turn_filter.py"
TURN_FILTER_ID = "teardown_context_turns"


def request_json(method: str, url: str, token: str | None = None, payload: dict | None = None) -> Any:
    headers: dict[str, str] = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def signin(base: str) -> str:
    email = os.getenv("TEARDOWN_ADMIN_EMAIL", "admin@localhost")
    password = os.getenv("TEARDOWN_ADMIN_PASSWORD", "admin")
    return request_json("POST", base + "/api/v1/auths/signin", payload={"email": email, "password": password})["token"]


def resolve_condition(condition_id: str) -> tuple[dict, dict]:
    matrix = yaml.safe_load(CONDITIONS_PATH.read_text(encoding="utf-8"))
    baseline = dict(matrix["baseline"])
    baseline.pop("id", None)
    for lever_id, lever in matrix["single_lever_conditions"].items():
        for level in lever.get("levels", []):
            if level["id"] == condition_id:
                state = {**baseline, **level["change"]}
                return state, {"lever": lever_id, "change": level["change"]}
    if condition_id in {"baseline", "baseline-local-qwen"}:
        return baseline, {"lever": None, "change": {}}
    raise SystemExit(f"Unknown or unsupported condition: {condition_id}")


def get_function(base: str, token: str) -> dict | None:
    try:
        return request_json("GET", base + f"/api/v1/functions/id/{TURN_FILTER_ID}", token)
    except urllib.error.HTTPError as error:
        if error.code in {401, 404}:
            return None
        raise


def set_toggle(base: str, token: str, function: dict, field: str, desired: bool) -> dict:
    if bool(function.get(field)) != desired:
        suffix = "toggle/global" if field == "is_global" else "toggle"
        function = request_json("POST", base + f"/api/v1/functions/id/{TURN_FILTER_ID}/{suffix}", token)
    return function


def configure_turn_filter(base: str, token: str, turns: int | None) -> dict:
    function = get_function(base, token)
    if function is None and turns is not None:
        function = request_json(
            "POST",
            base + "/api/v1/functions/create",
            token,
            {
                "id": TURN_FILTER_ID,
                "name": "Teardown Sliding Turn Window",
                "content": TURN_FILTER_PATH.read_text(encoding="utf-8"),
                "meta": {"description": "Controlled L4 filter; keeps the newest N user turns."},
            },
        )
    if function is None:
        return {"installed": False, "active": False, "global": False, "turns": None}
    if turns is not None:
        request_json("POST", base + f"/api/v1/functions/id/{TURN_FILTER_ID}/valves/update", token, {"turns": turns})
    function = set_toggle(base, token, function, "is_active", turns is not None)
    function = set_toggle(base, token, function, "is_global", turns is not None)
    valves = request_json("GET", base + f"/api/v1/functions/id/{TURN_FILTER_ID}/valves", token)
    return {
        "installed": True,
        "active": bool(function.get("is_active")),
        "global": bool(function.get("is_global")),
        "turns": valves.get("turns") if isinstance(valves, dict) else None,
    }


def apply(base: str, condition_id: str, output: Path | None = None) -> dict:
    base = base.rstrip("/")
    state, diff = resolve_condition(condition_id)
    policy = state.get("context_policy")
    if state.get("enable_queries_cache"):
        raise SystemExit("L5 requires an Open WebUI restart with ENABLE_QUERIES_CACHE=True; dynamic mutation would be invalid")

    token = signin(base)
    task = request_json("GET", base + "/api/v1/tasks/config", token)
    task_model = "" if state.get("task_model") == "main_chat_model" else state.get("task_model", "")
    task.update(
        {
            "TASK_MODEL": task_model,
            "TASK_MODEL_EXTERNAL": task_model,
            "TASK_MODEL_PARAMS": state.get("task_model_params") or {},
            "TITLE_GENERATION_PROMPT_TEMPLATE": "",
            "ENABLE_AUTOCOMPLETE_GENERATION": bool(state.get("autocomplete")),
        }
    )
    task = request_json("POST", base + "/api/v1/tasks/config/update", token, task)

    retrieval = request_json("POST", base + "/api/v1/retrieval/config/update", token, {"TOP_K": int(state.get("rag_top_k", 3))})

    chat = request_json("GET", base + "/api/v1/chats/config", token)
    native = isinstance(policy, dict) and policy.get("kind") == "native_compaction"
    chat.update(
        {
            "CONTEXT_COMPACTION_MODEL": task_model,
            "ENABLE_CONTEXT_COMPACTION": native,
            "CONTEXT_COMPACTION_TOKEN_THRESHOLD": int(policy.get("token_threshold", 80000)) if native else 80000,
            "CONTEXT_COMPACTION_TOKEN_CAP": int(policy.get("token_cap", 80000)) if native else 80000,
            "CONTEXT_COMPACTION_RETENTION_PERCENTAGE": int(policy.get("retention_percentage", 40)) if native else 40,
            "CONTEXT_COMPACTION_PROMPT_TEMPLATE": "",
        }
    )
    chat = request_json("POST", base + "/api/v1/chats/config", token, chat)

    turns = int(policy["turns"]) if isinstance(policy, dict) and policy.get("kind") == "sliding_turns" else None
    filter_state = configure_turn_filter(base, token, turns)
    applied = {
        "condition": condition_id,
        "declared_diff": diff,
        "task_model": task.get("TASK_MODEL_EXTERNAL"),
        "task_model_params": task.get("TASK_MODEL_PARAMS"),
        "autocomplete": task.get("ENABLE_AUTOCOMPLETE_GENERATION"),
        "rag_top_k": retrieval.get("TOP_K"),
        "context_compaction": {
            "enabled": chat.get("ENABLE_CONTEXT_COMPACTION"),
            "threshold": chat.get("CONTEXT_COMPACTION_TOKEN_THRESHOLD"),
            "cap": chat.get("CONTEXT_COMPACTION_TOKEN_CAP"),
            "retention_percentage": chat.get("CONTEXT_COMPACTION_RETENTION_PERCENTAGE"),
        },
        "turn_filter": filter_state,
    }
    output = output or ROOT / "results" / "runtime-condition.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(applied, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return applied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("condition")
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(apply(args.base_url, args.condition, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
