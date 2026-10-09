## Summary

CI that actually runs, on a single pinned ClickHouse, with the delivery path's
documentation consolidated into one page. The pipeline itself — generator → collector →
`bronze.*` — is untouched.

50 commits, 122 files, rebased onto `main` at `1aa8d92` (which carries PR #59).

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
individual commits rather than between them — measured, not assumed: **24 of 50 commits
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

**Not run in this session, and not claimed:** `make test-generator`, `make test-flow-ui`,
`make test-hyperdx`, `make lint` and `make test-silver`. All five go through Docker
(`DK_RUN`) or need ruff, and this environment has neither a reachable Docker daemon nor
ruff on `PATH`. The Python sources are unchanged by the last three commits on this branch,
but that is an argument, not a test run. The `docker stop` assertion itself has likewise
only been exercised down its skip and `REQUIRE_DOCKER=1` paths — its first real run will
be the weekly `docker-build` job.

**Not run, and this is the whole point of the PR:**

```
every workflow in .github/workflows/   → has never executed
```

GitHub Actions has been failing account-wide since 2026-10-05 — jobs end in 1–3 s with
`runner_name: ""` and zero steps, across every workflow here and other repositories on
the same account. The two shellcheck notes were confirmed present on the pre-rebase
branch, so neither is introduced here. clippy and the tests ran on host cargo 1.99.0,
not the 1.96.0 that `rust-toolchain.toml` pins, so CI could still differ.

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
