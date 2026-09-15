"""Run the frozen targeted eval through the real local Open WebUI API."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from eval.mock_run import atomic_json, objective
from eval.scoring import normalized_token_jaccard, retrieval_recall
from scenario.install_corpus import extract_doc_ids


ROOT = Path(__file__).parents[1]


def request_json(method: str, url: str, token: str | None = None, payload: dict | None = None, timeout: int = 180) -> tuple[Any, float]:
    headers: dict[str, str] = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return (json.loads(raw) if raw else {}), round((time.perf_counter() - started) * 1000, 3)


def response_text(response: Any) -> str:
    choices = response.get("choices") if isinstance(response, dict) else None
    if isinstance(choices, list) and choices:
        return str(choices[0].get("message", {}).get("content") or choices[0].get("text") or "")
    return ""


def payload_and_endpoint(case: dict, model: str, collection_id: str, retrieval_k: int) -> tuple[str, dict]:
    kind = case["call_type"]
    if kind in {"title", "tags"}:
        return f"/api/v1/tasks/{kind}/completions", {"model": model, "messages": case["input"]["messages"], "stream": False}
    if kind in {"retrieval_query", "web_query"}:
        return "/api/v1/tasks/queries/completions", {
            "model": model,
            "messages": case["input"]["messages"],
            "type": "retrieval" if kind == "retrieval_query" else "web_search",
            "stream": False,
        }
    if kind == "main_chat_context":
        return "/api/chat/completions", {"model": model, "messages": case["input"]["messages"], "stream": False}
    if kind == "autocomplete":
        prompt = case["input"]["prompt"]
        return "/api/v1/tasks/auto/completions", {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "prompt": prompt,
            "type": "general",
            "stream": False,
        }
    if kind == "retrieval":
        return "/api/v1/retrieval/query/collection", {
            "collection_names": [collection_id],
            "query": case["input"]["query"],
            "k": retrieval_k,
        }
    raise ValueError(f"Unsupported eval call type: {kind}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--eval", type=Path, default=Path("eval/cases.json"))
    parser.add_argument("--condition", required=True)
    parser.add_argument("--model", default="qwen2.5:14b-instruct")
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--retrieval-k", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--call-types", help="Comma-separated affected types; omitted evaluates all types")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    eval_bytes = args.eval.read_bytes()
    eval_sha = hashlib.sha256(eval_bytes).hexdigest()
    cases = json.loads(eval_bytes)["cases"]
    if args.call_types:
        selected = {value.strip() for value in args.call_types.split(",") if value.strip()}
        cases = [case for case in cases if case["call_type"] in selected]
    base = args.base_url.rstrip("/")
    email = os.getenv("TEARDOWN_ADMIN_EMAIL", "admin@localhost")
    password = os.getenv("TEARDOWN_ADMIN_PASSWORD", "admin")
    session, _ = request_json("POST", base + "/api/v1/auths/signin", payload={"email": email, "password": password}, timeout=args.timeout)
    token = session["token"]
    cache_dir = ROOT / "results" / "cache" / "local-eval" / args.condition
    rows = []
    cached = 0
    for index, case in enumerate(cases, 1):
        endpoint, payload = payload_and_endpoint(case, args.model, args.collection_id, args.retrieval_k)
        key = hashlib.sha256(
            json.dumps(
                {"condition": args.condition, "eval_sha256": eval_sha, "case_id": case["id"], "endpoint": endpoint, "payload": payload},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        cache_path = cache_dir / f"{key}.json"
        if cache_path.exists():
            row = json.loads(cache_path.read_text(encoding="utf-8"))
            if row.get("cache_key") != key or "response" not in row:
                raise RuntimeError(f"Invalid local eval cache: {cache_path}")
            cached += 1
        else:
            response, completion_ms = request_json("POST", base + endpoint, token, payload, args.timeout)
            text = response_text(response)
            if case["call_type"] == "retrieval":
                retrieved = extract_doc_ids(response)[: args.retrieval_k]
                score = retrieval_recall(retrieved, case["expected"]["relevant_document_ids"], args.retrieval_k)
            else:
                retrieved = None
                score = objective(case, text)
            row = {
                "cache_key": key,
                "condition": args.condition,
                "case_id": case["id"],
                "call_type": case["call_type"],
                "endpoint": endpoint,
                "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "response": response,
                "response_text": text,
                "retrieved_document_ids": retrieved,
                "completion_ms": completion_ms,
                "objective_score": score,
            }
            atomic_json(cache_path, row)
        rows.append(row)
        if len(cases) > 50 and index % 10 == 0:
            print(f"local-eval condition={args.condition} completed={index}/{len(cases)} cached={cached} api_cost_usd=0", flush=True)

    baseline_path = ROOT / "results" / "eval" / "baseline.rows.json"
    baseline = {row["case_id"]: row for row in json.loads(baseline_path.read_text(encoding="utf-8"))} if baseline_path.exists() else {}
    by_type: dict[str, list[float]] = defaultdict(list)
    agreement: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_type[row["call_type"]].append(float(row["objective_score"]))
        reference = baseline.get(row["case_id"])
        if reference and row["call_type"] != "retrieval":
            agreement[row["call_type"]].append(normalized_token_jaccard(reference["response_text"], row["response_text"]))
    rows_path = ROOT / "results" / "eval" / f"{args.condition}.rows.json"
    summary_path = ROOT / "results" / "eval" / f"{args.condition}.summary.json"
    atomic_json(rows_path, rows)
    if args.condition == "baseline":
        baseline = {row["case_id"]: row for row in rows}
    summary = {
        "schema_version": 1,
        "condition": args.condition,
        "provider": "local_ollama_via_open_webui",
        "actual_api_cost_usd": "0",
        "eval_sha256": eval_sha,
        "completed_cases": len(rows),
        "cached_cases": cached,
        "counts_by_call_type": dict(sorted(Counter(row["call_type"] for row in rows).items())),
        "objective_mean_by_call_type": {kind: round(sum(values) / len(values), 6) for kind, values in sorted(by_type.items())},
        "lexical_agreement_vs_baseline_by_call_type": {kind: round(sum(values) / len(values), 6) for kind, values in sorted(agreement.items())},
        "agreement_warning": "Lexical overlap is diagnostic only. Objective scores drive local grading; semantic pairwise judging remains blocked from paid execution.",
        "rows": str(rows_path.relative_to(ROOT)).replace("\\", "/"),
    }
    atomic_json(summary_path, summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
