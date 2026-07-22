# ClickHouse Schema Divergence (carried forward for POD 3)

> **RESOLVED by [ADR-0007](adr/0007-bronze-canonical-contract.md).** This divergence is
> fully closed. The canonical read schema is Pod 3's **bronze** DDL
> (`infra/clickhouse/init.d/01-bronze-otel.sql`, database `bronze`, `bronze.*`,
> otel-collector-contrib v0.105.0). **Both** collectors — Rust **and** Go — now write
> directly into bronze; cross-collector equivalence is verified (identical row counts). The
> retired `default.*` normalized write path is gone. Kept below for history.

The two collectors currently ship **different, incompatible** ClickHouse schemas. As decided
in DEFINE v1.1, the monorepo integration **does not** reconcile them — each collector keeps its
own DDL. This document records the divergence so POD 3 (data modeling) can make the canonical
decision later, with full context.

## Where each schema lives

| Collector | DDL location |
|-----------|--------------|
| Rust | `services/collector-rust/infra/clickhouse/ddl/{001_otel_logs,002_otel_traces,003_otel_metrics}.sql` |
| Go | `services/collector-go/migrations/001_init_schema.sql` |

## Divergence matrix

| Dimension | Rust | Go | Deferred decision (POD 3) |
|-----------|------|----|---------------------------|
| Column naming | PascalCase (`ServiceName`, `Timestamp`, `TraceId`) | snake_case (`service_name`, `time_unix_nano`, `trace_id`) | Pick one convention |
| Database | default db | `sentinel` | Pick db name |
| Traces table | `otel_traces` | `otel_spans` | Pick table name |
| Partitioning | `PARTITION BY toDate(Timestamp)` (daily) | `PARTITION BY toYYYYMM(toDateTime(ingested_at))` (monthly) | Pick partition strategy |
| Timestamp repr | `DateTime64(9, 'UTC')` | raw `*_unix_nano` Int + `ingested_at` | Pick representation |
| ORDER BY (logs) | `(ServiceName, Timestamp, TraceId)` | `(service_name, time_unix_nano)` | Pick sort key |
| Engine | `MergeTree` | `MergeTree()` | Compatible |
| Sentinel metadata cols | `SentinelScenario`, `SentinelRunId`, `CloudProvider`, `SentinelSynthetic`, `ContractVersion` | fewer / different | Decide canonical metadata columns |

## Consequence for the orchestrator

Because the schemas differ, schema initialization is **collector-scoped**: `make init` applies the
*selected* collector's own DDL. Switching `COLLECTOR` against a populated ClickHouse may leave the
other collector's tables behind — run `make reset` for a clean slate.

When POD 3 produces a canonical model, the expected change is small: replace the per-collector
`make init` branch with a single canonical DDL and update each collector's writer accordingly.
The `services/` layout and the orchestrator do not need to change.
