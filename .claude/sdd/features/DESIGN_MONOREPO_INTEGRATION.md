# DESIGN: Monorepo Integration ("Glue" Branch)

> Technical design for unifying the three POD branches into one generic, contract-driven monorepo with a **configurable** end-to-end pipeline (choose which collector to run).

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | MONOREPO_INTEGRATION |
| **Date** | 2026-06-15 |
| **Author** | design-agent |
| **DEFINE** | [DEFINE_MONOREPO_INTEGRATION.md](./DEFINE_MONOREPO_INTEGRATION.md) (v1.1) |
| **Status** | Ready for Build |

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                    SENTINEL MONOREPO (feat/monorepo-integration)           │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  contracts/v1/        ← SINGLE SOURCE OF TRUTH (OTLP output schema+golden) │
│      ▲  ▲  ▲             validated at the producer→consumer boundary       │
│      │  │  └───────────────────────────────────┐                          │
│      │  └──────────────────────┐                │                          │
│  ┌───┴─────────┐   COLLECTOR=rust|go   ┌────────┴────────┐                 │
│  │ generator-  │  OTLP gRPC :4317  ┌──▶│ collector-rust  │──┐              │
│  │  python     │──────────────────▶│   └─────────────────┘  │ :8123 HTTP   │
│  │ (otelgen)   │   (only ONE       │   ┌─────────────────┐  ├────▶ ClickHouse
│  └─────────────┘    collector up)  └──▶│ collector-go    │──┘   (Play UI    │
│         │                              └─────────────────┘       :8123/play)│
│         │ scenarios/seed (config)        each keeps its OWN DDL              │
│         ▼                                (NOT reconciled — POD 3 later)      │
│   services/generator-python/config/                                         │
│                                                                            │
│  infra/ (root orchestrator) ── docker-compose.yml + Makefile ──────────────│
│      `make up COLLECTOR=rust|go`  → clickhouse + selected collector         │
│      `make init`                  → applies SELECTED collector's DDL        │
│      `make generate`              → otelgen → :4317 → ClickHouse            │
└──────────────────────────────────────────────────────────────────────────┘
```

**The new requirement** — *make the end-to-end configurable* — is realized by a single `COLLECTOR` switch (default `rust`) that selects which collector Docker Compose profile comes up and which per-service DDL is applied. This is also the answer to DEFINE Open Question 4.

---

## Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| `services/generator-python/` | Synthetic OTLP signal generator; emits to OTLP gRPC :4317 | Python, `otelgen` CLI (Typer) |
| `services/collector-rust/` | OTLP receiver → ClickHouse writer (selectable) | Rust, `cargo`/`just` |
| `services/collector-go/` | OTLP receiver → ClickHouse writer (selectable) | Go, `Makefile`/`go` |
| `contracts/v1/` | Canonical OTLP output schema + golden fixture (SSOT) | JSON Schema + JSONL |
| `infra/` (root) | Configurable orchestrator selecting collector + schema | Docker Compose profiles + Makefile |
| ClickHouse | RAW telemetry store; inspection via Play UI | `clickhouse-server:24.3`, :8123/:9000 |

---

## Key Decisions

### Decision 1: Configurable collector via Docker Compose profiles + `COLLECTOR` variable

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-06-15 |

**Context:** Both collectors are kept (DEFINE constraint) and both listen on OTLP gRPC :4317, so only one can run at a time. The end-to-end must let a developer choose which collector to exercise.

**Choice:** Define `collector-rust` (profile `rust`) and `collector-go` (profile `go`) in one root `docker-compose.yml`. A `COLLECTOR` Make variable (default `rust`) maps to `COMPOSE_PROFILES`. `make up COLLECTOR=go` brings up ClickHouse + the Go collector; `make up COLLECTOR=rust` brings up the Rust one. The generator and ClickHouse are profile-agnostic (members of both).

**Rationale:** Profiles are the native Compose mechanism for "one of N" services in a single file — no duplicated compose files, single source of orchestration truth, trivial to extend (`profiles: [<pod3>]`).

**Alternatives Rejected:**
1. Separate compose file per collector (`docker-compose.rust.yml`, `…go.yml`) — rejected: duplicates the shared ClickHouse/generator wiring; drifts over time.
2. One `collector` service with an env-swapped image — rejected: the two collectors build from different Dockerfiles/contexts; can't swap a build via env.

**Consequences:**
- (+) One file, one switch; new collectors/services are additive profiles.
- (−) :4317 is owned by whichever collector is up — running both at once is intentionally unsupported (documented).

---

### Decision 2: Schema initialization is collector-scoped (consequence of per-service schemas)

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-06-15 |

**Context:** Per DEFINE v1.1, the two ClickHouse schemas are **not** reconciled — each collector keeps its own DDL (`services/collector-rust/infra/clickhouse/ddl/*.sql` vs `services/collector-go/migrations/*.sql`). They differ in db name, table names (`otel_traces` vs `otel_spans`), naming convention, and partitioning. So the ClickHouse schema that must exist depends on which collector runs.

**Choice:** A `make init` target applies the **selected** collector's own DDL (driven by the same `COLLECTOR` var) via `clickhouse-client`, after ClickHouse is healthy and before `make generate`. No merged `infra/clickhouse/` schema is produced.

**Rationale:** Keeps the per-service-schema decision intact while still giving a one-command bring-up. Make-driven init avoids templating divergent DDL paths into Compose `initdb` mounts.

**Alternatives Rejected:**
1. Mount a single `infra/clickhouse/init/` into ClickHouse `docker-entrypoint-initdb.d` — rejected: implies a canonical schema, which is explicitly out of scope.
2. Compose `volumes:` templated by `${COLLECTOR}` — rejected: the two DDL dirs have different structures/paths (`ddl/` vs `migrations/`), brittle to template.

**Consequences:**
- (+) Honors "schemas stay per-service"; POD 3 later swaps in a canonical `make init` with zero orchestrator restructuring.
- (−) Switching `COLLECTOR` against a populated ClickHouse may leave the other collector's tables behind — `make reset` documented to drop volumes.

---

### Decision 3: Root `Makefile` is the single UX, delegating to per-service toolchains

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-06-15 |

**Context:** Three native toolchains exist (`otelgen`/pyproject, `just`/cargo, `Makefile`/go). The orchestrator must not replace them — only coordinate the end-to-end.

**Choice:** A thin root `Makefile` with `up / init / generate / e2e / down / reset / logs` that wraps Docker Compose and shells out to each service's own toolchain. Per-service `just`/`make`/`cargo`/`go` remain for isolated dev.

**Rationale:** One discoverable entry point for the whole pipeline; services stay self-contained (DEFINE constraint).

**Alternatives Rejected:**
1. Impose one build system (e.g. `just`) across all services — rejected: churns each POD's working tooling; out of scope.

**Consequences:** (+) `make e2e COLLECTOR=go` runs the full pipeline. (−) Two layers of build entry (root + per-service), documented in README.

---

### Decision 4: Services reach `contracts/v1/` via repo-root build context + bind mount

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-06-15 |

**Context:** `contracts/v1/` lives outside each service dir (SSOT), but each service's Docker build and tests must read it (DEFINE assumption A-004).

**Choice:** Service Docker builds use **repo root** as build context with `-f services/<svc>/Dockerfile`; for runtime/tests, root compose bind-mounts `./contracts:/contracts:ro`. Source code references the contract via a `CONTRACTS_DIR` env (default `/contracts` in container, `../../contracts` for local dev).

**Rationale:** Keeps one physical contract copy (kills the divergence) while every service can still build and validate against it.

**Alternatives Rejected:**
1. Per-service synced copies — rejected: reintroduces the exact drift problem (DEFINE rejected this).

**Consequences:** (+) True SSOT. (−) Dockerfiles need context/path edits during import (tracked in manifest).

---

### Decision 5: History-preserving import via `git read-tree --prefix`

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-06-15 |

**Context:** DEFINE Open Question 3 — preserve each POD's authorship on import.

**Choice:** Assemble each `services/<component>/` with `git read-tree --prefix=services/<x>/ <branch>` (merging histories), or `git merge -s ours` + subtree where cleaner. Plain copy is the documented fallback if history merge gets noisy.

**Rationale:** Retains blame/authorship for each POD's work in the unified history.

**Alternatives Rejected:** Plain `cp` (loses history) — kept only as fallback.

**Consequences:** (+) Traceable history. (−) More careful import scripting; contract/infra path moves happen as follow-up commits.

---

## File Manifest

> Most entries are **structural** (branch, import, move). New authored files are the orchestrator + docs. `<svc-rust> = services/collector-rust`, etc.

| # | File / Path | Action | Purpose | Agent | Dependencies |
|---|-------------|--------|---------|-------|--------------|
| 1 | `feat/monorepo-integration` (branch) | Create | Glue branch off `main` | @shell-script-specialist | None |
| 2 | `services/generator-python/**` | Import | From `001-otel-data-generator` (`src/otelgen`, `pyproject.toml`, `Dockerfile`, tests) | @shell-script-specialist | 1 |
| 3 | `services/collector-rust/**` | Import | From `feat/rust-otel-collector` (`services/collector-rust`, `infra/`, `justfile`) | @shell-script-specialist | 1 |
| 4 | `services/collector-go/**` | Import | From `feat/02-otel-collector-go` (`cmd/`, `internal/`, `migrations/`, `Makefile`) | @shell-script-specialist | 1 |
| 5 | `contracts/v1/schema/otlp_output.schema.json` | Create (move) | Canonical OTLP output schema (from generator) | @data-contracts-engineer | 2 |
| 6 | `contracts/v1/golden/baseline_seed42.jsonl` | Create (move) | Canonical golden fixture (from generator) | @data-contracts-engineer | 2 |
| 7 | `contracts/v1/README.md` | Create | Contract version policy + producer/consumer note | @code-documenter | 5,6 |
| 8 | `services/*/contract/` duplicate schema+golden | Delete | Remove diverged copies (0 duplicates remain) | @shell-script-specialist | 5,6 |
| 9 | `services/generator-python/config/{scenarios,topology,provider_profiles}/` | Move | Relocate generator-only input config out of shared contract space | @python-developer | 2 |
| 10 | `services/generator-python/Dockerfile` | Modify | Root build context; `CONTRACTS_DIR=/contracts`; config path update | @python-developer | 2,9 |
| 11 | `services/collector-rust/**/Dockerfile` + `config.example.yaml` | Modify | Root context; point at `/contracts/v1`; keep own DDL | @shell-script-specialist | 3 |
| 12 | `services/collector-go/Dockerfile` + config | Modify | Root context; point at `/contracts/v1`; keep own `migrations/` | @shell-script-specialist | 4 |
| 13 | `docker-compose.yml` (root) | Create | Profiles `rust`/`go`; clickhouse + generator + both collectors; bind-mount contracts | @shell-script-specialist | 10,11,12 |
| 14 | `Makefile` (root) | Create | `up/init/generate/e2e/down/reset/logs`; `COLLECTOR`/`SCENARIO`/`SEED` vars | @shell-script-specialist | 13 |
| 15 | `.gitignore` (root) | Create (merge) | Union of the three branches' ignores | @shell-script-specialist | 2,3,4 |
| 16 | `README.md` (root) | Create | Monorepo map, `make` UX, `COLLECTOR` switch, per-service pointers | @code-documenter | 13,14 |
| 17 | `docs/clickhouse-schema-divergence.md` | Create | Record the Rust↔Go schema divergence table for POD 3 | @code-documenter | 3,4 |
| 18 | `services/collector-{rust,go}/**` golden tests | Modify | Re-point golden tests at `contracts/v1/golden/` (COULD) | @shell-script-specialist | 6 |

**Total Files/Steps:** 18

---

## Agent Assignment Rationale

| Agent | Steps Assigned | Why This Agent |
|-------|----------------|----------------|
| @shell-script-specialist | 1,2,3,4,8,11,12,13,14,15,18 | Git import scripting, Docker Compose/Makefile orchestration, build-context edits |
| @python-developer | 9,10 | Generator config relocation + Python Dockerfile/path changes |
| @data-contracts-engineer | 5,6 | Canonical contract/golden placement + versioned registry semantics |
| @code-documenter | 7,16,17 | Contract README, root README, schema-divergence record |

**Agent Discovery:** matched by path patterns (Makefile/compose → shell; `src/otelgen` → python), purpose keywords (contract → data-contracts-engineer; README/docs → documenter), and KB domains (OTel, ClickHouse, data contracts).

---

## Code Patterns

### Pattern 1: Root `docker-compose.yml` with collector profiles

```yaml
# Only ONE collector profile is active per run (both bind :4317).
services:
  clickhouse:
    image: clickhouse/clickhouse-server:24.3
    ports: ["8123:8123", "9000:9000"]
    volumes: ["clickhouse_data:/var/lib/clickhouse"]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8123/?query=SELECT+1"]
      interval: 5s
      retries: 10
    profiles: ["rust", "go"]          # always up (member of both)

  collector-rust:
    build: { context: ., dockerfile: services/collector-rust/services/collector-rust/Dockerfile }
    environment: { CONTRACTS_DIR: /contracts/v1, CH_URL: "http://clickhouse:8123" }
    volumes: ["./contracts:/contracts:ro"]
    ports: ["4317:4317"]
    depends_on: { clickhouse: { condition: service_healthy } }
    profiles: ["rust"]

  collector-go:
    build: { context: ., dockerfile: services/collector-go/Dockerfile }
    environment: { CONTRACTS_DIR: /contracts/v1, GRPC_PORT: "4317", CH_HOST: clickhouse }
    volumes: ["./contracts:/contracts:ro"]
    ports: ["4317:4317"]
    depends_on: { clickhouse: { condition: service_healthy } }
    profiles: ["go"]

  generator:                          # collector-agnostic; emits to :4317
    build: { context: ., dockerfile: services/generator-python/Dockerfile }
    environment:
      CONTRACTS_DIR: /contracts/v1
      OTLP_ENDPOINT: "${OTLP_ENDPOINT:-collector:4317}"
      SCENARIO: "${SCENARIO:-baseline}"
      SEED: "${SEED:-42}"
    volumes: ["./contracts:/contracts:ro"]
    profiles: ["rust", "go"]
volumes: { clickhouse_data: {} }
```

### Pattern 2: Root `Makefile` — the `COLLECTOR` switch

```makefile
COLLECTOR ?= rust            # rust | go
SCENARIO  ?= baseline
SEED      ?= 42
export COMPOSE_PROFILES = $(COLLECTOR)

up:                          ## clickhouse + selected collector
	docker compose up -d clickhouse collector-$(COLLECTOR)

init:                        ## apply the SELECTED collector's own DDL
ifeq ($(COLLECTOR),rust)
	cat services/collector-rust/infra/clickhouse/ddl/*.sql | docker compose exec -T clickhouse clickhouse-client -mn
else
	cat services/collector-go/migrations/*.sql           | docker compose exec -T clickhouse clickhouse-client -mn
endif

generate:                    ## run generator → :4317
	docker compose run --rm generator otelgen run --scenario $(SCENARIO) --seed $(SEED)

e2e: up init generate        ## full configurable pipeline
down:
	docker compose --profile rust --profile go down
reset:
	docker compose --profile rust --profile go down -v
```

### Pattern 3: `contracts/v1/` layout (SSOT)

```text
contracts/
└── v1/
    ├── schema/otlp_output.schema.json     # canonical OTLP output contract
    ├── golden/baseline_seed42.jsonl       # canonical golden fixture
    └── README.md                          # producer=generator; consumers validate; version policy
```

---

## Data Flow

```text
1. `make up COLLECTOR=<rust|go>` → ClickHouse healthy + selected collector on :4317
   │
   ▼
2. `make init` → applies the SELECTED collector's own DDL into ClickHouse
   │
   ▼
3. `make generate` → otelgen builds signals (SCENARIO/SEED), validates against contracts/v1, emits OTLP gRPC :4317
   │
   ▼
4. Selected collector receives OTLP, transforms, writes to ClickHouse (its own schema)
   │
   ▼
5. Inspect at http://localhost:8123/play  (rows present in that collector's tables)
```

---

## Integration Points

| External System | Integration Type | Authentication |
|-----------------|-----------------|----------------|
| ClickHouse (`clickhouse-server:24.3`) | HTTP :8123 / native :9000 | default user (local dev) |
| OTLP gRPC receiver (:4317) | gRPC | none (local) |
| ClickStack / HyperDX all-in-one (optional UI) | Docker image, optional profile | none (local) |

---

## Testing Strategy

| Test Type | Scope | Files | Tools | Coverage Goal |
|-----------|-------|-------|-------|---------------|
| Unit (per service, unchanged) | Each component's existing tests | `services/*/.../tests` | pytest / `cargo test` / `go test` | Keep green post-import |
| Contract | Golden validates against `contracts/v1` schema | `contracts/v1/golden` + each collector's golden test | jsonschema / `cargo test golden_parse` / `go test` | 0 rejections |
| Integration | Collector ↔ ClickHouse roundtrip (each) | `collector-rust/tests/clickhouse_roundtrip.rs`, `collector-go/internal/chstore/*_integration_test.go` | per-toolchain | Key paths |
| E2E (configurable) | `make e2e COLLECTOR=rust` and `COLLECTOR=go` both land rows | root `Makefile` | docker compose | Happy path, both collectors |

**Acceptance mapping:** AT-002/003/004 → per-service builds; AT-005 → single golden (step 8); AT-006 → per-service `make init`; AT-007 → `make e2e`; AT-008 → add a placeholder profile; AT-009 → contract test.

---

## Error Handling

| Error Type | Handling Strategy | Retry? |
|------------|-------------------|--------|
| Invalid `COLLECTOR` value | Makefile guards against `rust|go`; clear error listing valid values | No |
| Collector build can't find `contracts/` | Root build context + bind mount (Decision 4); fail fast with path hint | No |
| Port :4317 already bound (both collectors) | Only one profile up; `make reset` / document single-collector rule | No |
| `make generate` before `make init` | `e2e` orders init→generate; standalone generate errors if tables missing | No |
| Switching collector over populated CH | `make reset` drops volumes; documented | Manual |

---

## Configuration

| Config Key | Type | Default | Description |
|------------|------|---------|-------------|
| `COLLECTOR` | string | `rust` | Which collector profile + DDL to run (`rust` \| `go`) |
| `SCENARIO` | string | `baseline` | Generator scenario (`baseline`, `black_friday`, `failure_spike`, …) |
| `SEED` | int | `42` | Generator RNG seed (golden reproducibility) |
| `OTLP_ENDPOINT` | string | `collector:4317` | Where the generator sends OTLP |
| `CONTRACTS_DIR` | string | `/contracts/v1` | Path services read the canonical contract from |
| `CH_URL` / `CH_HOST` | string | `http://clickhouse:8123` | ClickHouse endpoint for the collector |

**Default `COLLECTOR=rust`:** the Rust branch ships the most complete infra (3 DDL files + golden/gRPC/roundtrip tests), making it the most reliable default for the baseline. Fully overridable.

---

## Security Considerations

- Local-only defaults: no auth on ClickHouse/OTLP — **dev only**, documented; do not expose ports beyond localhost.
- `contracts/` mounted read-only (`:ro`) into services — consumers cannot mutate the SSOT at runtime.
- No secrets committed; `.env.example` retained, real `.env` git-ignored (merged `.gitignore`).

---

## Observability

| Aspect | Implementation |
|--------|----------------|
| Logging | Each collector's existing structured logging (unchanged) |
| Metrics | Out of scope for the baseline (deferred) |
| Tracing | The product *is* OTel telemetry; inspect ingested signals via ClickHouse Play UI :8123/play |

---

## Pipeline Architecture

### DAG Diagram

```text
[otelgen generator] ──OTLP gRPC :4317──▶ [collector-rust | collector-go] ──HTTP :8123──▶ [ClickHouse RAW]
        │  (SCENARIO, SEED)                 (selected via COLLECTOR)            (per-service schema)
        └── validates against contracts/v1 ─────────────────────────────────────────────▶ [Play UI]
```

### Partition Strategy (per-service, NOT reconciled — recorded for POD 3)

| Collector | Logs partition | Traces table | Naming |
|-----------|----------------|--------------|--------|
| Rust | `toDate(Timestamp)` (daily) | `otel_traces` | PascalCase, `DateTime64(9)` |
| Go | `toYYYYMM(ingested_at)` (monthly) | `otel_spans` | snake_case, raw `*_unix_nano` |

> Reconciliation is **out of scope** (DEFINE v1.1). `docs/clickhouse-schema-divergence.md` carries this table forward for POD 3.

### Schema Evolution Plan

| Change Type | Handling | Rollback |
|-------------|----------|----------|
| New contract field | Add to `contracts/v1`; if breaking, open `contracts/v2/` | Keep `v1` consumers pinned |
| Collector schema change | Lives in that service's own DDL; no cross-impact until POD 3 canonicalizes | Per-service revert |

### Data Quality Gates

| Gate | Tool | Threshold | Action on Failure |
|------|------|-----------|-------------------|
| Golden validates vs `contracts/v1` schema | jsonschema / per-collector golden test | 0 violations | Block (contract test) |
| E2E row count after `make e2e` | manual / Make check | > 0 rows in target tables | Fail the run |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-15 | design-agent | Initial design from DEFINE v1.1; adds configurable-collector orchestrator (resolves DEFINE Open Q4) |

---

## Next Step

**Ready for:** `/build .claude/sdd/features/DESIGN_MONOREPO_INTEGRATION.md`
