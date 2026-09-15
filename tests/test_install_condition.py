from __future__ import annotations

import unittest

from configs.install_condition import resolve_condition


class InstallConditionTestCase(unittest.TestCase):
    def test_baseline_is_exactly_the_frozen_baseline(self):
        state, diff = resolve_condition("baseline")
        self.assertEqual("main_chat_model", state["task_model"])
        self.assertEqual({}, state["task_model_params"])
        self.assertEqual(3, state["rag_top_k"])
        self.assertTrue(state["autocomplete"])
        self.assertIsNone(diff["lever"])

    def test_each_level_changes_only_its_declared_top_level_keys(self):
        baseline, _ = resolve_condition("baseline")
        for condition in (
            "l1-local-ollama",
            "l2-cap-512",
            "l2-cap-128",
            "l2-cap-32",
            "l4-last-10-turns",
            "l4-last-6-turns",
            "l4-last-3-turns",
            "l4-native-compaction",
            "l5-query-reuse-on",
            "l6-top-k-2",
            "l6-top-k-1",
            "l7-autocomplete-off",
        ):
            state, metadata = resolve_condition(condition)
            changed = {key for key in baseline if baseline[key] != state[key]}
            self.assertEqual(set(metadata["change"]), changed, condition)


if __name__ == "__main__":
    unittest.main()
