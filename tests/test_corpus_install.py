from __future__ import annotations

import unittest

from scenario.install_corpus import extract_doc_ids


class CorpusInstallTestCase(unittest.TestCase):
    def test_extracts_document_ids_from_metadata_and_content(self) -> None:
        response = {
            "documents": [["[DOC_ID:task-model] text", "other"]],
            "metadatas": [[{"name": "teardown:budget"}, {"name": "unrelated"}]],
        }
        self.assertEqual(extract_doc_ids(response), ["task-model", "budget"])


if __name__ == "__main__":
    unittest.main()
