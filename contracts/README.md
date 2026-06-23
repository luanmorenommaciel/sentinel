# Contracts

The versioned **contract boundaries** between Pods — the durable interfaces a downstream Pod
codes against. Each is owned jointly by the Pods on both sides of the boundary and changes
only with both signatures.

| Contract | Direction | Artifact | Version |
|---|---|---|---|
| **Input** | Pod 1 → Pod 2 | [`v1/`](v1/) — `schema/otlp_output.schema.json` + `golden/baseline_seed42.jsonl` (the OTLP wire schema + conformance fixture; mounted into containers via `CONTRACTS_DIR=/contracts/v1`) | `v1.0.0` |
| **Read** | Pod 2 → Pod 3 | [`pod2-pod3-read-contract.md`](pod2-pod3-read-contract.md) — the ClickHouse **bronze** read interface (the semantic layer over [`infra/clickhouse/init.d/01-bronze-otel.sql`](../infra/clickhouse/init.d/01-bronze-otel.sql)) | `v1.0.0.1` |

The **input** contract is the producer (generator) single source of truth, versioned by
directory (`v1/`, `v2/`, …). The **read** contract is the Pod 2 → Pod 3 bronze schema
boundary — see [ADR-0007](../docs/adr/0007-bronze-canonical-contract.md). Decisions of
record live in [`docs/adr/`](../docs/adr/).
