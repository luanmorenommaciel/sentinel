## Summary

CI that actually runs, on a single pinned ClickHouse, with the delivery path's
documentation consolidated into one page. The pipeline itself — generator → collector →
`bronze.*` — is untouched.

**56 commits, 126 files changed**, rebased onto `main` at `1aa8d92`,
which carries PR #59.

<details>
<summary>Why you may have seen 44 commits / 200 files quoted earlier</summary>

Four different measures were in circulation. The two in the line above are the ones this
PR's own diff shows — commits since the merge-base with `main`, and files in
`git diff origin/main...HEAD`:

```
$ git rev-list --count origin/main..HEAD                       #  commits in the PR
56
$ git diff --name-only origin/main...HEAD | wc -l              #  files in the PR diff
126
$ git rev-list --count origin/origin/sdlc-e2e-review..HEAD      #  counted against the
54                                                              #  PRE-REBASE remote head
$ git log --format='' --name-only origin/main..HEAD \
    | sed '/^$/d' | sort -u | wc -l                             #  files touched across all
213                                                             #  commits, union
```

**54** was counted against the pre-rebase remote head `ac0b633`, so it also included
`main`'s own two commits that the old head predates. That head has since been replaced by
this branch, so the figure is historical. **213** is the union across every commit,
including files a later commit reverted — which is where the "~200 files" figure came from.

The PR diff fell from **207** files to **123** for one reason: restoring `.claude/` removed 87
deletion entries from it. The arithmetic closes exactly:

```
$ git diff --name-only origin/main...93141c4 | wc -l            #  before any of this work
207
$ git diff --name-only origin/main...93141c4 | grep -c '^\.claude/'
87

207 − 87 restored + 3 new files (docs/sdlc.md, docs/pr-body-sdlc-e2e-review.md,
                                services/collector-rust/tests/docker-stop.test.sh) = 123
```

The earlier "44 commits" was measured before the rebase, against the old merge-base
`3af2ee7`; that count is now 47 for the same range, plus the 9 commits added by this work.

</details>

```diff
 .github/workflows/
-├── rust-ci.yml            # the only gate
+├── rust-ci.yml            # PR: gates · supply-chain
+│                          # weekly: integration · release-build · docker-build · musl spike
+├── python-ci.yml          # PR: ruff · pytest matrix · supply-chain*
+├── repo-invariants.yml    # PR: 10 whole-tree asserts
+├── e2e-silver.yml         # weekly: real pipeline + 18 silver asserts
+├── pr-linked-issue.yml    # PR: requires Closes #n
+└── release.yml            # GATED OFF — workflow_dispatch only, no registry exists
                            # (* = deliberately non-blocking)

 infra/clickhouse/
-├── three coexisting pins: 24.3, 25.4, 24.3
+├── compose.clickhouse.yml # ONE service definition, pinned 25.4
+├── migrations/0001..0006  # the DDL source of truth
+├── init.d/                # symlinks into migrations/ — one source, two apply paths
+└── backfill/              # runner + canonical SQL, refuses the live partition

 docs/
+└── sdlc.md                # Stage · Artifact · Gate · Owner, one page
```

Two lanes, which is the shape PR #59 set and this branch keeps: cheap checks on every
pull request, anything needing a live ClickHouse or an emulated architecture on a weekly
schedule plus `workflow_dispatch`. `docs/ci-gates.md` carries the full table and the
trade-off in writing.

### Code that landed inside two documentation commits

This branch was **not** split into the five focused PRs that were considered (Process
Docs · CI · Migrations · Silver/Backfill · Flow-UI). The split lines cut through
individual commits rather than between them — measured, not assumed: **25 of 56 commits
touch more than one of those five areas**, and the two commits below are the worst cases.
Splitting would mean rewriting commit *contents*, not reordering them.

So the code those two commits carry is called out here instead, because their subject
lines say "docs" and a reviewer reading subject lines would miss it:

| Commit | Subject says | Also contains |
|---|---|---|
| `8417bee` | `docs: update README with task status tracking` | **5 areas, 10 files.** `migrations/0005_silver_watcher_models.sql` (+264) — the four Pod 3 Watcher read models and their MVs · `tests/03-watcher-models.test.sql` (+247) · `queries/03-watcher-sample.sql` · invariants `07-silver-mv-determinism.sh` (+84) and `08-no-verdict-in-silver.sh` (+46) · `e2e-silver.yml` · `Makefile` · `spec/core-spec.md` |
| `97982b9` | `docs: reconcile the records with the 2026-10-06 rulings` | **6 areas, 40 files.** The whole backfill runner — `backfill.sh` (+211), 20 canonical/phase SQL files, `runner-refusal.test.sh`, `canonical-sync.test.sh` · `migrations/0006_repoint_metric_rollup.sql` (+81) · invariant `09-local-compose-boundary.sh` (+51) · **flow-ui Python**: `clickhouse.py` (+90), `pipeline.py`, `test_clickhouse.py` · `docker-compose.yml` · `Makefile` (+55) |

Reviewing those two commits as documentation changes would miss a 264-line migration, a
211-line shell runner, three new repository invariants and a change to flow-ui's read
path.

## Evidence

**SIGTERM, issue #45.** The missing acceptance criterion was `docker stop`. Verified by
running the test both ways on host cargo 1.99.0:

```
with the fix (src/main.rs selects on SignalKind::terminate + ctrl_c):
  cargo test --test shutdown_signals
    sigterm_stops_collector_cleanly ... ok
    sigint_stops_collector_cleanly  ... ok
    2 passed; 0 failed; 2 ignored

with shutdown_signal reverted to ctrl_c-only:
  sigterm_stops_collector_cleanly ... FAILED
    "SIGTERM should exit successfully: signal: 15 (SIGTERM)"
```

The test has teeth: it fails without the fix. New in this PR is
`services/collector-rust/tests/docker-stop.test.sh` (`make test-collector-shutdown`),
which asserts the *image* exits 0 within 5 s of `docker stop -t 10` — the configuration
#45 actually observed failing (`docker stop -t 12` → exit 137, SIGKILL). A cargo test
cannot reach it: the binary has to be PID 1 in distroless and receive Docker's own
signal.

**Local gates, all run:**

```
scripts/ci/run-invariants.sh                             → 10 assert(s) run, 0 failed
cargo test --locked                                      → 99 unit + integration targets,
                                                            0 failed, 4 ignored
cargo fmt --all -- --check                               → clean
cargo clippy --all-targets --all-features -- -D warnings → clean
actionlint .github/workflows/*.yml                       → 2 pre-existing style notes,
                                                            0 errors
shellcheck tests/docker-stop.test.sh                     → clean
```

**Python suites, now actually run** (outside Docker, in a 3.14 venv, because this
environment has no Docker daemon):

```
flow-ui    pytest          → 87 passed
generator  pytest          → 178 passed, 6 errors (the live-ClickHouse integration tests)
ruff       the 3 edited files → All checks passed!
bandit     generator (all checks)        → exit 0
bandit     flow-ui (B608 scoped off)     → exit 0
cargo deny --all-features check          → advisories/bans/licenses/sources ok
invariants under Compose v2.27.0 / v2.39.4 / v5.1.4 → 10 run, 0 failed (each)
```

**Still not run:** `make test-silver` and `make test-hyperdx` (Docker), and the
`docker stop` assertion itself, which has only been exercised down its skip and
`REQUIRE_DOCKER=1` paths — its first real run is the weekly `docker-build` job. Two
pre-existing ruff errors sit in `services/generator-python/tests/` (E501, I001); they are
outside `make lint-generator`'s scope, which checks `src` only, and are not touched here.

**CI ran, for the first time since 2026-10-05.** The account-wide Actions failure (jobs
ending in 1–3 s with `runner_name: ""`) cleared on 2026-10-08. The first real run on this
branch both confirmed the lean shape and found three things no local run could:

```
gates (fmt · clippy · test)            pass   1m12s
lint (ruff)                            pass   7s
test (python 3.10 / 3.11 / 3.12)       pass   46s / 58s / 48s
linked-issue                           pass   4s
integration · docker-build ·           skipped on the PR  ← the lean default, working
  release build · musl TLS spike

invariants                             FAILED 2 of 10   → fixed
supply-chain (cargo deny)              FAILED           → fixed
supply-chain (pip-audit · bandit)      FAILED           → fixed
```

**1. `invariants`: a Compose portability defect.** `02-service-named-clickhouse` and
`03-no-duplicate-host-8080` read merged `docker compose config`, and the runner rejected
the `collector-ci` stack: `volumes.clickhouse_data conflicts with imported resource`.
`services/collector-rust/infra/docker-compose.yml` both `include:`d
`compose.clickhouse.yml` *and* re-declared `clickhouse_data` to pin its name — a conflict
with an imported resource, not an override. **The local toolchain (v5.1.4) tolerates it
and passed 10/10, which is why it survived unnoticed.** Reproduced against v2.27.0 and
v2.39.4, fixed by making the included file the single owner *and* moving the `name:` pin
into it, re-verified 10/10 under all three versions.

**2. `cargo deny`: `RUSTSEC-2025-0134`** — `rustls-pemfile` unmaintained (not a
vulnerability). Absent from the default feature set; it reaches the graph only via
`tls-spike`, T04's compile-only TLS experiment, because CI runs `--all-features`.
Removing it needs tonic 0.13+ and the whole opentelemetry 0.27 stack, which is
contract-adjacent and does not belong here. One scoped, dated `ignore` in `deny.toml`
naming T42 as its removal trigger; the `unmaintained` lint stays on otherwise.
`cargo deny --all-features check` → `advisories ok, bans ok, licenses ok, sources ok`.

**3. `bandit`: 22 findings, split by judgement rather than blanket-suppressed.**
pip-audit was clean. B110 (×3) was a real smell — three silent `except Exception: pass`
on exporter shutdown — and is **fixed**: teardown stays best-effort but logs, so a
half-closed exporter is no longer invisible. B311 (×1) and B107 (×1) are false positives
with per-line `# nosec` and reasons (`random.Random(seed)` *is* the contract — `SEED=42`
must replay the golden fixture; `password_file` is a path, not a credential). B608 (×17,
`flow_ui/clickhouse.py`) are false positives — every interpolation is a module constant
and the module reads no request input — and are scoped off for flow-ui only, in
`make audit-python`, with the trade-off written there. Both bandit invocations now exit 0.

Also corrected: this repo recorded `continue-on-error` as making a check non-blocking.
Measured on run `37871412941`, the **run** concluded `success` while the **job**
concluded `failure` — so the check still shows red. It buys "does not fail the run",
never "shows green". Those checks are green now because the findings are fixed.

**Still true:** the two shellcheck notes were confirmed present on the pre-rebase branch,
so neither is introduced here; and the Rust clippy/test runs quoted above were on host
cargo 1.99.0, not the 1.96.0 `rust-toolchain.toml` pins — though CI's own `gates` job has
now passed on the pinned toolchain.

## Why

Closes #34

`#34` is the issue this branch answers: `.github/workflows/` contained only `rust-ci.yml`,
so 235 tests and 60 SQL asserts existed, were green, and gated nothing. They are wired now.

Refs #45 · Refs #56 · Refs #35

**Deliberately `Refs`, not `Closes`, for those three.** They were reopened as part of this
work. #45's `docker stop` criterion is now covered by a check that has never executed; #56
tracks a cycle whose gates have never run; #35 is a GitHub repository setting, not a file,
and no rule exists on `main` today. Marking any of them Done on merge would record a
green that nobody has seen. They close when Actions runs and the checks pass.

## Merge Danger

**Door:** two-way for everything except one migration.

Reverting this PR restores the previous CI shape, the previous docs and the previous
Makefile with no data consequence — none of it holds state.
`migrations/0006_repoint_metric_rollup.sql` is the exception: it is
`CREATE OR REPLACE VIEW silver.metric_rollup_1m`, so a revert leaves the replaced view in
place on any volume that already applied it. Re-pointing it back is one statement, and
`_meta.schema_migrations` records that it ran — but it is not undone by `git revert`
alone.

**Blast Radius:** repo-wide.

- **CI behaviour changes for every PR, in both directions.** Four PR-lane checks appear
  where there was one. Four jobs *leave* the PR lane for a weekly schedule, so a PR can
  break the live ClickHouse round-trip, the 18 silver assertions or the `linux/arm64`
  image and still show a green PR lane. That regression window is up to a week wide, it
  is the deliberate cost of PR #59's shape, and it is written down in
  `docs/ci-gates.md`. Any author who suspects they touched those paths can trigger the
  heavy lane with `workflow_dispatch` before asking for review.
- **A single ClickHouse pin at 25.4** replaces three coexisting pins. Anyone holding a
  volume created under 24.3 must `make reset` — `CREATE TABLE IF NOT EXISTS` will not
  update a changed schema, and inserts fail with `NO_SUCH_COLUMN` instead.
- **The root stack's ClickHouse volume is renamed, and this one needs reading.** Fixing
  the Compose conflict moved the `name: sentinel-clickhouse-data` pin into the included
  file, so it now reaches *every* consumer. Measured before and after with
  `docker compose config`:

  ```
  before   docker-compose.yml                       → origin-sdlc-e2e-review_clickhouse_data
           collector-rust/infra/docker-compose.yml  → sentinel-clickhouse-data
  after    both                                     → sentinel-clickhouse-data
  ```

  Two consequences. Existing local data in the project-prefixed volume is **orphaned, not
  migrated** — the stack comes up empty and `make reset` is the clean path, which is the
  stale-volume gotcha the README already warns about. And the root stack and the
  collector-ci stack now **share one named volume**, so a `docker compose down -v` in
  either removes the other's data locally. That follows from "one ClickHouse definition"
  (REQ-I-01/I-02) and is arguably correct, but it is a behaviour change, not a pure
  conflict removal. The alternative — dropping the pin instead — would have removed the
  conflict while losing a stable volume name, which is the worse trade.
- **`release.yml` no longer triggers on push to `main` or on a `v*` tag.** If anyone
  believed images were being published from `main`, they were not — the registry does not
  exist — but the workflow will now also stop *appearing* to try. Re-enabling is one PR,
  and the steps are at the top of the file.
- **`.claude/` is restored** (87 files: 16 agents, 10 skills, the 11-KB tree, 6 internal
  standards, 2 path-scoped rules, 4 SDD artefacts). It was deleted earlier on this branch
  while still tracked on `main`; this PR reverts that deletion, so the agent layer
  `main` already had is preserved rather than dropped. `meetings/` (2 files) stays
  deleted. One consequence to note: `.claude/CLAUDE.md`'s Crew B table is a live second
  statement of the Pod↔layer mapping again, which the root `CLAUDE.md` drift table now
  records as needing a ratification that reconciles both sources rather than one that
  picks the survivor.
- **The Rust service's `src/` changes are three files, 336 insertions:** `config.rs`
  (+211 — the `user` / `password_file` credential config, T06), `clickhouse_exporter.rs`
  (+57 — `build_client_from_config`, resolving the credential from a file path), and
  `main.rs` (+85 — the shutdown signal handler plus the connect/credential-failure path).
  A credential that cannot be read is now a startup failure rather than a silently
  passwordless connection, so a misconfigured `password_file` turns a previously-starting
  collector into one that exits `FAILURE`. That is intended (REQ-H-05), and it is the one
  behaviour change in the ingest service worth a second look.
- **Not touched:** the OTLP wire path and its parsing, the `bronze.*` schema, and both
  contracts under `contracts/`.

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
