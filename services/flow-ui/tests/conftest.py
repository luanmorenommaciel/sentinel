"""Shared fixtures for the flow-ui suite.

Every ClickHouse read in flow-ui goes through one method — `ClickHouse._query`, which
POSTs the SQL as the raw request body — so faking that method's *response text* exercises
the whole read path without a database (S2). Three of the five test files were each
building their own version of that fake; the builders live here instead, so the dual-source
boards can be asserted in one shape rather than five.

The load-bearing one is `silver_coverage`. A board reads silver when silver's history
reaches back past the window it needs and bronze when it does not, so both branches of
every migrated method must be asserted against the same probe response in two
configurations — covering the window, and short of it.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping

import pytest

from flow_ui.clickhouse import ClickHouse
from flow_ui.pipeline import Snapshot

#: The silver base tables whose `min(event_time)` the coverage probe reports. Mirrors
#: `ClickHouse.SILVER_MODELS`; named here so a fixture stays readable at its call site.
SILVER_BASE_TABLES = ("operation_executions", "log_events", "metric_observations")


class _QueryStub:
    """`ClickHouse._query` replaced by a lookup over SQL fragments.

    `answers` is either one answer for every query, or an ordered mapping from a
    distinguishing SQL fragment to that query's answer. An answer is the response text
    ClickHouse would return, or an exception to raise instead — an unreachable database is
    a normal state for every board and has to be as easy to express as a row.
    """

    def __init__(self, answers: str | BaseException | Mapping[str, str | BaseException]):
        self._answers = answers
        self.seen: list[str] = []

    async def __call__(self, sql: str) -> str:
        self.seen.append(sql)
        answers = self._answers
        if isinstance(answers, Mapping):
            for fragment, answer in answers.items():
                if fragment in sql:
                    return self._unwrap(answer)
            return ""
        return self._unwrap(answers)

    @staticmethod
    def _unwrap(answer: str | BaseException) -> str:
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def count_matching(self, fragment: str) -> int:
        """How many queries carried `fragment` — REQ-E-14 is a statement about this."""
        return sum(1 for sql in self.seen if fragment in sql)


@pytest.fixture
def ch_stub():
    """Return a factory building a `ClickHouse` whose `_query` answers from a stub.

        ch, stub = ch_stub({"system.tables": tsv, "min(event_time)": coverage})
        rows = asyncio.run(ch.volume_band(minutes=60))

    The client is never opened, so no fixture teardown is needed: `_query` is the only
    place the real `httpx` client would be touched.
    """

    def _build(
        answers: str | BaseException | Mapping[str, str | BaseException],
        url: str = "http://ch:8123",
        database: str = "bronze",
    ) -> tuple[ClickHouse, _QueryStub]:
        ch = ClickHouse(url, database)
        stub = _QueryStub(answers)
        ch._query = stub  # type: ignore[method-assign]
        return ch, stub

    return _build


@pytest.fixture
def run_query(ch_stub):
    """`run_query(answers, lambda ch: ch.silver_state())` → the awaited result.

    The suite installs no asyncio plugin (`make test-flow-ui` installs pytest only), so a
    coroutine is driven with `asyncio.run` rather than an async test.
    """

    def _run(answers, call):
        ch, _stub = ch_stub(answers)
        return asyncio.run(call(ch))

    return _run


class SilverCoverage:
    """The two-coverage response builder (REQ-E-13).

    `min(event_time)` per silver base table as a unix timestamp, TSV, which is what the
    30 s-lane coverage probe reads (spec §7.3). The two methods are the two states a board
    has to behave differently in:

    - `covering(window)` — silver reaches back past the window, so the board reads silver;
    - `short_of(window)` — silver begins inside the window, so a silver read would show a
      shorter history than bronze and the board must fall back to bronze.

    `absent()` is the third state that already exists today and must not regress: no rows
    at all, which is a volume older than the silver DDL.
    """

    def __init__(self, now: float | None = None, tables: Iterable[str] = SILVER_BASE_TABLES):
        self.now = time.time() if now is None else now
        self.tables = tuple(tables)

    def covering(self, window_minutes: int, margin_s: float = 60.0) -> str:
        """Backfilled past the window: the oldest silver row predates `now - window`."""
        return self._tsv(self.now - window_minutes * 60 - margin_s)

    def short_of(self, window_minutes: int) -> str:
        """Partially backfilled: silver starts halfway into the window."""
        return self._tsv(self.now - window_minutes * 60 / 2)

    def absent(self) -> str:
        """No `silver` database, or no rows in it — the probe returns nothing."""
        return ""

    def _tsv(self, oldest: float) -> str:
        return "".join(f"{table}\t{int(oldest)}\n" for table in self.tables)


@pytest.fixture
def silver_coverage() -> SilverCoverage:
    return SilverCoverage()


@pytest.fixture
def band_row():
    """One `volume_band` row, defaulted. `volume_state` is pure, so the band is arithmetic.

    Shared because the migration's key assertion is that the band numbers are identical
    from either source for the same data — one row builder, two sources.
    """

    def _row(**kw) -> dict:
        base = {
            "service": "s", "median": 100.0, "mad": 0.0, "sd": 0.0,
            "seen": 30, "estate": 30, "latest": 100, "latest_t": 0, "series": [],
        }
        return {**base, **kw}

    return _row


@pytest.fixture
def snapshot():
    """A fully populated `Snapshot`, as one real tick of the live pipeline produced it.

    The figures are the recorded 233,100-signal run, so the page tests assert against
    numbers that actually occurred. A board that gains a field gains it here once.
    """

    def _snapshot(**kw) -> Snapshot:
        base = {
            "mode": "batch", "collector_up": True, "clickhouse_up": True,
            "ingest_rate": {"logs": 3100.0, "trace": 3100.0, "metrics": 12154.0},
            "reject_rate": {"logs": 0.4},
            "reject_by_reason": {"contract": 0.4},
            "reject_matrix": {"contract": {"logs": 0.4}},
            "contract_violations": [{"service": "third-party-agent", "rows": 2760,
                                     "violating": 2760,
                                     "missing": {"sentinel.run_id": 2760},
                                     "total_missing": 2760}],
            "flush_rate": 5.9, "records_per_flush": 2500.0, "export_latency_ms": 45.3,
            "persist_rate": 14750.0, "drop_rate": 0.0,
            "totals": {"ingested": 233100.0, "persisted": 233100.0},
            "bronze": {"otel_logs": 40200, "otel_traces": 40200,
                       "otel_metrics_gauge": 83400, "otel_metrics_sum": 69300},
            "bronze_rate": {"otel_logs": 2723.0},
            "lineage": [{"service": "pubsub-ingestion-topic", "total": 98700,
                         "logs": 16450, "traces": 16450, "gauge": 32900, "sum": 32900}],
            "metrics_by_service": {"pubsub-ingestion-topic": {
                "gauge": ["operation.latency_ms"],
                "sum": ["operation.request_count", "operation.error_count"]}},
            "scenario": "baseline",
        }
        return Snapshot(**{**base, **kw})

    return _snapshot
