from __future__ import annotations

import unittest

from analysis.summarize_terra_repeats import aggregate, percentile


def run(name: str, candidate_cost: str, completion_ms: float) -> dict:
    return {
        "condition": name,
        "paired_actions": 32,
        "baseline_cost_usd": "1.0",
        "candidate_cost_usd": candidate_cost,
        "cost_saving_percent": (1 - float(candidate_cost)) * 100,
        "baseline_counts": {"calls": 32, "input_tokens": 100, "output_tokens": 20},
        "candidate_counts": {"calls": 32, "input_tokens": 100, "output_tokens": 10},
        "pairs": [
            {
                "action_id": str(index),
                "call_type": "title",
                "baseline": {
                    "cost_usd": "0.03125",
                    "completion_ms": 2,
                    "structural_valid": True,
                },
                "candidate": {
                    "cost_usd": str(float(candidate_cost) / 32),
                    "completion_ms": completion_ms,
                    "structural_valid": True,
                },
            }
            for index in range(32)
        ],
    }


JUDGE = {
    "paired_actions": 32,
    "model": "judge",
    "systems": {
        "baseline": {"mean_composite": 4.5},
        "terra": {
            "mean_composite": 4.5,
            "mean_paired_delta_vs_baseline": 0,
            "paired_delta_bootstrap_95_percent_ci": [-0.1, 0.1],
            "noninferiority_margin_on_5_point_scale": 0.25,
            "passes_quality_guard": True,
        },
    },
}


class TerraRepeatSummaryTestCase(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(2.5, percentile([1, 2, 3, 4], 0.5))

    def test_aggregate_counts_all_three_runs(self):
        result = aggregate(
            [run("r1", "0.5", 1), run("r2", "0.4", 2), run("r3", "0.6", 3)],
            JUDGE,
        )
        self.assertEqual(50.0, result["cost_saving_percent"])
        self.assertEqual(96, result["candidate"]["structural_passes"])
        self.assertEqual(2.0, result["candidate"]["completion_latency_ms"]["p50"])
        self.assertTrue(result["semantic_quality"]["passes_quality_guard"])


if __name__ == "__main__":
    unittest.main()
