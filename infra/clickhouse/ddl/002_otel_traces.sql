-- =============================================================================
-- Sentinel OTel Traces Table
-- File   : infra/clickhouse/ddl/002_otel_traces.sql
-- Signal : SpanSignal (contract.rs)
-- Created: 2026-06-01 (Day-3 schema design)
-- Pod    : Pod 2 (OTel Collector)
--
-- DESIGN DECISIONS
-- ----------------
-- Engine: plain MergeTree.
--   Spans are append-only. The trace assembly pattern (GROUP BY TraceId to
--   reconstruct a distributed trace) is a read-side aggregation, not a write-
--   side deduplication. MergeTree is the correct choice.
--
-- Timestamp: we store BOTH DateTime64(9) and a derived Duration column.
--   - Timestamp maps to start_unix_nano — the conventional "when did this
--     event happen" for time-range filtering and partitioning.
--   - Duration (Int64 nanoseconds) = end_unix_nano - start_unix_nano,
--     computed at insert time (Rust exporter or MV). This matches the KB's
--     canonical schema and is what the Latency watcher (W05) will query
--     (quantile over Duration, not over a computed difference).
--   - end_unix_nano is NOT stored as a separate DateTime64 column: the Latency
--     watcher never queries "give me spans that ended after T" — Duration is
--     sufficient and saves one ~8-byte column per row.
--
--   CODEC(Delta, ZSTD(1)) on Timestamp and Duration:
--   - Timestamps for spans within a single trace are near-equal — Delta
--     encoding reduces inter-row differences to single-digit nanoseconds
--     before ZSTD, yielding very high compression ratios.
--   - Duration values cluster around service-specific means (~200ms in the
--     golden data); Delta encoding also benefits here.
--
-- StatusCode: LowCardinality(String).
--   contract.rs StatusCode enum has exactly two wire values: "OK" and "ERROR".
--   LowCardinality on a 2-value domain stores each value as a 1-byte dict
--   index. An Enum8('OK' = 0, 'ERROR' = 1) would be slightly more storage-
--   efficient but adds a migration cost if Pod 1 ever adds a third status
--   (UNSET is in the OTel spec). LowCardinality(String) gives us the
--   dictionary benefit with forward-compatibility.
--
-- ParentSpanId: String (not Nullable(String)).
--   The KB notes Nullable adds an internal null-bitmap column. 50% of golden
--   spans have a parent; 50% are root spans. We represent "no parent" as the
--   empty string '' rather than NULL. This avoids Nullable overhead and the
--   Rust `clickhouse` crate handles String serialization uniformly for both
--   Some and None cases (caller converts None → "").
--
-- Resource-key hoisting: same policy as otel_logs.
--   ServiceName, SentinelScenario, SentinelRunId, CloudProvider, and
--   SentinelSynthetic are promoted to typed columns for index-usable
--   filtering. Anomaly-detection queries always scope by ServiceName first;
--   these five columns are in every WHERE clause a Watcher will write.
--
-- SpanName: LowCardinality(String).
--   Golden data has 4 distinct span names; production may have dozens. At
--   <10,000 distinct values LowCardinality is appropriate; the Latency watcher
--   (W05) groups by (ServiceName, SpanName) for p95 computations.
--
-- ORDER BY: (ServiceName, Timestamp, TraceId)
--   - ServiceName first for service-scoped time-range queries.
--   - TraceId last clusters all spans of a trace together after the time
--     filter, making trace assembly a sequential read rather than scattered
--     seeks. Golden data shows 24 distinct trace IDs with 2 spans each.
--
-- TraceId / SpanId: plain String.
--   32-char and 16-char lowercase hex respectively. Same rationale as in
--   otel_logs: FixedString(N) would require a custom serializer on the Rust
--   side (clickhouse 0.13 does not auto-coerce String → FixedString).
--
-- PARTITION BY toDate(Timestamp): same day-partition rationale as otel_logs.
--
-- TTL: 30 days (placeholder — same as logs; see open questions).
--   ⚠️ Golden fixture (2023-11-14) is older than this TTL → purged on first
--   merge. Day-4 test must shift fixture timestamps to ~now or strip TTL.
--   See docs/research/clickhouse-schema-pod2.md ("Day-4 gotcha: TTL ...").
-- =============================================================================

CREATE TABLE IF NOT EXISTS otel_traces
(
    -- Primary timestamp: start_unix_nano → nanosecond-precision DateTime
    Timestamp           DateTime64(9, 'UTC')
                            CODEC(Delta, ZSTD(1)),

    -- Trace / span identity
    TraceId             String,                   -- 32-char lowercase hex
    SpanId              String,                   -- 16-char lowercase hex
    ParentSpanId        String,                   -- 16-char lowercase hex, '' for root spans

    -- Span descriptor
    SpanName            LowCardinality(String),

    -- Hoisted from resource_attributes (always present per contract.rs v1.0.0)
    ServiceName         LowCardinality(String),   -- resource_attributes["service.name"]
    SentinelScenario    LowCardinality(String),   -- resource_attributes["sentinel.scenario"]
    SentinelRunId       LowCardinality(String),   -- resource_attributes["sentinel.run_id"]
    CloudProvider       LowCardinality(String),   -- resource_attributes["cloud.provider"]
    SentinelSynthetic   UInt8,                    -- resource_attributes["sentinel.synthetic"] cast to 1/0

    -- Duration in nanoseconds (end_unix_nano - start_unix_nano, computed at insert)
    -- Divide by 1e6 for milliseconds. Used by W05 Latency watcher.
    Duration            Int64                     CODEC(Delta, ZSTD(1)),

    -- Status
    StatusCode          LowCardinality(String),   -- "OK" | "ERROR"

    -- Contract metadata
    ContractVersion     LowCardinality(String),

    -- Remaining span-level attributes (component.name, component.type, etc.)
    SpanAttributes      Map(String, String),

    -- Remaining resource attributes not hoisted above
    ResourceAttributes  Map(String, String)
)
ENGINE = MergeTree
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, Timestamp, TraceId)
TTL toDate(Timestamp) + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- =============================================================================
-- VERIFICATION QUERIES (run after docker compose up)
-- =============================================================================
-- 1. Confirm columns:
--    SELECT name, type FROM system.columns WHERE table = 'otel_traces';
--
-- 2. After inserting golden data (48 spans):
--    SELECT count() FROM otel_traces;       -- expect 48
--    SELECT ServiceName, StatusCode, count()
--    FROM otel_traces GROUP BY 1, 2 ORDER BY 1, 2;
--
-- 3. Latency sanity check (p50, p95 in ms):
--    SELECT
--        ServiceName,
--        SpanName,
--        round(quantile(0.50)(Duration) / 1e6, 2) AS p50_ms,
--        round(quantile(0.95)(Duration) / 1e6, 2) AS p95_ms
--    FROM otel_traces
--    GROUP BY ServiceName, SpanName
--    ORDER BY p95_ms DESC;
--
-- 4. Trace assembly sanity (each trace_id should have >= 1 span):
--    SELECT TraceId, count() AS span_count
--    FROM otel_traces
--    GROUP BY TraceId
--    ORDER BY span_count DESC
--    LIMIT 10;
-- =============================================================================
