"""Run blinded paired judging for the frozen hosted task-model sample."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import time
from pathlib import Path

from analysis.budget import BudgetGuard, BudgetStop
from analysis.summarize_paid_sample import parse_json_text, sample_actions
from scenario.run import Action, action_id, atomic, call, signin


ROOT = Path(__file__).parents[1]
SYSTEM_NAMES = ("baseline", "terra", "luna")
LABELS = ("A", "B", "C")
PERMUTATIONS = tuple(itertools.permutations(SYSTEM_NAMES))


def load_system_outputs() -> dict[str, dict[str, str]]:
    paths = {
        "terra": ROOT / "results" / "runs" / "l1-mid-hosted-paid-sample.json",
        "luna": ROOT / "results" / "runs" / "l1-small-hosted-paid-sample.json",
    }
    systems = {name: {} for name in SYSTEM_NAMES}
    for path in paths.values():
        data = json.loads(path.read_text(encoding="utf-8"))
        for pair in data["pairs"]:
            systems["baseline"][pair["action_id"]] = pair["baseline"]["response_text"]
        logical = "terra" if "mid-hosted" in path.name else "luna"
        for pair in data["pairs"]:
            systems[logical][pair["action_id"]] = pair["candidate"]["response_text"]
    return systems


def last_user_text(action: Action) -> str:
    for message in reversed(action.payload.get("messages", [])):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return str(action.payload.get("prompt") or "")


def blinded_prompt(action: Action, outputs: dict[str, str]) -> tuple[str, dict[str, str]]:
    aid = action_id(action)
    order = PERMUTATIONS[int(aid[:8], 16) % len(PERMUTATIONS)]
    mapping = dict(zip(LABELS, order))
    rendered = "\n\n".join(f"OUTPUT {label}:\n{outputs[name]}" for label, name in mapping.items())
    prompt = f"""You are a strict, blind evaluator of three outputs from an Open WebUI background task.

Task type: {action.call_type}
Relevant user context:
{last_user_text(action)}

Score each output independently from 1 (bad) to 5 (excellent) on:
- task_compliance: follows the requested task and required output schema;
- topical_relevance: stays grounded in the user context without inventing specifics;
- usefulness: would be useful in the Open WebUI feature that requested it.

Do not reward verbosity. Malformed JSON or a broken required schema must score task_compliance 1. Return only one JSON object with exactly this shape:
{{"A":{{"task_compliance":1,"topical_relevance":1,"usefulness":1}},"B":{{"task_compliance":1,"topical_relevance":1,"usefulness":1}},"C":{{"task_compliance":1,"topical_relevance":1,"usefulness":1}},"ranking":["A","B","C"],"reason":"at most 30 words"}}

{rendered}"""
    return prompt, mapping


def validate_judgment(value) -> bool:
    if not isinstance(value, dict) or set(value.get("ranking", [])) != set(LABELS):
        return False
    for label in LABELS:
        scores = value.get(label)
        if not isinstance(scores, dict):
            return False
        for key in ("task_compliance", "topical_relevance", "usefulness"):
            score = scores.get(key)
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                return False
    return isinstance(value.get("reason"), str)


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8089")
    parser.add_argument("--mode", choices=("paid-smoke", "paid-batch"), required=True)
    parser.add_argument("--start-action", type=int, default=0)
    parser.add_argument("--max-actions", type=int)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if args.start_action < 0:
        parser.error("--start-action must be non-negative")

    guard = BudgetGuard(ROOT)
    if args.mode == "paid-batch" and not guard.smoke_passed("judge"):
        raise BudgetStop("judge paid batch requires a passed smoke marker")
    actions, sample_sha = sample_actions(ROOT / "scenario" / "paid-sample-task-32.json")
    actions = actions[args.start_action :]
    if args.max_actions is not None:
        actions = actions[: args.max_actions]
    if args.mode == "paid-smoke" and len(actions) > 2:
        raise SystemExit("paid-smoke refuses more than two actions")

    outputs = load_system_outputs()
    model = "gpt-4o-2024-11-20"
    condition = "judge-l1-task-model-tier"
    cache_dir = ROOT / "results" / "cache" / "judge" / condition
    manifest = ROOT / "results" / "judge" / f"{condition}.jsonl"
    cache_dir.mkdir(parents=True, exist_ok=True)
    existing = {}
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("cache_key") and row.get("judgment_valid"):
                existing[row["cache_key"]] = row

    token = signin(args.base_url.rstrip("/"), args.timeout)
    done = cached = 0
    for action in actions:
        aid = action_id(action)
        logical_outputs = {name: outputs[name][aid] for name in SYSTEM_NAMES}
        prompt, mapping = blinded_prompt(action, logical_outputs)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }
        key = hashlib.sha256(
            json.dumps({"condition": condition, "sample_sha256": sample_sha, "action_id": aid, "payload": payload}, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        cache_path = cache_dir / f"{key}.json"
        row = None
        if cache_path.exists():
            try:
                candidate = json.loads(cache_path.read_text(encoding="utf-8"))
                if candidate.get("cache_key") == key and candidate.get("judgment_valid"):
                    row = candidate
            except (OSError, json.JSONDecodeError):
                pass
        if row is None and key in existing:
            row = existing[key]
            atomic(cache_path, row)
        if row is not None:
            cached += 1
        else:
            request_action = Action(aid, "judge", "/api/chat/completions", payload)
            response, attempts, error, completion_ms = call(
                args.base_url.rstrip("/"), token, request_action, args.timeout, 2 if args.mode == "paid-smoke" else int(guard.budget["max_retries"])
            )
            text = ""
            if response:
                try:
                    text = str(response["choices"][0]["message"]["content"])
                except (KeyError, IndexError, TypeError):
                    pass
            judgment = parse_json_text(text)
            valid = validate_judgment(judgment)
            row = {
                "cache_key": key,
                "condition": condition,
                "sample_sha256": sample_sha,
                "action_id": aid,
                "call_type": action.call_type,
                "blind_mapping": mapping,
                "response": response,
                "judgment": judgment,
                "judgment_valid": valid,
                "attempts": attempts,
                "completion_ms": completion_ms,
                "error": error or (None if valid else "invalid judge schema"),
            }
            atomic(cache_path, row)
            append(manifest, row)
            if row["error"]:
                raise RuntimeError(f"Judge failed for {aid}: {row['error']}")
        done += 1
        progress = guard.progress(done, planned_calls=len(actions))
        if progress:
            print(f"{progress} cached={cached}", flush=True)
    print(json.dumps({"condition": condition, "planned": len(actions), "completed": done, "cached": cached, "measured_spend_usd": str(guard.running_total()), "effective_exposure_usd": str(guard.effective_total())}, sort_keys=True))


if __name__ == "__main__":
    main()
