# Contracts — v1 (Single Source of Truth)

This directory is the **canonical** producer→consumer contract for the Sentinel pipeline.
The **producer** (the OTel data generator, POD 1) owns it; every **consumer** (the collectors)
validates against this one copy. There are no per-service duplicates.

## Contents

| Path | Purpose |
|------|---------|
| `schema/otlp_output.schema.json` | JSON Schema for the OTLP output signals the generator emits (the POD 1 → POD 2 handoff shape). |
| `golden/baseline_seed42.jsonl` | Canonical golden fixture (seed 42, baseline scenario). The single reference NDJSON used by collector golden/roundtrip tests. |

## How services reference it

Services read this directory via the `CONTRACTS_DIR` environment variable
(`/contracts/v1` inside containers; the root `docker-compose.yml` bind-mounts
`./contracts:/contracts:ro`). For local development the generator falls back to
the repo-root path, and the Rust collector tests resolve `../../contracts/v1/golden`
from the crate directory.

## Versioning

Contracts are versioned by directory. `v1` is the current contract. A **breaking**
change opens `contracts/v2/` while `v1` consumers stay pinned; an additive change
edits `v1` in place (keep the schema's top-level `version` and `CONTRACT_VERSION`
in the generator in sync).

> Note: the **ClickHouse storage schema** is deliberately *not* part of this contract —
> each collector keeps its own DDL for now. See [`../../docs/clickhouse-schema-divergence.md`](../../docs/clickhouse-schema-divergence.md).
