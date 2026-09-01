# CLAUDE.md — Sentinel monorepo

Context for working in this repository. Sentinel is an autonomous, OTel-native
observability and data-pipeline anomaly-detection platform. This branch is the
integrated monorepo baseline (`v0.0.1`) gluing the POD branches together.

## Pipeline

```
generator (otelgen) ──OTLP gRPC :4317──▶ collector-rust ──▶ ClickHouse :8123/:9000 ──▶ Play UI :8123/play
                       │                        │                    │
                       │                        └── /metrics :9090 ──┴──▶ flow-ui :8080
                       └── validates against contracts/generator/v1 (single source of truth)
```

## Layout

```
contracts/                 # SSOT contract registry, namespaced by producing Pod
  generator/v1/            #   POD 1 → POD 2 input contract (OTLP output schema + golden fixture)
  collector/v1/            #   POD 2 → POD 3 read contract (bronze semantic layer, bronze.*)
services/
  generator-python/        # POD 1 — synthetic OTLP generator (otelgen CLI); config/ holds scenarios/topology/provider_profiles
  collector-rust/          # POD 2 — OTLP→ClickHouse collector (Rust); own DDL in infra/clickhouse/ddl/
  flow-ui/                 # the pipeline watching itself — four boards over /metrics + bronze
infra/                     # ClickHouse bootstrap (init user/db + users.d network override)
docs/                      # shared docs (clickhouse-schema-divergence.md)
docker-compose.yml         # root orchestrator (rust|go profiles)
Makefile                   # one-command UX
```

## Common commands (all run in Docker — no host toolchains required)

| Command | What it does |
|---------|--------------|
| `make e2e COLLECTOR=rust\|go` | Full pipeline: build+up clickhouse+collector → apply its DDL → generate → land rows |
| `make ui` | Start flow-ui on http://localhost:8080 (see `services/flow-ui/README.md`) |
| `make generate-stream DURATION=10m` | Real-time telemetry paced by the wall clock, rather than a backfilled window |
| `make up / init / generate / logs / down / reset` | Individual pipeline steps |
| `make build` | Build all service images |
| `make test` | All unit suites (generator pytest, `cargo test`, `go test`) |
| `make lint` | ruff + `cargo fmt/clippy` + `go vet` |
| `make help` | List targets + active `COLLECTOR/SCENARIO/SEED/WINDOW` |

Variables: `COLLECTOR` (rust\|go, default rust), `SCENARIO`, `SEED`, `WINDOW`.

## Conventions

- **Each service keeps its native toolchain** (`pyproject`/`otelgen`, `cargo`/`just`, `go`/`make`). Don't impose a shared build system.
- **`contracts/` is the contract registry, namespaced by producing Pod.** `generator/v1/` is the POD 1 → POD 2 input contract — the producer (generator) owns it and consumers reference it via `CONTRACTS_DIR` (`/contracts/generator/v1` in containers). `collector/v1/` is the POD 2 → POD 3 read contract (the bronze semantic layer, database `bronze`) — one shared, implementation-agnostic contract every collector writes into. Bump versions per boundary by directory (`generator/v2/`, `collector/v2/`) for breaking changes.
- **Only one collector runs at a time** — both bind OTLP `:4317`. The generator targets the `collector` network alias, so it works regardless of which is active.
- **Both collectors now write the identical bronze split schema directly into database `bronze`** (POD 2 → POD 3 landing — `otel_logs / otel_traces / otel_metrics_gauge / otel_metrics_sum`, OTel-contrib style with metrics split by data-point type, Sentinel-enriched via `ResourceAttributes`). Cross-collector equivalence is verified (identical row counts). The old normalized `default.*` write path (and the `otel_metrics_1m` rollup MV) is retired.
- **POD 3's canonical bronze** (database `bronze`, `bronze.*`, OTel-contrib style, metrics split by type) is auto-applied on ClickHouse boot from `infra/clickhouse/init.d/01-bronze-otel.sql`. **Both collectors write directly into it** — the former collector→bronze gap is now closed (historical rationale: [docs/research/pod3-bronze-gap.md](docs/research/pod3-bronze-gap.md)).
- **flow-ui reads, never writes.** It polls the collector's `/metrics` and queries `bronze.*`
  read-only, plus Pod 1's `topology/default.yaml` and the collector's `config.docker.yaml`,
  both mounted read-only — the picture is drawn from the files that define the thing, so it
  cannot drift from them. Nothing in the pipeline depends on it being up.
- **No comments-as-noise**; match each service's existing style. Keep the repo clean for the agentic phase that follows this baseline.

## Gotchas

- **Stale ClickHouse volume:** `CREATE TABLE IF NOT EXISTS` won't update a changed schema. After a collector DDL change, `make reset` before `make init`, or inserts fail with `NO_SUCH_COLUMN`.
- **Dev-only ClickHouse auth:** `infra/clickhouse-init.sql` creates `otelgen`/`sentinel` (Go's DSN) and `infra/clickhouse-users.d/` opens the `default` user to the Docker network (Rust). Local only — do not expose beyond the compose network.
- The Rust collector only enters OTLP **server** mode when its config (`services/collector-rust/config.docker.yaml`) has a `grpc` section.

## Status & what's next

`v0.0.1` baseline is verified end-to-end (generator 176 unit tests; both collectors unit + live-ClickHouse integration; full `make e2e` for both). Not yet on `main`.

POD 2 (collector → bronze) and POD 3 (canonical bronze DDL) have landed: both collectors write the identical bronze split schema directly into database `bronze` (metrics split by type), and cross-collector equivalence is verified. The former collector→bronze gap is now **closed** (historical rationale: `docs/research/pod3-bronze-gap.md`).

Still deferred: contract *enforcement* in the Go collector, CI/CD + branch protection + pre-commit gates, and the agentic layer (agent fleet, KBs, routines). See [.claude/sdd/reports/BUILD_REPORT_MONOREPO_INTEGRATION.md](.claude/sdd/reports/BUILD_REPORT_MONOREPO_INTEGRATION.md).
