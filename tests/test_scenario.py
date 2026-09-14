from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from scenario.run import Action, build_actions, cache_key, valid_row


PROJECT = Path(__file__).parents[1]


class ScenarioTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads((PROJECT / "scenario/cases.json").read_text(encoding="utf-8"))

    def test_fixture_and_action_counts_are_frozen(self) -> None:
        self.assertEqual(len(self.data["conversations"]), 30)
        user_turns = sum(
            message["role"] == "user"
            for conversation in self.data["conversations"]
            for message in conversation["messages"]
        )
        self.assertEqual(user_turns, 129)
        baseline = build_actions(self.data, "gpt-4o-mini", "baseline")
        optimized = build_actions(self.data, "gpt-4o-mini", "optimized")
        self.assertEqual(len(baseline), 329)
        self.assertEqual(len(optimized), 327)
        self.assertEqual(Counter(action.call_type for action in baseline)["autocomplete"], 2)

    def test_cache_key_binds_condition_scenario_and_payload(self) -> None:
        action = Action("case", "title", "/endpoint", {"model": "m"})
        base = cache_key("paid", "baseline", "scenario-a", "baseline", action)
        self.assertNotEqual(
            base, cache_key("paid", "different", "scenario-a", "baseline", action)
        )
        self.assertNotEqual(
            base, cache_key("paid", "baseline", "scenario-b", "baseline", action)
        )

    def test_valid_cache_row_does_not_require_manifest_presence(self) -> None:
        row = {"cache_key": "abc", "response": {"ok": True}, "error": None}
        self.assertTrue(valid_row(row, "abc"))
        self.assertFalse(valid_row(row, "different"))
        self.assertFalse(valid_row({**row, "error": "failed"}, "abc"))


if __name__ == "__main__":
    unittest.main()
