"""Summarize paired blind judge scores with a deterministic bootstrap interval."""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).parents[1]
SYSTEMS = ("baseline", "terra", "luna")
SCORE_KEYS = ("task_compliance", "topical_relevance", "usefulness")


def composite(scores: dict) -> float:
    return mean(float(scores[key]) for key in SCORE_KEYS)


def bootstrap_ci(differences: list[float], seed: int = 0, repetitions: int = 10000) -> tuple[float, float]:
    generator = random.Random(seed)
    estimates = sorted(mean(generator.choice(differences) for _ in differences) for _ in range(repetitions))
    return estimates[int(0.025 * repetitions)], estimates[int(0.975 * repetitions)]


def main() -> None:
    manifest = ROOT / "results" / "judge" / "judge-l1-task-model-tier.jsonl"
    latest = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("judgment_valid"):
            latest[row["action_id"]] = row
    if len(latest) != 32:
        raise RuntimeError(f"Expected 32 valid paired judgments, found {len(latest)}")

    scores = defaultdict(list)
    by_type = defaultdict(lambda: defaultdict(list))
    paired_differences = defaultdict(list)
    for row in latest.values():
        reverse = {logical: label for label, logical in row["blind_mapping"].items()}
        values = {}
        for system in SYSTEMS:
            value = composite(row["judgment"][reverse[system]])
            values[system] = value
            scores[system].append(value)
            by_type[row["call_type"]][system].append(value)
        for candidate in ("terra", "luna"):
            paired_differences[candidate].append(values[candidate] - values["baseline"])

    paid_summaries = {
        "terra": json.loads((ROOT / "results" / "runs" / "l1-mid-hosted-paid-sample.json").read_text(encoding="utf-8")),
        "luna": json.loads((ROOT / "results" / "runs" / "l1-small-hosted-paid-sample.json").read_text(encoding="utf-8")),
    }
    margin = 0.25
    systems = {"baseline": {"mean_composite": round(mean(scores["baseline"]), 6)}}
    for candidate in ("terra", "luna"):
        differences = paired_differences[candidate]
        low, high = bootstrap_ci(differences)
        structural = float(paid_summaries[candidate]["candidate_structural_pass_rate"])
        systems[candidate] = {
            "mean_composite": round(mean(scores[candidate]), 6),
            "mean_paired_delta_vs_baseline": round(mean(differences), 6),
            "paired_delta_bootstrap_95_percent_ci": [round(low, 6), round(high, 6)],
            "higher_equal_lower_counts": {
                "higher": sum(value > 0 for value in differences),
                "equal": sum(value == 0 for value in differences),
                "lower": sum(value < 0 for value in differences),
            },
            "structural_pass_rate": structural,
            "noninferiority_margin_on_5_point_scale": margin,
            "passes_quality_guard": low >= -margin and structural == 1.0,
        }

    call_types = {}
    for call_type, values in sorted(by_type.items()):
        call_types[call_type] = {
            system: round(mean(values[system]), 6) for system in SYSTEMS
        }
    result = {
        "schema_version": 1,
        "condition": "judge-l1-task-model-tier",
        "model": "gpt-4o-2024-11-20",
        "method": "32 action-level blinded three-way judgments with label order rotated by action ID",
        "score_scale": "Mean of task compliance, topical relevance, and usefulness; each 1-5",
        "paired_actions": 32,
        "systems": systems,
        "mean_composite_by_call_type": call_types,
        "interpretation": "A candidate passes only if the paired bootstrap lower bound is at least -0.25 and all outputs pass deterministic structural validation.",
    }
    output = ROOT / "results" / "runs" / "l1-task-model-tier-judge.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "systems": systems}, sort_keys=True))


if __name__ == "__main__":
    main()
