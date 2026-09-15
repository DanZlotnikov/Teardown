"""Summarize the saved-chat native compaction condition and its trigger evidence."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import yaml

from analysis.summarize_local_run import percentile, sha256


ROOT = Path(__file__).parents[1]


def response_usage(response: dict) -> tuple[int, int, int]:
    value = response.get("usage") or {}
    return (
        int(value.get("input_tokens", value.get("prompt_tokens", 0)) or 0),
        int(value.get("cached_input_tokens", 0) or 0),
        int(value.get("output_tokens", value.get("completion_tokens", 0)) or 0),
    )


def cost(counts: Counter, prices: dict) -> Decimal:
    uncached = max(0, counts["input_tokens"] - counts["cached_input_tokens"])
    return (
        Decimal(uncached) * Decimal(str(prices["input"]))
        + Decimal(counts["cached_input_tokens"]) * Decimal(str(prices["cached_input"]))
        + Decimal(counts["output_tokens"]) * Decimal(str(prices["output"]))
    ) / Decimal(1_000_000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, default=Path("results/raw-proxy-logs/l4-native-compaction.jsonl"))
    parser.add_argument("--condition-rows", type=Path, default=Path("results/eval/l4-native-compaction.rows.json"))
    parser.add_argument("--baseline-rows", type=Path, default=Path("results/eval/baseline.rows.json"))
    parser.add_argument("--price-model", default="gpt-5.6-sol")
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    prices = config["pricing_snapshot"]["models"][args.price_model]
    captures = [json.loads(line) for line in args.capture.read_text(encoding="utf-8").splitlines() if line.strip()]
    provider_calls = [entry for entry in captures if entry.get("path") == "/api/chat" and isinstance(entry.get("usage"), dict)]
    condition_rows = json.loads(args.condition_rows.read_text(encoding="utf-8"))
    baseline_rows = [row for row in json.loads(args.baseline_rows.read_text(encoding="utf-8")) if row["call_type"] == "main_chat_context"]
    condition_counts = Counter()
    for entry in provider_calls:
        value = entry["usage"]
        condition_counts["calls"] += 1
        condition_counts["input_tokens"] += int(value.get("input_tokens", 0))
        condition_counts["cached_input_tokens"] += int(value.get("cached_input_tokens", 0))
        condition_counts["output_tokens"] += int(value.get("output_tokens", 0))
    baseline_counts = Counter()
    for row in baseline_rows:
        input_tokens, cached_tokens, output_tokens = response_usage(row["response"])
        baseline_counts["calls"] += 1
        baseline_counts["input_tokens"] += input_tokens
        baseline_counts["cached_input_tokens"] += cached_tokens
        baseline_counts["output_tokens"] += output_tokens
    condition_cost = cost(condition_counts, prices)
    baseline_cost = cost(baseline_counts, prices)
    saving = (baseline_cost - condition_cost) / baseline_cost * Decimal(100) if baseline_cost else Decimal(0)
    objective = sum(float(row["objective_score"]) for row in condition_rows) / len(condition_rows)
    baseline_objective = sum(float(row["objective_score"]) for row in baseline_rows) / len(baseline_rows)
    output = ROOT / "results" / "runs" / "l4-native-compaction.json"
    run = {
        "schema_version": 1,
        "condition": "l4-native-compaction",
        "lever": "L4_context_management",
        "configuration_diff": {
            "context_policy": {
                "kind": "native_compaction",
                "enabled": True,
                "token_threshold": 256,
                "token_cap": 256,
                "retention_percentage": 40,
            }
        },
        "measurement": "Twenty saved-chat context cases; each required persisted evidence that native compaction triggered.",
        "measurement_scope": {"targeted_cases": len(condition_rows), "provider_calls_including_summaries": len(provider_calls)},
        "actual_api_cost_usd": "0",
        "derived_price_model": args.price_model,
        "derived_cost_usd": format(condition_cost, "f"),
        "baseline_targeted_cost_usd": format(baseline_cost, "f"),
        "targeted_cost_saving_percent": float(round(saving, 6)),
        "counts": {key: int(condition_counts[key]) for key in ("calls", "input_tokens", "cached_input_tokens", "output_tokens")},
        "quality": {
            "objective_mean": round(objective, 6),
            "baseline_objective_mean": round(baseline_objective, 6),
            "objective_delta_points": round((objective - baseline_objective) * 100, 6),
            "compaction_triggered_cases": sum(bool(row.get("compaction_triggered")) for row in condition_rows),
        },
        "main_chat_path_risk": True,
        "latency": {
            "open_webui_completion_ms_p50": percentile([float(row["completion_ms"]) for row in condition_rows], 0.50),
            "open_webui_completion_ms_p95": percentile([float(row["completion_ms"]) for row in condition_rows], 0.95),
            "ttft_ms_p50": None,
            "ttft_ms_p95": None,
        },
        "latency_note": "Completion includes the native summary call and final answer. TTFT is unavailable because the controlled request is nonstreaming.",
        "locks": {
            "open_webui_commit": config["subject"]["commit"],
            "open_webui_version": config["subject"]["version"],
            "pricing_snapshot_sha256": sha256(ROOT / "config.yaml"),
            "eval_sha256": sha256(ROOT / "eval/cases.json"),
            "capture_sha256": sha256(args.capture),
        },
        "raw_capture": str(args.capture).replace("\\", "/"),
        "eval_rows": str(args.condition_rows).replace("\\", "/"),
        "run_count": 1,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"condition": run["condition"], "triggered": run["quality"]["compaction_triggered_cases"], "derived_cost_usd": run["derived_cost_usd"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
