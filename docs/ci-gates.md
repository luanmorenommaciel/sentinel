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
| `image-scan` | `image-scan (shipped base images)` | **PR** | every shipped base image in `services/*/Dockerfile`, for both platforms the repo ships, at `HIGH,CRITICAL` with `--ignore-unfixed`, **warn-only** — plus a teeth assertion that fails the job if the policy stops finding anything (T24 / REQ-H-12) | no | when a severity threshold is ruled on; see *The image scan, and why it is not in `release.yml`* below |
| `image-scan` | `image-scan (images as built)` | **weekly** | the same policy against `docker save` tarballs of all three images as actually built — adds the pip-installed packages inside generator and flow-ui, which a base-image scan cannot see | no | needs a full Rust musl build; promote only with the rest of the weekly lane |
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
plus `workflow_dispatch`. Five jobs sit in the weekly lane, each for a named reason.

| Job | Why not per-PR |
|---|---|
| `integration (every #[ignore]d test)` | needs a live ClickHouse brought up with `docker compose … --wait`. Moving ClickHouse off the PR path is precisely what #59 did |
| `e2e-silver` | the same, at 30 minutes — the largest single budget in the repo. It is the one weekly job that also runs on `push` to `main` |
| `docker-build` | builds `linux/arm64` under QEMU emulation, which is several times slower than the native leg |
| `musl TLS spike` | two musl cross-compiles with no warm target cache, and it is evidence for DEC-A4 rather than a gate |
| `image-scan (images as built)` | builds all three images, including the full Rust musl compile, only to scan the result. The base-image half of the same policy runs on every PR instead |

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

## The image scan, and why it is not in `release.yml`

T24 asked for an image vulnerability scan that **gates the push**, proven "on a real push",
in `release.yml`. That proof is unreachable and will stay unreachable for as long as the
local scope holds: no container registry exists, `release.yml` is gated to
`workflow_dispatch` precisely because of that, and `DEC-A1`/`DEC-A2` leave remote deployment
unauthorized. A scan step that only ever runs inside a workflow nothing triggers is not a
gate, whatever its configuration says.

**A scan does not need a push — it needs bytes.** `image-scan.yml` scans bytes that exist
without a registry, so REQ-H-12's intent (extend the Rust path's crate-level discipline from
`cargo deny` to container images) lands now rather than after a platform decision. The scan
step already written into `release.yml` is left alone: once a registry exists, scanning a
published digest is the right thing to do there, and this workflow does not replace it.

**Two lanes, for one measured reason.** The PR lane scans the *shipped base image* of every
service — the last `FROM` in each `services/*/Dockerfile`, pulled from its registry, for both
`linux/amd64` and `linux/arm64`. Measured on a cold cache: **~80 s** on a laptop and **18 s on
the runner** (run `37876581847`), no service container, no build. For a distroless + static-musl image that is very nearly the whole
surface: the collector's own layer is one static binary and `gcr.io/distroless/static-debian12`
carries **zero** HIGH or CRITICAL findings. The weekly lane builds all three images and scans
the `docker save` tarballs, which is the only way to see our own layers — the pip-installed
packages inside generator and flow-ui. It pays a full Rust musl build, which is why it sits
beside `docker-build` rather than on the PR path.

Neither job is path-filtered, unlike `rust-ci` and `python-ci`. The finding source here is the
vulnerability database, which moves without this repository changing; a path filter would mean
the gate reports only on the PRs that could not have introduced the finding.

**The threshold, and the calibration behind it.** T24 rules the blocking threshold a policy
call rather than a test, so the gate ships **warn-only**: `IMAGE_SCAN_EXIT_CODE=0` in
`scripts/ci/audit-images.sh`, and flipping that one default to `1` is the whole change.
What calibration exists, measured 2026-10-08 against `python:3.12-slim`, the real base of two
of the three images:

| Policy | Findings |
|---|---|
| `--severity HIGH,CRITICAL` | **44 HIGH**, 0 CRITICAL |
| `--severity HIGH,CRITICAL --ignore-unfixed` | 0 HIGH, 0 CRITICAL |

All 44 carry no patched upstream version (`fix_deferred` / `affected`). A blocking gate
counting those would have been red from the first run with nothing any author could do about
it, which is how a gate gets switched off — so `--ignore-unfixed` is on, and the full
unfiltered set is one environment variable away (`IMAGE_SCAN_IGNORE_UNFIXED=false`).

One more number worth recording before anyone flips the flag: the fixable count on
`python:3.12-slim` moved from 0 to 1 and back within fifteen minutes of each other on
2026-10-08, as `CVE-2026-103111` (libpcre2) gained and lost a published fix across two
registry snapshots of the same tag. That is the volatility a blocking gate inherits, and it is
the reason to read a few weeks of warn-only runs before promoting this check.

**Warn-only is not toothless, and that is asserted rather than claimed.** Every invocation —
PR lane, weekly lane and local `make audit-images` alike — ends by scanning a digest-pinned
deliberately vulnerable base image (`python:3.9-slim`, one token away from the real base) under
*the current policy*, and **fails the job** if that fixture produces no CRITICAL finding. A
scanner loosened to the point where nothing can fail it therefore breaks the build on the
loosening, not silently years later. Measured locally with the policy flipped to blocking:
`72 HIGH, 6 CRITICAL`, exit 1; the same tree warn-only prints the same 78 findings and exits 0.

**And the job itself was shown to go red, in CI, not only on a laptop.** Commit `8cfff6e` flipped
the PR-lane step to `IMAGE_SCAN_EXIT_CODE=1` with `IMAGE_SCAN_IGNORE_UNFIXED=false` for one run,
which is enough to make `python:3.12-slim`'s unfixed set count. Run `37876696811` concluded
**failure**: `44 HIGH` on each of the two platforms, `image scan: 88 finding(s) … and
IMAGE_SCAN_EXIT_CODE=1 makes them blocking`, `Process completed with exit code 2`. The flag was
reverted in the next commit, the same way issue #45's SIGTERM fix was proven by reverting it. That
run is also the measurement behind scanning both platforms: amd64 and arm64 produced 44 unfixed
HIGHs **independently**, which is the per-arch package snapshot the base loop exists to cover.

**The verdict comes from the report, not from the exit status.** Found while building this: a
transient `docker pull` failure against Docker Hub (`TLS handshake timeout`, exit 125 — the
same flakiness the Makefile's `DOCKER_BUILD_RETRIES` comment documents for gcr.io) was
indistinguishable from "findings found" when the exit code was the only signal, and trivy
itself overloads exit 1 for an internal error and a policy hit. So the scanner image is pulled
up front with retries, every scan writes JSON, a missing report is a hard failure that says the
scan could not run, and the counts are read from the file. A gate that cannot tell *clean* from
*never ran* is worse than no gate.

**Why Trivy.** `release.yml` already uses `aquasecurity/trivy-action`, so no second vendor is
introduced; Trivy scans a registry reference, a local daemon image and a `docker save`/OCI
tarball with the same CLI, needs no Docker socket mounted into it, and exposes the exact two
knobs this policy is made of (`--severity`, `--ignore-unfixed`) plus `--exit-code` as the
single warn-to-block switch. Grype (`anchore/scan-action`) would do the same job and was
rejected only to avoid a second scanner in the repo. Docker Scout authenticates to Docker Hub
for its advisory data, an external account this repo does not have and DEC-A1/A2 would not
sanction. GitHub-native scanning does not cover OS packages in an image we build and never
push.

**Residue, explicitly deferred.** T24's own words are "gates the **push**". What image scanning
can prove without a registry is proven here; what genuinely cannot is everything that needs a
published digest — provenance (`provenance: mode=max`), the SBOM attestation, cosign signing
and verify-before-admit. Those stay in `release.yml`, gated off, and remain T22/T23/T40's
business under DEC-A1/A2.

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

**`image-scan` landed green on its first real run.** Run `37876581847`, 18 s, both platforms of
both shipped base images at `0 HIGH / 0 CRITICAL`, the teeth fixture at `6 fixable CRITICAL`, and
`image-scan (images as built)` correctly **skipped on the PR** as the lean default intends. What
that green covers: the two base images as they stood on 2026-10-08, for amd64 and arm64, at
`HIGH,CRITICAL` with unfixed findings excluded, plus the assertion that the policy still bites.
What it does **not** cover: the images as built (weekly lane, never yet run — its first run is the
Monday schedule or a `workflow_dispatch`), anything below HIGH, unfixed findings, and every
registry-side property T24 also named.

Branch protection remains unset (issue #35), so every "no" in the Required column still
stands — but it is now a policy gap, not a platform one. Configuring a required set is
finally possible.
