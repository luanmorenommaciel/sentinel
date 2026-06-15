-- =============================================================================
-- Sentinel OTel Logs Table
-- File   : infra/clickhouse/ddl/001_otel_logs.sql
-- Signal : LogSignal (contract.rs)
-- Created: 2026-06-01 (Day-3 schema design)
-- Pod    : Pod 2 (OTel Collector)
--
-- DESIGN DECISIONS
-- ----------------
-- Engine: plain MergeTree (not ReplacingMergeTree).
--   Sentinel ingests append-only synthetic telemetry; there is no meaningful
--   deduplication key for log rows. ReplacingMergeTree would require a
--   deterministic row identity (e.g. a content hash) that we do not have in
--   v1.0.0. Plain MergeTree is also simpler to reason about for the anomaly-
--   detection reads in rolling_stats.
--
-- Timestamp storage: DateTime64(9, 'UTC').
--   contract.rs carries time_unix_nano as i64 nanoseconds. We store as
--   DateTime64(9) rather than raw Int64 because:
--     (a) PARTITION BY toDate(...) and TTL both require a DateTime type.
--     (b) ClickHouse's query engine applies date-range pruning on DateTime64
--         columns in the ORDER BY — this is lost on Int64.
--     (c) The Rust `clickhouse` crate 0.13 with feature "time" can serialize
--         time::OffsetDateTime → DateTime64(9) via the `Row` derive.
--   CODEC(Delta, ZSTD(1)): Delta encoding reduces inter-row differences on
--   monotonically increasing timestamps before ZSTD compression, improving
--   ratio by ~20-30% over ZSTD alone on telemetry workloads.
--
-- Resource-key hoisting: five guaranteed keys promoted to typed columns.
--   The five keys guaranteed on every record by REQUIRED_RESOURCE_KEYS in
--   contract.rs — sentinel.synthetic, sentinel.scenario, sentinel.run_id,
--   cloud.provider, service.name — are also materialized as first-class
--   columns. Rationale:
--     (a) Filtering on sentinel.scenario or sentinel.run_id for anomaly-
--         detection queries requires a Map lookup otherwise, which cannot use
--         the primary index.
--     (b) LowCardinality can be applied to these columns; Map values are
--         always plain String.
--     (c) sentinel.synthetic is a boolean flag — storing as a 1-byte UInt8
--         rather than a string "true"/"false" halves its storage cost.
--   The remainder of resource_attributes (cloud.account.id, cloud.region,
--   cloud.platform, etc.) stays in ResourceAttributes Map for flexibility.
--
-- ORDER BY: (ServiceName, Timestamp, TraceId)
--   - ServiceName first: the dominant Watcher query shape is
--     "all logs for service X in time window T". A low-cardinality leading
--     column lets ClickHouse skip whole column ranges for other services.
--   - Timestamp second: time-range scans within a service are contiguous on
--     disk — no scattered seeks.
--   - TraceId last: trace assembly (join logs to spans by trace) benefits from
--     locality within the (service, time) slice without disrupting the primary
--     access pattern.
--
-- PARTITION BY toDate(Timestamp):
--   One partition per calendar day. The golden data is one synthetic run at a
--   fixed timestamp (2023-11-14). In production, runs are replayed over days,
--   so day-partitioning aligns TTL drops with natural ingestion cadence and
--   keeps each partition manageable (<200 MB target for dev workloads).
--
-- TraceId / SpanId as String (not FixedString):
--   contract.rs validates exactly 32 / 16 lowercase hex chars, so FixedString
--   would save ~8 bytes per ID. However, the Rust `clickhouse` crate 0.13
--   does not natively serialize `String` to `FixedString(N)` — you must
--   provide the exact byte slice. Using plain `String` eliminates a custom
--   serializer on Day 4. Log trace_id/span_id are Option<String>; we store
--   empty string '' for absent values (avoids Nullable's null-bitmap overhead).
--
-- Body: ZSTD(1) codec.
--   Log message text compresses extremely well with ZSTD. The golden data has
--   6 distinct body strings of ~20-38 chars; production bodies may be longer.
--   ZSTD(1) gives ~3-5x ratio improvement over LZ4 for natural-language text
--   at modest CPU cost.
--
-- SeverityText: LowCardinality(String).
--   Golden data shows only 'INFO' and 'ERROR'. OTel SeverityText spec has
--   ~24 levels — well within LowCardinality's 10,000-value dictionary limit.
--
-- TTL: 30 days (placeholder).
--   Pending ADR for retention tiers. Hot telemetry (logs, traces) may drop
--   to 7 days in production; this default matches the KB's recommendation.
--   ⚠️ The golden fixture is timestamped 2023-11-14 — older than any TTL here,
--   so it is purged on the first merge. The Day-4 test must shift fixture
--   timestamps to ~now or strip TTL. See docs/research/clickhouse-schema-pod2.md
--   ("Day-4 gotcha: TTL vs. the golden fixture's timestamp").
-- =============================================================================

CREATE TABLE IF NOT EXISTS otel_logs
(
    -- Primary timestamp: nanosecond precision, drives partitioning + TTL
    Timestamp           DateTime64(9, 'UTC')
                            CODEC(Delta, ZSTD(1)),

    -- Hoisted from resource_attributes (always present per contract.rs v1.0.0)
    ServiceName         LowCardinality(String),   -- resource_attributes["service.name"]
    SentinelScenario    LowCardinality(String),   -- resource_attributes["sentinel.scenario"]
    SentinelRunId       LowCardinality(String),   -- resource_attributes["sentinel.run_id"]
    CloudProvider       LowCardinality(String),   -- resource_attributes["cloud.provider"]
    SentinelSynthetic   UInt8,                    -- resource_attributes["sentinel.synthetic"] cast to 1/0

    -- Log-specific columns
    SeverityText        LowCardinality(String),   -- bounded OTel enum (~24 levels)
    SeverityNumber      Int32                     CODEC(Delta, ZSTD(1)),
    Body                String                    CODEC(ZSTD(1)),

    -- Trace correlation (optional on log records; empty string when absent)
    TraceId             String,                   -- 32-char lowercase hex, '' if null
    SpanId              String,                   -- 16-char lowercase hex, '' if null

    -- Contract metadata
    ContractVersion     LowCardinality(String),   -- e.g. "1.0.0"

    -- Remaining log-level attributes (component.name, etc.)
    LogAttributes       Map(String, String),

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
-- 1. Confirm table exists with expected columns:
--    SELECT name, type FROM system.columns WHERE table = 'otel_logs';
--
-- 2. After inserting the golden file (279 records, 48 logs):
--    SELECT count() FROM otel_logs;         -- expect 48
--    SELECT ServiceName, SeverityText, count()
--    FROM otel_logs GROUP BY ServiceName, SeverityText ORDER BY 1,2;
--
-- 3. Confirm partition layout:
--    SELECT partition, rows, formatReadableSize(bytes_on_disk) AS size
--    FROM system.parts WHERE table = 'otel_logs' AND active = 1;
-- =============================================================================
