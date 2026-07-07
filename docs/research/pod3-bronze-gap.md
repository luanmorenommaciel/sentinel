# POD2 (Rust collector) → POD3 Bronze — Schema Gap Analysis

| Field | Value |
|---|---|
| Status | **Research / decision-input — not a decision** |
| Date | 2026-06-16 |
| Author | Victor Urquiola (Pod 2) |
| Purpose | Capture the exact schema gap between the validated Rust collector's ClickHouse output and POD3's bronze landing schema, and scope the minimum change to make them compatible **without** altering the OTLP ingest path. |
| Related | [ADR-0005](../adr/0005-clickhouse-storage-schema.md) · [ADR-0006](../adr/0006-optional-id-representation.md) · [pod2→pod3 read contract](../../contracts/collector/v1/pod2-pod3-read-contract.md) · [canonical-read-schema proposal](../proposals/canonical-read-schema.md) · POD3 bronze DDL (`01-bronze-layer.sql`, provided 2026-06-16) |
| Constraint | Rust collector remains the Phase-1 reference implementation. No contrib-collector switch. |

---

## 0. Headline

The incompatibility between Pod 2's output and POD3's bronze is **concentrated entirely at the ClickHouse export layer** — the OTLP ingest path, the contract-validation layer, and the collector architecture are unaffected. The Rust collector is validated end-to-end (see §5). POD3's bronze is a live capture of the upstream `otel/opentelemetry-collector-contrib` v0.105.0 ClickHouse-exporter schema; the Rust collector writes a hand-rolled, Sentinel-enriched subset of it.

Crucially, the `clickhouse` 0.13 crate issues **named-column** inserts (verified from `system.query_log`):

```
INSERT INTO otel_logs(`Timestamp`,`ServiceName`,`SentinelScenario`,…,`ResourceAttributes`) FORMAT RowBinary
```

→ Columns **omitted** from the Row struct take ClickHouse defaults; columns **listed** must exist in the target table. This is why a parser-preserving, exporter-only change is sufficient: POD3's extra columns can stay empty, and only our extra (`Sentinel*`) columns force a change.

---

## 1. Current Rust output schema (live `SHOW CREATE`, db `default`)

Producer: `services/collector-rust`. Wire: RowBinary over HTTP `:8123`. Row structs: `clickhouse_exporter.rs:231–377`. Resource-key hoisting: `clickhouse_exporter.rs:174` (`hoist`). Optional-ID `''` sentinel: ADR-0006.

### `otel_logs` (14 cols)
`Timestamp DateTime64(9,'UTC')`, `ServiceName LowCardinality(String)`, **`SentinelScenario`**, **`SentinelRunId`**, **`CloudProvider`** `LowCardinality(String)`, **`SentinelSynthetic UInt8`**, `SeverityText LowCardinality(String)`, `SeverityNumber Int32`, `Body String`, `TraceId String`, `SpanId String`, **`ContractVersion LowCardinality(String)`**, `LogAttributes Map(String,String)`, `ResourceAttributes Map(String,String)`.
ORDER BY `(ServiceName, Timestamp, TraceId)` · PARTITION `toDate(Timestamp)` · TTL 30d.

### `otel_traces` (15 cols)
`Timestamp DateTime64(9,'UTC')`, `TraceId String`, `SpanId String`, `ParentSpanId String`, `SpanName LowCardinality(String)`, `ServiceName`, **`SentinelScenario`/`SentinelRunId`/`CloudProvider`/`SentinelSynthetic`**, `Duration Int64`, `StatusCode LowCardinality(String)` (`"OK"`/`"ERROR"`), **`ContractVersion`**, `SpanAttributes Map(String,String)`, `ResourceAttributes Map(String,String)`.
ORDER BY `(ServiceName, Timestamp, TraceId)` · PARTITION `toDate(Timestamp)` · TTL 30d.

### `otel_metrics` (12 cols)
`Timestamp DateTime64(9,'UTC')`, `MetricName LowCardinality(String)`, `MetricType LowCardinality(String)` (`"gauge"`/`"sum"`), `Value Float64`, `ServiceName`, **`SentinelScenario`/`SentinelRunId`/`CloudProvider`/`SentinelSynthetic`**, **`ContractVersion`**, `Attributes Map(String,String)`, `ResourceAttributes Map(String,String)`.
ORDER BY `(ServiceName, MetricName, Timestamp)` · PARTITION `toDate(Timestamp)` · TTL 90d.

### `otel_metrics_1m` (+ MV `otel_metrics_1m_mv`)
`AggregatingMergeTree`, populated by MV from `otel_metrics`: `window_start`, `ServiceName`, `MetricName`, `SentinelScenario`, `count`, `sum_val`, `sum_sq`, `min_val`, `max_val` (SimpleAggregateFunction). Pre-built z-score baseline for the `rolling_stats` spine stage. **No POD3 equivalent.**

Parser note (`otlp.rs`): only `Gauge`/`Sum` `NumberDataPoint`s are mapped; `Histogram`/`ExponentialHistogram`/`Summary` are skipped (`otlp.rs:306–314`). Span `events`/`links`/`kind`/`trace_state`/`status.message`/scope and log `flags`/scope/schema-urls are **not parsed**.

---

## 2. POD3 bronze schema (db `sentinel`, contrib v0.105.0 capture)

Owned by POD3 (`create_schema:false`; collector only INSERTs). Maps are `Map(LowCardinality(String), String)`; bloom_filter / minmax / tokenbf skip indexes throughout.

- **`otel_traces`**: `Timestamp`, `TraceId`, `SpanId`, `ParentSpanId`, `TraceState`, `SpanName`, `SpanKind`, `ServiceName`, `ResourceAttributes`, `ScopeName`, `ScopeVersion`, `SpanAttributes`, `Duration`, `StatusCode`, `StatusMessage`, `Events.{Timestamp,Name,Attributes}`, `Links.{TraceId,SpanId,TraceState,Attributes}`. ORDER BY `(ServiceName, SpanName, toUnixTimestamp(Timestamp), TraceId)`.
- **`otel_traces_trace_id_ts`** (+ MV): TraceId → time-range helper.
- **`otel_logs`**: `Timestamp`, `TimestampDate`(DEFAULT), `TimestampTime`(DEFAULT), `TraceId`, `SpanId`, `TraceFlags UInt8`, `SeverityText`, `SeverityNumber UInt8`, `ServiceName`, `Body`, `ResourceSchemaUrl`, `ResourceAttributes`, `ScopeSchemaUrl`, `ScopeName`, `ScopeVersion`, `ScopeAttributes`, `LogAttributes`. PARTITION `toYYYYMM(TimestampDate)`, ORDER BY `(ServiceName, TimestampDate, TimestampTime)`.
- **Metrics — 5 tables**: `otel_metrics_gauge`, `otel_metrics_sum`, `otel_metrics_histogram`, `otel_metrics_exponential_histogram`, `otel_metrics_summary`. Shared base: `Resource*`, `Scope*` (incl. `ScopeDroppedAttrCount`), `ServiceName`, `MetricName`, `MetricDescription`, `MetricUnit`, `Attributes`, `StartTimeUnix`, `TimeUnix`, `Flags`, `Exemplars.*`. Per-type: gauge/sum add `Value` (sum also `AggregationTemporality`, `IsMonotonic`); histogram adds `Count`/`Sum`/`BucketCounts`/`ExplicitBounds`/`Min`/`Max`; exponential adds `Scale`/`ZeroCount`/`Positive*`/`Negative*`; summary adds `ValueAtQuantiles.*`. All PARTITION `toDate(TimeUnix)`, ORDER BY `(ServiceName, MetricName, Attributes, toUnixTimestamp64Nano(TimeUnix))`, TTL 30d.

> POD3's note states Sentinel emits sum + histogram and that gauge/exp_histogram/summary "must exist or the exporter's table check fails at startup" — an assumption that the **contrib** collector is the runtime. Under the Rust collector that startup check does not apply; the empty tables are harmless.

---

## 3. Gap analysis

Legend: ✅ compatible · ⚠️ needs a small align · ⬜ POD3-only → defaults on insert (no Rust work) · ❌ ours-only → **would error** against POD3's table.

**Cross-cutting:** database `default` (ours) vs `sentinel` (POD3); map key type `Map(String,String)` vs `Map(LowCardinality(String),String)` (likely fine — scalar `LowCardinality(String)` inserts already work, ClickHouse dict-encodes server-side on RowBinary; **verify** map-key case); `StatusCode` values `"OK"/"ERROR"` (ours) vs contrib enum (POD3 to confirm acceptable).

### Logs
| POD3 column | Ours | Status |
|---|---|---|
| `Timestamp`, `TraceId`, `SpanId`, `ServiceName`, `Body`, `LogAttributes`, `ResourceAttributes` | same names | ✅ (map key type aside) |
| `SeverityText` | same | ✅ |
| `SeverityNumber UInt8` | `Int32` | ⚠️ width mismatch → change field to `u8` |
| `TimestampDate/Time`, `TraceFlags`, `ResourceSchemaUrl`, `ScopeSchemaUrl`, `ScopeName/Version`, `ScopeAttributes` | — | ⬜ default |
| — | `SentinelScenario/RunId`, `CloudProvider`, `SentinelSynthetic`, `ContractVersion` | ❌ drop or POD3 adds |

### Traces
| POD3 column | Ours | Status |
|---|---|---|
| `Timestamp`, `TraceId`, `SpanId`, `ParentSpanId`, `SpanName`, `ServiceName`, `Duration`, `SpanAttributes`, `ResourceAttributes` | same names | ✅ |
| `StatusCode` | same | ⚠️ value convention |
| `TraceState`, `SpanKind`, `ScopeName/Version`, `StatusMessage`, `Events.*`, `Links.*` | — | ⬜ default (unused by Phase-1 watchers) |
| — | `Sentinel*` (4) + `ContractVersion` | ❌ drop or POD3 adds |

### Metrics (structural)
| Aspect | POD3 | Ours | Status |
|---|---|---|---|
| Table layout | 5 typed tables | 1 `otel_metrics` (+ rollup) | ❌ must **route** gauge→`otel_metrics_gauge`, sum→`otel_metrics_sum` |
| Event time col | `TimeUnix` | `Timestamp` | ⚠️ rename |
| Type discriminator | table identity | `MetricType` column | ⚠️ drop column |
| `ServiceName`, `MetricName`, `Value`, `Attributes`, `ResourceAttributes` | present | present | ✅ |
| `MetricDescription/Unit`, `StartTimeUnix`, `Flags`, `Exemplars.*`, `Scope*`, `AggregationTemporality`, `IsMonotonic` | present | — | ⬜ default |
| `otel_metrics_1m` rollup | — | present | ❌ relocate to POD3 silver |
| histogram/exp/summary | dedicated tables | dropped at parser | ⬜ latent — no histograms in baseline run |

---

## 4. Proposed minimum change set (parser-preserving)

**Scope = exporter + config only.** `otlp.rs` (parser) and `contract.rs` (signal model) are **untouched**; the collector architecture, gRPC server, and contract-validation layer are preserved.

| # | Change | File(s) | Effort |
|---|---|---|---|
| 1 | Drop the 5–6 ours-only columns (`SentinelScenario`, `SentinelRunId`, `CloudProvider`, `SentinelSynthetic`, `ContractVersion`) from the three Row structs; stop hoisting → leave `sentinel.*`/`cloud.provider` in `ResourceAttributes` so the data is preserved | `clickhouse_exporter.rs` (structs + `From` impls + `hoist`) | S–M |
| 2 | Metrics: route by type into `otel_metrics_gauge` / `otel_metrics_sum`; rename metric `Timestamp`→`TimeUnix`; drop `MetricType` | `clickhouse_exporter.rs::export` | M |
| 3 | `SeverityNumber` `i32` → `u8` | `clickhouse_exporter.rs` (+ `contract.rs` field if shared) | S |
| 4 | Database `default` → `sentinel` | `config.docker.yaml` (DB/grants already exist in monorepo init) | S |
| 5 | Retire our DDL from `make init` (POD3 owns bronze DDL); keep `.sql` as reference | `Makefile`, `infra/clickhouse/ddl/` | S |
| 6 | Verify `Map(LowCardinality(String),String)` insert path (one round-trip) | test | S |

**Estimated effort: ~1–3 days** (one focused exporter PR + tests). This is *not* the multi-week full-contrib rewrite — Events/Links/Exemplars and the 3 unused metric tables stay empty by default.

**What this costs (open decisions — see §5):**
- **Sentinel enrichment** moves from typed columns into `ResourceAttributes` (data preserved; loses indexed fast-path). *Avoidable* if POD3 adds the 5 `Sentinel*` columns.
- **`otel_metrics_1m` z-score rollup** has no home in the split schema → becomes a POD3 **silver** object reading from `otel_metrics_{gauge,sum}`.
- Map key type, `StatusCode` value convention, `SeverityNumber` width — confirm with POD3.

---

## 5. Resolution options (for the review)

The choice is not one-sided: POD3 owns the bronze DDL and Pod 2 owns the collector — both are Crew B, unlike the immutable contrib exporter.

| Option | Who changes | Rust effort | POD3 effort | Preserves Sentinel enrichment? | Notes |
|---|---|---|---|---|---|
| **A — POD3 adapts bronze** | POD3 trims bronze to columns its Phase-1 watchers use + keeps `Sentinel*` cols | **minimal** (db name + metric-table naming) | moderate (edit DDL, drop unused tables) | ✅ yes (typed cols) | Deviates from verbatim contrib dump |
| **B — POD2 adapts exporter** | Pod 2 conforms to POD3's bronze as written (§4) | **~1–3 days** | none | ⚠️ via `ResourceAttributes` only | Bronze stays canonical-contrib-shaped |
| **C — meet in middle** | Pod 2 does §4 minus `Sentinel*` drop; POD3 adds the 5 `Sentinel*` cols + drops 3 unused metric tables | ~1–2 days | small | ✅ yes | Likely best effort/value ratio |

Recommendation to bring to the sync: **Option C** — smallest combined effort, preserves the detection enrichment, and keeps the Rust architecture intact. Final call is the team's after reviewing the §4 effort.

---

## Appendix — operational evidence (live, 2026-06-16)

`make COLLECTOR=rust e2e` (generator → Rust collector OTLP `:4317` → ClickHouse), exact lossless counts:

| table | rows |
|---|---|
| `otel_logs` | 40,200 |
| `otel_traces` | 40,200 |
| `otel_metrics` | 152,700 (gauge 83,400 + sum 69,300; 0 histograms in baseline) |
| `otel_metrics_1m` | 199 buckets |

Collector logs: `received == exported`, `rejected:0` (receive-boundary validation passes). Named-column INSERT confirmed from `system.query_log` (see §0). The earlier 0-row failure was an environment artifact (a stale container's port collision left ClickHouse network-orphaned), not a branch defect — resolved by a clean `make reset`.
