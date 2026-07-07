# Contract — generator/v1 (Pod 1 → Pod 2 input)

The **input** contract boundary of the Sentinel pipeline: the OTLP output shape the
generator (POD 1) emits and every collector (POD 2) validates against. The producer
(generator) owns it; consumers read this one copy — there are no per-service duplicates.
It is one boundary in the [`contracts/`](../../README.md) registry (the Pod 2 → Pod 3 read
contract lives under [`collector/`](../../collector/v1/pod2-pod3-read-contract.md)).

## Contents

| Path | Purpose |
|------|---------|
| `schema/otlp_output.schema.json` | JSON Schema for the OTLP output signals the generator emits (the POD 1 → POD 2 handoff shape). |
| `golden/baseline_seed42.jsonl` | Canonical golden fixture (seed 42, baseline scenario). The single reference NDJSON used by collector golden/roundtrip tests. |

## How services reference it

Services read this directory via the `CONTRACTS_DIR` environment variable
(`/contracts/generator/v1` inside containers; the root `docker-compose.yml` bind-mounts
`./contracts:/contracts:ro`). For local development the generator falls back to the
repo-root path, and the Rust collector tests resolve `../../contracts/generator/v1/golden`
from the crate directory.

## Versioning

Contracts are versioned per boundary, by directory. `generator/v1` is the current input
contract. A **breaking** change opens `contracts/generator/v2/` while `v1` consumers stay
pinned; an additive change edits `v1` in place (keep the schema's top-level `version` and
`CONTRACT_VERSION` in the generator in sync).

> The **ClickHouse storage schema** is a separate boundary — see the Pod 2 → Pod 3 read
> contract at [`../../collector/v1/pod2-pod3-read-contract.md`](../../collector/v1/pod2-pod3-read-contract.md).
