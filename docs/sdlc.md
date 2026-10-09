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

> **The one thing to read before claiming anything is finished:** GitHub Actions has not
> executed since 2026-10-05 — jobs end in 1–3 s with `runner_name: ""` and zero steps, across
> every workflow here and other repositories on the same account. **No gate in column *Gate*
> below has run in CI.** A green local run is evidence about a laptop, not about `main`. The
> honest status for work in that state is ***Done (local)***, and `docs/ci-gates.md` says the
> same thing from the checks' side.

---

## 1. The stage table

**Owner vocabulary.** *Pod* = the unit that owns a feature end-to-end (ADR-0009 §Decision).
*Captain* = Crew B's engineering lead. *Commander* = Luan Moreno, who alone can take the
decisions marked `type:commander-attention` and change GitHub repository settings.

| # | Stage | Artifact | Gate — what must be true to leave the stage | Owner |
|---|---|---|---|---|
| 0 | **Grill → Intent**<br>reverse-engineer the verified As-Is | `intent/core-intent.md` | Every claim about the current system is read out of the tree, not inferred. Unknowns are left as `[TBD]` rather than guessed. Driven by `prompts/00-grill-to-intent.md` + `/grilling`. | Captain |
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
| 9 | **CI gates** | the status checks in `docs/ci-gates.md` | The required set is green. **Today: unreachable.** No branch-protection rule exists on `main` (issue #35, API returns 404) and no workflow has executed since 2026-10-05. `docs/ci-gates.md` is the table to configure the required set *from*, once Actions runs. | Commander (setting) · Captain (table) |
| 10 | **Merge to `main`** | the squash commit | Conventional Commits · signed (`git commit -S`) · `Co-Authored-By:` for every human and LLM contributor. ADR-0009 amends the WoW's blanket "squash-merge to main" for legs. | Captain |
| 11 | **Status record** | [README §8](../README.md#8-current-status) per-ticket registry | A ticket moves to **Done** only when its checks are green **in CI** and the code is on `main`. Otherwise it is ***Done (local)*** — done within DEC-2026-10-06's local scope and unverified against any deployed target. Drift between a record and reality goes in `CLAUDE.md` → *Known doc drift* with a named resolution owner. | Captain |

---

## 2. Gate inventory, by what it can actually prove

| Gate | Runs | Proves | State today |
|---|---|---|---|
| `make test` | locally, and `python-ci` / `rust-ci` | unit + golden + gRPC + doc tests | runs locally; never executed in CI |
| `make lint` | locally, and `python-ci` / `rust-ci` | ruff · `cargo fmt --check` · clippy `-D warnings` | runs locally; never executed in CI |
| `make build` | locally, and `rust-ci` | the images build | runs locally; never executed in CI |
| `make test-silver` | locally, and `e2e-silver` | the silver read models' SQL assertions | runs locally; never executed in CI |
| `scripts/ci/run-invariants.sh` | locally, and `repo-invariants` | the ten whole-tree properties (`docs/ci-gates.md`) | all ten pass locally; never executed in CI |
| `pr-linked-issue` | on every PR | the PR closes an issue or carries `no-issue` | never executed |
| `e2e-silver` | on every PR | the real pipeline end-to-end against live ClickHouse | never executed; the check most likely to flake — read a week of real runs before promoting it |
| `release` | `main` / tags | build · push · provenance · SBOM · cosign signing | **gated off**: no container registry exists, and remote deploy is unauthorized (DEC-A1/A2) |
| branch protection | — | that any of the above is *required* | **does not exist** — issue #35 |

**The asymmetry to keep in mind:** stages 0–8 can be satisfied by a human or an agent in this
repository today. Stages 9–11 cannot — they depend on GitHub Actions executing and on a
repository setting only the Commander can make. Any claim of "Done" that spans that line is a
claim about the future.

---

## 3. Where each stage's instructions live

| Stage | Prompt | Skill | Repo rule |
|---|---|---|---|
| 0 | `prompts/00-grill-to-intent.md` | `/grilling` | — |
| 1 | `prompts/01-intent-to-spec.md` | `/to-spec` | `plan/decisions/DEC-2026-10-06-local-scope.md` (scope guard) |
| 2 | `prompts/02-spec-to-plan.md` | `/to-tickets` | ADR-0009 R1 (disjoint paths) |
| 2a | — | — | `plan/decisions/README.md` (brief shape + evidence tags) |
| 2b | — | `/adr` (`.claude/skills/adr/`) | `docs/adr/` |
| 3 | — | `/using-git-worktrees` | ADR-0009 · `.claude/docs/AGENTIC_GITFLOW.md` |
| 4–6 | `prompts/03-plan-to-tdd.md` | `/implement` → `/tdd` | `/verification-before-completion` |
| 7 | — | — | `.claude/rules/pre-pr-discipline.md` · `.github/PULL_REQUEST_TEMPLATE.md` |
| 8 | — | `/code-review` | `.claude/agents/code-quality/code-reviewer.md` |
| 9 | — | — | `docs/ci-gates.md` |
| 10–11 | — | — | `README.md` §8 · `CLAUDE.md` *Known doc drift* |

The `/to-spec`, `/to-tickets` and `/implement` skills ship with
`disable-model-invocation: true` — they are **slash commands a human types**, not skills a
model may reach for on its own. That is deliberate: stages 1, 2 and 4 start on a human's word.
