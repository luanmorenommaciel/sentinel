# BUILD REPORT: Monorepo Integration ("Glue" Branch)

> Implementation report for MONOREPO_INTEGRATION

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | MONOREPO_INTEGRATION |
| **Date** | 2026-06-15 |
| **Author** | build-agent |
| **DEFINE** | [DEFINE_MONOREPO_INTEGRATION.md](../features/DEFINE_MONOREPO_INTEGRATION.md) (v1.1) |
| **DESIGN** | [DESIGN_MONOREPO_INTEGRATION.md](../features/DESIGN_MONOREPO_INTEGRATION.md) |
| **Branch** | `feat/monorepo-integration` (off `main`) |
| **Status** | Complete — generator + both collectors tested (collectors via Docker against live ClickHouse) |

---

## Summary

| Metric | Value |
|--------|-------|
| **Tasks Completed** | 18/18 manifest steps |
| **Files Created/Imported** | ~130 (118 under `services/`, + contracts, orchestrator, docs) |
| **New authored files** | 6 (`docker-compose.yml`, `Makefile`, root `README.md`, `.gitignore`, `contracts/v1/README.md`, `docs/clickhouse-schema-divergence.md`) |
| **Generator tests** | 176 passed (unit); integration covered by Docker e2e below |
| **Collector tests (Docker)** | Rust: 90 passed (incl. 2 live-ClickHouse). Go: unit + 3 live-ClickHouse integration passed |
| **Golden fixtures** | 1 (AT-005 satisfied) |
| **Agents Used** | 0 (built directly — structural git/devops work) |

---

## Task Execution

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Create `feat/monorepo-integration` off `main` | ✅ | Untracked SDD/meeting docs carried over |
| 2 | Import generator → `services/generator-python` | ✅ | `git archive` of `src`, `tests`, root files, `config/` |
| 3 | Import collector-rust → `services/collector-rust` (+ infra) | ✅ | Crate subdir imported cleanly — no double-nesting |
| 4 | Import collector-go → `services/collector-go` | ✅ | Whole branch tree (cmd/internal/migrations) |
| 5–6 | `contracts/v1/` schema + golden (SSOT) | ✅ | Moved from generator; canonical |
| 7 | `contracts/v1/README.md` | ✅ | Version policy + producer/consumer |
| 8 | Remove duplicate golden | ✅ | Go dup removed; Rust had none in-crate |
| 9 | Relocate generator config → `config/` | ✅ | scenarios/topology/provider_profiles/clickhouse_schema.yaml |
| 10 | Generator Dockerfile + `output_schema.py` path | ✅ | `COPY config/`, `CONTRACTS_DIR` env, schema_path env-aware |
| 11–12 | Collector golden path re-point | ✅ | Rust config + tests `contract/golden`→`contracts/v1/golden` (same depth) |
| 13 | Root `docker-compose.yml` (profiles) | ✅ | `rust`/`go` profiles, `collector` alias, parses for both |
| 14 | Root `Makefile` (`COLLECTOR` switch) | ✅ | up/init/generate/e2e/down/reset/logs + guard |
| 15 | Merged `.gitignore` | ✅ | Union of 3 branches (minus `docs/`) |
| 16 | Root `README.md` | ✅ | Monorepo map + configurable e2e UX |
| 17 | `docs/clickhouse-schema-divergence.md` | ✅ | Carried forward for POD 3 |
| 18 | Re-point collector golden tests | ✅ | Rust `golden_parse.rs` + `clickhouse_roundtrip.rs` |
| + | Fix stale test paths (relocation cascade) | ✅ | `conftest.py`, `test_cli.py`, `test_golden.py` |

---

## Files Created (authored, not imported)

| File | Purpose | Verified |
|------|---------|----------|
| `docker-compose.yml` | Root orchestrator, `rust`/`go` profiles, `collector` network alias | ✅ `docker compose config` parses both profiles |
| `Makefile` | `COLLECTOR`/`SCENARIO`/`SEED`/`WINDOW` switches; e2e pipeline | ✅ `guard` accepts rust/go, rejects invalid |
| `README.md` (root) | Monorepo map + configurable e2e quick start | ✅ |
| `.gitignore` (root) | Merged ignores (Python/Rust/Go/infra) | ✅ |
| `contracts/v1/README.md` | SSOT contract version policy | ✅ |
| `docs/clickhouse-schema-divergence.md` | POD 3 reconciliation record | ✅ |

---

## Verification Results

### Generator (Python) — full toolchain available

```text
ruff check src/            → All checks passed!
pytest tests/unit          → 176 passed
pytest tests/integration   → 6 errored (require a live ClickHouse — run via `make e2e`)
otelgen dry-run (config/)  → exit 0, validates relocated config + contracts/v1 schema
```

**Status:** ✅ Pass (unit) — config relocation and `contracts/v1` resolution proven end-to-end.

### Orchestrator

```text
COMPOSE_PROFILES=rust docker compose config  → OK
COMPOSE_PROFILES=go   docker compose config  → OK
make guard COLLECTOR=rust|go                  → OK
make guard COLLECTOR=java                     → correctly rejected
find … -name baseline_seed42.jsonl            → exactly 1 (AT-005)
```

**Status:** ✅ Pass.

### Collectors (Rust / Go) — compiled & tested in Docker

No host `cargo`/`go` toolchain, so both collectors were compiled and tested in
official language containers (`rust:1.96`, `golang:1.21`) on a shared Docker
network with a live `clickhouse-server:24.3`.

```text
# Go (golang:1.21)
go test ./...                              → grpcserver ok, transform ok
go test -tags integration ./internal/chstore/...
    TestIntegration_InsertSpan   PASS
    TestIntegration_InsertLog    PASS
    TestIntegration_InsertMetric PASS      → writes to sentinel.* over :9000

# Rust (rust:1.96)
cargo test --locked                        → 88 passed (81 unit + 3 golden_parse + 2 grpc_smoke + 2 doctest)
cargo test --locked -- --ignored
    clickhouse_roundtrip::golden_fixture_round_trip            ok   (golden → default.* , MV fires)
    grpc_export_roundtrip::otlp_grpc_payload_lands_in_clickhouse ok (OTLP gRPC → ClickHouse e2e)
```

**Both schemas coexisted** in one ClickHouse: `default.*` (Rust, 5 tables) + `sentinel.*`
(Go, 3 tables) — a live demonstration of AT-006. The Rust golden tests also confirm the
`contracts/v1/golden` re-point.

**Status:** ✅ Pass — collectors compile and pass unit + live-ClickHouse integration tests.

### Full root-compose end-to-end (`make e2e`) — both collectors

Built the service images and ran the whole pipeline through `docker-compose.yml`
(`make up/init/generate`), generating `--scenario baseline --seed 42 --window 5m`
(233,100 signals) into each collector and counting rows in ClickHouse:

```text
COLLECTOR=rust  →  default.otel_logs=40200  otel_traces=40200  otel_metrics=152700  (otel_metrics_1m MV: 166)
COLLECTOR=go    →  sentinel.otel_logs=40200 otel_spans=40200   otel_metrics=152700
generator emitted: log=40200  span=40200  metric=152700  (delivery otlp, 0 failures)
```

**Exact row-count match for both collectors, zero loss, no export errors** — the
configurable `COLLECTOR=rust|go` pipeline works end-to-end (AT-007 fully closed).

---

## Autonomous Decisions

| # | Fork | Decision | Rationale |
|---|------|----------|-----------|
| 1 | History-preserving merge vs clean import (DESIGN Decision 5) | Clean import via `git archive \| tar` | Avoids fragile unrelated-history merges; origin branches retain full history. Matches DESIGN's documented fallback. |
| 2 | Root build context vs runtime mount for `contracts/` (DESIGN Decision 4) | Service-local build context + runtime read-only bind-mount (`CONTRACTS_DIR=/contracts/v1`) | Contract is needed at runtime, not build; avoids rewriting every `COPY` path. Smallest correct change. |
| 3 | Generator targeting one of two collector hostnames | Network alias `collector` on both collectors | Generator uses `http://collector:4317` regardless of active profile. |
| 4 | ClickHouse auth (Go needs `otelgen@sentinel`, Rust uses `default@http`) | CH service env creates `otelgen`/`sentinel`; `default` user remains | Satisfies both collectors from one ClickHouse. |
| 5 | Generator CLI invocation in `make generate` | `otelgen --scenario …` (no `run` subcommand) + `WINDOW=5m` default | otelgen is a single-command Typer app; small default window keeps `make e2e` fast. |
| 6 | Stale test paths after relocation | Updated `conftest.py`→`config/`, `test_cli.py`→`config/`, `test_golden.py`→`contracts/v1` (env-aware) | Required so generator tests pass against the new layout. |
| 7 | Default collector | `COLLECTOR=rust` (per DESIGN) | Rust ships the most complete infra (3 DDL + golden/gRPC/roundtrip tests). Overridable. |
| 8 | ClickHouse user setup (found during Docker testing) | Create `otelgen`/`sentinel` via init script, NOT `CLICKHOUSE_USER` env | `CLICKHOUSE_USER`/`PASSWORD` env breaks the passwordless `default` user that the Rust collector uses. Added `infra/clickhouse-init.sql`. |
| 9 | ClickHouse `default` user is localhost-only (image default) | Mount `users.d` override widening `default` networks to `::/0` | The Rust collector connects as `default` over the Docker network; the image restricts it to `::1`/`127.0.0.1`. Added `infra/clickhouse-users.d/zz-default-network.xml`. |
| 10 | Rust collector needs a `grpc` config section + reads `CLICKHOUSE_URL` (found during compose e2e) | Added `services/collector-rust/config.docker.yaml` (grpc + clickhouse), mounted it, pass as argv[1]; fixed compose env `CH_URL`→`CLICKHOUSE_URL` | The binary only enters OTLP server mode when its config file has a `grpc` section; env alone keeps it in file/count mode. |

---

## Verification Gaps (not blockers)

None remaining for the integration scope. Generator (176 unit), both collectors
(unit + live-ClickHouse integration), and the full `make e2e` for both `COLLECTOR`
values were all run and pass.

**Operational note — stale ClickHouse volume:** `CREATE TABLE IF NOT EXISTS` will not
update an existing table whose schema changed. When a collector's DDL changes, run
`make reset` (drops the `clickhouse_data` volume) before `make init`, or inserts fail
with `NO_SUCH_COLUMN`. Hit and resolved during this e2e.

---

## Acceptance Test Mapping

| AT | Status | Evidence |
|----|--------|----------|
| AT-001 branch + skeleton | ✅ | `services/`, `contracts/v1/`, root compose + Makefile present |
| AT-002 generator builds in place | ✅ | `uv pip install -e .` + 176 unit tests pass |
| AT-003/004 collectors build in place | ✅ | Compiled in Docker (`rust:1.96`, `golang:1.21`); unit + integration tests pass |
| AT-005 single contract SSOT | ✅ | exactly 1 `baseline_seed42.jsonl` |
| AT-006 per-service schemas coexist | ✅ | Live: `default.*` (Rust, 5) + `sentinel.*` (Go, 3) applied to one ClickHouse |
| AT-007 end-to-end configurable | ✅ (collector paths proven) | Rust `grpc_export_roundtrip` + Go integration land OTLP→ClickHouse; full `make e2e` via root compose still recommended as a final check |
| AT-008 new-service drop-in | ✅ | Adding a `services/<x>/` + profile requires no structural change |
| AT-009 contract validation at boundary | ✅ (generator side) | `output_schema.schema_path()` resolves `contracts/v1`; golden validates in tests |

---

## Blockers

None. The build is structurally complete; the only open items are toolchain/runtime
verifications that cannot run in this environment (logged as gaps, not blockers).

---

## Addendum — POD 2 / POD 3 integration (2026-06-22, post-pull)

Pulled commits `660920d` (POD 3 bronze DDL), `4c60245` (POD-2 foundation), `de5cc24`
(schema standardization). Verified the merged state and aligned the orchestrator:

**What POD 2/3 delivered**
- **POD 2 normalized both collectors** to write an *identical* schema (`otel_logs /
  otel_traces / otel_metrics` + `otel_metrics_1m` MV) to the **`default`** db.
- **POD 3 added a canonical bronze DDL** at `infra/clickhouse/init.d/01-bronze-otel.sql`
  (`sentinel.*`, OTel-contrib style, metrics split into 5 type tables).

**Compliance check (answering "are the collectors compliant with the canonical DDL?")**
- ✅ The two collectors are compliant **with each other** (normalized, identical columns).
- ✅ The canonical bronze DDL is **valid** — applies cleanly on boot; all 9 `sentinel.*`
  tables created, no errors.
- ❌ The collectors do **NOT** write to the canonical bronze. They write the normalized
  schema to `default.*`; the bronze `sentinel.*` tables stay empty. This is the
  **documented gap** (`docs/research/pod3-bronze-gap.md`) — bridging collector output to
  the bronze landing is the remaining POD 2→3 work.

**Orchestrator fixes applied**
1. `collector-go` DSN `…/sentinel` → `…/default` — Go now writes the normalized schema to
   `default` (its migration header: "Database: default (matches Rust)"); the old DSN would
   have written to the wrong db.
2. Mounted the bronze DDL into `/docker-entrypoint-initdb.d/02-bronze-otel.sql` so the
   canonical schema is present + validated at runtime.

**Re-verified end-to-end (full `make e2e`, baseline seed 42, window 5m → 233,100 signals)**
```text
COLLECTOR=rust  →  default.{otel_logs=40200, otel_traces=40200, otel_metrics=152700}   (0 errors)
COLLECTOR=go    →  default.{otel_logs=40200, otel_traces=40200, otel_metrics=152700}   (0 errors)
sentinel.* bronze present, valid, empty (collectors don't feed it yet — the gap)
```
All test suites green post-pull: generator 176; Go grpcserver + transform; Rust 88 (CH tests `#[ignore]`d).

## Next Step

1. **Bridge collectors → bronze** (the open gap): make the collectors write to POD 3's
   `sentinel.*` bronze (per `pod3-bronze-gap.md`, an export-layer-only change).
2. `/ship` when the team is ready to archive the baseline.
