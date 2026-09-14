from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

import yaml

from analysis.budget import BudgetGuard, BudgetStop, TokenUsage


PROJECT = Path(__file__).parents[1]


class BudgetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "results").mkdir()
        shutil.copy2(PROJECT / "config.yaml", self.root / "config.yaml")
        shutil.copy2(
            PROJECT / "results/historical-spend.json",
            self.root / "results/historical-spend.json",
        )
        (self.root / "results/spend-log.jsonl").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def config(self, mutate=None) -> None:
        path = self.root / "config.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if mutate:
            mutate(data)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def guard(self, blocked: bool = False) -> BudgetGuard:
        marker = self.root / "results/PAID-CALLS-BLOCKED"
        if blocked:
            marker.write_text("test blocker\n", encoding="utf-8")
        return BudgetGuard(self.root)

    def test_historical_carry_forward_is_in_every_total(self) -> None:
        guard = self.guard()
        self.assertEqual(guard.running_total(), Decimal("0.067766300"))
        self.assertEqual(guard.effective_total(), Decimal("0.067766300"))
        self.assertEqual(guard.phase_total("baseline"), Decimal("0.066599100"))
        self.assertEqual(guard.phase_total("optimized"), Decimal("0.000368400"))
        self.assertEqual(
            (self.root / "results/spend-total.txt").read_text().strip(),
            "0.067766300",
        )

    def test_frozen_price_math_handles_cached_input(self) -> None:
        guard = self.guard()
        cost = guard.compute_cost(
            "gpt-4o-mini", TokenUsage(1000, 100, cached_input_tokens=200)
        )
        self.assertEqual(cost, Decimal("0.000195"))

    def test_section_10_budget_policy_is_exact(self) -> None:
        guard = self.guard()
        self.assertEqual(Decimal(str(guard.budget["soft_stop"])), Decimal("15.0"))
        self.assertEqual(Decimal(str(guard.budget["hard_stop"])), Decimal("20.0"))
        self.assertEqual(
            guard.budget["phase_caps"],
            {
                "baseline": 3.0,
                "optimized": 1.0,
                "quality_eval": 12.0,
                "judge": 2.0,
                "contingency": 2.0,
            },
        )

    def test_status_uses_configured_stops(self) -> None:
        guard = self.guard()
        guard.write_status("policy-test")
        status = guard.status_path.read_text(encoding="utf-8")
        self.assertIn("Soft stop: $15.00", status)
        self.assertIn("Hard stop: $20.00", status)
        self.assertNotIn("$23.00", status)
        self.assertNotIn("$30.00", status)

    def test_soft_stop_requires_durable_authorization_marker(self) -> None:
        def mutate(data):
            data["budget"]["smoke_test"]["required_before_batch"] = False
            data["budget"]["soft_stop"] = 0.01

        self.config(mutate)
        guard = self.guard()
        os.environ["TEARDOWN_ALLOW_POST_SOFT_STOP"] = "1"
        try:
            with self.assertRaisesRegex(BudgetStop, "authorization marker required"):
                guard.reserve_call(
                    phase="contingency",
                    condition="soft-stop-without-marker",
                    model="gpt-4o-mini",
                    input_tokens=1,
                    max_output_tokens=1,
                    attempt=1,
                )
        finally:
            os.environ.pop("TEARDOWN_ALLOW_POST_SOFT_STOP", None)
        guard.post_soft_stop_auth_path.write_text("explicit test authorization\n", encoding="utf-8")
        reservation = guard.reserve_call(
            phase="contingency",
            condition="soft-stop-with-marker",
            model="gpt-4o-mini",
            input_tokens=1,
            max_output_tokens=1,
            attempt=1,
        )
        self.assertIsNotNone(reservation.reservation_id)

    def test_blocker_prevents_persisted_reservation(self) -> None:
        guard = self.guard(blocked=True)
        with self.assertRaises(BudgetStop):
            guard.reserve_call(
                phase="baseline",
                condition="blocked",
                model="gpt-4o-mini",
                input_tokens=10,
                max_output_tokens=10,
                attempt=1,
            )
        self.assertEqual((self.root / "results/spend-log.jsonl").read_text(), "")

    def test_success_is_reserved_before_it_is_settled(self) -> None:
        self.config(lambda d: d["budget"]["smoke_test"].update(required_before_batch=False))
        guard = self.guard()
        reservation = guard.reserve_call(
            phase="contingency",
            condition="unit-success",
            model="gpt-4o-mini",
            input_tokens=100,
            max_output_tokens=20,
            attempt=1,
        )
        self.assertEqual(guard.unresolved_reservations(), reservation.worst_case_cost_usd)
        row = guard.settle_call(
            reservation,
            usage=TokenUsage(90, 8, 10),
            status="success",
        )
        actual = guard.compute_cost("gpt-4o-mini", TokenUsage(90, 8, 10))
        self.assertEqual(row["condition"], "unit-success")
        self.assertEqual(guard.unresolved_reservations(), Decimal("0"))
        self.assertEqual(guard.running_total(), Decimal("0.067766300") + actual)
        records = [json.loads(line) for line in guard.log_path.read_text().splitlines()]
        self.assertEqual([record["status"] for record in records], ["reserved", "success"])
        self.assertEqual(records[0]["reservation_id"], records[1]["reservation_id"])

    def test_unknown_failure_keeps_worst_case_exposure(self) -> None:
        self.config(lambda d: d["budget"]["smoke_test"].update(required_before_batch=False))
        guard = self.guard()
        reservation = guard.reserve_call(
            phase="contingency",
            condition="unit-failure",
            model="gpt-4o-mini",
            input_tokens=100,
            max_output_tokens=20,
            attempt=1,
        )
        guard.settle_call(
            reservation,
            usage=None,
            status="failed_unknown_usage",
            error="timeout",
        )
        self.assertEqual(guard.running_total(), Decimal("0.067766300"))
        self.assertEqual(guard.unresolved_reservations(), reservation.worst_case_cost_usd)

    def test_phase_stop_accounts_for_historical_spend(self) -> None:
        def mutate(data):
            data["budget"]["smoke_test"]["required_before_batch"] = False
            data["budget"]["phase_caps"]["baseline"] = 0.04

        self.config(mutate)
        guard = self.guard()
        with self.assertRaisesRegex(BudgetStop, "Phase stop"):
            guard.reserve_call(
                phase="baseline",
                condition="phase-cap",
                model="gpt-4o-mini",
                input_tokens=1,
                max_output_tokens=1,
                attempt=1,
            )

    def test_concurrent_preflight_cannot_overbook_hard_cap(self) -> None:
        def mutate(data):
            data["budget"]["smoke_test"]["required_before_batch"] = False
            data["budget"]["hard_stop"] = 0.070

        self.config(mutate)
        guard = self.guard()
        barrier = threading.Barrier(8)
        accepted = []
        rejected = []

        def worker(index: int) -> None:
            barrier.wait()
            try:
                reservation = guard.reserve_call(
                    phase="contingency",
                    condition=f"thread-{index}",
                    model="gpt-5.6-sol",
                    input_tokens=0,
                    max_output_tokens=40,
                    attempt=1,
                )
                accepted.append(reservation)
            except BudgetStop as exc:
                rejected.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertGreater(len(accepted), 0)
        self.assertGreater(len(rejected), 0)
        self.assertLessEqual(guard.effective_total(), Decimal("0.070"))
        ids = {reservation.reservation_id for reservation in accepted}
        self.assertEqual(len(ids), len(accepted))

    def test_retries_are_bounded_and_each_unknown_attempt_stays_reserved(self) -> None:
        self.config(lambda d: d["budget"]["smoke_test"].update(required_before_batch=False))
        guard = self.guard()
        calls = 0

        def fail():
            nonlocal calls
            calls += 1
            raise TimeoutError("unknown provider state")

        with self.assertRaises(TimeoutError):
            guard.call_with_retries(
                phase="contingency",
                condition="retry-test",
                model="gpt-4o-mini",
                input_tokens=10,
                max_output_tokens=10,
                call=fail,
                sleep=lambda _: None,
            )
        self.assertEqual(calls, 3)
        records = [json.loads(line) for line in guard.log_path.read_text().splitlines()]
        self.assertEqual(len(records), 6)
        self.assertEqual(sum(row["status"] == "reserved" for row in records), 3)
        self.assertGreater(guard.unresolved_reservations(), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
