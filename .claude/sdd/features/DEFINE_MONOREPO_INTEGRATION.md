# DEFINE: Monorepo Integration ("Glue" Branch)

> Unify the three POD branches into one generic, contract-driven monorepo on `feat/monorepo-integration` — the `0.0.x` baseline the whole crew builds on.

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | MONOREPO_INTEGRATION |
| **Date** | 2026-06-15 |
| **Author** | define-agent |
| **Status** | Ready for Design |
| **Clarity Score** | 14/15 |
| **Version** | 1.1 |

---

## Problem Statement

The three POD branches (`001-otel-data-generator` Python, `feat/rust-otel-collector` Rust, `feat/02-otel-collector-go` Go) have **incompatible repository layouts**, **three diverged copies of the shared contract** (`contract/golden/baseline_seed42.jsonl` plus differing schema files), and **two mutually incompatible ClickHouse schemas** — so the components cannot be developed, run, or governed together. The crew needs a single "glue" monorepo branch with a generic, extensible structure and one canonical, versioned contract, to serve as the `0.0.x` baseline before shared governance and the agentic build-out begin.

---

## Target Users

| User | Role | Pain Point |
|------|------|------------|
| POD 1 — Vinícius, Caio | Generator (Python) | Output contract is duplicated/scattered; no shared home; can't prove the generator's output feeds a collector end-to-end |
| POD 2 — Victor, Alex, Ruan | Collector (Rust + Go) | Two collector implementations in incompatible layouts, each carrying its own diverged contract copy and its own ClickHouse DDL |
| POD 3 — Adilson, Lucas, Rafael | Infra / data modeling | No authoritative ClickHouse schema or single output structure to model against; two conflicting DDLs to choose between |
| Whole crew (led by Luan) | Integration / governance | No single repo to run the full pipeline locally or apply shared rules (PRs, CLAUDE.md, worktrees) to |

---

## Goals

| Priority | Goal |
|----------|------|
| **MUST** | Create `feat/monorepo-integration` off `main` with the `services/` + `contracts/` + `infra/` skeleton |
| **MUST** | Import all three components into self-contained `services/<component>/` dirs, each building independently with its native tooling (pyproject / Cargo / go.mod) |
| **MUST** | Establish one canonical, versioned `contracts/v1/` (output schema + golden) as SSOT; remove the duplicate per-branch copies |
| **MUST** | Keep each collector's existing ClickHouse schema inside its own `services/<collector>/` dir (no reconciliation now); document the two side-by-side and defer a single canonical model to POD 3 |
| **MUST** | Provide a root `docker-compose.yml` + `Makefile` that runs generator → collector → ClickHouse end-to-end with one command |
| **SHOULD** | Relocate generator-only config (`scenarios`, `topology`, `provider_profiles`) inside `services/generator-python/`; merge `.gitignore`; write one root `README` describing the monorepo |
| **SHOULD** | Preserve each component's git authorship/history on import where practical |
| **COULD** | Re-point each collector's golden tests at the canonical `contracts/v1/golden/` fixture |

---

## Success Criteria

- [ ] `feat/monorepo-integration` exists, branched from `main`, with the agreed `services/` + `contracts/` + `infra/` skeleton.
- [ ] **3/3** components present under `services/` (`generator-python`, `collector-rust`, `collector-go`), each building green with its own toolchain (no cross-service path breakage).
- [ ] Exactly **1** canonical contract version directory (`contracts/v1/`) containing the output schema + golden; **0** duplicate `golden/baseline_seed42.jsonl` copies remain elsewhere in the tree.
- [ ] Each collector retains its **own** ClickHouse DDL inside its `services/<collector>/` dir; the Rust and Go schemas are **not** merged. Their divergence is documented side-by-side for POD 3 to reconcile later.
- [ ] **1** command (`make up && make generate`) brings up ClickHouse + a collector and lands generator output in ClickHouse — verifiable by a non-zero row count in the target tables.
- [ ] **1** merged root `.gitignore` and **1** root `README`; generator-only config no longer sits in a shared `contracts/` location.
- [ ] Structure is clean and ready to tag `0.0.x` (no leftover per-branch `Dockerfile`/`compose`/`README` at the repo root that conflict with the root orchestrator).

---

## Acceptance Tests

| ID | Scenario | Given | When | Then |
|----|----------|-------|------|------|
| AT-001 | Branch + skeleton | `main` checked out | `feat/monorepo-integration` is created and scaffolded | `services/`, `contracts/v1/`, `infra/`, root `docker-compose.yml` + `Makefile` exist |
| AT-002 | Generator builds in place | Monorepo branch | `services/generator-python` is built/installed | Build succeeds; generator CLI runs from its new path |
| AT-003 | Rust collector builds in place | Monorepo branch | `cargo build` runs in `services/collector-rust` | Compiles green; references `contracts/v1/` (not a local copy) |
| AT-004 | Go collector builds in place | Monorepo branch | `go build ./...` runs in `services/collector-go` | Compiles green; references `contracts/v1/` (not a local copy) |
| AT-005 | Single contract SSOT | Imported repo | Search the tree for `baseline_seed42.jsonl` | Exactly one copy, under `contracts/v1/golden/` |
| AT-006 | Per-service schemas coexist | Imported repo | Each collector's own DDL is applied to its own ClickHouse run | Each schema applies cleanly within its service; no attempt to merge Rust vs Go is made |
| AT-007 | End-to-end pipeline | Monorepo branch | `make up` then `make generate` | Generator emits OTLP → collector ingests → ClickHouse tables have rows |
| AT-008 | New service drop-in (extensibility) | Monorepo branch | A placeholder `services/<pod3>/` is added | No structural change needed elsewhere; root orchestrator can reference it |
| AT-009 | Contract validation at boundary | Running pipeline | Generator emits a payload | Collector validates it against `contracts/v1/` schema and accepts it |

---

## Out of Scope

- **Reconciling the two ClickHouse schemas into one canonical model** — each collector keeps its own DDL in its service dir for now; the unified data model is POD 3's later decision.
- CI/CD, branch protection, PR-approval rules, pre-commit quality gates — deferred to the post-baseline governance phase.
- The agentic layer (agent fleet, knowledge bases, routines, loops, worktree conventions, "Dark Factory").
- Choosing a single collector language (both Rust and Go stay at the baseline).
- Azure/AWS generators and any new feature/functionality work beyond integration.
- Contract-sync automation tooling (the versioned registry is referenced directly by path).
- Adopting monorepo tooling (Nx/Turborepo).
- Performance tuning / load testing of the collectors or ClickHouse.

---

## Constraints

| Type | Constraint | Impact |
|------|------------|--------|
| Technical | Keep all three languages (Python, Go, Rust) — no consolidation | Two collector service dirs coexist; layout must hold both cleanly |
| Technical | Preserve each component's native build tooling (pyproject / Cargo / go.mod) | Services stay self-contained; no shared build system imposed |
| Technical | Producer (generator) owns the canonical contract; consumers validate against it | `contracts/v1/` schema is authoritative; collectors read it, not their own copy |
| Technical | Each collector keeps its own ClickHouse schema; no canonical DDL is produced now | `infra/` holds only the root orchestrator, not a merged schema; POD 3 reconciles later. Note: the contract SSOT still applies — only the *ClickHouse storage* schema stays per-service |
| Technical | Docker build contexts must reach the shared `contracts/` (root context or bind mount) | Dockerfiles/compose need adjusted build context; affects design of the root orchestrator |
| Technical | Branch from near-empty `main` (only `README.md`) | Clean base; import is additive rather than a conflicting 3-way merge |
| Timeline | Targeted as a 1–2 hour-per-member effort, baseline tagged ~next sync | Scope ruthlessly to integration only; defer everything governance/agentic |
| Resource | No new cloud infra — local Docker/ClickHouse only | Orchestrator must run fully locally |

---

## Technical Context

| Aspect | Value | Notes |
|--------|-------|-------|
| **Deployment Location** | New branch `feat/monorepo-integration`; layout `services/<component>/` + `contracts/v1/` + `infra/` + root orchestrator | Generic monorepo; new PODs/clouds are drop-in `services/` entries |
| **KB Domains** | OpenTelemetry / OTLP, ClickHouse / ClickStack, monorepo structure, Docker Compose orchestration, data contracts | Patterns for multi-language monorepo + OTel ingestion pipeline |
| **IaC Impact** | Additive — keep each collector's existing ClickHouse DDL inside its service dir (no canonical `infra/clickhouse/` merge now); add root `docker-compose.yml` + `Makefile` | No new cloud resources; local Docker only |

---

## Data Contract

> This feature is fundamentally a data-contract consolidation, so this section is central.

### Source Inventory
| Source | Type | Volume | Freshness | Owner |
|--------|------|--------|-----------|-------|
| OTel Data Generator (Python) | Synthetic OTLP emitter | Configurable via scenarios; throttled local ingest | Near real-time (streaming OTLP gRPC :4317) | POD 1 |
| OTel Collector (Rust) | OTLP receiver → ClickHouse writer | Pass-through of generator volume | Near real-time | POD 2 |
| OTel Collector (Go) | OTLP receiver → ClickHouse writer | Pass-through of generator volume | Near real-time | POD 2 |
| ClickHouse / ClickStack | Columnar store (RAW layer) | TBD by POD 3 | Near real-time ingest | POD 3 |

### Contract Sources to Reconcile (as-is, verified in branches)
| Branch | Output schema | Golden | ClickHouse schema |
|--------|---------------|--------|-------------------|
| `001-otel-data-generator` | `contract/schema/otlp_output.schema.json` | `contract/golden/baseline_seed42.jsonl` | `contract/clickhouse_schema.yaml` (reference) |
| `feat/rust-otel-collector` | `contract/schema/otlp_output.schema.json` | `contract/golden/baseline_seed42.jsonl` | `infra/clickhouse/ddl/{001_otel_logs,002_otel_traces,003_otel_metrics}.sql` |
| `feat/02-otel-collector-go` | `contract/schema/schema_output.json` + `contract/output_contract/contract.{json,yml}` | `contract/golden/baseline_seed42.jsonl` | `migrations/001_init_schema.sql` (db `sentinel`) |

### ClickHouse Schema Divergence (documented for POD 3 — NOT reconciled in this feature)

> Each collector keeps its own schema for now. This table is recorded so POD 3 can make the canonical decision later with full context; nothing here is resolved in MONOREPO_INTEGRATION.

| Dimension | Rust (`feat/rust-otel-collector`) | Go (`feat/02-otel-collector-go`) | Deferred decision (POD 3) |
|-----------|-----------------------------------|----------------------------------|---------------------------|
| Column naming | PascalCase (`ServiceName`, `Timestamp`, `TraceId`) | snake_case (`service_name`, `time_unix_nano`, `trace_id`) | Pick one convention |
| Database | default db | `sentinel` | Pick db name |
| Traces table | `otel_traces` | `otel_spans` | Pick table name |
| Partitioning | `PARTITION BY toDate(Timestamp)` (daily) | `PARTITION BY toYYYYMM(toDateTime(ingested_at))` (monthly) | Pick partition strategy |
| Timestamp representation | `DateTime64(9,'UTC')` | raw `*_unix_nano` Int + `ingested_at` | Pick representation |
| ORDER BY (logs) | `(ServiceName, Timestamp, TraceId)` | `(service_name, time_unix_nano)` | Pick sort key |
| Engine | `MergeTree` | `MergeTree()` | Compatible |
| Sentinel metadata cols | `SentinelScenario`, `SentinelRunId`, `CloudProvider`, `SentinelSynthetic`, `ContractVersion` | (fewer / different) | Decide canonical metadata columns |

### Freshness SLAs
| Layer | Target | Measurement |
|-------|--------|-------------|
| Raw (ClickHouse) | Within seconds of generator emission (streaming) | Compare `ingested_at`/`Timestamp` vs emit time |

### Completeness Metrics
- Every OTLP signal emitted by the generator in a run is queryable in ClickHouse (no dropped signals in the happy-path local run).
- Zero contract-validation rejections for golden input against `contracts/v1/` schema.

### Lineage Requirements
- `contracts/v1/` schema is the explicit producer→consumer lineage anchor; the ClickHouse DDL declares its `ContractVersion`/contract reference so stored rows trace back to a contract version.

---

## Assumptions

| ID | Assumption | If Wrong, Impact | Validated? |
|----|------------|------------------|------------|
| A-001 | The three branches' generator output schemas are compatible enough that one `contracts/v1/` schema satisfies all consumers | Would need per-consumer contract variants or a v1/v2 split before baseline | [ ] |
| A-002 | Keeping two separate collector schemas is acceptable for the baseline (the end-to-end run uses one default collector against its own schema) | If a unified model is needed before POD 3, scope expands to a reconciliation task | [ ] |
| A-003 | POD 3 (Adilson/Lucas/Rafael) will later own the canonical schema reconciliation, using the divergence table as input | If deferred indefinitely, the two collectors keep diverging and integration debt grows | [ ] |
| A-004 | Docker build context can be set to repo root so services reach `contracts/v1/` without copying | Would fall back to per-service synced copies (drift risk), partly undermining the SSOT goal | [ ] |
| A-005 | The three golden `baseline_seed42.jsonl` files are produced by the same seed/logic, so the generator's copy is a valid canonical for all | Collector golden tests would fail against the canonical and need regeneration | [ ] |

**Note:** With schema reconciliation now deferred, the highest-risk assumptions are A-001 (one contract schema satisfies all consumers) and A-004 (Docker build context can reach `contracts/v1/`); validate these early in DESIGN.

---

## Clarity Score Breakdown

| Element | Score (0-3) | Notes |
|---------|-------------|-------|
| Problem | 3 | Specific: incompatible layouts + diverged contracts + conflicting schemas, with named branches |
| Users | 3 | Four personas (3 PODs + integration lead) with concrete pain points |
| Goals | 3 | Prioritized MUST/SHOULD/COULD, all integration-scoped |
| Success | 2 | Mostly boolean/countable (1 contract, 3 services, 0 duplicates, 1 command) — testable but few numeric thresholds, as expected for a refactor |
| Scope | 3 | Explicit, generous out-of-scope list |
| **Total** | **14/15** | Exceeds the 12/15 threshold — ready for Design |

---

## Open Questions

1. **Canonical ClickHouse schema** — which conventions win (naming, db name, traces table name, partition strategy, timestamp representation)? **DEFERRED — out of scope for this feature.** Each collector keeps its own schema for now; POD 3 reconciles later using the divergence table above. No longer blocks this feature.
2. **Contract format unification** — Go uses `schema_output.json` + `output_contract/contract.{json,yml}` (a table-level contract); Python/Rust use `otlp_output.schema.json`. Which becomes the canonical `contracts/v1/` shape (and does the table-level contract move to `infra/`)?
3. **History preservation method** — `git read-tree`/subtree (preserve authorship) vs plain copy (simplest) — confirm during DESIGN/BUILD.
4. **Which collector does the end-to-end `make up` default to** (Rust or Go), given both are kept?

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-15 | define-agent | Initial version from BRAINSTORM_MONOREPO_INTEGRATION |
| 1.1 | 2026-06-15 | iterate-agent | Do NOT reconcile the two ClickHouse schemas — each collector keeps its own DDL in its service dir; canonical model deferred to POD 3. Updated Goals, Success Criteria, AT-006, Out of Scope, Constraints, IaC Impact, Data Contract divergence table, assumptions A-002/A-003, and Open Question 1 |

---

## Next Step

**Ready for:** `/design .claude/sdd/features/DEFINE_MONOREPO_INTEGRATION.md`
