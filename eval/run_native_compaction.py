"""Exercise native context compaction through saved Open WebUI chats."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from eval.mock_run import atomic_json, objective
from eval.run_local import request_json, response_text


ROOT = Path(__file__).parents[1]


def chat_payload(case: dict, model: str) -> tuple[dict, dict]:
    messages = []
    parent_id = None
    for source in case["input"]["messages"]:
        message_id = str(uuid.uuid4())
        message = {
            "id": message_id,
            "parentId": parent_id,
            "childrenIds": [],
            "role": source["role"],
            "content": source["content"],
            "model": model if source["role"] == "assistant" else None,
            "done": True,
            "timestamp": int(time.time()),
        }
        if messages:
            messages[-1]["childrenIds"] = [message_id]
        messages.append(message)
        parent_id = message_id
    message_map = {message["id"]: message for message in messages}
    chat = {
        "title": f"Teardown native compaction {case['id']}",
        "models": [model],
        "history": {"messages": message_map, "currentId": messages[-1]["id"]},
        "messages": messages,
    }
    return {"chat": chat}, messages[-1]


def find_context_summaries(value) -> list[str]:
    summaries = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"contextSummary", "context_summary"} and isinstance(child, str) and child.strip():
                summaries.append(child)
            else:
                summaries.extend(find_context_summaries(child))
    elif isinstance(value, list):
        for child in value:
            summaries.extend(find_context_summaries(child))
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--eval", type=Path, default=Path("eval/cases.json"))
    parser.add_argument("--condition", default="l4-native-compaction")
    parser.add_argument("--model", default="qwen2.5:14b-instruct")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    eval_bytes = args.eval.read_bytes()
    eval_sha = hashlib.sha256(eval_bytes).hexdigest()
    cases = [case for case in json.loads(eval_bytes)["cases"] if case["call_type"] == "main_chat_context"]
    email = os.getenv("TEARDOWN_ADMIN_EMAIL", "admin@localhost")
    password = os.getenv("TEARDOWN_ADMIN_PASSWORD", "admin")
    session, _ = request_json("POST", base + "/api/v1/auths/signin", payload={"email": email, "password": password}, timeout=args.timeout)
    token = session["token"]
    cache_dir = ROOT / "results" / "cache" / "local-eval" / args.condition
    rows = []
    cached = 0
    for case in cases:
        key = hashlib.sha256(
            json.dumps({"condition": args.condition, "eval_sha256": eval_sha, "case_id": case["id"], "model": args.model}, sort_keys=True).encode()
        ).hexdigest()
        cache_path = cache_dir / f"{key}.json"
        if cache_path.exists():
            row = json.loads(cache_path.read_text(encoding="utf-8"))
            if row.get("cache_key") != key or not row.get("compaction_triggered"):
                raise RuntimeError(f"Invalid native compaction cache: {cache_path}")
            cached += 1
        else:
            create_payload, final_user = chat_payload(case, args.model)
            created, _ = request_json("POST", base + "/api/v1/chats/new", token, create_payload, args.timeout)
            assistant_message_id = str(uuid.uuid4())
            completion_payload = {
                "model": args.model,
                "messages": case["input"]["messages"],
                "stream": False,
                "chat_id": created["id"],
                "id": assistant_message_id,
                "user_message": final_user,
            }
            response, completion_ms = request_json("POST", base + "/api/chat/completions", token, completion_payload, args.timeout)
            persisted, _ = request_json("GET", base + f"/api/v1/chats/{created['id']}", token, timeout=args.timeout)
            summaries = find_context_summaries(persisted)
            if not summaries:
                raise RuntimeError(f"Native compaction did not persist trigger evidence for {case['id']}")
            text = response_text(response)
            row = {
                "cache_key": key,
                "condition": args.condition,
                "case_id": case["id"],
                "call_type": case["call_type"],
                "chat_id": created["id"],
                "response": response,
                "response_text": text,
                "completion_ms": completion_ms,
                "objective_score": objective(case, text),
                "compaction_triggered": True,
                "persisted_summary_sha256": hashlib.sha256(summaries[-1].encode()).hexdigest(),
                "persisted_summary_chars": len(summaries[-1]),
            }
            atomic_json(cache_path, row)
        rows.append(row)
        print(f"native-compaction completed={len(rows)}/{len(cases)} cached={cached} triggered={sum(bool(item['compaction_triggered']) for item in rows)}", flush=True)

    rows_path = ROOT / "results" / "eval" / f"{args.condition}.rows.json"
    summary_path = ROOT / "results" / "eval" / f"{args.condition}.summary.json"
    atomic_json(rows_path, rows)
    summary = {
        "schema_version": 1,
        "condition": args.condition,
        "provider": "local_ollama_via_saved_open_webui_chat",
        "actual_api_cost_usd": "0",
        "eval_sha256": eval_sha,
        "completed_cases": len(rows),
        "cached_cases": cached,
        "compaction_triggered_cases": sum(bool(row["compaction_triggered"]) for row in rows),
        "objective_mean_by_call_type": {"main_chat_context": round(sum(float(row["objective_score"]) for row in rows) / len(rows), 6)},
        "rows": str(rows_path.relative_to(ROOT)).replace("\\", "/"),
    }
    atomic_json(summary_path, summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
