-- Sentinel Pod 2 — ClickHouse schema init (Go custom OTLP collector)
--
-- Aligned with collector-rust DDL (infra/clickhouse/ddl/) per POD 2 normalization.
-- Database: default (matches Rust). See docs/clickhouse-schema-divergence3.md.
--
-- Run via:
--   clickhouse-client --user=otelgen --password=otelgen_secret \
--     < migrations/001_init_schema.sql
-- Idempotent: CREATE … IF NOT EXISTS throughout, safe to re-run.

CREATE TABLE IF NOT EXISTS otel_logs
(
    Timestamp           DateTime64(9, 'UTC')     CODEC(Delta, ZSTD(1)),
    ServiceName         LowCardinality(String),
    SentinelScenario    LowCardinality(String),
    SentinelRunId       LowCardinality(String),
    CloudProvider       LowCardinality(String),
    SentinelSynthetic   UInt8,
    SeverityText        LowCardinality(String),
    SeverityNumber      Int32                    CODEC(Delta, ZSTD(1)),
    Body                String                   CODEC(ZSTD(1)),
    TraceId             String,
    SpanId              String,
    ContractVersion     LowCardinality(String),
    LogAttributes       Map(String, String),
    ResourceAttributes  Map(String, String)
)
ENGINE = MergeTree
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, Timestamp, TraceId)
TTL toDate(Timestamp) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS otel_traces
(
    Timestamp           DateTime64(9, 'UTC')     CODEC(Delta, ZSTD(1)),
    TraceId             String,
    SpanId              String,
    ParentSpanId        String,
    SpanName            LowCardinality(String),
    ServiceName         LowCardinality(String),
    SentinelScenario    LowCardinality(String),
    SentinelRunId       LowCardinality(String),
    CloudProvider       LowCardinality(String),
    SentinelSynthetic   UInt8,
    Duration            Int64                    CODEC(Delta, ZSTD(1)),
    StatusCode          LowCardinality(String),
    ContractVersion     LowCardinality(String),
    SpanAttributes      Map(String, String),
    ResourceAttributes  Map(String, String)
)
ENGINE = MergeTree
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, Timestamp, TraceId)
TTL toDate(Timestamp) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

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
