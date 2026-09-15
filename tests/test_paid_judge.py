from __future__ import annotations

import unittest

from analysis.run_paid_judge import validate_judgment
from analysis.summarize_paid_judge import bootstrap_ci, composite


class PaidJudgeTestCase(unittest.TestCase):
    def test_judgment_schema(self):
        value = {
            label: {"task_compliance": 5, "topical_relevance": 4, "usefulness": 3}
            for label in ("A", "B", "C")
        }
        value.update({"ranking": ["B", "A", "C"], "reason": "concise"})
        self.assertTrue(validate_judgment(value))
        value["A"]["task_compliance"] = 0
        self.assertFalse(validate_judgment(value))

    def test_composite_and_bootstrap(self):
        self.assertEqual(4, composite({"task_compliance": 5, "topical_relevance": 4, "usefulness": 3}))
        self.assertEqual((1.0, 1.0), bootstrap_ci([1.0, 1.0], repetitions=100))


if __name__ == "__main__":
    unittest.main()
