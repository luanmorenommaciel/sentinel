# Proposal — Canonical ClickHouse Read Schema (Pod 2 → Pod 3)

> **RESOLVED / CLOSED (2026-06-23).** This proposal weighed options A/B/C for reconciling the
> Rust and Go schemas. Outcome: Pod 3's **bronze** schema (contrib v0.105.0, `sentinel.*`)
> was adopted as canonical and the Rust collector aligned to write into it — recorded in
> [ADR-0007](../adr/0007-bronze-canonical-contract.md) and the
> [v1.0.0.1 read contract](../../contracts/collector/v1/pod2-pod3-read-contract.md). Kept for history.

| Field | Value |
|---|---|
| Status | **Proposed — for Crew B sync sign-off** |
| Date | 2026-06-16 |
| Author | Victor Urquiola (Pod 2) |
| Decision owners | Captain + Pod 2 leads (Alex Botelho · Victor Urquiola · Ruan Pomponet) |
| Affects | Pod 2 (both collectors) · Pod 3 (Watchers / data modeling) |
| Supersedes question | "DEFINE v1.1: do not reconcile schemas — POD 3 decides later" |
| Related | [ADR-0004](../adr/0004-collector-implementation-language.md) · [ADR-0005](../adr/0005-clickhouse-storage-schema.md) · [ADR-0006](../adr/0006-optional-id-representation.md) · [read contract](../../contracts/collector/v1/pod2-pod3-read-contract.md) · [divergence doc](../clickhouse-schema-divergence.md) |

---

## TL;DR

The Go and Rust collectors currently write **incompatible ClickHouse schemas**.
`feat/monorepo-integration` (DEFINE v1.1) deliberately left them unreconciled and
deferred the canonical decision to Pod 3. **This proposal asks Crew B to make one
decision now: pick the canonical *read schema* (the table/column shape Pod 3 codes
against).** This is separable from — and does **not** block — the still-open
ADR-0004 language bake-off.

**Recommendation:** adopt the **Rust / ADR-0005** conventions as canonical; require
whichever collector runs (Go or Rust) to emit that shape; adopt one idea *from* Go
(an additive `IngestedAt` column). Restore + freeze the read contract on the
integration branch so Pod 3 has a single source of truth.

---

## 1. Problem

The Pod 1 → Pod 2 **input** contract is *not* the issue — `otlp_output.schema.json`
v1.0.0 is semantically identical on all three branches. The fork is entirely in the
Pod 2 → Pod 3 **read schema** (what lands in ClickHouse). A Pod 3 query written for
one collector returns **zero rows or errors** against the other.

The monorepo records the divergence
([`docs/clickhouse-schema-divergence.md`](../clickhouse-schema-divergence.md)) but
explicitly *defers* the decision. Consequence: on the branch Pod 3 would actually
clone, there is **no canonical schema, no decision record, and two competing DDLs**.
That is the one thing Pod 3 cannot "start confidently" against.

## 2. Two decisions, deliberately separated

DEFINE v1.1 conflated two independent choices. Separating them unblocks Pod 3 without
forcing the perf bake-off:

| Decision | Recommendation | Why it can be made independently |
|---|---|---|
| **A. Runtime collector language** (ADR-0004: Go vs Rust) | **Keep deferred** until the perf bake-off produces numbers | Pod 3 reads ClickHouse; it does not care which binary wrote the rows |
| **B. Canonical read schema** (this proposal) | **Decide now** | ADR-0005 itself states the schema "must be decided before the read contract can freeze, because it determines the column names and types Pod 3 codes against" |

Whichever language wins **A** simply must emit the schema chosen in **B**.

## 3. Verified divergence (what Pod 3 is up against)

Confirmed against the DDL + exporters of both collectors. The original divergence doc
was directionally correct but missed several **blocker-grade** rows (marked ⛔):

| Dimension | Rust (`services/collector-rust`) | Go (`services/collector-go`) | Severity |
|---|---|---|---|
| Traces table | `otel_traces` | `otel_spans` | ⛔ |
| Column naming | PascalCase | snake_case | ⛔ |
| Event-time type | `DateTime64(9,'UTC')` | raw `Int64 *_unix_nano` | ⛔ |
| Partition key | `toDate(Timestamp)` (signal-time) | `toYYYYMM(toDateTime(ingested_at))` (ingestion-time) | high |
| Optional IDs | `''` empty-string sentinel (ADR-0006) | `Nullable(String)` → incompatible SQL (`= ''` vs `IS NULL`) | ⛔ |
| Hoisted metadata cols | **5** typed (incl. `SentinelScenario`) | **2** (`contract_version`, `ingested_at`); rest in `Map` | ⛔ |
| `rolling_stats` rollup (`otel_metrics_1m` + MV) | ✅ present (z-score baseline) | ❌ none | ⛔ |
| TTL | 30 / 30 / 90 d | none | high |
| Histograms | silently **dropped** | flattened into rows (`bucket_le`) | ⛔ |
| Database / transport | `default` / HTTP `:8123` | `sentinel` / native `:9000` | low |

Detail + line-level evidence: see the review notes appended to the integration PR.

## 4. Recommendation — adopt Rust / ADR-0005 as canonical

| # | Reason | Impact for Pod 3 |
|---|---|---|
| 1 | **Only schema with a decision record.** ADR-0005 + ADR-0006 + read contract v1.0.0-rc.1 document every column, type, guarantee, and optional-ID semantic. Go's `contract.{json,yml}` conflates input + read versions under one `1.0.0` and has no ADR rationale. | A canonical schema needs a *why*, not just a *what*. |
| 2 | **OTel / ClickStack alignment.** PascalCase + `otel_logs/otel_traces/otel_metrics` is the ClickStack convention; ADR-0005 chose it so a future move to the upstream OTel-native schema is rename-light. Go's snake_case + `otel_spans` diverges from upstream. | Eventual ClickStack adoption is easier, not harder. |
| 3 | **Query ergonomics.** 5 hoisted, `LowCardinality`, primary-index-participating columns mean Watcher filters (`WHERE SentinelScenario=`, `WHERE ServiceName=`) hit the index; Go buries those in `Map(String,String)` (full scans). `DateTime64(9,'UTC')` gives native date pruning + `INTERVAL` arithmetic; Go's raw `Int64` forces `fromUnixTimestamp64Nano()` wrapping everywhere. | Meets the <1s aggregation target. |
| 4 | **Purpose-built detection substrate.** `otel_metrics_1m` + the MV give Pod 3 a ready z-score baseline (count/sum/sum_sq/min/max per service/metric/scenario) — the `rolling_stats` spine stage, pre-materialized. Go has no equivalent. | Pod 3 doesn't have to build the rollup. |
| 5 | **Safe absence semantics.** ADR-0006's `''` sentinel is safe because present IDs are validated as 32/16-hex upstream; it avoids the per-column null-bitmap + `isNull()/coalesce()` that Go's `Nullable` forces into every correlation query. | Cleaner, faster correlation queries. |

**Adopt one idea *from* Go:** add an **additive `IngestedAt DateTime64(9,'UTC')`** column
for late-arrival / lag / Storage-watcher analysis — but keep **signal-time**
partitioning (Rust), not ingestion-time (Go). Additive ⇒ a minor read-contract bump,
not a breaking change.

## 5. What "make Go conform" means (bounded, if Go stays a bake-off entrant)

Rename `otel_spans` → `otel_traces`; snake_case → PascalCase; `Int64 *_unix_nano` →
`DateTime64(9,'UTC')` (+ derived `Duration`); add the 5 hoisted columns
(`ServiceName`, `SentinelScenario`, `SentinelRunId`, `CloudProvider`,
`SentinelSynthetic UInt8`); switch `Nullable` IDs → `''` sentinel; add
`otel_metrics_1m` + the MV; add TTLs. None of this touches the OTLP ingest path.

**Alternative if conformance is out of scope this sprint:** explicitly scope Pod 3 to
the **Rust** collector for the foundation phase and tag Go conformance as follow-up
work. Either way Pod 3 gets a single, stable target.

## 6. Decision asks for the sync

- [ ] **A.** Adopt the Rust / ADR-0005 conventions as the **canonical read schema**? (recommend: yes)
- [ ] **B.** Path for Go: **(i)** conform to the canonical schema, or **(ii)** scope Pod 3 to Rust for the foundation phase and defer Go conformance?
- [ ] **C.** Accept the additive `IngestedAt` column into the canonical schema?
- [ ] **D.** Flip **ADR-0005** and **ADR-0006** `Proposed → Accepted` and promote the read contract `1.0.0-rc.1 → 1.0.0` once a Pod 3 reviewer signs off?
- [ ] **E.** Confirm ADR-0004 (collector language) **stays deferred** and is decoupled from the above.

## 7. Still needs an owner (not resolved here)

These remain open and should **not** be silently decided as part of this proposal:

- **Pod ↔ layer ownership** — the README frames POD3 = storage/read-layer; CLAUDE.md
  lists B3 = Volume/Schema/Latency/Storage watchers. Needs Captain/Commander sign-off.
- **ClickHouse operational ownership** — currently unassigned (grants, migrations,
  the canonical database name `default` vs `sentinel`).
- **Pod 3 staffing** — B3 is unstaffed, so the read-contract review freeze-gate (#4)
  cannot close until a reviewer is borrowed/assigned.

## 8. If approved — follow-up work

1. Make the canonical DDL the single source the orchestrator's `make init` applies (replace the per-collector branch).
2. Open the Go-conformance task (or the "Pod 3 → Rust only" scoping note).
3. Run the Pod 3 inbound contract review; on close, flip ADR-0005/0006 to Accepted and promote the contract to `1.0.0`.
4. Resolve the documented attribute-naming nit (`LogAttributes` / `SpanAttributes` / `Attributes`) before Pod 3 writes queries.
5. Make Rust's histogram skip explicit/logged; document v1.0.0 as gauge/sum-only in both collectors.
