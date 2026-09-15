"""Summarize the paired real-path L5 query-reuse experiment."""
from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def capture_counts(path: Path) -> Counter:
    counts = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        usage = row.get("usage")
        if row.get("path") != "/api/chat" or row.get("status") != 200 or not isinstance(usage, dict):
            continue
        counts["calls"] += 1
        counts["input_tokens"] += int(usage.get("input_tokens", 0))
        counts["output_tokens"] += int(usage.get("output_tokens", 0))
    return counts


def uncached_cost(counts: Counter, prices: dict) -> Decimal:
    return (
        Decimal(counts["input_tokens"]) * Decimal(str(prices["input"]))
        + Decimal(counts["output_tokens"]) * Decimal(str(prices["output"]))
    ) / Decimal(1_000_000)


def main() -> None:
    off_eval = json.loads((ROOT / "results" / "eval" / "l5-query-reuse-off-8.json").read_text(encoding="utf-8"))
    on_eval = json.loads((ROOT / "results" / "eval" / "l5-query-reuse-on-8.json").read_text(encoding="utf-8"))
    off_capture = ROOT / "results" / "raw-proxy-logs" / "l5-query-reuse-off-8.jsonl"
    on_capture = ROOT / "results" / "raw-proxy-logs" / "l5-query-reuse-on-8.jsonl"
    off = capture_counts(off_capture)
    on = capture_counts(on_capture)
    prices = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["pricing_snapshot"]["models"]["gpt-5.6-sol"]
    off_cost, on_cost = uncached_cost(off, prices), uncached_cost(on, prices)
    result = {
        "schema_version": 1,
        "condition": "l5-query-reuse-on",
        "lever": "L5_query_reuse",
        "measurement": "Eight real Open WebUI combined web-search-plus-file-retrieval chat requests per condition",
        "actual_api_cost_usd": "0",
        "baseline": {
            "provider_chat_calls": off["calls"],
            "query_generation_calls": off_eval["query_generation_calls"],
            "input_tokens": off["input_tokens"],
            "output_tokens": off["output_tokens"],
            "derived_uncached_sol_cost_usd": format(off_cost, "f"),
            "objective_mean": off_eval["objective_mean"],
        },
        "query_reuse": {
            "provider_chat_calls": on["calls"],
            "query_generation_calls": on_eval["query_generation_calls"],
            "input_tokens": on["input_tokens"],
            "output_tokens": on["output_tokens"],
            "derived_uncached_sol_cost_usd": format(on_cost, "f"),
            "objective_mean": on_eval["objective_mean"],
        },
        "provider_call_saving_percent": float(round((Decimal(off["calls"]) - Decimal(on["calls"])) / Decimal(off["calls"]) * 100, 6)),
        "query_generation_call_saving_percent": float(round((Decimal(off_eval["query_generation_calls"]) - Decimal(on_eval["query_generation_calls"])) / Decimal(off_eval["query_generation_calls"]) * 100, 6)),
        "derived_uncached_cost_saving_percent": float(round((off_cost - on_cost) / off_cost * 100, 6)),
        "quality_delta_points": round((on_eval["objective_mean"] - off_eval["objective_mean"]) * 100, 6),
        "pricing_note": "Local Ollama usage is repriced at frozen Sol rates with all inputs treated as uncached to avoid cross-condition local-cache bias.",
        "scope_note": "The web-search handler executed query generation but used an intentionally unconfigured search engine; file retrieval and final grounded answers executed normally.",
    }
    output = ROOT / "results" / "runs" / "l5-query-reuse-on.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "provider_call_saving_percent": result["provider_call_saving_percent"], "cost_saving_percent": result["derived_uncached_cost_saving_percent"], "quality_delta_points": result["quality_delta_points"]}, sort_keys=True))


if __name__ == "__main__":
    main()
