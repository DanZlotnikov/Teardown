"""Run zero-cost task-shaped smoke cases against an already-installed Ollama model."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


CASES = [
    ("title", "Return only JSON with a 2-4 word title for: Open WebUI stopped loading knowledge lists after an upgrade."),
    ("tags", "Return only JSON with 1-3 short tags for: Open WebUI stopped loading knowledge lists after an upgrade."),
    ("retrieval_query", "Return only JSON with one concise retrieval query for diagnosing Open WebUI knowledge-list loading."),
    ("autocomplete", "Continue this text with at most eight useful words, no preamble: To reduce Open WebUI task-model cost, configure"),
]


def request_json(url: str, payload: dict, timeout: int) -> dict:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def get_json(url: str, timeout: int) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen2.5:14b-instruct")
    parser.add_argument("--output", type=Path, default=Path("results/local-model-smoke.json"))
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    tags = get_json(args.base_url.rstrip("/") + "/api/tags", args.timeout)
    installed = next((item for item in tags.get("models", []) if item.get("name") == args.model), None)
    if installed is None:
        raise SystemExit(f"Refusing to pull a model implicitly; {args.model!r} is not already installed")
    rows = []
    for call_type, prompt in CASES:
        started = time.monotonic()
        response = request_json(
            args.base_url.rstrip("/") + "/api/chat",
            {
                "model": args.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0, "seed": 42, "num_predict": 64},
            },
            args.timeout,
        )
        text = ((response.get("message") or {}).get("content") or "").strip()
        if not text:
            raise RuntimeError(f"Local smoke returned no content for {call_type}")
        rows.append(
            {
                "call_type": call_type,
                "completion_ms": round((time.monotonic() - started) * 1000, 3),
                "response_text": text,
                "prompt_eval_count": response.get("prompt_eval_count"),
                "eval_count": response.get("eval_count"),
                "done_reason": response.get("done_reason"),
            }
        )
    report = {
        "schema_version": 1,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "provider": "local_ollama",
        "api_cost_usd": "0",
        "model": args.model,
        "model_digest": installed.get("digest"),
        "model_size_bytes": installed.get("size"),
        "model_details": installed.get("details"),
        "options": {"temperature": 0, "seed": 42, "num_predict": 64},
        "status": "passed",
        "scope_warning": "Deployability smoke only. These outputs are not evidence of hosted-model quality equivalence.",
        "cases": rows,
    }
    atomic_json(args.output, report)
    print(json.dumps({"status": "passed", "model": args.model, "cases": len(rows), "api_cost_usd": "0", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
