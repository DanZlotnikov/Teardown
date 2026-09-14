"""Concurrency-safe API spend controls using the frozen pricing snapshot."""
from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, TypeVar

import yaml

T = TypeVar("T")
TERMINAL_STATUSES = {"success", "failed_with_usage", "failed_unknown_usage"}
_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


class BudgetStop(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    phase: str
    condition: str
    model: str
    attempt: int
    estimated_input_tokens: int
    reserved_input_tokens: int
    max_output_tokens: int
    worst_case_cost_usd: Decimal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BudgetGuard:
    def __init__(self, root: Path, config_path: Path | None = None):
        self.root = root.resolve()
        self.config_path = config_path or self.root / "config.yaml"
        self.config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.budget = self.config["budget"]
        self.models = self.config["pricing_snapshot"]["models"]
        paths = self.config["paths"]
        self.log_path = self.root / paths["spend_log"]
        self.total_path = self.root / paths["spend_total"]
        self.historical_path = self.root / paths["historical_spend"]
        self.lock_path = self.root / paths["budget_lock"]
        self.status_path = self.root / paths["budget_status"]
        self.smoke_config = self.budget["smoke_test"]
        self.smoke_dir = self.root / self.smoke_config["marker_directory"]
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.smoke_dir.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()
        if not self.historical_path.exists():
            raise RuntimeError(f"Required historical spend carry-forward is missing: {self.historical_path}")
        with self._locked():
            self._write_total_unlocked(self._running_total_unlocked(self._records_unlocked()))

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Serialize ledger decisions across threads and processes."""
        key = str(self.lock_path.resolve())
        with _PROCESS_LOCKS_GUARD:
            process_lock = _PROCESS_LOCKS.setdefault(key, threading.RLock())
        with process_lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    try:
                        yield
                    finally:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _records_unlocked(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            self.log_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid spend ledger JSON on line {line_number}") from exc
        return records

    def _historical(self) -> dict[str, Any]:
        data = json.loads(self.historical_path.read_text(encoding="utf-8"))
        phase_sum = sum(
            (Decimal(str(item["total_usd"])) for item in data["phases"].values()),
            Decimal("0"),
        )
        total = Decimal(str(data["total_usd"]))
        if phase_sum != total:
            raise RuntimeError(f"Historical phase totals ${phase_sum} do not reconcile to ${total}")
        if data.get("per_call_records_available") is not False:
            raise RuntimeError("Historical aggregate must disclose unavailable per-call records")
        return data

    @staticmethod
    def _actual_ledger_total(records: list[dict[str, Any]], phase: str | None = None) -> Decimal:
        return sum(
            (
                Decimal(str(row["computed_cost_usd"]))
                for row in records
                if row.get("status") in {"success", "failed_with_usage"}
                and row.get("computed_cost_usd") is not None
                and (phase is None or row.get("phase") == phase)
            ),
            Decimal("0"),
        )

    @staticmethod
    def _outstanding(records: list[dict[str, Any]], phase: str | None = None) -> Decimal:
        reservations = {
            row["reservation_id"]: row
            for row in records
            if row.get("status") == "reserved"
            and row.get("reservation_id")
            and (phase is None or row.get("phase") == phase)
        }
        terminals = {
            row["reservation_id"]: row
            for row in records
            if row.get("status") in TERMINAL_STATUSES and row.get("reservation_id")
        }
        total = Decimal("0")
        for reservation_id, reserved in reservations.items():
            terminal = terminals.get(reservation_id)
            if terminal is None or terminal.get("status") == "failed_unknown_usage":
                total += Decimal(str(reserved["reserved_worst_case_cost_usd"]))
        return total

    def _historical_total(self, phase: str | None = None) -> Decimal:
        historical = self._historical()
        if phase is None:
            return Decimal(str(historical["total_usd"]))
        item = historical["phases"].get(phase)
        return Decimal(str(item["total_usd"])) if item else Decimal("0")

    def _running_total_unlocked(self, records: list[dict[str, Any]]) -> Decimal:
        return self._historical_total() + self._actual_ledger_total(records)

    def running_total(self) -> Decimal:
        with self._locked():
            return self._running_total_unlocked(self._records_unlocked())

    def unresolved_reservations(self) -> Decimal:
        with self._locked():
            return self._outstanding(self._records_unlocked())

    def effective_total(self) -> Decimal:
        with self._locked():
            records = self._records_unlocked()
            return self._running_total_unlocked(records) + self._outstanding(records)

    def phase_total(self, phase: str) -> Decimal:
        with self._locked():
            records = self._records_unlocked()
            return self._historical_total(phase) + self._actual_ledger_total(records, phase)

    def compute_cost(self, model: str, usage: TokenUsage) -> Decimal:
        if model not in self.models:
            raise KeyError(f"No pinned pricing for model {model!r}")
        for name, value in asdict(usage).items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if usage.cached_input_tokens > usage.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        pricing = self.models[model]
        uncached = usage.input_tokens - usage.cached_input_tokens
        million = Decimal("1000000")
        return (
            Decimal(uncached) * Decimal(str(pricing["input"]))
            + Decimal(usage.cached_input_tokens) * Decimal(str(pricing["cached_input"]))
            + Decimal(usage.output_tokens) * Decimal(str(pricing["output"]))
        ) / million

    def _reserved_input_tokens(self, estimated_input_tokens: int) -> int:
        config = self.budget["reservation"]
        return math.ceil(
            estimated_input_tokens * float(config["input_token_multiplier"])
        ) + int(config["input_token_fixed_margin"])

    def _smoke_passed_unlocked(self, phase: str) -> bool:
        try:
            data = json.loads(self.smoke_marker_path(phase).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        required = {
            "mock_dry_run_passed",
            "paid_calls_persisted",
            "token_usage_present",
            "spend_log_reconciled",
            "resume_check_passed",
            "secrets_scan_passed",
        }
        return data.get("phase") == phase and all(data.get(key) is True for key in required)

    def smoke_marker_path(self, phase: str) -> Path:
        return self.smoke_dir / f"{phase}.passed.json"

    def smoke_passed(self, phase: str) -> bool:
        with self._locked():
            return self._smoke_passed_unlocked(phase)

    def _enforce_smoke_gate_unlocked(
        self,
        records: list[dict[str, Any]],
        *,
        phase: str,
        worst: Decimal,
    ) -> None:
        if not self.smoke_config.get("required_before_batch", True) or self._smoke_passed_unlocked(phase):
            return
        attempts = [
            row for row in records if row.get("phase") == phase and row.get("status") == "reserved"
        ]
        if len(attempts) >= int(self.smoke_config["max_calls_per_phase"]):
            raise BudgetStop(f"Smoke gate blocks additional {phase} calls until validation passes")
        ledger_phase_actual = self._actual_ledger_total(records, phase)
        ledger_phase_outstanding = self._outstanding(records, phase)
        if (
            ledger_phase_actual + ledger_phase_outstanding + worst
            > Decimal(str(self.smoke_config["max_cost_per_phase"]))
        ):
            raise BudgetStop("Smoke request could exceed smoke cap")

    def reserve_call(
        self,
        *,
        phase: str,
        condition: str,
        model: str,
        input_tokens: int,
        max_output_tokens: int,
        attempt: int,
    ) -> Reservation:
        if not condition.strip():
            raise ValueError("condition is required for every attempted call")
        if input_tokens < 0 or max_output_tokens < 0 or attempt < 1:
            raise ValueError("token estimates must be non-negative and attempt must be positive")
        with self._locked():
            if (self.root / "results/PAID-CALLS-BLOCKED").exists():
                raise BudgetStop(
                    "Paid calls blocked: historical per-call records were lost; "
                    "see results/BUDGET-STATUS.md"
                )
            if phase not in self.budget["phase_caps"]:
                raise KeyError(f"Unknown budget phase {phase!r}")
            records = self._records_unlocked()
            reserved_input = self._reserved_input_tokens(input_tokens)
            worst = self.compute_cost(model, TokenUsage(reserved_input, max_output_tokens))
            self._enforce_smoke_gate_unlocked(records, phase=phase, worst=worst)
            running = self._running_total_unlocked(records)
            outstanding = self._outstanding(records)
            effective = running + outstanding
            soft = Decimal(str(self.budget["soft_stop"]))
            hard = Decimal(str(self.budget["hard_stop"]))
            if effective >= soft and os.getenv("TEARDOWN_ALLOW_POST_SOFT_STOP") != "1":
                self._write_status_unlocked("Soft stop reached before request", records)
                raise BudgetStop(f"Soft stop reached: ${effective:.6f} >= ${soft}")
            if effective + worst > hard:
                self._write_status_unlocked("Request reservation could cross hard stop", records)
                raise BudgetStop("Request could cross hard stop")
            phase_cap = Decimal(str(self.budget["phase_caps"][phase]))
            multiplier = Decimal(str(self.budget["phase_overage_stop_multiplier"]))
            phase_exposure = (
                self._historical_total(phase)
                + self._actual_ledger_total(records, phase)
                + self._outstanding(records, phase)
            )
            if phase_exposure + worst > phase_cap * multiplier:
                self._write_status_unlocked(f"{phase} request could exceed 150% phase stop", records)
                raise BudgetStop(f"Phase stop would be crossed for {phase}")
            reservation = Reservation(
                reservation_id=str(uuid.uuid4()),
                phase=phase,
                condition=condition,
                model=model,
                attempt=attempt,
                estimated_input_tokens=input_tokens,
                reserved_input_tokens=reserved_input,
                max_output_tokens=max_output_tokens,
                worst_case_cost_usd=worst,
            )
            row = {
                "timestamp": _now(),
                "reservation_id": reservation.reservation_id,
                "phase": phase,
                "condition": condition,
                "model": model,
                "status": "reserved",
                "attempt": attempt,
                "input_tokens": None,
                "output_tokens": None,
                "cached_input_tokens": None,
                "estimated_input_tokens": input_tokens,
                "reserved_input_tokens": reserved_input,
                "max_output_tokens": max_output_tokens,
                "computed_cost_usd": None,
                "running_total_usd": str(running),
                "effective_exposure_usd": str(effective + worst),
                "reserved_worst_case_cost_usd": str(worst),
                "error": None,
            }
            self._append_unlocked(row)
            self._write_total_unlocked(running)
            return reservation

    def settle_call(
        self,
        reservation: Reservation,
        *,
        usage: TokenUsage | None,
        status: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"Invalid terminal status {status!r}")
        if status in {"success", "failed_with_usage"} and usage is None:
            raise ValueError(f"{status} requires reported token usage")
        if status == "failed_unknown_usage" and usage is not None:
            raise ValueError("failed_unknown_usage cannot include token usage")
        with self._locked():
            records = self._records_unlocked()
            reserved_rows = [
                row
                for row in records
                if row.get("reservation_id") == reservation.reservation_id
                and row.get("status") == "reserved"
            ]
            terminal_rows = [
                row
                for row in records
                if row.get("reservation_id") == reservation.reservation_id
                and row.get("status") in TERMINAL_STATUSES
            ]
            if len(reserved_rows) != 1:
                raise RuntimeError("Reservation is missing or duplicated")
            if terminal_rows:
                raise RuntimeError("Reservation has already been settled")
            cost = self.compute_cost(reservation.model, usage) if usage else None
            row = {
                "timestamp": _now(),
                "reservation_id": reservation.reservation_id,
                "phase": reservation.phase,
                "condition": reservation.condition,
                "model": reservation.model,
                "status": status,
                "attempt": reservation.attempt,
                "input_tokens": usage.input_tokens if usage else None,
                "output_tokens": usage.output_tokens if usage else None,
                "cached_input_tokens": usage.cached_input_tokens if usage else None,
                "estimated_input_tokens": reservation.estimated_input_tokens,
                "reserved_input_tokens": reservation.reserved_input_tokens,
                "max_output_tokens": reservation.max_output_tokens,
                "computed_cost_usd": str(cost) if cost is not None else None,
                "running_total_usd": None,
                "effective_exposure_usd": None,
                "reserved_worst_case_cost_usd": str(reservation.worst_case_cost_usd),
                "error": error,
            }
            prospective = records + [row]
            running = self._running_total_unlocked(prospective)
            effective = running + self._outstanding(prospective)
            row["running_total_usd"] = str(running)
            row["effective_exposure_usd"] = str(effective)
            self._append_unlocked(row)
            self._write_total_unlocked(running)
            if running >= Decimal(str(self.budget["hard_stop"])):
                self._write_status_unlocked("Hard stop reached", prospective)
                raise BudgetStop("Hard stop reached")
            if effective >= Decimal(str(self.budget["soft_stop"])):
                self._write_status_unlocked("Soft stop reached", prospective)
            return row

    def call_with_retries(
        self,
        *,
        phase: str,
        condition: str,
        model: str,
        input_tokens: int,
        max_output_tokens: int,
        call: Callable[[], tuple[T, TokenUsage]],
        sleep: Callable[[float], None] = time.sleep,
    ) -> T:
        retries = int(self.budget["max_retries"])
        for attempt in range(1, retries + 1):
            reservation = self.reserve_call(
                phase=phase,
                condition=condition,
                model=model,
                input_tokens=input_tokens,
                max_output_tokens=max_output_tokens,
                attempt=attempt,
            )
            try:
                result, usage = call()
            except Exception as exc:
                self.settle_call(
                    reservation,
                    usage=None,
                    status="failed_unknown_usage",
                    error=f"{type(exc).__name__}: {exc}",
                )
                if attempt == retries:
                    raise
                sleep(2 ** (attempt - 1))
                continue
            self.settle_call(reservation, usage=usage, status="success")
            return result
        raise AssertionError("unreachable")

    def write_smoke_marker(self, phase: str, checks: Mapping[str, bool]) -> Path:
        required = [
            "mock_dry_run_passed",
            "paid_calls_persisted",
            "token_usage_present",
            "spend_log_reconciled",
            "resume_check_passed",
            "secrets_scan_passed",
        ]
        missing = [key for key in required if checks.get(key) is not True]
        if missing:
            raise ValueError(f"Smoke test cannot pass; failed checks: {missing}")
        with self._locked():
            records = self._records_unlocked()
            paid = [
                row
                for row in records
                if row.get("phase") == phase and row.get("status") == "success"
            ]
            if not paid:
                raise ValueError("Smoke test cannot pass without a successful paid call")
            if len(paid) > int(self.smoke_config["max_calls_per_phase"]):
                raise ValueError("Smoke test exceeded its call limit")
            smoke_cost = self._actual_ledger_total(records, phase)
            if smoke_cost > Decimal(str(self.smoke_config["max_cost_per_phase"])):
                raise ValueError("Smoke test exceeded its spend limit")
            marker = {
                "phase": phase,
                "validated_at": _now(),
                "calls": len(paid),
                "cost_usd": str(smoke_cost),
                **{key: True for key in required},
            }
            target = self.smoke_marker_path(phase)
            self._atomic_text(target, json.dumps(marker, indent=2, sort_keys=True) + "\n")
            return target

    def progress(self, completed_calls: int, planned_calls: int | None = None) -> str | None:
        if (
            planned_calls is not None
            and planned_calls > int(self.budget["long_run_threshold_calls"])
            and completed_calls % int(self.budget["progress_every_calls"]) == 0
        ):
            return (
                f"calls={completed_calls}/{planned_calls} spend=${self.running_total():.6f} "
                f"exposure=${self.effective_total():.6f}"
            )
        return None

    def write_status(self, reason: str) -> None:
        with self._locked():
            records = self._records_unlocked()
            self._write_status_unlocked(reason, records)

    def _write_status_unlocked(self, reason: str, records: list[dict[str, Any]]) -> None:
        running = self._running_total_unlocked(records)
        effective = running + self._outstanding(records)
        phases = "\n".join(
            f"- `{phase}`: ${self._historical_total(phase) + self._actual_ledger_total(records, phase):.6f} / ${cap:.2f}"
            for phase, cap in self.budget["phase_caps"].items()
        )
        content = (
            f"# Budget status\n\n- Reason: {reason}\n"
            f"- Running measured total (including historical carry-forward): ${running:.6f}\n"
            f"- Effective budget exposure: ${effective:.6f}\n"
            "- Soft stop: $23.00\n- Hard stop: $30.00\n\n"
            f"## Phase totals\n\n{phases}\n\n"
            "## Work status\n\nPopulate this section from the run manifest before requesting approval.\n"
        )
        self._atomic_text(self.status_path, content)

    def _append_unlocked(self, row: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write_total_unlocked(self, total: Decimal) -> None:
        self._atomic_text(self.total_path, f"{total:.9f}\n")

    @staticmethod
    def _atomic_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
