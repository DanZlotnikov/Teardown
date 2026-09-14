from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from analysis.source_audit import PINNED_COMMIT, audit


PROJECT = Path(__file__).parents[1]
UPSTREAM = PROJECT.parent / "openwebui-upstream"


class SourceAuditTestCase(unittest.TestCase):
    @unittest.skipUnless(UPSTREAM.exists(), "pinned upstream checkout is not available")
    def test_all_seven_levers_are_checked_at_pinned_commit(self) -> None:
        report = audit(UPSTREAM)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["subject"]["commit"], PINNED_COMMIT)
        self.assertEqual(len(report["levers"]), 7)
        self.assertEqual(
            report["levers"]["L3_title_input_token_truncation"]["finding"],
            "unsupported_natively",
        )
        self.assertEqual(
            report["levers"]["L5_query_reuse"]["finding"],
            "supported_only_in_combined_middleware_path",
        )


if __name__ == "__main__":
    unittest.main()
