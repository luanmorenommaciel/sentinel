# ClickHouse Schema Design — Pod 2 Day-3 Note

> **SUPERSEDED (2026-06-23) by [ADR-0007](../adr/0007-bronze-canonical-contract.md).** This
> note is the design rationale for the *hand-rolled* `default.*` schema (ADR-0005, now
> superseded). The canonical schema is now Pod 3's bronze (contrib v0.105.0, `sentinel.*`).
> Kept for history — the ClickHouse reasoning (codecs, TTL-vs-fixture-age, MergeTree choices)
> remains a useful reference.

> Author: Pod 2 (clickhouse-engineer agent, 2026-06-01)
> Status: Design draft — pending ADR and Pod 3 review
> Source of truth: `services/collector-rust/src/contract.rs` (v1.0.0)
> Golden data: `contract/golden/baseline_seed42.jsonl` (279 records: 48 logs, 48 spans, 183 metrics)
> KB reference: `.claude/kb/storage/clickhouse/index.md`

---

## Why hand-rolled tables instead of ClickHouse's built-in OTel schema?

ClickHouse ships an opinionated "ClickStack" schema for OTel signals that
mirrors the OpenTelemetry Collector's ClickHouse exporter. It is a solid
production baseline. We are not using it directly for the MVP because:

1. **Learning.** The team is new to both ClickHouse and the OTel data model.
   Hand-rolling the schema forces understanding of each column-type decision.
   Adopting the standard schema blindly would leave the team unable to debug
   query slowness or schema drift.

2. **Control.** Sentinel's contract (v1.0.0) has a specific field set and 5
   guaranteed resource keys. Our schema hoists those keys into typed columns
   for indexed filtering; the standard ClickStack schema keeps everything in
   Maps. For Sentinel's anomaly-detection workload, the hoisted columns matter.

3. **Naming alignment.** contract.rs uses `service_name`, `time_unix_nano`,
   `severity_text`. The standard ClickStack schema uses `ServiceName`,
   `Timestamp`, `SeverityText` (PascalCase). Our schema follows ClickStack
   conventions (PascalCase) while mapping from the contract's snake_case — the
   Rust exporter performs this translation at insert time.

**When to revisit:** If the team adopts the OpenTelemetry Collector's
ClickHouse exporter plugin in a future sprint, the standard schema becomes
preferable. The migration path is a shadow table + dual-write + cutover — the
ORDER BY is immutable post-creation.

---

## Field-to-column mapping

### LogSignal

| contract.rs field | Rust type | ClickHouse column | CH type | Notes |
|---|---|---|---|---|
| `time_unix_nano` | `i64` | `Timestamp` | `DateTime64(9, 'UTC')` | Convert nanos → OffsetDateTime |
| `severity_text` | `String` | `SeverityText` | `LowCardinality(String)` | ~24 OTel levels |
| `severity_number` | `i32` | `SeverityNumber` | `Int32` | |
| `service_name` | `String` | `ServiceName` | `LowCardinality(String)` | Also in ResourceAttributes |
| `body` | `String` | `Body` | `String` CODEC(ZSTD(1)) | Variable length, compresses well |
| `trace_id` (Option) | `Option<String>` | `TraceId` | `String` | `None` → `""` |
| `span_id` (Option) | `Option<String>` | `SpanId` | `String` | `None` → `""` |
| `contract_version` | `String` | `ContractVersion` | `LowCardinality(String)` | Always "1.0.0" for now |
| `attributes` | `HashMap<String,String>` | `LogAttributes` | `Map(String, String)` | Keys: component.name, etc. |
| `resource_attributes["sentinel.synthetic"]` | `String` ("true") | `SentinelSynthetic` | `UInt8` | Parse "true"→1, "false"→0 |
| `resource_attributes["sentinel.scenario"]` | `String` | `SentinelScenario` | `LowCardinality(String)` | |
| `resource_attributes["sentinel.run_id"]` | `String` | `SentinelRunId` | `LowCardinality(String)` | |
| `resource_attributes["cloud.provider"]` | `String` | `CloudProvider` | `LowCardinality(String)` | |
| `resource_attributes["service.name"]` | `String` | `ServiceName` | see above | Same value as `service_name` field |
| `resource_attributes` (remainder) | `HashMap<String,String>` | `ResourceAttributes` | `Map(String, String)` | cloud.account.id, cloud.region, etc. |

### SpanSignal

| contract.rs field | Rust type | ClickHouse column | CH type | Notes |
|---|---|---|---|---|
| `start_unix_nano` | `i64` | `Timestamp` | `DateTime64(9, 'UTC')` | Start time = "when it happened" |
| `end_unix_nano` | `i64` | `Duration` | `Int64` | Store as `end - start` in nanos |
| `trace_id` | `String` | `TraceId` | `String` | 32-char lowercase hex |
| `span_id` | `String` | `SpanId` | `String` | 16-char lowercase hex |
| `parent_span_id` (Option) | `Option<String>` | `ParentSpanId` | `String` | `None` → `""` (50% of golden spans are root) |
| `name` | `String` | `SpanName` | `LowCardinality(String)` | 4 distinct values in golden data |
| `service_name` | `String` | `ServiceName` | `LowCardinality(String)` | |
| `status_code` | `StatusCode` | `StatusCode` | `LowCardinality(String)` | "OK" or "ERROR" |
| `contract_version` | `String` | `ContractVersion` | `LowCardinality(String)` | |
| `attributes` | `HashMap<String,String>` | `SpanAttributes` | `Map(String, String)` | |
| `resource_attributes` (hoisted 5) | see above | same hoisted columns | same types | |
| `resource_attributes` (remainder) | `HashMap<String,String>` | `ResourceAttributes` | `Map(String, String)` | |

**Note on `end_unix_nano`:** the raw field is not stored. `Duration` is derived
as `end_unix_nano - start_unix_nano` at insert time. The Latency watcher (W05)
never queries "spans that ended after T"; it queries quantiles over Duration.
Dropping `end_unix_nano` saves an 8-byte column on every row.

### MetricSignal

| contract.rs field | Rust type | ClickHouse column | CH type | Notes |
|---|---|---|---|---|
| `time_unix_nano` | `i64` | `Timestamp` | `DateTime64(9, 'UTC')` | |
| `name` | `String` | `MetricName` | `LowCardinality(String)` | Max 64 chars in golden data |
| `metric_type` (renamed `type`) | `MetricType` | `MetricType` | `LowCardinality(String)` | "gauge" or "sum" |
| `value` | `f64` | `Value` | `Float64` | |
| `service_name` | `String` | `ServiceName` | `LowCardinality(String)` | |
| `contract_version` | `String` | `ContractVersion` | `LowCardinality(String)` | |
| `attributes` | `HashMap<String,String>` | `Attributes` | `Map(String, String)` | |
| `resource_attributes` (hoisted 5) | see above | same hoisted columns | same types | |
| `resource_attributes` (remainder) | `HashMap<String,String>` | `ResourceAttributes` | `Map(String, String)` | |

---

## Key design decisions with rationale

### 1. Engine: plain MergeTree on all three tables

**Decision:** `ENGINE = MergeTree` on `otel_logs`, `otel_traces`, `otel_metrics`.

**Rationale:** Sentinel's v1.0.0 contract produces append-only synthetic data.
There is no deduplication requirement — each event is a distinct observation.
`ReplacingMergeTree` would require a stable row identity (a content hash or a
deterministic primary key that identifies "the same event re-delivered"), which
we do not have. Using `ReplacingMergeTree` without a correct `ver` column
introduces silent data loss. Plain `MergeTree` is the right default for
append-only telemetry; we can migrate to `ReplacingMergeTree` via an ADR when
an idempotent delivery requirement is confirmed.

`AggregatingMergeTree` (with `SimpleAggregateFunction` columns) is used for
`otel_metrics_1m` (the rolling_stats pre-aggregation table). It is deliberately
**not** `SummingMergeTree`: that engine sums every non-key numeric column on
merge, which is correct for `count`/`sum_val`/`sum_sq` but would corrupt
`min_val`/`max_val` (the min of two parts is not the sum of their mins).
`SimpleAggregateFunction(sum|min|max, T)` lets each column declare its own merge
combinator. Readers must re-aggregate with the same function in a `GROUP BY`
(the DDL's verification queries show the pattern).

### 2. Timestamp storage: DateTime64(9, 'UTC') — not raw Int64

**Decision:** Store timestamps as `DateTime64(9, 'UTC')` with codec
`CODEC(Delta, ZSTD(1))`.

**Rationale:** contract.rs carries `time_unix_nano` as `i64` nanoseconds.
Storing as raw `Int64` would preserve the full value but break two critical
ClickHouse features:
- `PARTITION BY toDate(Timestamp)` requires a DateTime-compatible column.
- `TTL toDate(Timestamp) + INTERVAL N DAY` requires the same.

`DateTime64(9, 'UTC')` stores nanosecond-precision Unix timestamps and
participates in date arithmetic. The cost is a small encoding step in the Rust
exporter (`time::OffsetDateTime` conversion, enabled by the `"time"` feature
already in Cargo.toml).

`Delta` codec: consecutive timestamps within a single telemetry stream differ
by milliseconds or microseconds. Delta encoding reduces each stored value to
a small delta before ZSTD. In benchmarks on monotonic integer sequences,
Delta+ZSTD achieves 3-5x better ratios than ZSTD alone.

### 3. Resource-key hoisting: promote 5 guaranteed keys, keep rest in Map

**Decision:** Hoist `sentinel.scenario`, `sentinel.run_id`, `sentinel.synthetic`,
`cloud.provider`, and `service.name` into typed `LowCardinality(String)` or
`UInt8` columns. Keep the remaining resource attributes (`cloud.account.id`,
`cloud.availability_zone`, `cloud.region`, `cloud.platform`, service-specific
GCP metadata) in `ResourceAttributes Map(String, String)`.

**Rationale:** This is the most consequential modeling decision. Two options:

Option A (flat, what we chose): Hoist the 5 guaranteed keys.
- Filtering `WHERE SentinelScenario = 'baseline' AND ServiceName = 'pubsub-ingestion-topic'` uses the primary index — no Map lookup.
- `LowCardinality` compression applies: 6 services × 1 scenario in golden data means the dictionary is tiny.
- The rolling_stats materialized view groups by `(ServiceName, MetricName, SentinelScenario, window_start)` — hoisted columns are essential for this to perform.

Option B (pure Map): keep everything in `ResourceAttributes`.
- Simpler schema, easier ingestion.
- Every Watcher query that scopes by service or scenario must do `ResourceAttributes['service.name'] = '...'`, which cannot use the primary index and forces a full column scan.
- Verdict: unacceptable for the detection-latency target (<1s aggregations per the KB).

The 9 additional resource keys observed in the golden data (`cloud.account.id`,
`cloud.availability_zone`, etc.) are kept in the Map because Watchers do not
filter on them directly; they are metadata for root-cause analysis dashboards.

### 4. ORDER BY: (ServiceName, MetricName, Timestamp) for metrics; (ServiceName, Timestamp, TraceId) for logs and traces

**Decision:** Different sort keys for metrics vs. logs/traces.

**Rationale:**
- Logs and traces: the dominant query is "all records for service X in time window T". ServiceName → Timestamp → TraceId matches this perfectly.
- Metrics: the dominant query is "all samples of metric M for service X over time". ServiceName → MetricName → Timestamp means the sort key is selective on two dimensions before hitting the time range. Without MetricName second, a query for `operation.latency_ms` must scan all metric names for a service.
- The rolling_stats MV (AggregatingMergeTree) on `otel_metrics_1m` uses `ORDER BY (ServiceName, MetricName, SentinelScenario, window_start)` — consistent with the raw table's ordering.

### 5. Partitioning: one partition per calendar day

**Decision:** `PARTITION BY toDate(Timestamp)` on all tables.

**Rationale:** The golden data is a single synthetic run at epoch timestamp
2023-11-14 — one partition in dev. In production, runs replay over multiple
days, so day partitions align with natural time boundaries. Benefits:
- TTL drops entire day partitions atomically (no row-level deletes).
- Date-range query filters skip whole partitions.
- Alternative (PARTITION BY SentinelRunId): tempting for batch analytics, but
  production will have many runs and could create thousands of small partitions,
  triggering the "too many parts" pathology the KB warns about.

---

## How a Rust beginner inserts a row (Day-4 orientation)

The `clickhouse` crate 0.13 uses an HTTP connection to port 8123 (not native
9000 — see infra/clickhouse/README.md for the explanation). The core pattern is:

```rust
// Cargo.toml already has:
// clickhouse = { version = "0.13", features = ["lz4", "time"] }

use clickhouse::Row;
use serde::Serialize;
use time::OffsetDateTime;

// One struct per table. Field names must match ClickHouse column names exactly
// (ClickHouse is case-sensitive for column lookups via the HTTP interface).
#[derive(Row, Serialize)]
pub struct OtelMetricRow {
    // DateTime64(9, 'UTC') ← time::OffsetDateTime
    // The serde attribute is provided by clickhouse::serde (re-exported).
    #[serde(with = "clickhouse::serde::time::datetime64::nanos")]
    pub timestamp: OffsetDateTime,

    pub metric_name: String,          // column: MetricName
    pub metric_type: String,          // column: MetricType
    pub value: f64,                   // column: Value
    pub service_name: String,         // column: ServiceName
    pub sentinel_scenario: String,    // column: SentinelScenario
    pub sentinel_run_id: String,      // column: SentinelRunId
    pub cloud_provider: String,       // column: CloudProvider
    pub sentinel_synthetic: u8,       // column: SentinelSynthetic
    pub contract_version: String,     // column: ContractVersion

    // Map(String, String) must be Vec<(String, String)> — not HashMap
    pub attributes: Vec<(String, String)>,
    pub resource_attributes: Vec<(String, String)>,
}

// In the exporter / actor:
async fn flush_metrics(
    client: &clickhouse::Client,
    rows: Vec<OtelMetricRow>,
) -> Result<(), clickhouse::error::Error> {
    let mut insert = client.insert("otel_metrics")?;
    for row in rows {
        insert.write(&row).await?;
    }
    insert.end().await?;   // flushes the batch
    Ok(())
}
```

**Converting from MetricSignal to OtelMetricRow** involves three steps:

1. `time_unix_nano: i64` → `OffsetDateTime`:
   `OffsetDateTime::from_unix_timestamp_nanos(signal.time_unix_nano as i128)?`

2. `metric_type: MetricType` → `String`:
   `match signal.metric_type { MetricType::Gauge => "gauge", MetricType::Sum => "sum" }.to_string()`

3. `attributes: HashMap<String,String>` → `Vec<(String,String)>`:
   `signal.attributes.into_iter().collect::<Vec<_>>()`

These conversions happen in a `From<MetricSignal>` impl on the Row struct — a
clean boundary between the contract layer and the storage layer.

### ⚠️ Day-4 gotcha: TTL vs. the golden fixture's timestamp

**Verified live on 2026-06-01 against ClickHouse 25.4.** The tables carry
event-time TTLs (`TTL toDate(Timestamp) + INTERVAL 30/90 DAY`), which is correct
for production (real-time telemetry). But the golden fixture
(`baseline_seed42.jsonl`) is timestamped **2023-11-14** (epoch `1700000000…`) —
~2.5 years before today. ClickHouse evaluates TTL on every merge, so:

> Inserting the golden data makes `count()` return 279 immediately, then **drop
> to 0 after the first background merge** (or `OPTIMIZE`). The rows are
> TTL-expired the instant they land.

This was hit during schema verification — two test rows at the fixture epoch
were purged on `OPTIMIZE FINAL`. **Do not weaken the production TTL to work
around it.** Instead, the Day-4 integration test must do ONE of:

1. **Shift timestamps to ingest-time-relative** in the replay harness (rewrite
   `time_unix_nano` to `now - offset` when loading the fixture), or
2. **Strip TTL in the test fixture** — apply the DDL then
   `ALTER TABLE otel_metrics MODIFY TTL toDate(Timestamp) + INTERVAL 100 YEAR`
   (or `REMOVE TTL`) in the test-only schema variant, or
3. **Assert before any merge** — fragile; background merges fire
   unpredictably. Not recommended.

Option 1 is closest to production behaviour (real OTLP arrives ~now) and is the
recommended path. Capture the decision in the Day-4 test setup.

---

## Open questions (ADR candidates)

### ADR-Q1: Retention tiers

Current DDL has placeholder TTLs: 30 days for logs and traces, 90 days for
metrics. Sentinel's detection quality depends on baseline window length.
Questions for the ADR:
- What is the minimum look-back for z-score baselines to be statistically
  meaningful? (7 days minimum per the anomaly-detection KB)
- Should raw metrics beyond 30 days move to an S3 cold tier rather than be
  dropped? (ClickHouse STORAGE POLICY can do this without schema changes)
- Should logs have a shorter hot-tier TTL (e.g. 7 days) with summary MVs
  keeping 90-day error-rate aggregates?

### ADR-Q2: Nullable vs empty-string for optional IDs

Current DDL uses empty string `''` for absent `TraceId`, `SpanId`, and
`ParentSpanId`. The KB recommends this to avoid Nullable's null-bitmap
overhead. However, empty string and "genuinely absent" are indistinguishable
at query time. If a Watcher needs to find logs without any trace correlation,
it must use `WHERE TraceId = ''`, which requires the reader to know the
convention. The ADR should decide: empty-string sentinel vs. Nullable, and
document the decision in the schema comments.

### ADR-Q3: resource_attributes "remainder" — Map or JSON or split further?

The golden data has 9 resource-attribute keys beyond the 5 guaranteed ones
(cloud.account.id, cloud.availability_zone, cloud.platform, cloud.region, and
4 service-specific GCP metadata keys). These are kept in
`ResourceAttributes Map(String, String)`. As new GCP services are added, the
key set will grow. The ADR should address:
- Are any of these remainder keys needed by Watchers for filtering (which would
  warrant hoisting)?
- Is a `JSONString` alternative better for dashboard ad-hoc queries?
- Should the schema be re-evaluated at contract v2.0 if Pod 1 adds attribute
  typing (contract review B1 flagged string-only as a v1.0.0 binding
  constraint)?

---

## KB gaps encountered

The following findings go beyond what the KB currently covers. Per
`.claude/rules/kb-enrichment.md`, run `/enrich-kb clickhouse` to capture them:

1. **clickhouse 0.13 crate uses HTTP port 8123, not native 9000.** The KB
   says "prefer Native TCP :9000 for high-throughput ingestion" and recommends
   `clickhouse-rs` for Rust. The crate named `clickhouse` (0.13) is a distinct
   crate from `clickhouse-rs`; it uses HTTP with binary RowBinary format and is
   already pinned in Cargo.toml. The KB should clarify this naming split.

2. **Map(String, String) → Vec<(String, String)> in clickhouse 0.13.** The
   crate does not support `HashMap<K,V>` serialization for Map columns — the
   caller must provide an ordered `Vec<(K,V)>`. This is not documented in the
   KB and will surprise Day-4 implementers.

3. **`clickhouse::serde::time::datetime64::nanos` serde attribute for DateTime64(9).** The specific serde path for nanosecond-precision timestamps via the
   `"time"` feature. Should be added to the KB's gotchas section.

---

## See also

- `services/collector-rust/src/contract.rs` — Rust struct definitions (source of truth)
- `infra/clickhouse/ddl/` — CREATE TABLE statements with inline design rationale
- `infra/clickhouse/README.md` — how to run locally + Rust crate type mapping
- `infra/docker-compose.yml` — local ClickHouse environment
- `.claude/kb/storage/clickhouse/index.md` — ClickHouse KB (engine, codecs, gotchas)
- `contract/golden/baseline_seed42.jsonl` — 279-record golden dataset (grounding for cardinality)
- `docs/adr/` — open ADRs for the three open questions above
