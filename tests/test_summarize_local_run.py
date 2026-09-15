from __future__ import annotations

import unittest

from analysis.summarize_local_run import compose_rows, percentile


class SummarizeLocalRunTestCase(unittest.TestCase):
    def test_condition_rows_replace_only_matching_occurrences(self):
        baseline = [
            {"conversation_id": "c", "call_type": "main", "value": 1},
            {"conversation_id": "c", "call_type": "title", "value": 2},
            {"conversation_id": "c", "call_type": "main", "value": 3},
        ]
        condition = [
            {"conversation_id": "c", "call_type": "main", "value": 10},
            {"conversation_id": "c", "call_type": "main", "value": 30},
        ]
        self.assertEqual([10, 2, 30], [row["value"] for row in compose_rows(condition, baseline, set())])

    def test_drop_call_type_changes_full_scenario_count(self):
        baseline = [
            {"conversation_id": "c", "call_type": "main"},
            {"conversation_id": "c", "call_type": "autocomplete"},
        ]
        self.assertEqual(1, len(compose_rows([], baseline, {"autocomplete"})))

    def test_percentile_is_interpolated(self):
        self.assertEqual(2.5, percentile([1, 2, 3, 4], 0.5))


if __name__ == "__main__":
    unittest.main()
