from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Literal

from otelgen.model import LogSignal, MetricSignal, Signal

SignalKind = Literal["log", "metric", "span"]
DeliveryPath = Literal["otlp", "direct", "unknown"]


def _kind_of(signal: Signal) -> SignalKind:
    if isinstance(signal, LogSignal):
        return "log"
    if isinstance(signal, MetricSignal):
        return "metric"
    return "span"


class RunReporter:
    """Accumulates per-signal-kind counts and delivery outcomes for a run."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {"log": 0, "metric": 0, "span": 0}
        self._success: dict[str, int] = {"log": 0, "metric": 0, "span": 0}
        self._failure: dict[str, int] = {"log": 0, "metric": 0, "span": 0}
        self._delivery_counts: dict[str, int] = {}
        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None
        self._errors: list[str] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._started_at = datetime.now(timezone.utc)

    def end(self) -> None:
        self._ended_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_emitted(self, signal: Signal, delivery: str = "unknown") -> None:
        kind = _kind_of(signal)
        self._counts[kind] += 1
        self._success[kind] += 1
        self._delivery_counts[delivery] = self._delivery_counts.get(delivery, 0) + 1

    def record_failed(self, signal: Signal, error: str, delivery: str = "unknown") -> None:
        kind = _kind_of(signal)
        self._counts[kind] += 1
        self._failure[kind] += 1
        self._errors.append(f"[{kind}][{delivery}] {error}")

    def record_error(self, message: str) -> None:
        self._errors.append(message)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        duration_s: float | None = None
        if self._started_at and self._ended_at:
            duration_s = (self._ended_at - self._started_at).total_seconds()

        return {
            "counts": dict(self._counts),
            "success": dict(self._success),
            "failure": dict(self._failure),
            "delivery": dict(self._delivery_counts),
            "duration_seconds": duration_s,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "errors": list(self._errors),
        }

    def render(self) -> None:
        s = self.summary()
        print("=" * 60, file=sys.stdout)
        print("OTel Generator — Run Summary", file=sys.stdout)
        print("=" * 60, file=sys.stdout)
        print(f"  Started:  {s['started_at']}", file=sys.stdout)
        print(f"  Ended:    {s['ended_at']}", file=sys.stdout)
        print(f"  Duration: {s['duration_seconds']:.1f}s", file=sys.stdout)
        print("", file=sys.stdout)
        print("  Signal counts (total / success / failure):", file=sys.stdout)
        for kind in ("log", "metric", "span"):
            print(
                f"    {kind:8s}  {s['counts'][kind]:>8d}  "
                f"{s['success'][kind]:>8d}  {s['failure'][kind]:>8d}",
                file=sys.stdout,
            )
        print("", file=sys.stdout)
        print("  Delivery breakdown:", file=sys.stdout)
        for path, count in s["delivery"].items():
            print(f"    {path}: {count}", file=sys.stdout)
        if s["errors"]:
            print("", file=sys.stdout)
            print(f"  Errors ({len(s['errors'])}):", file=sys.stdout)
            for err in s["errors"][:20]:
                print(f"    - {err}", file=sys.stdout)
            if len(s["errors"]) > 20:
                print(f"    ... and {len(s['errors']) - 20} more", file=sys.stdout)
        print("=" * 60, file=sys.stdout)

    @property
    def exit_code(self) -> int:
        """Return 0 on a fully successful run; non-zero if any signals failed."""
        total_failures = sum(self._failure.values())
        return 0 if total_failures == 0 and not self._errors else 1
