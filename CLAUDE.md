# CLAUDE.md — Sentinel monorepo

Context for working in this repository. Sentinel is an autonomous, OTel-native
observability and data-pipeline anomaly-detection platform. `main` is the
integrated monorepo: every Pod's component behind versioned contracts.

## Pipeline

```
generator (otelgen) ──OTLP gRPC :4317──▶ collector-rust ──HTTP :8123──▶ ClickHouse bronze.* ──▶ Play UI :8123/play
                       │                        │          (Pod-3-owned DDL, auto-applied on boot)
                       │                        └── /metrics :9090 ──▶ flow-ui :8080
                       └── validates against contracts/generator/v1 (single source of truth)
```

## Layout

```
contracts/                 # SSOT contract registry, namespaced by producing Pod
  generator/v1/            #   POD 1 → POD 2 input contract (OTLP output schema + golden fixture)
  collector/v1/            #   POD 2 → POD 3 read contract (bronze semantic layer, bronze.*)
services/
  generator-python/        # POD 1 — synthetic OTLP generator (otelgen CLI); config/ holds scenarios/topology/provider_profiles
  collector-rust/          # POD 2 — OTLP→ClickHouse collector (Rust), the selected implementation
  flow-ui/                 # the pipeline watching itself — four boards over /metrics + bronze/silver
                           #   ARCHITECTURE.md = stack + cadences + module map (Mermaid)
infra/                     # ClickHouse bootstrap (users/db init + users.d network override + bronze DDL in init.d/)
docs/                      # shared docs (ADRs, research, proposals)
                           #   research/ holds the V2 product roadmap for flow-ui:
                           #   data-observability-competitive-landscape.md §6
docker-compose.yml         # root orchestrator
Makefile                   # one-command UX
```

## Common commands (all run in Docker — no host toolchains required)

| Command | What it does |
|---------|--------------|
| `make e2e` | Full local pipeline: ClickHouse → migrations → collector readiness → generate rows in `bronze.*` |
| `make ui` / `make down-ui` | Start or stop flow-ui independently on http://127.0.0.1:8080 |
| `make generate-stream DURATION=10m` | Real-time telemetry paced by the wall clock, rather than a backfilled window |
| `make up / init / migrate / generate / logs / ps / down / reset` | Local pipeline steps; `make up` migrates before starting the collector |
| `make build` | Build all service images |
| `make test` | All unit suites (`test-generator` + `test-flow-ui` pytest, `test-collector-rust` cargo) |
| `make lint` | `lint-generator` + `lint-flow-ui` (ruff) + `lint-collector-rust` (cargo fmt --check + clippy) |
| `make help` | List targets + active `SCENARIO/SEED/WINDOW` |

Variables: `SCENARIO` (default `baseline`), `SEED` (`42`), `WINDOW` (`5m`).

## Conventions

- **Each service keeps its native toolchain** (`pyproject`/`otelgen`, `cargo`). Don't impose a shared build system.
- **`contracts/` is the contract registry, namespaced by producing Pod.** `generator/v1/` is the POD 1 → POD 2 input contract — the producer (generator) owns it and consumers reference it via `CONTRACTS_DIR` (`/contracts/generator/v1` in containers). `collector/v1/` is the POD 2 → POD 3 read contract (the bronze semantic layer, database `bronze`) — implementation-agnostic, so it survives a collector swap. Bump versions per boundary by directory (`generator/v2/`, `collector/v2/`) for breaking changes.
- **Rust is the selected collector implementation.** The Go collector was removed from the repo in PR #28 (merged 2026-08-12); `services/collector-rust/` is the only ingestion path. ADR-0004 still carries `Proposed` and has not been updated to record the selection — see *Known doc drift* below.
- **The collector writes the bronze split schema directly into database `bronze`** (`otel_logs / otel_traces / otel_metrics_gauge / otel_metrics_sum`, otel-collector-contrib v0.105.0 style with metrics split by data-point type, Sentinel-enriched via `ResourceAttributes`). The old normalized `default.*` write path and the `otel_metrics_1m` rollup MV are retired; the rollup is now a Pod 3 silver artifact.
- **The bronze DDL is Pod-3-owned** and auto-applies on ClickHouse boot from `infra/clickhouse/init.d/01-bronze-otel.sql`. The collector issues no DDL — it only `INSERT`s. (The repo calls this policy `create_schema:false`, borrowing the contrib exporter's flag name; it is not a literal key in our Rust config.) The former collector→bronze gap is now closed (historical rationale: [docs/research/pod3-bronze-gap.md](docs/research/pod3-bronze-gap.md)).
- **flow-ui reads, never writes.** It polls the collector's `/metrics` and queries `bronze.*`
  and `silver.*` read-only, plus Pod 1's `topology/default.yaml` and the collector's
  `config.docker.yaml`, both mounted read-only — the picture is drawn from the files that define the thing, so it
  cannot drift from them. Nothing in the pipeline depends on it being up.
- **Agent-assisted work follows [ADR-0009](docs/adr/0009-agentic-gitflow.md)** — *seam → swimlane → leg → task*. One `git worktree` per agent under `.worktrees/`, branches named `leg/<area>/<task>-v<n>`, and **every leg declares disjoint paths** before it opens. The ADR is the record; the `.claude/` companion that carried the commands was removed in `7689c16`. Export a shared `CARGO_TARGET_DIR` before running a fleet, or N worktrees means N cold Rust builds.
- **No comments-as-noise**; match each service's existing style. Keep the repo clean for the agentic phase that follows this baseline.

## Gotchas

- **Stale ClickHouse volume:** `CREATE TABLE IF NOT EXISTS` won't update a changed schema. After a DDL change, `make reset` before `make up`, or inserts fail with `NO_SUCH_COLUMN`.
- **Local boundary:** host ports bind to loopback; services use the private Compose network. This is for local development and does not provide remote edge authentication or TLS.
- The Rust collector only enters OTLP **server** mode when its config (`services/collector-rust/config.docker.yaml`) has a `grpc` section. Without it, it runs FILE mode (read `input` once, exit).
- **ClickHouse port:** the collector's `clickhouse` crate speaks RowBinary over **HTTP :8123**, not native :9000.

## Status & what's next

Pod 2's Rust collector is verified end-to-end on `main`: generator → OTLP `:4317` → `bronze.*`, lossless. Latest local snapshot (2026-08-04): 233,100 signals in 4.5s, 0 rejected / 0 dropped / 0 export errors, avg export latency 32.3ms. Golden file-mode round-trip: 48 logs / 48 spans / 183 metrics. Full detail in [README §8](README.md).

**The `sdlc-e2e-review` cycle is landed** — see [README §8](README.md) for the per-ticket registry
and [`plan/core-plan.md`](plan/core-plan.md) for the tickets themselves. In short: one pinned
ClickHouse (25.4) behind a single Compose definition, DDL in `migrations/` with `init.d/` as
symlinks into it, least-privilege roles with the credential delivered as a file path, both `::/0`
routes closed, the four Pod 3 Watcher read models, the backfill runner, five CI workflows and nine
repository invariants.

**Scope ruled on 2026-10-06** ([`plan/decisions/DEC-2026-10-06-local-scope.md`](plan/decisions/DEC-2026-10-06-local-scope.md)):
everything runs **locally, Docker + Make only**. That is a deliberate boundary, not an omission —
no remote platform or ClickHouse provider is selected (DEC-A1/A2), **TLS is deferred** (DEC-A4, so
T42 is not attempted), and documentation now lands in the same PR as the behaviour it describes
(DEC-I2, so the T45–T48 docs wave is dissolved). Anything marked *Done (local)* means done within
that scope and unverified against a deployed target.

**Open:** ADR-0007 acceptance (Pod 3 sign-off) · histogram/summary metrics (no v1.0.0 type) ·
branch protection, which is a GitHub setting and not a file — [`docs/ci-gates.md`](docs/ci-gates.md)
is the required-check set to configure from, and `main` carries no rule today (issue #35) · the
agentic layer (agent fleet, KBs, routines) · **GitHub Actions has been failing account-wide since
2026-10-05** — jobs end in 1–3 s with no runner assigned, across every workflow here and other
repositories on the account, so none of the CI above has actually executed.

**Known doc drift** — decisions taken by merge that the records don't yet reflect:

| Drift | Where | Resolution owner |
|---|---|---|
| ADR-0007 / ADR-0008 still `Proposed` | `docs/adr/` | cross-Pod ratification at sync |
| Pod↔layer mapping unratified (README POD3 = storage/read-layer vs the removed `.claude/CLAUDE.md`'s B3 = watchers). The second source is gone as of `7689c16`, so README is now the only statement — ratify it rather than reconcile two | `README.md` | Captain / Commander |
| ADR-0009 amends the WoW's "squash-merge to main" rule | `docs/adr/0009-agentic-gitflow.md` | Captain / Commander |

Historical records under `docs/research/`, `docs/proposals/`, `docs/clickhouse-schema-divergence*.md`, `intent/` and `spec/` are point-in-time artifacts — they mention the Go collector by design. Don't "fix" them; they carry a superseded banner. **`plan/` is not in that set:** `plan/core-plan.md` is the live ticket registry and `plan/decisions/` are live briefs that gain evidence until their decision is taken. Amend those; don't freeze them.

## Agent skills

Per-repo configuration for the engineering skills, written by `/setup-matt-pocock-skills`.

### Issue tracker

Issues live in GitHub Issues on `luanmorenommaciel/sentinel`, driven by the `gh` CLI — propose, never create unprompted. See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

### Triage labels

The five canonical triage roles **projected onto this repo's real `type:*`/`phase:*`/`priority:*` scheme** — four of the five canonical label strings do not exist here (verified 2026-10-05). See [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md).

### Domain docs

Single-context: one root `CONTEXT.md` (not yet written) plus the shared `docs/adr/`; ADRs are history, so conflicts get flagged, not rewritten. See [`docs/agents/domain.md`](docs/agents/domain.md).
