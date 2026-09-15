from __future__ import annotations

import unittest

from eval.run_local import payload_and_endpoint


class LocalEvalTestCase(unittest.TestCase):
    def test_query_type_uses_real_task_endpoint(self):
        case = {"call_type": "web_query", "input": {"messages": [{"role": "user", "content": "x"}]}}
        endpoint, payload = payload_and_endpoint(case, "model", "collection", 3)
        self.assertEqual("/api/v1/tasks/queries/completions", endpoint)
        self.assertEqual("web_search", payload["type"])

    def test_retrieval_uses_controlled_collection_and_k(self):
        case = {"call_type": "retrieval", "input": {"query": "x"}}
        endpoint, payload = payload_and_endpoint(case, "model", "fixed", 2)
        self.assertEqual("/api/v1/retrieval/query/collection", endpoint)
        self.assertEqual(["fixed"], payload["collection_names"])
        self.assertEqual(2, payload["k"])


if __name__ == "__main__":
    unittest.main()
