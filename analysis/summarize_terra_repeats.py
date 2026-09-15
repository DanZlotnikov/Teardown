"""Aggregate the three frozen hosted Terra task-model repetitions."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import mean, pstdev


ROOT = Path(__file__).parents[1]
RUN_NAMES = ("l1-mid-hosted", "l1-mid-hosted-r2", "l1-mid-hosted-r3")


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower), 3)


def aggregate(runs: list[dict], judge: dict) -> dict:
    if len(runs) != 3:
        raise ValueError("Exactly three repetitions are required")
    if any(run.get("paired_actions") != 32 for run in runs):
        raise ValueError("Every repetition must contain the full 32-action sample")

    action_ids = [{pair["action_id"] for pair in run["pairs"]} for run in runs]
    if any(ids != action_ids[0] for ids in action_ids[1:]):
        raise ValueError("Repetitions do not contain identical frozen actions")

    costs = {
        label: [Decimal(run[f"{label}_cost_usd"]) for run in runs]
        for label in ("baseline", "candidate")
    }
    total_baseline = sum(costs["baseline"], Decimal(0))
    total_candidate = sum(costs["candidate"], Decimal(0))
    total_saving = (total_baseline - total_candidate) / total_baseline * Decimal(100)
    repeat_savings = [float(run["cost_saving_percent"]) for run in runs]

    structure = {"baseline": 0, "candidate": 0}
    latency: dict[str, list[float]] = {"baseline": [], "candidate": []}
    tokens: dict[str, Counter] = {"baseline": Counter(), "candidate": Counter()}
    by_type: dict[str, dict[str, Counter]] = defaultdict(
        lambda: {"baseline": Counter(), "candidate": Counter()}
    )
    for run in runs:
        for label in ("baseline", "candidate"):
            tokens[label].update(run[f"{label}_counts"])
        for pair in run["pairs"]:
            for label in ("baseline", "candidate"):
                item = pair[label]
                structure[label] += int(item["structural_valid"])
                latency[label].append(float(item["completion_ms"]))
                by_type[pair["call_type"]][label]["calls"] += 1
                by_type[pair["call_type"]][label]["cost_micro_usd"] += int(
                    Decimal(item["cost_usd"]) * Decimal(1_000_000)
                )
                by_type[pair["call_type"]][label]["structural_valid"] += int(
                    item["structural_valid"]
                )

    type_summary = {}
    for call_type, labels in sorted(by_type.items()):
        baseline_cost = Decimal(labels["baseline"]["cost_micro_usd"]) / Decimal(1_000_000)
        candidate_cost = Decimal(labels["candidate"]["cost_micro_usd"]) / Decimal(1_000_000)
        calls = labels["candidate"]["calls"]
        type_summary[call_type] = {
            "calls_across_repetitions": calls,
            "baseline_cost_usd": format(baseline_cost, "f"),
            "candidate_cost_usd": format(candidate_cost, "f"),
            "cost_saving_percent": float(
                round((baseline_cost - candidate_cost) / baseline_cost * Decimal(100), 6)
            ),
            "candidate_structural_pass_rate": round(
                labels["candidate"]["structural_valid"] / calls, 6
            ),
        }

    terra_judge = judge["systems"]["terra"]
    return {
        "schema_version": 1,
        "condition": "l1-mid-hosted-three-repetition-aggregate",
        "lever": "L1_task_model_tier",
        "baseline_model": "gpt-5.6-sol",
        "candidate_model": "gpt-5.6-terra",
        "main_chat_path_touched": False,
        "run_count": len(runs),
        "conditions": [run["condition"] for run in runs],
        "paired_actions_per_run": 32,
        "paired_actions_across_repetitions": 96,
        "identical_action_set_across_repetitions": True,
        "baseline": {
            "total_cost_usd": format(total_baseline, "f"),
            "mean_cost_per_run_usd": format(total_baseline / len(runs), "f"),
            "counts": dict(tokens["baseline"]),
            "structural_passes": structure["baseline"],
            "structural_pass_rate": structure["baseline"] / 96,
            "completion_latency_ms": {
                "p50": percentile(latency["baseline"], 0.5),
                "p95": percentile(latency["baseline"], 0.95),
            },
        },
        "candidate": {
            "total_cost_usd": format(total_candidate, "f"),
            "mean_cost_per_run_usd": format(total_candidate / len(runs), "f"),
            "counts": dict(tokens["candidate"]),
            "structural_passes": structure["candidate"],
            "structural_pass_rate": structure["candidate"] / 96,
            "completion_latency_ms": {
                "p50": percentile(latency["candidate"], 0.5),
                "p95": percentile(latency["candidate"], 0.95),
            },
        },
        "cost_saving_percent": float(round(total_saving, 6)),
        "repeat_cost_saving_percent": {
            "values": repeat_savings,
            "mean": round(mean(repeat_savings), 6),
            "population_sd": round(pstdev(repeat_savings), 6),
            "min": min(repeat_savings),
            "max": max(repeat_savings),
        },
        "semantic_quality": {
            "judged_repetition": runs[0]["condition"],
            "paired_actions": judge["paired_actions"],
            "judge_model": judge["model"],
            "baseline_mean_composite": judge["systems"]["baseline"]["mean_composite"],
            "candidate_mean_composite": terra_judge["mean_composite"],
            "mean_paired_delta_vs_baseline": terra_judge["mean_paired_delta_vs_baseline"],
            "paired_delta_bootstrap_95_percent_ci": terra_judge[
                "paired_delta_bootstrap_95_percent_ci"
            ],
            "noninferiority_margin_on_5_point_scale": terra_judge[
                "noninferiority_margin_on_5_point_scale"
            ],
            "passes_quality_guard": terra_judge["passes_quality_guard"],
            "note": "Semantic judging covers repetition 1; repetitions 2 and 3 add cost, latency, and structural reliability evidence.",
        },
        "by_call_type": type_summary,
        "ttft": None,
        "latency_note": "Task endpoints were nonstreaming, so completion latency is measured and TTFT is unavailable.",
    }


def main() -> None:
    runs = [
        json.loads((ROOT / "results" / "runs" / f"{name}-paid-sample.json").read_text(encoding="utf-8"))
        for name in RUN_NAMES
    ]
    judge = json.loads(
        (ROOT / "results" / "runs" / "l1-task-model-tier-judge.json").read_text(encoding="utf-8")
    )
    result = aggregate(runs, judge)
    output = ROOT / "results" / "runs" / "l1-mid-hosted-three-repetition-aggregate.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "cost_saving_percent": result["cost_saving_percent"],
                "structural_passes": result["candidate"]["structural_passes"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
