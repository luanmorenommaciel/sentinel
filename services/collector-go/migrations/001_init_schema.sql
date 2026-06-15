-- Sentinel Pod 2 — ClickHouse schema init
-- Run via: clickhouse-client --user=otelgen --password=otelgen_secret < migrations/001_init_schema.sql
-- Or mount as docker-entrypoint-initdb.d volume (ClickHouse auto-runs .sql files on first start)

CREATE DATABASE IF NOT EXISTS sentinel;

CREATE TABLE IF NOT EXISTS sentinel.otel_spans
(
    trace_id            String,
    span_id             String,
    parent_span_id      Nullable(String),
    service_name        LowCardinality(String),
    name                String,
    start_unix_nano     Int64,
    end_unix_nano       Int64,
    status_code         LowCardinality(String),
    attributes          Map(String, String),
    resource_attributes Map(String, String),
    contract_version    LowCardinality(String),
    ingested_at         DateTime64(9)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(toDateTime(ingested_at))
ORDER BY (service_name, start_unix_nano, trace_id)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS sentinel.otel_logs
(
    time_unix_nano      Int64,
    service_name        LowCardinality(String),
    severity_text       LowCardinality(String),
    severity_number     Int32,
    body                String,
    trace_id            Nullable(String),
    span_id             Nullable(String),
    attributes          Map(String, String),
    resource_attributes Map(String, String),
    contract_version    LowCardinality(String),
    ingested_at         DateTime64(9)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(toDateTime(ingested_at))
ORDER BY (service_name, time_unix_nano)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS sentinel.otel_metrics
(
    time_unix_nano      Int64,
    service_name        LowCardinality(String),
    name                String,
    type                LowCardinality(String),
    value               Float64,
    attributes          Map(String, String),
    resource_attributes Map(String, String),
    contract_version    LowCardinality(String),
    ingested_at         DateTime64(9)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(toDateTime(ingested_at))
ORDER BY (service_name, name, time_unix_nano)
SETTINGS index_granularity = 8192;
