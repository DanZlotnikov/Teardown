from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

from eval.scoring import normalized_token_jaccard, parse_json_object, required_phrase_recall, retrieval_recall


PROJECT = Path(__file__).parents[1]


class EvalTestCase(unittest.TestCase):
    def test_frozen_eval_has_over_one_hundred_unique_cases(self) -> None:
        data = json.loads((PROJECT / "eval/cases.json").read_text(encoding="utf-8"))
        ids = [case["id"] for case in data["cases"]]
        self.assertGreaterEqual(len(ids), 100)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(data["temperature"], 0)

    def test_objective_scoring(self) -> None:
        self.assertEqual(parse_json_object('```json\n{"title":"Good"}\n```'), {"title": "Good"})
        self.assertEqual(required_phrase_recall("Alpha and Bravo", ["alpha", "charlie"]), 0.5)
        self.assertEqual(retrieval_recall(["a", "b"], ["b", "c"], 2), 0.5)
        self.assertAlmostEqual(normalized_token_jaccard("alpha beta", "beta gamma"), 1 / 3)

    def test_single_lever_matrix_changes_one_top_level_variable(self) -> None:
        matrix = yaml.safe_load((PROJECT / "configs/conditions.yaml").read_text(encoding="utf-8"))
        supported = 0
        for lever in matrix["single_lever_conditions"].values():
            for level in lever.get("levels", []):
                self.assertEqual(len(level["change"]), 1, level["id"])
                supported += 1
        self.assertEqual(supported, 14)
        self.assertEqual(
            matrix["single_lever_conditions"]["L3_title_input_truncation"]["status"],
            "unsupported",
        )


if __name__ == "__main__":
    unittest.main()
