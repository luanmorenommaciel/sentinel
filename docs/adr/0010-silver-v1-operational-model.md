# ADR-0010 · Silver v1 operational model

| Field | Value |
|---|---|
| Status | Proposed |
| Date | 2026-08-18 |
| Owners | Pod 3 |
| Proposer | Sentinel team |
| Supersedes | — |
| Related | ADR-0007 · Pod 2 → Pod 3 read contract |

## Context

The canonical Bronze layer preserves the OTel Collector schema and carries Sentinel dimensions inside attribute Maps. The first Watchers need typed, indexed dimensions and stable one-minute inputs for latency and operational-volume detection. The current telemetry does not carry business row counts, schema snapshots, dataset identity, or expected schedules, so the first Silver contract must not imply support for those semantics.

## Decision

Create Silver v1 in ClickHouse with three physical, append-only models fed by materialized views:

- `silver.operation_executions`, one row per Bronze span;
- `silver.log_events`, one row per Bronze log record;
- `silver.metric_observations`, one row per Bronze gauge or sum data point.

Expose the complete set of read models supported by the guaranteed Bronze fields:

- `silver.metric_rollup_1m`, with count, sum, sum-of-squares, min, max, average, and population standard deviation;
- `silver.service_health_1m`, with operation/error counts and p50/p95/p99/max span latency;
- `silver.log_health_1m`, with log/error counts, severity, and affected traces;
- `silver.telemetry_coverage_1m`, with span/log/metric coverage per service and component;
- `silver.trace_summary`, one correlated summary per non-empty trace id;
- `silver.run_summary`, evidence counts and observed duration per Sentinel run.

Materialize `sentinel.scenario`, `sentinel.run_id`, `cloud.provider`, `sentinel.synthetic`, and `contract_version` as typed columns. Convert span duration from nanoseconds to milliseconds. Retain the source attribute Maps for drill-down and forward-compatible dimensions. Match Bronze's 30-day retention.

The materialized views process new Bronze inserts. Historical loading is an explicit deployment/backfill operation; the schema does not use `POPULATE` because it can miss concurrent inserts.

## Options considered

| Option | Advantages | Disadvantages |
|---|---|---|
| Query Bronze directly | No duplicated storage or deployment object | Repeated Map probes and conversions; Watchers couple to the Collector schema |
| Typed physical models plus read views | Stable Watcher contract, simple ingestion, typed hot path | Duplicates selected telemetry; analytical views compute at read time |
| Pre-aggregated `AggregatingMergeTree` only | Fast baseline queries | Loses row-level evidence and complicates reprocessing/debugging |

## Trade-offs

Ordinary rollup views favor correctness and iteration speed for the MVP over maximum query performance. They can become materialized aggregate tables when measured Watcher latency or data volume requires it without changing the row-level Silver models.

`operation.request_count` and span counts represent operations, not committed business records. The Volume Watcher built on this version is therefore operational-volume detection only.

## Consequences

- Latency, error, operational-volume, and dependency Watchers can use stable, typed Silver inputs.
- Watcher queries no longer depend on Bronze attribute Map syntax or nanosecond conversion.
- Schema, business-volume, freshness, and storage Watchers still require new producer signals/contracts.
- Service dependency edges remain deferred because current live telemetry does not populate parent span ids.
- Deployments over existing Bronze data require a controlled backfill before parity checks pass.

## Risks

- Duplicate Bronze delivery is preserved as duplicate Silver evidence; end-to-end idempotency is not introduced here.
- Exact quantiles can become expensive at high cardinality; the MVP must measure this before choosing approximate/materialized states.
- A stale ClickHouse volume will not receive new init scripts automatically; apply the DDL explicitly or reset the local volume.

## Next steps

1. Implement the Latency Watcher against `service_health_1m`.
2. Implement an operational Volume Watcher against `metric_rollup_1m`.
3. Add explicit backfill tooling with a bounded time range and deduplication policy.
4. Extend the telemetry contract with business row counts, dataset identity, schema fingerprints, expected schedules, and watermarks.

## References

- [ADR-0007](0007-bronze-canonical-contract.md)
- [Pod 2 → Pod 3 read contract](../../contracts/collector/v1/pod2-pod3-read-contract.md)
- [Silver DDL](../../infra/clickhouse/init.d/02-silver-layer.sql)
