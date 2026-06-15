-- =============================================================================
-- Sentinel OTel Metrics Table
-- File   : infra/clickhouse/ddl/003_otel_metrics.sql
-- Signal : MetricSignal (contract.rs)
-- Created: 2026-06-01 (Day-3 schema design)
-- Pod    : Pod 2 (OTel Collector)
--
-- DESIGN DECISIONS
-- ----------------
-- Engine: plain MergeTree.
--   v1.0.0 only has gauge and sum types — no cumulative resets or
--   temporality metadata to de-duplicate. MergeTree is the right default.
--   If contract v2 adds monotonic counters with resets, a migration to
--   ReplacingMergeTree (keyed on (ServiceName, MetricName, Timestamp)) would
--   handle idempotent re-delivery without double-counting.
--
-- MetricType: LowCardinality(String).
--   contract.rs MetricType has exactly two values: "gauge" and "sum". An
--   Enum8 would work, but LowCardinality(String) is forward-compatible when
--   "histogram" is added in a future contract version (contract.rs notes this
--   is intentionally absent for v1.0.0 but expected later).
--
-- MetricName: LowCardinality(String).
--   Golden data has 10 distinct metric names. The longest is 64 chars
--   ("dataproc.googleapis.com/cluster/yarn/allocated_memory_percentage").
--   Production may have more but OTel GCP metric names are namespaced and
--   bounded. Well within the LowCardinality 10,000-value limit.
--
-- Value: Float64.
--   Maps directly from contract.rs `f64`. Golden data has values from 1.0 to
--   ~1974. Float64 is the correct type for the rolling_stats materialized view
--   (stores sum and sum_of_squares as Float64 for stddev derivation).
--
-- ORDER BY: (ServiceName, MetricName, Timestamp)
--   Differs from logs/traces. The dominant Watcher query for metrics is:
--     "give me the last N minutes of metric X for service Y".
--   MetricName in the second position means ClickHouse can skip parts for
--   metrics the query does not request, without scanning all metric names
--   for a service. This is more selective than putting Timestamp second when
--   a query is scoped to a specific metric.
--
-- Timestamp: same DateTime64(9, 'UTC') + Delta/ZSTD strategy as logs.
--   Metric timestamps in the golden data are epoch-aligned (many share
--   identical time_unix_nano = 1700000000000000000). In production, successive
--   gauge samples for the same metric are at fixed intervals — Delta encoding
--   compresses these differences to near-zero.
--
-- Resource-key hoisting: same policy as otel_logs and otel_traces.
--   The rolling_stats materialized view groups by (ServiceName, MetricName,
--   window_start). Hoisted SentinelScenario and SentinelRunId let the
--   anomaly-detection engine filter baselines per scenario without a Map
--   lookup.
--
-- PARTITION BY toDate(Timestamp):
--   Metrics dominate the golden data (183 of 279 records = 66%). Day
--   partitioning keeps TTL efficient and avoids very large single partitions
--   for high-frequency metric emission.
--
-- TTL: 90 days (longer than logs/traces).
--   Metrics summary tables (rolling_stats materialized view) need a longer
--   look-back window for baseline calibration. Raw metrics at 90 days is a
--   placeholder; the ADR should address tiered storage (S3 cold tier) for
--   anything beyond 30 days to control NVMe cost.
--   ⚠️ Golden fixture (2023-11-14) is older than this TTL → purged on first
--   merge (verified live 2026-06-01). Day-4 test must shift fixture timestamps
--   to ~now or strip TTL. See docs/research/clickhouse-schema-pod2.md
--   ("Day-4 gotcha: TTL vs. the golden fixture's timestamp").
-- =============================================================================

CREATE TABLE IF NOT EXISTS otel_metrics
(
    -- Primary timestamp: nanosecond precision
    Timestamp           DateTime64(9, 'UTC')
                            CODEC(Delta, ZSTD(1)),

    -- Metric identity
    MetricName          LowCardinality(String),
    MetricType          LowCardinality(String),   -- "gauge" | "sum"
    Value               Float64                   CODEC(ZSTD(1)),

    -- Hoisted from resource_attributes (always present per contract.rs v1.0.0)
    ServiceName         LowCardinality(String),   -- resource_attributes["service.name"]
    SentinelScenario    LowCardinality(String),   -- resource_attributes["sentinel.scenario"]
    SentinelRunId       LowCardinality(String),   -- resource_attributes["sentinel.run_id"]
    CloudProvider       LowCardinality(String),   -- resource_attributes["cloud.provider"]
    SentinelSynthetic   UInt8,                    -- resource_attributes["sentinel.synthetic"] cast to 1/0

    -- Contract metadata
    ContractVersion     LowCardinality(String),

    -- Metric-level attributes (component.name, component.type, status, unit, etc.)
    Attributes          Map(String, String),

    -- Remaining resource attributes not hoisted above
    ResourceAttributes  Map(String, String)
)
ENGINE = MergeTree
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, MetricName, Timestamp)
TTL toDate(Timestamp) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- =============================================================================
-- ROLLING STATS MATERIALIZED VIEW (rolling_stats spine stage, stage 2)
-- Pre-aggregates 1-minute buckets for z-score anomaly detection.
-- The detection engine reads from otel_metrics_1m, not otel_metrics directly.
--
-- ENGINE: AggregatingMergeTree + SimpleAggregateFunction (NOT SummingMergeTree).
--   SummingMergeTree sums EVERY non-key numeric column on merge — correct for
--   count/sum_val/sum_sq (all additive), but it would also SUM min_val and
--   max_val across merged parts, producing nonsense (the "min" of two parts is
--   not the sum of their mins). AggregatingMergeTree lets each column declare
--   its own combinator via SimpleAggregateFunction(<fn>, <type>):
--     - sum for count / sum_val / sum_sq   (additive)
--     - min for min_val, max for max_val   (correct range semantics)
--   SimpleAggregateFunction stores the plain value (not an opaque -State blob),
--   so reads are ordinary columns — but because parts may be unmerged, readers
--   MUST re-aggregate with the SAME function in a GROUP BY (or use FINAL). The
--   verification queries below show the correct read pattern.
-- =============================================================================

CREATE TABLE IF NOT EXISTS otel_metrics_1m
(
    window_start        DateTime,
    ServiceName         LowCardinality(String),
    MetricName          LowCardinality(String),
    SentinelScenario    LowCardinality(String),
    count               SimpleAggregateFunction(sum, UInt64),
    sum_val             SimpleAggregateFunction(sum, Float64),   -- for mean: sum_val/count
    sum_sq              SimpleAggregateFunction(sum, Float64),   -- for stddev: sqrt(sum_sq/n - (sum/n)^2)
    min_val             SimpleAggregateFunction(min, Float64),
    max_val             SimpleAggregateFunction(max, Float64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (ServiceName, MetricName, SentinelScenario, window_start)
TTL toDate(window_start) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- The MV fires on every INSERT into otel_metrics. The per-block aggregates
-- below are written straight into the SimpleAggregateFunction columns;
-- AggregatingMergeTree combines them across parts using each column's declared
-- function (sum/sum/sum/min/max). SentinelScenario is included so the detection
-- engine can compute separate baselines per scenario (baseline vs anomaly).
CREATE MATERIALIZED VIEW IF NOT EXISTS otel_metrics_1m_mv
TO otel_metrics_1m
AS
SELECT
    toStartOfMinute(Timestamp)  AS window_start,
    ServiceName,
    MetricName,
    SentinelScenario,
    count()                     AS count,
    sum(Value)                  AS sum_val,
    sum(Value * Value)          AS sum_sq,
    min(Value)                  AS min_val,
    max(Value)                  AS max_val
FROM otel_metrics
GROUP BY window_start, ServiceName, MetricName, SentinelScenario;

-- =============================================================================
-- VERIFICATION QUERIES (run after docker compose up)
-- =============================================================================
-- 1. Confirm columns:
--    SELECT name, type FROM system.columns WHERE table = 'otel_metrics';
--
-- 2. After inserting golden data (183 metrics):
--    SELECT count() FROM otel_metrics;       -- expect 183
--    SELECT MetricName, MetricType, count()
--    FROM otel_metrics GROUP BY 1, 2 ORDER BY 3 DESC;
--
-- 3. Rolling stats populated by the MV. NOTE: re-aggregate with the SAME
--    function per column (sum/min/max) to collapse any unmerged parts —
--    reading the raw columns can return multiple rows per (key, window):
--    SELECT
--        ServiceName, MetricName, window_start,
--        sum(count)   AS n,
--        sum(sum_val) AS total,
--        min(min_val) AS lo,
--        max(max_val) AS hi
--    FROM otel_metrics_1m
--    GROUP BY ServiceName, MetricName, window_start
--    ORDER BY window_start, ServiceName, MetricName;
--
-- 4. Stddev derivation sanity (should return non-null for multi-sample metrics):
--    SELECT
--        ServiceName,
--        MetricName,
--        sqrt(sum(sum_sq) / sum(count) - pow(sum(sum_val) / sum(count), 2)) AS stddev
--    FROM otel_metrics_1m
--    GROUP BY ServiceName, MetricName
--    ORDER BY ServiceName, MetricName;
-- =============================================================================
