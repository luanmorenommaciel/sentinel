# ADR-0007 · Bronze (otel-collector-contrib v0.105.0) ClickHouse schema as the canonical Pod 2 → Pod 3 contract

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 2026-06-23 |
| Owners | Pod 2 (OTel Collector) · Pod 3 (Data modelling) |
| Proposer | Victor Urquiola |
| Supersedes | ADR-0005 (hand-rolled ClickHouse storage schema) |
| Related | ADR-0006 (optional-ID representation — refined, not superseded) · ADR-0004 (Collector language) · [Pod 2→Pod 3 read contract](../contracts/pod2-pod3-read-contract.md) · [bronze gap analysis](../research/pod3-bronze-gap.md) · [schema-divergence note](../clickhouse-schema-divergence.md) · bronze DDL `infra/clickhouse/init.d/01-bronze-otel.sql` |

## Context

ADR-0005 chose a **hand-rolled** ClickHouse schema (`default.*`, the 5 guaranteed
resource keys hoisted into typed columns, a custom `otel_metrics_1m` rolling-stats
MV) as the Pod 2 → Pod 3 interface, explicitly **deferring** the OTel-native option
(its Option B) until the upstream exporter was chosen.

Two facts have since changed the ground:

1. **Pod 3 took ownership of the bronze layer.** Pod 3 committed a version-controlled
   bronze DDL (`infra/clickhouse/init.d/01-bronze-otel.sql`, commit `660920d`) pinned
   to the **otel-collector-contrib v0.105.0** ClickHouse-exporter schema: database
   `sentinel`; `otel_logs`, `otel_traces`, five `otel_metrics_*` type-tables;
   `Map(LowCardinality(String),String)` attributes; full Scope/Events/Links/Exemplars
   columns; `create_schema:false`. The file self-declares as a TYPE CONTRACT.
2. **Both collectors converged.** Pod 2 normalized the Go + Rust collectors onto one
   schema (commit `de5cc24`), resolving the earlier `default.*` divergence.

This left two competing read schemas: ADR-0005's hand-rolled one (which the collectors
wrote) and Pod 3's bronze (valid but unpopulated). The decision ADR-0005 deferred is now
forced — and Pod 3, the rightful owner of the data model, has chosen the OTel-native path.
A gap analysis ([`pod3-bronze-gap.md`](../research/pod3-bronze-gap.md)) showed the
divergence is concentrated at the **export layer, not the parser**, so aligning the Rust
collector to write into bronze is a bounded, exporter-only change.

## Decision

**Adopt Pod 3's bronze DDL (otel-collector-contrib v0.105.0, `sentinel.*`) as the
canonical Pod 2 → Pod 3 read-schema contract, and align the Rust collector to write
directly into it.** This reverses ADR-0005's "hand-roll for the MVP" decision (its
Option B is now chosen).

The Rust collector now:

- writes to database `sentinel`, tables `otel_logs` / `otel_traces`, routing metrics by
  data-point type into `otel_metrics_gauge` / `otel_metrics_sum`;
- carries the 5 Sentinel / `cloud.provider` / `contract_version` values inside
  `ResourceAttributes` (bronze has no typed columns for them — ADR-0005's hoisting is
  reversed; only `service.name` is copied into the typed `ServiceName` column, matching
  contrib);
- leaves the contrib-rich columns it does not produce (TraceState, SpanKind, Scope*,
  StatusMessage, Events.*, Links.*, Exemplars.*, histogram/summary/exp tables) at their
  ClickHouse defaults — the named-column `INSERT` makes this safe;
- no longer emits `otel_metrics_1m` — that rolling-stats rollup becomes a Pod 3 **silver**
  artifact.

The parser (`otlp.rs`) and the receive-boundary validation layer (`contract.rs`) are
**unchanged**. Ownership inverts: the schema is a version-controlled artifact Pod 3 owns
(`create_schema:false`; the collector only INSERTs), not an emergent property of collector
code. The contrib version (`v0.105.0`) is the schema version anchor.

## Options considered

| Option | Summary | Verdict |
|---|---|---|
| **A. Bronze = canonical; align collector (chosen)** | Pod 3's contrib bronze is the contract; Rust writes into it | Chosen — Pod 3 owns the model and has committed the DDL; aligning is a bounded, validated exporter-only change; the upstream-standard schema turns a future ClickStack move into adoption, not migration |
| B. Keep ADR-0005 hand-rolled; Pod 3 re-pins bronze to it | Bronze becomes the hand-rolled shape | Rejected — contradicts Pod 3's `create_schema:false` + "contrib is the type contract" stance; keeps a bespoke schema the community would otherwise maintain |
| C. Meet in the middle (Pod 3 adds the 5 Sentinel typed columns to bronze) | Bronze + Sentinel typed cols | Deferred — preserves index-accelerated Sentinel filters but diverges from the verbatim contrib dump; better handled as silver materialized columns (Pod 3) than by forking bronze |

## Trade-offs

**For bronze:** one canonical, version-controlled, Pod-3-owned schema; the
upstream-standard shape; and a *simpler* collector (the exporter shrank ~125 net lines —
hoisting and the bespoke MV are gone).

**Against:** the 5 Sentinel keys move from typed, index-accelerated columns into
`Map(LowCardinality(String),String)` — filtering by `sentinel.scenario` / `run_id` /
`cloud.provider` becomes a Map probe rather than a primary-index hit (exactly the
regression ADR-0005's Option-B verdict warned about). `ServiceName` keeps its typed
column. Pod 3 can recover the fast path with **materialized columns in silver** if Watcher
latency requires it. The `otel_metrics_1m` rolling-stats input for Tier-1 z-score detection
moves to silver and must be rebuilt there.

## Consequences

- **ADR-0005 is superseded** (status flipped; body kept as historical). Its PascalCase
  choice is **vindicated**: because the hand-rolled columns were already
  `ServiceName` / `Timestamp` / `TraceId` / `Duration` / etc., this migration was
  rename-light (column re-mapping + Map-demotion of 5 keys), not a rewrite — exactly as
  ADR-0005 §Decision predicted.
- **ADR-0006 is refined, not superseded.** The `''`=absent convention holds: bronze stores
  `TraceId` / `SpanId` / `ParentSpanId` as plain `String`, and its own
  `otel_traces_trace_id_ts_mv` keys on `WHERE TraceId != ''`. One change: the hex-validity
  invariant is now enforced **collector-side at insert** (bronze is a generic contrib
  schema that does not validate), not implied by the table. See the ADR-0006 annotation.
- **The read contract is rewritten to v1.0.0.1** — it points at the bronze DDL
  as source of truth (db `sentinel`) and documents the *semantic* layer a raw DDL cannot
  express (the 5 Sentinel keys guaranteed present in `ResourceAttributes`; `''`=absent +
  valid-hex; Duration ns; metrics split gauge/sum; the rollup is silver).
- Pod 3 builds Watchers/silver against bronze and owns the DDL lifecycle.
- The Go collector still writes `default.*`; it needs the same alignment to feed bronze
  (tracked separately).

## Risks

- **Index-acceleration regression on Sentinel filters.** Mitigated by Pod 3 materializing
  the hot keys in silver if needed; `ServiceName` (the most common filter) keeps its typed
  column.
- **Rollup gap for Tier-1 detection.** `otel_metrics_1m` must be rebuilt in silver before
  z-score detection has an input — flagged for Pod 3.
- **Pinned to a contrib version.** Bronze is pinned to v0.105.0; a Collector-image bump
  requires re-dumping the schema (documented in the bronze DDL header).
- **`StatusCode` value convention.** The collector writes `"OK"` / `"ERROR"`; if Pod 3's
  silver keys on the contrib enum (`"Unset"` / `"Ok"` / `"Error"`), a one-line exporter
  change is needed (R3, open).

## Next steps

1. **Acceptance gate** (flips Proposed → Accepted): round-trip-into-bronze evidence + Pod 3
   sign-off. The **evidence is met** — generator → Rust collector → `sentinel.*` lands
   40,200 logs / 40,200 traces / 152,700 metrics (gauge 83,400 + sum 69,300), lossless;
   file-mode golden round-trip green. **Pod 3 review is open.**
2. On acceptance: flip ADR-0005 → `Superseded by ADR-0007`; the read contract is firmed at
   `1.0.0.1`.
3. Confirm with Pod 3: the `StatusCode` value convention (R3) and ownership of the
   `otel_metrics_1m` rollup in silver (R4).
4. Align the Go collector to bronze (separate task).

## References

- [`infra/clickhouse/init.d/01-bronze-otel.sql`](../../infra/clickhouse/init.d/01-bronze-otel.sql) — the canonical bronze DDL (Pod 3, contrib v0.105.0)
- [`docs/research/pod3-bronze-gap.md`](../research/pod3-bronze-gap.md) — gap analysis, minimum-change set, and the live evidence
- [`docs/contracts/pod2-pod3-read-contract.md`](../contracts/pod2-pod3-read-contract.md) — the read contract (rewritten to v1.0.0.1)
- [ADR-0005](0005-clickhouse-storage-schema.md) (superseded) · [ADR-0006](0006-optional-id-representation.md) (refined)
- [`services/collector-rust/src/clickhouse_exporter.rs`](../../services/collector-rust/src/clickhouse_exporter.rs) — the aligned exporter
