# ADR-0005 · ClickHouse storage schema for OTLP signals (hand-rolled vs OTel-native)

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 2026-06-01 |
| Owners | Pod 2 (OTel Collector) |
| Proposer | Victor Urquiola |
| Supersedes | — |
| Related | ADR-0004 (Collector language) · [schema design note](../research/clickhouse-schema-pod2.md) · [Pod 2→Pod 3 read contract](../contracts/pod2-pod3-read-contract.md) · ADR-0006 (optional-ID representation) |

## Context

Pod 2's Collector parses Pod 1's OTLP signals (`contract.rs`: `LogSignal`,
`SpanSignal`, `MetricSignal`) and must persist them to ClickHouse so Pod 3's
Watchers (Volume, Schema, Latency, Storage) can run detection reads. The
**table schema is the Pod 2 → Pod 3 interface** — it is to Pod 3 what Pod 1's
`otlp_output.schema.json` v1.0.0 is to Pod 2.

There are two ways to get a ClickHouse schema for OTel data:

1. **Adopt the OTel-native schema** — the OpenTelemetry Collector's ClickHouse
   exporter (and ClickStack) ships an opinionated, production-tested schema
   (`otel_logs`, `otel_traces`, `otel_metrics_*` with `Map`-heavy columns).
2. **Hand-roll** a schema tailored to Sentinel's contract — fewer columns, the
   5 guaranteed resource keys hoisted into typed columns, a purpose-built
   rolling-stats pre-aggregation for Tier-1 detection.

This decision must be made before the read contract can be frozen, because it
determines the column names and types Pod 3 codes against.

## Decision

**Hand-roll the schema for the MVP** (see `infra/clickhouse/ddl/`), with three
defining choices:

- **Engine:** plain `MergeTree` for the three raw tables (append-only synthetic
  telemetry, no dedup key); `AggregatingMergeTree` + `SimpleAggregateFunction`
  for the `otel_metrics_1m` rolling-stats table (per-column merge combinators —
  see ADR rationale in the DDL header and the min/max correctness note).
- **Resource-key hoisting:** promote the 5 keys guaranteed by Pod 1's
  `REQUIRED_RESOURCE_KEYS` (`service.name`, `sentinel.scenario`,
  `sentinel.run_id`, `cloud.provider`, `sentinel.synthetic`) into typed
  `LowCardinality`/`UInt8` columns; keep the rest in `Map(String,String)`.
- **Naming:** follow ClickStack PascalCase conventions (`ServiceName`,
  `Timestamp`, `SeverityText`) even though we hand-roll, so a future migration
  to the OTel-native schema is a rename-light path, not a rewrite.

Revisit adopting the OTel-native schema if/when Sentinel adopts the upstream
OTel Collector's ClickHouse exporter plugin (a separate, larger decision).

## Options considered

| Option | Summary | Verdict |
|---|---|---|
| **A. Hand-rolled (chosen)** | Tailored columns, hoisted keys, custom rolling-stats MV | Chosen for MVP — control + learning + index-accelerated Watcher filters |
| B. OTel-native ClickStack | Adopt the standard exporter schema wholesale | Deferred — couples us to the upstream exporter before we've chosen it (ADR-0004 still open); `Map`-only resource attrs defeat index-accelerated scenario/service filtering |
| C. Hybrid | OTel-native tables + our own MV layer on top | Rejected for MVP — combines both migration surfaces with none of the simplicity |

## Trade-offs

**For hand-rolled:** every column-type decision is understood (the team is new
to ClickHouse + the OTel data model); hoisted keys let Watcher queries use the
primary index instead of `Map` lookups (the KB's <1s aggregation target);
the rolling-stats MV is shaped exactly for z-score detection.

**Against:** we own a schema the upstream community would otherwise maintain;
risk of reinventing decisions ClickStack already got right; a later migration
to the standard schema is real work (shadow table + dual-write + cutover, since
`ORDER BY` is immutable post-creation).

## Consequences

- Pod 3 codes against our column names/types (documented in the read contract).
- The PascalCase naming choice keeps a future ClickStack migration rename-light.
- The hoisting choice is the one most likely to force a migration if Pod 1 adds
  guaranteed resource keys in contract v2 — flagged in the read contract.

## Risks

- **Schema drift from upstream.** Mitigated by mirroring ClickStack naming.
- **Hoisting churn on contract v2.** Mitigated by treating the hoisted set as a
  versioned part of the read contract (a v2 resource key = a contract minor bump).
- **Reinvention.** Mitigated by keeping the design note's rationale auditable.

## Next steps

1. Day-4/5: write the Rust exporter; prove golden file → ClickHouse round-trips
   to the expected 48/48/183 counts (verifies the schema is real, not just valid).
2. Resolve ADR-0006 (optional-ID representation) — it changes column types.
3. Freeze the [Pod 2 → Pod 3 read contract](../contracts/pod2-pod3-read-contract.md)
   to v1.0.0 after (1) + (2) + Pod 3 review.

## References

- [`docs/research/clickhouse-schema-pod2.md`](../research/clickhouse-schema-pod2.md) — full design receipts
- [`infra/clickhouse/ddl/`](../../infra/clickhouse/ddl/) — the executable schema
- [`services/collector-rust/src/contract.rs`](../../services/collector-rust/src/contract.rs) — source-of-truth field set
- `.claude/kb/storage/clickhouse/index.md` — ClickHouse KB
- ADR-0004 — Collector implementation language (still open; this ADR avoids pre-committing to the upstream exporter)
