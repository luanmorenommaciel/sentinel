# Pod 2 → Pod 3 ClickHouse Read Contract

| Field | Value |
|---|---|
| Status | **Proposed — authoritative for integration (release candidate)** |
| Version | `1.0.0-rc.1` |
| Date | 2026-06-05 (promoted from `0.1.0-draft`, published 2026-06-01) |
| Producer | Pod 2 (OTel Collector) |
| Consumer | Pod 3 (Volume · Schema · Latency · Storage Watchers) |
| Transport | ClickHouse — HTTP `:8123` / native `:9000`, database `default` |
| Source of truth | [`infra/clickhouse/ddl/`](../../infra/clickhouse/ddl/) (executable schema) |
| Decisions | [ADR-0005](../adr/0005-clickhouse-storage-schema.md) (schema) · [ADR-0006](../adr/0006-optional-id-representation.md) (optional IDs) |
| Rationale | [`docs/research/clickhouse-schema-pod2.md`](../research/clickhouse-schema-pod2.md) |

> **This contract is an authoritative release candidate (`1.0.0-rc.1`) — build
> against it now.** It is the mirror, in the other direction, of Pod 1's
> `otlp_output.schema.json` v1.0.0 that Pod 2 consumes. The exporter that
> produces these tables is implemented and round-trip verified (see
> [Freeze gates](#freeze-gates-what-blocks-v100)). Pod 3 should design and build
> Watchers against this RC today: the table/column shape and the semantic
> guarantees in §5 are stable. Any breaking change before the final `1.0.0` will
> come via an RC bump (`-rc.2`, …) with notice — not silently. The two remaining
> [freeze gates](#freeze-gates-what-blocks-v100) (ADR-0005/0006 acceptance and
> Pod 3 sign-off) promote this RC to a frozen `1.0.0`; they do **not** block
> Pod 3 from building.

---

## 1. What this contract covers

Pod 2's Collector parses Pod 1's OTLP signals and writes them to ClickHouse.
Pod 3's Watchers **read** from these tables. This document is the read
interface: table names, columns, types, and the **semantic guarantees** Pod 3
may rely on — plus the consumer obligations Pod 3 must honour.

It does **not** cover the OTLP `:4317` gRPC ingest path (Pod 2's *input* side,
still Pod 1's NDJSON contract in the MVP).

---

## 2. Tables

Four objects. Three raw signal tables + one rolling-stats pre-aggregation that
feeds Tier-1 (z-score) detection.

### 2.1 `otel_logs` — from `LogSignal`

| Column | Type | Guarantee |
|---|---|---|
| `Timestamp` | `DateTime64(9, 'UTC')` | Event time (`time_unix_nano`), nanosecond precision, UTC |
| `ServiceName` | `LowCardinality(String)` | Always present (hoisted `service.name`) |
| `SentinelScenario` | `LowCardinality(String)` | Always present (hoisted `sentinel.scenario`) |
| `SentinelRunId` | `LowCardinality(String)` | Always present (hoisted `sentinel.run_id`) |
| `CloudProvider` | `LowCardinality(String)` | Always present (hoisted `cloud.provider`) |
| `SentinelSynthetic` | `UInt8` | `1`/`0` (hoisted `sentinel.synthetic`) |
| `SeverityText` | `LowCardinality(String)` | OTel severity (`INFO`, `ERROR`, …) |
| `SeverityNumber` | `Int32` | OTel severity number |
| `Body` | `String` | Log message text |
| `TraceId` | `String` | 32-char lowercase hex, **`''` if absent** (see §4) |
| `SpanId` | `String` | 16-char lowercase hex, **`''` if absent** (see §4) |
| `ContractVersion` | `LowCardinality(String)` | Pod 1 contract version, e.g. `1.0.0` |
| `LogAttributes` | `Map(String, String)` | Record-level attributes |
| `ResourceAttributes` | `Map(String, String)` | Non-hoisted resource attrs |

`ORDER BY (ServiceName, Timestamp, TraceId)` · `PARTITION BY toDate(Timestamp)` · TTL 30d (placeholder, see [freeze gates](#freeze-gates-what-blocks-v100)).

### 2.2 `otel_traces` — from `SpanSignal`

| Column | Type | Guarantee |
|---|---|---|
| `Timestamp` | `DateTime64(9, 'UTC')` | Span **start** time (`start_unix_nano`) |
| `TraceId` | `String` | 32-char lowercase hex, always present |
| `SpanId` | `String` | 16-char lowercase hex, always present |
| `ParentSpanId` | `String` | 16-char lowercase hex, **`''` for root spans** (see §4) |
| `SpanName` | `LowCardinality(String)` | Span name |
| `ServiceName` | `LowCardinality(String)` | Always present (hoisted) |
| `SentinelScenario` | `LowCardinality(String)` | Always present (hoisted) |
| `SentinelRunId` | `LowCardinality(String)` | Always present (hoisted) |
| `CloudProvider` | `LowCardinality(String)` | Always present (hoisted) |
| `SentinelSynthetic` | `UInt8` | `1`/`0` (hoisted) |
| `Duration` | `Int64` | **Nanoseconds** (`end_unix_nano - start_unix_nano`), pre-computed; `/1e6` for ms. W05 reads quantiles over this |
| `StatusCode` | `LowCardinality(String)` | `"OK"` or `"ERROR"` |
| `ContractVersion` | `LowCardinality(String)` | e.g. `1.0.0` |
| `SpanAttributes` | `Map(String, String)` | Span-level attributes |
| `ResourceAttributes` | `Map(String, String)` | Non-hoisted resource attrs |

`ORDER BY (ServiceName, Timestamp, TraceId)` · `PARTITION BY toDate(Timestamp)` · TTL 30d.

> **Note:** `end_unix_nano` is **not** a column — only `Duration` is stored.
> "When did this span end" is `Timestamp + Duration`.

### 2.3 `otel_metrics` — from `MetricSignal`

| Column | Type | Guarantee |
|---|---|---|
| `Timestamp` | `DateTime64(9, 'UTC')` | Event time (`time_unix_nano`) |
| `MetricName` | `LowCardinality(String)` | Metric name |
| `MetricType` | `LowCardinality(String)` | `"gauge"` or `"sum"` (no histogram in v1.0.0) |
| `Value` | `Float64` | Sample value |
| `ServiceName` | `LowCardinality(String)` | Always present (hoisted) |
| `SentinelScenario` | `LowCardinality(String)` | Always present (hoisted) |
| `SentinelRunId` | `LowCardinality(String)` | Always present (hoisted) |
| `CloudProvider` | `LowCardinality(String)` | Always present (hoisted) |
| `SentinelSynthetic` | `UInt8` | `1`/`0` (hoisted) |
| `ContractVersion` | `LowCardinality(String)` | e.g. `1.0.0` |
| `Attributes` | `Map(String, String)` | Metric-level attributes |
| `ResourceAttributes` | `Map(String, String)` | Non-hoisted resource attrs |

`ORDER BY (ServiceName, MetricName, Timestamp)` · `PARTITION BY toDate(Timestamp)` · TTL 90d.

### 2.4 `otel_metrics_1m` — rolling-stats pre-aggregation (Tier-1 input)

`AggregatingMergeTree`, populated by the `otel_metrics_1m_mv` materialized view
on every insert into `otel_metrics`. **1-minute buckets per
(service, metric, scenario).** This is the table Tier-1 z-score detection reads.

| Column | Type | Meaning |
|---|---|---|
| `window_start` | `DateTime` | `toStartOfMinute(Timestamp)` |
| `ServiceName` | `LowCardinality(String)` | |
| `MetricName` | `LowCardinality(String)` | |
| `SentinelScenario` | `LowCardinality(String)` | Separate baselines per scenario |
| `count` | `SimpleAggregateFunction(sum, UInt64)` | Sample count |
| `sum_val` | `SimpleAggregateFunction(sum, Float64)` | Σ value → mean = `sum_val/count` |
| `sum_sq` | `SimpleAggregateFunction(sum, Float64)` | Σ value² → stddev (below) |
| `min_val` | `SimpleAggregateFunction(min, Float64)` | Window min |
| `max_val` | `SimpleAggregateFunction(max, Float64)` | Window max |

`ORDER BY (ServiceName, MetricName, SentinelScenario, window_start)` · TTL 90d.

> **⚠ CONSUMER OBLIGATION (§3).** These are `SimpleAggregateFunction` columns.
> Parts may be unmerged, so you **must re-aggregate with the same function** in
> a `GROUP BY` (or use `FINAL`) — reading the raw columns can return multiple
> rows per `(key, window)`.

---

## 3. How Pod 3 must read `otel_metrics_1m`

Correct mean + stddev for a z-score baseline:

```sql
SELECT
    ServiceName, MetricName, SentinelScenario,
    sum(sum_val) / sum(count)                                              AS mean,
    sqrt(sum(sum_sq) / sum(count) - pow(sum(sum_val) / sum(count), 2))     AS stddev,
    min(min_val)                                                          AS lo,
    max(max_val)                                                          AS hi
FROM otel_metrics_1m
WHERE ServiceName = {svc:String}
  AND MetricName = {metric:String}
  AND SentinelScenario = {scenario:String}
  AND window_start >= now() - INTERVAL 7 DAY
GROUP BY ServiceName, MetricName, SentinelScenario;
```

Re-applying `sum`/`min`/`max` is mandatory — not an optimization. Reading
`min_val` directly without `min(...)` may return a per-part partial, not the
true window min.

---

## 4. Optional-ID semantics (per ADR-0006)

`TraceId` / `SpanId` (logs) and `ParentSpanId` (traces) are **`''` when absent,
never `NULL`.** A non-empty value is guaranteed valid lowercase hex (32 or 16
chars) — Pod 1 + Pod 2 validate this upstream, so `''` can never collide with a
real ID.

- Absent: `WHERE TraceId = ''`
- Present: `WHERE TraceId != ''`

---

## 5. Guarantees Pod 2 makes (won't change without a version bump)

1. **Table + column names and types** as listed in §2.
2. **The 5 hoisted resource keys are always present** on every row (backed by
   Pod 1's `REQUIRED_RESOURCE_KEYS`). A v2 resource key = a contract minor bump.
3. **`Timestamp` is UTC `DateTime64(9)`** event time; `Duration` is nanoseconds.
4. **Optional IDs follow §4** (`''` = absent; non-empty = valid hex).
5. **`otel_metrics_1m` keeps the §3 read shape** (count/sum_val/sum_sq/min/max
   with the documented combinators).
6. **The documented `ORDER BY` access patterns stay index-accelerated** (filter
   by `ServiceName`, then time / metric).

## 6. Explicit NON-guarantees (do not depend on these)

- **`Map` iteration order** in `*Attributes` / `ResourceAttributes`.
- **Exact partition layout** (`toDate` today; may change).
- **Exact TTL value** — a retention *floor* will be set by a pending ADR; do not
  assume data older than the floor exists.
- **The non-hoisted `ResourceAttributes` key set** — it grows as GCP services
  are added. Filter on hoisted columns, not `ResourceAttributes[...]`, for
  anything performance-sensitive.

---

## 7. Versioning

Semver, independent of Pod 1's contract version. This is `1.0.0-rc.1`: an
authoritative release candidate — stable enough to build against, with any
breaking change gated behind an RC bump (`-rc.2`, …) until the
[freeze gates](#freeze-gates-what-blocks-v100) close and it becomes a frozen
`1.0.0`. A `ContractVersion` column on every row carries **Pod 1's** version
(not this contract's) — they version independently.

## Freeze gates (what blocks `v1.0.0`)

This contract freezes to `v1.0.0` only after **all** of:

1. ☐ **ADR-0005 accepted** — schema-as-contract (hand-rolled vs OTel-native).
2. ☐ **ADR-0006 accepted** — optional-ID representation (`''` vs Nullable).
3. ☑ **Day-4 round-trip verified** *(2026-06-01)* — golden file → ClickHouse
   yields `48 logs / 48 spans / 183 metrics`, zero parse/validation errors; the
   rolling-stats MV fires; hoisted columns populated with no key leakage into
   `ResourceAttributes`; span `Duration` derived correctly. Proven live against
   ClickHouse 25.4 via `tests/clickhouse_roundtrip.rs` (commit `973a1f0`),
   including the TTL-vs-fixture-age handling (strip TTL on the 2023-dated
   fixture). Now also runs in CI against a containerized ClickHouse
   (`.github/workflows/rust-ci.yml`, `integration` job).
4. ☐ **Pod 3 review sign-off** — Pod 3 reviews this the way Pod 2 reviewed
   Pod 1's contract (`docs/research/contract-review-pod1-v1.0.0.md`), filing
   blockers if any.

### Deferred decisions (do not block freeze, tracked for follow-up ADRs)

- **Retention tiers** (TTL 30/90d placeholders; S3 cold tier?) — design note ADR-Q1.
- **Non-hoisted attribute strategy** (`Map` vs `JSONString` vs hoist-more) — ADR-Q3.

### Known nits for Pod 3 review

- **Attribute column naming is inconsistent:** `LogAttributes` (logs),
  `SpanAttributes` (traces), `Attributes` (metrics). Harmonize before freeze?
  (Pro: consistency. Con: the OTel-native schema also uses per-signal names.)

---

## 8. How Pod 3 should respond

Treat this like an inbound contract review. For each issue, file a blocker
(B-series) or nit (N-series) the way Pod 2 did for Pod 1's contract. Open
questions especially welcome on: §4 optional-ID semantics (does `''`=absent fit
W01's log↔trace correlation?), the §3 read obligation (acceptable, or do you
want a convenience view that pre-`FINAL`s the rollup?), and the retention floor
your baselines need (drives ADR-Q1).

## See also

- [`infra/clickhouse/ddl/`](../../infra/clickhouse/ddl/) — executable schema (source of truth)
- [`docs/research/clickhouse-schema-pod2.md`](../research/clickhouse-schema-pod2.md) — design rationale + Day-4 gotchas
- [ADR-0005](../adr/0005-clickhouse-storage-schema.md) · [ADR-0006](../adr/0006-optional-id-representation.md)
- [`services/collector-rust/src/contract.rs`](../../services/collector-rust/src/contract.rs) — Pod 1→Pod 2 contract mirror (the upstream side)
- `contract/schema/otlp_output.schema.json` — Pod 1's v1.0.0 contract (the pattern this mirrors)
