-- Sentinel Pod 2 — otel_metrics (+ 1m rollup) (Go OTLP collector)
--
-- Signal   : MetricSignal. Database: default (matches collector-rust).
-- Engine   : MergeTree (v1 has gauge/sum only — no counter resets to dedup).
-- ORDER BY : (ServiceName, MetricName, Timestamp) — MetricName 2nd so scans for
--            one metric skip parts for others.
-- TTL      : 90 days (longer than logs/traces — baseline look-back).
-- Rollup   : otel_metrics_1m is an AggregatingMergeTree fed by otel_metrics_1m_mv,
--            pre-aggregating 1-minute buckets for z-score detection. Kept in this
--            file because the table + MV are one unit. SimpleAggregateFunction uses
--            sum for count/sum_val/sum_sq and min/max for min_val/max_val — readers
--            MUST re-aggregate with the same fn in a GROUP BY (or FINAL).
-- Layout   : mirrors services/collector-rust/infra/clickhouse/ddl/003_otel_metrics.sql
--            column-for-column. Full design rationale lives in the Rust file.
-- Idempotent: CREATE … IF NOT EXISTS, safe to re-run. Edit + `make reset` to change
--            (desired-state, not a migration ledger). See
--            docs/clickhouse-schema-divergence-solved.md.

CREATE TABLE IF NOT EXISTS otel_metrics
(
    Timestamp           DateTime64(9, 'UTC')     CODEC(Delta, ZSTD(1)),
    MetricName          LowCardinality(String),
    MetricType          LowCardinality(String),
    Value               Float64                  CODEC(ZSTD(1)),
    ServiceName         LowCardinality(String),
    SentinelScenario    LowCardinality(String),
    SentinelRunId       LowCardinality(String),
    CloudProvider       LowCardinality(String),
    SentinelSynthetic   UInt8,
    ContractVersion     LowCardinality(String),
    Attributes          Map(String, String),
    ResourceAttributes  Map(String, String)
)
ENGINE = MergeTree
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, MetricName, Timestamp)
TTL toDate(Timestamp) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS otel_metrics_1m
(
    window_start        DateTime,
    ServiceName         LowCardinality(String),
    MetricName          LowCardinality(String),
    SentinelScenario    LowCardinality(String),
    count               SimpleAggregateFunction(sum, UInt64),
    sum_val             SimpleAggregateFunction(sum, Float64),
    sum_sq              SimpleAggregateFunction(sum, Float64),
    min_val             SimpleAggregateFunction(min, Float64),
    max_val             SimpleAggregateFunction(max, Float64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (ServiceName, MetricName, SentinelScenario, window_start)
TTL toDate(window_start) + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS otel_metrics_1m_mv
TO otel_metrics_1m
AS SELECT
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
