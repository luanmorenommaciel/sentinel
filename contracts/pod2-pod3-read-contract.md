# Pod 2 → Pod 3 ClickHouse Read Contract

| Field | Value |
|---|---|
| Status | **Authoritative — Pod 2 → Pod 3 contract boundary** |
| Version | `1.0.0.1` |
| Date | 2026-06-23 (supersedes `1.0.0-rc.1`: adopts the bronze schema) |
| Producer | Pod 2 (OTel Collector) |
| Consumer | Pod 3 (Volume · Schema · Latency · Storage Watchers) |
| Transport | ClickHouse — HTTP `:8123` / native `:9000`, database **`sentinel`** |
| Source of truth | [`infra/clickhouse/init.d/01-bronze-otel.sql`](../infra/clickhouse/init.d/01-bronze-otel.sql) — the bronze DDL (Pod-3-owned, otel-collector-contrib v0.105.0) |
| Decisions | [ADR-0007](../docs/adr/0007-bronze-canonical-contract.md) (bronze = canonical) · [ADR-0006](../docs/adr/0006-optional-id-representation.md) (optional IDs, refined) · ~~ADR-0005~~ (superseded) |
| Rationale | [`docs/research/pod3-bronze-gap.md`](../docs/research/pod3-bronze-gap.md) (gap analysis + live evidence) |

> **What changed in 1.0.0.1 (consumers must update reads).** This contract previously documented Pod 2's
> *hand-rolled* `default.*` schema (ADR-0005). Per **ADR-0007**, the canonical read
> schema is now Pod 3's **bronze** DDL (`sentinel.*`, otel-collector-contrib v0.105.0),
> and the Rust collector writes directly into it. The structural shape is therefore owned
> by the bronze DDL — this document is the **semantic layer** on top of it: which columns
> Pod 2 populates and guarantees, where the Sentinel metadata lives, and the conventions
> a raw DDL cannot express. The hand-rolled schema, the 5 hoisted typed columns, and the
> `otel_metrics_1m` rollup are retired (the rollup moves to Pod 3 **silver**).

> **Build against this now.** The bronze schema is the agreed Pod 2 → Pod 3 contract
> boundary, and the exporter is implemented and round-trip verified end to end (see
> [Acceptance](#acceptance-pod-3-sign-off)). Any breaking change comes via a version bump
> (`1.0.0.2`, …) with notice — not silently.

---

## 1. What this contract covers

Pod 2's Collector parses Pod 1's OTLP signals and writes them into the **bronze**
ClickHouse tables (database `sentinel`). Pod 3's Watchers and silver layer **read** from
bronze. The bronze table/column *structure* is defined by the DDL (source of truth above,
`create_schema:false` — Pod 3 owns the lifecycle; the collector only `INSERT`s). This
document adds the **semantic guarantees** Pod 3 may rely on, plus consumer obligations.

It does **not** cover the OTLP `:4317` gRPC ingest path (Pod 2's *input* side, still Pod
1's NDJSON contract).

---

## 2. Tables — what Pod 2 populates

The bronze tables carry the full otel-collector-contrib v0.105.0 column set. The Rust
collector populates the subset below; **every other bronze column is left at its ClickHouse
default** (`''` / `0` / `[]`) — this is by design (named-column `INSERT`), not data loss.

### 2.1 `otel_logs` — from `LogSignal`

| Column Pod 2 writes | Type | Guarantee |
|---|---|---|
| `Timestamp` | `DateTime64(9)` | Event time (`time_unix_nano`), UTC, ns precision |
| `ServiceName` | `LowCardinality(String)` | Always present (from `service.name`) |
| `SeverityText` | `LowCardinality(String)` | OTel severity (`INFO`, `ERROR`, …) |
| `SeverityNumber` | `UInt8` | OTel severity number (0–24) |
| `Body` | `String` | Log message text |
| `TraceId` | `String` | 32-char lowercase hex, **`''` if absent** (§4) |
| `SpanId` | `String` | 16-char lowercase hex, **`''` if absent** (§4) |
| `LogAttributes` | `Map(LowCardinality(String), String)` | Record-level attributes |
| `ResourceAttributes` | `Map(LowCardinality(String), String)` | All resource attrs incl. the Sentinel keys (§3) |

Left at default (not written by Pod 2): `TimestampDate` / `TimestampTime` (DDL `DEFAULT`s of
`Timestamp`), `TraceFlags`, `ResourceSchemaUrl`, `ScopeSchemaUrl`, `ScopeName`,
`ScopeVersion`, `ScopeAttributes`.
`ORDER BY (ServiceName, TimestampDate, TimestampTime)` · `PARTITION BY toYYYYMM(TimestampDate)` · TTL 30d.

### 2.2 `otel_traces` — from `SpanSignal`

| Column Pod 2 writes | Type | Guarantee |
|---|---|---|
| `Timestamp` | `DateTime64(9)` | Span **start** time (`start_unix_nano`) |
| `TraceId` | `String` | 32-char lowercase hex, always present |
| `SpanId` | `String` | 16-char lowercase hex, always present |
| `ParentSpanId` | `String` | 16-char lowercase hex, **`''` for root spans** (§4) |
| `SpanName` | `LowCardinality(String)` | Span name |
| `ServiceName` | `LowCardinality(String)` | Always present |
| `Duration` | `Int64` | **Nanoseconds** (`end - start`), pre-computed; `/1e6` for ms. W05 reads quantiles over this |
| `StatusCode` | `LowCardinality(String)` | `"Ok"` or `"Error"` (contrib convention; OTLP `Unset` is collapsed to `"Ok"` upstream) |
| `SpanAttributes` | `Map(LowCardinality(String), String)` | Span-level attributes |
| `ResourceAttributes` | `Map(LowCardinality(String), String)` | All resource attrs incl. Sentinel keys (§3) |

Left at default: `TraceState`, `SpanKind`, `ScopeName`, `ScopeVersion`, `StatusMessage`,
`Events.*`, `Links.*`.
`ORDER BY (ServiceName, SpanName, toUnixTimestamp(Timestamp), TraceId)` · `PARTITION BY toDate(Timestamp)` · TTL 30d.

> **Note:** end time is **not** a column — only `Duration`. "When did this span end" is
> `Timestamp + Duration`.

### 2.3 Metrics — `otel_metrics_gauge` / `otel_metrics_sum`

Bronze splits metrics by data-point type into five tables. Pod 1's contract v1.0.0 emits
**gauge** and **sum** only, so Pod 2 writes those two; `otel_metrics_histogram` /
`_exponential_histogram` / `_summary` exist but stay **empty** in this version. The **data-point
type selects the table** — there is no `MetricType` column.

| Column Pod 2 writes (both tables) | Type | Guarantee |
|---|---|---|
| `ServiceName` | `LowCardinality(String)` | Always present |
| `MetricName` | `LowCardinality(String)` | Metric name |
| `TimeUnix` | `DateTime64(9)` | Event time (`time_unix_nano`) |
| `Value` | `Float64` | Sample value |
| `Attributes` | `Map(LowCardinality(String), String)` | Data-point attributes |
| `ResourceAttributes` | `Map(LowCardinality(String), String)` | All resource attrs incl. Sentinel keys (§3) |

Left at default: `Resource/ScopeSchemaUrl`, `Scope*`, `MetricDescription`, `MetricUnit`,
`StartTimeUnix`, `Flags`, `Exemplars.*`, and (sum) `AggregationTemporality`, `IsMonotonic`.
`ORDER BY (ServiceName, MetricName, Attributes, toUnixTimestamp64Nano(TimeUnix))` · `PARTITION BY toDate(TimeUnix)` · TTL 30d.

> **Rolling-stats moved to silver.** The previous `otel_metrics_1m` `AggregatingMergeTree`
> rollup (Tier-1 z-score input) is **no longer produced by the collector**. Pod 3 rebuilds
> it in **silver** from `otel_metrics_gauge` / `_sum`. The proven shape to replicate
> (1-minute buckets per service/metric/scenario with `count` / `sum_val` / `sum_sq` /
> `min` / `max`, re-aggregated with the same combinators) is preserved in §6.

---

## 3. Sentinel metadata lives in `ResourceAttributes`

Under bronze there are **no typed `Sentinel*` columns**. The values Pod 1 guarantees are
carried inside the `ResourceAttributes` Map, **guaranteed present on every row**, under
these keys:

| Map key | Meaning |
|---|---|
| `service.name` | also copied to the typed `ServiceName` column |
| `sentinel.scenario` | scenario id (z-score baselines key on this) |
| `sentinel.run_id` | generator run id |
| `cloud.provider` | e.g. `gcp` |
| `sentinel.synthetic` | string `"true"` / `"false"` |
| `contract_version` | Pod 1's contract version, e.g. `1.0.0` |

Read e.g. `ResourceAttributes['sentinel.scenario']`. **Trade-off (ADR-0007):** these are
`Map` probes, **not** primary-index-accelerated — only `ServiceName` keeps a typed,
indexed column. For latency-sensitive Watcher filters on `sentinel.scenario` /
`cloud.provider`, materialize them as silver columns rather than probing the Map in the hot
path.

---

## 4. Optional-ID semantics (per ADR-0006, refined by ADR-0007)

`TraceId` / `SpanId` (logs) and `ParentSpanId` (traces) are **`''` when absent, never
`NULL`.** A non-empty value is guaranteed valid lowercase hex (32 or 16 chars) — Pod 2
validates this **at insert** (bronze itself does not enforce it), so `''` can never collide
with a real ID. Bronze's own `otel_traces_trace_id_ts_mv` relies on this (`WHERE TraceId != ''`).

- Absent: `WHERE TraceId = ''`
- Present: `WHERE TraceId != ''`

---

## 5. Guarantees Pod 2 makes (won't change without a version bump)

1. **The columns in §2 are populated with the listed types and semantics.**
2. **The 6 Sentinel/`contract_version` keys in §3 are always present in `ResourceAttributes`**
   (backed by Pod 1's `REQUIRED_RESOURCE_KEYS`). A v2 resource key = a contract minor bump.
3. **`Timestamp`/`TimeUnix` are UTC `DateTime64(9)` event time; `Duration` is nanoseconds.**
4. **Optional IDs follow §4** (`''` = absent; non-empty = valid hex).
5. **Metrics are gauge/sum only** in this version (histogram/summary/exp tables stay empty).
6. **`ServiceName` filtering is index-accelerated** (leading `ORDER BY` key on all tables).

## 6. Explicit NON-guarantees (do not depend on these)

- **Contrib-rich columns** (`Scope*`, `Events.*`, `Links.*`, `Exemplars.*`, `SpanKind`,
  `TraceState`, `StatusMessage`, `TraceFlags`, histogram/summary/exp tables) — present in
  the DDL but **empty** in this version. Do not read them expecting data.
- **`Map` iteration order** in `*Attributes` / `ResourceAttributes`.
- **Index acceleration for non-`ServiceName` resource keys** — `sentinel.scenario` etc. are
  `Map` probes (see §3).
- **Exact partition layout / TTL value** — a retention *floor* is owned by the bronze DDL
  (30d today); do not assume data older than the floor exists.

---

## 7. Versioning

Versioned independently of Pod 1's contract version. This is `1.0.0.1` — the bronze-aligned
revision of the `1.0.0` read contract (db, table set, and the Sentinel-metadata location all
changed vs `1.0.0-rc.1`, so consumers must update their reads). Any further breaking change is
gated behind a version bump (`1.0.0.2`, …) with notice. The `contract_version` value in
`ResourceAttributes` carries **Pod 1's** version, not this contract's. Bronze itself is
version-anchored to **otel-collector-contrib v0.105.0** (a Collector-image bump means
re-dumping the bronze DDL — see its header).

## Acceptance (Pod 3 sign-off)

The bronze schema is already the agreed contract boundary (`1.0.0.1`); full ratification
(flipping [ADR-0007](../docs/adr/0007-bronze-canonical-contract.md) → Accepted) needs **all** of:

1. ☑ **Round-trip into bronze verified** *(2026-06-23)* — generator → Rust collector →
   `sentinel.*` lands `40,200 logs / 40,200 traces / 152,700 metrics` (gauge 83,400 + sum
   69,300), lossless, zero export failures; the file-mode golden round-trip yields
   `48 logs / 48 traces / 183 metrics`; Sentinel keys present in `ResourceAttributes`;
   contrib-rich columns defaulted; no leakage to `default.*`. Proven live against ClickHouse
   24.3 via `tests/clickhouse_roundtrip.rs` + `tests/grpc_export_roundtrip.rs`.
2. ☐ **Pod 3 review sign-off** — Pod 3 reviews this the way Pod 2 reviewed Pod 1's contract
   (`docs/research/contract-review-pod1-v1.0.0.md`), filing blockers if any.

### Open items for Pod 3 review

- **`StatusCode` value convention (R3 — resolved).** Pod 2 writes the contrib values `"Ok"` /
  `"Error"`. Pod 1's contract has no `Unset` status and OTLP `Unset` is collapsed to `"Ok"` in
  the parser, so this collector never emits `"Unset"`. Flag if your silver needs the `Unset`
  distinction (it would require a parser change).
- **Rolling-stats rollup ownership (R4).** §2.3 moves `otel_metrics_1m` to silver. Confirm
  Pod 3 owns it; the proven shape to replicate:

  ```sql
  -- Per-(service, metric, scenario) 1-minute baseline from gauge/sum bronze:
  SELECT ServiceName, MetricName, ResourceAttributes['sentinel.scenario'] AS scenario,
         toStartOfMinute(TimeUnix) AS window_start,
         count()        AS cnt,
         sum(Value)     AS sum_val,
         sum(Value*Value) AS sum_sq,
         min(Value)     AS min_val,
         max(Value)     AS max_val
  FROM sentinel.otel_metrics_sum   -- (UNION the gauge table as needed)
  GROUP BY ServiceName, MetricName, scenario, window_start;
  ```
- **Index acceleration for Sentinel filters (§3).** Do you want these materialized as silver
  columns (recovering the index fast-path the hand-rolled schema had)?

---

## 8. How Pod 3 should respond

Treat this like an inbound contract review. For each issue, file a blocker (B-series) or nit
(N-series) the way Pod 2 did for Pod 1's contract. Especially welcome: §4 optional-ID
semantics (does `''`=absent fit W01's log↔trace correlation?), §3 Sentinel-key access (Map
probe vs silver materialized column), the metrics rollup ownership (R4), and the retention
floor your baselines need.

## See also

- [`infra/clickhouse/init.d/01-bronze-otel.sql`](../infra/clickhouse/init.d/01-bronze-otel.sql) — bronze DDL (structural source of truth)
- [`docs/research/pod3-bronze-gap.md`](../docs/research/pod3-bronze-gap.md) — gap analysis + live evidence
- [ADR-0007](../docs/adr/0007-bronze-canonical-contract.md) (canonical) · [ADR-0006](../docs/adr/0006-optional-id-representation.md) (optional IDs) · [ADR-0005](../docs/adr/0005-clickhouse-storage-schema.md) (superseded)
- [`services/collector-rust/src/clickhouse_exporter.rs`](../services/collector-rust/src/clickhouse_exporter.rs) — the aligned exporter
- [`services/collector-rust/src/contract.rs`](../services/collector-rust/src/contract.rs) — Pod 1 → Pod 2 contract mirror (the upstream side)
