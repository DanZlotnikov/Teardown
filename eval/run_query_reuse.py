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
PROMPT = "According to the attached controlled corpus, which Open WebUI work can a smaller task model handle, and what model remains unchanged?"


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
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    email = os.getenv("TEARDOWN_ADMIN_EMAIL", "admin@localhost")
    password = os.getenv("TEARDOWN_ADMIN_PASSWORD", "admin")
    session, _ = request_json("POST", base + "/api/v1/auths/signin", payload={"email": email, "password": password}, timeout=args.timeout)
    token = session["token"]
    configure_web(base, token, args.timeout)
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": PROMPT}],
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
    captures = [json.loads(line) for line in args.capture.read_text(encoding="utf-8").splitlines() if line.strip()]
    provider_calls = [row for row in captures if row.get("path") == "/api/chat" and row.get("status") == 200]
    result = {
        "schema_version": 1,
        "condition": args.condition,
        "actual_api_cost_usd": "0",
        "combined_web_and_file_path": True,
        "provider_chat_calls": len(provider_calls),
        "completion_ms": completion_ms,
        "response_text": text,
        "objective_score": float("smaller task model" in text.lower() and "main chat model" in text.lower()),
        "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "capture": str(args.capture).replace("\\", "/"),
    }
    output = ROOT / "results" / "eval" / f"{args.condition}.json"
    atomic_json(output, result)
    print(json.dumps({"condition": args.condition, "provider_chat_calls": len(provider_calls), "objective_score": result["objective_score"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
