-- Silver Watcher read models (T25, T27, T28, T29 — SPEC §6.3, REQ-D-01..D-09, D-12).
--
-- These are Tier-1 *inputs*, never verdicts. No threshold, band, severity or
-- escalation literal appears below, and `07-no-verdict-in-silver.sh` fails the
-- build if one does: Candidate G owns verdicts, D owns the numbers they read.
--
-- All three aggregating rollups lead with `window_start`, which is SPEC §4
-- correction 9 and the one place the spec overrules the design proposal. The
-- queries that read them filter on time and nothing else — `clickhouse.py:272-290`
-- has no `ServiceName` predicate anywhere in `volume_band`; the service is a
-- GROUP BY. Leading with `service_name` would put the only filtered column second.
--
-- Every MV here reads a silver base table that is itself an MV target, so all of D
-- rests on chained MV firing: an MV on `T` must fire for inserts into `T` made by
-- another MV writing `TO T`. That is `[V-1]`, measured PASS on 24.3.18.7 and
-- 25.4.13.22 with no setting required (SPEC §11.1), which is why these read silver
-- rather than re-paying bronze's 1.26 s unindexed Map probe.

-- ════════════════════════════════════════════════════════════════════════════
-- (a) metric_stats_1m — the rolling-stats rollup (T25, REQ-D-01, D-02)
-- ════════════════════════════════════════════════════════════════════════════
-- The five value columns are the z-score INPUT, not a z-score. Deciding what is
-- anomalous happens elsewhere.
--
-- `SimpleAggregateFunction` rather than `AggregateFunction` + -State/-Merge:
-- readers need no combinators, so `0006`'s view body stays legible and the
-- 18-assertion regression guard keeps working on a plain `sum()`.
CREATE TABLE IF NOT EXISTS silver.metric_stats_1m
(
    `window_start`   DateTime CODEC(Delta(4), ZSTD(1)),
    `scenario`       LowCardinality(String) CODEC(ZSTD(1)),
    `service_name`   LowCardinality(String) CODEC(ZSTD(1)),
    `component_name` LowCardinality(String) CODEC(ZSTD(1)),
    `metric_name`    LowCardinality(String) CODEC(ZSTD(1)),
    `metric_kind`    Enum8('gauge' = 1, 'sum' = 2),
    `sample_count`   SimpleAggregateFunction(sum, UInt64),
    `sum_value`      SimpleAggregateFunction(sum, Float64),
    `sum_squares`    SimpleAggregateFunction(sum, Float64),
    `min_value`      SimpleAggregateFunction(min, Float64),
    `max_value`      SimpleAggregateFunction(max, Float64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, scenario, service_name, metric_name, component_name, metric_kind)
TTL window_start + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.metric_stats_1m_mv
TO silver.metric_stats_1m
AS SELECT
    toStartOfMinute(event_time) AS window_start,
    scenario,
    service_name,
    component_name,
    metric_name,
    metric_kind,
    toUInt64(count())  AS sample_count,
    sum(value)         AS sum_value,
    sum(value * value) AS sum_squares,
    min(value)         AS min_value,
    max(value)         AS max_value
FROM silver.metric_observations
GROUP BY window_start, scenario, service_name, component_name, metric_name, metric_kind;

-- ════════════════════════════════════════════════════════════════════════════
-- (b) volume_1m — rows per minute per producer per signal (T27, REQ-D-03)
-- ════════════════════════════════════════════════════════════════════════════
-- Carrying `signal` keeps the otel_logs-only semantics `volume_band` uses today
-- (`clickhouse.py:274`) while making traces and metrics reachable without a second
-- table. Re-aiming `volume_band` at `silver.log_events` directly was rejected: its
-- ORDER BY puts `event_time` fifth (0004_silver_layer.sql:91), so a window filter
-- prunes only to the day — a measurable regression against bronze's 0.135 s.
CREATE TABLE IF NOT EXISTS silver.volume_1m
(
    `window_start` DateTime CODEC(Delta(4), ZSTD(1)),
    `service_name` LowCardinality(String) CODEC(ZSTD(1)),
    `signal`       Enum8('log' = 1, 'trace' = 2, 'metric' = 3),
    `rows`         SimpleAggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, service_name, signal)
TTL window_start + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.volume_1m_logs_mv TO silver.volume_1m
AS SELECT toStartOfMinute(event_time) AS window_start, service_name,
          CAST('log', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
          toUInt64(count()) AS rows
   FROM silver.log_events GROUP BY window_start, service_name;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.volume_1m_traces_mv TO silver.volume_1m
AS SELECT toStartOfMinute(event_time) AS window_start, service_name,
          CAST('trace', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
          toUInt64(count()) AS rows
   FROM silver.operation_executions GROUP BY window_start, service_name;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.volume_1m_metrics_mv TO silver.volume_1m
AS SELECT toStartOfMinute(event_time) AS window_start, service_name,
          CAST('metric', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
          toUInt64(count()) AS rows
   FROM silver.metric_observations GROUP BY window_start, service_name;

-- ════════════════════════════════════════════════════════════════════════════
-- (c) resource_key_presence_1m — the contract read model (T28, REQ-D-04, D-06)
-- ════════════════════════════════════════════════════════════════════════════
-- KEY-LIST AGNOSTIC, and that is load-bearing. flow-ui keeps its own
-- REQUIRED_RESOURCE_KEYS, "duplicated deliberately: this is the *reader's* copy,
-- and if the two ever disagree the board should show what the collector is actually
-- enforcing" (`clickhouse.py:36-45`). A key list here would be a THIRD copy, would
-- make flow-ui draw Pod 3's opinion instead of its own (REQ-D-06), and would
-- quietly decide DEC-D1. So this table counts whatever keys arrive and the reader
-- supplies the list.
--
-- KNOWN LIMITATION, named rather than silent: `rows - key_counts[k]` is *rows
-- missing key k*, and the SUM OVER k IS NOT THE NUMBER OF BAD ROWS — a row missing
-- four keys is one bad row, not four. `clickhouse.py:197-200` records that
-- reporting the sum made a producer missing 4 of 5 keys read "80%", which looks
-- like a row percentage and is not one. `countIf(NOT has_all)` cannot be
-- reconstructed from `key_counts`, so the contract board's `bad` column keeps
-- coming from bronze until a `rows_missing_any` column exists. That is why T38
-- keeps its bronze fallback longest.
--
-- `sumMap` returns Map(String, UInt64) on the pinned ClickHouse version. Keeping
-- LowCardinality in the map key type is rejected by SimpleAggregateFunction's
-- return-type check even though the input keys are LowCardinality.
CREATE TABLE IF NOT EXISTS silver.resource_key_presence_1m
(
    `window_start` DateTime CODEC(Delta(4), ZSTD(1)),
    `service_name` LowCardinality(String) CODEC(ZSTD(1)),
    `signal`       Enum8('log' = 1, 'trace' = 2, 'metric' = 3),
    `rows`         SimpleAggregateFunction(sum, UInt64),
    `key_counts`   SimpleAggregateFunction(sumMap, Map(String, UInt64))
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, service_name, signal)
TTL window_start + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.rkp_1m_logs_mv TO silver.resource_key_presence_1m
AS SELECT
    toStartOfMinute(event_time) AS window_start,
    service_name,
    CAST('log', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
    toUInt64(count()) AS rows,
    sumMap(
        CAST(
            (mapKeys(resource_attributes),
             arrayResize(CAST([1], 'Array(UInt64)'), length(mapKeys(resource_attributes)), toUInt64(1))),
            'Map(String, UInt64)'
        )
    ) AS key_counts
FROM silver.log_events
GROUP BY window_start, service_name;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.rkp_1m_traces_mv TO silver.resource_key_presence_1m
AS SELECT
    toStartOfMinute(event_time) AS window_start,
    service_name,
    CAST('trace', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
    toUInt64(count()) AS rows,
    sumMap(
        CAST(
            (mapKeys(resource_attributes),
             arrayResize(CAST([1], 'Array(UInt64)'), length(mapKeys(resource_attributes)), toUInt64(1))),
            'Map(String, UInt64)'
        )
    ) AS key_counts
FROM silver.operation_executions
GROUP BY window_start, service_name;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.rkp_1m_metrics_mv TO silver.resource_key_presence_1m
AS SELECT
    toStartOfMinute(event_time) AS window_start,
    service_name,
    CAST('metric', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
    toUInt64(count()) AS rows,
    sumMap(
        CAST(
            (mapKeys(resource_attributes),
             arrayResize(CAST([1], 'Array(UInt64)'), length(mapKeys(resource_attributes)), toUInt64(1))),
            'Map(String, UInt64)'
        )
    ) AS key_counts
FROM silver.metric_observations
GROUP BY window_start, service_name;

-- ════════════════════════════════════════════════════════════════════════════
-- (d) call_edges_1m — the call-edge read model (T29, REQ-D-05, D-12)
-- ════════════════════════════════════════════════════════════════════════════
-- THIS CANNOT BE AN INCREMENTAL MV, and that is a hard fact: an MV sees only the
-- current insert block, and a call edge joins a child span to its parent, which
-- routinely sit in different blocks and different batches. Hence a REFRESHABLE MV.
--
-- Two guards, both paid for by a measured regression:
--   * GROUP BY trace_id, span_id collapses parents to one row per (trace, span).
--     Without it a 15-minute window produced 445,229 joined rows from 16,154
--     children — a 27.6x fan-out that made edge width encode run history rather
--     than traffic (`clickhouse.py:311-331`).
--   * The join is on trace_id AND parent_span_id. On span_id alone the seeded RNG
--     repeats ids across runs and invented EIGHT non-existent edges.
--
-- Trailing 24 h, TTL 2 days. A refreshable MV without APPEND atomically replaces
-- its target, so the window bounds the recompute cost. THE COST IS EXPLICIT: this
-- table holds 24 h of history, not 30 days. flow-ui's call_edges default window is
-- 15 minutes, so 24 h is ample.
--
-- This body references now(), making it the ONE non-deterministic silver object.
-- REQ-D-12 names it the single exception to `07-silver-mv-determinism.sh`, and
-- excludes it from the backfill and from REQ-E-03/E-11's content checksum. It needs
-- no backfill: each refresh recomputes from scratch, which is also its rollback —
-- drop it and the next refresh rebuilds.
--
-- Refreshable MVs are ungated on 25.4.13.22 (the flag reports `Obsolete setting,
-- does nothing`) and gated only on 24.3.18.7 — [V-3a] as corrected 2026-10-05. The
-- repo pins 25.4 (DEC-I1), so no setting is needed here and the scheduled-INSERT
-- fallback is unnecessary.
CREATE TABLE IF NOT EXISTS silver.call_edges_1m
(
    `window_start` DateTime CODEC(Delta(4), ZSTD(1)),
    `src_service`  LowCardinality(String) CODEC(ZSTD(1)),
    `dst_service`  LowCardinality(String) CODEC(ZSTD(1)),
    `spans`        UInt64,
    `errors`       UInt64
)
ENGINE = MergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, src_service, dst_service)
TTL window_start + toIntervalDay(2)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.call_edges_1m_rmv
REFRESH EVERY 1 MINUTE
TO silver.call_edges_1m
AS WITH parents AS (
       SELECT trace_id, span_id, any(service_name) AS src
       FROM silver.operation_executions
       WHERE event_time >= now() - INTERVAL 24 HOUR
       GROUP BY trace_id, span_id
   )
   SELECT toStartOfMinute(c.event_time) AS window_start,
          p.src AS src_service,
          c.service_name AS dst_service,
          toUInt64(count())             AS spans,
          toUInt64(countIf(c.is_error)) AS errors
   FROM silver.operation_executions AS c
   INNER JOIN parents AS p
          ON c.trace_id = p.trace_id AND c.parent_span_id = p.span_id
   WHERE c.event_time >= now() - INTERVAL 24 HOUR
     AND c.parent_span_id != ''
   GROUP BY window_start, src_service, dst_service;

-- Chained MVs execute under the inserting user's privileges. The collector
-- writes bronze, whose silver MVs insert into these tables; the read-model MVs
-- then need SELECT on only the source columns they consume.
GRANT SELECT(event_time, scenario, service_name, component_name, metric_name, metric_kind, value)
    ON silver.metric_observations TO sentinel_collector;
GRANT SELECT(event_time, service_name, resource_attributes, `resource_attributes.keys`)
    ON silver.log_events TO sentinel_collector;
GRANT SELECT(event_time, service_name, resource_attributes, `resource_attributes.keys`)
    ON silver.operation_executions TO sentinel_collector;
GRANT SELECT(event_time, service_name, resource_attributes, `resource_attributes.keys`)
    ON silver.metric_observations TO sentinel_collector;
