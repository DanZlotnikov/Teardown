from __future__ import annotations

import json
import multiprocessing
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import yaml

from analysis.budget import BudgetGuard, BudgetStop


PROJECT = Path(__file__).parents[1]


def reserve_worker(root: str, index: int, queue) -> None:
    guard = BudgetGuard(Path(root))
    try:
        reservation = guard.reserve_call(
            phase="contingency",
            condition=f"process-{index}",
            model="gpt-5.6-sol",
            input_tokens=0,
            max_output_tokens=40,
            attempt=1,
        )
        queue.put(("accepted", reservation.reservation_id))
    except BudgetStop as exc:
        queue.put(("rejected", str(exc)))


class BudgetProcessTestCase(unittest.TestCase):
    def test_processes_cannot_overbook_hard_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "results").mkdir()
            config = yaml.safe_load((PROJECT / "config.yaml").read_text(encoding="utf-8"))
            config["budget"]["smoke_test"]["required_before_batch"] = False
            config["budget"]["hard_stop"] = 0.070
            (root / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            shutil.copy2(PROJECT / "results/historical-spend.json", root / "results/historical-spend.json")
            (root / "results/spend-log.jsonl").write_text("", encoding="utf-8")
            context = multiprocessing.get_context("spawn")
            queue = context.Queue()
            processes = [context.Process(target=reserve_worker, args=(str(root), index, queue)) for index in range(4)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)
                self.assertEqual(process.exitcode, 0)
            results = [queue.get(timeout=5) for _ in processes]
            accepted = [value for status, value in results if status == "accepted"]
            rejected = [value for status, value in results if status == "rejected"]
            guard = BudgetGuard(root)
            self.assertEqual(len(accepted), 1)
            self.assertEqual(len(rejected), 3)
            self.assertLessEqual(guard.effective_total(), Decimal("0.070"))
            records = [json.loads(line) for line in guard.log_path.read_text().splitlines()]
            self.assertEqual(sum(row["status"] == "reserved" for row in records), 1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
