# CLAUDE.md — Sentinel monorepo

Context for working in this repository. Sentinel is an autonomous, OTel-native
observability and data-pipeline anomaly-detection platform. This branch is the
integrated monorepo baseline (`v0.0.1`) gluing the POD branches together.

## Pipeline

```
generator (otelgen) ──OTLP gRPC :4317──▶ collector (rust | go) ──▶ ClickHouse :8123/:9000 ──▶ Play UI :8123/play
                       │                  (selected via COLLECTOR)
                       └── validates against contracts/v1 (single source of truth)
```

## Layout

```
contracts/v1/              # SSOT: OTLP output schema + golden fixture (producer = generator)
services/
  generator-python/        # POD 1 — synthetic OTLP generator (otelgen CLI); config/ holds scenarios/topology/provider_profiles
  collector-rust/          # POD 2 — OTLP→ClickHouse collector (Rust); own DDL in infra/clickhouse/ddl/
  collector-go/            # POD 2 — OTLP→ClickHouse collector (Go);   own DDL in migrations/
infra/                     # ClickHouse bootstrap (init user/db + users.d network override)
docs/                      # shared docs (clickhouse-schema-divergence.md)
docker-compose.yml         # root orchestrator (rust|go profiles)
Makefile                   # one-command UX
```

## Common commands (all run in Docker — no host toolchains required)

| Command | What it does |
|---------|--------------|
| `make e2e COLLECTOR=rust\|go` | Full pipeline: build+up clickhouse+collector → apply its DDL → generate → land rows |
| `make up / init / generate / logs / down / reset` | Individual pipeline steps |
| `make build` | Build all service images |
| `make test` | All unit suites (generator pytest, `cargo test`, `go test`) |
| `make lint` | ruff + `cargo fmt/clippy` + `go vet` |
| `make help` | List targets + active `COLLECTOR/SCENARIO/SEED/WINDOW` |

Variables: `COLLECTOR` (rust\|go, default rust), `SCENARIO`, `SEED`, `WINDOW`.

## Conventions

- **Each service keeps its native toolchain** (`pyproject`/`otelgen`, `cargo`/`just`, `go`/`make`). Don't impose a shared build system.
- **`contracts/v1/` is the single source of truth** for the generator→collector handoff. The producer (generator) owns it; consumers reference it via `CONTRACTS_DIR` (`/contracts/v1` in containers). Bump versions by directory (`contracts/v2/`) for breaking changes.
- **Only one collector runs at a time** — both bind OTLP `:4317`. The generator targets the `collector` network alias, so it works regardless of which is active.
- **ClickHouse storage schema is per-collector and intentionally NOT reconciled** — `default.*` (Rust) vs `sentinel.*` (Go). A canonical model is POD 3's job; see [docs/clickhouse-schema-divergence.md](docs/clickhouse-schema-divergence.md). Until then, schema init is collector-scoped (`make init`).
- **No comments-as-noise**; match each service's existing style. Keep the repo clean for the agentic phase that follows this baseline.

## Gotchas

- **Stale ClickHouse volume:** `CREATE TABLE IF NOT EXISTS` won't update a changed schema. After a collector DDL change, `make reset` before `make init`, or inserts fail with `NO_SUCH_COLUMN`.
- **Dev-only ClickHouse auth:** `infra/clickhouse-init.sql` creates `otelgen`/`sentinel` (Go's DSN) and `infra/clickhouse-users.d/` opens the `default` user to the Docker network (Rust). Local only — do not expose beyond the compose network.
- The Rust collector only enters OTLP **server** mode when its config (`services/collector-rust/config.docker.yaml`) has a `grpc` section.

## Status & what's next

`v0.0.1` baseline is verified end-to-end (generator 176 unit tests; both collectors unit + live-ClickHouse integration; full `make e2e` for both). Not yet on `main`.

Deferred to the post-baseline phase (not yet present): POD 3 data-modeling service + canonical schema, contract *enforcement* in the Go collector, CI/CD + branch protection + pre-commit gates, and the agentic layer (agent fleet, KBs, routines). See [.claude/sdd/reports/BUILD_REPORT_MONOREPO_INTEGRATION.md](.claude/sdd/reports/BUILD_REPORT_MONOREPO_INTEGRATION.md).
