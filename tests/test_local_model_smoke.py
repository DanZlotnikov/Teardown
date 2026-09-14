from __future__ import annotations

import unittest

from analysis.local_model_smoke import CASES


class LocalModelSmokeTestCase(unittest.TestCase):
    def test_smoke_covers_each_required_task_shape(self) -> None:
        self.assertEqual(
            {call_type for call_type, _ in CASES},
            {"title", "tags", "retrieval_query", "autocomplete"},
        )
        self.assertTrue(all(prompt.strip() for _, prompt in CASES))


if __name__ == "__main__":
    unittest.main()
