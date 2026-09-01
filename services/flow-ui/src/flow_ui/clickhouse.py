"""Reading bronze — the Pod 2 → Pod 3 read contract, from the consumer side.

Built against `contracts/collector/v1/pod2-pod3-read-contract.md` v1.0.0.1.

**Row counts are read with bare `count()`, never with a time window, and that is a
correctness decision before it is a performance one.** Bronze stores *event* time: the
contract (§2) defines `Timestamp` / `TimeUnix` as the signal's own timestamp, and there is
no ingest-time column anywhere in the schema. In backfill mode the generator writes a
window of history — measured: five minutes of timestamps ingested in 13.5 seconds — so
`WHERE Timestamp > now() - INTERVAL 10 SECOND` asks "which rows *happened* recently",
which is not the question. "How many rows *arrived*" is a delta of `count()`.

It is also far cheaper. Measured on 233k rows: bare `count()` reads 1 row (it comes from
part metadata) in 3.7 ms; the same count with a 10-second predicate reads all 40,200 rows
of the table. That gap widens with every row inserted.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("flow_ui.clickhouse")

#: The tables Pod 2 actually writes. The bronze DDL also defines
#: `otel_metrics_histogram`, `_exponential_histogram` and `_summary`; contract §2.3 and §5
#: state they stay empty in this version because Pod 1's v1.0.0 emits gauge and sum only.
#: They are listed separately so the UI can say "empty by contract" rather than draw four
#: live tables and two dead ones with no explanation.
LIVE_TABLES = ("otel_logs", "otel_traces", "otel_metrics_gauge", "otel_metrics_sum")
EMPTY_BY_CONTRACT = (
    "otel_metrics_histogram",
    "otel_metrics_exponential_histogram",
    "otel_metrics_summary",
)


class ClickHouse:
    """A thin async client over the HTTP interface."""

    def __init__(self, url: str, database: str, timeout: float = 4.0) -> None:
        self._url = url.rstrip("/")
        self._db = database
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _query(self, sql: str) -> str:
        """POST the SQL as the raw request body.

        Not as a url-encoded ``query=`` form field: ClickHouse takes the whole body as the
        statement, so a form encoding makes it try to parse the literal text ``query=SELECT
        ...`` and fail with `Syntax error: failed at position 1 ('query')`.
        """
        resp = await self._client.post(self._url + "/", content=sql.encode())
        resp.raise_for_status()
        return resp.text

    async def counts(self) -> dict[str, int]:
        """Total rows per live table, in one round trip.

        `ORDER BY` over a `UNION ALL` cannot see the branch aliases, so the union is
        wrapped in a subquery — otherwise ClickHouse raises `UNKNOWN_IDENTIFIER`.
        """
        union = "\nUNION ALL ".join(
            f"SELECT '{t}' AS tbl, count() AS n FROM {self._db}.{t}" for t in LIVE_TABLES
        )
        sql = f"SELECT * FROM (\n{union}\n) ORDER BY tbl FORMAT TSV"
        out: dict[str, int] = {t: 0 for t in LIVE_TABLES}
        try:
            for line in (await self._query(sql)).splitlines():
                if not line.strip():
                    continue
                tbl, n = line.split("\t")
                out[tbl] = int(n)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("bronze counts unavailable: %s", exc)
        return out

    async def lineage(self, limit: int = 12) -> list[dict]:
        """Rows per service, split by destination table.

        `ServiceName` is the leading `ORDER BY` key on every bronze table (contract §5.6),
        so this grouping is index-accelerated. `sentinel.scenario` deliberately is *not*
        used: it lives inside the `ResourceAttributes` Map and §3/§6 warn it is an
        unindexed probe, which is not something to put on a polling path.

        The four counts are kept apart rather than summed into "metrics" because that is
        the only thing that distinguishes one service from another here — **every service
        writes to all four tables**, so the shape of the split is the information, not the
        set of destinations.
        """
        sql = f"""
        SELECT ServiceName,
               sum(n) AS total,
               sumIf(n, t = 'logs')   AS logs,
               sumIf(n, t = 'traces') AS traces,
               sumIf(n, t = 'gauge')  AS gauge,
               sumIf(n, t = 'sum')    AS sums
        FROM (
            SELECT ServiceName, 'logs' AS t, count() AS n
              FROM {self._db}.otel_logs GROUP BY ServiceName
            UNION ALL
            SELECT ServiceName, 'traces', count() FROM {self._db}.otel_traces GROUP BY ServiceName
            UNION ALL
            SELECT ServiceName, 'gauge', count()
              FROM {self._db}.otel_metrics_gauge GROUP BY ServiceName
            UNION ALL
            SELECT ServiceName, 'sum', count()
              FROM {self._db}.otel_metrics_sum GROUP BY ServiceName
        )
        GROUP BY ServiceName ORDER BY total DESC LIMIT {int(limit)} FORMAT TSV
        """
        rows: list[dict] = []
        try:
            for line in (await self._query(sql)).splitlines():
                if not line.strip():
                    continue
                name, total, logs, traces, gauge, sums = line.split("\t")
                rows.append({
                    "service": name, "total": int(total), "logs": int(logs),
                    "traces": int(traces), "gauge": int(gauge), "sum": int(sums),
                })
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("bronze lineage unavailable: %s", exc)
        return rows

    async def metric_inventory(self) -> dict[str, dict[str, list[str]]]:
        """Which named metrics each service emits, and which table each lands in.

        This is the answer to "what is *this* service's path", and it is the only place
        the per-service question has a real answer: routing to a bronze table is decided
        by the **data-point type**, never by the producer, so every service reaches every
        table. What differs is *which metrics* it emits — and that is what makes one
        service's split 3:1 gauge-to-sum and another's 1:2.

        Grouping by name over both metric tables is heavier than the counters, so the
        poller runs it on its own slow cadence. The inventory is effectively static.
        """
        sql = f"""
        SELECT ServiceName, tbl, MetricName FROM (
            SELECT ServiceName, 'gauge' AS tbl, MetricName
              FROM {self._db}.otel_metrics_gauge GROUP BY ServiceName, MetricName
            UNION ALL
            SELECT ServiceName, 'sum', MetricName
              FROM {self._db}.otel_metrics_sum GROUP BY ServiceName, MetricName
        ) ORDER BY ServiceName, tbl, MetricName FORMAT TSV
        """
        out: dict[str, dict[str, list[str]]] = {}
        try:
            for line in (await self._query(sql)).splitlines():
                if not line.strip():
                    continue
                svc, tbl, name = line.split("\t")
                out.setdefault(svc, {"gauge": [], "sum": []})[tbl].append(name)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("metric inventory unavailable: %s", exc)
        return out

    async def scenario(self) -> str:
        """The most recent run's scenario, for the header.

        This *does* probe the `ResourceAttributes` Map, which §3 flags as unindexed — which
        is exactly why it is read on the slow lineage cadence and never per tick.
        """
        sql = (
            f"SELECT ResourceAttributes['sentinel.scenario'] "
            f"FROM {self._db}.otel_logs ORDER BY Timestamp DESC LIMIT 1 FORMAT TSV"
        )
        try:
            return (await self._query(sql)).strip() or "—"
        except httpx.HTTPError:
            return "—"

    async def ping(self) -> bool:
        try:
            await self._query("SELECT 1")
            return True
        except (httpx.HTTPError, asyncio.TimeoutError):
            return False
