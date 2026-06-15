# Sentinel

Self-Healing Data Pipelines. Autonomous detection, AI-native reasoning, OTel-native by design.

This is the **integrated monorepo** that glues the POD branches together — the `0.0.x` baseline
the whole crew builds on. The pipeline is:

```
generator (otelgen) ──OTLP gRPC :4317──▶ collector (rust | go) ──▶ ClickHouse :8123/:9000 ──▶ Play UI :8123/play
                       │                  (selected via COLLECTOR)
                       └── validates against contracts/v1 (single source of truth)
```

## Layout

```
sentinel/
├── contracts/v1/              # SSOT: OTLP output schema + golden fixture (producer = generator)
├── services/
│   ├── generator-python/      # POD 1 — synthetic OTLP generator (otelgen CLI)
│   │   └── config/            #   generator INPUT config (scenarios, topology, provider_profiles)
│   ├── collector-rust/        # POD 2 — OTLP→ClickHouse collector (Rust); keeps its own DDL
│   └── collector-go/          # POD 2 — OTLP→ClickHouse collector (Go);   keeps its own DDL
├── docs/                      # shared docs (incl. clickhouse-schema-divergence.md)
├── docker-compose.yml         # root orchestrator (rust|go profiles)
└── Makefile                   # one-command UX (COLLECTOR switch)
```

Each service keeps its **native toolchain** (`pyproject`/`otelgen`, `cargo`/`just`, `go`/`make`)
for isolated development. The root `Makefile` only coordinates the end-to-end pipeline.

## Quick start — configurable end-to-end

Requires Docker. Choose which collector to run with `COLLECTOR` (default `rust`):

```bash
make e2e                  # ClickHouse + Rust collector + generator, end-to-end
make e2e COLLECTOR=go     # same, with the Go collector
```

Or step by step:

```bash
make up   COLLECTOR=go         # start ClickHouse + the Go collector
make init COLLECTOR=go         # apply the Go collector's own ClickHouse DDL
make generate SCENARIO=black_friday SEED=42   # generate → OTLP :4317
make logs COLLECTOR=go         # tail collector logs
# inspect ingested telemetry at http://localhost:8123/play
make reset                     # stop everything + drop ClickHouse volume
```

Run `make help` for all targets and the active `COLLECTOR / SCENARIO / SEED`.

> Only one collector runs at a time — both bind OTLP `:4317`. The generator targets the
> network alias `collector`, so it works regardless of which collector is active.

## Contracts & schema

- `contracts/v1/` is the **single source of truth** for the generator→collector handoff.
  See [`contracts/v1/README.md`](contracts/v1/README.md).
- The **ClickHouse storage schema is per-collector and intentionally not reconciled** yet.
  See [`docs/clickhouse-schema-divergence.md`](docs/clickhouse-schema-divergence.md) — POD 3 owns the canonical model.

## Status

Baseline integration of three POD branches (`001-otel-data-generator`, `feat/rust-otel-collector`,
`feat/02-otel-collector-go`). Governance (CI, branch protection, pre-commit) and the agentic layer
come after this baseline is tagged.
