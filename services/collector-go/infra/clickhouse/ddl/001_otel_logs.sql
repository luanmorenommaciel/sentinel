-- Sentinel Pod 2 — otel_logs (Go OTLP collector)
--
-- Signal   : LogSignal. Database: default (matches collector-rust).
-- Engine   : MergeTree (append-only synthetic telemetry; no dedup key).
-- ORDER BY : (ServiceName, Timestamp, TraceId) — service-scoped time-range scans.
-- TTL      : 30 days (placeholder, pending retention ADR).
-- Layout   : mirrors services/collector-rust/infra/clickhouse/ddl/001_otel_logs.sql
--            column-for-column. Full design rationale lives in the Rust file.
-- Idempotent: CREATE … IF NOT EXISTS, safe to re-run. Edit + `make reset` to change
--            (desired-state, not a migration ledger). See
--            docs/clickhouse-schema-divergence-solved.md.

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
