# CI gates

Every status check this repository produces, what it covers, and whether it is
**required today** — so the Ways of Working's claim and the configured reality can be
compared instead of assumed (`SPEC §12.4`, REQ-B-10).

> **This file cannot prove itself.** Branch protection is a GitHub setting, not a file
> in the repo, so nothing here can assert what is actually enforced. The substitute is
> explicit: the Captain configures the rule set from this table and records the date
> below; a reviewer compares the two. As of the date on this file, `main` carries **no
> branch-protection rule at all** — verified against the API on 2026-10-06, which
> returned `protected: false` and 404 on the protection endpoint. Tracked in issue #35.

**Required set configured on:** _not yet configured_ · **recorded by:** —

## The checks

**Two lanes, after PR #59's lean default.** A *PR lane* runs on every pull request: cheap,
cached, no service containers. A *weekly lane* runs Mondays 06:00 UTC and on
`workflow_dispatch`: anything that needs a live ClickHouse, an emulated architecture, or a
cold cross-compile. One weekly job is wider than that: `e2e-silver` is **not** gated on
`github.event_name`, and its workflow also triggers on `push: branches: [main]`, so it runs
on every merge to `main` as well — after review, not before it. The split is a cost and
latency decision, not a statement that the weekly jobs matter less — see *Why the heavy jobs
are weekly* below.

| Workflow | Job | Lane | Covers | Required today | Promote when |
|---|---|---|---|---|---|
| `rust-ci` | `gates (fmt · clippy · test)` | **PR** | `cargo fmt --check`, `clippy -D warnings`, unit + golden + gRPC + doc tests | no | with the first required set |
| `rust-ci` | `integration (every #[ignore]d test)` | **weekly** | every `#[ignore]`d test against a live ClickHouse (T09) — the round-trip, the gRPC export path, and **the SIGTERM flush proof for issue #45** — plus the orphan check that fails if an `#[ignore]`d test did not run | no | needs a ClickHouse service container; promote only if the PR lane gains one |
| `rust-ci` | `supply-chain (cargo deny)` | **PR** | licences, advisories, bans, `yanked = "deny"` | no | with the first required set |
| `rust-ci` | `release build` | **weekly** | `cargo build --release --locked` | no | with the first required set |
| `rust-ci` | `docker-build (distroless image)` | **weekly** | the image builds for `linux/amd64` **and `linux/arm64`**, `push: false` so a fork PR cannot publish. arm64 is emulated, so `docker/setup-qemu-action@v3` registers the binfmt handlers before buildx — without it the first non-native `RUN` fails with `exec format error` | no | with the first required set |
| `rust-ci` | `musl TLS spike (<target>)` | **weekly** | T04's evidence for DEC-A4 — **not a gate**, and `continue-on-error` | no | never; delete with T42 |
| `python-ci` | `lint (ruff)` | **PR** | ruff over both Python packages | no | with the first required set |
| `python-ci` | `test (python <version>)` | **PR** | pytest across the `PYTHON_IMAGE` matrix — 178 generator + 83 flow-ui | no | with the first required set |
| `python-ci` | `supply-chain (pip-audit · bandit)` | **PR** | advisories + static security scan. `continue-on-error` at job level: it does not fail the **run**, but the **check** still reports failure (measured — see below) | no | after a lockfile exists (REQ-B-07) |
| `repo-invariants` | `invariants (scripts/ci/invariants.d)` | **PR** | the ten cross-cutting properties below | no | **ready now** — all ten pass in CI as of 2026-10-08, and locally under Compose v2.27.0 / v2.39.4 / v5.1.4 |
| `e2e-silver` | `e2e-silver (live ClickHouse)` | **weekly + push to `main`** + `workflow_dispatch` | the real pipeline, the 18 silver assertions, the generator integration suite, and the role grants | no | after a week of real runs (`SPEC §16`) — it is the heaviest job here at 30 min, and the one most likely to flake |
| `pr-linked-issue` | `linked-issue` | **PR** | the PR closes an issue, or carries `no-issue` | no | with the first required set |
| `release` | `publish (<image>)` | **gated off** | build, push, provenance, SBOM, cosign signing | n/a | `workflow_dispatch` only — see *`release` is gated off* below |
| `release` | `promote (<image>)` | **gated off** | digest promotion with verify-before-tag | n/a | `workflow_dispatch` only — see below |

## What `repo-invariants` gates on

Ten asserts, each a property of the repository as a whole, so any PR can break one.
All ten pass. Four of the first five were authored to the end state and failed by
design until T19, which is why the job carried `continue-on-error` and why it does not
any more; 06 arrived with T16, 07 and 08 with T29, 10 with HyperDX (ADR-0011), and 09 with the local-runtime scope
DEC-A1/A2 settled.

| Assert | Property |
|---|---|
| `01-single-clickhouse-image` | exactly one ClickHouse version pinned, and not `:latest` |
| `02-service-named-clickhouse` | every stack exposes a service literally named `clickhouse` (REQ-I-07) |
| `03-no-duplicate-host-8080` | no host port published twice, within a stack or across two |
| `04-no-plaintext-secrets` | no inline credential in the operational tree; nothing but `*.example` committed under `infra/secrets/` |
| `05-flow-ui-is-read-only` | flow-ui issues no write statement |
| `06-initd-matches-migrations` | `init.d/` is symlinks into `migrations/` — one DDL source, two apply paths |
| `07-silver-mv-determinism` | every silver MV body is deterministic, with `call_edges_1m_rmv` the one exception REQ-D-12 names |
| `08-no-verdict-in-silver` | no threshold, severity, escalation or verdict literal in the silver read models (REQ-D-07) |
| `09-local-compose-boundary` | host ports bind loopback-only, and `make` supplies the collector's OTLP port default (DEC-A1/A2 local scope) |
| `10-hyperdx-is-read-only` | HyperDX connects as `sentinel_hyperdx_u`, takes its password as a file path, publishes loopback only, keeps Mongo unpublished, pins both images, and no bundled ClickStack image adds a second ClickHouse or collector (ADR-0011) |

## Why the heavy jobs are weekly

PR #59 set the shape and it is kept here: cheap checks on the pull request, heavy jobs weekly
plus `workflow_dispatch`. Four jobs sit in the weekly lane, each for a named reason.

| Job | Why not per-PR |
|---|---|
| `integration (every #[ignore]d test)` | needs a live ClickHouse brought up with `docker compose … --wait`. Moving ClickHouse off the PR path is precisely what #59 did |
| `e2e-silver` | the same, at 30 minutes — the largest single budget in the repo. It is the one weekly job that also runs on `push` to `main` |
| `docker-build` | builds `linux/arm64` under QEMU emulation, which is several times slower than the native leg |
| `musl TLS spike` | two musl cross-compiles with no warm target cache, and it is evidence for DEC-A4 rather than a gate |

**The SIGTERM proof for issue #45 lands in the weekly lane, deliberately.** The test sends
`SIGTERM` to a collector holding a non-empty export buffer and asserts the buffered rows reach
ClickHouse — so it is `#[ignore]`d and needs the same ClickHouse service container as the rest
of the `integration` job. Putting it on every PR would re-import the exact cost #59 removed.
What keeps it from rotting is the orphan check in that job: it fails if any `#[ignore]`d test
in `tests/*.rs` did not appear in the run, so the test cannot be silently skipped by a
reintroduced `--test` filter. The signal-handling change it covers is **not** left to the weekly lane
alone. `tests/shutdown_signals.rs` holds two non-`#[ignore]`d tests —
`sigterm_stops_collector_cleanly` and `sigint_stops_collector_cleanly` — which spawn the real
collector binary, send it the real signal and assert it exits 0 within 3 s, with no database
at all. Those run in the **PR lane** inside `gates`. Only the *flush to ClickHouse* half needs
the weekly lane.

The image is covered separately by `services/collector-rust/tests/docker-stop.test.sh`
(`make test-collector-shutdown`), a step in the weekly `docker-build` job. The cargo test
proves the bare binary acts on SIGTERM; the script proves it when it is PID 1 in the
distroless image, stopped the way Docker, Kubernetes and systemd stop it — which is the
configuration issue #45 actually observed failing (`docker stop -t 12` → exit 137). Locally it
**skips** with exit 0 when no Docker daemon is reachable; CI sets `REQUIRE_DOCKER=1`, which
turns that skip into a failure, so the check cannot quietly no-op on a runner.

**The trade-off this accepts:** a PR can break the live round-trip, the silver assertions or
the arm64 image and still show a green PR lane. That is a real regression window, up to a week
wide. It is accepted because the alternative — a 30-minute ClickHouse job on every push —
was judged worse, and because the weekly run plus `workflow_dispatch` means any author who
suspects they touched those paths can trigger the heavy lane on demand before asking for
review. Whoever configures the first required set should revisit this with real flake data.

## `release` is gated off

`release.yml` triggers on `workflow_dispatch` **only**. Its `push: branches: [main]` and
`tags: ["v*"]` triggers are removed, and the reason is written at the top of the file.

Every job in it pushes to a container registry that **does not exist**: no GCP project, no
Artifact Registry repository, no Workload Identity provider. `publish` would fail at
authentication and `promote` could never find a digest to move. Separately,
`plan/decisions/DEC-2026-10-06-local-scope.md` (DEC-A1/A2) leaves remote deployment
unauthorized — no platform and no ClickHouse operational owner is selected, so there is
nothing to release *to*. A workflow that cannot succeed must not sit on `main`'s push trigger
looking like a release path; a reader would reasonably conclude images are being published.

Re-enabling is one PR: create the registry and the WIF provider, set the repository variables
the jobs read, restore the two triggers, and record the required-check decision here.
`workflow_dispatch` is kept rather than deleting the workflow, because a human running it by
hand is the only way it can be exercised against a real registry the first time.

## Two things this table is deliberately honest about

**`e2e-silver` is the only check that can fail for reasons unrelated to the change.**
`SPEC §16` names it the job most likely to flake, and its quiescence loop is reasoned
rather than measured. It lands reporting truthfully — **not** wrapped in
`continue-on-error`, because a job that always reports green tells you nothing about
its own flake rate. Read a week of real runs before promoting it.

**Actions resumed on 2026-10-08, and the lane split is confirmed by a real run.**

From 2026-10-05 the account-wide failure meant every job completed in 1–3 seconds with
`runner_name: ""` and zero steps, so nothing in this document had ever executed. That
is over. The first real run on `origin/sdlc-e2e-review` (workflow runs `37871412937`,
`37871412941`, `37871413069`, `37871426052`) executed with real durations, and the
two-lane shape behaved exactly as designed:

| Check | First real result |
|---|---|
| `gates (fmt · clippy · test)` | pass, 1m12s |
| `lint (ruff)` | pass, 7s |
| `test (python 3.10 / 3.11 / 3.12)` | pass, 46s / 58s / 48s |
| `linked-issue` | pass, 4s |
| `invariants` | **failed 2 of 10** — fixed, see below |
| `supply-chain (cargo deny)` | **failed** — fixed, see below |
| `supply-chain (pip-audit · bandit)` | **failed** — fixed, see below |
| `integration`, `docker-build`, `release build`, `musl TLS spike` | **skipped on the PR**, as the lean default intends |

Three findings only an actual run could have produced, each fixed in the same PR:

**`invariants` — a Compose portability defect, not a regression.** Asserts
`02-service-named-clickhouse` and `03-no-duplicate-host-8080` read merged
`docker compose config`, and the runner rejected the `collector-ci` stack with
`volumes.clickhouse_data conflicts with imported resource`:
`services/collector-rust/infra/docker-compose.yml` both `include:`d
`compose.clickhouse.yml` *and* re-declared `clickhouse_data` to pin its name, which
Compose treats as a conflict with an imported resource rather than an override. The
local toolchain (**v5.1.4**) tolerates it and passed 10/10, which is exactly why this
survived to `main` unnoticed. Reproduced locally against **v2.27.0** and **v2.39.4**,
fixed by making the included file the single owner *and* giving it the `name:` pin, and
re-verified 10/10 under all three versions. **A local invariant pass is not evidence
about CI unless the Compose version matches** — pin one, or run the harness against the
version CI uses.

**`cargo deny` — `RUSTSEC-2025-0134`, `rustls-pemfile` unmaintained.** Unmaintained, not
a vulnerability. It is absent from the default feature set and reaches the graph only
through `tls-spike` (T04's compile-only TLS experiment), which CI enables because it
runs `--all-features`. Not removable without bumping tonic to 0.13+ and the whole
opentelemetry 0.27 stack with it, so it carries a single scoped, dated `ignore` in
`deny.toml` naming T42 as its removal trigger. The `unmaintained` lint stays on for
everything else.

**`supply-chain (pip-audit · bandit)` — and a defect in how "non-blocking" was recorded.**
pip-audit was clean; bandit reported 22 findings. B110 (×3, silent `except: pass` on
exporter shutdown) was a real smell and is **fixed** — teardown stays best-effort but now
logs. B311 (×1, `random.Random(seed)`) and B107 (×1, `password_file` default) are false
positives and carry per-line `# nosec` with reasons. B608 (×17, hardcoded SQL in
`flow_ui/clickhouse.py`) are false positives too — every interpolated value is a module
constant and the module reads no request input — and are scoped off for flow-ui only, in
`make audit-python`, with the reasoning and the trade-off recorded there.

**What "non-blocking" actually means, corrected.** This document previously implied a
`continue-on-error` job reports green. It does not. Measured on run `37871412941`: the
**run** concluded `success` while the **job** `supply-chain (pip-audit · bandit)`
concluded `failure`, so the check shows red in the PR while not failing the workflow.
Job-level `continue-on-error` buys "does not fail the run", never "shows green" — the
only way a check shows green is for its step to exit 0. Those three checks are green now
because the findings are fixed, not because a flag hides them.

Branch protection remains unset (issue #35), so every "no" in the Required column still
stands — but it is now a policy gap, not a platform one. Configuring a required set is
finally possible.
