from __future__ import annotations

import unittest

from analysis.summarize_paid_sample import lexical_jaccard, parse_json_text, structural_valid


class PaidSampleSummaryTestCase(unittest.TestCase):
    def test_json_fence_is_tolerated(self):
        self.assertEqual({"tags": ["one"]}, parse_json_text('```json\n{"tags":["one"]}\n```'))

    def test_structural_schemas(self):
        self.assertTrue(structural_valid("follow_up", '{"follow_ups":["a","b","c"]}'))
        self.assertTrue(structural_valid("title", '{"title":"Useful title"}'))
        self.assertTrue(structural_valid("tags", '{"tags":["one"]}'))
        self.assertTrue(structural_valid("retrieval_query", '{"queries":["one"]}'))
        self.assertTrue(structural_valid("autocomplete", '{"text":"one"}'))
        self.assertFalse(structural_valid("follow_up", '{"follow_ups":["a"]}'))

    def test_lexical_jaccard(self):
        self.assertAlmostEqual(1 / 3, lexical_jaccard("one two", "two three"))


if __name__ == "__main__":
    unittest.main()
