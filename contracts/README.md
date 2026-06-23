# Contracts

The versioned **contract boundaries** between Pods — the durable interfaces a downstream
Pod codes against. The registry is namespaced by the **producing Pod** so each boundary is
owned and versioned independently; contracts are language-agnostic and never duplicated
inside an implementation.

| Boundary | Direction | Artifact | Version |
|---|---|---|---|
| **`generator/`** | Pod 1 → Pod 2 (input) | [`generator/v1/`](generator/v1/) — `schema/otlp_output.schema.json` + `golden/baseline_seed42.jsonl` (the OTLP wire schema + conformance fixture; mounted into containers via `CONTRACTS_DIR=/contracts/generator/v1`) | `v1.0.0` |
| **`collector/`** | Pod 2 → Pod 3 (read) | [`collector/v1/pod2-pod3-read-contract.md`](collector/v1/pod2-pod3-read-contract.md) — the ClickHouse **bronze** read interface (the semantic layer over [`infra/clickhouse/init.d/01-bronze-otel.sql`](../infra/clickhouse/init.d/01-bronze-otel.sql)); machine-readable companion [`pod2-pod3-read-contract.yaml`](collector/v1/pod2-pod3-read-contract.yaml) | `v1.0.0.1` |

- **`generator/`** is the producer (generator) single source of truth for the Pod 1 → Pod 2
  OTLP handoff. Both collectors (Rust + Go) validate against it; neither keeps its own copy.
- **`collector/`** is the Pod 2 → Pod 3 bronze-schema boundary — one shared, implementation-
  agnostic contract that every collector implementation writes into. See
  [ADR-0007](../docs/adr/0007-bronze-canonical-contract.md).

Versioning is **per boundary, by directory** (`generator/v2/`, `collector/v2/`) for breaking
changes — each side bumps on its own cadence. Decisions of record live in
[`docs/adr/`](../docs/adr/).
