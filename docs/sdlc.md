# The Sentinel SDLC

One page for the delivery process this repository actually runs. Nothing here is new: the
stages were already enacted across `prompts/`, `plan/`, `plan/decisions/`, `docs/ci-gates.md`,
`.github/PULL_REQUEST_TEMPLATE.md`, [ADR-0009](adr/0009-agentic-gitflow.md) and
[README §8](../README.md#8-current-status). They are collected here so a stage can be named,
its artifact found, and its gate checked without reading six files to infer the shape.

The process is the **Matt Pocock skill chain** (`mattpocock-skills@claude-plugins-official`,
installed at user scope and recorded in `CLAUDE.md` → *Agent skills*) wrapped in this
repository's own gates. The skills carry the method; `.claude/` carries the Sentinel-specific
agents, slash commands, KB and rules the method runs against. Neither is optional and neither
is a substitute for the other.

**Getting the chain on a clean laptop**, which is what stage 0 needs before it can start:

```sh
# once per machine — verified against this repo's Claude Code build via `claude plugin --help`
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install mattpocock-skills@claude-plugins-official

# once per repository — writes CLAUDE.md § Agent skills and docs/agents/*
/setup-matt-pocock-skills
```

(The same two steps are reachable in-session through the interactive `/plugin` command.)

`claude plugin install` takes **no version flag**, so it resolves whatever the marketplace
head carries. The version this cycle ran at is therefore recorded rather than pinned —
`1.2.3`, marketplace `anthropics/claude-plugins-official`, commit
`c55ee46073ed923f86ce59a5eb3b6d895095d1b7` — and re-read with:

```sh
jq -r '.plugins["mattpocock-skills@claude-plugins-official"][0].version' \
  ~/.claude/plugins/installed_plugins.json      # → 1.2.3
```

Two crew members can therefore run `/to-tickets` at different versions and get different
output. That is a real gap and it is a decision, not a doc fix: vendor the chain into
`.claude/`, pin it in a committed manifest, or document-and-accept. It is on the post-merge
issue list in `plan/fix_before_merge_01.md` §5.

**The install is user-scope, so several of these skills are invisible to an agent** — see the
note at the end of §3. Not finding `/to-spec` in a skill list is not evidence it is missing.

> **The one thing to read before claiming anything is finished.** Actions was dead from
> 2026-10-05 to 2026-10-08 — jobs ending in 1–3 s with `runner_name: ""` and zero steps — so
> for three days no gate below had ever run. It works again, and **every gate below has now
> executed at least once and is green**: the PR lane, the weekly lane on run `37923509295`
> (all seven jobs, including issue #45's `docker stop` proof, which had never run by any
> path), and `e2e-silver` on run `38833172124` — ten steps, 3 m 35 s, the real pipeline and
> 34 silver SQL assertions. The first weekly dispatch, `37875017554`, was red on three of
> four jobs, and the first `e2e-silver` dispatch, `38831986773`, died inside `make up`; both
> defects are fixed here, and both are the reason the rule below is phrased as it is.
>
> Two things still make "finished" a claim about the future rather than the past. The weekly
> lane **does not run on a PR**, so a green PR lane tells you nothing about it; its green comes
> from hand-fired dispatches, and a scheduled run on `main` four days later (`38266048240`)
> went red on `cargo deny` — read the run, never the lane. (`e2e-silver` is on the PR lane
> since 2026-10-16: run `38843684967`, event `pull_request`, green.) And **no
> branch-protection rule exists** (issue #35), so nothing below is actually *required*. A green
> local run is still evidence about a laptop — and the outage proved that sharply: the invariant
> harness passed 10/10 locally while failing 2/10 on the runner, purely on a Compose version
> difference. ***Done (local)*** remains the honest status for laptop-only evidence, and
> `docs/ci-gates.md` carries the per-check detail.

---

## 1. The stage table

**Owner vocabulary.** *Pod* = the unit that owns a feature end-to-end (ADR-0009 §Decision).
*Captain* = Crew B's engineering lead, a rotating hat rather than a permanent role.
*Commander* = Luan Moreno, who alone can take the decisions marked `type:commander-attention`
and change GitHub repository settings.

**Captain (as of 2026-10-16): Adilson Cesar**, named by the Commander, leading all SDLC brownfield
work on this project. Every stage this table assigns to *Captain* is Adilson's until the hat
moves; when it does, this line is the one edit that changes. **Pod owners are still open:** the
Commander named the Captain only, so *Pod* in the table remains a role, and `.claude/CLAUDE.md` §
Crew B layout is the only place Pod membership is recorded (B1, B3, B4 `TBD`).

| # | Stage | Artifact | Gate — what must be true to leave the stage | Owner |
|---|---|---|---|---|
| 0 | **Grill → Intent**<br>reverse-engineer the verified As-Is | `intent/core-intent.md` | Every claim about the current system is read out of the tree, not inferred. Unknowns are left as `[TBD]` rather than guessed. Driven by `prompts/00-grill-to-intent.md` + `/grill-with-docs`. | Captain |
| 1 | **Intent → Spec**<br>formalise the To-Be | `spec/core-spec.md` (`SPEC §n`, numbered `REQ-<area>-<n>`)<br>+ `intent/design-spec.md` (`DSP §n`, the rationale) | Every requirement is numbered and citable. Contradicting policies are named as concerns, not silently resolved. Scope stays inside DEC-2026-10-06. `prompts/01-intent-to-spec.md` + `/to-spec`. | Captain, Pod consulted |
| 2 | **Spec → Plan**<br>break into tracer-bullet tickets | `plan/core-plan.md` — tickets `T01…`, each with Leg · Blocked by · REQ · Seam · Files · Does · **Proof** · Judgement | Every ticket has a *runnable* proof command and declared disjoint paths (ADR-0009 R1). Anything needing a human answer becomes a `DEC-*` brief, not a ticket. `prompts/02-spec-to-plan.md` + `/to-tickets`. | Captain |
| 2a | **Decision** (runs beside 2, blocks tickets) | `plan/decisions/DEC-*.md` — six sections: question · why open · options · established facts · what it unblocks · what it cannot settle | A brief is closed only by a named owner's ruling, recorded as a dated ruling file (e.g. `DEC-2026-10-06-local-scope.md`). A brief carries evidence tags `[M]/[S]/[D]/[R]`; no invented cost, SLA or capacity figures. | per brief — Commander for `A2`/`I1`/`I2`, Pod for `A3`/`A4`/`D1` |
| 2b | **Architecture decision** (any horizon longer than the sprint) | `docs/adr/NNNN-*.md`, status `Proposed` → ratified | Opened with the `/adr` skill, numbered monotonically, Captain + Commander review. **ADRs are records:** a superseded ADR is corrected by a new ADR, never rewritten. | Captain + Commander |
| 3 | **Leg open**<br>allocate the work to an agent or human | a branch `leg/<area>/<task>-v<n>` + a worktree at `.worktrees/<task>-v<n>` | The leg declares the paths it owns **before it opens**, and they are disjoint from every concurrent leg (ADR-0009 R1). Work that crosses a seam is sequenced, never fanned out. | the executing Pod |
| 4 | **RED**<br>failing test first | a test asserting the ticket's **Proof** criterion | The test runner has been run and the **failing output quoted**. No implementation code written yet. `prompts/03-plan-to-tdd.md` prompt 1 + `/implement` → `/tdd`. | leg agent |
| 5 | **GREEN**<br>minimal implementation | the change, inside the leg's declared paths only | The previously failing test passes. | leg agent |
| 6 | **Three green checks** | quoted command output | `make test` (+ `make test-silver` when `migrations/` or `silver.*` is touched) · `make lint` · `make build` — all three, output quoted, not summarised. Then `scripts/ci/run-invariants.sh`: all **ten** invariants pass, because they are properties of the whole tree and any ticket can break one. | leg agent |
| 7 | **Pre-PR discipline** | the issue number, and the doc fixes | (i) An issue covers the work, or the `no-issue` label records who decided it did not — `pr-linked-issue.yml` fails a PR that closes neither. Issues are **proposed, never created unprompted** (`docs/agents/issue-tracker.md`). (ii) `git ls-files '*.md' \| xargs grep -ln "<what you touched>"`, and every **live** doc that no longer holds is fixed **in the same PR** (DEC-I2). `docs/adr/`, `intent/`, `spec/`, `docs/proposals/` are records — left alone. `plan/` is live — amended. | author |
| 8 | **Code review** | the PR | `/code-review` on two axes — Standards (repo conventions) and Spec (does it do what the ticket's REQ asked). WoW asks for two approvals: peer, then Captain. | reviewer + Captain |
| 9 | **CI gates** | the status checks in `docs/ci-gates.md` | **Every check in `docs/ci-gates.md` has now executed at least once, and all of them are green.** Actions resumed on 2026-10-08 and the PR lane is green — on `392da82`, 10 checks pass and 5 skip by design (the tenth arrived with T24's `image-scan`). The **weekly lane** went red on its first hand-fired run (`37875017554`) and green on the second, `37923509295`, all seven jobs, `docker-build` at 22 m 05 s — which is where issue #45's `docker stop` proof finally ran. **`e2e-silver`**, the last check that had never executed at all, is green on run `38833172124` (2026-10-16): ten steps, 3 m 35 s, 233,100 signals through the real pipeline and 34 silver SQL assertions — and since it now triggers on `pull_request`, it also gates every PR (first PR-event run `38843684967`, green in 3 m 45 s). One gap remains and it is not a test: **no branch-protection rule exists** on `main` (issue #35, the API returns 404), so nothing here is actually *required* — the green is advisory. `docs/ci-gates.md` is the table to configure the required set *from*. | Commander (setting) · Captain (table) |
| 10 | **Merge to `main`** | the squash commit | Conventional Commits · signed (`git commit -S`) · `Co-Authored-By:` for every human and LLM contributor. ADR-0009 amends the WoW's blanket "squash-merge to main" for legs. | Captain |
| 11 | **Status record** | [README §8](../README.md#8-current-status) per-ticket registry | A ticket moves to **Done** only when its checks are green **in CI** and the code is on `main`. Otherwise it is ***Done (local)*** — done within DEC-2026-10-06's local scope and unverified against any deployed target. Drift between a record and reality goes in `CLAUDE.md` → *Known doc drift* with a named resolution owner. | Captain |

---

## 2. Gate inventory, by what it can actually prove

State as of **2026-10-16**: Actions resumed on 2026-10-08 after a three-day account-wide
outage; the weekly lane was dispatched by hand on 2026-10-09 and `e2e-silver` on 2026-10-16, when it also moved onto the PR lane.
"Executed" below means a real run with real durations, not a 1–3 s no-runner stub.

| Gate | Lane | Proves | State |
|---|---|---|---|
| `make test` | **PR** — `rust-ci` `gates`, `python-ci` `test` | unit + golden + gRPC + doc tests | **executed, green** — 3 Python versions + the cargo suite |
| `make lint` | **PR** — `python-ci` `lint`, `rust-ci` `gates` | ruff · `cargo fmt --check` · clippy `-D warnings` | **executed, green** |
| `scripts/ci/run-invariants.sh` | **PR** — `repo-invariants` | the ten whole-tree properties (`docs/ci-gates.md`) | **executed, green** — after a Compose-portability fix the first run caught |
| supply chain | **PR** — `cargo deny`, `pip-audit · bandit` | advisories · licences · bans · static security scan | **executed, green** — after one scoped advisory ignore and the bandit triage |
| `pr-linked-issue` | **PR** | the PR closes an issue or carries `no-issue` | **executed, green** |
| `make build` | **weekly** — `rust-ci` `release build` | `cargo build --release` | skipped on PRs by design; **executed, green** — once, on the 2026-10-09 dispatch |
| `docker stop` (#45) | **weekly** — `rust-ci` `docker-build` | the image handles SIGTERM as PID 1 | skipped on PRs by design; **executed, green** — run `37923509295` prints `docker stop -t 10: exit 0 after 0s (budget 5s)` / `PASS the image handles SIGTERM and exits cleanly inside the grace period`. The earlier dispatch reached the job and was cut off by `timeout-minutes: 20`; the budget is now 45 minutes, set from the measured 22 m 05 s. #45 stays open pending a human reading the proof |
| `make test-silver` / `e2e-silver` | **PR** + push to `main` + weekly + `workflow_dispatch` | the real pipeline + the silver SQL assertions | **executed, green, and gating PRs** — unfiltered `pull_request` trigger added 2026-10-16; first PR-event run `38843684967`: 3 m 45 s, both Silver steps executed. Before that, run `38833172124` (2026-10-16) was the first real run this workflow had ever had; the six `pull_request` runs from the outage remain stubs (zero steps) and prove nothing. All ten steps in **3 m 35 s** against the 30-minute budget: 233,100 signals ingested and persisted, 18 base + 16 watcher SQL assertions, 6 generator integration tests. Re-run green at 3 m 52 s on the final head (`38834675607`). Unlike the three `rust-ci` jobs above it is **not** gated to `schedule`/`workflow_dispatch`. Three runs are not a flake rate — read a week before making it *required* |
| `release` | **gated off** | build · push · provenance · SBOM · cosign signing | `workflow_dispatch` only: no registry exists, and remote deploy is unauthorized (DEC-A1/A2) |
| branch protection | — | that any of the above is *required* | **does not exist** — issue #35 |

**The asymmetry to keep in mind, restated now that it has moved.** Stages 0–8 can be
satisfied by a human or an agent in this repository today, and stage 9 finally can too:
the PR lane executes and is green. What stands between that and stage 10–11 is no longer
the platform but a repository setting only the Commander can make. Two caveats keep
"Done" honest. First, the weekly lane is green but it is **not on the
PR lane**, so a PR can be green and still have broken it; its evidence is hand-fired
dispatches (`37923509295`, `38835877392`) and one regression that only a
scheduled run caught (`38266048240` on `main`) — read the run, do not assume the lane.
`e2e-silver` was in that position until 2026-10-16 and no longer is: it runs on the PR.
Second, ***Done (local)*** remains the right status for anything whose only evidence is a
laptop, and for everything in this cycle, because nothing is on `main` yet.

**One lesson worth carrying out of the outage.** A green local run is not evidence about
CI when the toolchain differs. `run-invariants.sh` passed 10/10 locally under Compose
v5.1.4 while failing 2/10 on the runner, because v5.1.4 tolerates a duplicate volume
declaration that v2.27.0 and v2.39.4 reject. Match the version, or treat the local pass
as a smoke test only.

---

## 3. Where each stage's instructions live

| Stage | Prompt | Skill | Repo rule |
|---|---|---|---|
| 0 | `prompts/00-grill-to-intent.md` | `/grill-with-docs` | — |
| 1 | `prompts/01-intent-to-spec.md` | `/to-spec` | `plan/decisions/DEC-2026-10-06-local-scope.md` (scope guard) |
| 2 | `prompts/02-spec-to-plan.md` | `/to-tickets` | ADR-0009 R1 (disjoint paths) |
| 2a | — | — | `plan/decisions/README.md` (brief shape + evidence tags) |
| 2b | — | `/adr` (`.claude/skills/adr/`) | `docs/adr/` |
| 3 | — | `/using-git-worktrees` | ADR-0009 · `.claude/docs/AGENTIC_GITFLOW.md` |
| 4–6 | `prompts/03-plan-to-tdd.md` | `/implement` → `/tdd` | `/verification-before-completion` |
| 7 | `prompts/04-feature-before-pr.md` | `/grill-me` → `/to-tickets` | `.claude/rules/pre-pr-discipline.md` · `.github/PULL_REQUEST_TEMPLATE.md` |
| 8 | — | `/code-review` | `.claude/agents/code-quality/code-reviewer.md` |
| 9 | — | — | `docs/ci-gates.md` |
| 10–11 | — | — | `README.md` §8 · `CLAUDE.md` *Known doc drift* |

The `/grill-with-docs`, `/to-spec`, `/to-tickets`, `/implement` and `/grill-me` skills ship
with `disable-model-invocation: true` — they are **slash commands a human types**, not skills
a model may reach for on its own, and they do not appear in an agent's skill list at all.
That is deliberate: stages 0, 1, 2, 4 and 7 start on a human's word. Their absence from a
skill list is therefore not evidence that the plugin is missing or mis-installed; verify the
install with the `jq` one-liner at the top of this page instead.
