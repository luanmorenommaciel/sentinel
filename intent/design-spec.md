# Requirements & Design Spec — SDLC cycle following the `sdlc-e2e-review` baseline

> **Companion document.** This spec assumes [`intent/core-intent.md`](core-intent.md) is open
> beside it (877 lines, HEAD `3af2ee7`, 2026-10-05). The As-Is is **not** restated here; it is
> referenced by section number (`CI §2`, `CI §5`, …). Where this spec contradicts or sharpens
> `core-intent.md`, it says so explicitly under *Corrections to the baseline*.
>
> **Evidence discipline.** Every claim is either **[E]** evidence (a file path, with line
> numbers where the line is load-bearing) or **[I]** inference. Three design decisions rest on
> ClickHouse behaviour I could **not** verify, because running the stack was out of scope —
> they are marked **[V]** *verify before implementing* and listed again in §8.
>
> *Written 2026-10-05. No file other than this one was created or modified.*

---

## 0. Corrections to the baseline

Four readings diverge from `core-intent.md`. They matter because requirements were going to be
built on them.

| # | `core-intent.md` says | Actually | Evidence |
|---|---|---|---|
| 1 | "ClickHouse operational ownership is unassigned (`README.md` §7)" (§3 Candidate A, §6) | README §7 does **not** say this. The sentence lives in a proposal doc, and in the deleted `.claude/CLAUDE.md` | `docs/proposals/canonical-read-schema.md:123`; `git show HEAD:.claude/CLAUDE.md` ("ClickHouse operational ownership stays unassigned") |
| 2 | "`clippy::pedantic`" is part of the lint policy (implied by the task brief, not by core-intent) | **Commented out.** `pedantic`, `nursery`, `missing_docs`, `missing_errors_doc`, `must_use_candidate` are all disabled, labelled *aspirational* pending a cleanup PR for ~50 warnings | `services/collector-rust/Cargo.toml:90-104` |
| 3 | "three Compose files" | **Four** Compose files; three of them define a ClickHouse. The fourth is a collector overlay | `docker-compose.yml`, `services/collector-rust/infra/docker-compose.yml`, `services/collector-rust/infra/docker-compose.collector.yml`, `services/generator-python/docker-compose.yaml` |
| 4 | generator `tests/unit/` = 175 test fns; 5 `#[ignore]`d Rust tests | 169 unit + 6 integration = 175 (the 175 folded integration in); **6** `#[ignore]`d | static grep, see REQ-B-09 |

Correction 2 is the consequential one: **no plan may assume `pedantic` is enforced.**

---

## 1. Scope & non-goals

### In scope — six candidates (user-selected, not re-litigated)

| ID | Candidate | One-line scope |
|---|---|---|
| **A** | Close the deployment gap | Image registry + provenance, config/secret flow, environment promotion, a ClickHouse DDL migration runner, and a deploy pipeline — with the **compute form left to an ADR** |
| **B** | Python CI coverage (issue #34) | Gate the 246 Python test functions, the 18 silver SQL asserts, and the ruff configs |
| **D** | Pod 3 silver completion | Table-backed rolling-stats rollup + the three Watcher read models the first Watchers need |
| **E** | Silver backfill + flow-ui migration (issue #37) | Idempotent, range-controlled backfill; move flow-ui's three bronze-derived boards without dropping history |
| **H** | Baseline security hardening | Least-privilege ClickHouse users, drop the passwordless `::/0` `default`, secrets flow, TLS per hop |
| **I** | Housekeeping with drift risk | Drop the vestigial `otelgen` user; reconcile the ClickHouse definitions and versions; kill the port-8080 collision |

### Out of scope — and why

- **Candidate C — decision-record drift.** Already owned, per the `CLAUDE.md` *Known doc drift*
  table (ADR-0004 → Pod 2; ADR-0007/0008 → cross-Pod sync; Pod↔layer mapping → Captain /
  Commander; ADR-0009 amendment → Captain / Commander). Excluding it is a **scheduling risk,
  not a scope saving** — this spec raises **seven** new ADRs (§9) into a team whose last six
  ADRs are still `Proposed`. See §8 risk R-01.
- **Candidate F — histogram / summary / exponential-histogram metrics.** Requires a contract
  version bump (`contracts/generator/v2/`, or an additive `v1` edit with the schema `version`
  and the generator's `CONTRACT_VERSION` kept in step) under ADR-0008's registry rule
  (`CLAUDE.md` *Conventions*). Not touched. The three bronze tables stay **empty by contract**,
  and flow-ui keeps saying so (`services/flow-ui/src/flow_ui/clickhouse.py:45-49`).
- **Candidate G — the detection spine.** Watchers, the 3-tier cascade, policy engine,
  remediation, audit log, feedback loop. Candidate D delivers the **inputs** those stages read
  and **must not** implement a threshold, a z-score verdict or an escalation. The boundary is
  sharp and is written into REQ-D-07.

### Standing exclusions (repository policy, restated so no leg violates them)

1. **Historical records are not "fixed."** `docs/adr/0*`, `docs/proposals/`, `docs/research/`,
   `docs/clickhouse-schema-divergence*.md`, `.claude/sdd/**` are point-in-time artifacts
   (`.claude/rules/pre-pr-discipline.md`). Candidate I deletes a **live** Compose file, which is
   not a record — §4.I.3 argues that distinction explicitly.
2. **`.claude/` is deleted in the working tree and is being recreated by the owner.** No leg
   writes there. It was read for this spec via `git show HEAD:.claude/...` only.
3. **flow-ui stays a reader.** See DS-05.

---

## 2. Derived standards

No brand guide, security policy or UX standard exists in the repository. The constraints below
are **inferred from what the code already enforces**, each cited. They are binding on this
design; where a standard is genuinely absent, that is stated rather than filled in.

| ID | Inferred standard | Enforced by |
|---|---|---|
| **DS-01** | **No `unsafe`, no `unwrap` in the collector.** `unsafe_code = "forbid"`, `clippy::unwrap_used = "deny"`, `expect_used = "warn"` — and because CI runs `cargo clippy --all-targets --all-features -- -D warnings`, `expect_used` is **effectively deny in CI**. `pedantic`/`nursery`/`missing_docs` are present but **disabled** — aspirational, not a standard (Correction 2). | `services/collector-rust/Cargo.toml:94-104`; `.github/workflows/rust-ci.yml:62` |
| **DS-02** | **Configuration must be auditable, not env-scavenged.** `std::env::var` is a `disallowed-methods` clippy ban. The codebase honours it with exactly **two** sanctioned call sites, both documented in place, both reading `CLICKHOUSE_URL`/`BATCH_SIZE`/`FLUSH_INTERVAL_MS`/`METRICS_PORT`. `std::env::args` is allowed. **Consequence for this design: new configuration goes into the YAML config file, not into env vars** (§4.A.4, §4.H.3). | `services/collector-rust/clippy.toml:10-12`; `src/config.rs:378-394`; `src/clickhouse_exporter.rs:121-141`; `src/main.rs:40` |
| **DS-03** | **Supply chain is gated on licence, advisory and ban — on the Rust path only.** `yanked = "deny"`, an explicit allow-list of 9 permissive licences (copyleft denied by omission), `confidence-threshold = 0.93`, `wildcards = "deny"`, registry restricted to crates.io, advisories ignorable only with an issue link. `Cargo.lock` + `--locked` throughout. **The Python path has no equivalent** — no lockfile, no `pip-audit`, no `bandit`, `>=` floors only. | `services/collector-rust/deny.toml`; `.github/workflows/rust-ci.yml:106-116`; `services/generator-python/pyproject.toml:10-17`; `services/flow-ui/pyproject.toml:6-12` |
| **DS-04** | **Minimal runtime, non-root everywhere.** Collector: fully static musl binary on `gcr.io/distroless/static-debian12:nonroot` — no libc, no shell, no package manager; the Dockerfile states the dependency tree is kept pure-Rust (`cityhash-rs + lz4_flex, no *-sys / OpenSSL / ring`) *precisely so this is possible*. Both Python images create and `USER appuser`. **Corollary the design must absorb: a distroless/static image has no `wget`/`sh`, so the collector cannot carry a Compose healthcheck** — which is why `docker-compose.yml:75` gates flow-ui on `service_started`. | `services/collector-rust/Dockerfile:1-16,60-67`; `services/generator-python/Dockerfile:7,25`; `services/flow-ui/Dockerfile:6,19` |
| **DS-05** | **flow-ui reads, never writes — architectural invariant, not preference.** No write path exists; all eight config/contract bind mounts are `:ro`; the picture is drawn from the files that define the thing (Pod 1's `config/`, the collector's `config.docker.yaml`) so it cannot drift; the browser never reaches ClickHouse or the collector (neither sets a CORS header, pinned by a test); and **nothing in the pipeline depends on flow-ui being up**, which is what makes it safe to break. | `docker-compose.yml:50-75` (esp. 55-57, 62-68); `services/flow-ui/src/flow_ui/clickhouse.py` (read-only client); `core-intent.md §2` |
| **DS-06** | **flow-ui UX standard: server-rendered, no bundler, no front-end framework.** FastAPI + Jinja2 + SSE; the full figure renders server-side before any script runs; ~1.7k lines of plain ES2020 + inline SVG; **no `package.json`**; no CSS value names a colour. Beyond that **there is no UX standard in this repository** — no design tokens doc, no component library, no accessibility statement. `DESIGN.md` / `DESIGN-DIRECTIONS.md` / `ARCHITECTURE.md` are the only written intent. Do not invent one. | `services/flow-ui/pyproject.toml:6-12`; `services/flow-ui/ARCHITECTURE.md`; `core-intent.md §2` |
| **DS-07** | **A drawn band *is* the rule.** On the Watchers board the band around rows/min is the alerting rule, not a picture of one, and the statistics are returned raw so band and threshold are computed in one place. Any migration of those boards must preserve that identity. | `services/flow-ui/src/flow_ui/clickhouse.py:249-253` (docstring) and `pipeline._volume_state` |
| **DS-08** | **`contracts/` is the registry, namespaced by producing Pod; breaking changes bump by directory.** One copy, resolved through `CONTRACTS_DIR`, mounted `:ro`. `generator/v1` = `1.0.0` frozen; `collector/v1` = `1.0.0.1`, Pod 3 sign-off pending. | `CLAUDE.md` *Conventions*; `docker-compose.yml:38,82-84`; ADR-0008 |
| **DS-09** | **Bronze DDL is Pod-3-owned and auto-applies on ClickHouse boot; the collector issues no DDL, only `INSERT`s** (`create_schema:false` — a policy name borrowed from the contrib exporter, *not* a key in the Rust config). Retention lives in the DDL (30-day TTL, `ttl_only_drop_parts = 1`), not in collector config. | `infra/clickhouse/init.d/01-bronze-otel.sql:1-22`; `docker-compose.yml:16-21`; `CLAUDE.md` *Conventions* |
| **DS-10** | **Schema before ingest is a hard requirement.** The silver MVs do not `POPULATE`; the DDL's own header says deploy it *before* enabling ingestion and use an explicit, range- and dedup-controlled backfill for existing bronze. | `infra/clickhouse/init.d/02-silver-layer.sql:7-9` |
| **DS-11** | **Each service keeps its native toolchain; no shared build system.** Three build backends in one repo (setuptools, hatchling, cargo) and that is deliberate. The **Makefile is the single operator interface**, and every target runs in Docker as the invoking UID/GID so **no host toolchain is required**. | `CLAUDE.md` *Conventions*; `Makefile:19`; `services/generator-python/pyproject.toml:1-3`; `services/flow-ui/pyproject.toml:14-16` |
| **DS-12** | **Python lint: ruff only, and unevenly configured.** The generator has `line-length = 120`, `target-version = "py310"`, `select = ["E","F","I","UP"]`. **flow-ui's `pyproject.toml` has no `[tool.ruff]` at all** and no root `pyproject.toml` exists, so `make lint-flow-ui` runs ruff on **defaults** (88 columns, `E`+`F`) over `src tests scripts`. **There is no mypy anywhere in the repository** — zero matches across all `.toml`/`.cfg`/`.ini`/`.yml`. The WoW's `mypy --strict` gate is aspiration, not configuration. | `services/generator-python/pyproject.toml:36-45`; `services/flow-ui/pyproject.toml` (absence); `Makefile:91-95`; repo-wide grep for `mypy` → 0 hits |
| **DS-13** | **Process: Conventional Commits; signed commits (`-S`); a mandatory attribution trailer naming both human and LLM; 2 approvals (peer + Captain); `main` protected.** Agent fleets follow ADR-0009 — *seam → swimlane → leg → task*, one worktree per agent under `.worktrees/`, `leg/<area>/<task>-v<n>`, **every leg declaring disjoint paths before it opens**, squash into the swimlane, merge commit into `main`. The merge-commit rule is `Proposed` / pending ratification. | `README.md` §7; ADR-0009:5; `git show HEAD:.claude/docs/AGENTIC_GITFLOW.md:92-112,180-187,325` |
| **DS-14** | **Per-component CI is path-filtered** so a Python-only or docs-only PR triggers no Rust build; superseded runs are cancelled by `concurrency`. A PR must close an issue (`closingIssuesReferences`, so a bare `#n` does not count), with a `no-issue` label as an attributable escape hatch. | `.github/workflows/rust-ci.yml:20-36`; `.github/workflows/pr-linked-issue.yml` |
| **DS-15** | **No comments-as-noise; match each service's existing style.** In practice the existing style is *long docstrings that carry the measurement that justified the choice* (e.g. `clickhouse.py` records 6.4 s vs 1.26 s for `ARRAY JOIN` vs `countIf`, and a 27.6× join fan-out). That is the house style for a non-obvious decision, and this design is held to it. | `CLAUDE.md` *Conventions*; `services/flow-ui/src/flow_ui/clickhouse.py:180-205,247-271,311-331` |

**One divergence inside the existing standards, worth fixing opportunistically (REQ-B-08):**
`make lint-collector-rust` runs `cargo clippy --locked` **without** `-D warnings`
(`Makefile:99`), while CI runs `-- -D warnings` (`rust-ci.yml:62`). Local lint is therefore
laxer than the gate, and under DS-01 that silently un-denies `expect_used`.

---

## 3. Requirements

MUST / SHOULD / MAY per RFC-2119 sense. Each ID is stable and referenced by §4–§7.

### 3.1 Functional

#### A — deployment gap

| ID | Req | Level |
|---|---|---|
| REQ-A-01 | All three service images MUST be published to a single OCI registry, tagged with the **immutable git SHA** of the commit that built them, plus a mutable channel tag (`:main`, `:vX.Y.Z`). No `:dev` or `:latest` tag in any deployed environment. | MUST |
| REQ-A-02 | Every published image MUST carry a provenance attestation and an SBOM, and MUST be signed. Deployment MUST verify the signature before admitting an image. | MUST |
| REQ-A-03 | CI MUST authenticate to the registry via short-lived federated credentials (OIDC → Workload Identity Federation). No long-lived service-account key may exist in a GitHub secret. | MUST |
| REQ-A-04 | A **versioned ClickHouse DDL migration runner** MUST exist, applying ordered, append-only migration files and recording applied versions in the database. It MUST be idempotent and MUST work against a ClickHouse with no `docker-entrypoint-initdb.d` (i.e. a managed instance). | MUST |
| REQ-A-05 | The existing `init.d` boot path MUST keep working unchanged for the local developer stack (`make up` stays one step; `rust-ci.yml`'s integration job keeps working). | MUST |
| REQ-A-06 | Configuration MUST be delivered as files, not environment variables, per DS-02. Secrets MUST be delivered as mounted files referenced by path from config. | MUST |
| REQ-A-07 | At least two promotion stages (`staging`, `prod`) MUST exist, promoting **the same image digest** — rebuild-on-promote is forbidden. | MUST |
| REQ-A-08 | Infrastructure MUST be declared as code in-repo, with no manual console step in the documented path. | MUST |
| REQ-A-09 | A deploy MUST apply DDL migrations as a distinct step that completes before any ingest workload starts (DS-10). | MUST |
| REQ-A-10 | The compute form and the ClickHouse hosting model MUST NOT be chosen inside an implementation leg; both are ADR decisions (§9 ADR-A1, ADR-A2). Work that is invariant to them MAY proceed first. | MUST |
| REQ-A-11 | flow-ui SHOULD be deployable and un-deployable independently, in any order, with no other component depending on it (DS-05). | SHOULD |
| REQ-A-12 | The collector's readiness MUST be determined without executing anything inside its container (DS-04) — i.e. by an external probe against `:9090/metrics`. | MUST |

#### B — Python CI coverage (issue #34)

| ID | Req | Level |
|---|---|---|
| REQ-B-01 | A path-filtered workflow MUST run ruff over both Python services on every PR touching them, with the same invocation `make lint-generator` / `make lint-flow-ui` uses (DS-11, DS-14). | MUST |
| REQ-B-02 | The same workflow MUST run the generator's unit suite and flow-ui's suite, and MUST fail the PR on any failure. | MUST |
| REQ-B-03 | CI MUST have exactly one definition of how a suite runs. The workflow MUST invoke the Make targets rather than re-declaring pip/pytest invocations. | MUST |
| REQ-B-04 | The 18 silver `throwIf` assertions MUST be executed against a live ClickHouse in CI, reusing the Docker-Compose-service pattern `rust-ci.yml:92-103` already establishes. | MUST |
| REQ-B-05 | The silver-assert job MUST wait for ingest quiescence before asserting, because the assertions are **exact bronze↔silver count equalities** and the collector buffers. | MUST |
| REQ-B-06 | Both Python services MUST be tested at their declared minimum Python version (`>=3.10` generator, `>=3.11` flow-ui), not only at 3.12. | MUST |
| REQ-B-07 | A Python supply-chain job SHOULD run `pip-audit` and `bandit`, closing the DS-03 asymmetry. Findings MAY be warn-only for the first iteration, then promoted. | SHOULD |
| REQ-B-08 | `make lint-collector-rust` MUST be brought to parity with the CI clippy invocation (`-D warnings`). | MUST |
| REQ-B-09 | The static-vs-collected test-count discrepancy MUST be resolved by making **CI output the authoritative number** and updating `README`/`CLAUDE.md` from it — not by re-counting by hand. | MUST |
| REQ-B-10 | The set of **required status checks** MUST be enumerated in the repo and configured on `main`. | MUST |
| REQ-B-11 | The generator's `tests/integration/` suite (6 fns, skip-guarded, needs ClickHouse) SHOULD run in the live-ClickHouse job, not the unit job. | SHOULD |

#### D — silver completion

| ID | Req | Level |
|---|---|---|
| REQ-D-01 | The rolling-stats rollup MUST become **storage-backed** (incrementally maintained) rather than a recompute-on-read `VIEW`, while the name `silver.metric_rollup_1m` and its column contract MUST be preserved for existing readers. | MUST |
| REQ-D-02 | The rollup MUST retain `sample_count`, `sum_value`, `sum_squares`, `min_value`, `max_value` so mean and standard deviation are computable additively over any window — the Tier-1 z-score input, without computing a z-score. | MUST |
| REQ-D-03 | A **Volume** read model MUST exist giving rows-per-minute per producer, keyed so that a time-window filter is index-accelerated. | MUST |
| REQ-D-04 | A **Schema/contract** read model MUST exist giving, per producer per minute, total rows and the count of rows carrying each resource-attribute key. It MUST NOT hard-code the required-key list (see REQ-D-06). | MUST |
| REQ-D-05 | A **call-edge** read model MUST exist giving `src → dst` span and error counts per window. | MUST |
| REQ-D-06 | The required-resource-key list MUST NOT gain a third copy. flow-ui's own copy (`clickhouse.py:39-45`, deliberately duplicated so drift is visible) MUST remain the reader's authority. | MUST |
| REQ-D-07 | No read model may encode a threshold, a band, a verdict, an escalation or a severity. Those are Candidate G. | MUST |
| REQ-D-08 | New silver DDL MUST be additive (`CREATE … IF NOT EXISTS`) and MUST NOT alter the three existing base tables' engine, `ORDER BY` or partition key. | MUST |
| REQ-D-09 | The 18 existing silver assertions MUST still pass unchanged after D. | MUST |

#### E — backfill + flow-ui migration (issue #37)

| ID | Req | Level |
|---|---|---|
| REQ-E-01 | A backfill MUST be **range-controlled** (explicit from/to), and MUST default to a range that excludes the partition currently receiving inserts. | MUST |
| REQ-E-02 | A backfill MUST be **idempotent**: re-running any range MUST leave the target identical, with no duplicated rows, without requiring a dedup key on the target tables. | MUST |
| REQ-E-03 | A backfill MUST produce rows **byte-identical** to those the streaming MV would have produced for the same bronze rows. | MUST |
| REQ-E-04 | A backfill MUST order its phases so that rollups derived from silver base tables are populated **after** those base tables, and MUST NOT assume an MV fires on a partition swap. | MUST |
| REQ-E-05 | A backfill MUST refuse to run and exit non-zero if `silver.*` is absent, if the target structure does not match the staging structure, or if the bronze partition changed mid-run. | MUST |
| REQ-E-06 | flow-ui's three bronze-derived derivations (contract violations, volume bands, call edges) MUST move to silver **without any window of reduced history**. | MUST |
| REQ-E-07 | flow-ui MUST keep tolerating absent `silver.*` (returning `[]`) and MUST additionally tolerate **partially backfilled** silver by falling back to its bronze query when silver's coverage is shorter than the window it needs. | MUST |
| REQ-E-08 | The migration MUST NOT introduce any write from flow-ui, and MUST NOT make the backfill a flow-ui responsibility (DS-05). | MUST |
| REQ-E-09 | The band/threshold identity (DS-07) MUST be preserved: the migrated queries return raw statistics, the band stays computed in `pipeline._volume_state`. | MUST |
| REQ-E-10 | A documented, testable **removal criterion** MUST accompany the dual-source fallback so it does not become permanent. | MUST |

#### H — security hardening

| ID | Req | Level |
|---|---|---|
| REQ-H-01 | The vestigial `otelgen` ClickHouse user and its committed plaintext password MUST be deleted from `infra/clickhouse-init.sql` and from every Compose file. | MUST |
| REQ-H-02 | The `default` user MUST be returned to the image's localhost-only network restriction; `infra/clickhouse-users.d/zz-default-network.xml` MUST be removed. | MUST |
| REQ-H-03 | Three least-privilege ClickHouse roles MUST exist: writer (collector), reader (flow-ui), migrator (DDL + backfill). Grants MUST be the minimum that makes each component's own tests pass. | MUST |
| REQ-H-04 | The reader role MUST include `SELECT` on `system.tables` and `system.columns` — flow-ui queries both. | MUST |
| REQ-H-05 | The collector's config MUST gain `user` and `password_file` for ClickHouse, reading the secret from a file, not an env var (DS-02). | MUST |
| REQ-H-06 | Grants MUST be **proven by CI**, not asserted: the live-ClickHouse jobs MUST connect as the least-privilege roles. | MUST |
| REQ-H-07 | In a deployed environment, all four hops MUST be encrypted in transit: generator→collector, collector→ClickHouse, flow-ui→ClickHouse, flow-ui→collector `/metrics`. | MUST |
| REQ-H-08 | OTLP `:4317` MUST NOT be reachable without authentication in a deployed environment. | MUST |
| REQ-H-09 | Secrets MUST come from a managed secret store, delivered as files, never committed and never passed as a deploy argument. | MUST |
| REQ-H-10 | If TLS is terminated inside the collector process, the resulting dependency change MUST be re-evaluated against DS-04 (static-musl / distroless) and `deny.toml`, and the Dockerfile's purity claim MUST be corrected if it stops holding. | MUST |
| REQ-H-11 | A real-telemetry tripwire SHOULD exist: ingesting a signal whose `sentinel.synthetic` is not `true` changes the compliance position of the whole system (`core-intent.md §5`) and SHOULD be surfaced, not silent. | SHOULD |
| REQ-H-12 | Container image scanning SHOULD gate the registry push. | SHOULD |

#### I — housekeeping

| ID | Req | Level |
|---|---|---|
| REQ-I-01 | Exactly **one** ClickHouse version MUST be pinned across the repository. | MUST |
| REQ-I-02 | Exactly **one** ClickHouse service definition MUST exist as source; any second consumer MUST include it rather than restate it. | MUST |
| REQ-I-03 | `services/collector-rust/infra/docker-compose.yml` MUST keep working for `rust-ci.yml:93,103` — it is load-bearing. | MUST |
| REQ-I-04 | CI's integration ClickHouse MUST mount the **silver** DDL as well as bronze, so the CI instance matches the deployed schema. | MUST |
| REQ-I-05 | The port-8080 collision between `clickstack` and flow-ui MUST be eliminated. | MUST |
| REQ-I-06 | `README.md` is the canonical "how do I run this" document; any Compose file removed MUST have its worked examples preserved in the owning service's README (`.claude/rules/pre-pr-discipline.md` check 2). | MUST |

### 3.2 Non-functional

| ID | Req | Level |
|---|---|---|
| NFR-01 | **The one-dependency setup MUST survive.** Docker + `make`, no host toolchain, every target running as the invoking UID/GID (DS-11). Any new tool ships as a container or a Make target, never as a host prerequisite. | MUST |
| NFR-02 | The collector image MUST remain distroless, static and non-root (DS-04). Any change that would add a shell, a package manager or a dynamic libc requires an ADR. | MUST |
| NFR-03 | No new comment, docstring or README text may restate what the code says; a non-obvious choice carries the measurement that justified it (DS-15). | MUST |
| NFR-04 | flow-ui MUST gain no front-end framework, bundler or `package.json` (DS-06). | MUST |
| NFR-05 | flow-ui's three cadences (1 s `/metrics`, 5 s and 30 s ClickHouse) MUST NOT get more expensive. A migrated query SHOULD be measured against the figure its current docstring records, and the new figure recorded there. | SHOULD |
| NFR-06 | The full PR gate for a Python-only change SHOULD complete in under 10 minutes; the live-ClickHouse e2e job SHOULD complete in under 20. | SHOULD |
| NFR-07 | A backfill of one day's partition SHOULD not degrade concurrent ingest beyond the collector's existing `export_latency` envelope (recorded avg 32.3 ms, 100% of flushes ≤80 ms — `README.md §8`). | SHOULD |
| NFR-08 | No ADR, proposal or research document under the standing exclusions may be edited by any leg in this plan. | MUST |
| NFR-09 | Every commit MUST satisfy DS-13 (Conventional Commits, `-S`, attribution trailer); every leg MUST declare disjoint paths before it opens. | MUST |
| NFR-10 | Secret material MUST NOT appear in the repository, in CI logs, in an image layer, or in a `docker inspect`. | MUST |

---

## 4. Design

### 4.A — Close the deployment gap

#### A.1 The two open decisions, and why I will not pick inside a leg

`core-intent.md §3` records that nothing commits to a compute form, and that **ClickHouse
operational ownership is unassigned** — which it correctly calls the real blocker on
managed-vs-self-hosted. Those are *different* decisions with *different* owners, and the second
is a staffing decision masquerading as a technology one. Both go to ADRs (§9 **ADR-A1**,
**ADR-A2**). What follows is a recommendation with its rationale and its cost, not a fait
accompli.

**Decision matrix — compute form for the three services**

| Criterion | **Cloud Run** | GKE Autopilot | GKE Standard | GCE VMs + Compose |
|---|---|---|---|---|
| Who must own the platform | Google | Google (nodes), us (cluster objects) | us | us |
| Fit: collector (long-running gRPC server) | good — terminates TLS, speaks h2c in; needs `min-instances=1` | good | good | good |
| Fit: generator (`docker compose run --rm`, exits) | **excellent** — Cloud Run Jobs is exactly this shape | Job | Job | cron/systemd |
| Fit: flow-ui (SSE, in-memory `Snapshot`) | good with `min=max=1`; SSE reconnects at the request-timeout ceiling | good | good | good |
| Fit: ClickHouse (stateful, large local disk) | **impossible** | possible (operator + PVs) | possible | possible |
| TLS on hop 1 (REQ-H-07) | **free at the edge** | Ingress/Gateway or mesh | same | ours to build |
| Graceful-shutdown risk to the buffered exporter | real: ~10 s after SIGTERM | configurable `terminationGracePeriodSeconds` | same | none |
| Incremental cost of the platform itself | none | cluster fee + nodes | cluster fee + nodes | VM only |
| New ops surface for a team with no ClickHouse owner | smallest | medium | largest | medium |

**Recommendation — Cloud Run (services + Jobs) for the three Sentinel components, and
*managed* ClickHouse for storage.** The rationale is a single sentence: *the binding constraint
is that nobody owns ClickHouse operationally, so the design should buy ownership where it can
and avoid creating a second unowned platform (a cluster) where it can't.* GKE is the better
answer the moment ADR-A2 assigns an owner and self-hosting is chosen, because then ClickHouse
lives in the cluster and co-locating the collector there removes a network hop.

**What the recommendation gives up, stated plainly:**
- **No mTLS identity inside the collector.** TLS terminates at the Cloud Run edge; the process
  still speaks plaintext h2c. Authentication on `:4317` becomes an edge concern (REQ-H-08) and
  the collector gains no peer identity. On GKE with a mesh it could.
- **Shutdown headroom.** Cloud Run sends SIGTERM and does not wait long. The collector's
  graceful final flush (`README.md §8`) must complete inside that window, which bounds
  `flush_interval_ms` and batch size from above. On GKE this is a tunable field.
- **flow-ui pinned to one instance.** Its `Snapshot` is per-process; two instances would show
  two different histories to two viewers. `min=max=1` is correct and caps it.
- **Managed ClickHouse removes the `init.d` bootstrap entirely** — see A.3. This is the single
  largest consequence of the recommendation and it is *good*: it forces the migration runner
  that `core-intent.md §6` already named as the biggest obstacle to non-destructive deployment.

**Decision matrix — ClickHouse hosting** (ADR-A2; the owner question gates it)

| | Managed (ClickHouse Cloud / equivalent) | Self-hosted on GKE (operator) | Self-hosted on a GCE VM |
|---|---|---|---|
| Needs an assigned ClickHouse owner | no | **yes** | **yes** |
| Backup/restore (today: none at all) | included | ours to build | ours to build |
| `init.d` bootstrap available | **no** → migration runner required | yes | yes |
| Engine | SharedMergeTree substituted for MergeTree **[V-3]** | MergeTree as written | MergeTree as written |
| `REPLACE PARTITION` (the backfill primitive, §4.E) | supported **[V-3]** | supported | supported |
| Forces TLS on the collector's client path | **yes** (HTTPS only) → REQ-H-10 | no | no |
| Cost shape | per-compute + storage, opex | node cost + our time | cheapest, least resilient |

#### A.2 Invariant work — designed now, independent of both decisions

**Registry and tagging (REQ-A-01).** Google Artifact Registry, one repo `sentinel`:

```
REGION-docker.pkg.dev/PROJECT/sentinel/collector-rust:<git-sha>   (+ :main, :vX.Y.Z)
REGION-docker.pkg.dev/PROJECT/sentinel/generator:<git-sha>
REGION-docker.pkg.dev/PROJECT/sentinel/flow-ui:<git-sha>
```

The SHA tag is the only thing a deployment ever names; channel tags are for humans.
`rust-ci.yml:129` (`push: false`) stays as the PR-time build check — pushes happen only from a
new `release.yml` on `push: main` and on tags, so a PR from a fork can never publish.

**Provenance (REQ-A-02).** `docker/build-push-action` with `provenance: mode=max` and
`sbom: true`; cosign keyless signing via the same OIDC identity; Artifact Registry vulnerability
scanning as the gate for REQ-H-12. Deployment verifies the signature. This is the natural
extension of DS-03 from crates to images, and it is the part of A with the least coupling to
anything else — it can land in wave 1.

**Credentials (REQ-A-03).** GitHub OIDC → Workload Identity Federation → a deploy service
account. No JSON key anywhere. This is the first real IAM in the project (`core-intent.md §5`
records that none exists) and so it is also the first thing an ADR should name an owner for.

**Config and secret flow (REQ-A-06, DS-02).** The shape the collector already has is the shape
to keep: a YAML file as `argv[1]`, mounted read-only. So:

```
infra/deploy/config/<env>/collector.yaml      # in repo, reviewed, no secrets
infra/deploy/config/<env>/flow-ui.env          # non-secret settings only
Secret Manager: sentinel-<env>-ch-password     # mounted at /etc/sentinel/secrets/ch_password
collector.yaml: clickhouse: { user: sentinel_collector, password_file: /etc/sentinel/secrets/ch_password }
```

A `password_file` indirection rather than a `password` value is what lets the config file stay
in git under review while the secret never does (NFR-10), and it is the DS-02-shaped answer:
the loader reads it, not `std::env::var`. It requires the Rust config work in REQ-H-05.

**Promotion (REQ-A-07).** `main` → `staging` on every merge; `staging` → `prod` on a tag, by
re-pointing the same digest. Environment differences live only in the per-env config directory
above. No rebuild on promote, so "roll back to the previous version" finally names an artifact —
the gap `core-intent.md §6` closes with "there is no artifact to name".

#### A.3 The keystone: a ClickHouse DDL migration runner (REQ-A-04, A-05, A-09)

This is the piece that A, D, E and I all stand on, and it exists today only as a destructive
`make reset`.

```
infra/clickhouse/migrations/
  0001_bronze_otel.sql          # = today's init.d/01-bronze-otel.sql, byte-identical
  0002_silver_layer.sql         # = today's init.d/02-silver-layer.sql
  0003_silver_watcher_models.sql# Candidate D
infra/clickhouse/migrate.sh     # the runner
```

Runner contract:
1. `CREATE DATABASE IF NOT EXISTS _meta; CREATE TABLE IF NOT EXISTS _meta.schema_migrations
   (version String, applied_at DateTime, checksum String) ENGINE = MergeTree ORDER BY version`.
2. Apply unapplied files in filename order via `clickhouse-client --multiquery`.
3. Record version + SHA-256. On a **re-run with a changed checksum, fail loudly** — migrations
   are append-only; a changed file is a mistake, not an edit.
4. Exit non-zero on any failure; never continue past one.

Implementation choice: **bash + `clickhouse-client`**, not Python. Rationale — it adds zero
dependencies (NFR-01), it is the same mechanism `make test-silver` already uses
(`Makefile:72`), and the identical script runs against a managed endpoint with
`--host/--secure/--password-file`. Cost given up: no rich error handling, and bash date/loop
arithmetic is awkward — which §4.E dodges by asking ClickHouse for the partition list instead
of computing dates in bash.

**Why `init.d` stays (REQ-A-05).** The two paths converge because they execute *the same files*:
`init.d/0*.sql` become symlinks or thin `-- source: migrations/NNNN` includes of the migration
files, so there is one source of DDL and two ways to apply it. The duplication of *mechanism*
is deliberate and the trade is explicit: the local stack keeps its zero-step `make up`
(NFR-01) and `rust-ci.yml:93` keeps working unchanged (REQ-I-03), at the cost of two apply
paths that must be kept in step by the one-source rule.

**Deployed ordering (REQ-A-09):** `migrate` is a Cloud Run Job (or a Kubernetes Job) that must
reach terminal success before the collector revision is promoted. That is DS-10 expressed as a
pipeline step rather than a README warning.

#### A.4 Readiness without a shell (REQ-A-12)

DS-04 means the collector container has no `wget`, so neither Compose nor a Kubernetes `exec`
probe can be used, which is exactly why `docker-compose.yml:75` settles for `service_started`.
The design keeps the invariant and moves the probe outside: an HTTP GET against
`:9090/metrics` from the orchestrator (Cloud Run startup probe / k8s `httpGet`) and, in CI, a
poll loop on the runner (§4.B). No binary is added to the image. flow-ui's existing
`/healthz` becomes its probe — today nothing polls it at all.

---

### 4.B — Python CI coverage (issue #34)

#### B.1 Workflow layout

Two new workflows, path-filtered per DS-14, both reusing `rust-ci.yml`'s `concurrency` block:

**`.github/workflows/python-ci.yml`** — triggers on `services/generator-python/**`,
`services/flow-ui/**`, `contracts/generator/**`, `Makefile`, and itself.

| Job | Matrix | Runs | Gates |
|---|---|---|---|
| `lint` | `{generator, flow-ui}` | `make lint-generator` / `make lint-flow-ui` | REQ-B-01 |
| `test` | `{generator: [3.10, 3.12], flow-ui: [3.11, 3.12]}` | `make test-generator` / `make test-flow-ui` with `PYTHON_IMAGE=python:<v>-slim` | REQ-B-02, B-06 |
| `supply-chain` | `{generator, flow-ui}` | `pip-audit`, `bandit -r src` in a container | REQ-B-07 |
| `docker-build` | `{generator, flow-ui}` | buildx, `push: false`, GHA cache | parity with `rust-ci.yml:119-132` |

**`.github/workflows/e2e-silver.yml`** — triggers on `infra/clickhouse/**`,
`services/collector-rust/**`, `services/generator-python/**`, `Makefile`, and itself.

```
make up                                     # ClickHouse (healthcheck-gated) + collector
poll http://localhost:9090/metrics          # REQ-A-12 / REQ-B-05 — readiness, no exec
make generate SCENARIO=baseline SEED=42 WINDOW=5m
poll until quiescent                        # REQ-B-05 — see B.3
make test-silver                            # the 18 throwIf assertions
make test-generator-integration             # REQ-B-11 (new target)
make down                                   # if: always()
```

#### B.2 One definition, and the price (REQ-B-03)

The workflows **call the Make targets**. The repo's genuine strength is that `make test` and
`make lint` already run everything in Docker as the invoking UID/GID with no host toolchain
(DS-11, `Makefile:19,77-99`); re-declaring pip and pytest invocations in YAML would create a
second definition that drifts — which is the exact failure mode `core-intent.md §2` documents
for nine documents asserting seven non-existent gates.

**Price paid, named:** each `make test-*` target builds a fresh venv inside `python:3.12-slim`
(`Makefile:79,89`), so there is no pip cache and the job pays ~60–90 s of install per matrix
cell. With a 2×2 test matrix that is real but inside NFR-06. Caching it would require either
`setup-python` + `cache: pip` (a second definition — rejected) or a cache mount in the Make
target (a Makefile change that only CI benefits from). **Recommendation: accept the cost now**,
and revisit only if NFR-06 is breached.

**The one Makefile change B needs** is parameterisation, not duplication (REQ-B-06):

```make
PYTHON_IMAGE ?= python:3.12-slim      # new; substituted in test-generator / test-flow-ui
```

Three lines. It makes the declared floors (`>=3.10`, `>=3.11`) testable for the first time —
today both are only ever exercised on 3.12.

#### B.3 Ingest quiescence (REQ-B-05) — the part most likely to flake

The silver assertions are **exact equalities** between bronze and silver counts
(`infra/clickhouse/tests/02-silver-layer.test.sql:16-33`: `silver.operation_executions` ==
`bronze.otel_traces`, `silver.metric_observations` == gauge + sum, `silver.log_events` ==
`bronze.otel_logs`). `make generate` returning does **not** mean the collector has flushed; it
buffers (avg batch 2,775 signals, `README.md §8`). Asserting immediately is a race.

Quiescence check, using only what already exists:

```
read sentinel_signals_ingested_total from :9090/metrics
poll until: it has not changed for 2 consecutive 2s samples
            AND sum(bronze live-table counts) == that total
then assert
```

This is better than a fixed sleep because it tests the *invariant the snapshot claims*
(ingested == persisted, `README.md §8`) and so turns the flake risk into a real assertion. Cap
it at 60 s and fail with both numbers printed.

Two further CI hazards, both read out of the tree:
- **TTL vs the golden fixture.** `services/collector-rust/infra/docker-compose.collector.yml:13-15`
  records that the golden fixture is 2023-dated and its rows are purged on the first background
  merge under the event-time TTL. The e2e-silver job must use `make generate` (now-relative
  timestamps), **not** the golden fixture, or the counts will drift to zero under it.
- **ClickHouse version.** CI's integration ClickHouse is 25.4 while the root stack is 24.3
  (`services/collector-rust/infra/docker-compose.yml:26` vs `docker-compose.yml:7`). Until
  REQ-I-01 lands, `e2e-silver` and `rust-ci/integration` are testing two different engines.
  **This is why I sequences before B's live job stabilises** (§5).

#### B.4 Reconciling the test counts (REQ-B-09)

Static counts, taken now with `grep -rhE '^[[:space:]]*(async )?def test_'`:

| Suite | Static test fns | `parametrize` expansion | Arithmetic collected | `CLAUDE.md` claims |
|---|---|---|---|---|
| generator `tests/unit/` | **169** | 3 fns × 4 (`test_signal_factory.py:131,136,141`) | 169 − 3 + 12 = **178** | **178** ✓ reconciles |
| generator `tests/integration/` | **6** | — | 6 | — |
| flow-ui `tests/` | **71** | 1 fn × 3 (`test_clickhouse.py:57`) | 71 − 1 + 3 = **73** | **63** ✗ does not reconcile |
| collector inline | **92** | — | 92 | 92 ✓ |
| collector `tests/` | **7** (6 `#[ignore]`d) | — | 7 | 4 ✗ (and core-intent says 5 ignored; it is 6) |

Python test **functions** total **246**, matching `core-intent.md §6`. `core-intent.md`'s "175
unit" folded the 6 integration tests in.

flow-ui's 73-vs-63 gap I **could not resolve statically** and did not try to: it could be
class-level skips, collection errors, or a stale number. The requirement is deliberately *not*
"find the right number" — it is **make CI print it and update the docs from that output**.
A hand-maintained count in three documents is the drift machine issue #40 already found.

#### B.5 Required status checks (REQ-B-10)

Proposed required set on `main`, recorded in the repo (a `docs/ci-gates.md` or a README §7
table) so the configuration is reviewable:

`rust-ci / gates` · `rust-ci / integration` · `rust-ci / supply-chain` ·
`rust-ci / docker-build` · `python-ci / lint (×2)` · `python-ci / test (×4)` ·
`python-ci / docker-build (×2)` · `e2e-silver / silver` · `pr-linked-issue`.

`python-ci / supply-chain` starts **non-required** (REQ-B-07 warn-only) and is promoted once its
output is clean — making an unclean new gate required is how a team learns to use `--no-verify`.

Note the path-filter interaction (DS-14): a required check that never triggers blocks the PR
forever on GitHub unless the workflow is declared with the path filter *and* the branch rule
tolerates skipped runs. The implementation must verify this behaviour per check; it is the most
common way this kind of change bricks a repo.

---

### 4.D / 4.E — Silver completion, backfill, and the flow-ui migration

These are designed together because D's deliverables are **exactly** the three things E needs,
and getting that coupling right is what makes E possible without dropping history.

#### D.1 Rolling-stats rollup: keep the name, change the storage (REQ-D-01, D-02)

`silver.metric_rollup_1m` is a plain `VIEW` today (`02-silver-layer.sql:187-209`) — it
recomputes the whole aggregation on every read, and it already carries `sum_squares` (line 197),
i.e. it is already shaped for additive mean/stddev. The design keeps the view as the **stable
interface** and puts an incrementally-maintained table behind it:

```sql
CREATE TABLE IF NOT EXISTS silver.metric_stats_1m
(
    window_start   DateTime,
    scenario       LowCardinality(String),
    service_name   LowCardinality(String),
    component_name LowCardinality(String),
    metric_name    LowCardinality(String),
    metric_kind    Enum8('gauge' = 1, 'sum' = 2),
    sample_count   SimpleAggregateFunction(sum, UInt64),
    sum_value      SimpleAggregateFunction(sum, Float64),
    sum_squares    SimpleAggregateFunction(sum, Float64),
    min_value      SimpleAggregateFunction(min, Float64),
    max_value      SimpleAggregateFunction(max, Float64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (scenario, service_name, metric_name, component_name, metric_kind, window_start)
TTL window_start + toIntervalDay(30) SETTINGS ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.metric_stats_1m_mv TO silver.metric_stats_1m
AS SELECT toStartOfMinute(event_time) AS window_start, scenario, service_name, component_name,
          metric_name, metric_kind,
          count() AS sample_count, sum(value), sum(value*value), min(value), max(value)
   FROM silver.metric_observations GROUP BY ...;
```

`SimpleAggregateFunction` rather than `AggregateFunction` + `-State`/`-Merge` is chosen so
readers need no combinators and the existing view body barely changes: `avg_value` becomes
`sum_value / sample_count` and `stddev_value` becomes
`sqrt(greatest(0, sum_squares/sample_count - pow(sum_value/sample_count, 2)))`. The `greatest(0, …)`
guard is not decoration — catastrophic cancellation on a near-constant series can make that
expression marginally negative, and `stddevPop` in the current view cannot.

**Trade-off given up:** `quantileExact` p50/p95/p99 are **not** additively mergeable, so
`silver.service_health_1m` (`02-silver-layer.sql:211-231`) cannot get the same treatment without
switching to `quantilesTDigestState` and changing the numbers flow-ui draws. **Decision: leave
`service_health_1m` as a view in this cycle.** It is the one flow-ui already reads
(`clickhouse.py:380-387`) and changing percentile semantics under a live board to save query
time nobody has complained about is a bad trade. Recorded as a follow-up, not scope.

**[V-1] Chained materialized views.** `metric_stats_1m_mv` reads `FROM silver.metric_observations`,
which is itself the target of two MVs (`02-silver-layer.sql:143,165`). This design assumes a
materialized view attached to table `T` fires on inserts into `T` *including inserts produced by
another MV writing `TO T`*. I believe that is correct ClickHouse behaviour, but **I did not run
it** (running the stack was out of scope). If it is wrong, every D rollup must read bronze
directly, re-paying the `Map` probing cost the silver layer exists to avoid — a material
redesign. **Verify first, in a throwaway container, before writing any of D.**

#### D.2 The three Watcher read models (REQ-D-03, D-04, D-05)

Each one is designed to be *the thing E migrates onto*, and each solves a concrete problem with
pointing flow-ui's current query at a silver base table.

**(a) Volume — `silver.volume_1m`** (REQ-D-03). The reason flow-ui cannot simply re-aim
`volume_band` at `silver.log_events`: `bronze.otel_logs`'s `ORDER BY (ServiceName,
TimestampDate, TimestampTime)` (`01-bronze-otel.sql:122`) makes its window filter
index-accelerated — the docstring records 0.135 s (`clickhouse.py:260-263`). `silver.log_events`
orders by `(scenario, service_name, component_name, severity_number, event_time, trace_id)`
(`02-silver-layer.sql:91`), so `event_time` is the **fifth** key and a window filter prunes only
to the day. Migrating onto the base table is a measurable regression. A purpose-built rollup
keyed `(service_name, window_start)` is both faster than bronze and correct:

```sql
ENGINE = AggregatingMergeTree PARTITION BY toDate(window_start)
ORDER BY (service_name, window_start)
-- cols: window_start, service_name, signal (Enum: log|trace|metric),
--       rows SimpleAggregateFunction(sum, UInt64)
```

fed by one MV per silver base table. Carrying `signal` keeps `otel_logs`-only semantics
available (which is what `volume_band` uses today) while allowing the other two later.

**(b) Contract/schema — `silver.resource_key_presence_1m`** (REQ-D-04, D-06). The naive
rollup would hard-code the five required keys — and that would quietly destroy a deliberate
property: flow-ui keeps its **own** copy of `REQUIRED_RESOURCE_KEYS`, "duplicated deliberately:
this is the *reader's* copy, and if the two ever disagree the board should show what the
collector is actually enforcing — so the drift is visible rather than silent"
(`clickhouse.py:35-45`). A key list in Pod 3's DDL would be a **third** copy and would make
flow-ui draw Pod 3's opinion instead of its own.

So the rollup is **key-list agnostic**: per producer per minute, store total rows and a map of
counts of keys *present*.

```sql
-- window_start, service_name, signal,
-- rows       SimpleAggregateFunction(sum, UInt64),
-- key_counts SimpleAggregateFunction(sumMap, Map(LowCardinality(String), UInt64))   -- [V-2]
```

MV body: `sumMap(CAST((mapKeys(resource_attributes), arrayResize([toUInt64(1)], length(mapKeys(resource_attributes)))) AS Map(...)))`.
flow-ui then computes `missing[k] = rows - key_counts[k]` from **its own** list — property
preserved, and the expensive unindexed `Map` probe over all four live tables
(1.26 s on ~6 M rows, `clickhouse.py:191-196`) becomes a scan of a tiny rollup.

**[V-2]** `SimpleAggregateFunction(sumMap, Map(K, V))` support is version-dependent. Fallbacks,
in preference order: `AggregatingMergeTree` with `AggregateFunction(sumMap, …)` + `sumMapMerge`
at read; or the older `Tuple(Array(K), Array(V))` form. Verify on the version REQ-I-01 picks.

**(c) Call edges — `silver.call_edges_1m`** (REQ-D-05). **This one cannot be a normal
materialized view, and that is a hard fact, not a preference.** An MV sees only the rows of the
current insert block; a call edge is a self-join between a child span and its parent, which
routinely sit in different blocks and different batches. `clickhouse.py:311-331` documents the
cost of getting the join wrong: joining on `SpanId` alone invented eight non-existent edges
(the seeded RNG repeats ids across runs), and without collapsing parents to one row per
`(TraceId, SpanId)` the window produced 445,229 joined rows from 16,154 children — a 27.6×
fan-out that made edge width encode run history instead of traffic.

Two viable forms:

| | **Refreshable MV** (`REFRESH EVERY 1 MINUTE`) | Scheduled job (the migration runner's sibling) |
|---|---|---|
| Needs a recent ClickHouse | yes — experimental in 24.x, production in later 25.x **[V-3]** | no |
| New moving part | none | a scheduler per environment |
| Atomicity | full replace per refresh | ours to build |

**Recommendation: refreshable MV, conditional on REQ-I-01 landing on a version where it is not
experimental** — which is a direct, concrete reason to converge on the newer ClickHouse rather
than the older one (§4.I.1). If ADR-A2 picks a version where it is experimental, fall back to a
scheduled `INSERT` + partition swap using the same primitive as the backfill (§E.1), which costs
a scheduler but no new concept.

#### D.3 What D must not do (REQ-D-07)

No model carries a threshold, a band, a verdict, a severity or an escalation payload. `volume_1m`
returns rows-per-minute; the band stays in `pipeline._volume_state` (DS-07, REQ-E-09).
`resource_key_presence_1m` returns counts; "violating" is the reader's arithmetic. The Tier-1
z-score consumes `metric_stats_1m` but lives in Candidate G.

#### E.1 Backfill: partition recompute, not dedup (REQ-E-01…E-05)

The structural fact that determines the whole design: **all three silver base tables are plain
`MergeTree` with no dedup key** (`02-silver-layer.sql:37, 89, 137`). A second `INSERT … SELECT`
over the same range double-counts, and the 18 assertions would catch it immediately (they are
exact count equalities).

Three options:

| | **Partition recompute + `REPLACE PARTITION`** | `ReplacingMergeTree` + a version column | `ALTER … DELETE` then `INSERT` |
|---|---|---|---|
| Idempotent | **yes, by construction** | yes, with `FINAL` | yes, eventually |
| Changes existing table DDL | no | **yes — breaking, on live tables** | no |
| Taxes every future reader | no | **yes — `FINAL` or `argMax` forever** | no |
| Atomic | **yes, per partition** | no (merge-eventual) | no (mutation is async) |
| Needs a dedup key | no | yes | no |

**Chosen: partition recompute + `REPLACE PARTITION`.** The reason it is idempotent *by
construction* rather than by bookkeeping is worth stating precisely, because it is the whole
argument: each silver MV body is **row-wise** — a projection of one bronze row to one silver row,
with no aggregation and no join (`02-silver-layer.sql:43-65, 95-114, 143-185`). Therefore
`silver_partition = f(bronze_partition)` is a pure function, and a full recompute of a partition
is correct regardless of what was in it. Nothing needs to know whether a previous run half-finished.

Per `(table, partition)`:

```sql
CREATE TABLE IF NOT EXISTS silver.operation_executions__bf AS silver.operation_executions;
INSERT INTO silver.operation_executions__bf
  <the MV's SELECT verbatim> WHERE toDate(Timestamp) = {d};          -- REQ-E-03
-- guard: bronze partition count unchanged since the SELECT began    -- REQ-E-05
ALTER TABLE silver.operation_executions REPLACE PARTITION {d} FROM silver.operation_executions__bf;
ALTER TABLE silver.operation_executions__bf DROP PARTITION {d};
```

`CREATE TABLE … AS` guarantees the structural identity `REPLACE PARTITION` requires (same
columns, engine, `ORDER BY`, partition key). `silver.metric_observations` takes **two** inserts
into the same staging partition (gauge then sum) before the single swap.

**Range control (REQ-E-01).** The partition list comes from ClickHouse, not from bash date
arithmetic:

```sql
SELECT DISTINCT partition FROM system.parts
WHERE database='bronze' AND table={t} AND active AND partition >= {from} AND partition <= {to}
ORDER BY partition
```

Default `to` = yesterday. **The live partition is the MV's, not the backfill's.** Note the
partition-granularity mismatch: `bronze.otel_logs` partitions by `toYYYYMM(TimestampDate)`
(`01-bronze-otel.sql:121`) while `silver.log_events` partitions by day
(`02-silver-layer.sql:90`) — so the logs backfill iterates *silver* days and filters bronze by
date, rather than mapping partition to partition. Getting this backwards would swap a day into a
month-shaped slot and is the most likely single implementation bug.

**The race, stated honestly (REQ-E-05).** Between the staging `SELECT` and the swap, a
late-arriving signal with that day's event timestamp can be MV-inserted into the target
partition and then destroyed by the swap. The window is sub-second; the guard (compare the
bronze partition's `count()` before and after) is a **heuristic, not a lock** — ClickHouse offers
no transaction that would make it airtight. The only sound version is pausing ingest for the
live partition. **Recommendation: backfill closed partitions only, with the guard; pause ingest
if the live partition must be backfilled.** Do not claim more than that.

**Phase ordering (REQ-E-04) — the detail most likely to be missed.** **Materialized views fire
on `INSERT`, not on `ALTER … REPLACE PARTITION`.** So a partition swap into `silver.log_events`
does **not** populate `silver.volume_1m`. The backfill is therefore two phases:

```
phase 1: bronze.*  →  silver.operation_executions | log_events | metric_observations   (swap)
phase 2: silver base  →  metric_stats_1m | volume_1m | resource_key_presence_1m         (swap)
         (call_edges_1m is refresh-driven and needs no backfill — its refresh recomputes)
```

Running phase 2 before phase 1 completes yields a rollup over partial data that looks perfectly
healthy. The runner must enforce the order and refuse to run phase 2 for a partition phase 1
has not recorded.

**Form.** `infra/clickhouse/backfill/backfill.sh` + per-table SQL templates, exposed as
`make backfill-silver FROM=YYYY-MM-DD TO=YYYY-MM-DD [PHASE=1|2|all]`. Bash + `clickhouse-client`,
same rationale as A.3. It is an `infra/` artifact, not a service — so it touches no service's
toolchain (DS-11) and **flow-ui is not involved at all** (REQ-E-08, DS-05).

#### E.2 Migrating flow-ui's three boards without a history gap (REQ-E-06, E-07, E-10)

Issue #37's constraint is that the three bronze-derived derivations depend on history the
non-`POPULATE`ing MVs never saw — `clickhouse.py:362-376` records the measurement:
`bronze.otel_traces` held 1,703,050 rows over 36 hours while `silver.operation_executions` held
12,849 over 12 minutes. A flag-day switch loses 36 hours of the Watchers board.

**Design: coverage-checked dual source, not a flag day.** flow-ui gains one cheap probe and each
of the three methods gains a silver path beside its bronze path:

```
silver_coverage()  ->  min(event_time) per silver base table   (one 30s-cadence query)
for each of {contract_violations, volume_band, call_edges}:
    if silver covers the window this board needs  -> read the silver rollup
    else                                          -> read bronze, as today
```

This is the posture flow-ui already has, extended: its silver reader "returns `[]` when
`silver.*` is absent, which is the normal state of any stack whose volume predates the merge"
(`clickhouse.py:375-377`). Coverage-checking generalises *absent* to *insufficient* and needs no
new table and no backfill bookkeeping — so flow-ui still derives its picture from the state of
the thing it draws (DS-05), rather than from a flag someone has to remember to flip.

**What this gives up:** both query paths live in the code for a release, roughly doubling the
surface of the three most carefully-reasoned methods in `clickhouse.py` — each of which carries
a measured justification in its docstring (DS-15). That is the cost of REQ-E-06, and it is why
REQ-E-10 demands a removal criterion:

> **Removal criterion.** The bronze path for a board is deleted in the first PR after
> `min(event_time)` in the backing silver table has been ≤ `now() - 30 days` (the TTL horizon,
> `01-bronze-otel.sql:63`) continuously for 7 days in the target environment — i.e. silver can
> no longer be shorter than bronze, because both are TTL-bounded to the same window. At that
> point the fallback is dead code and `clickhouse.py` loses three branches.

NFR-05 applies: each migrated query's docstring must carry the **new** measurement beside the
old one, in the existing house style. I cannot produce those numbers statically.

---

### 4.H — Security hardening

#### H.1 What is doable now, locally, with no deployment

These three land together as one atomic change (they are mutually breaking) and are **independent
of A**:

1. **Delete the `otelgen` user** (REQ-H-01) — `infra/clickhouse-init.sql:15-17` creates it
   `IDENTIFIED WITH plaintext_password BY 'otelgen_secret'` with `ALL ON bronze.*` **and**
   `ALL ON default.*`, and the file itself says it is vestigial and safe to drop. The same
   credential is hard-coded at `services/generator-python/docker-compose.yaml:16-17,63` — which
   §4.I.3 deletes.
2. **Revert `default` to localhost-only** (REQ-H-02) — delete
   `infra/clickhouse-users.d/zz-default-network.xml` (whose `<networks replace="replace"><ip>::/0</ip>`
   is the single most load-bearing security assumption in the baseline) and drop its mount at
   `docker-compose.yml:15`.
3. **Create three roles** (REQ-H-03, H-04) in a migration, not an init script:

| Role | Grants | Why exactly this |
|---|---|---|
| `sentinel_collector` | `INSERT ON bronze.*` | DS-09: the collector issues no DDL and reads nothing |
| `sentinel_reader` | `SELECT ON bronze.*`, `SELECT ON silver.*`, `SELECT ON system.tables`, `SELECT ON system.columns` | flow-ui queries `system.tables` (`clickhouse.py:428-429, 501-503`) and `system.columns` (`:505`) to draw the silver graph — omit these and the Flow board silently loses its fourth box |
| `sentinel_migrator` | DDL on `bronze`/`silver`/`_meta` + `SELECT`/`INSERT`/`ALTER` for the backfill | migration runner and backfill only |

Steps 2 and 3 break the collector unless it can authenticate, so REQ-H-05 (`clickhouse.user` +
`clickhouse.password_file` in `src/config.rs` / `src/clickhouse_exporter.rs`) ships in the same
swimlane. That is **two legs with disjoint paths** (`infra/` + compose; `services/collector-rust/src/`)
that must merge **together** — exactly the shape ADR-0009's swimlane exists for.

**Grants proven, not asserted (REQ-H-06).** The CI jobs connect as `sentinel_collector` /
`sentinel_reader`. If a grant is missing, the integration or e2e-silver job fails. I am
deliberately *not* claiming the grant lists above are complete — the Rust exporter may touch
`system.*` for its table check. The design makes CI the oracle instead of me.

#### H.2 TLS per hop — and the dependency it threatens

| Hop | Today | Design | Depends on |
|---|---|---|---|
| generator → collector `:4317` | plaintext gRPC, `[::]:4317`, zero TLS code (grep for `tls`/`ServerTlsConfig`/`certificate` in `src/grpc.rs`, `src/config.rs`, `src/clickhouse_exporter.rs` → 0 hits) | **Terminate at the platform edge.** The generator already has `--otlp-secure`, `--otlp-api-key`, `--otlp-header` (`src/otelgen/cli.py`), so the client side needs no code | ADR-A1 |
| collector → ClickHouse `:8123` | plaintext HTTP, passwordless `default` | HTTPS + `user`/`password_file`. **Forced, not optional, if ADR-A2 picks managed ClickHouse** | ADR-A2, REQ-H-05 |
| flow-ui → ClickHouse | plaintext HTTP | `https://` + `sentinel_reader`; `httpx` needs no code change | ADR-A2 |
| flow-ui → collector `/metrics` | plaintext HTTP | platform-internal TLS or stay inside the trust boundary | ADR-A1 |

**REQ-H-10 is the sharp edge.** `services/collector-rust/Dockerfile:3-6` states the dependency
tree is pure Rust — "cityhash-rs + lz4_flex, no `*-sys` / OpenSSL / ring" — and that this is
*why* a fully static musl binary on distroless is achievable (DS-04, NFR-02). Adding TLS to the
collector means adding a TLS implementation, and `rustls` pulls a crypto provider (`ring` or
`aws-lc-rs`), neither of which is pure Rust.

- **Hop 1 (server TLS): avoided entirely** by terminating at the edge — a concrete reason the
  Cloud Run recommendation is cheaper than it looks.
- **Hop 2 (client TLS): cannot be avoided** if ClickHouse is managed. The resolution is to enable
  the `clickhouse` crate's rustls feature, verify the musl-static build **on both `x86_64` and
  `aarch64`** (the recorded E2E snapshot is arm64 — `README.md §8`, so the team's own machines
  hit this first), re-run `cargo deny` against the new licences (DS-03: `ring` is
  `ISC AND MIT AND OpenSSL`-ish and may need an `allow` addition — a deliberate, reviewed
  `deny.toml` change, not a bypass), and **correct the Dockerfile comment**, which otherwise
  becomes a false claim in the repo's strongest security artifact.
- Alternative considered and rejected: a TLS-terminating sidecar so the collector stays
  plaintext. Preserves purity exactly; costs a second image, a second config and a second thing
  to patch — disproportionate for one outbound HTTPS client.

#### H.3 Secrets (REQ-H-09) and the real-telemetry tripwire (REQ-H-11)

Secret Manager → mounted file → referenced by path from the YAML config (§4.A.2). No secret in
git, in a layer, in `docker inspect`, or in an env var (DS-02, NFR-10). Local dev keeps a
gitignored file under `infra/secrets/` with a committed `.example`.

REQ-H-11 deserves its own note because `core-intent.md §5` makes the point well: the baseline's
strongest compliance fact is that *all data is synthetic*, and **nothing in the current design
would flag the transition**. Every signal already carries `sentinel.synthetic`, surfaced as
`is_synthetic Bool` in `silver.operation_executions` (`02-silver-layer.sql:20,51`). The tripwire
is therefore nearly free: a non-synthetic row in silver is a one-predicate check. It belongs in
this cycle precisely because it is cheap now and unaffordable to retrofit after the swap.

#### H.4 Sequencing H against A

- **H.1 (users, grants, collector auth) — now.** No deployment needed; it is the highest
  value-per-line item in the whole plan and it removes a committed plaintext credential.
- **H.2/H.3 (TLS, secret store, edge auth) — after ADR-A1/A2.** "Enable TLS" has no meaning
  without a terminator, and "mount from Secret Manager" has no meaning without a runtime. Doing
  these before the compute form is chosen builds for a platform that may not be picked.

---

### 4.I — Housekeeping with real drift risk

#### I.1 One version (REQ-I-01)

Three ClickHouse definitions on two versions: root `24.3` (`docker-compose.yml:7`), CI's
integration `25.4` (`services/collector-rust/infra/docker-compose.yml:26`), generator's `24.3`
(`services/generator-python/docker-compose.yaml:10`) plus `clickstack-all-in-one:latest`'s
bundled one (`:39`). **CI tests the bronze DDL on an engine the local stack does not run.**

**Converge on 25.4** (or the newest pinned minor the hosting choice supports). Reasons, in order:
CI already runs it, so it is the more-tested of the two; it unlocks production-grade refreshable
materialized views, which §4.D.2(c) needs for `call_edges_1m` **[V-3]**; and if ADR-A2 picks
managed ClickHouse, the local stack should not be older than the deployed one. Cost: a
`make reset` (the volume cannot be upgraded in place for a changed DDL anyway — `CLAUDE.md`
*Gotchas*), and re-verification of the 18 assertions on 25.4, which `e2e-silver` does
automatically. All data is synthetic, so the reset costs nothing.

#### I.2 One definition (REQ-I-02, I-03, I-04)

`services/collector-rust/infra/docker-compose.yml` is **load-bearing** — `rust-ci.yml:93,103`
start and tear down the integration ClickHouse from it. It is not deleted. Instead the drift is
removed at the source:

```
infra/clickhouse/compose.clickhouse.yml     # NEW: the single ClickHouse service definition
docker-compose.yml                          # include: it, add collector / flow-ui / generator
services/collector-rust/infra/docker-compose.yml
                                            # include: it — keeps its path, keeps CI working
```

Compose `include:` requires Compose v2.20+, already implied by the repo's Compose-v2 baseline
(`core-intent.md §4`) — **verify before relying on it**; the fallback is `extends:` per service,
which is older and more verbose but equivalent here.

Two bugs the single definition fixes by construction:
- REQ-I-04: the CI ClickHouse mounts **only** bronze today (`:34`), so the silver DDL is never
  exercised by `rust-ci.yml` at all.
- The CI ClickHouse sets `CLICKHOUSE_USER: default` + `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1`
  (`:37-39`). The entrypoint's generated user file is what lets the CI test reach it from the
  runner — i.e. **there is a second, undocumented route to the `::/0` posture** besides
  `zz-default-network.xml`. REQ-H-02 must close both, or deleting the XML will look like it
  worked while CI keeps running wide open.

#### I.3 `services/generator-python/docker-compose.yaml` — delete it (REQ-I-05, I-06)

What it contains: a 24.3 ClickHouse with the `otelgen`/`otelgen_secret` plaintext credentials
(`:10,15-17`), the generator wired to those credentials (`:60-64`), and `clickstack-all-in-one`
publishing **`8080:8080`** (`:41`) — the same host port as flow-ui (`docker-compose.yml:70`), so
the two stacks cannot coexist.

**Is this a historical record protected by the standing exclusion?** No, and the distinction
matters. The exclusion covers `docs/adr/0*`, `docs/proposals/`, `docs/research/`,
`.claude/sdd/**` — documents that *assert the past* and carry superseded banners
(`.claude/rules/pre-pr-discipline.md`). A Compose file **asserts the present**: it is an
executable claim about how to run the system, it carries no banner, and `core-intent.md §2`
flags it as a drift hazard precisely because nothing marks it superseded. Deleting it is in
policy; editing an ADR would not be.

**Delete, and preserve what it taught (REQ-I-06):** `services/generator-python/README.md:457`
already promises a root-level Compose for the full stack — which now exists — and the two worked
invocations in the comments (`--delivery direct --init-schema`, and the HyperDX OTLP target with
an ingestion key) move into that README as documentation. No code is touched: `--delivery direct`
stays in the CLI (`src/otelgen/cli.py:70,268-270`) and `OTELGEN_OTLP_API_KEY` stays a capability.

Alternative considered: keep it, strip the credentials, move HyperDX to `8081`, add a superseded
banner. Rejected — it leaves a third ClickHouse definition alive to drift again, which is the
problem Candidate I exists to end. Flagged as an owner decision in §9 (ADR-I1) only because
deleting a file someone may be using is a social act, not a technical one.

`services/collector-rust/infra/docker-compose.collector.yml` (the fourth file,
`core-intent.md` does not mention it) is a Day-7 golden-fixture overlay with no ClickHouse. It is
unreferenced by CI and by any Make target. **Leave it.** It documents the FILE-mode path and its
TTL caveat (`:13-15`), which §4.B.3 depends on. Deleting it is churn with no drift payoff.

---

## 5. Sequencing & dependencies

### 5.1 Dependency graph

```
                        ┌──────────────── W0: DECISIONS (no code) ───────────────┐
                        │ ADR-A1 compute form                                    │
                        │ ADR-A2 ClickHouse hosting + operational OWNER          │
                        │ ADR-A3 migration tooling (bespoke runner vs off-shelf) │
                        │ ADR-I1 ClickHouse version + delete generator compose   │
                        └───┬──────────────────────┬─────────────────────────────┘
                            │                      │
 ┌──────────────────────────┼──────────────────────┼───────────────────────────────┐
 │ W1 (parallel)            │                      │                               │
 │  B  python-ci + e2e-silver ◀── soft: easier after I                             │
 │  I+H1  compose unify · version pin · drop otelgen · 3 roles                     │
 │         └─ leg I/H1-a infra+compose   leg I/H1-b collector src (user/pwd_file)  │
 │  MIG   migration runner (REQ-A-04/05)  ◀── ADR-A3                               │
 │  A-inv registry · provenance · OIDC · release.yml   ◀── ADR-A1 only for deploy  │
 └──────────┬──────────────────┬────────────────────────────┬──────────────────────┘
            │                  │                            │
            ▼                  ▼                            ▼
   ┌─────────────────┐  ┌──────────────────┐      ┌─────────────────────┐
   │ W2  D silver    │  │ W2  A-compute    │      │ (gated on MIG + D)  │
   │  stats_1m       │  │  IaC · envs ·    │      │                     │
   │  volume_1m      │  │  deploy pipeline │      │                     │
   │  key_presence   │  │  ◀── ADR-A1/A2   │      │                     │
   │  call_edges_1m  │  └────────┬─────────┘      │                     │
   └────────┬────────┘           │                └─────────────────────┘
            ▼                    │
   ┌─────────────────────────┐   │
   │ W3  E backfill          │   │
   │  phase1 · phase2        │   │
   │  flow-ui dual-source    │   │
   └────────┬────────────────┘   │
            │                    ▼
            └────────▶ ┌──────────────────────────────────┐
                       │ W4  H2/H3  TLS · secrets · edge  │
                       │     auth · image scanning        │
                       └──────────────────────────────────┘
```

**Hard blocks**
- `ADR-A1` → A-compute, H2 (nothing to terminate TLS at), REQ-A-12's probe form.
- `ADR-A2` → whether the collector needs client TLS at all (REQ-H-10), and MIG's necessity.
- `ADR-A3` → MIG's form. MIG → D's non-destructive application on existing volumes, and E in
  deployed environments.
- `ADR-I1` → I. I → the version everything else is tested on.
- **D → E, strictly.** E migrates onto D's three read models; there is nothing to migrate to
  before D.
- **E phase 1 → E phase 2**, enforced in the runner (REQ-E-04).
- `H1` → `H2`: roles must exist before TLS/secret delivery means anything.
- **[V-1] must be verified before any of D is written.**

**Genuinely parallel:** B · I+H1 · MIG · A-inv. Four lanes in W1.

**Soft blocks (ordering preference, not a dependency):** B's `e2e-silver` job is more stable
after I (one engine version, silver mounted in CI). Design B to call only Make targets and it
survives either order — which is REQ-B-03's second payoff.

**Near-cycle, called out:** A-compute wants TLS (H2); H2's shape depends on A-compute. Broken by
putting the *decision* in W0 and both *implementations* downstream. If ADR-A1/A2 stall, A-inv
still ships and H1 still ships; A-compute and H2 stall together.

### 5.2 Legs and declared paths (ADR-0009, DS-13)

Every leg declares disjoint paths before it opens. Within a wave, every cell below is disjoint
from every other cell in that wave.

**Wave 1**

| Leg | Declared paths |
|---|---|
| `leg/ci/python-gates-v1` | `.github/workflows/python-ci.yml`, `.github/workflows/e2e-silver.yml`, `docs/ci-gates.md` |
| `leg/infra/clickhouse-unify-v1` | `infra/clickhouse/compose.clickhouse.yml`, `infra/clickhouse-init.sql`, `infra/clickhouse-users.d/**`, `docker-compose.yml`, `services/collector-rust/infra/docker-compose.yml`, `services/generator-python/docker-compose.yaml` (deletion), `services/generator-python/README.md` |
| `leg/collector/ch-auth-v1` | `services/collector-rust/src/config.rs`, `services/collector-rust/src/clickhouse_exporter.rs`, `services/collector-rust/config.docker.yaml` |
| `leg/infra/ch-migrate-v1` | `infra/clickhouse/migrations/**`, `infra/clickhouse/migrate.sh`, `infra/clickhouse/init.d/**` |
| `leg/release/registry-provenance-v1` | `.github/workflows/release.yml`, `infra/deploy/README.md` |
| **Makefile owner this wave** | `leg/ci/python-gates-v1` (adds `PYTHON_IMAGE`, `test-generator-integration`, REQ-B-08's `-D warnings`) |

**Wave 2**

| Leg | Declared paths |
|---|---|
| `leg/silver/watcher-models-v1` | `infra/clickhouse/migrations/0003_silver_watcher_models.sql`, `infra/clickhouse/tests/03-watcher-models.test.sql`, `infra/clickhouse/queries/03-watcher-sample.sql` |
| `leg/deploy/<platform>-v1` | `infra/deploy/**` (excluding `README.md`), per-env config dirs |
| **Makefile owner this wave** | `leg/silver/watcher-models-v1` |

**Wave 3**

| Leg | Declared paths |
|---|---|
| `leg/silver/backfill-v1` | `infra/clickhouse/backfill/**` |
| `leg/flow-ui/silver-boards-v1` | `services/flow-ui/src/flow_ui/clickhouse.py`, `services/flow-ui/src/flow_ui/pipeline.py`, `services/flow-ui/tests/test_clickhouse.py`, `services/flow-ui/tests/test_pipeline.py`, `services/flow-ui/ARCHITECTURE.md` |
| **Makefile owner this wave** | `leg/silver/backfill-v1` (adds `backfill-silver`) |

**Wave 4**

| Leg | Declared paths |
|---|---|
| `leg/security/transport-v1` | `services/collector-rust/Cargo.toml`, `Cargo.lock`, `deny.toml`, `Dockerfile`, `src/grpc.rs` |
| `leg/security/secrets-v1` | `infra/deploy/secrets/**`, per-env config |

### 5.3 The disjointness problem, stated rather than hidden

**ADR-0009's disjoint-paths rule cannot be satisfied for four hot files**, and pretending
otherwise is how this plan would actually fail:

| File | Wanted by |
|---|---|
| `Makefile` | B (`PYTHON_IMAGE`, integration target, `-D warnings`), E (`backfill-silver`), MIG (`migrate`), I (compose paths) |
| `docker-compose.yml` | I, H1, A |
| `README.md` | every candidate (pre-PR-discipline check 2 obliges each one to update what it invalidated) |
| `CLAUDE.md` | B (test counts), D (silver), I (compose), H (auth gotchas) |

**Resolution:** one named owner per wave for each hot file (the tables above do this for
`Makefile`); `README.md` and `CLAUDE.md` are edited **only** in a single docs leg at the end of
each wave, which collects the invalidated claims from that wave's legs. The cost is that doc
updates lag their code by one leg — which violates the letter of
`.claude/rules/pre-pr-discipline.md` ("fix the ones that do not hold **in the same PR**"). That
is a real conflict between two repo rules, and it needs the Captain's call, not mine. It is
ADR-I2 in §9.

---

## 6. Testing strategy

| Candidate | Test | Proves | Where |
|---|---|---|---|
| A | `migrate.sh` applied twice over a fresh ClickHouse → identical `_meta.schema_migrations`, no error | REQ-A-04 idempotence | new `e2e-silver` step |
| A | A migration file edited after being applied → runner **fails** on checksum | A-04 append-only | unit-ish shell test |
| A | `make up` unchanged after `init.d` is re-pointed at `migrations/` | REQ-A-05 | `e2e-silver` |
| A | `rust-ci / integration` still green after I.2's `include:` | REQ-I-03 | existing job |
| A | A deploy pipeline dry-run rejects an unsigned digest | REQ-A-02 | release workflow test job |
| A | Promotion moves a digest without rebuilding (compare digests pre/post) | REQ-A-07 | release workflow |
| B | `python-ci / lint` fails on an injected ruff violation | REQ-B-01 | PR check |
| B | `python-ci / test` fails on an injected assertion failure | REQ-B-02 | PR check |
| B | Matrix runs 3.10 and 3.11 and both pass | REQ-B-06 | PR check |
| B | `e2e-silver` runs all 18 `throwIf`s and reports counts on failure | REQ-B-04 | new job |
| B | Quiescence loop times out loudly rather than asserting early | REQ-B-05 | inject a stalled collector |
| B | CI prints collected counts; `README`/`CLAUDE.md` match that output | REQ-B-09 | job summary + review |
| D | The existing 18 assertions pass unchanged | REQ-D-09 | `make test-silver` |
| D | `sum(sample_count) FROM silver.metric_rollup_1m == count() FROM silver.metric_observations` **after** the view is re-pointed at `metric_stats_1m` | REQ-D-01/D-02 — this assertion already exists (`02-silver-layer.test.sql:47-51`) and becomes the regression guard for D's whole storage swap | `make test-silver` |
| D | `stddev` from `sum_squares` matches `stddevPop` on the same rows to 1e-9 | REQ-D-02 numerics | new `03-watcher-models.test.sql` |
| D | `volume_1m` row totals == `log_events` row totals per producer | REQ-D-03 | new asserts |
| D | `key_counts[k] <= rows` for every k; and `rows - key_counts['service.name']` equals the bronze `countIf(NOT mapContains(...))` | REQ-D-04 | new asserts |
| D | `call_edges_1m` contains no `src == dst` edge and no edge absent from `topology/default.yaml`'s declared DAG | REQ-D-05 + the 8-phantom-edge regression `clickhouse.py:318-324` records | new asserts |
| D | grep: no threshold/severity literal in `0003_silver_watcher_models.sql` | REQ-D-07 | review + a lint assert |
| E | Backfill one partition twice → counts identical; assertions still exact | **REQ-E-02, the central property** | new `make test-backfill` in `e2e-silver` |
| E | Backfilled partition's rows are row-for-row equal to MV-produced rows for the same bronze range (checksum both) | REQ-E-03 | new test |
| E | Phase 2 refuses a partition phase 1 has not recorded | REQ-E-04 | runner test |
| E | Runner exits non-zero when `silver` absent / structure mismatch / bronze count changed | REQ-E-05 | runner test |
| E | flow-ui returns `[]` with `silver.*` absent (existing behaviour, must not regress) | REQ-E-07 | `test_clickhouse.py` |
| E | flow-ui picks bronze when coverage < window, silver when ≥; both paths asserted | REQ-E-07 | new pytest with two fake responses |
| E | Band numbers identical from either source for the same data | REQ-E-09, DS-07 | `test_pipeline.py` |
| E | grep: no `INSERT`/`ALTER`/`CREATE` in `flow_ui/**` | REQ-E-08, DS-05 | new pytest (cheap, permanent) |
| H | CI's integration + e2e jobs connect as `sentinel_collector` / `sentinel_reader` and pass | **REQ-H-06 — grants proven, not assumed** | both live jobs |
| H | `sentinel_reader` cannot `INSERT` (expect a permission error) | REQ-H-03 | new assert |
| H | flow-ui's silver graph still renders as `sentinel_reader` (the `system.tables`/`system.columns` grant) | REQ-H-04 | `e2e-silver` + a flow-ui smoke |
| H | grep over the tree for `otelgen_secret` → 0 hits | REQ-H-01 | CI assert |
| H | ClickHouse rejects a non-localhost connection as `default` | REQ-H-02 — and this must be checked against **both** routes (the XML *and* the `CLICKHOUSE_USER` entrypoint path, §4.I.2) | `e2e-silver` |
| H | `cargo build --release --target *-musl` succeeds on x86_64 **and** aarch64 after the TLS feature; `cargo deny check` passes | REQ-H-10, NFR-02 | `rust-ci` + a buildx matrix |
| H | A non-synthetic row in silver is detected | REQ-H-11 | new assert |
| I | Exactly one `image: clickhouse/clickhouse-server:` string in the tree | REQ-I-01 | CI grep assert |
| I | No two Compose files publish host `8080` | REQ-I-05 | CI grep assert |
| I | CI's ClickHouse has both `bronze` and `silver` databases | REQ-I-04 | `rust-ci / integration` |

Three of these are **grep assertions in CI** (no `INSERT` in flow-ui; one ClickHouse version; no
`otelgen_secret`). They are cheap, they never flake, and each encodes an invariant that was
previously only a convention — which is the pattern that would have caught the drift issue #40
found.

---

## 7. Rollout & rollback

| Candidate | Rollout | Rollback |
|---|---|---|
| **A — invariant parts** | `release.yml` on `push: main` pushes SHA-tagged, signed images. Additive; nothing consumes them yet, so the first weeks are provenance accumulating with no risk. | Revert the workflow. Published images are immutable and harmless. |
| **A — migration runner** | Add `migrations/` + `migrate.sh`; re-point `init.d` at the same files; prove `make up` and `rust-ci / integration` unchanged **before** anything depends on it. | Revert; `init.d` returns to standalone files. No data touched (all DDL is `IF NOT EXISTS`). |
| **A — compute** | **Partly undefined until ADR-A1.** Invariant to the choice: DDL migration job → collector → generator job → flow-ui last (REQ-A-11, DS-05). Variant: whether "roll" means a Cloud Run revision split, a k8s rolling update, or `docker compose up` on a VM. **Blue/green, canary and rolling cannot be chosen before the orchestrator is** — `core-intent.md §6` is right about that and this spec does not pretend otherwise. | Re-point the previous image digest (REQ-A-01/A-07 is what makes this possible for the first time). **DDL rollback is the unsolved half**: a forward-only runner has no `down` step. The honest position is that bronze/silver changes in this cycle are **additive only** (REQ-D-08), so rollback is "deploy the old image against the new schema", which works for additive DDL and for nothing else. A genuine down-migration story is out of scope and should be an ADR when the first destructive change is proposed. |
| **B** | Land both workflows **non-required**; watch one week of real PRs; then set required (REQ-B-10). Promoting a gate before its flake rate is known is how teams learn to bypass gates. | Un-require the check; delete the workflow. Zero runtime impact. |
| **D** | DDL is additive (`IF NOT EXISTS`, new objects only, REQ-D-08). On a fresh volume it arrives via `init.d`; on an existing one via `migrate.sh`. The rollups are empty until ingest or E runs — and **that empty state is correct and visible**, not a failure. | `DROP` the new objects; re-point `metric_rollup_1m` at its original `VIEW` body. No existing table altered, so nothing to undo. |
| **E** | **Per-partition, oldest first, closed partitions only.** Observe one partition end to end before the loop. flow-ui needs no deploy coordination: the coverage check flips each board over on its own as coverage grows, so there is no cutover moment and no history gap (REQ-E-06). | **Per-partition and genuinely safe**, which is the design's main virtue: a bad partition is re-swapped from a corrected recompute, because the content is a pure function of bronze (§4.E.1). flow-ui falls back to bronze automatically while silver coverage is short. The irreversible case is a backfill of the **live** partition racing the MV — hence REQ-E-01's default excluding it. |
| **H1** | One atomic change: drop `otelgen`, remove the `::/0` override, create roles, collector gains `user`/`password_file`. **Requires `make reset`** (the users live in init/migrations, and the existing volume has the old grants). Synthetic data; no cost. | Revert the commit + `make reset`. The reverted state is the current, known-working one. |
| **H2/H3** | After A. TLS per hop, one hop at a time, outermost first (edge → collector→CH → flow-ui reads). | Per hop: disable the `tls`/`secure` setting in the per-env config and redeploy the same image. Keeping TLS a **config** concern rather than a build concern is what makes this revertible without a rebuild — a second argument for edge termination (§4.H.2). |
| **I** | Together with H1 (shared paths). Version bump + `include:` + delete the generator Compose. **Requires `make reset`.** | Revert the commit. The deleted Compose file returns from git; its worked examples live on in the README either way. |

---

## 8. Risks, and where this plan is weakest

Adversarial pass. The `grill-with-docs` skill does not exist in this setup, so this section is my
own attempt to break the plan. It is not reassuring, by design.

**R-01 — Excluding Candidate C while raising seven ADRs is the most likely way this stalls.**
Six of seven existing ADRs are `Proposed`, the oldest since 2026-06 (`docs/adr/`, `CLAUDE.md`
drift table). The team's demonstrated ADR throughput is approximately **zero ratifications per
quarter**. This plan's W0 is four ADRs, two of which (`ADR-A2` ClickHouse ownership,
`ADR-I2` the pre-PR-discipline conflict) require the Captain *and* Commander. If W0 does not
clear, W1's four parallel lanes shrink to **two** (B and I+H1), and A and D/E do not start at
all. This is not a technical risk; it is the plan's single largest schedule risk and it was
created by the scope selection. **The mitigation is to run W0 as one sync agenda item, not four
documents** — and to accept that `ADR-A2` is really a staffing request.

**R-02 — [V-1] chained materialized views. I could not verify it and the whole of D rests on it.**
`metric_stats_1m_mv`, `volume_1m` and `resource_key_presence_1m` all read *silver* base tables
that are themselves MV targets. If an MV does not fire on MV-produced inserts in the chosen
ClickHouse version, all three must be rebuilt against bronze — re-paying the unindexed `Map`
probe cost (1.26 s over ~6 M rows, `clickhouse.py:191-196`) that the silver layer exists to
avoid, and losing the typed-dimension benefit entirely. I was instructed not to run the stack, so
**this is an unverified load-bearing assumption and the first thing to test**: ten minutes in a
throwaway container, before a line of D is written.

**R-03 — The REPLACE PARTITION race has no sound fix and I am dressing it up as a guard.**
My count-before/count-after check narrows a sub-second window; it does not close it. ClickHouse
offers no transaction that makes "recompute then swap" atomic against a concurrent MV insert.
If the team backfills the live partition under load — which someone will, because it is the
partition anyone actually cares about — rows will be lost silently and the 18 assertions will
*pass*, because they compare totals that are both wrong in the same direction. Only pausing
ingest is correct. **Expect this to be violated in practice, and consider making the runner
refuse the live partition outright rather than behind a flag.**

**R-04 — The collector's TLS dependency threatens the baseline's best artifact.**
`core-intent.md §5` calls the distroless static-musl image "the strongest single artifact in the
baseline's security posture", and the Dockerfile ties that explicitly to having no `*-sys` /
OpenSSL / ring (`Dockerfile:3-6`). Managed ClickHouse forces HTTPS, which forces a crypto
provider. If `rustls` + `ring` fails to produce a static `aarch64-unknown-linux-musl` binary —
and `rust-toolchain.toml:19` only adds `x86_64`, while the recorded E2E snapshot is **arm64**
(`README.md §8`) — the team's own development machines break before any cloud does. Worse, the
"fix" that keeps shipping (dynamic linking, or a non-distroless base) silently trades away the
thing Candidate H was supposed to be improving. **A security hardening item whose most likely
failure mode is weakening security is a bad shape, and I do not have a better one that does not
cost a sidecar.**

**R-05 — `e2e-silver` is the job most likely to be flaky, and I cannot calibrate it.**
It builds the Rust image, boots ClickHouse, runs a generator backfill, waits for quiescence, and
then asserts **exact** count equality bronze↔silver (`02-silver-layer.test.sql:16-33`). Every one
of those steps is a flake source, and my quiescence loop is reasoned, not measured. If it flakes
even at 5%, it will be marked non-required and Candidate B will have delivered a workflow that
gates nothing — reproducing issue #34 with more YAML. **Honest estimate of my confidence in
NFR-06's 20-minute budget for this job: low.**

**R-06 — `Makefile` disjointness is unachievable and the parallelism is weaker than §5 implies.**
Four lanes in W1 look parallel; three of them want the same 99-line Makefile, plus
`docker-compose.yml`, `README.md` and `CLAUDE.md`. My "one owner per wave" rule works but means
non-owning legs must either defer their Make target to the next wave or coordinate a
cross-leg edit, which is precisely what ADR-0009's disjointness rule forbids. And it puts the
plan in direct conflict with `.claude/rules/pre-pr-discipline.md`'s "fix it in the same PR".
**Two repo rules collide here and this plan cannot resolve it** — see ADR-I2.

**R-07 — flow-ui's three migrated queries lose their measured justification.**
Each of `contract_violations`, `volume_band` and `call_edges` carries a docstring recording the
measurement that produced its current shape — 6.4 s vs 1.26 s, 0.135 s, a 27.6× join fan-out,
eight phantom edges. DS-15/NFR-05 oblige the migration to re-measure against silver, and
**I cannot produce those numbers statically.** The `volume_band` sorting-key regression I
identified (§4.D.2(a)) is the one I am confident about; there may be others I have not found,
and the dual-source design means a regression can hide behind the bronze fallback for a release.

**R-08 — "One ClickHouse version" may be the wrong version.**
I recommend 25.4 partly because refreshable MVs for `call_edges_1m` are production-ready on a
newer line — **[V-3]**, which I did not verify, and which I am also relying on for the
SharedMergeTree substitution in managed ClickHouse and for `REPLACE PARTITION` there. If
refreshable MVs are still experimental on the chosen version, `call_edges_1m` needs a scheduler,
which is a new moving part in a plan that already has four. If managed ClickHouse substitutes
SharedMergeTree and `REPLACE PARTITION` behaves differently there, **the entire E design loses
its primitive** and I have no second idea that does not change the base tables' engine.

**R-09 — The estimates I trust least**, ranked: (1) `e2e-silver`'s runtime and flake rate;
(2) the three `[V]` ClickHouse behaviours; (3) whether `sentinel_collector` really needs only
`INSERT` (the exporter may read `system.*` for a table check — I designed CI to find out rather
than claim an answer); (4) whether Compose `include:` is available in the team's Compose version;
(5) flow-ui's 73-vs-63 collected-test gap, which I did not resolve.

**R-10 — Scope collisions I expect.** H1 and I cannot be separate legs (shared `infra/` and
`docker-compose.yml`) — merged in §5.2, but anyone reading the candidate list would plan them
apart. B and A both add workflows and both want to define the required-check set. D's read
models and E's flow-ui migration look like independent candidates and are in fact one design,
sequenced strictly. And the `CLICKHOUSE_USER: default` entrypoint route (§4.I.2) means someone
will delete `zz-default-network.xml`, see CI stay green, and believe REQ-H-02 is done.

**R-11 — What this plan quietly assumes about Candidate G.** D's read models are shaped for
Watchers that do not exist yet. I inferred the three (Volume, Schema, Latency/call-graph) from
flow-ui's four boards and the six named Watcher crews. If the Pod↔layer mapping lands differently
— and `CLAUDE.md` flags it as unratified, README's POD3 = storage/read-layer vs `.claude/CLAUDE.md`'s
B3 = watchers — **D may have built read models for the wrong consumer.** Candidate C, excluded
from scope, is the thing that would have told us.

---

## 9. Open decisions requiring an ADR

Owners assigned per the `CLAUDE.md` *Known doc drift* table and README §7 ("components are
singly owned; contracts are jointly owned by the Pods on both sides").

| ADR | Question | Options | Owner |
|---|---|---|---|
| **ADR-A1** | What compute form hosts the three Sentinel services? | Cloud Run (services + Jobs) · GKE Autopilot · GKE Standard · GCE VMs + Compose | **Captain / Commander** — crosses all Pods; no Pod owns deployment today |
| **ADR-A2** | **Who owns ClickHouse operationally, and is it managed or self-hosted?** The ownership question gates the technology one, not the reverse. | Assign an owner + self-host (GKE operator / GCE VM) · buy ownership via managed ClickHouse · leave unassigned and do not deploy storage | **Commander** — `docs/proposals/canonical-read-schema.md:123` and `.claude/CLAUDE.md` both record this as unassigned; it is a staffing decision |
| **ADR-A3** | What applies ClickHouse DDL in a deployed environment? | Bespoke ordered-SQL runner (§4.A.3) · an off-the-shelf migration tool · managed-provider tooling · keep `init.d` and accept no non-destructive path | **Pod 3** (bronze/silver DDL owner, DS-09) with Pod 2 consulted |
| **ADR-A4** | Does the collector terminate TLS itself, or does the platform? Consequence: whether DS-04/NFR-02's pure-Rust static-musl property survives. | Edge termination (recommended) · in-process `rustls` + a crypto provider · TLS-terminating sidecar | **Pod 2** — it owns the collector and `deny.toml` |
| **ADR-I1** | One ClickHouse version, one service definition — and is deleting `services/generator-python/docker-compose.yaml` acceptable? | 25.4 everywhere + `include:` + delete (recommended) · pin 24.3 · keep the file with a superseded banner and port 8081 | **Pod 1** owns the file; **Pod 3** owns the ClickHouse version |
| **ADR-I2** | `.claude/rules/pre-pr-discipline.md` says fix invalidated docs **in the same PR**; ADR-0009 says every leg declares **disjoint paths**. `README.md` and `CLAUDE.md` cannot satisfy both under a parallel fleet. Which rule yields? | Per-wave docs leg (this spec's choice) · serialize legs that touch docs · allow a shared-path exception for docs only | **Captain / Commander** — both documents are theirs; this is the same class of amendment ADR-0009 already has pending |
| **ADR-D1** | Does silver materialise the Sentinel resource keys as typed columns? README §9 item 3 and ADR-0007's trade-offs leave it open; §4.D.2(b)'s key-agnostic `resource_key_presence_1m` deliberately **does not** decide it, and REQ-D-06 depends on it staying undecided in flow-ui's favour. | Keep `Map` probes + a key-agnostic rollup (this spec) · materialise typed columns in silver · materialise in bronze (a contract change → Candidate F territory) | **Pod 3** with **Pod 2** (joint contract owners of the bronze read boundary) |

Also noted, not new ADRs but prerequisites this plan inherits: **ADR-0007's Pod 3 sign-off** is
what moves the Pod 2 → Pod 3 read contract from "agreed boundary" to accepted, and every one of
D, E and H reads or re-grants against that boundary. It sits in the excluded Candidate C.

---

## Appendix — files read for this spec

Beyond `core-intent.md`'s own evidence index: `Makefile`; `docker-compose.yml`; all four Compose
files; `.github/workflows/rust-ci.yml`; `services/collector-rust/{Cargo.toml, clippy.toml,
deny.toml, rust-toolchain.toml, Dockerfile, config.docker.yaml, justfile}`;
`services/collector-rust/src/{config.rs, clickhouse_exporter.rs, main.rs}` (env-access grep);
`services/{generator-python, flow-ui}/pyproject.toml`; both Python `Dockerfile`s;
`infra/clickhouse-init.sql`; `infra/clickhouse-users.d/zz-default-network.xml`;
`infra/clickhouse/init.d/{01-bronze-otel.sql (keys/partitions), 02-silver-layer.sql (full)}`;
`infra/clickhouse/tests/02-silver-layer.test.sql`;
`services/flow-ui/src/flow_ui/clickhouse.py` (full); `README.md` §7–§9; `docs/adr/` listing +
ADR-0009 header; `docs/proposals/canonical-read-schema.md:123`; and via git only:
`HEAD:.claude/CLAUDE.md`, `HEAD:.claude/docs/AGENTIC_GITFLOW.md`.
