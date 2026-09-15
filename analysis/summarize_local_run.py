"""Turn a completed local Open WebUI condition into a reproducible run artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from eval.scoring import normalized_token_jaccard, retrieval_recall
from scenario.install_corpus import extract_doc_ids


ROOT = Path(__file__).parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compose_rows(rows: list[dict], baseline_rows: list[dict], drop_call_types: set[str]) -> list[dict]:
    replacements: dict[tuple[str, str, int], dict] = {}
    offsets = Counter()
    for row in rows:
        base_key = (row["conversation_id"], row["call_type"])
        key = (*base_key, offsets[base_key])
        offsets[base_key] += 1
        replacements[key] = row
    composed = []
    offsets.clear()
    used = set()
    for baseline in baseline_rows:
        if baseline["call_type"] in drop_call_types:
            continue
        base_key = (baseline["conversation_id"], baseline["call_type"])
        key = (*base_key, offsets[base_key])
        offsets[base_key] += 1
        if key in replacements:
            composed.append(replacements[key])
            used.add(key)
        else:
            composed.append(baseline)
    unused = set(replacements) - used
    if unused:
        raise SystemExit(f"Condition actions cannot be aligned to baseline: {sorted(unused)[:3]}")
    return composed


def response_text(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        return str(message.get("content") or choices[0].get("text") or "")
    message = response.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(response.get("response") or "")


def usage(response: Any) -> tuple[int, int, int]:
    value = response.get("usage", {}) if isinstance(response, dict) else {}
    input_tokens = int(value.get("input_tokens", value.get("prompt_tokens", value.get("prompt_eval_count", 0))) or 0)
    cached_tokens = int(value.get("cached_input_tokens", value.get("prompt_eval_cached_count", 0)) or 0)
    output_tokens = int(value.get("output_tokens", value.get("completion_tokens", value.get("eval_count", 0))) or 0)
    return input_tokens, cached_tokens, output_tokens


def provider_completion_ms(response: Any) -> float | None:
    value = response.get("usage", {}) if isinstance(response, dict) else {}
    duration = value.get("total_duration")
    return round(float(duration) / 1_000_000, 3) if duration is not None else None


def declared_condition(condition: str) -> tuple[dict, str | None]:
    matrix = yaml.safe_load((ROOT / "configs" / "conditions.yaml").read_text(encoding="utf-8"))
    if condition == "baseline":
        return {}, None
    for lever, data in matrix["single_lever_conditions"].items():
        for level in data.get("levels", []):
            if level["id"] == condition:
                return level["change"], lever
    return {}, None


def paired_agreement(rows: list[dict], baseline_rows: list[dict]) -> dict[str, float]:
    baseline = defaultdict(list)
    for row in baseline_rows:
        baseline[(row["conversation_id"], row["call_type"])].append(response_text(row.get("response")))
    offsets = Counter()
    scores: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        key = (row["conversation_id"], row["call_type"])
        offset = offsets[key]
        offsets[key] += 1
        if offset < len(baseline[key]) and row["call_type"] != "retrieval":
            scores[row["call_type"]].append(normalized_token_jaccard(baseline[key][offset], response_text(row.get("response"))))
    return {kind: round(sum(values) / len(values), 6) for kind, values in sorted(scores.items()) if values}


def retrieval_quality(rows: list[dict], k: int) -> dict:
    expected_data = json.loads((ROOT / "scenario" / "retrieval-cases.json").read_text(encoding="utf-8"))
    expected = {case["id"]: case["relevant_document_ids"] for case in expected_data["queries"]}
    scores = []
    cases = []
    for row in rows:
        if row["call_type"] != "retrieval":
            continue
        retrieved = extract_doc_ids(row.get("response"))[:k]
        relevant = expected[row["conversation_id"]]
        score = retrieval_recall(retrieved, relevant, k)
        scores.append(score)
        cases.append({"case_id": row["conversation_id"], "retrieved_document_ids": retrieved, "relevant_document_ids": relevant, "recall": score})
    return {"mean_recall": round(sum(scores) / len(scores), 6) if scores else None, "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--baseline-actions", type=Path, default=ROOT / "results/actions/mock/baseline.jsonl")
    parser.add_argument("--price-model", default="gpt-5.6-sol")
    parser.add_argument("--retrieval-k", type=int, default=3)
    parser.add_argument("--compose-with-baseline", action="store_true")
    parser.add_argument("--drop-call-types", default="")
    args = parser.parse_args()

    actions_path = args.actions or ROOT / f"results/actions/mock/{args.condition}.jsonl"
    measured_rows = load_rows(actions_path)
    baseline_rows = load_rows(args.baseline_actions) if args.baseline_actions.exists() else []
    drop_call_types = {value.strip() for value in args.drop_call_types.split(",") if value.strip()}
    rows = compose_rows(measured_rows, baseline_rows, drop_call_types) if args.compose_with_baseline else measured_rows
    if any(row.get("error") for row in rows):
        raise SystemExit("Refusing to summarize a run containing errors")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    prices = config["pricing_snapshot"]["models"][args.price_model]
    input_price = Decimal(str(prices["input"])) / Decimal(1_000_000)
    cached_price = Decimal(str(prices["cached_input"])) / Decimal(1_000_000)
    output_price = Decimal(str(prices["output"])) / Decimal(1_000_000)

    totals = Counter()
    by_type: dict[str, Counter] = defaultdict(Counter)
    latencies: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        input_tokens, cached_tokens, output_tokens = usage(row.get("response"))
        uncached_tokens = max(0, input_tokens - cached_tokens)
        cost = Decimal(uncached_tokens) * input_price + Decimal(cached_tokens) * cached_price + Decimal(output_tokens) * output_price
        for key, value in (("calls", 1), ("input_tokens", input_tokens), ("cached_input_tokens", cached_tokens), ("output_tokens", output_tokens)):
            totals[key] += value
            by_type[row["call_type"]][key] += value
        by_type[row["call_type"]]["derived_cost_usd"] += cost
        totals["derived_cost_usd"] += cost
        latency = provider_completion_ms(row.get("response"))
        if latency is not None:
            latencies[row["call_type"]].append(latency)

    diff, lever = declared_condition(args.condition)
    run = {
        "schema_version": 1,
        "condition": args.condition,
        "lever": lever,
        "configuration_diff": diff,
        "measurement": "Local Ollama wire-observed tokens; frozen-price costs are derived counterfactuals, not observed provider billing.",
        "actual_api_cost_usd": "0",
        "measurement_scope": {
            "measured_condition_actions": len(measured_rows),
            "composed_unchanged_baseline_actions": len(rows) - len(measured_rows),
            "dropped_call_types": sorted(drop_call_types),
            "total_scenario_actions": len(rows),
        },
        "derived_price_model": args.price_model,
        "derived_cost_usd": format(totals["derived_cost_usd"], "f"),
        "derived_cost_per_conversation_usd": format(totals["derived_cost_usd"] / Decimal(30), "f"),
        "counts": {key: int(totals[key]) for key in ("calls", "input_tokens", "cached_input_tokens", "output_tokens")},
        "by_call_type": {
            kind: {
                "calls": int(values["calls"]),
                "input_tokens": int(values["input_tokens"]),
                "cached_input_tokens": int(values["cached_input_tokens"]),
                "output_tokens": int(values["output_tokens"]),
                "derived_cost_usd": format(values["derived_cost_usd"], "f"),
                "provider_completion_ms_p50": percentile(latencies[kind], 0.50),
                "provider_completion_ms_p95": percentile(latencies[kind], 0.95),
                "ttft_ms_p50": None,
                "ttft_ms_p95": None,
            }
            for kind, values in sorted(by_type.items())
        },
        "quality": {
            "lexical_agreement_vs_baseline_by_call_type": paired_agreement(rows, baseline_rows) if baseline_rows else {},
            "lexical_agreement_warning": "Diagnostic only; not a semantic quality score and not used for final grading.",
            "retrieval": retrieval_quality(rows, args.retrieval_k),
        },
        "main_chat_path_risk": bool(lever in {"L4_context_management", "L6_retrieved_chunk_count"}),
        "latency_note": "Provider completion is Ollama total_duration. TTFT is unavailable because all controlled calls are nonstreaming.",
        "locks": {
            "open_webui_commit": config["subject"]["commit"],
            "open_webui_version": config["subject"]["version"],
            "pricing_snapshot_sha256": sha256(ROOT / "config.yaml"),
            "scenario_sha256": rows[0]["scenario_sha256"] if rows else (baseline_rows[0]["scenario_sha256"] if baseline_rows else None),
            "eval_sha256": sha256(ROOT / "eval/cases.json"),
            "capture_sha256": sha256(args.capture),
            "actions_sha256": sha256(actions_path) if actions_path.exists() else None,
        },
        "raw_capture": str(args.capture.relative_to(ROOT)).replace("\\", "/"),
        "actions": str(actions_path.relative_to(ROOT)).replace("\\", "/"),
        "run_count": 1,
    }
    output = ROOT / "results" / "runs" / f"{args.condition}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"condition": args.condition, "calls": totals["calls"], "derived_cost_usd": run["derived_cost_usd"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
