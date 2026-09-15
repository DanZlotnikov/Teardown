from __future__ import annotations

import unittest

from eval.run_native_compaction import chat_payload, find_context_summaries


class NativeCompactionEvalTestCase(unittest.TestCase):
    def test_chat_payload_is_a_linked_saved_branch(self):
        case = {
            "id": "context-1",
            "input": {"messages": [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"}]},
        }
        payload, final = chat_payload(case, "model")
        messages = payload["chat"]["history"]["messages"]
        self.assertEqual(final["id"], payload["chat"]["history"]["currentId"])
        self.assertEqual(final["id"], messages[next(iter(messages))]["childrenIds"][0])

    def test_summary_finder_requires_nonempty_persisted_text(self):
        value = {"a": [{"contextSummary": "kept"}, {"context_summary": ""}]}
        self.assertEqual(["kept"], find_context_summaries(value))


if __name__ == "__main__":
    unittest.main()
