# Core Spec — SDLC cycle following the `sdlc-e2e-review` baseline

> **Implementation-ready.** Hand this to the legs. It is the third document in the chain:
> [`intent/core-intent.md`](../intent/core-intent.md) is the verified As-Is (referenced as
> `CI §n`, never restated); [`intent/design-spec.md`](../intent/design-spec.md) is the
> requirements and design (`DSP §n`). This file is what engineering builds from — exact DDL,
> exact endpoint contracts, exact state transitions, exact grants, and the requirement→seam
> matrix the test plan is built on.
>
> **Evidence discipline, unchanged from DSP.** **[E]** = read out of the tree, with line
> numbers where the line is load-bearing. **[I]** = inference. **[V]** = verify in a throwaway
> container before implementing; §11 lists every one.
>
> **REQ-* IDs are carried forward from DSP §3 unchanged.** Nothing is renumbered. New
> requirements are appended at the end of each candidate's block (`REQ-A-13+`, `REQ-B-12+`,
> `REQ-D-10+`, `REQ-E-11+`, `REQ-H-13+`, `REQ-I-07+`).
>
> **Naming.** Decision IDs here were `ADR-A*`/`ADR-I*`/`ADR-D*` in earlier drafts and in
> `design-spec.md` §9; they are renamed `DEC-*` to match `plan/core-plan.md` and
> `plan/decisions/`. `ADR-0004`-style numbers are real repository ADRs and are unchanged.
>
> *Written 2026-10-05 against HEAD `3af2ee7`. The stack was not run; `.claude/` was read via
> `git show HEAD:.claude/...` only.*

---

## 1. Problem Statement

Sentinel's Phase-1 telemetry spine works and is measured (`README.md` §8). What does not exist
is everything around it that makes it a system someone can operate. Five gaps:

1. **Nothing can be deployed.** No registry, no nameable image, no config/secret delivery path,
   no promotion, and — the keystone — **no way to apply a DDL change to a ClickHouse that
   already holds data**. The only schema path is `docker-entrypoint-initdb.d`, which runs once
   on an empty volume; the only recovery is `make reset`, which destroys it. "Roll back to the
   previous version" names no artifact.
2. **The Python half of the repo gates nothing.** 246 Python test functions and 18 silver SQL
   assertions run on a laptop and nowhere else (issue #34). The WoW claims seven CI gates;
   `mypy` appears **zero times** in the repository and flow-ui has no `[tool.ruff]` section, so
   the gates are not stale — they were never authored.
3. **Silver stops short of the Watchers.** The rolling-stats rollup is a recompute-on-read
   `VIEW` (`infra/clickhouse/init.d/02-silver-layer.sql:187`) **[E]**, and the three read models
   the first Watchers need — volume, contract/schema presence, call edges — do not exist.
4. **Silver cannot be given history.** The MVs do not `POPULATE` by design
   (`02-silver-layer.sql:7-9`) **[E]**. Measured on a live stack: 1,703,050 bronze trace rows
   over 36 h against 12,849 silver rows over 12 min (`clickhouse.py:362-376`) **[E]**. Moving
   flow-ui's boards across today silently drops 36 hours of evidence (issue #37).
5. **The security posture is a dev-only shortcut with a committed credential.** `default` is
   passwordless and opened to `::/0` (`infra/clickhouse-users.d/zz-default-network.xml`)
   **[E]**; a vestigial `otelgen` user ships with the plaintext password `otelgen_secret` in two
   files **[E]**; there is zero TLS code in the collector.

Under all five sits a structural one: **four Compose files, three of which define a ClickHouse,
on two engine versions** — so CI tests the DDL on an engine the local stack does not run.

## 2. Solution

Six candidates, in four waves, on four test seams — three of which already exist — so the work
is verifiable from the first leg rather than the last.

- **A** closes the deployment gap with the pieces *invariant to the compute form* — registry,
  signing, provenance, OIDC, config/secret-by-file, digest promotion — plus the keystone: a
  versioned, checksum-guarded ClickHouse migration runner that works where `init.d` does not
  exist. The compute form itself goes to an ADR and does not block.
- **B** *authors* the Python gates (not a restoration) and stands up the live-ClickHouse job
  that D, E and H all need as their oracle.
- **D** completes silver: a storage-backed rolling-stats rollup behind the existing view name,
  and three Watcher read models carrying no threshold, no band and no verdict.
- **E** gives silver its history through an idempotent, range-controlled, partition-recompute
  backfill, and migrates flow-ui's three bronze-derived boards behind a *coverage check*, not a
  flag day.
- **H** replaces the passwordless `::/0` posture with three least-privilege roles proven by CI,
  moves the collector's credential to a `password_file`, and sequences TLS per hop behind the
  decisions it depends on.
- **I** collapses three ClickHouse definitions into one at one version, deletes the Compose
  file carrying the plaintext credential, and ends the port-8080 collision.

The organising idea: **every requirement lands on one of four seams, and the seam is named in
the requirement.** Where no seam can catch a failure, this spec specifies a *prohibition*
instead of pretending a test exists (§8.6).

## 3. User stories

1. As a Pod-3 engineer, I want to apply a silver DDL change to a ClickHouse that already holds
   30 days of bronze, so that a schema change stops meaning data loss.
2. As a Pod-2 engineer, I want the collector to read its ClickHouse credential from a mounted
   file, so that the config file can stay in git under review while the secret never does.
3. As a Watcher author, I want `sample_count`, `sum_value` and `sum_squares` per minute per
   series, so that I can compute a z-score over any window without scanning raw observations —
   and without silver having already decided what is anomalous.
4. As a flow-ui viewer, I want the Watchers board to keep showing 36 hours of volume history on
   the day silver's rollups go live, so that the migration is invisible to me.
5. As an operator, I want `make backfill-silver` to refuse a range that includes today, so that
   nobody loses live rows to a partition swap by typing a date wrong.
6. As the Captain, I want a deploy to name an immutable digest signed by CI, so that "roll
   back" is an operation rather than a rebuild.

---

## 4. Corrections and sharpenings carried into this spec

DSP §0 carries four corrections to `core-intent.md`; all four stand. This spec adds six more,
five of which change a requirement.

| # | Claim | Actually | Evidence | Consequence |
|---|---|---|---|---|
| 5 | DSP §8 R-03: a backfill that destroys a live silver row is **silent**, because the 18 assertions "compare totals that are both wrong in the same direction" | **Wrong — the failure is loud and permanent.** `infra/clickhouse/tests/02-silver-layer.test.sql:16-33` are **exact equalities between silver and bronze**, not silver-to-silver. A destroyed silver row leaves its bronze row untouched, so `count(silver.log_events) != count(bronze.otel_logs)` and stays unequal for the TTL lifetime of that partition | **[E]** `02-silver-layer.test.sql:16-21, 22-27, 28-33` | R-03's *severity* drops (the loss is detected) but its *irreversibility* does not: detection happens after the fact and the evidence is gone. The response is still a prohibition, not a test — §8.4 |
| 6 | REQ-E-03 (row-identical backfill output) is phrased as a property to test | **Promoted to MANDATORY, and it is the only check with teeth.** Count equality is blind to content divergence at constant cardinality: a `Map` column copied with a different key order, a `Float64` computed by a different expression, a wrong `metric_kind` — all pass all 18 assertions | **[E]** §8.3; the determinism result below | REQ-E-03 changes level from "a backfill MUST produce rows byte-identical" (already MUST) to **MUST be verified by an order-insensitive content checksum on every backfilled partition, in the runner, not only in a test** — new REQ-E-11 |
| 7 | "verify the six MV bodies for determinism" | **There are five materialized views in the repository, not six** — four in silver, one in bronze. The "six" are the six plain read `VIEW`s. Full result in §8.3 | **[E]** `grep -rn "MATERIALIZED VIEW" infra/` → `01-bronze-otel.sql:79`; `02-silver-layer.sql:43, 95, 143, 165` | The four silver MVs are deterministic, so correction 6 is sound. `bronze.otel_traces_trace_id_ts_mv` is **not**, and that bounds what the backfill may touch — §7.5 |
| 8 | DSP R-04 / §4.H.2: `rust-toolchain.toml:19` adds only the x86_64 musl target, so an arm64 TLS build breaks the team's machines | **Line 17, and the gap is narrower and differently shaped.** `Dockerfile:22-35` maps `TARGETARCH` to its own musl triple and runs `rustup target add` *inside the builder*, so the **image** build already handles arm64 natively. The two real gaps are: (i) `rust-ci.yml:119-132`'s `docker-build` passes **no `platforms:`**, so arm64 is never built in CI at all; (ii) `rust-toolchain.toml:17` lacks `aarch64-unknown-linux-musl`, so the *host-side* spike (`cargo build --target aarch64-...`) fails until someone adds the target | **[E]** `rust-toolchain.toml:17`; `Dockerfile:22-35, 60`; `rust-ci.yml:119-132` | The spike is still first-wave and still decides DEC-A4, but it is a **CI matrix + toolchain** change, not a Dockerfile rewrite — REQ-H-13 |
| 9 | DSP §4.D.2(a) proposes `volume_1m` keyed `ORDER BY (service_name, window_start)`, mirroring bronze | **Wrong key for the actual query.** `clickhouse.py:273-277` filters on **time only** — there is no `ServiceName` predicate anywhere in `volume_band`; the service is a `GROUP BY` **[E]**. Leading with `service_name` puts the only filtered column second | **[E]** `clickhouse.py:272-290`; `01-bronze-otel.sql:122` | All three new rollups lead with `window_start` — §6.3. This is the one place this spec contradicts DSP's design, and it is a correction, not a preference |
| 10 | DSP and three docstrings call the band function `pipeline._volume_state` | It is **public**: `volume_state`, `services/flow-ui/src/flow_ui/pipeline.py:78` | **[E]** `pipeline.py:78`; stale references at `clickhouse.py:251`, `pipeline.py` docstrings, `static/app.js:1874` | Cosmetic, but S2 is named on it — the seam is `volume_state`, and the stale name is fixed in the same leg that touches those docstrings (REQ-E-09's leg) |

---

## 5. Requirements

RFC-2119 senses. **Seam** names which of S1–S4 (§8) makes the requirement testable; `—` means
no automated seam exists and the requirement is satisfied by a prohibition or a review gate,
which is said explicitly.

### 5.1 A — deployment gap

| ID | Req | Level | Seam |
|---|---|---|---|
| REQ-A-01 | All three service images MUST be published to one OCI registry tagged with the immutable git SHA, plus a mutable channel tag (`:main`, `:vX.Y.Z`). No `:dev`/`:latest` in any deployed environment. | MUST | S4 |
| REQ-A-02 | Every published image MUST carry a provenance attestation and an SBOM and MUST be signed; deployment MUST verify the signature before admitting the image. | MUST | S4 |
| REQ-A-03 | CI MUST authenticate to the registry via short-lived federated credentials (GitHub OIDC → Workload Identity Federation). No long-lived service-account key may exist in a GitHub secret. | MUST | S4 |
| REQ-A-04 | A versioned ClickHouse DDL migration runner MUST exist, applying ordered append-only files and recording applied versions **in the database**; idempotent; MUST work against a ClickHouse with no `docker-entrypoint-initdb.d`. | MUST | S1 |
| REQ-A-05 | The `init.d` boot path MUST keep working unchanged for the local stack (`make up` stays one step) and for `rust-ci.yml:93`. | MUST | S1 |
| REQ-A-06 | Configuration MUST be delivered as files, not environment variables; secrets MUST be delivered as mounted files referenced **by path** from config. | MUST | S3 |
| REQ-A-07 | At least two promotion stages (`staging`, `prod`) MUST exist, promoting **the same image digest**. Rebuild-on-promote is forbidden. | MUST | S4 |
| REQ-A-08 | Infrastructure MUST be declared as code in-repo with no manual console step in the documented path. | MUST | — (review gate; DEC-A1 sets the target) |
| REQ-A-09 | A deploy MUST apply DDL migrations as a distinct step that reaches terminal success **before** any ingest workload starts. | MUST | S1 |
| REQ-A-10 | Compute form and ClickHouse hosting MUST NOT be chosen inside an implementation leg (DEC-A1, DEC-A2). Work invariant to them MAY proceed first. | MUST | — (process) |
| REQ-A-11 | flow-ui SHOULD be deployable and un-deployable independently, in any order, with nothing depending on it. | SHOULD | S2 |
| REQ-A-12 | The collector's readiness MUST be determined **without executing anything inside its container** — an external HTTP probe against `:9090/metrics`. | MUST | S1 |
| **REQ-A-13** | **NEW.** The migration runner MUST refuse to apply a file whose checksum differs from the recorded one for that version, MUST exit non-zero, and MUST name both checksums. Migrations are append-only; a changed file is a mistake, not an edit. | MUST | S1 |
| **REQ-A-14** | **NEW.** The runner MUST be the only writer of `_meta.schema_migrations`, MUST record `applied_at`, `checksum`, `duration_ms` and `applied_by`, and MUST NOT delete or update a row. There is no `down` step in this cycle (see §12 R-A). | MUST | S1 |
| **REQ-A-15** | **NEW.** `init.d/0*.sql` and `migrations/NNNN_*.sql` MUST be **one source of DDL with two apply paths** — the `init.d` entries are symlinks to the migration files, byte-identical. A CI assert MUST fail if any `init.d` file's content diverges from its migration counterpart. | MUST | S1 |

### 5.2 B — Python CI coverage (issue #34)

| ID | Req | Level | Seam |
|---|---|---|---|
| REQ-B-01 | A path-filtered workflow MUST run ruff over both Python services on every touching PR, with the same invocation `make lint-generator` / `make lint-flow-ui` uses. | MUST | S1 |
| REQ-B-02 | The same workflow MUST run the generator's unit suite and flow-ui's suite and MUST fail the PR on any failure. | MUST | S1 |
| REQ-B-03 | CI MUST have exactly one definition of how a suite runs: the workflow invokes Make targets, never re-declared pip/pytest lines. | MUST | S1 |
| REQ-B-04 | The 18 silver `throwIf` assertions MUST execute against a live ClickHouse in CI. | MUST | S1 |
| REQ-B-05 | The silver-assert job MUST wait for ingest quiescence before asserting (the assertions are exact bronze↔silver equalities and the collector buffers). | MUST | S1 |
| REQ-B-06 | Both Python services MUST be tested at their declared minimum (`>=3.10` generator, `>=3.11` flow-ui), not only 3.12. | MUST | S1 |
| REQ-B-07 | A Python supply-chain job SHOULD run `pip-audit` and `bandit`, closing the DSP DS-03 asymmetry; warn-only first, then promoted. | SHOULD | S1 |
| REQ-B-08 | `make lint-collector-rust` MUST reach parity with CI's clippy invocation (`-- -D warnings`). `Makefile:99` omits it today, which silently un-denies `expect_used`. | MUST | S1 |
| REQ-B-09 | The static-vs-collected test-count discrepancy MUST be resolved by making **CI output the authoritative number** and updating `README.md`/`CLAUDE.md` from that output. | MUST | S1 |
| REQ-B-10 | The set of required status checks MUST be enumerated in the repo and configured on `main`. | MUST | — (branch protection; recorded in `docs/ci-gates.md`) |
| REQ-B-11 | **Resolved, see §9.** The generator's `tests/integration/` suite MUST be rewritten to target `CLICKHOUSE_URL` and MUST run in the live-ClickHouse job via a new `make test-generator-integration`. The `testcontainers` + `importorskip` form is removed. | MUST (was SHOULD) | S1 |
| **REQ-B-12** | **NEW — CI defect (a).** CI's integration ClickHouse mounts **bronze only** (`services/collector-rust/infra/docker-compose.yml:34`), so the silver DDL is **never exercised in CI**. The CI instance MUST mount the same DDL set the root stack mounts (`docker-compose.yml:19-21`). | MUST | S1 |
| **REQ-B-13** | **NEW — CI defect (b).** `rust-ci.yml:99` runs `cargo test --test clickhouse_roundtrip -- --ignored` only, so `tests/grpc_export_roundtrip.rs:133`'s `#[ignore]`d test **runs nowhere** — the gRPC ingest path, the only path that drives the silver MVs under real inserts, has **zero live coverage**, and both D and E depend on it. The live job MUST run `cargo test --locked -- --ignored` (or enumerate every integration target), and a CI assert MUST fail if an `#[ignore]`d test exists in `tests/` that no job runs. | MUST | S1 |
| **REQ-B-14** | **NEW — CI defect (c).** `CLICKHOUSE_USER: default` + `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "1"` (`services/collector-rust/infra/docker-compose.yml:37-39`) is a **second route to the `::/0` posture**, independent of `zz-default-network.xml`: the entrypoint generates its own users file. REQ-H-02 MUST close both routes, and the CI assert for it MUST exercise both. | MUST | S1 |
| **REQ-B-15** | **NEW.** `make test` MUST NOT acquire a dependency on a running stack. `test-generator-integration` and `test-silver` are live-stack targets and MUST stay out of the `test` aggregate (`Makefile:69`). | MUST | S1 |

### 5.3 D — silver completion

| ID | Req | Level | Seam |
|---|---|---|---|
| REQ-D-01 | The rolling-stats rollup MUST become storage-backed (incrementally maintained) while the name `silver.metric_rollup_1m` and its column contract are preserved for existing readers. | MUST | S1 |
| REQ-D-02 | The rollup MUST retain `sample_count`, `sum_value`, `sum_squares`, `min_value`, `max_value` so mean and standard deviation are additively computable over any window — the Tier-1 z-score *input*, not a z-score. | MUST | S1 |
| REQ-D-03 | A **Volume** read model MUST exist giving rows-per-minute per producer, keyed so a time-window filter is index-accelerated. | MUST | S1 |
| REQ-D-04 | A **Schema/contract** read model MUST exist giving, per producer per minute, total rows and the count of rows carrying each resource-attribute key. It MUST NOT hard-code the required-key list. | MUST | S1 |
| REQ-D-05 | A **call-edge** read model MUST exist giving `src → dst` span and error counts per window. | MUST | S1 |
| REQ-D-06 | The required-resource-key list MUST NOT gain a third copy. flow-ui's own copy (`clickhouse.py:39-45`, duplicated deliberately so drift is visible) remains the reader's authority. | MUST | S1 + S2 |
| REQ-D-07 | No read model may encode a threshold, a band, a verdict, an escalation or a severity. Those are Candidate G. | MUST | S1 (grep assert) |
| REQ-D-08 | New silver DDL MUST be additive (`CREATE … IF NOT EXISTS`) and MUST NOT alter the three existing base tables' engine, `ORDER BY` or partition key. | MUST | S1 |
| REQ-D-09 | The 18 existing silver assertions MUST still pass unchanged after D. | MUST | S1 |
| **REQ-D-10** | **NEW — the ordering hazard D would otherwise ship.** Re-pointing `silver.metric_rollup_1m` at the new storage table breaks assertion `02-silver-layer.test.sql:47-51` (`sum(sample_count) == count(metric_observations)`) on **any existing volume**, because the new MV does not `POPULATE`. The re-point MUST therefore be a **separate migration** (`0006`) that refuses to apply unless `_meta.backfill_runs` records a completed phase-2 for every partition present in `silver.metric_observations`. A fresh volume satisfies this trivially (no partitions, nothing to backfill). | MUST | S1 |
| **REQ-D-11** | **NEW.** `CREATE VIEW IF NOT EXISTS` does **not** update an existing view, so migration `0006` MUST use `CREATE OR REPLACE VIEW`. The runner MUST tolerate a statement that is not `IF NOT EXISTS`-shaped; idempotence comes from the migrations ledger, not from every statement being individually re-runnable. | MUST | S1 |
| **REQ-D-12** | **NEW.** `silver.call_edges_1m`'s body references `now()` (§6.3c) and is therefore **excluded by name** from REQ-E-03/E-11's content checksum and from the backfill. Every other new silver object MUST be deterministic, and a CI assert MUST fail on any `now()`/`today()`/`rand()`/`generateUUID`/`hostName`/`_part` reference in a silver MV body other than `call_edges_1m`'s. | MUST | S1 (grep assert) |

### 5.4 E — backfill + flow-ui migration (issue #37)

| ID | Req | Level | Seam |
|---|---|---|---|
| REQ-E-01 | A backfill MUST be range-controlled (explicit from/to) and MUST default to a range excluding the partition currently receiving inserts. | MUST | S1 |
| REQ-E-02 | A backfill MUST be idempotent: re-running any range leaves the target identical, with no duplicated rows, without requiring a dedup key on the target tables. | MUST | S1 |
| REQ-E-03 | A backfill MUST produce rows byte-identical to those the streaming MV would have produced for the same bronze rows. | MUST | S1 |
| REQ-E-04 | A backfill MUST order its phases so rollups derived from silver base tables are populated **after** those base tables, and MUST NOT assume an MV fires on a partition swap. | MUST | S1 |
| REQ-E-05 | A backfill MUST refuse and exit non-zero if `silver.*` is absent, if target structure ≠ staging structure, or if the bronze partition changed mid-run. | MUST | S1 |
| REQ-E-06 | flow-ui's three bronze-derived derivations MUST move to silver with **no window of reduced history**. | MUST | S2 |
| REQ-E-07 | flow-ui MUST keep tolerating absent `silver.*` (returning `[]`) and MUST additionally tolerate **partially backfilled** silver by falling back to bronze when silver's coverage is shorter than the window the board needs. | MUST | S2 |
| REQ-E-08 | The migration MUST NOT introduce any write from flow-ui and MUST NOT make the backfill a flow-ui responsibility. | MUST | S2 (grep assert) |
| REQ-E-09 | The band/threshold identity MUST be preserved: migrated queries return raw statistics; the band stays computed in `volume_state` (§4 correction 10). | MUST | S2 |
| REQ-E-10 | A documented, testable removal criterion MUST accompany the dual-source fallback so it does not become permanent. | MUST | S2 |
| **REQ-E-11** | **NEW — promotes correction 6.** The runner MUST compute an **order-insensitive content checksum** over every backfilled partition and compare it against the same checksum taken over the MV-produced rows for the same bronze range, **inside the run**, refusing the swap on mismatch. Shape in §6.5. Count equality alone MUST NOT be accepted as proof. | MUST | S1 |
| **REQ-E-12** | **NEW — the prohibition that replaces the untestable race (§8.4).** The backfill runner MUST refuse the live partition **outright, not behind a flag**: any range whose upper bound is ≥ `today()` MUST cause `make backfill-silver` to exit non-zero before issuing a single `INSERT`. There MUST be no override flag, no env var and no `--force`. Backfilling the live partition requires pausing ingest, which is an operator procedure documented in `infra/clickhouse/backfill/README.md`, not a code path. | MUST | S1 |
| **REQ-E-13** | **NEW.** `services/flow-ui/tests/conftest.py` MUST be created, exposing a shared two-coverage response builder, because flow-ui has **no `conftest.py` today** and each test file builds its own fake **[E]** (`find services/flow-ui -name conftest.py` → empty). This path MUST be added to `leg/flow-ui/silver-boards-v1`'s declared paths, which DSP §5.2 omits. | MUST | S2 |
| **REQ-E-14** | **NEW.** The coverage probe MUST be a single query on the 30 s cadence and MUST NOT be issued per board per tick; a probe failure MUST degrade to the bronze path, never to an error (NFR-05). | MUST | S2 |

### 5.5 H — security hardening

| ID | Req | Level | Seam |
|---|---|---|---|
| REQ-H-01 | The vestigial `otelgen` user and its committed plaintext password MUST be deleted from `infra/clickhouse-init.sql:15-17` and from every Compose file. | MUST | S1 (grep assert) |
| REQ-H-02 | The `default` user MUST return to the image's localhost-only restriction; `infra/clickhouse-users.d/zz-default-network.xml` MUST be removed — **and the second route in REQ-B-14 closed with it**. | MUST | S1 |
| REQ-H-03 | Three least-privilege roles MUST exist — writer (collector), reader (flow-ui), migrator (DDL + backfill) — granted the minimum that makes each component's own tests pass. | MUST | S1 |
| REQ-H-04 | The reader role MUST include `SELECT` on `system.tables` and `system.columns`; flow-ui queries both (`clickhouse.py:429, 503, 505`). | MUST | S1 |
| REQ-H-05 | The collector's config MUST gain `user` and `password_file` for ClickHouse, reading the secret from a file, not an env var. | MUST | S3 |
| REQ-H-06 | Grants MUST be **proven by CI**, not asserted: the live jobs connect as the least-privilege roles. | MUST | S1 |
| REQ-H-07 | In a deployed environment all four hops MUST be encrypted in transit. | MUST | — (deploy-time; DEC-A1/A2) |
| REQ-H-08 | OTLP `:4317` MUST NOT be reachable without authentication in a deployed environment. | MUST | — (edge; DEC-A1) |
| REQ-H-09 | Secrets MUST come from a managed secret store, delivered as files, never committed and never passed as a deploy argument. | MUST | S3 + S4 |
| REQ-H-10 | If TLS terminates inside the collector, the dependency change MUST be re-evaluated against the static-musl/distroless property and `deny.toml`, and the Dockerfile's purity claim MUST be corrected if it stops holding. | MUST | S4 |
| REQ-H-11 | A real-telemetry tripwire SHOULD exist: a signal whose `sentinel.synthetic` is not `true` SHOULD be surfaced, not silent. | SHOULD | S1 |
| REQ-H-12 | Container image scanning SHOULD gate the registry push. | SHOULD | S4 |
| **REQ-H-13** | **NEW — replaces DSP R-04's framing (correction 8).** Before DEC-A4 is taken, a spike MUST produce a static musl binary **with the TLS feature enabled** for **both** `x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl`, and MUST run `cargo deny check` against the resulting licence set. This requires (i) adding `aarch64-unknown-linux-musl` to `rust-toolchain.toml:17` and (ii) adding `platforms: linux/amd64,linux/arm64` to `rust-ci.yml`'s `docker-build`, which builds **no arm64 today**. The spike is first-wave and is independent of whether TLS ships. | MUST | S4 |
| **REQ-H-14** | **NEW.** `:9090/metrics` MUST remain unauthenticated on the wire, because it **is** the readiness probe (REQ-A-12) and the probe is invariant to compute form. It MUST NOT be exposed outside the trust boundary; where the platform demands an authenticated probe, that authentication MUST be the platform's own identity, never an application credential embedded in the collector. | MUST | S1 |
| **REQ-H-15** | **NEW.** The `METRICS_PORT` env override rebinds to `0.0.0.0:<port>`, **discarding the host part of a config-supplied `metrics.listen`** (`src/config.rs:373-397`) **[E]**. Deployed configuration MUST set `metrics.listen` in the YAML file and MUST NOT set `METRICS_PORT`, because the env path cannot express a loopback-only bind. | MUST | S3 |

### 5.6 I — housekeeping

| ID | Req | Level | Seam |
|---|---|---|---|
| REQ-I-01 | Exactly one ClickHouse version MUST be pinned across the repository. | MUST | S1 (grep assert) |
| REQ-I-02 | Exactly one ClickHouse service definition MUST exist as source; any second consumer includes it rather than restating it. | MUST | S1 |
| REQ-I-03 | `services/collector-rust/infra/docker-compose.yml` MUST keep working for `rust-ci.yml:93,103` — it is load-bearing. | MUST | S1 |
| REQ-I-04 | CI's integration ClickHouse MUST mount the silver DDL as well as bronze (= REQ-B-12). | MUST | S1 |
| REQ-I-05 | The port collisions between `services/generator-python/docker-compose.yaml` and the root `docker-compose.yml` MUST be eliminated: **8080** (`clickstack` `:41` vs flow-ui `:70`), **4317** (`clickstack` `:42` vs collector `:41`) and **8123** (the generator file's ClickHouse `:12` vs the root ClickHouse `:11`). | MUST | S1 (grep assert) |
| REQ-I-06 | `README.md` is canonical for "how do I run this"; any removed Compose file MUST have its worked examples preserved in the owning service's README. | MUST | — (review gate) |
| **REQ-I-07** | **NEW — the silent break the unification would cause.** `make test-silver` runs `docker compose exec -T clickhouse …` against the service **literally named `clickhouse`** (`Makefile:72`) **[E]**. The single ClickHouse definition MUST keep the service name `clickhouse` in every Compose file that includes it, or **S1 breaks silently** — `make test-silver` would fail to find the service and a wrapper that swallowed the error would report nothing. A CI assert MUST fail if no Compose file defines a service named `clickhouse`. **The assert MUST inspect the merged `docker compose config` output, not the source files:** a local service with the same name as an included one silently wins and `config` exits 0 (measured, Compose v5.1.4, `infra/clickhouse/README.md`), so a source-file grep can pass while the stack runs a different `clickhouse` than the shared definition. | MUST | S1 |
| **REQ-I-08** | **NEW.** The unified definition MUST mount the DDL by the same relative path from every consumer. `services/collector-rust/infra/docker-compose.yml:34` reaches it with `../../../infra/clickhouse/init.d/...`; the `[V-4]` premise that an `include:` shifts the base to the including file is **false** (resolved 2026-10-05, §11.1): Compose resolves relative `source:` paths from the **included** file's directory, so the shared file in `infra/clickhouse/` mounts `./init.d/...` and every consumer gets the same absolute path. T12 uses `include:`; `extends:` rebases identically and offers nothing. `services/collector-rust/infra/docker-compose.yml:34` is affected only if its mount moves into the shared file, in which case its own mount MUST be removed. **[V-4]** | MUST | S1 |

### 5.7 Non-functional

Carried from DSP §3.2 unchanged: **NFR-01** one-dependency setup survives (Docker + `make`,
no host toolchain) · **NFR-02** collector image stays distroless/static/non-root · **NFR-03**
no comment restates the code; a non-obvious choice carries its measurement · **NFR-04** no
front-end framework, bundler or `package.json` in flow-ui · **NFR-05** flow-ui's three
cadences do not get more expensive; a migrated query is re-measured and the new figure
recorded in the docstring · **NFR-06** Python PR gate < 10 min, live job < 20 min ·
**NFR-07** a one-day backfill does not degrade concurrent ingest beyond the recorded
`export_latency` envelope · **NFR-08** no leg edits an ADR/proposal/research record ·
**NFR-09** every commit satisfies Conventional Commits + `-S` + attribution trailer, and
every leg declares disjoint paths · **NFR-10** no secret in the repo, in CI logs, in an image
layer, or in a `docker inspect`.

One addition:

| ID | Req | Level |
|---|---|---|
| **NFR-11** | The migration runner and the backfill runner MUST be bash + `clickhouse-client`, adding **zero** new host or image dependencies (NFR-01, and the same mechanism `Makefile:72` already uses). Neither may require Python, a JVM or a migration framework image. | MUST |

---

## 6. Data models and schema changes

### 6.1 Inventory: new / altered / untouched

**NEW objects** (all `IF NOT EXISTS`; all in `infra/clickhouse/migrations/`):

| Object | Kind | Migration | Candidate |
|---|---|---|---|
| `_meta` | database | `0003` | A |
| `_meta.schema_migrations` | `MergeTree` table | `0003` (self-created by the runner before any file) | A |
| `_meta.backfill_runs` | `MergeTree` table | `0003` | A/E |
| `silver.metric_stats_1m` | `AggregatingMergeTree` table | `0005` | D |
| `silver.metric_stats_1m_mv` | MV → `metric_stats_1m` | `0005` | D |
| `silver.volume_1m` | `AggregatingMergeTree` table | `0005` | D |
| `silver.volume_1m_logs_mv` / `_traces_mv` / `_metrics_mv` | 3 MVs → `volume_1m` | `0005` | D |
| `silver.resource_key_presence_1m` | `AggregatingMergeTree` table | `0005` | D |
| `silver.rkp_1m_logs_mv` / `_traces_mv` / `_metrics_mv` | 3 MVs → `resource_key_presence_1m` | `0005` | D |
| `silver.call_edges_1m` | `MergeTree` table | `0005` | D |
| `silver.call_edges_1m_rmv` | **refreshable** MV → `call_edges_1m` | `0005` | D **[V-3]** |
| `silver.<base>__bf` ×3 | staging tables, created and dropped by the backfill | runtime, not a migration | E |
| ClickHouse roles `sentinel_collector` / `sentinel_reader` / `sentinel_migrator` + 3 users | roles + users | `0002` | H |

**ALTERED objects:**

| Object | Change | Migration | Why |
|---|---|---|---|
| `silver.metric_rollup_1m` | `CREATE OR REPLACE VIEW` — body re-pointed from `silver.metric_observations` to `silver.metric_stats_1m`. **Column contract unchanged**, including `avg_value` and `stddev_value`. | `0006`, gated by REQ-D-10 | REQ-D-01 keeps the name; REQ-D-11 forces `OR REPLACE` |
| `infra/clickhouse-init.sql` | `CREATE USER otelgen` + its two `GRANT ALL`s deleted | file removed from the init path; its `CREATE DATABASE bronze` folds into `0001` | REQ-H-01 |
| `infra/clickhouse-users.d/zz-default-network.xml` | **deleted** | n/a | REQ-H-02 |

**UNTOUCHED — stated explicitly, because REQ-D-08 and REQ-E-02 both depend on it:**

- All seven `bronze.*` tables: engine, `ORDER BY`, `PARTITION BY`, TTL, codecs, skip indexes —
  **no change**. Including the three empty-by-contract tables (histogram, exponential
  histogram, summary), which stay empty: Candidate F is out of scope.
- `bronze.otel_traces_trace_id_ts` and `bronze.otel_traces_trace_id_ts_mv` — **no change, and
  off-limits to the backfill** (§7.5).
- `silver.operation_executions`, `silver.log_events`, `silver.metric_observations`: columns,
  engine, `ORDER BY`, `PARTITION BY`, TTL, codecs, skip indexes — **no change**. The backfill
  works by partition swap precisely so it never needs a DDL change here.
- The four existing silver MVs — bodies **unchanged**; this is what makes REQ-E-03 meaningful.
- `silver.service_health_1m` stays a plain `VIEW`. Its `quantileExact` p50/p95/p99 are **not**
  additively mergeable, and swapping to `quantilesTDigestState` would change the numbers
  flow-ui already draws (`clickhouse.py:380-387`). **Trade given up:** the one view a live
  board reads on a 5 s cadence keeps recomputing. Recorded as a follow-up, not scope.
- The other five read views (`log_health_1m`, `trace_summary`, `telemetry_coverage_1m`,
  `run_summary`, and `metric_rollup_1m`'s *contract*) — unchanged.

### 6.2 `_meta` — the migration ledger and the backfill ledger

The ledger is **the new source of truth for applied DDL**. Before this cycle, "what schema is
deployed?" was answerable only by `SHOW CREATE TABLE` on a live instance; after it, the
answer is a table.

```sql
CREATE DATABASE IF NOT EXISTS _meta;

CREATE TABLE IF NOT EXISTS _meta.schema_migrations
(
    `version`     String,                           -- '0001' … '0006', from the filename
    `filename`    String,
    `checksum`    FixedString(64),                   -- SHA-256 of the file, lowercase hex
    `applied_at`  DateTime DEFAULT now(),
    `applied_by`  LowCardinality(String),            -- git SHA of the runner's commit, or 'initdb'
    `duration_ms` UInt32,
    `runner_host` LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY version;
```

Deliberate choices, each with its cost:

- **No `PARTITION BY`.** The table holds one row per migration — tens of rows for the project's
  lifetime. A partition key would create more parts than rows.
- **No TTL.** Every other table in the repository carries a 30-day TTL; this one must not.
  An audit record that expires cannot answer "when did `0005` land", which is the only
  question it exists for.
- **`ORDER BY version`, not `(version, applied_at)`.** One row per version is the invariant;
  making `applied_at` part of the key would silently permit two rows for one version and turn
  the checksum refusal into a no-op. The cost: a re-apply attempt is a *refusal*, not a second
  row — the attempt is recorded in CI output and the runner's exit code, not in the table
  (REQ-A-14).
- **`FixedString(64)` not `String`.** The length is the format check.

**Runner contract (REQ-A-04, A-13, A-14, D-11):**

1. `CREATE DATABASE IF NOT EXISTS _meta` + the table above, every run, before reading any file.
2. Read `version, checksum` for all recorded rows.
3. For each `migrations/NNNN_*.sql` in filename order:
   - recorded **and** checksum matches → skip, log `already applied`.
   - recorded **and** checksum differs → **print both checksums, exit 3.** No further file is
     attempted (REQ-A-13).
   - not recorded → apply via `clickhouse-client --multiquery`; on success insert the ledger
     row; on failure **exit 4 without inserting**, so the next run retries the same file.
4. Exit 0 only if every file is applied or skipped.
5. Exit codes are part of the contract: `0` ok · `2` cannot reach ClickHouse · `3` checksum
   divergence · `4` a migration failed.

Note what step 3 buys: idempotence lives in the **ledger**, not in the statements. That is
what makes REQ-D-11's `CREATE OR REPLACE VIEW` admissible in a migration.

The backfill's own state (REQ-E-04's phase gate, REQ-D-10's gate, REQ-E-11's checksum
evidence):

```sql
CREATE TABLE IF NOT EXISTS _meta.backfill_runs
(
    `run_id`              String,                    -- the runner's invocation id
    `phase`               Enum8('phase1' = 1, 'phase2' = 2),
    `target_table`        LowCardinality(String),     -- 'silver.log_events', …
    `partition_id`        String,                     -- as system.parts reports it
    `bronze_rows_before`  UInt64,
    `bronze_rows_after`   UInt64,
    `silver_rows_written` UInt64,
    `content_hash`        UInt64,                     -- REQ-E-11, §6.5
    `expected_hash`       UInt64,
    `started_at`          DateTime,
    `finished_at`         DateTime,
    `status`              Enum8('running' = 1, 'ok' = 2, 'failed' = 3, 'refused' = 4)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (target_table, partition_id, started_at);
```

`status = 'refused'` is recorded, not just logged: REQ-E-12's refusal of the live partition
must leave a trace, because "I ran it and nothing happened" is the report that wastes an hour.

### 6.3 The D read models

All three lead with `window_start`. This is correction 9: the queries that will read them
filter on **time and nothing else** (`clickhouse.py:272-277` has no `ServiceName` predicate),
so leading with `service_name` as DSP proposed would put the only filtered column second in
the key. Partition-level pruning is by day in all three; the key gives mark-level pruning
inside the day.

**(a) `silver.metric_stats_1m` — the rolling-stats rollup (REQ-D-01, D-02)**

```sql
CREATE TABLE IF NOT EXISTS silver.metric_stats_1m
(
    `window_start`   DateTime CODEC(Delta(4), ZSTD(1)),
    `scenario`       LowCardinality(String) CODEC(ZSTD(1)),
    `service_name`   LowCardinality(String) CODEC(ZSTD(1)),
    `component_name` LowCardinality(String) CODEC(ZSTD(1)),
    `metric_name`    LowCardinality(String) CODEC(ZSTD(1)),
    `metric_kind`    Enum8('gauge' = 1, 'sum' = 2),
    `sample_count`   SimpleAggregateFunction(sum, UInt64),
    `sum_value`      SimpleAggregateFunction(sum, Float64),
    `sum_squares`    SimpleAggregateFunction(sum, Float64),
    `min_value`      SimpleAggregateFunction(min, Float64),
    `max_value`      SimpleAggregateFunction(max, Float64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, scenario, service_name, metric_name, component_name, metric_kind)
TTL window_start + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.metric_stats_1m_mv
TO silver.metric_stats_1m
AS SELECT
    toStartOfMinute(event_time) AS window_start,
    scenario,
    service_name,
    component_name,
    metric_name,
    metric_kind,
    toUInt64(count())     AS sample_count,
    sum(value)            AS sum_value,
    sum(value * value)    AS sum_squares,
    min(value)            AS min_value,
    max(value)            AS max_value
FROM silver.metric_observations
GROUP BY window_start, scenario, service_name, component_name, metric_name, metric_kind;
```

`SimpleAggregateFunction` rather than `AggregateFunction` + `-State`/`-Merge`: readers need no
combinators, so `0006`'s view body stays legible and the 18-assertion regression guard
(`02-silver-layer.test.sql:47-51`) keeps working on a plain `sum()`.

Migration `0006` re-points the existing view, column contract intact:

```sql
CREATE OR REPLACE VIEW silver.metric_rollup_1m AS
SELECT
    window_start, scenario, service_name, component_name, metric_name, metric_kind,
    sum(sample_count) AS sample_count,
    sum(sum_value)    AS sum_value,
    sum(sum_squares)  AS sum_squares,
    min(min_value)    AS min_value,
    max(max_value)    AS max_value,
    sum_value / sample_count AS avg_value,
    sqrt(greatest(0, sum_squares / sample_count - pow(sum_value / sample_count, 2)))
        AS stddev_value
FROM silver.metric_stats_1m
GROUP BY window_start, scenario, service_name, component_name, metric_name, metric_kind;
```

The `greatest(0, …)` is not decoration: on a near-constant series, catastrophic cancellation
in `E[x²] − E[x]²` can make that expression marginally negative, where `stddevPop` in the
current body cannot. The 1e-9 agreement test (§8.2) is what pins it.

**(b) `silver.volume_1m` — the Volume read model (REQ-D-03)**

```sql
CREATE TABLE IF NOT EXISTS silver.volume_1m
(
    `window_start` DateTime CODEC(Delta(4), ZSTD(1)),
    `service_name` LowCardinality(String) CODEC(ZSTD(1)),
    `signal`       Enum8('log' = 1, 'trace' = 2, 'metric' = 3),
    `rows`         SimpleAggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, service_name, signal)
TTL window_start + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.volume_1m_logs_mv TO silver.volume_1m
AS SELECT toStartOfMinute(event_time) AS window_start, service_name,
          CAST('log', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
          toUInt64(count()) AS rows
   FROM silver.log_events GROUP BY window_start, service_name;
-- …_traces_mv FROM silver.operation_executions with 'trace'
-- …_metrics_mv FROM silver.metric_observations with 'metric'
```

Carrying `signal` keeps `otel_logs`-only semantics available — which is exactly what
`volume_band` uses today (`clickhouse.py:274`) — while making the other two available without
a second table. **Why not re-aim `volume_band` at `silver.log_events` directly:** its
`ORDER BY (scenario, service_name, component_name, severity_number, event_time, trace_id)`
(`02-silver-layer.sql:91`) puts `event_time` **fifth**, so a window filter prunes only to the
day — a measurable regression against bronze's recorded 0.135 s (`clickhouse.py:260-263`).

**(c) `silver.resource_key_presence_1m` — the Schema/contract read model (REQ-D-04, D-06)**

Key-list **agnostic**, and that is load-bearing. flow-ui keeps its own
`REQUIRED_RESOURCE_KEYS` "duplicated deliberately: this is the *reader's* copy, and if the two
ever disagree the board should show what the collector is actually enforcing"
(`clickhouse.py:36-45`) **[E]**. A key list in Pod 3's DDL would be a **third** copy and would
make flow-ui draw Pod 3's opinion instead of its own.

```sql
CREATE TABLE IF NOT EXISTS silver.resource_key_presence_1m
(
    `window_start` DateTime CODEC(Delta(4), ZSTD(1)),
    `service_name` LowCardinality(String) CODEC(ZSTD(1)),
    `signal`       Enum8('log' = 1, 'trace' = 2, 'metric' = 3),
    `rows`         SimpleAggregateFunction(sum, UInt64),
    `key_counts`   SimpleAggregateFunction(sumMap, Map(String, UInt64))  -- [V-2]
)
ENGINE = AggregatingMergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, service_name, signal)
TTL window_start + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.rkp_1m_logs_mv TO silver.resource_key_presence_1m
AS SELECT
    toStartOfMinute(event_time) AS window_start,
    service_name,
    CAST('log', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
    toUInt64(count()) AS rows,
    sumMap(
        CAST(
            (mapKeys(resource_attributes),
             arrayResize(CAST([1], 'Array(UInt64)'), length(mapKeys(resource_attributes)), toUInt64(1))),
            'Map(String, UInt64)'
        )
    ) AS key_counts
FROM silver.log_events
GROUP BY window_start, service_name;
-- two siblings over silver.operation_executions and silver.metric_observations
```

The reader computes `missing[k] = rows - key_counts[k]` from **its own** list — property
preserved — and the unindexed `Map` probe across four live bronze tables (measured 1.26 s over
~6 M rows, with the `ARRAY JOIN` form at 6.4 s, `clickhouse.py:191-196`) **[E]** becomes a
scan of a rollup two orders of magnitude smaller.

`sumMap` returns `Map(String, UInt64)` on the pinned engine. Although the input key array is
`LowCardinality(String)`, declaring the aggregate column with LowCardinality keys fails the
engine's return-type compatibility check (`sumMap` returns `Map(String, UInt64)`). **[V-2]**
`SimpleAggregateFunction(sumMap, Map(K, V))` support is version-dependent. Fallbacks
in preference order: (i) `AggregateFunction(sumMap, Map(…))` with `sumMapMerge` at read; (ii)
the older `Tuple(Array(K), Array(V))` pair with `sumMap(keys, values)`. Verify on the version
REQ-I-01 picks, before writing the MVs.

One semantic the reader must absorb: `rows - key_counts[k]` answers *rows missing key k*, and
the **sum over k is not the number of bad rows** — a row missing four keys is one bad row, not
four. `clickhouse.py:197-200` records that reporting the sum made a producer missing 4 of 5
keys read "80%" **[E]**. The rollup cannot reconstruct `countIf(NOT (has_all))` from
`key_counts` alone, so the `bad` column keeps coming from the bronze path until a future
`rows_missing_any SimpleAggregateFunction(sum, UInt64)` column is added — **named as a known
limitation, not a silent one**, and it is why E's contract board keeps its bronze fallback
longest.

**(d) `silver.call_edges_1m` — the call-edge read model (REQ-D-05, D-12)**

**This cannot be an incremental MV, and that is a hard fact.** An MV sees only the rows of the
current insert block; a call edge is a self-join between a child span and its parent, which
routinely sit in different blocks and different batches. `clickhouse.py:311-331` records the
cost of getting the join wrong: joining on `SpanId` alone invented **eight non-existent
edges** (the seeded RNG repeats ids across runs), and without collapsing parents to one row
per `(TraceId, SpanId)` a 15-minute window produced **445,229 joined rows from 16,154
children** — a 27.6× fan-out that made edge width encode run history instead of traffic **[E]**.

```sql
CREATE TABLE IF NOT EXISTS silver.call_edges_1m
(
    `window_start` DateTime CODEC(Delta(4), ZSTD(1)),
    `src_service`  LowCardinality(String) CODEC(ZSTD(1)),
    `dst_service`  LowCardinality(String) CODEC(ZSTD(1)),
    `spans`        UInt64,
    `errors`       UInt64
)
ENGINE = MergeTree
PARTITION BY toDate(window_start)
ORDER BY (window_start, src_service, dst_service)
TTL window_start + toIntervalDay(2)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.call_edges_1m_rmv
REFRESH EVERY 1 MINUTE
TO silver.call_edges_1m
AS WITH parents AS (
       SELECT trace_id, span_id, any(service_name) AS src
       FROM silver.operation_executions
       WHERE event_time >= now() - INTERVAL 24 HOUR
       GROUP BY trace_id, span_id          -- one row per (trace, span): the 27.6× guard
   )
   SELECT toStartOfMinute(c.event_time) AS window_start,
          p.src AS src_service,
          c.service_name AS dst_service,
          toUInt64(count())            AS spans,
          toUInt64(countIf(c.is_error)) AS errors
   FROM silver.operation_executions AS c
   INNER JOIN parents AS p
          ON c.trace_id = p.trace_id AND c.parent_span_id = p.span_id   -- trace_id too: the 8-phantom guard
   WHERE c.event_time >= now() - INTERVAL 24 HOUR
     AND c.parent_span_id != ''
   GROUP BY window_start, src_service, dst_service;
```

Three decisions and what each costs:

- **Full replace, bounded to a trailing 24 h.** A refreshable MV without `APPEND` atomically
  replaces its target. Over 30 days that recompute would be expensive; over 24 h it is small,
  and flow-ui's `call_edges` default window is **15 minutes** (`clickhouse.py:311`) **[E]**, so
  24 h is ample. **Cost: `call_edges_1m` holds 24 h of history, not 30 days.** The table's own
  TTL says so rather than leaving it implicit, and the Watchers board's edge view is a
  short-window view by nature.
- **It references `now()`, so it is the one non-deterministic silver object.** That is why
  REQ-D-12 names it as the single exception to the determinism assert and excludes it from the
  backfill and the checksum. It needs no backfill: each refresh recomputes from scratch, which
  is also its rollback (drop it; the next refresh rebuilds).
- **[V-3]** refreshable-MV maturity. If the version REQ-I-01 picks still marks them
  experimental, the fallback is a scheduled `INSERT` + partition swap reusing the backfill's
  primitive — costing a scheduler per environment but no new concept. **This is a concrete
  reason to converge on the newer engine (§6.7), not an abstract one.**

### 6.4 `[V-1]` — the assumption all of D rests on, and its named fallback

`metric_stats_1m_mv`, the three `volume_1m` MVs and the three `rkp_1m` MVs all read **silver
base tables that are themselves MV targets** (`02-silver-layer.sql:43, 95, 143, 165`). D
assumes a materialized view attached to table `T` fires on inserts into `T` *including inserts
produced by another MV writing `TO T`* — chained MV firing.

**Status: UNVERIFIED. It gates all of D.** Do not write a line of `0005` before the probe
returns.

**Named fallback if it is false:** every D rollup reads **bronze** directly instead of silver,
re-paying the unindexed `Map` probe the silver layer exists to avoid (1.26 s over ~6 M rows)
and losing the typed-dimension benefit — a material redesign of `0005`, not a tweak. In that
world `metric_stats_1m` reads `bronze.otel_metrics_gauge` + `bronze.otel_metrics_sum` through
two MVs instead of one, `volume_1m` reads four bronze tables through four, and
`resource_key_presence_1m` reads four bronze tables through four, each re-deriving
`service_name` from `ServiceName` and `scenario` from `ResourceAttributes['sentinel.scenario']`.
REQ-E-03's checksum survives that change; REQ-D-06 survives it; NFR-05 is the casualty.

Marked **[V]** here and in §11, consistently with DSP.

### 6.5 The backfill primitive, and REQ-E-11's checksum

**Chosen: partition recompute + `REPLACE PARTITION`.** Idempotent *by construction*, and the
argument is one sentence: each silver MV body is **row-wise** — one bronze row projects to
exactly one silver row, no aggregation, no join (`02-silver-layer.sql:43-65, 95-114, 143-185`)
**[E]** — therefore `silver_partition = f(bronze_partition)` is a pure function and a full
recompute is correct regardless of what the partition previously held. Nothing needs to know
whether a previous run half-finished.

Rejected: `ReplacingMergeTree` + a version column (breaking DDL change on live tables; taxes
every future reader with `FINAL` or `argMax` forever); `ALTER … DELETE` then `INSERT` (async
mutation, not atomic).

Per `(table, partition)`:

```sql
CREATE TABLE IF NOT EXISTS silver.log_events__bf AS silver.log_events;

INSERT INTO silver.log_events__bf
  <the MV's SELECT verbatim, from 02-silver-layer.sql:97-114>
  WHERE TimestampDate = {d};                                   -- REQ-E-03

-- REQ-E-11: order-insensitive content checksum, both sides, before the swap
SELECT sum(cityHash64(*)) FROM silver.log_events__bf WHERE toDate(event_time) = {d};
SELECT sum(cityHash64(*)) FROM silver.log_events      WHERE toDate(event_time) = {d};

-- REQ-E-05 guard: bronze partition row count unchanged since the staging SELECT began
ALTER TABLE silver.log_events REPLACE PARTITION {d} FROM silver.log_events__bf;
ALTER TABLE silver.log_events__bf DROP PARTITION {d};
```

Why **order-insensitive**: `silver.metric_observations` receives rows from **two** MVs (gauge
then sum, `02-silver-layer.sql:143, 165`), so physical row order inside a part is not a
property of the data. `sum(cityHash64(*))` over the partition is commutative, covers every
column including the `Map`s, and is comparable across a staging table and a live one.
`groupBitXor` is the alternative if a pathological collision is ever observed; `sum` is chosen
because it is one function and reads in a review.

Two details the implementation gets wrong by default:

- **Partition granularity mismatch.** `bronze.otel_logs` partitions by
  `toYYYYMM(TimestampDate)` (`01-bronze-otel.sql:121`) while `silver.log_events` partitions by
  **day** (`02-silver-layer.sql:90`) **[E]**. The logs backfill therefore iterates **silver
  days** and filters bronze by date — it does **not** map partition to partition. Getting this
  backwards swaps a day into a month-shaped slot and is the single most likely implementation
  bug in this cycle.
- **`metric_observations` takes two staging inserts** (gauge then sum) into the same staging
  partition before the one swap.

**Range control (REQ-E-01, E-12).** The partition list comes from ClickHouse, not from bash
date arithmetic:

```sql
SELECT DISTINCT partition FROM system.parts
WHERE database = 'bronze' AND table = {t} AND active
  AND partition >= {from} AND partition <= {to}
ORDER BY partition
```

Default `to` = yesterday. **`to >= today()` is refused with no override (REQ-E-12).**

**Phase ordering (REQ-E-04) — the detail most likely to be missed.** **Materialized views fire
on `INSERT`, not on `ALTER … REPLACE PARTITION`.** A swap into `silver.log_events` does **not**
populate `silver.volume_1m`:

```
phase 1: bronze.*     → silver.operation_executions | log_events | metric_observations   (swap)
phase 2: silver base  → metric_stats_1m | volume_1m | resource_key_presence_1m           (swap)
         call_edges_1m: refresh-driven, never backfilled (REQ-D-12)
```

Running phase 2 before phase 1 completes yields a rollup over partial data **that looks
perfectly healthy**. The runner enforces the order and refuses phase 2 for any partition
phase 1 has not recorded `status='ok'` for in `_meta.backfill_runs`.

Form: `infra/clickhouse/backfill/backfill.sh` + per-table SQL templates, exposed as
`make backfill-silver FROM=YYYY-MM-DD TO=YYYY-MM-DD [PHASE=1|2|all]`. Bash +
`clickhouse-client` (NFR-11). It is an `infra/` artifact, not a service, so it touches no
service's toolchain and **flow-ui is not involved at all** (REQ-E-08).

### 6.6 Indexes, codecs, TTL — the conventions this spec follows

Read off the existing DDL and applied uniformly to every new object:

| Convention | Source | Applied |
|---|---|---|
| `ttl_only_drop_parts = 1` with a 30-day event-time TTL | `01-bronze-otel.sql:64` etc.; `02-silver-layer.sql:41, 93, 141` | all new rollups, except `call_edges_1m` (2 days, §6.3d) and `_meta.*` (none) |
| `index_granularity = 8192` explicit | all existing tables | all new tables |
| `CODEC(ZSTD(1))` on strings/maps; `CODEC(Delta(…), ZSTD(1))` on time columns | `02-silver-layer.sql:15-33` | `Delta(4)` on the new `DateTime window_start` columns (4-byte type → 4-byte delta; the existing `Delta(8)` is for `DateTime64(9)`) |
| `LowCardinality(String)` for dimensions, `Enum8` for closed sets | `02-silver-layer.sql:129` (`metric_kind`) | `signal`, `metric_kind`, `phase`, `status` |
| **No skip indexes on the new rollups** | — | Deliberate: a bloom filter over a table whose primary key already leads with the only filtered column is cost without benefit. Bronze needs `mapKeys`/`mapValues` bloom filters because it is probed by attribute; the rollups are probed by time. |

### 6.7 One ClickHouse version, one definition (REQ-I-01, I-02, I-07, I-08)

Three definitions on two versions: root `24.3` (`docker-compose.yml:7`), CI's integration
`25.4` (`services/collector-rust/infra/docker-compose.yml:26`), the generator's `24.3`
(`services/generator-python/docker-compose.yaml:10`), plus `clickstack-all-in-one:latest`'s
bundled one (`:38-41`) **[E]**. **CI tests the bronze DDL on an engine the local stack does not
run**, and CI's instance has no silver at all (REQ-B-12).

**Converge on 25.4** or the newest pinned minor the hosting choice supports. In order: CI
already runs it so it is the more-tested of the two; `call_edges_1m` needs production-grade
refreshable MVs **[V-3]**; and if DEC-A2 picks managed ClickHouse, the local stack should not
be older than the deployed one. Cost: a `make reset`, which is free — all data is synthetic.

```
infra/clickhouse/compose.clickhouse.yml       # NEW: the single ClickHouse service definition
docker-compose.yml                            # include: it
services/collector-rust/infra/docker-compose.yml   # include: it — same path, CI keeps working
services/generator-python/docker-compose.yaml      # DELETED (§6.8)
```

**The service name stays `clickhouse` in every consumer (REQ-I-07).** `Makefile:72`'s
`docker compose exec -T clickhouse` is S1's entry point for the 18 assertions; rename it and
the seam breaks quietly. **[V-4]** Compose `include:` requires v2.20+. It resolves relative
volume paths from the **included** file's directory (resolved 2026-10-05, §11.1), so the shared
definition lives in `infra/clickhouse/` and writes its mounts as `./init.d/…`;
`services/collector-rust/infra/docker-compose.yml:34` currently reaches the DDL with
`../../../infra/clickhouse/init.d/…` and drops that mount when it includes the shared file.
`extends:` rebases the same way and is not a fallback.

### 6.8 `services/generator-python/docker-compose.yaml` — delete it

It carries the `otelgen`/`otelgen_secret` plaintext credentials (`:7, 15-18, 62-63`), a second
`24.3` ClickHouse, and `clickstack-all-in-one` publishing **`8080:8080`** (`:41`) — the same
host port as flow-ui (`docker-compose.yml:70`), so the two stacks cannot coexist **[E]**.

**Is it a protected historical record?** No, and the distinction is the one
`.claude/rules/pre-pr-discipline.md` draws: the exclusion covers documents that *assert the
past* and carry superseded banners. A Compose file **asserts the present** — an executable
claim about how to run the system, with no banner. Deleting it is in policy; editing an ADR
would not be. Its two worked invocations (`--delivery direct --init-schema`, and the HyperDX
OTLP target with an ingestion key) move into `services/generator-python/README.md` (REQ-I-06).
No code changes: `--delivery direct` stays in the CLI and `OTELGEN_OTLP_API_KEY` stays a
capability.

`services/collector-rust/infra/docker-compose.collector.yml` — the fourth file — is a
golden-fixture FILE-mode overlay with no ClickHouse, unreferenced by CI and by every Make
target. **Leave it:** it documents the FILE-mode path and the TTL caveat at `:13-15` that
§8.1's job design depends on. Deleting it is churn with no drift payoff.

---

## 7. State management

Five distinct pieces of state change in this cycle. Each is specified with its owner, its
transitions, and the invariant that must hold across them.

### 7.1 Applied DDL — from implicit to explicit

| | Before | After |
|---|---|---|
| Where it lives | Nowhere. Implicit in whichever `init.d` files happened to run on the volume's first boot | `_meta.schema_migrations`, one row per version |
| How you read it | `SHOW CREATE TABLE` on a live instance, per object | one `SELECT` |
| Transitions | none (no-op `make init`, destructive `make reset`) | **unrecorded → applied** (insert) and nothing else. No update, no delete (REQ-A-14) |
| Idempotence | per statement, via `IF NOT EXISTS` | **per migration, via the ledger** — which is what admits `CREATE OR REPLACE VIEW` |
| Failure state | partial `init.d` run leaves an undiagnosable mix | migration `N` fails → no row → the next run retries `N`; `N-1` is not re-applied |

**Standing invariant:** the two apply paths execute *the same bytes* (REQ-A-15, `init.d`
entries are symlinks into `migrations/`). The CI assert exists because a copy would drift
within one sprint.

### 7.2 The backfill — range, dedup and idempotence state

- **Range state** is derived, never stored: `system.parts` is the authority on which
  partitions exist (§6.5). The runner holds no cursor, so an interrupted run has no state to
  resume from — and does not need one, because a partition recompute is a pure function.
- **Dedup state: none, by design.** No target table gains a dedup key (REQ-E-02, REQ-D-08).
  Idempotence comes from `REPLACE PARTITION` being a whole-partition substitution.
- **Per-partition evidence** lives in `_meta.backfill_runs`: counts before and after,
  `content_hash` vs `expected_hash`, and `status`. `phase2` reads this table to find its gate
  (REQ-E-04); `0006` reads it to find its gate (REQ-D-10).
- **Staging tables** (`silver.<base>__bf`) are the only mutable intermediate state. They are
  created `AS silver.<base>` — which is what guarantees the structural identity
  `REPLACE PARTITION` requires — and their partition is dropped immediately after each swap, so
  a crashed run leaves at most one stale staging partition, which the next run overwrites.
- **Refused state is recorded** (`status='refused'`), so REQ-E-12's refusal is visible in the
  ledger and not only in a shell exit code.

### 7.3 flow-ui — the in-memory `Snapshot` and what dual-source adds

`Snapshot` (`services/flow-ui/src/flow_ui/pipeline.py:136-240`) **[E]** is a single per-process
dataclass holding one tick: rate maps, the reject matrix, export-latency quantiles, bronze
counts and growth rates, the silver inventory, `service_health`, `call_edges`, `volume`,
`contract_violations`. `history` is a `deque(maxlen=settings.history)` (default 60,
`config.py:46`) **[E]**. It is **per-process and not shared**, which is why REQ-A-11's
deployment must pin flow-ui to one instance: two instances show two histories to two viewers.

Three cadences, unchanged by this cycle (NFR-05):

| Lane | Interval | Reads | Fills |
|---|---|---|---|
| fast | **1 s** (`poll_interval_s`) | collector `/metrics`, bronze `count()` | rates, latency, health verdict, `history` |
| lineage | **5 s** (`lineage_interval_s`) | bronze `GROUP BY`, `silver.service_health_1m`, `silver_state` | `lineage`, `service_health`, `silver`, `volume`, `call_edges` |
| contract | **30 s** (`contract_interval_s`) | the unindexed `Map` probe — measured 1.26 s | `contract_violations` |

**What the dual-source decision adds — exactly three things, no more:**

1. One new field on `Snapshot`: `silver_coverage: dict[str, float]` — `min(event_time)` per
   silver base table, as a unix timestamp. Populated on the **30 s** lane (REQ-E-14), not per
   board and not per tick.
2. A per-board source decision, taken at read time from that field: *silver if
   `coverage[table] <= now() - window`, else bronze.* The three affected methods
   (`contract_violations`, `volume_band`, `call_edges`) gain a branch each; their return shapes
   do **not** change, so `volume_state` (S2) and every template stay untouched.
3. One new field per affected board entry: `source: "silver" | "bronze"`, so the page can say
   which it drew and the removal criterion is observable rather than inferred.

**What it must not add:** no write path (REQ-E-08, grep-asserted), no flag, no operator
switch. The source decision is derived from the state of the thing being drawn — which is the
same property that makes the rest of flow-ui unable to drift from the pipeline.

**Removal criterion (REQ-E-10), restated as a testable predicate:** the bronze path for a
board is deleted in the first PR after `min(event_time)` in its backing silver table has been
≤ `now() - 30 days` — the bronze TTL horizon (`01-bronze-otel.sql:63`) — continuously for 7
days in the target environment. At that point silver can no longer be shorter than bronze,
because both are TTL-bounded to the same window, and the fallback is dead code.

### 7.4 The collector — config-shape-determined mode, and buffer state

**Mode is a function of config shape, not of a flag** (`src/main.rs:60-64`) **[E]**:

```rust
match config.grpc {
    Some(_) => serve_grpc(&config).await,   // server: runs until Ctrl-C
    None    => run(&config).await,          // file: read `input` once, exit
}
```

and within server mode, `config.clickhouse.is_some()` selects **export** vs **log-only**
(`main.rs:88-105`). Three lifecycles from two optional sections. Consequence for A: the
deployed `collector.yaml` must carry **both** sections or the collector silently becomes a
one-shot file reader or a counter that persists nothing. REQ-A-06's per-env config directory is
where that is reviewed.

Buffer and flush state (`src/buffer.rs`) **[E]**:

| Element | Value | Source |
|---|---|---|
| channel capacity | **64 batches**, hard-coded | `buffer.rs:140-141` |
| `batch_size` | 1000 (config, `ClickHouseConfig`) | `config.rs:98-99` |
| `flush_interval_ms` | 500 (config) | `config.rs:103-104` |
| flush attempts | `MAX_FLUSH_ATTEMPTS = 3`, jittered backoff from `BASE_BACKOFF_MS = 100` | `buffer.rs:66, 70` |
| saturation behaviour | `try_send` all-or-nothing → `Status::resource_exhausted`, no partial send | `buffer.rs:156-176`; `grpc.rs:219-222, 293-296, 373-376` |
| terminal failure | batch **dropped** after 3 attempts, logged | `buffer.rs:352-353` |

Two consequences this spec carries forward:

- **REQ-B-05's quiescence check is not optional.** `make generate` returning does not mean the
  collector has flushed; up to 64 batches may be in flight. The check is: read
  `sentinel_signals_ingested_total` from `:9090/metrics`, poll until it is unchanged for two
  consecutive 2 s samples **and** `sum(bronze live-table counts) == that total`, cap at 60 s,
  fail printing both numbers. This is better than a sleep because it asserts the invariant the
  recorded snapshot claims (ingested == persisted).
- **The collector does not flush on SIGTERM — an existing defect, not a platform trade-off.**
  `services/collector-rust/src/main.rs:131-141` handles only `ctrl_c` (SIGINT). Observed: the
  image kept running on SIGTERM, exited 0 on SIGINT, and `docker stop -t 12` took the full 12 s
  and exited 137. Filed as luanmorenommaciel/sentinel#45. **Limit:** probed in log-only mode, so
  the flush path itself was not exercised. Once fixed, the flush window still bounds
  `batch_size` and `flush_interval_ms` from above on any platform with a short grace period
  (DEC-A1).

### 7.5 The non-`POPULATE` consequence, as a standing state invariant

`02-silver-layer.sql:7-9` **[E]** is not a deployment note; it is a permanent property of the
system and it must be treated as one:

> **Invariant SI-1.** For every materialized view in this repository, the target's contents
> are a function of the inserts that occurred **after** the view existed — never of the
> source's history. Therefore: (i) silver's coverage can be shorter than bronze's and
> frequently is (measured 12 min vs 36 h); (ii) an empty rollup on a fresh stack is **correct
> and expected**, not a failure, and flow-ui must keep saying so (`Snapshot.silver.present` is
> load-bearing: absent ≠ empty); (iii) any new MV added later inherits the same gap and needs
> the same backfill; (iv) a partition swap is an `ALTER`, not an `INSERT`, so it fires nothing
> downstream (REQ-E-04).

And the one place SI-1 has a sharp edge:

> **`bronze.otel_traces_trace_id_ts_mv` is an aggregating, block-local MV** —
> `SELECT TraceId, min(Timestamp), max(Timestamp) … GROUP BY TraceId` into a plain `MergeTree`
> (`01-bronze-otel.sql:79-89`) **[E]**. Its output depends on how rows were grouped into insert
> blocks, so it is **neither deterministic nor idempotent** under replay: a re-insert of the
> same bronze rows produces *additional* rows with different min/max boundaries. **The backfill
> MUST never insert into `bronze.otel_traces`, and `bronze.otel_traces_trace_id_ts` MUST NOT be
> backfilled by replay.** Nothing in this cycle needs it to be; it is recorded so that the next
> cycle does not discover it the hard way.

---

## 8. Test seams and the testing strategy

Four seams, three of which already exist. **A requirement that cannot be attached to one of
them is specified as a prohibition or a review gate and says so** (§5's `—` rows).

### 8.1 S1 — the Makefile target set (existing, extended)

**What it is:** `Makefile` is the single operator interface; every target runs in Docker as the
invoking UID/GID so no host toolchain is required (NFR-01). CI invokes **the targets**, never
re-declared pip/pytest/cargo lines (REQ-B-03), so there is exactly one definition of how a
suite runs. This nests the silver SQL assertions, `/metrics`, the golden fixture and the
live-ClickHouse job inside one seam.

**Extensions this cycle** (all additive; the `Makefile` owner per wave is named in §10):

| Addition | For |
|---|---|
| `PYTHON_IMAGE ?= python:3.12-slim`, substituted into `test-generator` (`Makefile:79`) and `test-flow-ui` (`:89`) | REQ-B-06 — makes the declared `>=3.10` / `>=3.11` floors testable for the first time |
| `migrate` → `infra/clickhouse/migrate.sh` | REQ-A-04, A-09 |
| `backfill-silver FROM= TO= [PHASE=]` | REQ-E-01, E-02, E-12 |
| `test-generator-integration` | REQ-B-11 |
| `-D warnings` appended to `lint-collector-rust` (`:99`) | REQ-B-08 |
| `infra/clickhouse/tests/03-watcher-models.test.sql` added to `test-silver`'s file set | REQ-D-02…D-07 |

`test-silver` keeps `docker compose exec -T clickhouse` (`Makefile:72`) and the service name
`clickhouse` is therefore a contract (REQ-I-07). New live-stack targets stay **out** of the
`make test` aggregate (REQ-B-15).

**Covers:** B (all), D (all), E's backfill half, H1, I, and A's migration-runner half. **Prior
art:** `make test-silver`'s 18 `throwIf` assertions and `rust-ci.yml:92-103`'s Compose-service
pattern, both reused rather than reinvented.

**Three defects in the existing live-CH job that this cycle fixes** (each now a requirement):

| Defect | Evidence | Requirement |
|---|---|---|
| (a) CI's ClickHouse mounts **bronze only** → the silver DDL is never exercised in CI | `services/collector-rust/infra/docker-compose.yml:34` vs `docker-compose.yml:19-21` | REQ-B-12 / REQ-I-04 |
| (b) CI runs only `--test clickhouse_roundtrip` → `tests/grpc_export_roundtrip.rs:133`'s `#[ignore]`d test **runs nowhere**; the gRPC ingest path — the only path driving MVs under real inserts, which D and E both depend on — has **zero live coverage** | `rust-ci.yml:99`; `grpc_export_roundtrip.rs:133` | REQ-B-13 |
| (c) `CLICKHOUSE_USER: default` + `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "1"` is a **second `::/0` route**, independent of the users.d XML | `services/collector-rust/infra/docker-compose.yml:37-39` | REQ-B-14 |

Defect (b) is the serious one. It means the current CI proves the *file*-mode exporter works
and proves nothing about the gRPC path, while every claim D and E make about MV firing is a
claim about the gRPC path.

**The e2e job's two known hazards, both read out of the tree:**

- **TTL vs the golden fixture.** `services/collector-rust/infra/docker-compose.collector.yml:13-15`
  records that the golden fixture is 2023-dated and its rows are purged on the first background
  merge under the event-time TTL **[E]**. The live job must drive ingest with `make generate`
  (now-relative timestamps), **never** the golden fixture, or counts drift to zero under it.
- **Engine divergence.** Until REQ-I-01 lands, the new job and `rust-ci / integration` test two
  different engines (25.4 vs 24.3). This is why I sequences before B's live job stabilises.

### 8.2 S2 — flow-ui's `_query` choke point + the pure `volume_state` (existing, unchanged)

**What it is:** every ClickHouse read in flow-ui goes through one method — `ClickHouse._query`,
which POSTs the SQL as the raw request body
(`services/flow-ui/src/flow_ui/clickhouse.py:64-74`) **[E]** — and every band/verdict decision
goes through one pure function, `volume_state(row) -> dict`
(`services/flow-ui/src/flow_ui/pipeline.py:78-133`) **[E]**. Faking `_query`'s response text
exercises the whole read path without a database; `volume_state` is pure, so the band is
testable as arithmetic.

**Unchanged by this cycle** — the point: the dual-source migration adds a branch *above*
`_query` and changes nothing *at* it, so every existing flow-ui test stays valid.

**Covers:** E's flow-ui half (REQ-E-06…E-10, E-13, E-14), REQ-D-06's reader half, REQ-A-11.

**What it needs:** `services/flow-ui/tests/conftest.py` (REQ-E-13), because there is **no
`conftest.py`** today and each of the five test files builds its own fake. The shared fixture is
a two-coverage response builder — one set where silver covers the window, one where it does not
— so both branches of every migrated method are asserted in the same shape. **Prior art:**
`tests/test_pipeline.py:156-229` already tests `volume_state` as pure arithmetic across six
scenarios; the new tests follow that form.

**Key assertions:** band numbers identical from either source for the same data (REQ-E-09, and
this is the test that proves the migration is invisible); `[]` on absent silver (existing
behaviour, must not regress); bronze chosen when coverage < window and silver when ≥; and a
permanent grep assert that `flow_ui/**` contains no `INSERT`/`ALTER`/`CREATE` (REQ-E-08).

### 8.3 S3 — the collector's YAML config as `argv[1]` (existing, unchanged)

**What it is:** the collector takes exactly one argument — a YAML file path — and derives
*everything* from that document's shape (`src/main.rs:40-64`) **[E]**. Mode, export target,
validation policy, metrics bind address and logging format are all fields of one reviewable
file, deserialized with `#[serde(deny_unknown_fields)]` on every section
(`src/config.rs:46, 67, 83, 136, 154, 175, 234`) **[E]**, so a typo is a startup failure, not a
silent default.

**Covers:** H's collector-auth half (REQ-H-05, H-15) and A's config/secret flow (REQ-A-06).

**What H adds to the config type — the whole of REQ-H-05:**

```rust
pub struct ClickHouseConfig {
    pub url: String,
    #[serde(default = "default_database")] pub database: String,
    #[serde(default = "default_batch_size")] pub batch_size: usize,
    #[serde(default = "default_flush_interval_ms")] pub flush_interval_ms: u64,
    #[serde(default)] pub user: Option<String>,            // NEW
    #[serde(default)] pub password_file: Option<PathBuf>,  // NEW — a path, never a value
}
```

and the deployed document:

```yaml
clickhouse:
  url: https://ch.<env>.internal:8443
  database: bronze
  user: sentinel_collector
  password_file: /etc/sentinel/secrets/ch_password   # mounted, mode 0400, never in git
metrics:
  listen: "0.0.0.0:9090"      # explicit; see REQ-H-15 — do NOT use METRICS_PORT
grpc:
  listen: "[::]:4317"
contract:
  expected_version: "1.0.0"
  grpc_validation: warn
```

**There is deliberately no `password` field.** A `password_file` indirection is what lets the
config file live in git under review while the secret never does (NFR-10), and it is the only
shape compatible with the `std::env::var` ban (§12 contradiction 1). The loader reads the file
at startup, trims a single trailing newline, and MUST NOT log its contents or its length.

**Testing at S3:** a config fixture per shape. Prior art is `src/config.rs:472-630`'s existing
table of parse tests, which already pin the tri-state default (`grpc_validation_defaults_to_warn`,
`:547`) and the metrics default (`metrics_listen_defaults_to_9090_on_all_interfaces`, `:609`).
New cases: `password_file` absent → no credential sent; present but unreadable → startup
failure with the **path** named and no content; present → credential used, never logged.

### 8.4 S4 — the published image digest and its attestation (NEW)

**What it is:** after `release.yml` builds and pushes, the artifact under test is **the digest
in the registry**, not the working tree. The checks are: the digest exists and is
SHA-tagged (REQ-A-01); `cosign verify` succeeds against the OIDC identity (REQ-A-02); a
provenance attestation and an SBOM are attached (REQ-A-02); the vulnerability scan is clean
(REQ-H-12); promotion moved the **same** digest (REQ-A-07, asserted by comparing digests
pre/post); and the arm64 + x86_64 musl/TLS spike builds and passes `cargo deny` (REQ-H-13).

**Covers:** A's invariant half and REQ-H-12, H-13.

**It cannot be a PR gate, and that is a requirement, not a limitation.** S4 runs on `main` and
on tags only. A `make` target for it would imply a laptop can run it, and the only way a
laptop can authenticate to a registry is a long-lived credential — **exactly the thing
REQ-A-03 deletes**. So S4 has no Make target, by design, and `release.yml` is the only caller.
`rust-ci.yml:129`'s `push: false` stays as the PR-time build check, so a PR from a fork can
never publish.

### 8.5 Requirement → seam matrix

| Seam | Requirements |
|---|---|
| **S1** | A-04, A-05, A-09, A-12, A-13, A-14, A-15 · B-01…B-09, B-11…B-15 · D-01…D-05, D-07…D-12 · E-01…E-05, E-11, E-12 · H-01…H-04, H-06, H-11, H-14 · I-01…I-05, I-07, I-08 |
| **S2** | A-11 · D-06 (reader half) · E-06…E-10, E-13, E-14 |
| **S3** | A-06 · H-05, H-15 |
| **S4** | A-01, A-02, A-03, A-07 · H-09 (delivery half), H-10, H-12, H-13 |
| **none — prohibition or review gate, stated as such** | A-08 (IaC review), A-10 (process), B-10 (branch protection), H-07, H-08 (deploy-time, ADR-gated), I-06 (review), E-12's *race* (see below) |

### 8.6 What remains genuinely uncatchable — and the prohibition that replaces it

DSP §8 R-03 identifies the `REPLACE PARTITION` race: between the staging `SELECT` and the swap,
a late-arriving signal with that day's event timestamp can be MV-inserted into the target
partition and then destroyed by the swap. Three things are true about it, and this spec states
all three rather than shipping a guard dressed as a fix:

1. **The count guard is a heuristic, not a lock.** ClickHouse offers no transaction that makes
   "recompute then swap" atomic against a concurrent MV insert. Comparing the bronze
   partition's `count()` before and after narrows a sub-second window; it does not close it.
2. **R-03's claim that the loss is silent is wrong** (correction 5). The 18 assertions are
   *exact silver↔bronze equalities*, so a destroyed silver row breaks an equality **permanently**
   — the bronze row stays. The failure is loud. It is also *after the fact*, and the evidence is
   already gone.
3. **No seam distinguishes "the race fired" from "the recompute had a bug."** Both present as
   the same broken equality. No test runs inside the sub-second window. And re-running the
   backfill to prove idempotence **erases the evidence** — the second run's output is correct
   by construction, which is precisely why it proves nothing about the first.

**Therefore the spec specifies a prohibition, not a test (REQ-E-12):** the runner refuses the
live partition **outright, not behind a flag**, and `make backfill-silver` with a range
including today **exits non-zero before issuing a single `INSERT`**. No `--force`, no env
override. Backfilling the live partition requires pausing ingest, which is an operator
procedure in `infra/clickhouse/backfill/README.md`, not a code path.

**That refusal is testable at S1**, and it is the only part of this that is: `make
backfill-silver FROM=<yesterday> TO=<today>` must exit non-zero, write no row to any silver
table, and record `status='refused'` in `_meta.backfill_runs`. One assert, no flake, and it
encodes the one thing a reviewer cannot be relied on to remember.

### 8.7 The six-MV determinism check — result

Required by correction 6, because REQ-E-03/E-11's content checksum is only sound if the MV
bodies are deterministic. **Performed statically over both DDL files**
(`grep -rnEi "now\(|today\(|rand|_part|uuid|generateUUID|currentDatabase|hostName|materialize\("`
→ the only hits are `ttl_only_drop_parts`, a substring match) **[E]**.

**There are five materialized views in the repository, not six** (correction 7):

| MV | Shape | Deterministic? | Consequence |
|---|---|---|---|
| `silver.operation_executions_mv` (`02:43-65`) | row-wise projection: `Timestamp`, `addNanoseconds`, `Map` lookups, `lower()`, `Duration/1e6`, `StatusCode = 'Error'` | **Yes** | checksummable |
| `silver.log_events_mv` (`02:95-114`) | row-wise: `Map` lookups, `upperUTF8`, `SeverityNumber >= 17 OR … IN (…)` | **Yes** | checksummable |
| `silver.metric_observations_gauge_mv` (`02:143-163`) | row-wise, `'gauge'` literal into `Enum8`, `if(MetricUnit != '', …)` | **Yes** | checksummable |
| `silver.metric_observations_sum_mv` (`02:165-185`) | row-wise, `'sum'` literal | **Yes** | checksummable |
| `bronze.otel_traces_trace_id_ts_mv` (`01:79-89`) | **aggregating, block-local**: `min/max … GROUP BY TraceId` into a plain `MergeTree` | **No** — output depends on insert-block grouping, and the target has no dedup key, so replay *adds* rows | **Off-limits to the backfill** (§7.5). Nothing in this cycle touches it |

**Result: REQ-E-03 holds and REQ-E-11 is sound.** All four MVs that write the silver base
tables are deterministic, row-wise, and free of `now()`, `today()`, `rand()`, `_part`, UUID
generation, `hostName` and `currentDatabase`. No adjustment to the backfill design is needed.

Two caveats the checksum design already absorbs:

- **The checksum must be order-insensitive.** `silver.metric_observations` receives rows from
  two MVs, so physical order inside a part is not a property of the data — hence
  `sum(cityHash64(*))` (§6.5), not a row-ordered digest.
- **`Map` key order is preserved from the source row**, because all four MVs copy
  `ResourceAttributes`/`SpanAttributes`/`LogAttributes`/`Attributes` wholesale rather than
  rebuilding them. A recompute therefore reproduces the same `Map` bytes. Had any MV
  reconstructed a `Map` from `mapKeys`/`mapValues`, this would not hold.

Beyond the MVs, two findings worth recording because a later cycle will trip on them:

- `silver.call_edges_1m_rmv`, new in this cycle, **is** non-deterministic by construction
  (`now()`), which is why REQ-D-12 names it as the sole exception.
- Of the six plain read **views**, `silver.trace_summary` (`02:251-271`) uses `argMin`,
  `argMax` and `groupUniqArray` — **order-sensitive under ties**. It is a recompute-on-read
  view today, so this costs nothing; **if a later cycle materialises it, its output is not
  checksum-stable** and REQ-E-11's method does not transfer.

---

## 9. REQ-B-11 — the unmade decision, resolved

`services/generator-python/tests/integration/test_e2e_clickhouse.py:21` **brings its own
ClickHouse** via `testcontainers` and `importorskip`s away when the package or the Docker
daemon is missing (`:21-42`) **[E]**. It therefore **does not cross S1's stack at all** —
DSP's REQ-B-11 ("SHOULD run in the live-ClickHouse job") is not implementable as written,
because running that file in the live job would start a *second*, different ClickHouse beside
the one the job booted.

**Decision: rewrite it against `CLICKHOUSE_URL`, and run it in the live job via a new
`make test-generator-integration`.** The `testcontainers` dependency and the `importorskip`
guard are deleted.

Why this and not "move it to the unit job with testcontainers installed":

1. **S1's entire value is one stack.** The live job boots one ClickHouse at the version
   REQ-I-01 pins, with **both** bronze and silver DDL mounted (REQ-B-12), reachable as the
   least-privilege roles (REQ-H-06). A testcontainers instance has none of that: its own
   image tag (evading REQ-I-01's single-version assert), no `init.d` mounts, no silver, and a
   passwordless `default`. It would prove the exporter can write *somewhere*, which is the one
   thing already proven.
2. **NFR-01.** `make test-*` targets run inside a `python:3.12-slim` container; testcontainers
   from inside that container needs the Docker socket mounted into it — a new host prerequisite
   in a repo whose stated strength is Docker + `make` and nothing else.
3. **REQ-I-01 by the back door.** A second image pin inside a Python test file is exactly the
   drift Candidate I exists to end.

**What is given up, named:** the test stops being runnable standalone on a laptop without
`make up` first, and `importorskip` goes away — so a missing ClickHouse becomes a **failure**
rather than a skip. That is the point (a test that skips in CI is issue #34 in miniature), and
it is why the new target stays out of the `make test` aggregate (REQ-B-15): `make test` must
keep working with no stack running.

Requirement as written: **REQ-B-11 (MUST, was SHOULD)** — the generator's `tests/integration/`
suite targets the ClickHouse named by `CLICKHOUSE_URL`, carries no container-management code
and no skip guard, and is invoked by `make test-generator-integration` from the live job only.

---

## 10. Sequencing, legs and declared paths

DSP §5.1's four-wave graph stands. The deltas this spec introduces:

**Wave 0 — decisions, no code:** DEC-A1 (compute form) · DEC-A2 (ClickHouse hosting **and
operational owner**) · DEC-A3 (migration tooling) · DEC-A4 (TLS in-process vs edge) · DEC-I1
(version + Compose deletion) · DEC-I2 (the doc-rule conflict, §12.3) · DEC-D1 (typed resource
keys in silver). **Run as one sync agenda item, not seven documents** — the team's
demonstrated ratification throughput is approximately zero per quarter, and six of seven
existing ADRs are still `Proposed`.

**Wave 1 — four parallel lanes, plus one spike:** B (python-ci + the live job) · I+H1 (compose
unification, version pin, drop `otelgen`, three roles, collector auth) · MIG (migration
runner) · A-inv (registry, provenance, OIDC, `release.yml`). **Plus REQ-H-13's arm64/musl
TLS spike, pulled into wave 1**: it decides DEC-A4, it is independent of whether TLS ships, and
a TLS-enabled musl build that fails on arm64 breaks the team's own machines before any cloud
does.

**Hard blocks, unchanged:** **[V-1]** before any of D · D → E strictly · E phase 1 → phase 2 ·
H1 → H2 · DEC-A1 → A-compute and H2 · DEC-A3 → MIG's form · DEC-I1 → I.

**New hard block:** **REQ-D-10** — migration `0006` (the view re-point) is blocked on E phase 2
for every environment holding pre-existing `silver.metric_observations` partitions. On a fresh
volume it is unblocked trivially. This is the one place D's wave-2 work has a wave-3
dependency, and it is why `0005` and `0006` are separate files.

**Leg path deltas against DSP §5.2:**

| Leg | Change |
|---|---|
| `leg/flow-ui/silver-boards-v1` | **add `services/flow-ui/tests/conftest.py`** (REQ-E-13) — DSP §5.2 omits it, and it is a new shared file, so it must be declared |
| `leg/infra/clickhouse-unify-v1` | add `.github/workflows/rust-ci.yml` (REQ-B-12's mount set and REQ-B-13's test invocation live in the same file the CI compose does) — **or** hand `rust-ci.yml` to `leg/ci/python-gates-v1` and declare it there. **Pick one and write it down before either leg opens**; this is a genuine new collision DSP does not list |
| `leg/collector/ch-auth-v1` | add `services/collector-rust/src/clickhouse_exporter.rs` already listed; **add `rust-toolchain.toml`** if REQ-H-13's spike lands in this leg rather than its own |
| `leg/infra/ch-migrate-v1` | add `infra/clickhouse-init.sql` (deletion) and `infra/clickhouse-users.d/**` (deletion) — these move into migration `0002`, so they belong to MIG, not to the unify leg. **This conflicts with DSP §5.2, which assigns them to `leg/infra/clickhouse-unify-v1`.** Resolve at the swimlane: they must not be in two legs' declared paths |

**Makefile owner per wave:** W1 → `leg/ci/python-gates-v1` (`PYTHON_IMAGE`,
`test-generator-integration`, `-D warnings`, `migrate`) · W2 → `leg/silver/watcher-models-v1`
(the `03-watcher-models.test.sql` file set) · W3 → `leg/silver/backfill-v1`
(`backfill-silver`). `README.md` and `CLAUDE.md` are edited **only** in one docs leg at the end
of each wave — which is the conflict §12.3 escalates.

---

## 11. Verification gates — do not implement past these

> **Status as of 2026-10-05: `[V-1]`, `[V-2]` and `[V-3b]` are VERIFIED PASS. `[V-3a]` is
> PASS on 25.4.13.22 with no settings and gated only on 24.3.18.7 — the earlier
> "experimental-gated on both" claim was a probe error, corrected in §11.1. The
> `SharedMergeTree` half of `[V-3]` remains open. `[V-4]` is RESOLVED but its premise was backwards: the gate as written **fails**
> while the risk it guarded against is gone (§11.1). Measurements and their limits are in §11.1 below — read it before acting on
> the fallback column, which is now partly obsolete.**

| | Assumption | Gates | Fallback if false |
|---|---|---|---|
| **[V-1]** | A materialized view on table `T` fires on inserts into `T` produced by another MV writing `TO T` (chained MV firing) | **all of D** (§6.3, §6.4) | Every D rollup reads **bronze** directly, re-paying the 1.26 s unindexed `Map` probe and losing the typed dimensions. Material redesign of `0005`; REQ-E-11 and REQ-D-06 survive it, NFR-05 does not |
| **[V-2]** | `SimpleAggregateFunction(sumMap, Map(String, UInt64))` is supported on the pinned version | `resource_key_presence_1m` (§6.3c) | (i) `AggregateFunction(sumMap, …)` + `sumMapMerge` at read; (ii) `Tuple(Array(K), Array(V))` |
| **[V-3]** | Refreshable MVs are production-grade (not experimental) on the pinned version; and `REPLACE PARTITION` behaves identically if a managed provider substitutes `SharedMergeTree` for `MergeTree` | `call_edges_1m` (§6.3d); **the entire E primitive** on managed ClickHouse | `call_edges_1m` → scheduled `INSERT` + partition swap (a scheduler per environment, no new concept). For `REPLACE PARTITION` on `SharedMergeTree` there is **no second idea** that does not change the base tables' engine — if it differs, E must be redesigned and DEC-A2 should know that before it chooses |
| **[V-4]** | Compose `include:` is available in the team's Compose version **and** resolves relative volume paths from the including file's directory | REQ-I-02, I-03, I-08 | **RESOLVED 2026-10-05, and the gate as written FAILS:** `include:` is available (Compose v5.1.4) but the base is the **included** file's directory, not the including file's. The risk the gate guarded against (the base shifting under the existing `../../../` mount) is gone, so `include:` is used as planned. `extends:` rebases identically and is not a better fallback |

### 11.1 Probe results — `[V-1]`, `[V-2]`, `[V-3]` RESOLVED 2026-10-05

**Added 2026-10-05 (#46).** The **18 silver assertions in `infra/clickhouse/tests/02-silver-layer.test.sql` PASS on 25.4.13.22, with output byte-identical to 24.3.18.7.** Measured on throwaway containers with `init.d` mounted read-only and synthetic `bronze` rows inserted post-boot so the non-`POPULATE` MVs fired (40/30/25/20 → 40/30/45 in silver, exact). This closes the one open gap in DEC-I1's recommendation to standardise on 25.4. Separately measured: the **24.3 `clickhouse-client` rejects multi-statement `-q`** (`Code: 62`) where 25.4 accepts it, so `migrate.sh` (REQ-A-04, T05) MUST pass `--multiquery` explicitly.

Measured directly, **after** the body of this spec was written, in throwaway `--rm`
`clickhouse/clickhouse-server` containers with no volume mounts and
`CLICKHOUSE_SKIP_USER_SETUP=1`. Run on **both** versions the repo references, with
**identical results on each**: `24.3.18.7` (root `docker-compose.yml`) and `25.4.13.22`
(`services/collector-rust/infra/docker-compose.yml`, the version CI's integration job starts).

| | Probe | Result | Consequence |
|---|---|---|---|
| **[V-1]** | `t1 → mv1 → t2 → mv2 → t3`; one `INSERT` into `t1` | **PASS** — `t3` received 2 rows summing to 8 (= 1+2+5). The second-level MV fired on the insert performed by the first-level MV. **No setting required.** | **D is unblocked.** The bronze-rebuild fallback in the row above is **not needed**; §6.3 and §6.4 stand as written. NFR-05 survives |
| **[V-2]** | `SimpleAggregateFunction(sumMap, Map(String, UInt64))`, two inserts, `OPTIMIZE FINAL` | **PASS** — merged to `{'a':6,'b':2}` | `resource_key_presence_1m` uses the Map-typed shape at §6.3c:500. Neither fallback is needed. `Map(LowCardinality(String), UInt64)` is rejected because it does not match `sumMap`'s return type. |
| **[V-3a]** | `CREATE MATERIALIZED VIEW … REFRESH EVERY 1 HOUR` | **PASS on 25.4.13.22 with no settings; GATED on 24.3.18.7** | **CORRECTED 2026-10-05 (re-probe).** The earlier entry claimed an experimental gate on *both* versions; that was an artifact of probing only with `allow_experimental_refreshable_materialized_view=1` set and never without it. On 25.4.13.22 the `CREATE` succeeds with no settings and the flag reports `Obsolete setting, does nothing` (`system.settings`), confirmed independently twice. The gate is real only on 24.3.18.7. **This makes `[V-3a]` a consequence of DEC-I1, not an independent risk**: on 25.4+ `call_edges_1m_rmv` rests on a stable feature and the scheduled-`INSERT` fallback is unnecessary. `design-spec.md:604-612` was right and this table was wrong. T29 MUST re-assert this in CI against the version DEC-I1 selects |
| **[V-3b]** | `ALTER TABLE p_dst REPLACE PARTITION '202601' FROM p_src` | **PASS** — the destination's pre-existing row was gone; 2 rows summing to 3 | `REPLACE PARTITION` semantics are as §6.5 assumes **on `MergeTree`** |

**Three limits on what these probes prove.** (i) They ran against a **bare** ClickHouse, not
this repo's schema: they establish that the *engine* supports each pattern, **not** that the
five MV bodies in `infra/clickhouse/init.d/` chain correctly — that still needs the live
`make test-silver` run under REQ-D-10. (ii) `CLICKHOUSE_SKIP_USER_SETUP=1` was set, so they say
**nothing** about the roles and grants in §6 or REQ-H-06. (iii) `[V-3b]` was measured on
`MergeTree` only. **The `SharedMergeTree` half of `[V-3]` remains unverified and unverifiable
locally** — it needs a managed provider, and §11's warning stands unchanged: if it differs, E
loses its primitive and there is no second design that leaves the base tables' engine alone.
**DEC-A2 must settle this before E is implemented.**

**`[V-4]` (Compose `include:`) — RESOLVED 2026-10-05; the premise was backwards, and the gate as
written technically FAILS.** Measured on Compose v5.1.4 (full detail in
`infra/clickhouse/README.md`): `include:` resolves relative bind-mount `source:` paths from the
**included** file's directory, not the including file's. Observable: `docker compose config`
printed `source: <scratchpad>/v4/marker/ddl.sql` with both candidate targets present, so Compose
chose the path rather than it being inferred from a missing file. This is not a clean pass: the
gate asserted "from the including file's directory" and that is false. What matters is that the
risk it guarded against is gone: a shared file in `infra/clickhouse/` with `./init.d/...` mounts
resolves identically for every consumer. T12 uses `include:`; `extends:` rebases identically and
offers nothing. `include:` with `project_directory: .` does resolve from the including file, but
is not needed. A second finding, recorded in REQ-I-07: a local service of the same name as an
included one silently wins and `config` exits 0. Limits: one Compose version (v5.1.4); the v2.20
floor was not re-verified.

---

## 12. Policy contradictions that engineering cannot resolve

Six places where two things the repository asserts cannot both be satisfied. For each: the
conflict, what engineering **can** decide, what it **cannot**, and the owner per the
`CLAUDE.md` *Known doc drift* table and README §7 ("components are singly owned; contracts are
jointly owned by the Pods on both sides").

### 12.1 `std::env::var` is banned, and platform config injection is environmental

`services/collector-rust/clippy.toml:10-12` bans `std::env::var` outright, with the reason
written in place: *"Use the Sentinel config loader (figment-based) instead"* — configuration
must be file-sourced and auditable **[E]**. The codebase honours it with exactly two sanctioned
call sites (`src/config.rs:382-394`, `src/clickhouse_exporter.rs:141`), both documented at the
site **[E]**. Every managed platform's config and secret injection, meanwhile, is
environment-based by default: Cloud Run env vars, Kubernetes `env`/`envFrom`, Secret Manager's
env integration.

- **Engineering can decide:** to make the collector's deployed path **entirely file-mounted** —
  YAML as `argv[1]` plus `password_file` — which is what REQ-A-06 and REQ-H-05 specify, and
  which keeps the ban intact with no exemption. Both Cloud Run (secret volumes) and Kubernetes
  (projected volumes) support it.
- **Engineering cannot decide:** whether a *future* platform feature that is env-only — a
  sidecar-injected token, a workload-identity hint, a platform-mandated `PORT` — justifies a
  second exemption boundary, or whether the ban is absolute. The ban's stated reason is
  auditability, which a single audited, documented exemption *module* would also serve; the ban
  as written does not admit one.
- **Note the asymmetry worth stating:** the ban is **Rust-scoped**. flow-ui reads **eight**
  environment variables in `src/flow_ui/config.py:18-46` **[E]** and nothing forbids it. So the
  repository's actual position is "the collector's config must be auditable", not "Sentinel's
  config must be". If the intent is the latter, flow-ui is already in violation and that is a
  separate decision.
- **Owner: Pod 2** (it owns `clippy.toml` and the collector), with the Captain consulted if the
  rule is meant to be repo-wide.

### 12.2 `create_schema:false` requires `init.d`; managed ClickHouse has no `init.d`

The bronze DDL is Pod-3-owned and auto-applies on ClickHouse boot from
`infra/clickhouse/init.d/` — "the collector issues no DDL, it only `INSERT`s" (`CLAUDE.md`
*Conventions*; `01-bronze-otel.sql:1-22`) **[E]**. `docker-entrypoint-initdb.d` is a property of
the **Docker image's entrypoint**. A managed ClickHouse has no entrypoint you control, so the
policy's mechanism does not exist there — while the policy itself (the collector must not issue
DDL) is one the repo should keep.

- **Engineering can decide:** the mechanism. It is the migration runner (§6.2), and the
  convergence trick that keeps both paths honest is REQ-A-15: `init.d/0*.sql` are **symlinks**
  into `migrations/`, so there is one source of DDL and two ways to apply it, with a CI assert
  against divergence. The local stack keeps its zero-step `make up`; `rust-ci.yml:93` keeps
  working; the deployed path gets a `migrate` job that must reach terminal success before the
  collector revision is promoted (REQ-A-09).
- **Engineering cannot decide:** whether a bespoke bash runner is the right long-term tool
  versus an off-the-shelf migration framework or a provider's own tooling — and, underneath it,
  **who operates ClickHouse at all**, which is a staffing decision recorded as unassigned
  (`docs/proposals/canonical-read-schema.md:123`; `git show HEAD:.claude/CLAUDE.md`) **[E]**.
  The hosting choice determines whether the runner is a convenience or the only option.
- **Owner: DEC-A3 → Pod 3** (DDL owner) with Pod 2 consulted; **DEC-A2 → Commander**, because
  the ownership question gates the technology one and not the reverse.

### 12.3 "Fix stale docs in the same PR" vs "every leg declares disjoint paths"

`.claude/rules/pre-pr-discipline.md` check 2: a document that describes something which no
longer exists is broken by the change that made it wrong, and the ones that no longer hold are
fixed **in the same PR**. ADR-0009: every leg declares **disjoint paths** before it opens
**[E]**. A doc fix touches `README.md`, `CLAUDE.md`, the `Makefile` — shared, hot files. The two
rules are jointly unsatisfiable the moment two legs run in parallel.

**It fires immediately.** Wave 1 has four lanes; three of them want the `Makefile`
(`PYTHON_IMAGE`, `migrate`, compose paths), three want `docker-compose.yml`, and **all four**
are obliged by check 2 to update what they invalidated in `README.md` and `CLAUDE.md`.

- **Engineering can decide:** a convention, and this spec picks one — one named `Makefile` owner
  per wave (§10), and `README.md`/`CLAUDE.md` edited only in a single docs leg at the end of
  each wave, collecting that wave's invalidated claims. It works mechanically.
- **Engineering cannot decide:** that this is acceptable. It **violates the letter** of
  pre-pr-discipline ("fix the ones that do not hold in the same PR") by making doc updates lag
  their code by one leg. That is a change to a repo rule, not an engineering judgement.
- **Owner: Captain / Commander** — both documents are theirs, and this is the same class of
  amendment ADR-0009 already has pending. **DEC-I2.**

### 12.4 The WoW names seven CI gates; four of them have never been configured

The WoW asserts ruff · `mypy --strict` · pytest >80% · bandit + safety · markdownlint ·
CodeRabbit · Docker build. Reality: **`mypy` appears zero times** across every `.toml`,
`.cfg`, `.ini` and `.yml` in the repository **[E]**; flow-ui's `pyproject.toml` has **no
`[tool.ruff]` section**, so `make lint-flow-ui` runs ruff on **bare defaults** — 88 columns,
`E`+`F` only — over `src tests scripts` (`Makefile:92`) **[E]**, while the generator pins
`line-length = 120`, `target-version = "py310"`, `select = ["E","F","I","UP"]`
(`services/generator-python/pyproject.toml:36-45`) **[E]**. There is no coverage threshold
anywhere, no `bandit`, no `safety`, no markdownlint config.

**So Candidate B must *author* gates, not restore them, and it is larger than issue #34
implies.** Issue #34 reads as "wire up the existing suites"; the actual work includes writing
flow-ui's ruff configuration (and absorbing the diff from 88→120 columns and from `E,F` to
`E,F,I,UP`), deciding whether `mypy` enters at all and at what strictness on a codebase that
has never been type-checked, and deciding what a coverage threshold means for three suites with
no baseline.

- **Engineering can decide:** the content — the ruff rule set, the `mypy` strictness ladder (and
  whether it starts non-blocking), the coverage floor, and the order in which gates become
  required. REQ-B-07's warn-then-promote pattern is the recommended shape: making an unclean
  new gate required is how a team learns to use `--no-verify`.
- **Engineering cannot decide:** whether the WoW's seven-gate list is a **description to be
  made true** or an **aspiration to be rewritten**. Nine documents assert it; issue #40 found
  that exact drift. If `mypy --strict` is genuinely required, someone must accept the cost of
  typing three untyped codebases; if it is not, the WoW should stop claiming it.
- **Owner: Captain / Commander** for the gate list (it is the WoW); **Pod 1 and the flow-ui
  owner** for their own ruff/mypy configuration.

### 12.5 ADR-0009's merge commit vs the WoW's squash-merge, still unratified

The WoW says squash-merge to `main`; ADR-0009 proposes a **merge commit** for swimlane→`main`
so per-leg attribution survives, and records itself as pending ratification **[E]**. Both are
live documents; `main` is protected either way.

- **Engineering can decide:** nothing. The only engineering-visible consequence is whether a
  wave's legs appear as one commit or several, and both work.
- **Engineering cannot decide:** which rule governs. It matters here because this plan is the
  first multi-leg fleet the repo will run, and the attribution trailer (`Co-Authored-By` naming
  both human and LLM) is **mandatory** — a squash collapses several legs' trailers into one
  commit message, which is the thing ADR-0009's merge commit exists to prevent.
- **Owner: Captain / Commander.** Pending since ADR-0009 was written; this cycle is where it
  stops being hypothetical.

### 12.6 H's TLS-in-collector weakens the property H exists to protect

`services/collector-rust/Dockerfile:3-6` states the dependency tree is pure Rust —
"cityhash-rs + lz4_flex, no `*-sys` / OpenSSL / ring" — and that this is **why** a fully static
musl binary on `gcr.io/distroless/static-debian12:nonroot` is achievable **[E]**.
`core-intent.md §5` calls that image the strongest single artifact in the baseline's security
posture. Adding TLS to the collector adds a TLS implementation, and `rustls` pulls a crypto
provider (`ring` or `aws-lc-rs`), neither of which is pure Rust. If DEC-A2 picks managed
ClickHouse, **client** TLS is not optional.

- **Engineering can decide:** hop 1 (server TLS) is avoided entirely by terminating at the
  platform edge — the generator already has `--otlp-secure` / `--otlp-api-key` /
  `--otlp-header`, so the client side needs no code. For hop 2, engineering can run REQ-H-13's
  spike and produce the facts: does a TLS-enabled static musl binary build on **both**
  `x86_64` and `aarch64`, and does `cargo deny` pass against the new licence set (`ring`'s
  licence terms may need a reviewed `deny.toml` addition — a deliberate change, not a bypass)?
  And engineering can correct the Dockerfile comment, which otherwise becomes a false claim in
  the repo's strongest security artifact (REQ-H-10).
- **Engineering cannot decide:** whether to accept the trade. The failure mode of this security
  item is *weakening security* — if the static aarch64 build fails, the fixes that keep shipping
  (dynamic linking, a non-distroless base) trade away exactly what Candidate H was improving.
  The alternative is a TLS-terminating sidecar: preserves purity exactly, costs a second image,
  a second config and a second thing to patch. **That is a disproportionality judgement about
  the collector's own invariants.**
- **Owner: Pod 2** — it owns the collector, the Dockerfile and `deny.toml`. **DEC-A4.** Note
  NFR-02 already says any change adding a shell, a package manager or a dynamic libc requires
  an ADR; this is that ADR, arriving before the change rather than after.

---

## 13. Endpoint interfaces

Four network surfaces. "Auth before" is the baseline; "auth after H" is what this cycle
changes.

| # | Surface | Method / path | Request | Response | Status / error semantics | Auth before | Auth after H |
|---|---|---|---|---|---|---|---|
| **1** | collector `/metrics`, `:9090` | `/metrics`, **any method** — `src/metrics_server.rs:65` checks the **path only** **[E]** | none | Prometheus text exposition, `Content-Type: text/plain; version=0.0.4; charset=utf-8` (`metrics_server.rs:57`). Five pinned families | `200` render ok · `404 "not found\n"` any other path (`:65-69`) · `500 "internal error rendering metrics\n"` on encode failure (`:80-87`). No `405` | none; binds `0.0.0.0:9090` by default (`config.rs:163, 170`) | **unchanged on the wire, deliberately** — this endpoint **is** the readiness/startup probe (REQ-A-12), invariant to compute form. Not exposed outside the trust boundary; platform-internal TLS only; no application credential (REQ-H-14) |
| **2** | collector OTLP gRPC `:4317` | `opentelemetry.proto.collector.{trace,logs,metrics}.v1.*/Export` | `ExportTraceServiceRequest` / `ExportLogsServiceRequest` / `ExportMetricsServiceRequest` | the matching `Export*ServiceResponse` | `OK` on accept · **`RESOURCE_EXHAUSTED`** when the buffer is saturated, all-or-nothing, with the pending/available counts in the message (`grpc.rs:219-222, 293-296, 373-376`; `buffer.rs:99-102`) **[E]** · `INVALID_ARGUMENT` on malformed OTLP | none; `[::]:4317`, zero TLS code in `grpc.rs`/`config.rs`/`clickhouse_exporter.rs` **[E]** | TLS + authentication at the **platform edge** (REQ-H-07, H-08); the process still speaks h2c inside the boundary and gains no peer identity (DEC-A1's named cost) |
| **3** | ClickHouse HTTP `:8123` | **`POST /`** with the SQL as the **raw body** (flow-ui, `clickhouse.py:64-74` — a url-encoded `query=` makes ClickHouse parse the literal string and fail) **[E]**; RowBinary `INSERT` from the collector's `clickhouse` 0.13 crate; `GET /?query=SELECT+1` as the Compose healthcheck | SQL text / RowBinary rows | `FORMAT TSV` or `FORMAT JSONEachRow` as the query asks | `200` + body · HTTP 4xx/5xx with the ClickHouse error text; flow-ui raises via `raise_for_status()` and each caller degrades to `[]` with a `log.warning` | **passwordless `default`, opened to `::/0`** by `infra/clickhouse-users.d/zz-default-network.xml` **[E]**, plus a **second route** via `CLICKHOUSE_USER` + `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT` in CI's compose (REQ-B-14) **[E]**; a vestigial `otelgen`/`otelgen_secret` with `ALL ON bronze.*` **and** `ALL ON default.*` **[E]** | **`default` back to localhost-only; `otelgen` deleted; three least-privilege roles** (§14.1); collector authenticates with `user` + `password_file`; HTTPS when DEC-A2 picks managed (REQ-H-07, H-10) |
| **4** | flow-ui `:8080` | `GET /` (HTML) · `GET /stream` (**SSE**) · `GET /api/snapshot` · `GET /api/graph` · `GET /api/history` · `GET /healthz` · `GET /static/*` — `src/flow_ui/main.py:95, 110, 141, 147, 168, 179, 63` **[E]** | none (no query parameters, no body, no write verb anywhere) | see below | FastAPI defaults: `200`/`404`/`422`. `docs_url=None, redoc_url=None` (`main.py:62`) — no OpenAPI surface. No CORS header is set anywhere, pinned by a test, which is **why the browser never reaches surfaces 1 and 3** | none | **unchanged in shape**; placed behind platform auth in a deployed environment. It discloses topology and volumes, never a credential. Reads as `sentinel_reader` (REQ-H-03, H-04) |

**Surface 4 response shapes** (all `application/json` except `/` and `/stream`):

- `GET /` → `text/html`. **Every figure is server-rendered before any script runs**; the
  animation illustrates numbers the page already printed (`main.py:13-16`).
- `GET /stream` → `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`
  (`main.py:135-138`). Frame format `data: <Snapshot.as_dict() JSON>\n\n`, one per poll tick;
  the current state is sent **immediately** on connect so a page joining between ticks is not
  blank; `: keepalive\n\n` after a 15 s idle timeout to stop proxies reaping the stream
  (`main.py:122-131`). Each subscriber has its own **bounded** queue, so a slow reader drops
  its own frames rather than stalling the poller or another viewer (`pipeline.py` `Broadcaster`).
- `GET /api/snapshot` → the latest `Snapshot.as_dict()` (§7.3's field list).
- `GET /api/graph` → `{topology, tables, silver_graph, silver_views, empty_by_contract,
  derived, contract}` — the static half, fetched **once at load**. Silver's schema lives here
  and not in the snapshot because three models of seventeen columns would be ~3 KB repeated
  every second to say what it said the tick before (`main.py:147-165`).
- `GET /api/history` → `{points: [...], ceiling_ms: 80.0}` — the rolling window behind the
  sparklines, served separately so it is not re-pushed 300 times (`main.py:168-176`).
- `GET /healthz` → `{ok, collector, clickhouse, subscribers}` (`main.py:179-186`). **Nothing
  polls it today**; it becomes flow-ui's deployment probe (REQ-A-11).

**The `:4317` receive boundary's validation tri-state** (`contract.grpc_validation`, default
**`warn`**; `src/grpc.rs:125-167`, `src/config.rs:190-221`) **[E]** — three behaviours that are
all `OK` on the wire, which is the part a consumer must understand:

| Policy | Per-signal behaviour | gRPC status | Metric |
|---|---|---|---|
| `off` | no validation | `OK` | — |
| **`warn` (default)** | invalid signals are counted and **exported anyway**; the evidence lands in bronze | `OK` | `sentinel_signals_rejected_total{signal, reason="contract"}` |
| `strict` | invalid signals are **dropped silently from the caller's point of view** — the response is still `OK` and the producer is never told which signals were discarded | `OK` | same |

`warn` is the default because foreign OTLP legitimately lacks the five `sentinel.*` resource
keys, so `strict` would drop it. **`strict`'s silent drop is the semantics a future
contract-enforcement feature must change**, and it is why flow-ui's Contract board must read
bronze or a silver rollup rather than the metric: `signals_rejected_total` carries `signal` and
`reason` but **no service label**, so it can say how many violated and how, never *who*
(`clickhouse.py:180-190`) **[E]**.

**The five pinned metric families** (names pinned by the test at `src/metrics.rs:307-311`, and
the endpoint's contract with flow-ui and with every probe) **[E]**:

| Family | Type | Labels | Note |
|---|---|---|---|
| `sentinel_signals_ingested_total` | counter | `signal` ∈ `trace\|logs\|metrics` | recorded at the gRPC receive boundary, **before** buffering — the only place the three types are distinguishable |
| `sentinel_signals_rejected_total` | counter | `signal`, `reason` ∈ `contract\|backpressure` | the cross-product flow-ui's `reject_matrix` draws from |
| `sentinel_batch_flush_total` | counter | `signal="all"`, `status` | `signal="all"` is **deliberate, not a placeholder**: the `BufferedExporter` enqueues every variant into one combined channel, so no per-signal flush boundary exists to label (`metrics.rs:13-16`) |
| `sentinel_batch_flush_size` | histogram | none | per successful flush |
| `sentinel_export_errors_total` / `sentinel_export_latency_seconds` | counter / histogram | none | `export_latency_seconds` is the wall-clock of each `clickhouse_exporter::export` call, success or failure |

---

## 14. Security protocols

### 14.1 Least-privilege ClickHouse roles — created by migration `0002`, not by an init script

Created as a **migration** so they apply identically to a local volume and to a managed
instance (§12.2). Replaces: passwordless `default` opened to `::/0`; the `CLICKHOUSE_USER` +
`CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT` route; and the `otelgen`/`otelgen_secret` user with
`ALL ON bronze.*` **and** `ALL ON default.*`.

```sql
-- REQ-H-01: the vestigial Go-collector DSN user and its committed plaintext password
DROP USER IF EXISTS otelgen;

-- REQ-H-03
CREATE ROLE IF NOT EXISTS sentinel_collector;
GRANT INSERT ON bronze.* TO sentinel_collector;

CREATE ROLE IF NOT EXISTS sentinel_reader;
GRANT SELECT ON bronze.*        TO sentinel_reader;
GRANT SELECT ON silver.*        TO sentinel_reader;
GRANT SELECT ON system.tables   TO sentinel_reader;   -- REQ-H-04: clickhouse.py:429, 503
GRANT SELECT ON system.columns  TO sentinel_reader;   -- REQ-H-04: clickhouse.py:505

CREATE ROLE IF NOT EXISTS sentinel_migrator;
GRANT CREATE DATABASE, CREATE TABLE, CREATE VIEW, ALTER, DROP, SELECT, INSERT
  ON bronze.* TO sentinel_migrator;
GRANT CREATE DATABASE, CREATE TABLE, CREATE VIEW, ALTER, DROP, SELECT, INSERT
  ON silver.* TO sentinel_migrator;
GRANT CREATE DATABASE, CREATE TABLE, SELECT, INSERT ON _meta.* TO sentinel_migrator;
GRANT SELECT ON system.parts TO sentinel_migrator;    -- the backfill's partition list (§6.5)

CREATE USER IF NOT EXISTS sentinel_collector_u IDENTIFIED WITH sha256_password BY {pw:String};
GRANT sentinel_collector TO sentinel_collector_u;
-- …_reader_u, …_migrator_u likewise
```

Deliberate choices:

- **Roles, then users.** The role is the reviewable artifact and survives a credential rotation.
- **`sha256_password`, never `plaintext_password`.** The password is supplied as a query
  parameter from a mounted secret file by the migration runner; it is never a literal in a
  migration file, because migration files are in git.
- **The collector gets `INSERT` and nothing else** — DS-09: it issues no DDL and reads nothing.
  **This grant list is explicitly not asserted to be complete.** The `clickhouse` crate may
  probe `system.*` for a table check. REQ-H-06 makes **CI the oracle**: the live jobs connect as
  these roles, and a missing grant fails the job rather than being discovered in staging.
- **`system.parts` to the migrator only.** It is the backfill's range authority (§6.5) and it
  leaks the shape of the data, so the reader does not get it.
- **Why the reader needs `system.tables`/`system.columns` specifically:** flow-ui draws the
  Silver box on the Flow board from them. Omit the grant and **the fourth box silently
  disappears** — a degradation that looks like a design choice.

### 14.2 The `password_file` contract (S3) and secrets handling

```yaml
clickhouse:
  user: sentinel_collector_u
  password_file: /etc/sentinel/secrets/ch_password
```

Rules, each testable at S3:

1. **The config file carries a path, never a value.** This is what lets the config live in git
   under review while the secret never does (NFR-10), and it is the only shape compatible with
   the `std::env::var` ban (§12.1).
2. The loader reads the file at startup, trims **one** trailing newline, and **MUST NOT** log
   its contents, its length, or a prefix. A missing or unreadable file is a startup failure
   naming the **path** only.
3. Mounted `0400`, owned by the container's non-root user. Secret Manager (or equivalent) →
   projected volume. **Never** an env var, never a build arg, never a `docker inspect`-visible
   field (NFR-10).
4. Local dev keeps a gitignored `infra/secrets/ch_password` with a committed
   `ch_password.example`. A CI grep assert fails on `otelgen_secret` anywhere in the tree
   (REQ-H-01) and on any file under `infra/secrets/` that is not `*.example`.
5. `METRICS_PORT` must not be set in a deployed environment (REQ-H-15): it rebinds to
   `0.0.0.0:<port>` and discards the host part, so the env path cannot express a loopback-only
   bind.

### 14.3 TLS per hop

| Hop | Today | Design | Gated on |
|---|---|---|---|
| generator → collector `:4317` | plaintext gRPC on `[::]:4317`; **zero TLS code** in the collector **[E]** | **terminate at the platform edge.** The generator already has `--otlp-secure`, `--otlp-api-key`, `--otlp-header`, so the client side needs no code | DEC-A1 |
| collector → ClickHouse `:8123` | plaintext HTTP, passwordless `default` | HTTPS + `user`/`password_file`. **Forced, not optional, if DEC-A2 picks managed ClickHouse** | DEC-A2, DEC-A4, REQ-H-05, H-10, H-13 |
| flow-ui → ClickHouse | plaintext HTTP | `https://` + `sentinel_reader`; `httpx` needs no code change | DEC-A2 |
| flow-ui → collector `/metrics` | plaintext HTTP | platform-internal TLS, or stay inside the trust boundary (REQ-H-14) | DEC-A1 |

Hop 2 is the sharp edge and §12.6 is its escalation. Hop 1 being avoidable by edge termination
is a concrete reason the Cloud Run recommendation is cheaper than it looks, and it is also why
TLS stays a **config** concern rather than a build concern wherever possible: that is what
makes a hop revertible by redeploying the **same digest** with a different per-env config
(REQ-A-07), rather than by rebuilding.

### 14.4 Supply chain, image signing and digest promotion (S4)

The Rust path already gates on licence, advisory and ban: `yanked = "deny"`, a nine-licence
permissive allow-list with copyleft denied by omission, `confidence-threshold = 0.93`,
`wildcards = "deny"`, registry restricted to crates.io, `Cargo.lock` + `--locked` throughout
**[E]**. **The Python path has no equivalent** — no lockfile, no `pip-audit`, no `bandit`,
`>=` floors only. REQ-B-07 closes that asymmetry; this section extends the same discipline from
crates to images.

```
REGION-docker.pkg.dev/PROJECT/sentinel/collector-rust:<git-sha>   (+ :main, :vX.Y.Z)
REGION-docker.pkg.dev/PROJECT/sentinel/generator:<git-sha>
REGION-docker.pkg.dev/PROJECT/sentinel/flow-ui:<git-sha>
```

- **The SHA tag is the only thing a deployment ever names.** Channel tags are for humans
  (REQ-A-01).
- `docker/build-push-action` with `provenance: mode=max` and `sbom: true`; **cosign keyless**
  signing via the same OIDC identity; registry vulnerability scanning as REQ-H-12's gate;
  deployment **verifies the signature before admitting** the image (REQ-A-02).
- **Credentials: GitHub OIDC → Workload Identity Federation → a deploy service account. No JSON
  key anywhere** (REQ-A-03). This is the project's first real IAM, and it is the first thing an
  ADR should name an owner for.
- **Promotion moves a digest, never a build** (REQ-A-07): `main` → `staging` on merge,
  `staging` → `prod` on a tag, by re-pointing the same digest. Per-environment differences live
  **only** in `infra/deploy/config/<env>/`. This is what makes "roll back to the previous
  version" finally name an artifact.
- `rust-ci.yml:129`'s `push: false` stays as the PR-time build check, so a fork PR can never
  publish. Pushes happen only from `release.yml` on `push: main` and on tags.
- **Multi-arch (REQ-H-13):** `release.yml` and `rust-ci.yml`'s `docker-build` both gain
  `platforms: linux/amd64,linux/arm64`. Today `rust-ci.yml:119-132` passes no `platforms:` at
  all, so **arm64 is never built in CI** even though the recorded E2E snapshot is arm64.

### 14.5 The real-telemetry tripwire (REQ-H-11)

The baseline's strongest compliance fact is that all data is synthetic, and **nothing in the
current design would flag the transition**. Every signal carries `sentinel.synthetic`, already
surfaced as `is_synthetic Bool` in all three silver base tables
(`02-silver-layer.sql:20, 51, 73, 102, 123, 151`) **[E]**, so the tripwire is one predicate:

```sql
SELECT throwIf(
    (SELECT countIf(NOT is_synthetic) FROM silver.operation_executions) != 0,
    'non-synthetic telemetry in silver.operation_executions — the compliance position has changed'
);
```

in `03-watcher-models.test.sql`, repeated for `log_events` and `metric_observations`. It
belongs in **this** cycle precisely because it is nearly free now and unaffordable to retrofit
after the first real-telemetry swap.

---

## 15. Out of scope

- **Candidate C — decision-record drift.** Already owned per `CLAUDE.md`'s *Known doc drift*
  table (ADR-0004 → Pod 2; ADR-0007/0008 → cross-Pod sync; the Pod↔layer mapping → Captain /
  Commander; the ADR-0009 amendment → Captain / Commander). Excluding it is a **scheduling
  risk, not a scope saving**: this spec raises seven ADRs into a team whose last six are still
  `Proposed`. And it leaves one specific hazard standing — D's three read models are shaped for
  Watchers inferred from flow-ui's four boards and the six named Watcher crews; **if the
  Pod↔layer mapping lands differently (README's POD3 = storage/read-layer vs
  `.claude/CLAUDE.md`'s B3 = watchers), D may have built for the wrong consumer.** Candidate C
  is the thing that would have told us.
- **Candidate F — histogram / summary / exponential-histogram metrics.** Requires a contract
  version bump under ADR-0008's registry rule. The three bronze tables stay **empty by
  contract**, and flow-ui keeps saying so (`clickhouse.py:46-50`).
- **Candidate G — the detection spine.** Watchers, the 3-tier cascade, policy engine,
  remediation, audit log, feedback loop. D delivers the **inputs** those stages read and
  **must not** implement a threshold, a z-score verdict or an escalation (REQ-D-07, grep-asserted).
- **Down-migrations.** The runner is forward-only (REQ-A-14). This cycle's DDL is **additive
  only** (REQ-D-08), so rollback is "deploy the old image against the new schema" — which works
  for additive DDL and for nothing else. A genuine down-migration story is an ADR for whenever
  the first destructive change is proposed.
- **`silver.service_health_1m` → storage-backed.** `quantileExact` is not additively mergeable;
  changing to `quantilesTDigestState` would change the numbers a live board draws (§6.1).
- **Historical records.** `docs/adr/0*`, `docs/proposals/`, `docs/research/`,
  `docs/clickhouse-schema-divergence*.md`, `.claude/sdd/**` are point-in-time artifacts
  (NFR-08). No leg edits them. `.claude/` is deleted in the working tree and is being recreated
  by its owner; it was read via `git show HEAD:.claude/...` only, and **no leg writes there**.
- **`services/collector-rust/infra/docker-compose.collector.yml`.** Left in place (§6.8).

---

## 16. Further notes

**Where this spec contradicts DSP, and why.** Three places, each a correction rather than a
preference: the rollup sorting keys lead with `window_start` (§4 correction 9, because the
reading query filters on time only); REQ-E-03's checksum becomes mandatory and in-runner (§4
correction 6, because count equality is blind at constant cardinality); and R-03's "silent
loss" is wrong (§4 correction 5, because the 18 assertions are silver↔**bronze** equalities).
Two places where it **adds** a hard constraint DSP does not have: REQ-D-10 (the view re-point
breaks an existing assertion on any volume with history) and REQ-E-12 (the live partition is
refused outright, no flag).

**Where this spec contradicts an ADR.** Nowhere directly — but §12.3 and §12.5 both say
plainly that this plan **cannot satisfy ADR-0009's disjoint-paths rule together with
pre-pr-discipline check 2**, and picks a convention that violates the letter of the latter,
pending DEC-I2. That is stated rather than silently overridden, per the ground rules.

**The highest value-per-line item in the whole plan** is H.1 — delete `otelgen`, remove the
`::/0` override, create three roles, give the collector `user`/`password_file`. It needs no
deployment, no ADR, and it removes a committed plaintext credential. It requires a `make reset`
(the users live in the init path and the existing volume carries the old grants), which costs
nothing because all data is synthetic.

**The job most likely to be flaky** is the new live-ClickHouse one: it builds the Rust image,
boots ClickHouse, runs a generator backfill, waits for quiescence and then asserts **exact**
count equality. Every step is a flake source, and §7.4's quiescence loop is **reasoned, not
measured**. Land it non-required, watch a week of real PRs, then require it (REQ-B-10).
Promoting a gate before its flake rate is known is how teams learn to bypass gates.

**What this spec could not determine.** (i) `[V-1]`, `[V-2]` and `[V-3b]` were unverified when
the body was written and have since been **measured PASS on both 24.3.18.7 and 25.4.13.22** —
see §11.1, which also records the three limits on what those probes prove. `[V-3a]` is
ungated on 25.4.13.22 and gated only on 24.3.18.7, so it follows DEC-I1; the **`SharedMergeTree` half of `[V-3]`** remains
genuinely open, and `[V-4]` is resolved (§11.1) with its premise reversed. (ii) flow-ui's
**73-vs-63** collected-test gap — static count 71 functions + one `parametrize`×3 = 73, while
`CLAUDE.md` claims 63; not resolvable statically, and REQ-B-09 deliberately does not ask anyone
to resolve it by hand. (iii) Every `NFR-05` re-measurement for the three migrated flow-ui
queries — the house style requires the new figure beside the old one in the docstring, and
those numbers need a running stack. (iv) Whether `sentinel_collector` really needs only
`INSERT`; REQ-H-06 makes CI the oracle rather than this document. (v) Whether a managed
provider's `SharedMergeTree` preserves `REPLACE PARTITION` semantics — **[V-3]**, and if it does
not, E loses its primitive and there is no second design that leaves the base tables' engine
alone.
