"""Exercise L5 query reuse on one real combined web-plus-file chat path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from eval.mock_run import atomic_json
from eval.run_local import request_json, response_text


ROOT = Path(__file__).parents[1]
CASES = (
    (
        "task-model",
        "According to the attached controlled corpus, which Open WebUI work can a smaller task model handle, and what model remains unchanged?",
        (("title", "tags", "follow-up"), ("main chat",)),
    ),
    (
        "task-cap",
        "According to the corpus, what is the scope risk of setting task.model.params max_tokens?",
        (("global",), ("task", "endpoint")),
    ),
    (
        "title-template",
        "According to the corpus, what units does native title-template truncation count?",
        (("message",), ("character",)),
    ),
    (
        "context-compaction",
        "According to the corpus, when does native context compaction trigger and what is its default state?",
        (("threshold",), ("disabled", "off")),
    ),
    (
        "query-cache",
        "According to the corpus, what duplicate work does query reuse avoid?",
        (("query",), ("duplicate", "reuse", "cached")),
    ),
    (
        "rag-top-k",
        "According to the corpus, what does retrieval top-k control?",
        (("chunk",), ("retriev",)),
    ),
    (
        "budget",
        "According to the corpus, what must happen before a paid provider attempt?",
        (("reserv",), ("ledger", "persist")),
    ),
    (
        "resume-cache",
        "According to the corpus, what must a stable paid-output cache key bind?",
        (("condition",), ("dataset", "fixture"), ("endpoint",), ("payload",)),
    ),
)


def configure_web(base: str, token: str, timeout: int) -> None:
    config, _ = request_json("GET", base + "/api/v1/retrieval/config", token, timeout=timeout)
    web = config["web"]
    web.update(
        {
            "ENABLE_WEB_SEARCH": True,
            "ENABLE_WEB_SEARCH_CONFIRMATION": False,
            "WEB_SEARCH_ENGINE": "",
            "WEB_SEARCH_RESULT_COUNT": 1,
            "BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL": True,
            "BYPASS_WEB_SEARCH_WEB_LOADER": True,
        }
    )
    updated, _ = request_json("POST", base + "/api/v1/retrieval/config/update", token, config, timeout)
    if not updated.get("web", {}).get("ENABLE_WEB_SEARCH"):
        raise RuntimeError("Web search did not become enabled")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--condition", required=True)
    parser.add_argument("--model", default="qwen2.5:14b-instruct")
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--case-limit", type=int)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    email = os.getenv("TEARDOWN_ADMIN_EMAIL", "admin@localhost")
    password = os.getenv("TEARDOWN_ADMIN_PASSWORD", "admin")
    session, _ = request_json("POST", base + "/api/v1/auths/signin", payload={"email": email, "password": password}, timeout=args.timeout)
    token = session["token"]
    configure_web(base, token, args.timeout)
    cases = CASES[: args.case_limit] if args.case_limit is not None else CASES
    rows = []
    payload_hashes = []
    for case_id, prompt, expected_groups in cases:
        payload = {
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "features": {"web_search": True},
            "params": {"function_calling": "legacy"},
            "files": [
                {
                    "id": args.collection_id,
                    "type": "collection",
                    "name": "Controlled teardown corpus",
                    "collection_names": [args.collection_id],
                    "legacy": True,
                }
            ],
        }
        response, completion_ms = request_json("POST", base + "/api/chat/completions", token, payload, args.timeout)
        text = response_text(response)
        lowered = text.lower()
        score = sum(any(term in lowered for term in group) for group in expected_groups) / len(expected_groups)
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        payload_hashes.append(payload_hash)
        rows.append(
            {
                "case_id": case_id,
                "response_text": text,
                "completion_ms": completion_ms,
                "objective_score": score,
                "payload_sha256": payload_hash,
            }
        )
    captures = [json.loads(line) for line in args.capture.read_text(encoding="utf-8").splitlines() if line.strip()]
    provider_calls = [row for row in captures if row.get("path") == "/api/chat" and row.get("status") == 200]
    query_calls = [
        row
        for row in provider_calls
        if str(((row.get("request_body") or {}).get("messages") or [{}])[0].get("content") or "").startswith("### Task:\nAnalyze the chat history")
    ]
    result = {
        "schema_version": 1,
        "condition": args.condition,
        "actual_api_cost_usd": "0",
        "combined_web_and_file_path": True,
        "provider_chat_calls": len(provider_calls),
        "query_generation_calls": len(query_calls),
        "final_answer_calls": len(provider_calls) - len(query_calls),
        "completed_cases": len(rows),
        "objective_mean": sum(row["objective_score"] for row in rows) / len(rows),
        "payload_sha256s": payload_hashes,
        "rows": rows,
        "capture": str(args.capture).replace("\\", "/"),
    }
    output = ROOT / "results" / "eval" / f"{args.condition}.json"
    atomic_json(output, result)
    print(json.dumps({"condition": args.condition, "provider_chat_calls": len(provider_calls), "query_generation_calls": len(query_calls), "objective_mean": result["objective_mean"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
