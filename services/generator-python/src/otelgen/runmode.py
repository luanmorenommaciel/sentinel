from __future__ import annotations

import time
from collections.abc import Generator
from datetime import datetime, timedelta, timezone


def backfill_ticks(
    window: timedelta,
    step: timedelta,
    end: datetime | None = None,
) -> Generator[int, None, None]:
    """Yield time_unix_nano ints covering [end - window, end) at step intervals.

    Args:
        window: Total historical window to cover.
        step:   Tick granularity.
        end:    End datetime (exclusive). Defaults to UTC now.
    """
    end = end or datetime.now(timezone.utc)
    start = end - window
    t = start
    while t < end:
        yield int(t.timestamp() * 1e9)
        t += step


def stream_ticks(
    step: timedelta,
    until: datetime,
) -> Generator[int, None, None]:
    """Yield time_unix_nano ints at approximately *step* intervals until *until*.

    Args:
        step:  Sleep interval between ticks.
        until: Wall-clock datetime (UTC) at which the generator stops.
    """
    while datetime.now(timezone.utc) < until:
        yield int(datetime.now(timezone.utc).timestamp() * 1e9)
        time.sleep(step.total_seconds())
