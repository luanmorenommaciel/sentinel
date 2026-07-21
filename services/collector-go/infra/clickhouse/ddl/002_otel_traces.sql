-- Sentinel Pod 2 — otel_traces (Go OTLP collector)
--
-- Signal   : SpanSignal. Database: default (matches collector-rust).
-- Engine   : MergeTree (append-only; trace assembly is a read-side GROUP BY).
-- Duration : Int64 ns (end - start, computed at insert) — what W05 Latency queries.
-- ORDER BY : (ServiceName, Timestamp, TraceId) — TraceId last clusters a trace's spans.
-- TTL      : 30 days (placeholder, pending retention ADR).
-- Layout   : mirrors services/collector-rust/infra/clickhouse/ddl/002_otel_traces.sql
--            column-for-column. Full design rationale lives in the Rust file.
-- Idempotent: CREATE … IF NOT EXISTS, safe to re-run. Edit + `make reset` to change
--            (desired-state, not a migration ledger). See
--            docs/clickhouse-schema-divergence-solved.md.

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
