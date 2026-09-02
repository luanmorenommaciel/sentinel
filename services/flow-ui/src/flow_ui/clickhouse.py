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

import json
import logging
from typing import ClassVar

import httpx

log = logging.getLogger("flow_ui.clickhouse")

#: The tables Pod 2 actually writes. The bronze DDL also defines
#: `otel_metrics_histogram`, `_exponential_histogram` and `_summary`; contract §2.3 and §5
#: state they stay empty in this version because Pod 1's v1.0.0 emits gauge and sum only.
#: They are listed separately so the UI can say "empty by contract" rather than draw four
#: live tables and two dead ones with no explanation.
LIVE_TABLES = ("otel_logs", "otel_traces", "otel_metrics_gauge", "otel_metrics_sum")

#: The five keys Pod 1 guarantees on every signal, mirrored from the collector's
#: `REQUIRED_RESOURCE_KEYS` (`collector-rust/src/contract.rs`). Duplicated deliberately:
#: this is the *reader's* copy, and if the two ever disagree the board should show what
#: the collector is actually enforcing — so the drift is visible rather than silent.
REQUIRED_RESOURCE_KEYS = (
    "sentinel.synthetic",
    "sentinel.scenario",
    "sentinel.run_id",
    "cloud.provider",
    "service.name",
)
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
            # `{}`, not a dict of zeros. Zeros are a claim — "the tables are empty" — and the
            # caller stores whatever it gets as the previous reading, so on the recovering
            # tick the whole table read as one second of growth.
            return {}
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

    async def contract_violations(self, limit: int = 10) -> list[dict]:
        """Which producers wrote rows missing a required key, and which key.

        **This is the only per-producer view of contract health that exists.** The
        collector's `signals_rejected_total` carries `signal` and `reason` but no service
        label, so it can say *how many* violated and *how*, never *who*. Bronze can,
        because under the default `warn` policy a violating signal is exported anyway —
        the evidence lands in the table.

        Two things make it affordable. It probes `ResourceAttributes`, an unindexed Map
        (§3), so it runs on its own slow cadence and never per tick. And it counts with
        `countIf` per key rather than `ARRAY JOIN`-ing the five key names: the array form
        multiplies every row by five *before* filtering, which measured 6.4s against
        1.26s over the same ~6M rows.

        `violating` counts ROWS missing at least one key, which is not the sum of the
        per-key counts: a row missing four keys is one bad row, not four. Reporting the sum
        as a share made a producer missing 4 of 5 keys on every row read "80%", which looks
        like a row percentage and is not one.

        Returns `[{service, rows, violating, missing: {key: n}, total_missing}]`, worst first.
        """
        keys = REQUIRED_RESOURCE_KEYS
        cols = ",\n".join(
            f"    countIf(NOT mapContains(ResourceAttributes, '{k}')) AS m{i}"
            for i, k in enumerate(keys)
        )
        has_all = " AND ".join(
            f"mapContains(ResourceAttributes, '{k}')" for k in keys
        )
        cols += f",\n    countIf(NOT ({has_all})) AS bad"
        per_table = "\n  UNION ALL\n".join(
            f"  SELECT ServiceName, count() AS rows,\n{cols}\n"
            f"    FROM {self._db}.{t} GROUP BY ServiceName"
            for t in LIVE_TABLES
        )
        sums = ", ".join(f"sum(m{i}) AS k{i}" for i in range(len(keys))) + ", sum(bad) AS bad"
        having = " + ".join(f"k{i}" for i in range(len(keys)))
        sql = f"""
        SELECT ServiceName, sum(rows) AS rows, {sums}
        FROM (
{per_table}
        )
        GROUP BY ServiceName
        HAVING {having} > 0
        ORDER BY {having} DESC LIMIT {int(limit)} FORMAT TSV
        """
        out: list[dict] = []
        try:
            for line in (await self._query(sql)).splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) != 3 + len(keys):
                    continue
                missing = {k: int(v) for k, v in zip(keys, parts[2:-1]) if int(v) > 0}
                out.append({
                    "service": parts[0],
                    "rows": int(parts[1]),
                    "violating": int(parts[-1]),
                    "missing": missing,
                    "total_missing": sum(missing.values()),
                })
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("contract violations unavailable: %s", exc)
        return out

    async def volume_band(self, minutes: int = 60, limit: int = 8) -> list[dict]:
        """Per producer: the volume distribution over the window, and the latest bucket.

        Returns the raw statistics, not a verdict — the band and the threshold are computed
        in one place (`pipeline._volume_state`) so the drawn band and the alerting rule are
        literally the same numbers. Metaplane shipped a version where they differed and
        publicly called fixing it a "simplification"; there is no reason to repeat it.

        Three deliberate choices, all cheap because `ServiceName, TimestampDate,
        TimestampTime` is the sorting key, so the window filter is index-accelerated
        (measured 0.135s):

        * **The current bucket is excluded.** It is partial, and comparing a half-filled
          bucket against a band built from full ones alarms on every tick.
        * **`estate`** is the number of buckets in which *anything at all* landed. A
          producer whose `seen` is below it was silent while the pipeline was not — which
          is the one signal a tool that looks at tables at rest cannot produce: it sees a
          stale table, not a write that failed to happen.
        * **Both scale estimates are returned.** MAD is the robust one and the reason to
          prefer this over a plain z-score, but a perfectly regular producer has MAD = 0 and
          a band of zero width, where every tick is infinitely anomalous. The caller falls
          back to stddev, and declares the series unmonitorable when both collapse.
        """
        win = int(minutes)
        sql = f"""
        WITH b AS (
            SELECT ServiceName AS svc, toStartOfMinute(Timestamp) AS t, count() AS n
            FROM {self._db}.otel_logs
            WHERE Timestamp >= now() - INTERVAL {win} MINUTE
              AND Timestamp < toStartOfMinute(now())
            GROUP BY svc, t
        ),
        est AS (SELECT count(DISTINCT t) AS estate FROM b),
        m AS (SELECT svc, quantileExact(0.5)(n) AS med, stddevPop(n) AS sd FROM b GROUP BY svc)
        SELECT b.svc AS svc, m.med AS med,
               quantileExact(0.5)(abs(b.n - m.med)) AS mad, any(m.sd) AS sd,
               count() AS seen, any(est.estate) AS estate,
               argMax(b.n, b.t) AS latest, toUnixTimestamp(max(b.t)) AS latest_t,
               arraySort(x -> x.1, groupArray((toUnixTimestamp(b.t), b.n))) AS series
        FROM b INNER JOIN m ON b.svc = m.svc CROSS JOIN est
        GROUP BY b.svc, m.med
        ORDER BY m.med DESC LIMIT {int(limit)} FORMAT JSONEachRow
        """
        out: list[dict] = []
        try:
            for line in (await self._query(sql)).splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                out.append({
                    "service": r["svc"],
                    "median": float(r["med"]),
                    "mad": float(r["mad"]),
                    "sd": float(r["sd"]),
                    "seen": int(r["seen"]),
                    "estate": int(r["estate"]),
                    "latest": int(r["latest"]),
                    "latest_t": int(r["latest_t"]),
                    "series": [[int(t), int(n)] for t, n in r["series"]],
                })
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("volume band unavailable: %s", exc)
        return out

    async def call_edges(self, minutes: int = 15, limit: int = 24) -> list[dict]:
        """The call graph as it was actually traced: `A -> B` with span counts and errors.

        This is the only per-edge measurement that exists anywhere in the pipeline. Neither
        the collector nor bronze counts anything per edge; what makes it possible is that a
        child span carries its parent, so parent and child rows join and the two
        `ServiceName`s are the edge.

        **The parent side must be deduplicated, and `TraceId` alone is not enough.** The
        generator seeds a deterministic RNG, so a fixed `--seed` repeats *both* ids across
        runs: joining on `SpanId` alone invented eight edges the topology does not contain,
        and adding `TraceId` removed those while still fanning out — measured on a live
        table, 16,154 children in the window produced 445,229 joined rows, a 27.6x
        multiplication, because each child matched every historical copy of its parent. Edge
        widths then encoded run history rather than traffic.

        Collapsing parents to one row per `(TraceId, SpanId)` first makes the join
        one-to-at-most-one, so a child is counted exactly once. Both sides are still bounded
        by the same window, and it stays on the slow lane because it remains a self-join.
        """
        sql = f"""
        WITH parents AS (
            SELECT TraceId, SpanId, any(ServiceName) AS svc
            FROM {self._db}.otel_traces
            WHERE Timestamp > now() - INTERVAL {int(minutes)} MINUTE
            GROUP BY TraceId, SpanId
        )
        SELECT p.svc AS src, c.ServiceName AS dst,
               count() AS spans, countIf(c.StatusCode = 'Error') AS errors
        FROM {self._db}.otel_traces AS c
        INNER JOIN parents AS p
          ON c.ParentSpanId = p.SpanId AND c.TraceId = p.TraceId
        WHERE c.Timestamp > now() - INTERVAL {int(minutes)} MINUTE AND c.ParentSpanId != ''
        GROUP BY src, dst HAVING src != dst
        ORDER BY spans DESC LIMIT {int(limit)} FORMAT TSV
        """
        out: list[dict] = []
        try:
            for line in (await self._query(sql)).splitlines():
                if not line.strip():
                    continue
                src, dst, spans, errors = line.split("\t")
                out.append({"src": src, "dst": dst,
                            "spans": int(spans), "errors": int(errors)})
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("call edges unavailable: %s", exc)
        return out

    async def service_health(self, minutes: int = 30, limit: int = 12) -> list[dict]:
        """Per-producer latency and error rate, from Silver.

        The first thing this service reads out of `silver.*` rather than deriving from
        Bronze. It is an **addition, not a migration**: Bronze keeps answering the questions
        it already answers, because Silver's materialized views do not `POPULATE` (ADR-0010)
        and only see inserts made after the DDL was applied. Measured on this stack the day
        Silver landed: `bronze.otel_traces` held 1,703,050 rows going back 36 hours while
        `silver.operation_executions` held 12,849 going back 12 minutes. Moving the contract
        and volume queries across today would have silently dropped 36 hours of evidence.

        What it adds is genuinely new: flow-ui had **no per-service latency at all**. The
        Health board's quantiles are the collector's *export* latency — how long writing to
        ClickHouse takes — which is a different question from how long a producer's own
        operations take.

        Returns `[]` when `silver.*` is absent, which is the normal state of any stack whose
        ClickHouse volume predates the Silver DDL: the boards degrade to what Bronze answers
        rather than erroring.
        """
        sql = f"""
        SELECT service_name,
               sum(operation_count) AS ops,
               sum(error_count) AS errors,
               round(avg(latency_p50_ms), 1) AS p50,
               round(max(latency_p95_ms), 1) AS p95,
               round(max(latency_p99_ms), 1) AS p99,
               round(max(latency_max_ms), 1) AS worst
        FROM silver.service_health_1m
        WHERE window_start >= now() - INTERVAL {int(minutes)} MINUTE
        GROUP BY service_name ORDER BY ops DESC LIMIT {int(limit)} FORMAT TSV
        """
        out: list[dict] = []
        try:
            for line in (await self._query(sql)).splitlines():
                if not line.strip():
                    continue
                svc, ops, errs, p50, p95, p99, worst = line.split("\t")
                ops_i, errs_i = int(ops), int(errs)
                out.append({
                    "service": svc, "ops": ops_i, "errors": errs_i,
                    "error_rate": round(errs_i / ops_i, 5) if ops_i else 0.0,
                    "p50": float(p50), "p95": float(p95),
                    "p99": float(p99), "max": float(worst),
                })
        except (httpx.HTTPError, ValueError) as exc:
            # `UNKNOWN_TABLE` arrives here when the Silver DDL was never applied.
            log.info("silver service health unavailable (is silver deployed?): %s", exc)
        return out

    #: Silver's three physical models, in the order the pipeline fills them.
    SILVER_MODELS = ("operation_executions", "log_events", "metric_observations")

    async def silver_state(self) -> dict:
        """What Silver holds, and whether it is there at all.

        Row counts come from `system.tables`, which is metadata — the same reason
        :meth:`counts` reads `count()` rather than a windowed query. Cheap enough for the
        slow lane and never scans a row.

        `present` is the distinction the board needs: a ClickHouse volume created before the
        Silver DDL landed has no `silver` database, and an empty Silver is a different
        statement from an absent one. Both are normal — the DDL runs on ClickHouse boot, so a
        fresh `make up` has Silver from the start and it stays empty until a stream runs,
        because ADR-0010's materialized views do not `POPULATE`.
        """
        out = {"present": False, "models": {}, "views": [], "mvs": 0}
        try:
            rows = await self._query(
                "SELECT engine, name, toUInt64(ifNull(total_rows, 0)) "
                "FROM system.tables WHERE database = 'silver' FORMAT TSV")
        except httpx.HTTPError as exc:
            log.info("silver state unavailable: %s", exc)
            return out
        for line in rows.splitlines():
            if not line.strip():
                continue
            try:
                engine, name, n = line.split("\t")
            except ValueError:
                continue
            out["present"] = True
            if engine == "MergeTree":
                out["models"][name] = int(n)
            elif engine == "View":
                out["views"].append(name)
            elif engine == "MaterializedView":
                out["mvs"] += 1
        out["views"].sort()
        return out

    #: What each Silver model is *for*. The only hand-written part of its datasheet, and
    #: deliberately so: a type is metadata, a purpose is a claim, and ClickHouse holds the
    #: first and not the second.
    SILVER_SUMMARY: ClassVar[dict[str, str]] = {
        "operation_executions": "One row per span. Duration is milliseconds, already "
                                "converted; the hot sentinel.* keys are columns, not Map "
                                "probes.",
        "log_events": "One row per log record, with severity normalized and is_error "
                      "precomputed.",
        "metric_observations": "One row per data point, gauge and sum unified — metric_kind "
                               "says which table it came from.",
    }

    #: What each read view answers, in the words of its own SELECT. A view stores nothing —
    #: it is a query over the models above, run at read time — and a bare list of six names
    #: with no explanation is a puzzle, not information.
    SILVER_VIEW_DOCS: ClassVar[dict[str, tuple[str, str]]] = {
        "service_health_1m": ("per minute", "op count, error rate, latency p50/p95/p99"),
        "log_health_1m": ("per minute", "log count, error rate, worst severity"),
        "metric_rollup_1m": ("per minute", "count, sum, min/max/avg, stddev per name"),
        "telemetry_coverage_1m": ("per minute", "spans, logs, metrics seen per component"),
        "trace_summary": ("per trace", "duration, span count, entry/exit service"),
        "run_summary": ("per run", "services, traces, operations, errors"),
    }

    async def silver_schema(self) -> dict:
        """Each Silver model's columns and keys, read from ClickHouse rather than restated.

        The asymmetry with :data:`topology.TABLE_DOCS` is the point. Bronze's datasheet is
        hand-written because the read contract makes a *subset* claim — only some columns are
        populated, the rest sit at their ClickHouse default by design (§2) — and no DDL can
        say that. Silver makes no such claim: the DDL is the whole definition, so restating
        it in Python would only create something that can drift from the deployed schema.

        `system.columns` and `system.tables` are both metadata; this scans no data.
        """
        out: dict[str, dict] = {}
        try:
            keys = await self._query(
                "SELECT name, sorting_key, partition_key FROM system.tables "
                "WHERE database = 'silver' AND engine = 'MergeTree' FORMAT TSV")
            cols = await self._query(
                "SELECT table, name, type FROM system.columns "
                "WHERE database = 'silver' ORDER BY table, position FORMAT TSV")
        except httpx.HTTPError as exc:
            log.info("silver schema unavailable: %s", exc)
            return out
        for line in keys.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            out[parts[0]] = {"columns": [], "order_by": parts[1], "partition": parts[2],
                             "summary": self.SILVER_SUMMARY.get(parts[0], "")}
        # Filtered here, not in the query: ClickHouse 24.3 rejects `IN (SELECT … FROM
        # system.tables)` with "Not-ready Set is passed as the second argument for function
        # 'in'". The names are already in hand from the query above, so the filter is free.
        # It matters — `system.columns` also returns the four materialized views and six read
        # views, and an MV's columns are its target's, so unfiltered each model's schema came
        # back three times under three names.
        for line in cols.splitlines():
            parts = line.split("\t")
            if len(parts) != 3 or parts[0] not in out:
                continue
            out[parts[0]]["columns"].append([parts[1], parts[2]])
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
        except (TimeoutError, httpx.HTTPError):
            return False
