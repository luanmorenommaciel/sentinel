# BRAINSTORM: Monorepo Integration ("Glue" Branch)

> Exploratory session to clarify intent and approach before requirements capture

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | MONOREPO_INTEGRATION |
| **Date** | 2026-06-15 |
| **Author** | brainstorm-agent |
| **Status** | Ready for Define |

---

## Initial Idea

**Raw Input:** Create a new branch that serves as the "glue" for all POD work, unifying the three existing component branches into one coherent repository. The structure must be generic enough to accommodate the existing branches *and* future ones (e.g. POD 3 data modeling, future Azure/AWS generators). Branches to glue:
- `001-otel-data-generator` (POD 1 — Generator, Python)
- `feat/rust-otel-collector` (POD 2 — Collector, Rust)
- `feat/02-otel-collector-go` (POD 2 — Collector, Go)

This realizes the **"fishbone" (espinha de peixe) merge** discussed in the Jun 9 sync and the contract-driven, Lego-style integration principle from the May 26 sync: unify the components into `master`, tag a `0.0.x` baseline, and only then begin shared-repo governance and the agentic build-out.

**Context Gathered:**
- Three branches exist with **radically different top-level layouts** — Python uses `src/otelgen/` + `pyproject.toml`; Rust uses `services/collector-rust/` + `infra/`; Go uses `cmd/` + `internal/` + `migrations/`.
- **All three independently carry a `contract/` folder** (the "contract is the handoff" principle in practice) — but they have **diverged**: different filenames, and three separate copies of `golden/baseline_seed42.jsonl`.
- `main` is currently nearly empty (just `README.md`) — a clean base to branch from.
- ClickHouse schema is **duplicated and divergent**: Rust ships `infra/clickhouse/ddl/{001_otel_logs,002_otel_traces,003_otel_metrics}.sql`; Go ships `migrations/001_init_schema.sql` + a table-level contract at `contract/output_contract/contract.yml` (database `sentinel`, tables `otel_spans`...).
- Each branch ships its own `Dockerfile`/`docker-compose`/`.gitignore`/`README`.
- Generator's `contract/` mixes two concerns: the **cross-component handoff** (`schema/otlp_output.schema.json` + `golden/`) and **generator-only input config** (`scenarios/`, `topology/`, `provider_profiles/`, `clickhouse_schema.yaml`).

**Technical Context Observed (for Define):**

| Aspect | Observation | Implication |
|--------|-------------|-------------|
| Likely Location | New branch `feat/monorepo-integration` off `main`; target layout `services/<component>/` + `contracts/` + `infra/` | Monorepo with self-contained services and shared, versioned contracts |
| Relevant KB Domains | OpenTelemetry (OTLP), ClickHouse / ClickStack, monorepo structure, Docker Compose orchestration | Patterns for multi-language monorepo + OTel pipeline |
| IaC Patterns | Docker Compose per service today; ClickHouse DDL split across `infra/clickhouse/ddl/` (Rust) and `migrations/` (Go) | Consolidate into root orchestrator + one canonical `infra/clickhouse/` |

---

## Discovery Questions & Answers

| # | Question | Answer | Impact |
|---|----------|--------|--------|
| 1 | Which top-level repo layout should the glue branch establish? | **`services/` + shared `contracts/`** (flat, self-contained services; shared `contracts/`, `infra/`, `docs/` at root) | New POD 3 / future generators drop in as new `services/` entries — no structural change |
| 2 | How should the divergent `contract/` folders be reconciled? | **Versioned contract registry** (`contracts/v1/`, `v2/`) as single source of truth (output schema + golden) | Producer (generator) owns canonical contract; collectors validate against it; explicit versioning from day one |
| 3 | How should the glue branch be physically assembled? | **New branch off `main`; import each component into its `services/` slot** | Deliberate, clean reorg; resolve contract/infra overlaps once rather than a noisy 3-way merge |
| 4 | What should the glue branch be named? | **`feat/monorepo-integration`** | Matches `feat/` prefix convention of the collector branches |
| 5 | How to handle the two divergent ClickHouse schemas? | **Reconcile into one canonical schema now** | This glue work produces the first authoritative ClickHouse DDL; POD 3 inherits/refines it |
| 6 | Ship a root-level orchestrator to run the full pipeline? | **Yes — root `docker-compose` + `Makefile`** (generator → collector → ClickHouse) | Everyone gets the identical local experience the Jun 9 sync called for |

**Minimum Questions:** 3 ✅ (6 asked)

---

## Sample Data Inventory

> The three branches themselves are the ground truth — real, working code, not mock samples.

| Type | Location | Count | Notes |
|------|----------|-------|-------|
| Related code | `origin/001-otel-data-generator:src/otelgen/` | ~22 files | Python generator: cli, config, contract loader/models, exporters (otlp, clickhouse), scenarios/anomalies, signals, topology |
| Related code | `origin/feat/rust-otel-collector:services/collector-rust/src/` | ~7 files | Rust collector: grpc, otlp, clickhouse_exporter, contract, config + golden/grpc tests |
| Related code | `origin/feat/02-otel-collector-go:{cmd,internal}/` | ~25 files | Go collector: grpcserver, httpserver, chstore, transform, model, config + tests |
| Output examples / Ground truth | `contract/golden/baseline_seed42.jsonl` (all three branches) | 3 copies | The golden OTLP output sample — **diverged across branches; must pick canonical** |
| Schema | `contract/schema/otlp_output.schema.json` (Python, Rust); `contract/schema/schema_output.json` + `output_contract/contract.{json,yml}` (Go) | — | Output schema; Go also has a ClickHouse table-level contract |
| DDL | Rust `infra/clickhouse/ddl/*.sql`; Go `migrations/001_init_schema.sql` | 4 files | Two divergent ClickHouse schemas to reconcile into one canonical set |

**How samples will be used:**

- The generator's `contract/golden/` becomes the **canonical golden fixture** under `contracts/v1/golden/` (producer owns it); collector golden tests point at it.
- The reconciled ClickHouse DDL becomes the canonical `infra/clickhouse/` schema, seeded into the root Compose stack.
- Each branch's source tree imports verbatim into its `services/<component>/` slot, preserving its build tooling.

---

## Approaches Explored

### Approach A: Monorepo — `services/<component>/` + shared versioned `contracts/` ⭐ Recommended

**Description:** One repository, branched from `main` as `feat/monorepo-integration`. Each component lives in a self-contained `services/<component>/` directory keeping its native build tooling (pyproject / Cargo / go.mod). A top-level `contracts/v1/` holds the canonical output schema + golden as the single source of truth. A top-level `infra/` holds the reconciled ClickHouse DDL and the root orchestrator (`docker-compose.yml` + `Makefile`). Components are imported into their slots via deliberate file moves (history-preserving where practical), resolving the contract/infra/`.gitignore` overlaps once.

```text
sentinel/
├── contracts/
│   └── v1/
│       ├── schema/otlp_output.schema.json   # canonical output contract
│       └── golden/baseline_seed42.jsonl     # canonical golden fixture
├── services/
│   ├── generator-python/        # from 001-otel-data-generator (src/otelgen → here)
│   │   └── config/              # scenarios, topology, provider_profiles (generator INPUT)
│   ├── collector-rust/          # from feat/rust-otel-collector
│   ├── collector-go/            # from feat/02-otel-collector-go
│   └── …                        # POD 3 / future generators drop in here
├── infra/
│   └── clickhouse/              # ONE canonical reconciled DDL
├── docs/
├── docker-compose.yml           # root orchestrator (generator → collector → ClickHouse)
├── Makefile                     # make up / generate / down
├── CLAUDE.md  .claude/  .specify/
└── README.md
```

**Pros:**
- Directly extends the convention the Rust branch already uses (`services/`).
- New PODs / clouds are pure additions — no restructuring (satisfies "generic enough").
- Single contract location kills the divergence problem at the root.
- Root orchestrator gives every developer the identical local pipeline experience.
- Keeps all three languages (per Jun 9 "keep all languages for now").

**Cons:**
- Contracts live outside each service dir → **Docker build context must include `contracts/`** (root build context or mounted), a real wiring concern to design.
- Reconciling the two ClickHouse schemas now requires resolving genuine table/column divergences.
- History-preserving import across reorganized paths takes more care than a plain merge.

**Why Recommended:** It's the layout that most cleanly satisfies the explicit "generic enough for existing + new branches" requirement, encodes the contract-as-SSOT principle structurally, and matches the team's stated baseline-then-govern sequence. **Confirmed by user across all six discovery questions.**

---

### Approach B: Group-by-domain (`generators/`, `collectors/`, `platform/`)

**Description:** Cluster components by type — `generators/python/`, `collectors/{rust,go}/`, `platform/` (POD 3) — with shared `contracts/` + `infra/`.

**Pros:**
- Visually groups the two collector implementations together.
- Obvious where a new generator vs. collector goes.

**Cons:**
- Extra nesting; awkward for components that span roles (POD 3 "platform" is a catch-all).
- Diverges from the `services/` convention already in the Rust branch.

---

### Approach C: `apps/` + `packages/` (monorepo tooling)

**Description:** Nx/Turborepo-style split — `apps/` for deployables, `packages/contracts/` for shared libraries.

**Pros:**
- Scales well once there is genuinely shared *code* (not just contracts) to extract.

**Cons:**
- Heavier convention with little payoff today (no shared library code yet — YAGNI).
- Implies tooling (Nx/Turbo) the team hasn't adopted.

---

## Data Engineering Context

### Source Systems
| Source | Type | Volume Estimate | Current Freshness |
|--------|------|-----------------|-------------------|
| OTel Data Generator (Python, POD 1) | Synthetic OTLP emitter | Configurable (scenarios; cron-throttled local ingest, e.g. every 15 min per Jun 9) | Near real-time (streaming OTLP) |
| OTel Collector (Rust / Go, POD 2) | OTLP gRPC :4317 receiver → ClickHouse writer | Pass-through of generator volume | Near real-time |
| ClickHouse / ClickStack (POD 3) | Columnar store (RAW layer) | TBD by POD 3 modeling | Near real-time ingest |

### Data Flow Sketch
```text
[Generator (Python)] --OTLP gRPC 4317--> [Collector (Rust | Go)] --> [ClickHouse / ClickStack]
        │                                        │                          │
   contracts/v1 (output schema + golden) ........│..........................│
   (validated at every boundary; producer = generator owns canonical contract)
```

### Key Data Questions Explored
| # | Question | Answer | Impact |
|---|----------|--------|--------|
| 1 | Which collector implementation is canonical? | Keep **both** Rust + Go for now (decide later) | Two `services/collector-*` dirs coexist at the baseline |
| 2 | Where does the data model (ClickHouse schema) live? | One canonical `infra/clickhouse/`, reconciled during this glue work | POD 3 inherits + refines rather than starting fresh |
| 3 | What is the contract handoff exactly? | Output schema + golden in `contracts/v1/`; generator scenario/topology config stays inside the generator service | Clear SSOT boundary; collectors validate against `contracts/v1` |

---

## Selected Approach

| Attribute | Value |
|-----------|-------|
| **Chosen** | Approach A — Monorepo `services/` + shared versioned `contracts/` |
| **User Confirmation** | 2026-06-15 (confirmed via 6 discovery-question answers) |
| **Reasoning** | Cleanest fit for the "generic enough for existing + future branches" requirement; encodes contract-as-SSOT structurally; matches the team's baseline-then-govern plan |

---

## Key Decisions Made

| # | Decision | Rationale | Alternative Rejected |
|---|----------|-----------|----------------------|
| 1 | Monorepo with flat `services/<component>/` layout | Extends existing Rust `services/` convention; new PODs are drop-in additions | Group-by-domain; apps/packages tooling |
| 2 | Top-level **versioned** `contracts/v1/` as SSOT (output schema + golden) | Producer owns the canonical contract; versioning supports future breaking changes | Per-service synced copies (drift risk); unversioned single dir |
| 3 | Generator-only config (`scenarios`, `topology`, `provider_profiles`) stays inside `services/generator-python/` | It's generator *input*, not the cross-component handoff | Lumping all of `contract/` into shared `contracts/` |
| 4 | Branch `feat/monorepo-integration` off `main` | Matches `feat/` prefix of collector branches; clean empty base | Working directly on `main` (no review); plain `integration` (breaks convention) |
| 5 | Reconcile both ClickHouse schemas into one canonical DDL now | Gives POD 3 an authoritative starting model; avoids two sources of truth | Defer to POD 3; keep per-service schemas |
| 6 | Root `docker-compose.yml` + `Makefile` orchestrator | One-command end-to-end pipeline → identical local experience for all | Per-service compose only (no unified entry point) |
| 7 | Keep all three languages (Python, Go, Rust) at the baseline | Per Jun 9 sync "keep all languages for now, decide later" | Consolidate to one collector language now |

---

## Features Removed (YAGNI)

| Feature Suggested | Reason Removed | Can Add Later? |
|-------------------|----------------|----------------|
| Consolidate Rust vs Go collector into a single language | Team explicitly chose to keep all languages until the baseline is stable | Yes |
| CI/CD, branch protection, PR-approval rules, pre-commit quality gates | These belong to the post-baseline "second phase" (governance) per the Jun 9 sync, after the `0.0.x` tag | Yes |
| Agentic layer (agent fleet, KBs, routines, worktree conventions, "Dark Factory") | Depends on a stable raw layer existing first; not part of gluing the branches | Yes |
| Contract-sync automation script | Versioned registry is referenced directly by path — no sync job needed | Yes |
| Nx/Turborepo monorepo tooling | No shared library code to extract yet | Yes |
| Azure/AWS generator services | GCP-first; structure already accommodates them as new `services/` entries | Yes |

---

## Incremental Validations

| Section | Presented | User Feedback | Adjusted? |
|---------|-----------|---------------|-----------|
| Repo layout (services/ + contracts/) | ✅ | Chose Approach A | No |
| Contract SSOT strategy | ✅ | Chose **versioned** registry (stronger than the unversioned default) | Yes — adopted `contracts/v1/` |
| Merge/assembly mechanics | ✅ | Chose new branch + import into slots | No |
| Branch name | ✅ | Adjusted to `feat/monorepo-integration` (from `003-…`) | Yes |
| ClickHouse schema handling | ✅ | Chose to reconcile into one canonical schema **now** (stronger than defer-to-POD3) | Yes — canonical DDL is in-scope |
| Root orchestration | ✅ | Confirmed root compose + Makefile | No |

**Minimum Validations:** 2 ✅ (6 validation points across two question rounds)

---

## Suggested Requirements for /define

### Problem Statement (Draft)
Three POD branches with incompatible repository layouts and divergent copies of the shared contract and ClickHouse schema cannot be developed or run together; the team needs a single "glue" monorepo branch that unifies them under a generic, extensible structure with one canonical, versioned contract — the `0.0.x` baseline everyone builds on.

### Target Users (Draft)
| User | Pain Point |
|------|------------|
| POD 1 (Generator — Vinícius, Caio) | Generator output contract scattered/duplicated; no shared home |
| POD 2 (Collector — Victor, Alex, Ruan) | Two collector impls in incompatible layouts; each carries its own diverged contract copy |
| POD 3 (Infra/Modeling — Adilson, Lucas, Rafael) | No authoritative ClickHouse schema or single output structure to model against |
| Whole crew | No single repo to run the full pipeline locally or apply shared governance to |

### Success Criteria (Draft)
- [ ] `feat/monorepo-integration` branched from `main` with the `services/` + `contracts/` + `infra/` skeleton.
- [ ] All three components imported into `services/generator-python`, `services/collector-rust`, `services/collector-go`, each building independently with its native tooling.
- [ ] One canonical, versioned `contracts/v1/` (output schema + golden); duplicate per-branch copies removed; collector tests reference it.
- [ ] One canonical reconciled ClickHouse DDL under `infra/clickhouse/`; the two divergent schemas merged with table/column conflicts resolved.
- [ ] Root `docker-compose.yml` + `Makefile` bring up ClickHouse + a collector and run the generator end-to-end with one command.
- [ ] Merged root `.gitignore`, single root `README` describing the monorepo, generator-only config relocated under the generator service.
- [ ] Clean structure ready to tag a `0.0.x` baseline.

### Constraints Identified
- Keep all three languages (Python, Go, Rust) — no consolidation yet.
- Preserve each component's native build tooling (pyproject / Cargo / go.mod).
- Docker build contexts must reach the shared `contracts/` (root context or mount).
- Producer (generator) owns the canonical contract; consumers validate against it.

### Out of Scope (Confirmed)
- CI/CD, branch protection, PR-approval rules, pre-commit gates (post-baseline governance phase).
- The agentic layer (agent fleet, KBs, routines, worktrees, "Dark Factory").
- Choosing a single collector language.
- Azure/AWS generators and any new feature work beyond integration.
- Contract-sync automation tooling.

### Open Risks to Resolve in Define/Design
- **ClickHouse schema divergence:** Rust `infra/clickhouse/ddl/*.sql` vs Go `migrations/001_init_schema.sql` + `output_contract/contract.yml` may define tables/columns differently — needs a per-table "which wins" decision.
- **Golden fixture divergence:** three copies of `baseline_seed42.jsonl` differ — pick the generator's as canonical and re-point collector tests.
- **Docker build context for shared contracts:** services referencing `contracts/v1/` from outside their dir need adjusted build context or bind mounts.
- **History preservation:** decide per-component whether to import with `git read-tree`/subtree (preserve authorship) or plain copy.

---

## Session Summary

| Metric | Value |
|--------|-------|
| Questions Asked | 6 |
| Approaches Explored | 3 |
| Features Removed (YAGNI) | 6 |
| Validations Completed | 6 |
| Duration | ~1 exploration session |

---

## Next Step

**Ready for:** `/define .claude/sdd/features/BRAINSTORM_MONOREPO_INTEGRATION.md`
