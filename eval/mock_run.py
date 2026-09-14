"""Run the frozen generation eval against the deterministic local mock provider."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
import urllib.request
from collections import defaultdict
from http.server import ThreadingHTTPServer
from pathlib import Path

from eval.scoring import parse_json_object, required_phrase_recall
from proxy.mock_provider import Handler as MockHandler


ROOT = Path(__file__).parents[1]


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def request(base: str, payload: dict) -> tuple[dict, float]:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    req = urllib.request.Request(base + "/v1/chat/completions", data=raw, headers={"Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read()), (time.monotonic() - started) * 1000


def payload_for(case: dict, model: str) -> dict:
    call_type = case["call_type"]
    if call_type == "title":
        instruction = "title: Return only JSON with a concise title."
        messages = case["input"]["messages"]
    elif call_type == "tags":
        instruction = "tags: Return only JSON with a tags array."
        messages = case["input"]["messages"]
    elif call_type in {"retrieval_query", "web_query"}:
        instruction = "query: Return only JSON with one query."
        messages = case["input"]["messages"]
    elif call_type == "main_chat_context":
        instruction = "Answer the final question using the conversation facts."
        messages = case["input"]["messages"]
    elif call_type == "autocomplete":
        instruction = "autocomplete: Continue the user text briefly."
        messages = [{"role": "user", "content": case["input"]["prompt"]}]
    else:
        raise ValueError(f"Unsupported generative mock call type: {call_type}")
    return {"model": model, "messages": [{"role": "system", "content": instruction}, *messages], "temperature": 0, "max_tokens": 128, "stream": False}


def objective(case: dict, text: str) -> float:
    kind = case["call_type"]
    if kind == "title":
        value = parse_json_object(text)
        return float(bool(value and isinstance(value.get("title"), str) and 1 <= len(value["title"].split()) <= 8))
    if kind == "tags":
        value = parse_json_object(text)
        return float(bool(value and isinstance(value.get("tags"), list) and value["tags"]))
    if kind in {"retrieval_query", "web_query"}:
        value = parse_json_object(text)
        return float(bool(value and isinstance(value.get("query"), str) and value["query"].strip()))
    if kind == "main_chat_context":
        return required_phrase_recall(text, case["expected"]["required_phrases"])
    return float(bool(text.strip()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", type=Path, default=Path("eval/cases.json"))
    parser.add_argument("--condition", default="mock-eval-v1")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--output", type=Path, default=Path("results/mock/eval-summary.json"))
    args = parser.parse_args()
    eval_bytes = args.eval.read_bytes()
    eval_sha = hashlib.sha256(eval_bytes).hexdigest()
    data = json.loads(eval_bytes)
    cases = [case for case in data["cases"] if case["call_type"] != "retrieval"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    cache_dir = ROOT / "results/cache/mock-eval" / args.condition
    rows = []
    cached = 0
    try:
        for case in cases:
            payload = payload_for(case, args.model)
            key = hashlib.sha256(json.dumps({"condition": args.condition, "eval_sha256": eval_sha, "case_id": case["id"], "payload": payload}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            cache_path = cache_dir / f"{key}.json"
            if cache_path.exists():
                row = json.loads(cache_path.read_text(encoding="utf-8"))
                if row.get("cache_key") != key or row.get("response_text") is None:
                    raise RuntimeError(f"Invalid mock cache: {cache_path}")
                cached += 1
            else:
                response, completion_ms = request(base, payload)
                text = response["choices"][0]["message"]["content"]
                row = {"cache_key": key, "case_id": case["id"], "call_type": case["call_type"], "response_text": text, "usage": response.get("usage"), "completion_ms": round(completion_ms, 3), "objective_score": objective(case, text)}
                atomic_json(cache_path, row)
            rows.append(row)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    by_type = defaultdict(list)
    for row in rows:
        by_type[row["call_type"]].append(row["objective_score"])
    summary = {"schema_version": 1, "status": "passed", "provider": "deterministic_embedded_mock", "api_cost_usd": "0", "condition": args.condition, "eval_sha256": eval_sha, "planned_generative_cases": len(cases), "completed_cases": len(rows), "cached_cases": cached, "skipped_retrieval_cases": len(data["cases"]) - len(cases), "objective_mean_by_call_type": {kind: sum(values) / len(values) for kind, values in sorted(by_type.items())}, "note": "Harness execution pass only. Mock objective scores are not model-quality findings."}
    atomic_json(args.output, summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
