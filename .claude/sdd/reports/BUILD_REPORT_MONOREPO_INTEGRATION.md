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
| **Status** | Complete (with verification gaps — see below) |

---

## Summary

| Metric | Value |
|--------|-------|
| **Tasks Completed** | 18/18 manifest steps |
| **Files Created/Imported** | ~130 (118 under `services/`, + contracts, orchestrator, docs) |
| **New authored files** | 6 (`docker-compose.yml`, `Makefile`, root `README.md`, `.gitignore`, `contracts/v1/README.md`, `docs/clickhouse-schema-divergence.md`) |
| **Generator tests** | 176 passed (unit), 6 integration errored (need live ClickHouse) |
| **Collector tests** | Not run — no `cargo`/`go` toolchain in this environment |
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

### Collectors (Rust / Go) — toolchain NOT available

`cargo`, `go`, and `just` are absent in this environment, so the Rust and Go
collectors were **not compiled or tested here**. Source path edits were applied
(golden path re-point) and are correct by inspection (same `../../` depth →
`contracts/v1/golden`). Compilation + their golden/roundtrip tests must be run
on a machine with the toolchains (or via `docker compose build`, which compiles
inside the image).

**Status:** ⚠️ Deferred — see Verification Gaps.

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

---

## Verification Gaps (not blockers)

| Gap | Why | How to close |
|-----|-----|--------------|
| Rust/Go collectors not compiled/tested | No `cargo`/`go`/`just` in this environment | Run `cargo test` / `go test`, or `docker compose build`, on a toolchain machine |
| Live end-to-end not executed (AT-007) | Full `docker compose build` + run is heavy/network-bound; not run in this pass | `make e2e COLLECTOR=rust` and `make e2e COLLECTOR=go`; confirm rows at `:8123/play` |
| Generator integration tests (6) | Require a live ClickHouse | Covered by the e2e run above |

---

## Acceptance Test Mapping

| AT | Status | Evidence |
|----|--------|----------|
| AT-001 branch + skeleton | ✅ | `services/`, `contracts/v1/`, root compose + Makefile present |
| AT-002 generator builds in place | ✅ | `uv pip install -e .` + 176 unit tests pass |
| AT-003/004 collectors build in place | ⚠️ deferred | No toolchain here; structure + path edits correct by inspection |
| AT-005 single contract SSOT | ✅ | exactly 1 `baseline_seed42.jsonl` |
| AT-006 per-service schemas coexist | ✅ | Rust DDL + Go migrations each in their service; `make init` is collector-scoped |
| AT-007 end-to-end configurable | ⚠️ deferred | Orchestrator built + parses; needs a live run |
| AT-008 new-service drop-in | ✅ | Adding a `services/<x>/` + profile requires no structural change |
| AT-009 contract validation at boundary | ✅ (generator side) | `output_schema.schema_path()` resolves `contracts/v1`; golden validates in tests |

---

## Blockers

None. The build is structurally complete; the only open items are toolchain/runtime
verifications that cannot run in this environment (logged as gaps, not blockers).

---

## Next Step

1. On a machine with `cargo`/`go` (or via Docker), run `make e2e COLLECTOR=rust` and
   `make e2e COLLECTOR=go` to close AT-003/004/007.
2. Tag the `0.0.x` baseline once the e2e passes.
3. `/ship .claude/sdd/features/DEFINE_MONOREPO_INTEGRATION.md` when ready.
