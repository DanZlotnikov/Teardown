"""Summarize a frozen paid task sample with paired cost and structural checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import median

import yaml

from scenario.run import action_id, build_actions


ROOT = Path(__file__).parents[1]


def response_text(row: dict) -> str:
    try:
        return str(row["response"]["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        return ""


def response_usage(row: dict) -> tuple[int, int, int, str]:
    response = row.get("response") or {}
    usage = response.get("usage") or {}
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    return (
        int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
        int(details.get("cached_tokens", 0) or 0),
        int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
        str(response.get("model") or ""),
    )


def parse_json_text(text: str):
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(value[start : end + 1])
            except json.JSONDecodeError:
                pass
    return None


def structural_valid(call_type: str, text: str) -> bool:
    value = parse_json_text(text)
    if not isinstance(value, dict):
        return False
    if call_type == "follow_up":
        items = value.get("follow_ups")
        return isinstance(items, list) and 3 <= len(items) <= 5 and all(isinstance(item, str) and item.strip() for item in items)
    if call_type == "title":
        return isinstance(value.get("title"), str) and bool(value["title"].strip())
    if call_type == "tags":
        items = value.get("tags")
        return isinstance(items, list) and bool(items) and all(isinstance(item, str) and item.strip() for item in items)
    if call_type in {"retrieval_query", "web_query"}:
        items = value.get("queries")
        return isinstance(items, list) and bool(items) and all(isinstance(item, str) and item.strip() for item in items)
    if call_type == "autocomplete":
        return isinstance(value.get("text"), str) and bool(value["text"].strip())
    return bool(text.strip())


def lexical_jaccard(left: str, right: str) -> float:
    words = lambda value: set(re.findall(r"[a-z0-9]+", value.lower()))
    a, b = words(left), words(right)
    return len(a & b) / len(a | b) if a or b else 1.0


def sample_actions(sample_path: Path) -> tuple[list, str]:
    scenario_path = ROOT / "scenario" / "cases.json"
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    wanted = {item["action_id"] for item in json.loads(sample_path.read_text(encoding="utf-8"))["actions"]}
    actions = [action for action in build_actions(data, "gpt-5.6-sol", "baseline") if action_id(action) in wanted]
    if len(actions) != len(wanted):
        raise RuntimeError(f"Resolved {len(actions)} of {len(wanted)} frozen sample actions")
    return actions, hashlib.sha256(sample_path.read_bytes()).hexdigest()


def load_rows(path: Path, actions: list, require_complete: bool = True) -> tuple[dict[str, dict], dict[str, dict], set[str]]:
    expected = {}
    for action in actions:
        payload_sha = hashlib.sha256(json.dumps(action.payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        expected[(action.conversation_id, action.call_type, action.endpoint, payload_sha)] = action_id(action)
    wanted = set(expected.values())
    selected = {}
    failures = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        resolved = row.get("action_id") or expected.get(
            (row.get("conversation_id"), row.get("call_type"), row.get("endpoint"), row.get("payload_sha256"))
        )
        if resolved not in wanted:
            continue
        if row.get("error") or row.get("response") is None:
            failures[resolved] = row
        else:
            selected[resolved] = row
            failures.pop(resolved, None)
    missing = wanted - set(selected) - set(failures)
    if require_complete and len(selected) != len(expected):
        raise RuntimeError(f"{path} is missing {len(missing)} frozen sample rows")
    return selected, failures, missing


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower), 3)


def cost(counts: Counter, prices: dict) -> Decimal:
    uncached = max(0, counts["input_tokens"] - counts["cached_input_tokens"])
    return (
        Decimal(uncached) * Decimal(str(prices["input"]))
        + Decimal(counts["cached_input_tokens"]) * Decimal(str(prices["cached_input"]))
        + Decimal(counts["output_tokens"]) * Decimal(str(prices["output"]))
    ) / Decimal(1_000_000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("condition")
    parser.add_argument("--baseline", type=Path, default=Path("results/actions/paid/paid-baseline.jsonl"))
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--sample", type=Path, default=Path("scenario/paid-sample-task-32.json"))
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    actions, sample_sha = sample_actions(ROOT / args.sample if not args.sample.is_absolute() else args.sample)
    baseline, baseline_failures, baseline_missing = load_rows(
        ROOT / args.baseline if not args.baseline.is_absolute() else args.baseline, actions
    )
    if baseline_failures or baseline_missing:
        raise RuntimeError("Baseline sample is not complete")
    action_path = args.actions or Path(f"results/actions/paid/{args.condition}.jsonl")
    candidate, candidate_failures, candidate_missing = load_rows(
        ROOT / action_path if not action_path.is_absolute() else action_path,
        actions,
        require_complete=not args.allow_incomplete,
    )
    expected_actions = len(actions)
    actions = [action for action in actions if action_id(action) in candidate]
    if not actions:
        raise RuntimeError("No valid paired candidate actions are available")

    totals: dict[str, Counter] = {"baseline": Counter(), "candidate": Counter()}
    by_type: dict[str, dict[str, Counter]] = {
        "baseline": defaultdict(Counter),
        "candidate": defaultdict(Counter),
    }
    pairs = []
    prices = config["pricing_snapshot"]["models"]
    condition_cost = Decimal(0)
    baseline_cost = Decimal(0)
    for action in actions:
        aid = action_id(action)
        left, right = baseline[aid], candidate[aid]
        pair = {"action_id": aid, "call_type": action.call_type}
        for label, row in (("baseline", left), ("candidate", right)):
            inp, cached, out, model = response_usage(row)
            counts = Counter(calls=1, input_tokens=inp, cached_input_tokens=cached, output_tokens=out)
            totals[label].update(counts)
            by_type[label][action.call_type].update(counts)
            row_cost = cost(counts, prices[model])
            if label == "baseline":
                baseline_cost += row_cost
            else:
                condition_cost += row_cost
            pair[label] = {
                "model": model,
                "input_tokens": inp,
                "cached_input_tokens": cached,
                "output_tokens": out,
                "cost_usd": format(row_cost, "f"),
                "completion_ms": float(row.get("completion_ms") or 0),
                "structural_valid": structural_valid(action.call_type, response_text(row)),
                "response_text": response_text(row),
            }
        pair["lexical_jaccard"] = round(lexical_jaccard(pair["baseline"]["response_text"], pair["candidate"]["response_text"]), 6)
        pairs.append(pair)

    saving = (baseline_cost - condition_cost) / baseline_cost * Decimal(100)
    call_types = sorted({action.call_type for action in actions})
    summary_by_type = {}
    for call_type in call_types:
        subset = [pair for pair in pairs if pair["call_type"] == call_type]
        base_counts, cand_counts = by_type["baseline"][call_type], by_type["candidate"][call_type]
        base_model = subset[0]["baseline"]["model"]
        cand_model = subset[0]["candidate"]["model"]
        base_cost = cost(base_counts, prices[base_model])
        cand_cost = cost(cand_counts, prices[cand_model])
        summary_by_type[call_type] = {
            "calls": len(subset),
            "baseline_cost_usd": format(base_cost, "f"),
            "candidate_cost_usd": format(cand_cost, "f"),
            "cost_saving_percent": float(round((base_cost - cand_cost) / base_cost * Decimal(100), 6)),
            "baseline_structural_pass_rate": round(sum(p["baseline"]["structural_valid"] for p in subset) / len(subset), 6),
            "candidate_structural_pass_rate": round(sum(p["candidate"]["structural_valid"] for p in subset) / len(subset), 6),
            "median_lexical_jaccard": round(median(p["lexical_jaccard"] for p in subset), 6),
        }

    result = {
        "schema_version": 1,
        "condition": args.condition,
        "lever": "L1_task_model_tier",
        "sample": str(args.sample).replace("\\", "/"),
        "sample_sha256": sample_sha,
        "paired_actions": len(pairs),
        "expected_actions": expected_actions,
        "condition_status": "stopped_on_failure" if candidate_failures or candidate_missing else "complete",
        "disqualified_by_failure": bool(candidate_failures),
        "failed_actions": [
            {
                "action_id": action_id_value,
                "call_type": row.get("call_type"),
                "error": row.get("error"),
            }
            for action_id_value, row in sorted(candidate_failures.items())
        ],
        "unattempted_action_ids": sorted(candidate_missing),
        "actual_api_calls_represented": len(pairs),
        "baseline_cost_usd": format(baseline_cost, "f"),
        "candidate_cost_usd": format(condition_cost, "f"),
        "cost_saving_percent": float(round(saving, 6)),
        "cost_comparison_scope": "complete_frozen_sample" if len(pairs) == expected_actions else "valid_paired_subset_only",
        "baseline_counts": dict(totals["baseline"]),
        "candidate_counts": dict(totals["candidate"]),
        "baseline_structural_pass_rate": round(sum(p["baseline"]["structural_valid"] for p in pairs) / len(pairs), 6),
        "candidate_structural_pass_rate": round(sum(p["candidate"]["structural_valid"] for p in pairs) / len(pairs), 6),
        "candidate_latency_ms": {
            "p50": percentile([p["candidate"]["completion_ms"] for p in pairs], 0.5),
            "p95": percentile([p["candidate"]["completion_ms"] for p in pairs], 0.95),
        },
        "by_call_type": summary_by_type,
        "quality_note": "Structural validity is deterministic. Lexical overlap is diagnostic only; semantic quality requires paired judging.",
        "pairs": pairs,
    }
    output = ROOT / "results" / "runs" / f"{args.condition}-paid-sample.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"condition": args.condition, "cost_saving_percent": result["cost_saving_percent"], "structural_pass_rate": result["candidate_structural_pass_rate"], "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
