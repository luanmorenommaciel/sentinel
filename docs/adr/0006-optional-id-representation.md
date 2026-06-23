# ADR-0006 · Optional trace/span IDs in ClickHouse — empty-string sentinel vs Nullable

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 2026-06-01 |
| Owners | Pod 2 (OTel Collector) |
| Proposer | Victor Urquiola |
| Supersedes | — |
| Related | ADR-0005 (storage schema) · ADR-0007 (bronze canonical contract — refines this) · [schema design note](../research/clickhouse-schema-pod2.md) · [Pod 2→Pod 3 read contract](../contracts/pod2-pod3-read-contract.md) |

> **Refined by [ADR-0007](0007-bronze-canonical-contract.md) (2026-06-23), not superseded.**
> The `''`=absent decision still holds on the bronze schema: bronze stores `TraceId` /
> `SpanId` / `ParentSpanId` as plain `String`, and its own `otel_traces_trace_id_ts_mv`
> treats `WHERE TraceId != ''` as "present". One change under bronze — the hex-validity
> invariant below is now enforced **collector-side at insert** (bronze is a generic contrib
> schema that does not validate IDs), rather than being implied by the table. Pod 3 readers
> still use `WHERE Column = ''` / `!= ''` exactly as stated here.

## Context

Three ID fields are optional in Pod 1's contract (`contract.rs`):

- `LogSignal.trace_id: Option<String>` and `LogSignal.span_id: Option<String>`
- `SpanSignal.parent_span_id: Option<String>` (`None` for root spans — ~50% of
  the golden spans)

ClickHouse offers two ways to store an optional string column:

1. **Empty-string sentinel** — `TraceId String`, store `''` when absent.
2. **`Nullable(String)`** — explicit `NULL` for absent, at the cost of a
   per-column null-bitmap and `NULL`-handling in every reader query.

This choice is part of the Pod 2 → Pod 3 read contract: Pod 3's Watchers (e.g.
Arrival/W01 correlating logs to traces) need an unambiguous way to ask "does
this record have trace context?".

The decision is **separable and Pod-3-facing**, so it gets its own ADR rather
than being buried in the schema ADR (per the "one decision per ADR" rule).

## Decision

**Use the empty-string `''` sentinel for absent IDs in v1.**

The crux that makes this safe: `contract.rs` validates that a *present* ID is
exactly 32 (trace) or 16 (span) lowercase-hex characters — a present ID can
**never** be the empty string. Therefore `''` is an unambiguous "absent" marker;
it cannot collide with a legitimate value. Pod 3 readers treat `Column = ''` as
"absent", `Column != ''` as "present and valid hex".

## Options considered

| Option | Summary | Verdict |
|---|---|---|
| **A. Empty-string sentinel (chosen)** | `String`, `''` = absent | Chosen — no null-bitmap; `''` can't collide with a valid hex ID, so it's unambiguous |
| B. `Nullable(String)` | `NULL` = absent | Deferred — semantically explicit, but adds a null-bitmap column (non-trivial for `ParentSpanId`, ~50% null) and forces `isNull()`/`coalesce` into every Watcher query |
| C. Separate `HasTrace UInt8` flag column | boolean + the ID column | Rejected — redundant given the hex-validation invariant already disambiguates `''` |

## Trade-offs

- **Sentinel ('') :** smaller/faster (no bitmap), simplest reader code, relies
  on the upstream hex-validation invariant to stay unambiguous.
- **Nullable :** self-documenting at the type level, but the invariant above
  already removes the ambiguity Nullable would resolve — so we'd pay the
  bitmap + query-complexity cost for clarity we get for free.

## Consequences

- The read contract states: **optional IDs are `''` when absent; never `NULL`;
  a non-empty value is guaranteed valid hex** (32/16 chars, lowercase).
- Pod 3 filters absence with `WHERE TraceId = ''`, presence with `!= ''`.
- If a future contract version legitimately needs to distinguish "absent" from
  "present but empty" (not possible today), this ADR is superseded.

## Risks

- **A future signal type where `''` is a valid ID value.** Effectively
  impossible while the 32/16-hex-validation invariant holds upstream; if Pod 1
  ever relaxes that, this decision must be revisited (and the read contract
  re-versioned).
- **Reader forgets the convention.** Mitigated by stating it explicitly in the
  read contract and in the DDL column comments.

## Next steps

1. Confirm with Pod 3 that `''` = absent satisfies the Arrival/W01 log↔trace
   correlation semantics before the read contract freezes.
2. Encode the invariant in the read contract's per-column guarantees.

## References

- [`services/collector-rust/src/contract.rs`](../../services/collector-rust/src/contract.rs) — `Option<String>` ID fields + hex validation (`is_hex_32` / `is_hex_16`)
- [`docs/research/clickhouse-schema-pod2.md`](../research/clickhouse-schema-pod2.md) — open question ADR-Q2
- [`infra/clickhouse/init.d/01-bronze-otel.sql`](../../infra/clickhouse/init.d/01-bronze-otel.sql) — bronze `String` ID columns + the `otel_traces_trace_id_ts_mv` `TraceId != ''` filter (the hand-rolled `infra/clickhouse/ddl/00{1,2}_*.sql` originally referenced here are superseded by ADR-0007)
