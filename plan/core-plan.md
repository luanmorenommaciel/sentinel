# Core Plan — execution tickets for the `sdlc-e2e-review` cycle

> **Fourth document in the chain.** [`intent/core-intent.md`](../intent/core-intent.md) is the
> verified As-Is, [`intent/design-spec.md`](../intent/design-spec.md) (`DSP §n`) the design
> rationale, [`spec/core-spec.md`](../spec/core-spec.md) (`SPEC §n`) the implementation-ready
> spec. This file is the **execution plan**: 8 decision tickets and 48 implementation tickets,
> each with its leg, declared paths, exact file locations, blocking edges and a runnable
> proof-of-completion.
>
> **Two deliberate departures from the `to-tickets` skill**, both decided by the user:
> (i) this is **one combined file**, not one file per ticket under `.scratch/`; (ii) tickets
> **do** name exact file paths and line numbers, overriding the skill's "avoid specific file
> paths" rule. Nothing is published to any tracker — the file is the deliverable.
>
> **Evidence marks**, unchanged: **[E]** read out of the tree · **[I]** inference ·
> **[V]** verify before implementing.
>
> *Written 2026-10-05 against HEAD `3af2ee7`. The stack was not run. `.claude/` is deleted in
> the working tree and was read via `git show HEAD:.claude/...` only; no ticket writes there.*

---

## 0. How to read a ticket

Fields, in order: **Leg** · **Blocked by** (`—` = startable immediately) · **REQ** · **Seam**
(S1–S4 or none) · **Files** (`+`created / `~`edited / `-`deleted, with line numbers where the
line is load-bearing) · **Does** · **Proof** (the exact command, then the observable that
constitutes done) · **Judgement** — present *only* where a criterion cannot be proven by a test.
Every ticket is additionally subject to §2.

### Migration numbering adopted here

`SPEC` is internally inconsistent: REQ-D-10 calls the view re-point `0004`, while §6.1, §6.3a
and §10 call it `0006`. **This plan uses `0006`.** The full set, derived from the numbers `SPEC`
states explicitly (`0002` §14.1, `0003`/`0005`/`0006` §6.1) plus §6.1's "`CREATE DATABASE bronze`
folds into `0001`":

| File | Contents | Ticket |
|---|---|---|
| `0001_bronze_otel.sql` | bronze DDL + `CREATE DATABASE bronze` (symlink target of `init.d/01-*`) | T16 |
| `0002_roles.sql` | three roles, three users, `DROP USER otelgen` | T17 / T19 |
| `0003_meta.sql` | `_meta` + `schema_migrations` + `backfill_runs` | T05 |
| `0004_silver_layer.sql` | existing silver base layer (symlink target of `init.d/02-*`) | T16 |
| `0005_silver_watcher_models.sql` | D's four read models and their MVs | T25–T29 |
| `0006_repoint_metric_rollup.sql` | `CREATE OR REPLACE VIEW silver.metric_rollup_1m` | T34 |

**[I]** `0002`'s `GRANT … ON silver.*` precedes `silver`'s creation in `0004`. ClickHouse does
not existence-check database-level grants, so the order holds — **[V]** confirm in the same
throwaway container used for `[V-4]`, and if it does not, swap `0002` and `0004`.

---

## 1. Ticket index

### Wave 0 — decisions (not implementable work)

| ID | Decision | Owner | Blocks |
|---|---|---|---|
| DEC-A1 | Compute form for the three services | Captain / Commander | T40, T43 |
| DEC-A2 | ClickHouse hosting **and operational owner**; settles `[V-3]` `SharedMergeTree` + `REPLACE PARTITION` | Commander | T30, T40 |
| DEC-A3 | What applies DDL in a deployed environment (bespoke runner vs off-shelf) | Pod 3, Pod 2 consulted | T05 (form only) |
| DEC-A4 | TLS: collector-terminated vs platform edge vs sidecar | Pod 2 | T42 |
| DEC-I1 | One ClickHouse version + deleting the generator Compose file | Pod 1 (file), Pod 3 (version) | T12 |
| DEC-I2 | `pre-pr-discipline` same-PR doc fixes vs ADR-0009 disjoint paths | Captain / Commander | T45–T48 |
| DEC-D1 | Does silver materialise typed Sentinel keys | Pod 3 + Pod 2 | — (must stay undecided; see T28) |
| DEC-V3a | *Folded into DEC-I1 (2026-10-05):* refreshable MVs are ungated on 25.4.13.22 and gated only on 24.3.18.7, so on 25.4+ the scheduled-INSERT fallback is unnecessary. A consequence of DEC-I1, not an independent decision | Pod 3 (follows DEC-I1) | T29 (via DEC-I1) |

Four are W1 blockers in practice: **DEC-A1, DEC-A2, DEC-A3, DEC-I1**.

### Waves 1–4 — implementation

| ID | Title | Blocked by |
|---|---|---|
| T01 | Invariant-assert harness with drop-in directory *(prefactor)* | — |
| T02 | flow-ui `conftest.py` two-coverage response builder *(prefactor)* | — |
| T03 | `[V-4]` Compose `include:` probe | — |
| T04 | arm64 + x86_64 musl/TLS spike, toolchain target, CI `platforms:` | — |
| T05 | `migrate.sh` + `_meta` ledger (`0003`) | — |
| T06 | Collector `user` / `password_file` config | — |
| T07 | `python-ci.yml`: ruff + pytest + `PYTHON_IMAGE` matrix + `-D warnings` | — |
| T08 | Generator integration suite against `CLICKHOUSE_URL` | — |
| T09 | `rust-ci.yml` runs every `#[ignore]`d integration test | — |
| T10 | Python supply-chain job, warn-only | — |
| T11 | `make migrate` target | T05, T07 |
| T12 | `compose.clickhouse.yml` — the single definition *(expand)* | DEC-I1, T03 |
| T13 | Root `docker-compose.yml` → `include:` *(migrate batch 1)* | T12 |
| T14 | CI Compose → `include:` + silver mount + drop env route *(migrate batch 2)* | T12, T09 |
| T15 | Delete the generator Compose file *(contract)* | T13, T14 |
| T16 | Extract `0001`/`0004`, symlink `init.d`, divergence assert | T05, T01, T13 |
| T17 | Roles + users created *(expand)* | T16 |
| T18 | Every consumer connects as a role *(migrate)* | T06, T13, T14, T17 |
| T19 | Delete the `::/0` routes and `otelgen` *(contract + integrate-and-verify)* | T15, T18 |
| T20 | `e2e-silver.yml` — the live-ClickHouse job | T07, T08, T09, T11, T19 |
| T21 | `docs/ci-gates.md` + required-check set | T20 |
| T22 | `release.yml` — registry, OIDC, provenance, SBOM, signing | — |
| T23 | Digest promotion staging→prod, verify-before-admit | T22 |
| T24 | Image vulnerability scan gates the push | T22 |
| T25 | `0005a` `silver.metric_stats_1m` + MV + the new test file | T16, T20 |
| T26 | Real-telemetry tripwire | T25 |
| T27 | `0005b` `silver.volume_1m` + 3 MVs | T25 |
| T28 | `0005c` `silver.resource_key_presence_1m` + 3 MVs | T27 |
| T29 | `0005d` `silver.call_edges_1m` + determinism / no-verdict asserts | T28, T01 *(DEC-V3a folded into DEC-I1, already inherited via T28)* |
| T30 | Backfill runner skeleton + live-partition refusal + README | T05, T19, DEC-A2 |
| T31 | Backfill phase 1 — bronze → silver base, partition swap | T30 |
| T32 | REQ-E-11 in-runner content checksum | T31 |
| T33 | Backfill phase 2 — silver base → rollups, phase gate | T32, T29 |
| T34 | `0006` re-point `metric_rollup_1m`, ledger-gated | T25, T33 |
| T35 | flow-ui `silver_coverage` on the 30 s lane + `source` field | T02 |
| T36 | Dual-source `volume_band` + the stale `_volume_state` name | T35, T27 |
| T37 | Dual-source `call_edges` | T35, T29 |
| T38 | Dual-source `contract_violations` | T35, T28 |
| T39 | Fallback removal criterion, as a test | T36, T37, T38 |
| T40 | A-compute: IaC, per-env config, migrate-before-ingest, readiness | DEC-A1, DEC-A2, T05, T22 |
| T41 | flow-ui deployable and un-deployable independently | T40 |
| T42 | TLS hop 2 + the Dockerfile purity claim | DEC-A4, T04, T40 |
| T43 | Edge auth for `:4317`, metrics inside the boundary | DEC-A1, T40 |
| T44 | Secrets from a managed store, delivered as files | T06, T40 |
| T45 | W1 docs leg | T24, DEC-I2 |
| T46 | W2 docs leg | T29 |
| T47 | W3 docs leg | T39, T34 |
| T48 | W4 docs leg | T44 |

---

## 2. Global constraints — every ticket is subject to these

**Lint policy (Rust).** `unsafe_code = "forbid"` (`services/collector-rust/Cargo.toml:95`) and
`unwrap_used = "deny"` (`:99`) are enforced; `expect_used = "warn"` (`:100`).
**`clippy::pedantic`, `nursery`, `missing_docs` and `missing_errors_doc` are commented out at
`Cargo.toml:101-104`** **[E]** — **no ticket may assume pedantic is enforced**, and no ticket
enables it (that is a separate cleanup PR the comment at `:90-93` already names).
`services/collector-rust/clippy.toml:10-12` bans `std::env::var` outright **[E]**; the two
sanctioned call sites are `src/config.rs:382-394` and `src/clickhouse_exporter.rs:141`.
**No ticket adds a third** — this is why REQ-H-05 is `password_file` and not `CH_PASSWORD`.

**`create_schema:false`.** The collector issues no DDL; it only `INSERT`s. Every schema change
in this plan lands in `infra/clickhouse/migrations/` and reaches the local stack through
`init.d` symlinks (REQ-A-15).

**flow-ui's read-only invariant.** flow-ui reads and never writes; nothing in the pipeline
depends on it being up. No ticket adds an `INSERT`/`ALTER`/`CREATE` under
`services/flow-ui/src/flow_ui/**` (grep-asserted, T01), and no ticket makes the backfill a
flow-ui responsibility (REQ-E-08).

**Contract registry.** `contracts/` is namespaced by producing Pod; a breaking change bumps the
directory (`generator/v2/`, `collector/v2/`), never edits `v1/`. **No ticket in this cycle
touches `contracts/`** — histogram/summary types are Candidate F, out of scope.

**Commits and review.** Conventional Commits · `git commit -S` · the attribution trailer
(`Co-Authored-By:` for human **and** model) on every commit · 2 approvals (first peer, then
Captain). Whether a swimlane squashes or merges into `main` is DEC-I2/ADR-0009 territory and is
**not** an engineering choice (SPEC §12.5).

**`make reset` after any DDL change.** `CREATE TABLE IF NOT EXISTS` will not update a changed
schema; a stale volume fails inserts with `NO_SUCH_COLUMN`. Every ticket that lands DDL states
`make reset && make up` in its proof. All data is synthetic, so the reset is free.

**`CARGO_TARGET_DIR`.** Export a shared `CARGO_TARGET_DIR` before running a fleet — N worktrees
otherwise means N cold Rust builds (ADR-0009 / `AGENTIC_GITFLOW.md`). **No host toolchains:**
everything runs in Docker via `make` (NFR-01); the migration and backfill runners are bash +
`clickhouse-client` and add **zero** new dependencies (NFR-11); no ticket adds a front-end
framework, bundler or `package.json` to flow-ui (NFR-04).

**`make test-silver` and the service name `clickhouse`.** `Makefile:72` is
`docker compose exec -T clickhouse clickhouse-client --multiquery < infra/clickhouse/tests/02-silver-layer.test.sql`
**[E]**. S1's entire silver seam enters through the service **literally named `clickhouse`**.
**T12–T15 must preserve that name in every Compose file that includes the unified definition,
or S1 breaks silently** (REQ-I-07). T01 carries the assert that fails if no Compose file defines
it.

**Live-stack targets stay out of `make test`.** `Makefile:69` is
`test: test-generator test-collector-rust test-flow-ui`. `test-silver`,
`test-generator-integration` and `test-backfill` must not join it (REQ-B-15): `make test` must
keep working with no stack running.

**No leg edits a record.** `docs/adr/0*`, `docs/proposals/`, `docs/research/`,
`docs/clickhouse-schema-divergence*.md`, `.claude/sdd/**` are point-in-time artifacts (NFR-08).

**NFR-05.** A migrated flow-ui query is re-measured and the new figure recorded beside the old
one in its docstring. The measurement needs a running stack; no ticket can produce it
statically (see T36–T38 **Judgement**).

---

## 3. Execution order and the frontier

```
W0 decisions ─▶ W1 nine legs (T01–T24) ─▶ W2 D (T25–T29) ─▶ W3 E (T30–T39) ─▶ W4 deploy/TLS (T40–T44)
W1 chains:  T05 ─▶ T11   T12 ─▶ T13 ─▶ T14 ─▶ T15   T16 ─▶ T17 ─▶ T18 ─▶ T19 ─▶ T20 ─▶ T21   T22 ─▶ {T23,T24}
W2: T25 ─▶ T26 · T25 ─▶ T27 ─▶ T28 ─▶ T29      W3: T30 ─▶ T31 ─▶ T32 ─▶ T33 ─▶ T34 ; T35 ─▶ {T36,T37,T38} ─▶ T39
W4: T40 ─▶ {T41,T42,T43,T44}                   Docs: T45 (end W1) · T46 (W2) · T47 (W3) · T48 (W4)
```

### Strict global order, by frontier

Work the frontier: start anything whose blockers are all done. Read top to bottom for a valid
serialisation if only one agent is available.

| Frontier | Startable | Note |
|---|---|---|
| **F0** | all 8 DEC tickets | Run as **one** sync agenda item, not eight documents — the team's demonstrated ADR throughput is ~0 ratifications/quarter (DSP R-01). |
| **F1** | **T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T22** — eleven tickets, no blockers | Plus T12 the moment DEC-I1 + T03 land. |
| **F2** | T11 (T05+T07) · T12 (DEC-I1+T03) · T35 (T02) | |
| **F3** | T13 (T12) · T23 T24 (T22) | |
| **F4** | T14 (T12+T09) | |
| **F5** | T15 (T13+T14) · T16 (T05+T01+T13) | |
| **F6** | T17 (T16) | |
| **F7** | T18 (T06+T13+T14+T17) | shared integration branch — see §4 |
| **F8** | T19 (T15+T18) | the posture is green **here**, not per-ticket |
| **F9** | T20 (T07+T08+T09+T11+T19) | |
| **F10** | T21 (T20) · T25 (T16+T20) · T30 (T05+T19+DEC-A2) | W2 and W3's runner lane open together |
| **F11** | T26 T27 (T25) · T31 (T30) | |
| **F12** | T28 (T27) · T32 (T31) | |
| **F13** | T29 (T28+T01) · T38 (T35+T28) | |
| **F14** | T33 (T32+T29) · T36 (T35+T27) · T37 (T35+T29) | |
| **F15** | T34 (T25+T33) · T39 (T36+T37+T38) | |
| **F16** | T40 (DEC-A1+DEC-A2+T05+T22) | |
| **F17** | T41 T42 T43 T44 (T40, plus DEC-A4/T04 for T42, T06 for T44) | |
| Docs | T45 after T24 · T46 after T29 · T47 after T34+T39 · T48 after T44 | gated on DEC-I2 |

**Parallelism actually available.** W1 runs **nine** legs (§4). If DEC-A1/A2/A3/I1 do not clear
W0, the frontier shrinks to T01–T11, the release lane T22–T24 and T35 — the prefactors, the probes, the migration runner,
the Python gates and the collector's config shape. That is still real work, and it is why those
carry no decision edges. A-compute (T40) and the whole compose
unification (T12–T15) stall together.

---

## 4. Legs and declared paths — disjointness verified

ADR-0009: every leg declares disjoint paths before it opens. Each cell below is disjoint from
every other cell **in the same wave**; cross-wave reuse of a path is fine because waves do not
overlap.

### Wave 1 — nine legs

| Leg | Declared paths | Tickets |
|---|---|---|
| `leg/ci/invariants-v1` | `scripts/ci/run-invariants.sh`, `scripts/ci/invariants.d/0{1,2,3,4}-*.sh`, `.github/workflows/repo-invariants.yml` | T01 |
| `leg/flow-ui/test-fixtures-v1` | `services/flow-ui/tests/conftest.py`, `tests/test_clickhouse.py`, `tests/test_pipeline.py`, `tests/test_app.py`, `tests/test_prom.py`, `tests/test_topology.py` | T02, T35 |
| `leg/infra/compose-probe-v1` | `infra/clickhouse/README.md` | T03 |
| `leg/ci/rust-ci-v1` | `.github/workflows/rust-ci.yml`, `services/collector-rust/rust-toolchain.toml` | T04, T09 |
| `leg/infra/ch-migrate-v1` | `infra/clickhouse/migrate.sh`, `infra/clickhouse/migrations/**`, `infra/clickhouse/init.d/**`, `infra/clickhouse-init.sql` (del), `infra/clickhouse-users.d/**` (del), `scripts/ci/invariants.d/05-*.sh` | T05, T16, T17, T19 |
| `leg/collector/ch-auth-v1` | `services/collector-rust/src/config.rs`, `src/clickhouse_exporter.rs`, `config.docker.yaml`, `infra/secrets/ch_password.example`, `.gitignore` | T06 |
| `leg/ci/python-gates-v1` | `Makefile`, `.github/workflows/python-ci.yml`, `.github/workflows/e2e-silver.yml`, `docs/ci-gates.md`, `services/flow-ui/pyproject.toml`, `services/generator-python/pyproject.toml`, `services/generator-python/tests/integration/**` | T07, T08, T10, T11, T18, T20, T21 |
| `leg/infra/clickhouse-unify-v1` | `infra/clickhouse/compose.clickhouse.yml`, `docker-compose.yml`, `services/collector-rust/infra/docker-compose.yml`, `services/generator-python/docker-compose.yaml` (del), `services/generator-python/README.md` | T12, T13, T14, T15 |
| `leg/release/registry-provenance-v1` | `.github/workflows/release.yml`, `infra/deploy/README.md` | T22, T23, T24 |

**Three collisions in `SPEC §10` / `DSP §5.2`, resolved here:**

1. **`rust-ci.yml`** — `SPEC §10` leaves it assigned to either `clickhouse-unify-v1` or
   `python-gates-v1` and says "pick one and write it down". **Resolved: a dedicated
   `leg/ci/rust-ci-v1` owns it exclusively**, carrying both the arm64 `platforms:` change (T04)
   and the `#[ignore]`d-test invocation fix (T09). The CI Compose file's own defects (silver
   mount, env route) stay with the unify leg, which owns that file.
2. **`infra/clickhouse-init.sql` + `infra/clickhouse-users.d/**`** — `DSP §5.2` assigns them to
   the unify leg, `SPEC §10` to the migrate leg. **Resolved: migrate leg** (they become
   migration `0002`'s business). The *mount lines* that reference them
   (`docker-compose.yml:14-15`) belong to the unify leg, which is why **T16 and T19 are blocked
   by T13**: the unified definition must stop mounting them before the files can go.
3. **`Makefile`** — one owner this wave: `leg/ci/python-gates-v1` (per `SPEC §10`). The
   `migrate` target (T11) therefore lands in that leg even though the script it calls is written
   in the migrate leg. T11 is blocked by T05 so the target is never committed dangling.

**The one collision that is structural and cannot be fixed by reordering.** `README.md` and
`CLAUDE.md`: `.claude/rules/pre-pr-discipline.md` check 2 obliges **every** leg that invalidates
a claim to fix it **in the same PR**; ADR-0009 obliges disjoint paths. All nine W1 legs
invalidate something in those two files. This plan takes `SPEC §12.3`'s convention — a single
docs leg at the end of each wave (T45–T48) — which **violates the letter of pre-pr-discipline**
by making doc updates lag their code by one leg. That is a repo-rule amendment, not an
engineering judgement. **DEC-I2 owns it, and T45–T48 are blocked on it.** No reordering
dissolves this; it is two rules in direct conflict.

**`scripts/ci/invariants.d/`** is a shared *directory* but never a shared *file*: T01 lays down
`01`–`04`, the migrate leg `05`, W2 `06`–`07`. One assert per file is the prefactor that keeps
paths disjoint (§5, T01).

### Waves 2–4

| Wave | Leg | Declared paths | Tickets |
|---|---|---|---|
| W2 | `leg/silver/watcher-models-v1` | `infra/clickhouse/migrations/0005_silver_watcher_models.sql`, `infra/clickhouse/tests/03-watcher-models.test.sql`, `infra/clickhouse/queries/03-watcher-sample.sql`, `scripts/ci/invariants.d/0{6,7}-*.sh`, `Makefile` *(owner this wave)* | T25–T29 |
| W3 | `leg/silver/backfill-v1` | `infra/clickhouse/backfill/**`, `infra/clickhouse/migrations/0006_repoint_metric_rollup.sql`, `Makefile` *(owner this wave)* | T30–T34 |
| W3 | `leg/flow-ui/silver-boards-v1` | `services/flow-ui/src/flow_ui/clickhouse.py`, `src/flow_ui/pipeline.py`, `services/flow-ui/tests/test_clickhouse.py`, `tests/test_pipeline.py`, `services/flow-ui/ARCHITECTURE.md`, `services/flow-ui/static/app.js` | T36–T39 |
| W4 | `leg/security/transport-v1` | `services/collector-rust/Cargo.toml`, `Cargo.lock`, `deny.toml`, `Dockerfile`, `src/grpc.rs` | T42 |
| W4 | `leg/security/secrets-v1` | `infra/deploy/secrets/**`, `infra/deploy/config/<env>/**` | T43, T44 |
| W4 | `leg/deploy/<platform>-v1` | `infra/deploy/**` except `README.md`, `infra/deploy/config/<env>/**` | T40 (starts when DEC-A1/A2 land and T05, T22 are done), T41 |
| each | `leg/docs/wave-<n>-v1` | `README.md`, `CLAUDE.md`, `.claude/**` is **excluded** | T45–T48 |

W3 disjointness: `0006_*.sql` sits in the backfill leg (not the W2 watcher-models leg) because
REQ-D-10 ties it to the backfill ledger. `app.js:1874` carries the stale `_volume_state` name
and belongs to the flow-ui leg. W4: `infra/deploy/config/<env>/**` is wanted by both the deploy
leg and the secrets leg — **resolved: secrets leg owns `infra/deploy/secrets/**` and the
`*.secret.yaml` fragments; the deploy leg owns everything else under `config/<env>/`.**

### Expand–contract, and the one shared integration branch

Two changes are wide refactors, not tracer bullets, and are sequenced expand → migrate → contract:

- **Compose unification** (REQ-I-01/02/03/07/08). Blast radius: three Compose files, `Makefile:72`,
  `rust-ci.yml:93,103`, both CI jobs. **Expand** T12 adds the single definition beside the
  existing three, consumed by nobody. **Migrate** T13 (root), T14 (CI) — each keeps CI green on
  its own because the old inline definitions survive until they are replaced one file at a time.
  **Contract** T15 deletes the generator Compose file, blocked by both batches.
- **ClickHouse role / grant replacement** (REQ-H-01/02/03/04/06, REQ-B-14). Blast radius: the
  collector's exporter, flow-ui's reader, both CI live jobs, two init files, two Compose files.
  **Expand** T17 creates the three roles and users with the passwordless `default` untouched —
  nothing changes posture, nothing breaks. **Migrate** T18 points every consumer at a role.
  **Contract** T19 deletes `zz-default-network.xml`, the `CLICKHOUSE_USER` /
  `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT` route and the `otelgen` user.

**T18 cannot stay green alone**, and that is stated rather than papered over: the moment the
collector is pointed at `sentinel_collector_u` it needs the users.d override gone *and* the
unified definition in place *and* `password_file` support compiled in — three legs. **T06, T13,
T14, T17, T18 and T19 therefore share the integration branch `swim/infra/ch-posture`, and green
is promised only at T19.** This is the `to-tickets` escape hatch for batches that cannot land
green individually, used deliberately and once.

---

## 5. Wave 1

### T01 — Invariant-assert harness with a drop-in directory *(prefactor)*
**Leg** `leg/ci/invariants-v1` · **Blocked by** — · **REQ** I-01, I-05, I-07, E-08, H-01 · **Seam** S1
**Files** +`scripts/ci/run-invariants.sh` · +`scripts/ci/invariants.d/01-single-clickhouse-image.sh`,
`02-service-named-clickhouse.sh`, `03-no-duplicate-host-8080.sh`, `04-no-plaintext-secrets.sh`,
`05-flow-ui-is-read-only.sh` · +`.github/workflows/repo-invariants.yml`
**Does** Makes repo invariants executable, and gives every later ticket a place to add its own
assert **as a new file** so no two legs edit the same one — the prefactor that makes T16, T29 and
T44's asserts cheap instead of a path collision.
**Proof** `bash scripts/ci/run-invariants.sh` → `05` passes today; `01`/`02`/`03` are authored to
the **post-T15** state and `04` to the **post-T19** state, so they fail until those tickets land.
The harness exits non-zero while any assert fails; land it `continue-on-error: true` and flip the
flag in T15. (`grep -rn "INSERT\|ALTER TABLE\|CREATE TABLE" services/flow-ui/src/flow_ui/` → no
hits **[E]**.) Negative proof per assert, each reverted: a
second `image: clickhouse/clickhouse-server:` line; a renamed service; `8080:8080` published
twice; `otelgen_secret` in a scratch file; `await self._query("INSERT INTO x VALUES")` in
`clickhouse.py` → each exits non-zero naming the file.

### T02 — flow-ui `conftest.py` two-coverage response builder *(prefactor)*
**Leg** `leg/flow-ui/test-fixtures-v1` · **Blocked by** — · **REQ** E-13 · **Seam** S2
**Files** +`services/flow-ui/tests/conftest.py` · ~`tests/test_clickhouse.py`,
`tests/test_pipeline.py`, `tests/test_app.py`, `tests/test_prom.py`, `tests/test_topology.py`
**Does** One fixture faking `ClickHouse._query`'s response text in two shapes — silver covers the
window, silver does not — so both branches of every method T36–T38 migrate are asserted in the same
form. `find services/flow-ui -name conftest.py` is empty today and each of the five files builds
its own fake **[E]**.
**Proof** `make test-flow-ui` → exit 0 with the same or greater collected count (record it).
`grep -c "def _fake\|class Fake" services/flow-ui/tests/test_*.py` → 0, proving the ad-hoc fakes
are gone rather than shadowed.

### T03 — `[V-4]` Compose `include:` probe
**Leg** `leg/infra/compose-probe-v1` · **Blocked by** — · **REQ** I-02, I-03, I-08 · **Seam** S1
**Files** +`infra/clickhouse/README.md`
**Does** Closes the last open ClickHouse-adjacent assumption: is `include:` available, and does it
resolve relative volume paths from the **including** file's directory or the included one's?
`services/collector-rust/infra/docker-compose.yml:34` reaches the DDL with
`../../../infra/clickhouse/init.d/...`, and a changed base is the most likely way REQ-I-03 breaks
**[E]**.
**Proof** Two throwaway files under the scratchpad, one including the other with a relative bind
mount; `docker compose version` then `docker compose -f outer.yml config` → the printed absolute
`source:` path is the observable. Record it and the Compose version floor in the README, plus
which form T12 must use (or `extends:` if resolution is from the including file).
**Resolved 2026-10-05:** resolution is from the **included** file; T12 uses `include:` with `./init.d/...` mounts in the shared file. `extends:` rebases identically. The T12 CI assert (REQ-I-07) must inspect merged `docker compose config` output, because a same-name local service silently wins.

### T04 — arm64 + x86_64 musl/TLS spike, toolchain target, CI `platforms:`
**Leg** `leg/ci/rust-ci-v1` · **Blocked by** — · **REQ** H-13, H-10, NFR-02 · **Seam** S4
**Files** ~`services/collector-rust/rust-toolchain.toml:17` (add `aarch64-unknown-linux-musl`) ·
~`.github/workflows/rust-ci.yml:119-132` (add `platforms: linux/amd64,linux/arm64`; `push: false`
at `:129` **stays**) · +a temporary `musl-tls-spike` job and a `tls-spike` feature, not in the
default feature set
**Does** Produces the facts DEC-A4 needs **before** the decision and closes the arm64 hole:
`rust-ci.yml:119-132` passes no `platforms:`, so arm64 is never built in CI even though the
recorded E2E snapshot is arm64 **[E]**. Independent of whether TLS ships — sequence it early.
**Proof** `docker buildx build --platform linux/amd64,linux/arm64 services/collector-rust` → both
manifests, exit 0. Per target,
`cargo build --release --features tls-spike --target {x86_64,aarch64}-unknown-linux-musl` → exit 0
and `file target/<t>/release/collector | grep -q "statically linked"` → exit 0 for **both**. Then
`cargo deny check --all-features` → exit 0, or a named licence needing a reviewed `deny.toml` entry.
**Judgement** Whether to **accept** the trade is DEC-A4's and is not test-provable: a crypto
provider breaks `Dockerfile:3-6`'s no-`*-sys`/OpenSSL/ring claim, which `core-intent.md §5` calls
the strongest artifact in the baseline's posture. The spike supplies evidence; Pod 2 decides.

### T05 — `migrate.sh` + the `_meta` ledger (`0003`)
**Leg** `leg/infra/ch-migrate-v1` · **Blocked by** — *(DEC-A3 sets its form, not its existence)* · **REQ** A-04, A-13, A-14, D-11, NFR-11 · **Seam** S1
**Files** +`infra/clickhouse/migrate.sh` · +`infra/clickhouse/migrations/0003_meta.sql`
*(2026-10-05: `migrate.sh` MUST pass `--multiquery` to `clickhouse-client` — the 24.3 client
rejects multi-statement `-q` with `Code: 62` where 25.4 accepts it. Measured, #46.)*
(`_meta.schema_migrations` + `_meta.backfill_runs`, verbatim from `SPEC §6.2`)
**Does** Makes "what schema is deployed?" a `SELECT`, and gives the deployed path a way to apply
DDL where `docker-entrypoint-initdb.d` does not exist. Bash + `clickhouse-client` only (NFR-11).
Runner contract and exit codes per `SPEC §6.2`: idempotence lives in the **ledger**, not in the
statements, which is what admits `CREATE OR REPLACE VIEW` in `0006`.
**Proof** Against a throwaway ClickHouse: (1) run twice →
`SELECT count() FROM _meta.schema_migrations` identical, exit 0 both times, second run logs
`already applied` per file. (2) Append a byte to an applied file → **exit 3**, stdout naming both
checksums and the file, no further file attempted. (3) Dead host → **exit 2**. (4) A deliberately
failing statement → **exit 4** and that version's ledger count is `0`, so the next run retries it.

### T06 — Collector `user` / `password_file` config
**Leg** `leg/collector/ch-auth-v1` · **Blocked by** — · **REQ** H-05, H-15, A-06 · **Seam** S3
**Files** ~`services/collector-rust/src/config.rs` (`ClickHouseConfig` + `user: Option<String>`,
`password_file: Option<PathBuf>`; `deny_unknown_fields` stays) · ~`src/clickhouse_exporter.rs`
(read at startup, trim **one** trailing newline, never log contents, length or prefix) ·
~`config.docker.yaml` · +`infra/secrets/ch_password.example` · ~`.gitignore`
**Does** The config file carries a **path, never a value** — the only shape compatible with
`clippy.toml:10-12`'s `std::env::var` ban. There is deliberately no `password` field.
**Proof** `make test-collector-rust` → exit 0 with four cases beside the parse table at
`src/config.rs:472-630`: absent → no credential sent; unreadable → startup error naming **the path
only**; present → credential used; and the error `Display` contains neither bytes nor length.
`make lint-collector-rust` → exit 0 (also the negative proof for the env ban).
`grep -n "METRICS_PORT" services/collector-rust/config.docker.yaml` → 0 hits: the env path rebinds
to `0.0.0.0:<port>` and discards a config-supplied host (`src/config.rs:373-397` **[E]**), so
deployed config sets `metrics.listen` in YAML (REQ-H-15).

### T07 — `python-ci.yml`: ruff + pytest + `PYTHON_IMAGE` matrix + `-D warnings`
**Leg** `leg/ci/python-gates-v1` · **Blocked by** — · **REQ** B-01, B-02, B-03, B-06, B-08 · **Seam** S1
**Files** +`.github/workflows/python-ci.yml` (path-filtered; matrix 3.10/3.11/3.12; calls **only**
Make targets) · ~`Makefile:79,89` (`PYTHON_IMAGE ?= python:3.12-slim`) · ~`Makefile:99` (append
`-- -D warnings`) · ~`services/flow-ui/pyproject.toml` (+`[tool.ruff]`: `line-length = 120`,
`target-version = "py311"`, `select = ["E","F","I","UP"]`, matching
`services/generator-python/pyproject.toml:36-45`)
**Does** *Authors* the gates — they were never written: `mypy` appears **zero** times in the repo
and flow-ui has no `[tool.ruff]`, so `make lint-flow-ui` runs bare defaults (88 cols, `E`+`F`) over
`src tests scripts` (`Makefile:92`) **[E]**. The 88→120 and `E,F`→`E,F,I,UP` diff lands here.
`Makefile:99` omits `-D warnings`, which silently un-denies `expect_used`.
**Proof** `make lint-generator && make lint-flow-ui && make test-generator && make test-flow-ui &&
make lint-collector-rust` → all exit 0. Four negative proofs, each reverted: an unused import in
`flow_ui/pipeline.py` → `make lint-flow-ui` non-zero; `assert False` in `tests/test_pipeline.py` →
`make test-flow-ui` non-zero; `PYTHON_IMAGE=python:3.10-slim make test-generator` → exit 0 while
the same for flow-ui → **expected non-zero** (it declares `>=3.11`; first time that floor is
testable); an `expect_used` call site → `make lint-collector-rust` non-zero.
**Judgement** Whether `mypy --strict` enters at all, and any coverage floor, are **not**
engineering calls — nine documents assert seven gates that have never existed (`SPEC §12.4`). This
ticket adds ruff + pytest + the matrix only and refers the rest to DEC-I2's sync.

### T08 — Generator integration suite against `CLICKHOUSE_URL`
**Leg** `leg/ci/python-gates-v1` · **Blocked by** — · **REQ** B-11, B-15 · **Seam** S1
**Files** ~`services/generator-python/tests/integration/test_e2e_clickhouse.py:21-42` (delete
`testcontainers` and the `importorskip`; target `CLICKHOUSE_URL`) ·
~`services/generator-python/pyproject.toml` · ~`Makefile` (+`test-generator-integration`, **not**
added to `test:` at `:69`)
**Does** Implements `SPEC §9`. The file brings its own ClickHouse today and skips itself away
**[E]**, so it crosses no seam; in the live job it would start a *second*, different ClickHouse
with its own image tag, no `init.d` mounts, no silver and a passwordless `default`.
**Proof** `grep -rn "testcontainers\|importorskip" services/generator-python/` → **0 hits**.
`make test` → exit 0 **with no stack running** (REQ-B-15 — the assert that matters).
`make test-generator-integration` with no stack → **non-zero, loudly**; with `make up` first →
exit 0.
**Judgement** Given up, named: the test is no longer runnable standalone without `make up`.

### T09 — `rust-ci.yml` runs every `#[ignore]`d integration test
**Leg** `leg/ci/rust-ci-v1` · **Blocked by** — · **REQ** B-13 · **Seam** S1
**Files** ~`.github/workflows/rust-ci.yml:99` (`cargo test --test clickhouse_roundtrip --locked --
--ignored` → `cargo test --locked -- --ignored`) · ~`rust-ci.yml` (+an orphan-ignored-test step;
it lives here, not in T01's directory, because that is another leg's path this wave)
**Does** Closes the serious CI defect. `tests/grpc_export_roundtrip.rs:133`'s `#[ignore]`d
`otlp_grpc_payload_lands_in_clickhouse` **runs nowhere** **[E]** — the gRPC ingest path, the only
path driving the silver MVs under real inserts, has **zero live coverage**, and T25–T34 rest on it.
**Proof** The `integration` job log shows `otlp_grpc_payload_lands_in_clickhouse ... ok` and **4**
integration targets attempted, not 1. Orphan step: list `#[ignore]` test names from
`services/collector-rust/tests/*.rs`, diff against `cargo test -- --ignored --list`, fail if any
name is unrun. Negative proof: add a new `#[ignore]`d test in an excluded target → non-zero.

### T10 — Python supply-chain job, warn-only
**Leg** `leg/ci/python-gates-v1` · **Blocked by** — · **REQ** B-07 · **Seam** S1
**Files** ~`.github/workflows/python-ci.yml` (+`supply-chain` job: `pip-audit` + `bandit`,
`continue-on-error: true`)
**Does** Closes the asymmetry: `cargo deny` gates licences, advisories and bans with
`yanked = "deny"` and `--locked` throughout, while Python has no lockfile, no `pip-audit`, no
`bandit`, `>=` floors only **[E]**.
**Proof** The job runs and prints findings; `grep -c continue-on-error` in the job → 1. Promotion
to required is T21's business, after a week of real PRs.

### T11 — `make migrate` target
**Leg** `leg/ci/python-gates-v1` *(Makefile owner, W1)* · **Blocked by** T05, T07 · **REQ** A-04, A-09, I-07 · **Seam** S1
**Files** ~`Makefile` (+`migrate:` calling `infra/clickhouse/migrate.sh` through
`docker compose exec -T clickhouse`, mirroring `:72`'s shape)
**Does** Puts the runner behind the one operator interface so CI invokes a target, never a
re-declared command (REQ-B-03).
**Proof** `make up && make migrate` → exit 0; again → exit 0 with
`clickhouse-client -q "SELECT count() FROM _meta.schema_migrations"` unchanged.
`grep -n "exec -T clickhouse" Makefile` → the service name is still literally `clickhouse` at both
`:72` and the new target (REQ-I-07).

### T12 — `compose.clickhouse.yml` — the single definition *(expand)*
**Leg** `leg/infra/clickhouse-unify-v1` · **Blocked by** DEC-I1, T03 · **REQ** I-01, I-02, I-07, I-08, B-12, B-14 · **Seam** S1
**Files** +`infra/clickhouse/compose.clickhouse.yml` — service **named `clickhouse`**, one pinned
image (DEC-I1; `SPEC §6.7` recommends `25.4`), **both** DDL mounts
(`init.d/01-bronze-otel.sql` and `init.d/02-silver-layer.sql`), the healthcheck from
`docker-compose.yml:22-26`, and **no** `CLICKHOUSE_USER`, **no**
`CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT`, **no** `clickhouse-init.sql` mount, **no** `users.d` mount
**Does** The expand step: one definition exists, consumed by nobody, so nothing can break. It
fixes three defects by construction — the single version (REQ-I-01); the silver mount CI has never
had (`services/collector-rust/infra/docker-compose.yml:34` mounts **bronze only** **[E]**,
REQ-B-12/I-04); and the second `::/0` route (`:37-39` makes the entrypoint generate its own users
file, independent of `zz-default-network.xml` **[E]**, REQ-B-14).
**Proof** `docker compose -f infra/clickhouse/compose.clickhouse.yml config` → exit 0, output
containing `clickhouse:` as a service key, exactly one `image:` line, two
`/docker-entrypoint-initdb.d/` mounts, and no `CLICKHOUSE_USER`. Existing stacks untouched:
`docker compose config` and
`docker compose -f services/collector-rust/infra/docker-compose.yml config` both still exit 0.

### T13 — Root `docker-compose.yml` → `include:` *(migrate batch 1)*
**Leg** `leg/infra/clickhouse-unify-v1` · **Blocked by** T12 · **REQ** I-02, I-07, I-08 · **Seam** S1
**Files** ~`docker-compose.yml:5-26` (inline `clickhouse:` → `include:`; the
`clickhouse-init.sql` mount at `:14` and the `users.d` mount at `:15` disappear with it — which is
why T16 and T19 are blocked on this ticket)
**Does** The local stack takes its ClickHouse from the single definition; `make up` stays one step.
**`default` reverts to localhost-only here**, so the collector's export breaks until T18 — green as
a Compose-config change, runtime green deferred to T19 on `swim/infra/ch-posture` (§4).
**Proof** `docker compose config` → exit 0 with exactly one service named `clickhouse` carrying the
T12 image and both DDL mounts. `grep -c "image: clickhouse/clickhouse-server" docker-compose.yml` →
0. `bash scripts/ci/run-invariants.sh` → `02-service-named-clickhouse.sh` passes.

### T14 — CI Compose → `include:` + silver mount + drop env route *(migrate batch 2)*
**Leg** `leg/infra/clickhouse-unify-v1` · **Blocked by** T12, T09 · **REQ** I-03, I-04, I-08, B-12, B-14 · **Seam** S1
**Files** ~`services/collector-rust/infra/docker-compose.yml:24-45` (inline service → `include:`;
the bronze-only mount at `:34` and the env block at `:35-39` go)
**Does** CI finally tests the DDL the local stack runs, with silver present. `rust-ci.yml:93,103`
keep working and that file is **not** edited here (REQ-I-03 calls it load-bearing).
**Proof** `docker compose -f services/collector-rust/infra/docker-compose.yml config` → exit 0 with
resolved DDL mount `source:` paths that are absolute and exist (where `[V-4]` bites; T03's README
says which form). In CI: `… up -d --wait` → healthy, then
`clickhouse-client -q "SELECT name FROM system.databases WHERE name IN ('bronze','silver')"` →
**both** rows (first time `silver` has ever appeared here). T09's four targets still pass.

### T15 — Delete the generator Compose file *(contract)*
**Leg** `leg/infra/clickhouse-unify-v1` · **Blocked by** T13, T14 · **REQ** I-05, I-06, H-01 *(partial)* · **Seam** S1
**Files** -`services/generator-python/docker-compose.yaml` ·
~`services/generator-python/README.md` (preserve both worked invocations:
`--delivery direct --init-schema`, and the HyperDX OTLP target with an ingestion key) ·
~`.github/workflows/repo-invariants.yml` (flip T01's `continue-on-error` off)
**Does** Removes plaintext `otelgen_secret` (`:7, 15-18, 62-63`), a second `24.3` ClickHouse
(`:10`) and `clickstack-all-in-one` publishing **`8080:8080`** (`:41`) — the same host port as
flow-ui (`docker-compose.yml:70`), so the two stacks cannot coexist today **[E]**. A Compose file
**asserts the present**, so it is not a protected record. No code changes: `--delivery direct` and
`OTELGEN_OTLP_API_KEY` stay.
**Proof** `bash scripts/ci/run-invariants.sh` → **exit 0** with `01`, `02` and `03` all green for
the first time. `git ls-files | grep -c "generator-python/docker-compose"` → 0.
**Judgement** REQ-I-06 — that the README preserves the examples *usefully* — is a review gate. The
bar: a reviewer who has never run the generator follows the README and reaches a sending
generator. No test applies that.

### T16 — Extract `0001`/`0004`, symlink `init.d`, divergence assert
**Leg** `leg/infra/ch-migrate-v1` · **Blocked by** T05, T01, T13 · **REQ** A-15, A-05, H-01 *(partial)* · **Seam** S1
**Files** +`infra/clickhouse/migrations/0001_bronze_otel.sql` (current
`init.d/01-bronze-otel.sql` **plus** `CREATE DATABASE IF NOT EXISTS bronze`, folded in from
`infra/clickhouse-init.sql:13`) · +`infra/clickhouse/migrations/0004_silver_layer.sql` (current
`init.d/02-silver-layer.sql`) · ~`infra/clickhouse/init.d/01-bronze-otel.sql` → **symlink** to
`../migrations/0001_bronze_otel.sql` · ~`init.d/02-silver-layer.sql` → symlink to
`../migrations/0004_silver_layer.sql` · -`infra/clickhouse-init.sql` ·
+`scripts/ci/invariants.d/05-initd-matches-migrations.sh`
**Does** One source of DDL, two apply paths — the mechanism that keeps `create_schema:false`
honest where `docker-entrypoint-initdb.d` does not exist (`SPEC §12.2`) without the local stack
losing its zero-step `make up`.
**Proof** `make reset && make up` → healthy, with
`clickhouse-client -q "SELECT count() FROM system.tables WHERE database='bronze'"` → **7** and the
current silver object count — `init.d` still applies through the symlinks (REQ-A-05). Then
`make migrate` against a volume created **without** `init.d` mounts → the same counts, proving one
source two paths. `bash scripts/ci/invariants.d/05-initd-matches-migrations.sh` → exit 0; negative
proof — replace a symlink with a copy and change one byte → non-zero naming both files.

### T17 — Roles + users created *(expand)*
**Leg** `leg/infra/ch-migrate-v1` · **Blocked by** T16 · **REQ** H-03, H-04 · **Seam** S1
**Files** +`infra/clickhouse/migrations/0002_roles.sql` (the three roles and three users from
`SPEC §14.1`, **without** the `DROP USER otelgen` line, which is T19's) · ~`infra/clickhouse/migrate.sh`
(pass the password as a **query parameter** from a mounted file, never a literal in a migration
file, because migration files are in git)
**Does** Expand: `sentinel_collector` (INSERT on `bronze.*`), `sentinel_reader` (SELECT on
`bronze.*`, `silver.*`, `system.tables`, `system.columns`), `sentinel_migrator` (DDL + SELECT on
`system.parts`) exist beside the untouched passwordless `default`. Posture is unchanged, so nothing
breaks. The `system.tables`/`system.columns` grant is not optional — flow-ui draws the Silver box
from them (`clickhouse.py:429, 503, 505` **[E]**) and omitting it makes the fourth box **silently
disappear**, which looks like a design choice.
**Proof** `make reset && make up && make migrate` → exit 0, then
`clickhouse-client -q "SELECT name FROM system.roles ORDER BY name"` → the three names, and
`SHOW GRANTS FOR sentinel_reader` includes `system.tables` and `system.columns`. Negative:
`clickhouse-client --user sentinel_reader_u … -q "INSERT INTO bronze.otel_logs VALUES"` → non-zero
`ACCESS_DENIED`. `grep -rn "plaintext_password\|otelgen_secret" infra/clickhouse/migrations/` → 0.
**Judgement** `SPEC §14.1` explicitly does **not** assert the grant list is complete — the
`clickhouse` crate may probe `system.*` for a table check. REQ-H-06 makes **CI the oracle** (T20),
not this document and not a reviewer.

### T18 — Every consumer connects as a role *(migrate)*
**Leg** `leg/ci/python-gates-v1` + `swim/infra/ch-posture` · **Blocked by** T06, T13, T14, T17 · **REQ** H-06, A-06 · **Seam** S1 + S3
**Files** ~`services/collector-rust/config.docker.yaml` (`user: sentinel_collector_u`,
`password_file: /run/secrets/ch_password`) · ~`docker-compose.yml` (mount the gitignored
`infra/secrets/ch_password`, mode `0400`) · ~`.github/workflows/rust-ci.yml` and
`e2e-silver.yml` (jobs connect as the roles, not `default`) ·
~`services/flow-ui/src/flow_ui/config.py` *(reader credentials; declared in this leg this wave)*
**Does** The migrate step. **Green is not promised by this ticket alone** — it lands on
`swim/infra/ch-posture` with T06/T13/T14/T17/T19 and is verified at T19 (§4).
**Proof** (at T19) the collector authenticated as `sentinel_collector_u` and flow-ui as
`sentinel_reader_u` with `make test-silver` exit 0;
`docker compose logs collector-rust | grep -ci "password\|secret"` → 0 (NFR-10);
`docker inspect sentinel-collector | grep -c ch_password` → the **path** only.

### T19 — Delete the `::/0` routes and `otelgen` *(contract + integrate-and-verify)*
**Leg** `leg/infra/ch-migrate-v1` + `swim/infra/ch-posture` · **Blocked by** T15, T18 · **REQ** H-01, H-02, B-14 · **Seam** S1
**Files** -`infra/clickhouse-users.d/zz-default-network.xml` ·
~`infra/clickhouse/migrations/0002_roles.sql` (+`DROP USER IF EXISTS otelgen`)
**Does** The contract step and the swimlane's single green gate. `SPEC §16` calls this the highest
value-per-line item in the plan: no deployment, no ADR, and a committed plaintext credential gone.
**Both** `::/0` routes close here. DSP R-10 predicts the failure mode precisely — someone deletes
the XML, sees CI stay green, and believes REQ-H-02 is done.
**Proof** The whole swimlane in one run: `make reset && make up && make migrate && make generate &&
make test-silver && make test && bash scripts/ci/run-invariants.sh` → **every command exit 0**.
Plus: `grep -rn "otelgen_secret" . --exclude-dir=.git` → **0 hits**;
`clickhouse-client -q "SELECT count() FROM system.users WHERE name='otelgen'"` → `0`; and from
**another container on the Compose network**, `wget -qO- 'http://clickhouse:8123/?query=SELECT+1'`
as `default` with no password → **denied** (route 1). Run the route-2 probe once in the PR against
a container with `CLICKHOUSE_USER` re-added to confirm it *was* a real route, then keep only the
route-1 assert in CI.

### T20 — `e2e-silver.yml` — the live-ClickHouse job
**Leg** `leg/ci/python-gates-v1` · **Blocked by** T07, T08, T09, T11, T19 · **REQ** B-04, B-05, B-09, H-06 · **Seam** S1
**Files** +`.github/workflows/e2e-silver.yml` (build the image → `make up` → `make migrate` →
`make generate` → quiescence wait → `make test-silver` → `make test-generator-integration` → print
collected counts to the job summary)
**Does** Stands up the oracle D, E and H all depend on; 18 silver assertions and 246 Python test
functions currently run on a laptop and nowhere else (issue #34). **Quiescence (REQ-B-05) is not a
sleep:** `make generate` returning does not mean the collector flushed — the channel holds **64
batches**, hard-coded at `buffer.rs:140-141` **[E]**. Read `sentinel_signals_ingested_total` from
`:9090/metrics`, poll until unchanged across two consecutive 2 s samples **and** `sum(bronze
live-table counts)` equals it, cap 60 s, and on timeout fail **printing both numbers**. **Drive
ingest with `make generate`, never the golden fixture** —
`services/collector-rust/infra/docker-compose.collector.yml:13-15` records that the 2023-dated
fixture's rows are purged on the first background merge under the event-time TTL **[E]**.
**Proof** The job green on a PR, its summary printing collected counts for all three suites
(REQ-B-09 — CI's output becomes the authoritative number, consumed by T45). Negative proof for the
quiescence loop: patch the image to drop the exporter → the job fails on **timeout** printing
ingested vs persisted, not on an early assertion.
**Judgement** `SPEC §16` names this the job most likely to flake and the quiescence loop is
*reasoned, not measured*. **Land it non-required**, watch a week of real PRs, then promote (T21).
No test asserts "this job's flake rate is acceptable"; a human reads a week of runs.

### T21 — `docs/ci-gates.md` + the required-check set
**Leg** `leg/ci/python-gates-v1` · **Blocked by** T20 · **REQ** B-10, B-07 *(promotion)* · **Seam** none
**Files** +`docs/ci-gates.md` (every required status check with its workflow, job name, and whether
it is required **today**)
**Does** Makes the gate set a reviewable artifact so the WoW's claim and the configured reality can
be compared instead of assumed (`SPEC §12.4`).
**Proof** `grep -c "^| " docs/ci-gates.md` matches the job count across `.github/workflows/*.yml`.
**Judgement** **Not provable from inside the repo.** Branch protection is a GitHub setting, not a
file, and this plan runs no `gh`. Substitute: the Captain configures the rule from
`docs/ci-gates.md` and records the date in that file; a reviewer compares the two.

### T22 — `release.yml` — registry, OIDC, provenance, SBOM, signing
**Leg** `leg/release/registry-provenance-v1` · **Blocked by** — · **REQ** A-01, A-02, A-03 · **Seam** S4
**DEC-A1 blocker removed (2026-10-05):** `design-spec.md` §5.1 lists registry, provenance, OIDC and `release.yml` as A-inv, invariant to the compute form (DEC-A1 gates only the deploy side, T40/T43), and every DEC-A1 option is a Google Cloud target, so the Workload Identity Federation push path is the same for all of them.
**Files** +`.github/workflows/release.yml` (on `push: main` and tags;
`docker/build-push-action` with `provenance: mode=max`, `sbom: true`,
`platforms: linux/amd64,linux/arm64`; cosign keyless via the same OIDC identity; GitHub OIDC →
Workload Identity Federation, **no JSON key**) · +`infra/deploy/README.md`
**Does** Gives "roll back to the previous version" an artifact to name for the first time. Three
images, SHA-tagged plus a channel tag; the SHA tag is the only thing a deployment names. **S4 has
no Make target by design** (`SPEC §8.4`): a laptop could only authenticate with a long-lived
credential, which is what REQ-A-03 deletes. `rust-ci.yml:129`'s `push: false` stays, so a fork PR
can never publish.
**Proof** After a merge to `main`: `crane digest …/collector-rust:<git-sha>` → a digest;
`cosign verify --certificate-oidc-issuer https://token.actions.githubusercontent.com <digest>` →
exit 0; `cosign verify-attestation --type slsaprovenance <digest>` → exit 0;
`cosign download sbom <digest> | head` → non-empty.
`grep -rn "GOOGLE_APPLICATION_CREDENTIALS\|_json_key\|service-account-key" .github/workflows/` →
**0 hits** (REQ-A-03).

### T23 — Digest promotion staging→prod, verify-before-admit
**Leg** `leg/release/registry-provenance-v1` · **Blocked by** T22 · **REQ** A-07, A-02 *(admission)* · **Seam** S4
**Files** ~`.github/workflows/release.yml` (+a promote job: re-tag **by digest**, never rebuild) ·
~`infra/deploy/README.md`
**Does** Rebuild-on-promote is forbidden; per-environment differences live **only** in
`infra/deploy/config/<env>/`, which is what makes a hop revertible by redeploying the same digest.
**Proof** `D1=$(crane digest …:<sha>)`; run the promote job; `D2=$(crane digest …:prod)`;
`[ "$D1" = "$D2" ]` → **exit 0**. Digest equality is the whole assertion. Negative: an unsigned
digest fed to the job → non-zero before tagging.
**Judgement** "Deployment verifies the signature **before admitting**" is only provable once a
platform exists (DEC-A1); the admission-controller half is asserted in T40.

### T24 — Image vulnerability scan gates the push
**Leg** `leg/release/registry-provenance-v1` · **Blocked by** T22 · **REQ** H-12 · **Seam** S4
**Files** ~`.github/workflows/release.yml` (scan step, warn-only first)
**Does** SHOULD-level; extends the Rust path's existing discipline from crates to images.
**Proof** The step runs and prints findings on a real push; after calibration, flip to blocking and
the negative proof is a deliberately vulnerable base image failing the job.
**Judgement** The severity threshold at which a push is blocked is a policy call, not a test.

---

## 6. Wave 2 — D, silver completion

`[V-1]` (chained MV firing) is **VERIFIED PASS** on both `24.3.18.7` and `25.4.13.22`
(`SPEC §11.1`), so **D is unblocked and no `[V-1]` ticket gates it**; the bronze-rebuild fallback
is not needed. Two limits carry forward: the probes ran against a **bare** ClickHouse, proving the
*engine* chains and **not** that this repo's five MV bodies chain — T25's live `make test-silver`
establishes that; and they ran with `CLICKHOUSE_SKIP_USER_SETUP=1`, so they say **nothing** about
grants (T17/T20's business).

### T25 — `0005a` `silver.metric_stats_1m` + MV + the new test file
**Leg** `leg/silver/watcher-models-v1` · **Blocked by** T16, T20 · **REQ** D-01, D-02, D-08, D-09 · **Seam** S1
**Files** +`infra/clickhouse/migrations/0005_silver_watcher_models.sql` (the
`AggregatingMergeTree` + `metric_stats_1m_mv` from `SPEC §6.3a`, verbatim) ·
+`infra/clickhouse/tests/03-watcher-models.test.sql` · ~`Makefile:72` (add the new file to
`test-silver`'s set) · +`infra/clickhouse/queries/03-watcher-sample.sql`
**Does** The rollup becomes storage-backed while `silver.metric_rollup_1m` keeps its name and
column contract. The five columns are the Tier-1 z-score **input**, not a z-score.
`SimpleAggregateFunction` keeps `0006`'s body legible and `02-silver-layer.test.sql:47-51`'s plain
`sum()` working. Leads with `window_start`, not `service_name`: `clickhouse.py:272-290` has **no
`ServiceName` predicate** — the service is a `GROUP BY` **[E]** (`SPEC §4` correction 9).
**Proof** `make reset && make up && make migrate && make generate && make test-silver` → exit 0,
with the **18 existing assertions unchanged and silent** (REQ-D-09) plus:
`sum(sample_count) FROM silver.metric_stats_1m == count() FROM silver.metric_observations`, and
`throwIf(abs(stddev_from_sum_squares - stddevPop) > 1e-9, …)`. That tolerance pins `0006`'s
`greatest(0, …)` guard: on a near-constant series, cancellation in `E[x²] − E[x]²` can go
marginally negative where `stddevPop` cannot. `SHOW CREATE TABLE silver.metric_observations`
byte-identical before and after (REQ-D-08).

### T26 — Real-telemetry tripwire
**Leg** `leg/silver/watcher-models-v1` · **Blocked by** T25 · **REQ** H-11 · **Seam** S1
**Files** ~`infra/clickhouse/tests/03-watcher-models.test.sql` (three `throwIf`s on
`countIf(NOT is_synthetic)` over `operation_executions`, `log_events`, `metric_observations`)
**Does** The baseline's strongest compliance fact is that all data is synthetic and **nothing today
would flag the transition**. `is_synthetic Bool` already exists in all three base tables
(`02-silver-layer.sql:20, 51, 73, 102, 123, 151` **[E]**), so the tripwire is one predicate —
nearly free now, unaffordable to retrofit after the first real-telemetry swap.
**Proof** `make test-silver` → exit 0 on synthetic data. Negative:
`INSERT INTO silver.log_events … is_synthetic = false` → `make test-silver` non-zero naming the
table; revert with `make reset`.

### T27 — `0005b` `silver.volume_1m` + 3 MVs
**Leg** `leg/silver/watcher-models-v1` · **Blocked by** T25 · **REQ** D-03, D-08 · **Seam** S1
**Files** ~`infra/clickhouse/migrations/0005_silver_watcher_models.sql` (+`volume_1m` and the three
`volume_1m_*_mv`, from `SPEC §6.3b`) · ~`infra/clickhouse/tests/03-watcher-models.test.sql`
**Does** Rows-per-minute per producer keyed `(window_start, service_name, signal)`. Carrying
`signal` keeps the `otel_logs`-only semantics `volume_band` uses today (`clickhouse.py:274`) while
making the other two reachable without a second table. Re-aiming `volume_band` at
`silver.log_events` directly is rejected: its `ORDER BY` puts `event_time` **fifth**
(`02-silver-layer.sql:91`), so a window filter prunes only to the day.
**Proof** `make test-silver` → exit 0 with `sum(rows) WHERE signal='log'` equal to
`count() FROM silver.log_events` per producer, and likewise `trace`/`metric`. Then
`clickhouse-client --time -q "SELECT service_name, sum(rows) FROM silver.volume_1m WHERE
window_start >= now() - INTERVAL 60 MINUTE GROUP BY service_name"` → record the elapsed time; it
must be **≤ 0.135 s** (bronze's recorded figure, `clickhouse.py:260-263` **[E]**) or T36 has no
justification to migrate.

### T28 — `0005c` `silver.resource_key_presence_1m` + 3 MVs
**Leg** `leg/silver/watcher-models-v1` · **Blocked by** T27 · **REQ** D-04, D-06, D-08 · **Seam** S1 + S2
**Files** ~`infra/clickhouse/migrations/0005_silver_watcher_models.sql` (+the table and three
`rkp_1m_*_mv`, from `SPEC §6.3c`) · ~`infra/clickhouse/tests/03-watcher-models.test.sql`
**Does** Per producer per minute: total rows and the count of rows carrying **each** resource-attribute
key. **Key-list agnostic, and that is load-bearing** — flow-ui keeps its own
`REQUIRED_RESOURCE_KEYS` (`clickhouse.py:36-45`, "duplicated deliberately: this is the *reader's*
copy" **[E]**); a key list in Pod 3's DDL would be a **third** copy, would make flow-ui draw Pod
3's opinion (REQ-D-06), and would quietly decide DEC-D1. `[V-2]` is **VERIFIED PASS** on both
versions, so the `Map`-typed shape stands and neither fallback is needed.
**Proof** `make test-silver` → exit 0 with `key_counts[k] <= rows` for **every** k (over an
`ARRAY JOIN` of the map) and `rows - key_counts['service.name']` equal to the bronze
`countIf(NOT mapContains(ResourceAttributes,'service.name'))` for the same window. Record the
rollup read time against the bronze probe's **1.26 s over ~6 M rows** (`clickhouse.py:191-196`
**[E]**).
**Judgement** A named limitation, not a silent one: `rows - key_counts[k]` is *rows missing key k*,
and the **sum over k is not the number of bad rows** — `clickhouse.py:197-200` records that
reporting the sum made a producer missing 4 of 5 keys read "80%" **[E]**. `countIf(NOT has_all)`
cannot be reconstructed from `key_counts`, so the `bad` column keeps coming from bronze until a
future `rows_missing_any` column exists. No test substitutes for understanding that; it goes in the
DDL comment and `ARCHITECTURE.md`, and it is why T38 keeps its fallback longest.

### T29 — `0005d` `silver.call_edges_1m` + determinism / no-verdict asserts
**Leg** `leg/silver/watcher-models-v1` · **Blocked by** T28, T01 *(DEC-V3a folded into DEC-I1)* · **REQ** D-05, D-07, D-12 · **Seam** S1
**Files** ~`infra/clickhouse/migrations/0005_silver_watcher_models.sql` (+`call_edges_1m` and
`call_edges_1m_rmv` with `REFRESH EVERY 1 MINUTE`; the scheduled-INSERT +
partition-swap fallback only if DEC-I1 selects 24.3) · ~`infra/clickhouse/tests/03-watcher-models.test.sql` ·
+`scripts/ci/invariants.d/06-silver-mv-determinism.sh` ·
+`scripts/ci/invariants.d/07-no-verdict-in-silver.sh`
**Does** `src → dst` span and error counts per window. **This cannot be an incremental MV and that
is a hard fact**: an MV sees only the current insert block, and a call edge joins a child span to
its parent, routinely in different blocks. `clickhouse.py:311-331` records the cost of getting it
wrong — joining on `SpanId` alone invented **eight non-existent edges**, and without collapsing
parents to one row per `(TraceId, SpanId)` a 15-minute window produced **445,229 joined rows from
16,154 children**, a 27.6× fan-out **[E]**. Hence the `GROUP BY trace_id, span_id` collapse and the
join on `trace_id` **and** `parent_span_id`. Trailing 24 h, TTL 2 days — the table holds 24 h of
history, not 30 days, said in the DDL rather than left implicit.
**`[V-3a]` (corrected 2026-10-05, `SPEC §11.1`): refreshable MVs are ungated on 25.4.13.22 (no
setting needed; the flag is `Obsolete`) and gated only on 24.3.18.7.** The earlier claim of an
experimental gate on both versions was a probe error (the setting was always set, never omitted).
So this is a consequence of DEC-I1, not an independent decision: on 25.4+ the scheduled-INSERT
fallback is unnecessary. **Do not implement before DEC-I1**; if it selects 24.3, the fallback (a
scheduler per environment; it cannot reuse `backfill.sh`, issue #48) or the flag as recorded risk
applies. This ticket MUST also assert refreshable-MV availability in CI, **without** the
experimental setting, against the version DEC-I1 selects (issue #49).
**Proof** `make test-silver` → exit 0 with: `throwIf((SELECT count() FROM silver.call_edges_1m
WHERE src_service = dst_service) != 0, …)`; **no edge absent from
`services/generator-python/config/topology/default.yaml`'s declared DAG** (the eight-phantom-edge
regression); and `sum(spans)` within the expected band of the bronze self-join over the same
window. `bash scripts/ci/invariants.d/06-silver-mv-determinism.sh` → exit 0 — it greps every silver
MV body for `now()`/`today()`/`rand()`/`generateUUID`/`hostName`/`_part` and fails on any hit
**other than `call_edges_1m`'s**, the single named exception (REQ-D-12).
`bash scripts/ci/invariants.d/07-no-verdict-in-silver.sh` → exit 0 — no threshold, band, verdict,
severity or escalation literal in `0005_*.sql` (REQ-D-07).
**Judgement** The grep proves no *literal* threshold; it cannot prove the models encode no
*opinion*. "Does this read model decide what is anomalous?" is a review question — Candidate G owns
verdicts, D owns inputs.

---

## 7. Wave 3 — E, backfill and the flow-ui migration

### T30 — Backfill runner skeleton + live-partition refusal + README
**Leg** `leg/silver/backfill-v1` · **Blocked by** T05, T19, DEC-A2 · **REQ** E-01, E-12, NFR-11 · **Seam** S1
**Files** +`infra/clickhouse/backfill/backfill.sh` · +`infra/clickhouse/backfill/README.md` ·
~`Makefile` (+`backfill-silver FROM= TO= [PHASE=]`)
**Does** Range control first, before a single `INSERT` exists. The partition list comes from
`system.parts`, not bash date arithmetic (`SPEC §6.5`); default `to` = **yesterday**. **Any range
whose upper bound is ≥ `today()` is refused outright — not behind a flag, no `--force`, no env
override** (REQ-E-12), and the refusal writes `status='refused'` to `_meta.backfill_runs`, because
"I ran it and nothing happened" is the report that wastes an hour. The README carries the operator
procedure for the live partition (pause ingest) — a **procedure, not a code path**.
**Proof** `make backfill-silver FROM=$(date -v-2d +%F) TO=$(date +%F)` → **exit non-zero**,
`SELECT count() FROM silver.log_events` **unchanged**, and
`SELECT status FROM _meta.backfill_runs ORDER BY started_at DESC LIMIT 1` → `refused`. Zero
inserts: `SELECT count() FROM system.query_log WHERE query ILIKE 'INSERT INTO silver.%__bf%' AND
event_time > {t0}` → `0`. Then `grep -cE '\-\-force|FORCE|ALLOW_LIVE'
infra/clickhouse/backfill/backfill.sh` → **0** — the absence of an override is itself the
requirement.
**Judgement** **The race this prohibition replaces is not testable and no test is invented for
it.** ClickHouse offers no transaction making "recompute then swap" atomic against a concurrent MV
insert, so a count guard narrows a sub-second window and does not close it; **no seam distinguishes
"the race fired" from "the recompute had a bug"** — both present as the same broken silver↔bronze
equality; and **re-running to prove idempotence erases the evidence**, the second run being correct
by construction. The substitute is the prohibition plus the documented procedure (`SPEC §8.6`).
**[V-3] still open:** whether a managed provider's `SharedMergeTree` preserves `REPLACE PARTITION`
is unverifiable locally — `[V-3b]` passed on `MergeTree` only. If it differs, **E loses its
primitive and there is no second design that leaves the base tables' engine alone.** DEC-A2 must
settle it before the deployed half is implemented.

### T31 — Backfill phase 1 — bronze → silver base, partition swap
**Leg** `leg/silver/backfill-v1` · **Blocked by** T30 · **REQ** E-02, E-03, E-04 *(ordering)*, E-05 · **Seam** S1
**Files** ~`infra/clickhouse/backfill/backfill.sh` ·
+`infra/clickhouse/backfill/sql/phase1-{log_events,operation_executions,metric_observations}.sql`
**Does** Per `(table, partition)`: `CREATE TABLE silver.<base>__bf AS silver.<base>` (the
structural identity `REPLACE PARTITION` requires), `INSERT` the MV's `SELECT` **verbatim** with a
date predicate, swap, drop the staging partition. Idempotent **by construction**: every silver MV
body is row-wise — one bronze row to exactly one silver row, no aggregation, no join
(`02-silver-layer.sql:43-65, 95-114, 143-185` **[E]**) — so `silver_partition = f(bronze_partition)`
is a pure function. No dedup key is added anywhere (REQ-E-02, D-08).
**Two details the implementation gets wrong by default.** (1) **Partition granularity mismatch:**
`bronze.otel_logs` partitions by `toYYYYMM(TimestampDate)` (`01-bronze-otel.sql:121`) while
`silver.log_events` partitions by **day** (`02-silver-layer.sql:90`) **[E]** — the logs backfill
iterates **silver days** and filters bronze by date; it does **not** map partition to partition.
Backwards, it swaps a day into a month-shaped slot: the single most likely bug in this cycle.
(2) `metric_observations` takes **two** staging inserts (gauge then sum) before the one swap.
**Hard bound:** never insert into `bronze.otel_traces`. `bronze.otel_traces_trace_id_ts_mv` is
block-local aggregating — `min/max … GROUP BY TraceId` into a dedup-keyless `MergeTree`
(`01-bronze-otel.sql:79-89` **[E]**) — so replay *adds* rows with different boundaries.
**Proof** Seed two days, then `make backfill-silver FROM=<d> TO=<d> PHASE=1` **twice** → both exit
0 with `SELECT count() FROM silver.log_events WHERE toDate(event_time)={d}` identical after each
(REQ-E-02, the central property). `make test-silver` → exit 0, the 18 exact equalities holding.
Guards (REQ-E-05): drop `silver` → non-zero; alter the staging structure → non-zero; mutate the
bronze partition's count mid-run → non-zero. And assert mechanically that `bronze.otel_traces`
appears only in a `FROM`, never an `INSERT INTO`, across
`infra/clickhouse/backfill/sql/*.sql`.

### T32 — REQ-E-11 in-runner content checksum
**Leg** `leg/silver/backfill-v1` · **Blocked by** T31 · **REQ** E-03, E-11 · **Seam** S1
**Files** ~`infra/clickhouse/backfill/backfill.sh` (both checksums before the swap; refuse on
mismatch; record `content_hash` and `expected_hash` in `_meta.backfill_runs`)
**Does** **Count equality is blind to content divergence at constant cardinality** — a `Map` copied
with a different key order, a `Float64` from a different expression, a wrong `metric_kind`: all
pass all 18 assertions. So the checksum is mandatory **in the runner, not only in a test**, and
count equality **must not** be accepted as proof. `sum(cityHash64(*))` is **order-insensitive**,
which it must be because `silver.metric_observations` receives rows from **two** MVs
(`02-silver-layer.sql:143, 165`), so physical row order inside a part is not a property of the
data. Sound because all four base MVs are deterministic and row-wise (`SPEC §8.7`) and all four
copy the attribute `Map`s **wholesale** rather than rebuilding them from `mapKeys`/`mapValues`, so
a recompute reproduces the same bytes. `call_edges_1m` is excluded by name (REQ-D-12).
**Proof** Run phase 1 → `SELECT content_hash, expected_hash FROM _meta.backfill_runs WHERE
phase='phase1' AND partition_id={d}` → **equal and both non-zero**. Negative proof, the one that
matters: patch a staging `SELECT` to compute `sum_value` differently (or swap `'gauge'` for
`'sum'`) → the runner **refuses the swap**, exits non-zero naming both hashes, the live partition
is unchanged, and `status='failed'` is recorded. Confirm the 18 count assertions would have
**passed** in that state — the demonstration that the checksum, not the counts, has teeth.

### T33 — Backfill phase 2 — silver base → rollups, phase gate
**Leg** `leg/silver/backfill-v1` · **Blocked by** T32, T29 · **REQ** E-04 · **Seam** S1
**Files** ~`infra/clickhouse/backfill/backfill.sh` ·
+`infra/clickhouse/backfill/sql/phase2-{metric_stats_1m,volume_1m,resource_key_presence_1m}.sql`
**Does** The detail most likely to be missed: **materialized views fire on `INSERT`, not on
`ALTER … REPLACE PARTITION`**, so a swap into `silver.log_events` does **not** populate
`silver.volume_1m`. Phase 2 recomputes the rollups from the silver base tables **after** phase 1
has recorded `status='ok'` for that partition, and **refuses** any partition it has not — running
phase 2 first yields a rollup over partial data **that looks perfectly healthy**. `call_edges_1m`
is refresh-driven and **never backfilled** (REQ-D-12).
**Proof** `make backfill-silver FROM=<d> TO=<d> PHASE=2` **before** phase 1 → **exit non-zero**
naming the partition and the missing phase-1 row, no rollup row written. Then `PHASE=1` →
`PHASE=2` → both exit 0, `make test-silver` exit 0, and `sum(sample_count) FROM
silver.metric_stats_1m WHERE toDate(window_start)={d}` equal to `count() FROM
silver.metric_observations WHERE toDate(event_time)={d}`. Run `PHASE=2` twice → counts and
`content_hash` identical.

### T34 — `0006` re-point `metric_rollup_1m`, ledger-gated
**Leg** `leg/silver/backfill-v1` · **Blocked by** T25, T33 · **REQ** D-01, D-10, D-11 · **Seam** S1
**Files** +`infra/clickhouse/migrations/0006_repoint_metric_rollup.sql` (`CREATE OR REPLACE VIEW
silver.metric_rollup_1m` over `silver.metric_stats_1m`, body from `SPEC §6.3a`, **column contract
unchanged** including `avg_value`/`stddev_value`, preceded by a `throwIf` gate)
**Does** The hazard D would otherwise ship. Re-pointing the view **breaks**
`infra/clickhouse/tests/02-silver-layer.test.sql:47-51` on **any volume with history**, because the
new MV does not `POPULATE` (invariant SI-1; measured 1,703,050 bronze trace rows over 36 h against
12,849 silver rows over 12 min **[E]**). So it is a **separate migration** that **refuses to apply**
unless `_meta.backfill_runs` records a completed `phase2` for **every** partition present in
`silver.metric_observations`; a fresh volume satisfies it trivially. `CREATE VIEW IF NOT EXISTS`
does not update an existing view, hence `CREATE OR REPLACE` (REQ-D-11).
**Proof** On a volume with un-backfilled partitions: `make migrate` → **exit 4** naming the missing
partitions, with `SHOW CREATE VIEW silver.metric_rollup_1m` **unchanged**. After
`make backfill-silver PHASE=all` covers them: `make migrate` → exit 0, `SHOW CREATE VIEW` now reads
`metric_stats_1m`, and **`make test-silver` → exit 0 with `02-silver-layer.test.sql:47-51`
passing** — that pre-existing assertion is the regression guard for D's whole storage swap. On a
fresh volume: `make reset && make up && make migrate` → exit 0, no backfill needed.

### T35 — flow-ui `silver_coverage` on the 30 s lane + `source` field
**Leg** `leg/flow-ui/test-fixtures-v1` *(W1)* → `leg/flow-ui/silver-boards-v1` *(W3)* · **Blocked by** T02 · **REQ** E-14, E-07 *(mechanism)* · **Seam** S2
**Files** ~`services/flow-ui/src/flow_ui/pipeline.py:136-240` (+`silver_coverage: dict[str, float]`
— `min(event_time)` per silver base table as a unix timestamp) ·
~`services/flow-ui/src/flow_ui/clickhouse.py` (+`silver_coverage()`, one query) ·
~`tests/test_pipeline.py`, `tests/test_clickhouse.py`
**Does** The dual-source decision adds **exactly three things**: this field; a per-board source
decision taken at read time (*silver if `coverage[table] <= now() - window`, else bronze*); and one
`source: "silver" | "bronze"` per affected board entry. **No write path, no flag, no operator
switch** — the decision is derived from the state of the thing being drawn, the same property that
stops flow-ui drifting from the pipeline. One query on the **30 s** cadence, never per board per
tick, and a probe failure **degrades to bronze, never to an error** (REQ-E-14, NFR-05).
**Proof** `make test-flow-ui` → exit 0 with new cases on T02's fixture: a probe raising →
`silver_coverage == {}` and no exception escapes; coverage present → populated. Cadence assert:
patch the clock, run one lineage tick and one contract tick, count calls → **exactly one per 30 s
tick, zero on the 1 s and 5 s lanes**.

### T36 — Dual-source `volume_band` + the stale `_volume_state` name
**Leg** `leg/flow-ui/silver-boards-v1` · **Blocked by** T35, T27 · **REQ** E-06, E-07, E-09, NFR-05 · **Seam** S2
**Files** ~`services/flow-ui/src/flow_ui/clickhouse.py:247-290` (branch on coverage; return shape
**unchanged**) · ~`clickhouse.py:251`, `pipeline.py` docstrings, `static/app.js:1874` (the function
is **public** — `volume_state`, `pipeline.py:78` **[E]** — and three places still call it
`_volume_state`) · ~`tests/test_clickhouse.py`, `tests/test_pipeline.py` ·
~`services/flow-ui/ARCHITECTURE.md`
**Does** The Watchers board keeps 36 hours of volume history on the day the rollups go live — no
cutover moment, each board flipping on its own as coverage grows. The band identity is preserved:
the query returns raw statistics and the band stays computed in `volume_state` (S2), pure and
therefore testable as arithmetic.
**Proof** `make test-flow-ui` → exit 0 with four cases on T02's fixture: (1) **band numbers
identical from either source for the same data** — *the* test that proves the migration is
invisible; (2) `[]` on absent `silver.*` (must not regress); (3) bronze chosen when
`coverage > now() - window`; (4) silver when `<=`. Then `grep -rn "_volume_state"
services/flow-ui/` → **0 hits**.
**Judgement** NFR-05's re-measurement **cannot be produced statically**: the docstring must carry
the new figure beside bronze's recorded 0.135 s, and that number needs `make up && make generate`
plus a timed query. A test can assert a measurement *line exists*; only a human running the stack
can assert it is **true**. T27's figure is the input.

### T37 — Dual-source `call_edges`
**Leg** `leg/flow-ui/silver-boards-v1` · **Blocked by** T35, T29 · **REQ** E-06, E-07, NFR-05 · **Seam** S2
**Files** ~`services/flow-ui/src/flow_ui/clickhouse.py:311-331` · ~`tests/test_clickhouse.py` ·
~`services/flow-ui/ARCHITECTURE.md`
**Does** Moves the edge derivation to `silver.call_edges_1m`. The bronze branch keeps the
collapse-and-join shape `clickhouse.py:318-324` records as the fix for the eight phantom edges and
the 27.6× fan-out — **not** simplified while it is still a live fallback. Coverage asymmetry:
`call_edges_1m` carries a **2-day** TTL and a 24 h body bound, so a board asking for more must stay
on bronze.
**Proof** `make test-flow-ui` → exit 0 with: both branches returning the same edge set for the same
data; **no `src == dst`** from either; `[]` on absent silver; and a case where the requested window
exceeds the 24 h bound → **bronze chosen** even though coverage exists.
**Judgement** NFR-05 as in T36 — the replacement figure must be measured on a live stack.

### T38 — Dual-source `contract_violations`
**Leg** `leg/flow-ui/silver-boards-v1` · **Blocked by** T35, T28 · **REQ** E-06, E-07, D-06, NFR-05 · **Seam** S2
**Files** ~`services/flow-ui/src/flow_ui/clickhouse.py:180-246` · ~`tests/test_clickhouse.py` ·
~`services/flow-ui/ARCHITECTURE.md`
**Does** Moves the unindexed `Map` probe — **1.26 s over ~6 M rows**, with the `ARRAY JOIN` form at
6.4 s (`clickhouse.py:191-196` **[E]**) — onto a rollup two orders of magnitude smaller. The reader
computes `missing[k] = rows - key_counts[k]` from **its own** `REQUIRED_RESOURCE_KEYS`
(`clickhouse.py:39-45`), so the key list gains no third copy (REQ-D-06). **This board keeps its
bronze fallback longest** (T28's limitation).
**Proof** `make test-flow-ui` → exit 0 with: per-key `missing` counts identical from either source
for the same data; the `bad` column still sourced from bronze **and a test asserting exactly
that**, so a later change cannot silently reconstruct it wrongly from `key_counts`; and `[]` on
absent silver. `grep -rn "REQUIRED_RESOURCE_KEYS" infra/ services/collector-rust/` → **0 hits** —
the three-copy assert.

### T39 — Fallback removal criterion, as a test
**Leg** `leg/flow-ui/silver-boards-v1` · **Blocked by** T36, T37, T38 · **REQ** E-10 · **Seam** S2
**Files** ~`services/flow-ui/ARCHITECTURE.md` · ~`services/flow-ui/tests/test_clickhouse.py`
**Does** Stops the fallback becoming permanent by making its removal condition a predicate: **the
bronze path for a board is deleted in the first PR after `min(event_time)` in its backing silver
table has been `<= now() - 30 days` — the bronze TTL horizon (`01-bronze-otel.sql:63`) —
continuously for 7 days in the target environment.** At that point silver cannot be shorter than
bronze, both being TTL-bounded to the same window, and the fallback is dead code.
**Proof** `make test-flow-ui` → exit 0 with the predicate tested across three fixtures: coverage
younger than 30 days → "keep"; older for 7 continuous days → "remove"; older but with a gap inside
the 7 days → "keep".
**Judgement** The **predicate** is tested; **satisfaction** of it is not — it needs 7 days of
observation in a real environment, which no CI run supplies. The substitute: T35's `source` field
makes the condition observable on the page rather than inferred, and a human reads it.

---

## 8. Wave 4 — A-compute, H2/H3

### T40 — A-compute: IaC, per-env config, migrate-before-ingest, readiness
**Leg** `leg/deploy/<platform>-v1` · **Blocked by** DEC-A1, DEC-A2, T05, T22 · **REQ** A-06, A-08, A-09, A-12, A-02 *(admission)*, H-07 · **Seam** S1 + S3
**Files** +`infra/deploy/**` (per the platform DEC-A1 picks) ·
+`infra/deploy/config/{staging,prod}/collector.yaml` ·
+`infra/deploy/config/{staging,prod}/flow-ui.env`
**Does** IaC with no manual console step in the documented path, and a **DDL migration step that
reaches terminal success before any ingest workload starts** (REQ-A-09). **The config shape is a
trap worth naming:** mode is a function of config *shape*, not a flag —
`match config.grpc { Some(_) => serve_grpc, None => run }` (`src/main.rs:60-64` **[E]**), and
within server mode `config.clickhouse.is_some()` selects export vs log-only (`main.rs:88-105`), so
a deployed `collector.yaml` missing either section **silently becomes a one-shot file reader or a
counter that persists nothing**. Readiness is an **external** HTTP probe against `:9090/metrics` —
nothing executes inside the container (REQ-A-12) — and `:9090` stays unauthenticated on the wire
because it **is** the probe (REQ-H-14). `Snapshot` is per-process and not shared
(`pipeline.py:136-240`), so **flow-ui pins to one instance**: two instances show two histories.
**Proof** `terraform plan` (or equivalent) → no drift from a clean apply; a staging apply from an
empty project reaching a healthy stack. Ordering: the deploy's logs show `migrate` exiting 0
**before** the collector revision accepts traffic, and an injected failing migration leaves the
revision **never promoted**. `curl -fsS http://<collector>:9090/metrics | grep -c
sentinel_signals_ingested_total` → `1` from **outside** the container. Config-shape assert in CI:
`grep -q '^grpc:' infra/deploy/config/*/collector.yaml && grep -q '^clickhouse:' …` → exit 0 for
every env file.
**Judgement** REQ-A-08 is a **review gate**: a reviewer follows `infra/deploy/README.md` on a clean
project and reports where they had to click. No test detects a step someone performed by hand and
forgot to write down. Blue/green vs canary vs rolling **cannot be chosen before the orchestrator
is** — DEC-A1.

### T41 — flow-ui deployable and un-deployable independently
**Leg** `leg/deploy/<platform>-v1` · **Blocked by** T40 · **REQ** A-11 · **Seam** S2
**Files** ~`infra/deploy/**` (flow-ui as its own unit, deployed last, removable first)
**Does** flow-ui reads and never writes, and nothing depends on it being up. `GET /healthz` →
`{ok, collector, clickhouse, subscribers}` (`main.py:179-186`) — **nothing polls it today** **[E]**
— becomes its deployment probe.
**Proof** In staging: destroy flow-ui, then `make generate` against the deployed collector → rows
still land in `bronze.*` and the 18 assertions still pass. Re-deploy,
`curl -fsS https://<flow-ui>/healthz` → `{"ok": true, …}`. Deploy flow-ui **before** the collector
on a fresh environment → it comes up and reports the collector absent rather than crash-looping.
`grep -rn "flow-ui" infra/deploy/ | grep -c depends_on` → flow-ui is nobody's dependency.

### T42 — TLS hop 2 + the Dockerfile purity claim
**Leg** `leg/security/transport-v1` · **Blocked by** DEC-A4, T04, T40 · **REQ** H-07, H-10, NFR-02 · **Seam** S4
**Files** ~`services/collector-rust/Cargo.toml`, `Cargo.lock`, `deny.toml`,
`services/collector-rust/Dockerfile:3-6`, `src/grpc.rs` *(only if DEC-A4 picks in-process)*
**Does** Only what DEC-A4 decided. Edge termination means **no collector code changes at all** —
hop 1 is avoided because the generator already has `--otlp-secure`, `--otlp-api-key`,
`--otlp-header`. In-process means `rustls` plus a crypto provider, which **breaks**
`Dockerfile:3-6`'s "cityhash-rs + lz4_flex, no `*-sys`/OpenSSL/ring" claim — and that claim is then
**corrected in the same PR**, because leaving it is a false statement in the repo's strongest
security artifact (REQ-H-10).
**Proof** If in-process: T04's two static-musl builds still pass with the feature in the **default**
set; `cargo deny check --all-features` → exit 0 (any `deny.toml` licence addition reviewed as a
deliberate change, not a bypass); `docker run --rm --entrypoint sh <image>` → **fails** (distroless
preserved, NFR-02); `file` → `statically linked` on both arches; and
`grep -n "no \*-sys" services/collector-rust/Dockerfile` → absent or rewritten to the truth. Hop:
`openssl s_client -connect <ch-host>:8443` succeeds and a plaintext `:8123` connection from the
collector's network is refused.
**Judgement** Whether the trade is acceptable is DEC-A4's. The failure mode of this security item
is **weakening security**: if the static aarch64 build fails, the fixes that keep shipping (dynamic
linking, a non-distroless base) trade away exactly what H was improving. The sidecar alternative
preserves purity exactly and costs a second image, config and patch surface.

### T43 — Edge auth for `:4317`, metrics inside the boundary
**Leg** `leg/security/secrets-v1` · **Blocked by** DEC-A1, T40 · **REQ** H-08, H-14 · **Seam** none
**Files** ~`infra/deploy/**` (edge policy) · ~`infra/deploy/README.md`
**Does** OTLP `:4317` unreachable without authentication in a deployed environment; `:9090/metrics`
unauthenticated **on the wire** but **inside** the boundary — where the platform demands an
authenticated probe, that authentication is the platform's own identity, **never** an application
credential embedded in the collector (REQ-H-14).
**Proof** From outside: a `grpcurl` Export call without credentials → rejected at the edge; with
credentials → `OK`. `curl http://<collector>:9090/metrics` from outside → no route; from inside →
`200`.
**Judgement** **Deploy-time only; no repo test exists** — these probes need a live environment and
cannot run in CI. The one in-repo half:
`grep -rn "api.key\|token" services/collector-rust/src/` → 0 hits (no embedded credential).

### T44 — Secrets from a managed store, delivered as files
**Leg** `leg/security/secrets-v1` · **Blocked by** T06, T40 · **REQ** H-09, A-06, NFR-10 · **Seam** S3 + S4
**Files** +`infra/deploy/secrets/**` (Secret Manager or equivalent → projected volume, mode `0400`,
owned by the container's non-root user) · ~`infra/deploy/config/<env>/*.secret.yaml` ·
~`scripts/ci/invariants.d/04-no-plaintext-secrets.sh`
**Does** The config carries a **path, never a value**. Never an env var, never a build arg, never a
`docker inspect`-visible field — the only shape compatible with the `std::env::var` ban.
**Proof** `docker inspect <collector> | grep -c ch_password` → the **path** only.
`<platform> logs <collector> | grep -ci "password\|secret"` → `0`.
`crane export <digest> - | tar -t | grep -c secrets` → `0` (no secret in any image layer).
`bash scripts/ci/invariants.d/04-no-plaintext-secrets.sh`, extended to fail on any file under
`infra/secrets/` that is not `*.example` → exit 0, with a committed non-example file as the
negative proof.

---

## 9. Docs legs

### T45–T48 — one docs leg per wave
**Leg** `leg/docs/wave-{1,2,3,4}-v1` · **Blocked by** T24 + DEC-I2 (W1) · T29 (W2) · T39, T34 (W3) · T44 (W4) · **REQ** B-09, I-06, NFR-08 · **Seam** none
**Files** ~`README.md` · ~`CLAUDE.md`. **`.claude/**` is excluded** — deleted in the working tree,
being recreated by its owner, no leg writes there. `docs/adr/0*`, `docs/proposals/`,
`docs/research/`, `.claude/sdd/**` are **not touched** (NFR-08).
**Does** Collects the claims that wave's legs invalidated. W1: the Compose inventory, the ClickHouse
version, the auth posture, the gate list, and the test counts **taken from CI's own output**
(REQ-B-09 — not recounted by hand; this is also where the **73-vs-63** flow-ui gap is settled by
printing the real number). W2: the silver object inventory. W3: silver's history story and
flow-ui's dual-source boards. W4: the deployment and TLS posture.
**Proof** `git ls-files '*.md' | xargs grep -ln "<each old fact>"` → the only remaining hits are in
protected records. For W1 specifically:
`grep -rn "clickhouse-server:24.3" README.md CLAUDE.md` → 0;
`grep -rn "generator-python/docker-compose" README.md` → 0;
`grep -rn "otelgen" README.md CLAUDE.md` → only a historical sentence.
**Judgement** **This ticket exists only because `pre-pr-discipline` and ADR-0009 cannot both be
satisfied** (§4): it violates the letter of check 2 by making doc updates lag their code by one leg.
**DEC-I2 must land first.** If the Captain rules the other way, T45–T48 dissolve and every
implementation ticket absorbs its own doc fix — which breaks disjointness instead. There is no
third option and no test decides which rule yields. Separately, "the README is useful" is a review
gate: a reader who has not seen this plan should be able to run the system from it.

---

## 10. What this plan could not determine

1. **`[V-3]`'s `SharedMergeTree` half.** Unverifiable locally — it needs a managed provider. If
   `REPLACE PARTITION` behaves differently there, **E loses its primitive and there is no second
   design that leaves the base tables' engine alone.** DEC-A2 must know this before it chooses
   hosting; T30 declares the edge.
2. **`[V-4]` Compose `include:`** — resolved 2026-10-05 (T03 / `infra/clickhouse/README.md`), with
   the premise reversed: `include:` resolves relative `source:` paths from the **included** file's
   directory, so T12 uses `include:` with the shared file in `infra/clickhouse/`. Measured on
   Compose v5.1.4 only.
3. **NFR-05's three re-measurements** (T36, T37, T38). The house style requires the new figure
   beside the old one in the docstring; those numbers need a running stack.
4. **Whether `sentinel_collector` really needs only `INSERT`.** The `clickhouse` crate may probe
   `system.*` for a table check. REQ-H-06 makes **CI the oracle** (T20) rather than this document.
5. **flow-ui's 73-vs-63 collected-test gap.** Static count is 71 functions + one `parametrize`×3
   = 73; `CLAUDE.md` claims 63. Not resolvable statically — T20 prints the real number and T45
   records it.
6. **`0002`'s grants preceding `0004`'s `silver` database** — marked **[I]** in §0, with a
   one-line `[V]` to run alongside T03's probe.
7. **`SPEC`'s `0004`-vs-`0006` numbering inconsistency** for the view re-point, resolved here in
   favour of `0006` (§0). If Pod 3 disagrees, only the filename changes.

---

## Correction note — 2026-10-05

Two count claims in this plan were wrong.

- **36 of 48** implementation tickets sit behind at least one decision, not 38 (computed from the §1 table by following `Blocked by` edges to a `DEC-*` node). *After* the T22 change below, the figure is **33 of 48**.
- **DEC-I1 blocks 26 tickets transitively; DEC-A3 blocks none** (T05 has no blockers; DEC-A3 shapes only T05's form). This contradicts "Four are W1 blockers in practice: DEC-A1, DEC-A2, DEC-A3, DEC-I1" in §1. In practice DEC-I1 is the W1 blocker; DEC-A2 (12) and DEC-A1 gate W3/W4, and DEC-V3a is folded into DEC-I1.

Other edits made the same day: T22's DEC-A1 blocker was removed (DEC-A1 now blocks 6 tickets, not 10); T40 is Wave 4 in both §4 and §8; DEC-V3a is a consequence of DEC-I1.
