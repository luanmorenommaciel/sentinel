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

| Workflow | Job | Covers | Required today | Promote when |
|---|---|---|---|---|
| `rust-ci` | `gates (fmt · clippy · test · build)` | `cargo fmt --check`, `clippy -D warnings`, unit + golden + gRPC + doc tests, release build | no | with the first required set |
| `rust-ci` | `integration (every #[ignore]d test)` | the live-ClickHouse round-trip and every `#[ignore]`d test (T09) | no | with the first required set |
| `rust-ci` | `supply-chain (cargo deny)` | licences, advisories, bans, `yanked = "deny"` | no | with the first required set |
| `rust-ci` | `docker-build (distroless image)` | the image builds, `push: false` so a fork PR cannot publish | no | with the first required set |
| `rust-ci` | `musl TLS spike (<target>)` | T04's evidence for DEC-A4 — **not a gate**, and `continue-on-error` | no | never; delete with T42 |
| `python-ci` | `lint (ruff)` | ruff over both Python packages | no | with the first required set |
| `python-ci` | `test (python <version>)` | pytest across the `PYTHON_IMAGE` matrix — 178 generator + 83 flow-ui | no | with the first required set |
| `python-ci` | `supply-chain (pip-audit · bandit)` | advisories + static security scan, `continue-on-error` | no | after a lockfile exists (REQ-B-07) |
| `repo-invariants` | `invariants (scripts/ci/invariants.d)` | the six cross-cutting properties below | no | **ready now** — all six pass as of T19 |
| `e2e-silver` | `e2e-silver (live ClickHouse)` | the real pipeline, the 18 silver assertions, the generator integration suite, and the role grants | no | after a week of real PRs (`SPEC §16`) |
| `pr-linked-issue` | `linked-issue` | the PR closes an issue, or carries `no-issue` | no | with the first required set |
| `release` | `publish (<image>)` | build, push, provenance, SBOM, cosign signing | n/a | runs on `main`/tags, not on PRs |
| `release` | `promote (<image>)` | digest promotion with verify-before-tag | n/a | runs on `main`/tags, not on PRs |

## What `repo-invariants` gates on

Nine asserts, each a property of the repository as a whole, so any PR can break one.
All nine pass. Four of the first five were authored to the end state and failed by
design until T19, which is why the job carried `continue-on-error` and why it does not
any more; 06 arrived with T16, 07 and 08 with T29, and 09 with the local-runtime scope
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

## Two things this table is deliberately honest about

**`e2e-silver` is the only check that can fail for reasons unrelated to the change.**
`SPEC §16` names it the job most likely to flake, and its quiescence loop is reasoned
rather than measured. It lands reporting truthfully — **not** wrapped in
`continue-on-error`, because a job that always reports green tells you nothing about
its own flake rate. Read a week of real runs before promoting it.

**Nothing has run since 2026-10-05.** GitHub Actions has been failing account-wide:
jobs complete in 1–3 seconds with `runner_name: ""` and zero steps, across all four
workflows here and other repositories under the same account, `windows-latest`
included. So every "no" in the Required column is also, right now, a check that has
never executed. Configuring a required set is pointless until that is fixed — which is
a billing or account-settings matter, not a repository one.
