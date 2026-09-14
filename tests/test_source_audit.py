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
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["subject"]["commit"], PINNED_COMMIT)
        self.assertEqual(len(report["levers"]), 7)
        self.assertEqual(len(report["hypotheses"]), 6)
        self.assertEqual(report["stop_rule"]["already_fixed_count"], 2)
        self.assertFalse(report["stop_rule"]["threshold_exceeded"])
        self.assertEqual(report["stop_rule"]["decision"], "continue")
        self.assertEqual(
            report["hypotheses"]["H2_some_task_calls_have_no_output_cap"]["finding"],
            "supported_with_title_caveat",
        )
        self.assertEqual(
            report["hypotheses"]["H5_autocomplete_fires_on_every_keystroke"]["finding"],
            "already_fixed",
        )
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
