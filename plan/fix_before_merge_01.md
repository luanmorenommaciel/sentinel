# Fix before merge — `sdlc-e2e-review` (batch 01)

> **What this file is.** The three things the Commander asked for before PR #57 merges, taken
> through the `/to-tickets` method and written as execution tickets, plus one defect and one
> verification ticket found while reading the tree. Eight tickets, `F01`…`F08`.
>
> **Two deliberate departures from the `to-tickets` skill**, the same two `plan/core-plan.md`
> already carries: (i) this is **one combined file**, not one file per ticket under
> `.scratch/`, and nothing is published to a tracker — the file is the deliverable;
> (ii) tickets **do** name exact file paths and line numbers, overriding the skill's "avoid
> specific file paths" rule.
>
> **Line numbers are measured, not guessed.** Every number below was read out of the tree at
> `f573efb` (branch `sdlc-e2e-review`, remote branch `origin/sdlc-e2e-review`, PR #57, base
> `main` at `1aa8d92`). Edits shift the lines beneath them, so work a file's edits
> **bottom-up**, or re-grep before each edit. Each ticket gives the grep that relocates its
> target.
>
> **Evidence marks**, as in `plan/core-plan.md`: **[E]** read out of the tree ·
> **[I]** inference · **[V]** verify before implementing.

---

## Outcome — 2026-10-16

All eight executed. The tickets below are left as written: they are the work order, and the
stale claims they quote are the evidence of the defects, not assertions about the present.
This section is the amendment (`plan/` is live, G4).

| ID | Outcome |
|---|---|
| **F01** | **Done, and the inference in the ticket was wrong in a useful way.** The dispatch was *not* refused with a 422 — `gh workflow run e2e-silver.yml --ref origin/sdlc-e2e-review` was accepted even though `e2e-silver.yml` is absent from `main`. Option (b) was therefore never needed. The first dispatch, `38831986773`, **failed** inside `make up` at 2 m 37 s on a CI-only defect: the step chmodded `infra/secrets/ch_password` to `0400` under the runner's uid, and a bind mount makes that unreadable to every container's non-root user — `hyperdx/hyperdx:2.40.0` runs as `node` and its entrypoint's `[ -r ... ]` guard exited 1 after 0.55 s. Fixed to `0444` with the reason inline, the `if: failure()` dump widened to all services, and re-dispatched: `38833172124`, **green on all ten steps in 3 m 35 s** — 233,100 signals ingested and persisted, 18 base + 16 watcher silver assertions, 6 generator integration tests. Step 5 (**drop `push: branches: [main]`**) was therefore **not** taken: that instruction was conditional on the failure being unfixable |
| **F02** | Done — all five `docs/sdlc.md` edits, plus the §2 state line moved to 2026-10-16 |
| **F03** | Done — `prompts/03`; the Done-in-CI rule and "read the run, not the lane" both kept, the latter now carrying `38266048240` as its example |
| **F04** | Done — `README.md` §7 now says seven workflows with the PR/weekly split and rust-ci's six jobs; §8's red-lane reason replaced, `Done (local)` conclusion kept |
| **F05** | Done — PR body leads with red `main` (`38266048240` / RUSTSEC-2025-0134), records both `e2e-silver` dispatches, and `Closes #34` is now supportable because both halves have run (`37926101611` Python, `38833172124` Silver). Counts re-measured against `origin/main` |
| **F06** | Done, with one correction to the ticket: `claude plugin install` takes **no version flag** (verified against `claude plugin --help`), so `1.2.3` is *recorded*, not pinned. The `/plugin` spellings in step 1 were unverified; the page gives the verified `claude plugin ...` CLI form instead |
| **F07** | **The premise expired between writing and execution.** `prompts/04-feature-before-pr.md` is no longer 0 bytes — it is 5.8 kB of the Commander's own stage-7 prompt, the one this batch was generated from. It is **committed**, not deleted, and `docs/sdlc.md` §3 gains a stage-7 row pointing at it. `prompts/00`'s uncommitted `/grill-with-docs` edit is **kept** — the skill is real in 1.2.3 and calls `grilling` + `domain-modeling` — and `docs/sdlc.md` lines for stage 0 now name it instead of `/grilling` (DEC-I2). The two other untracked files, `docs/questions_answered_before_pr.md` and this one, are committed too |
| **F01b** | **Found during F08, outside the original eight.** `supply-chain (cargo deny)` went from green on `f573efb` to **red** on `9350328` with no dependency change — five advisories were published in between (four rustls CVEs, `RUSTSEC-2026-0346/0347/0348/0349`, plus `RUSTSEC-2024-0449` for `unsafe-libyaml`). Fixed in-PR: `cargo update -p rustls` 0.23.45 → 0.23.46 for the four, and a scoped dated ignore for the fifth, which has no safe upgrade. Green again on `cffeb2c`, 1 m 17 s. The lesson is recorded in `docs/ci-gates.md`: a supply-chain check is a clock, not a property of the diff |
| **F08** | `scripts/ci/run-invariants.sh` → **10 run, 0 failed** under Compose v5.1.4. `make test` / `make lint` **could not run**: no Docker daemon on this machine (`make lint-generator` fails at `dial unix .../docker.sock`). That is a **skip, not a pass**. The batch changed only Markdown and one workflow YAML — no Rust, Python or SQL — so the PR lane is the real check — and it is **green**: 10 checks pass, 5 skip by design, on `cffeb2c` |

---

## 0. How to read a ticket

Fields, in order: **Blocked by** · **Why** · **Files** (`~`edited / `+`created / `-`deleted,
with line numbers) · **Steps** (ordered) · **Proof** (a command whose *output* is the proof) ·
**Judgement** (only where a criterion cannot be proven by a command).

Frontier order: `F01` → `F06` and `F07` may start immediately. `F02`–`F05` wait on `F01`,
because each of them writes a sentence about `e2e-silver` whose truth depends on `F01`'s
outcome. `F08` is last and gates the merge.

---

## 1. Global constraints

These bind every ticket in this file. They are not restated per ticket.

| # | Constraint | Source | How it bites here |
|---|---|---|---|
| G1 | **Local scope only** — Docker + Make. No remote platform, no hosted ClickHouse, no deploy target is selected | `plan/decisions/DEC-2026-10-06-local-scope.md` (DEC-A1/A2) | No ticket may propose a registry, a cloud runner or a deployed verification. `release.yml` stays `workflow_dispatch`-only |
| G2 | **TLS is deferred** | `DEC-2026-10-06-local-scope.md` §DEC-A4 | T42 is not attempted and no ticket may reopen it. The `musl TLS spike` job stays `continue-on-error` evidence, not a gate |
| G3 | **Docs land in the same PR as the behaviour they describe** | `DEC-2026-10-06-local-scope.md` §DEC-I2 · `.claude/rules/pre-pr-discipline.md` check 2 | Every ticket here *is* a doc fix for behaviour that already landed. None of them may be deferred to a follow-up PR |
| G4 | **Records are not edited to match the present** | `.claude/rules/pre-pr-discipline.md` | `docs/adr/0*`, `intent/`, `spec/`, `docs/proposals/`, `docs/research/` are **out of scope for every ticket below**. `plan/`, `README.md`, `CLAUDE.md`, `docs/sdlc.md`, `docs/ci-gates.md`, `prompts/` are live and are amended |
| G5 | **The ten repository invariants are whole-tree properties** — any change can break one | `scripts/ci/run-invariants.sh` + `scripts/ci/invariants.d/01..10` | `F08` runs the harness. Note the harness path is `scripts/ci/run-invariants.sh`, **not** `scripts/run-invariants.sh` |
| G6 | **No hard-coded `127.0.0.1:<port>` in the `Makefile`** | invariant `09-local-compose-boundary` | No ticket here edits the `Makefile`; the constraint is listed so a ticket that grows into one does not break it |
| G7 | **No issue is created, no workflow is dispatched, no branch is pushed without the Commander saying so** | `.claude/rules/pre-pr-discipline.md` · `docs/agents/issue-tracker.md` ("propose, never create unprompted") | `F01` is the only ticket that fires anything remote, and it carries an explicit go/no-go |
| G8 | **A ticket is `Done`, not `Done (local)`, only when its checks are green in CI and the code is on `main`** | `docs/sdlc.md` stage 11 | Every ticket in this file is a documentation change; its proof is a grep or a run id, not a test suite |

---

## 2. Ticket index

| ID | Title | Blocked by | Commander's item |
|---|---|---|---|
| **F01** | Dispatch `e2e-silver` once and link the run — or record why it cannot be dispatched yet | — | 1 |
| **F02** | `docs/sdlc.md` — the runbook still says the heavy lane is red | F01 | 2 |
| **F03** | `prompts/03-plan-to-tdd.md` — same stale paragraph, second copy | F01 | 2 |
| **F04** | `README.md` §7 "five workflows" (there are seven) and §8's red-lane sentence | F01 | 2 |
| **F05** | PR #57 body — 74 commits, "Still not run", the `Refs #45` line | F01 | 2 |
| **F06** | `docs/sdlc.md` — one setup line for the skill plugin, with the pinned version | — | 3 |
| **F07** | `prompts/04-feature-before-pr.md` is an empty untracked file | — | found while reading |
| **F08** | Pre-merge verification sweep | F01–F07 | — |

---

## 3. The tickets

### F01 — Dispatch `e2e-silver` once and link the run

**Blocked by** — (startable immediately; it is the long pole, start it first)

**Why.** `e2e-silver` is the only check in `docs/ci-gates.md` that has never executed with a
real runner. **[E]** Its six recorded runs are all `pull_request` events from 2026-10-06/07,
inside the Actions outage window, each with **zero steps** and a 2–3 second wall time:

```
$ gh run list --workflow=e2e-silver.yml --limit 20 \
    --json databaseId,event,conclusion,createdAt
37566047738  pull_request  failure  2026-10-07T03:17:18Z
37564473809  pull_request  failure  2026-10-07T02:57:36Z
37563293404  pull_request  failure  2026-10-07T02:42:54Z
37554141429  pull_request  failure  2026-10-07T00:51:27Z
37551791603  pull_request  failure  2026-10-07T00:24:24Z
37549573249  pull_request  failure  2026-10-06T23:59:54Z

$ gh run view 37566047738 --json jobs \
    --jq '.jobs[]|{name,conclusion,steps:(.steps|length)}'
{"name":"e2e-silver (live ClickHouse)","conclusion":"failure","steps":0}
```

Its triggers are `workflow_dispatch`, `schedule` (Mon 06:00 UTC) and `push: branches: [main]`
(`.github/workflows/e2e-silver.yml:26-31`). None has fired. So on today's trajectory **the
first real `e2e-silver` run is the merge of PR #57 itself** — and PR #57 carries
`Closes #34` ("[FEATURE] CI runs the Python and Silver suites",
`docs/pr-body-sdlc-e2e-review.md:368`). Merging would close the issue that asked for the
silver suite to be wired, on the evidence of a run nobody has seen, which is precisely the
failure mode `docs/sdlc.md` stage 11 exists to prevent.

**The blocker found while verifying this. [E]** `e2e-silver.yml` **does not exist on the
default branch**:

```
$ git ls-tree --name-only origin/main .github/workflows/
.github/workflows/pr-linked-issue.yml
.github/workflows/rust-ci.yml
```

GitHub only honours `workflow_dispatch` for a workflow whose file is present on the default
branch; `--ref` then selects which branch's copy runs. `rust-ci` could be dispatched onto this
branch (run `37923509295`) exactly because `rust-ci.yml` **is** on `main` and already carries
`workflow_dispatch` (`git show origin/main:.github/workflows/rust-ci.yml`, `on:` block).
`e2e-silver`, `python-ci`, `repo-invariants` and `image-scan` are all new in this PR, so none
of them is on `main` yet. **[I]** The dispatch below will therefore most likely be rejected
with `HTTP 422: Workflow does not have 'workflow_dispatch' trigger`. This has **not** been
fired, so it is an inference from the documented rule plus the file listing, not a measurement.

**Files** — none in this ticket. It produces a run id that F02–F05 cite.

**Steps.**

1. Confirm the premise, read-only, and paste the output:

   ```sh
   git ls-tree --name-only origin/main .github/workflows/
   gh run list --workflow=e2e-silver.yml --limit 20 \
     --json databaseId,event,status,conclusion,createdAt
   ```

2. **Ask the Commander to choose one of three.** This is a `G7` go/no-go; do not pick for them.

   | Option | What it costs | What it buys |
   |---|---|---|
   | **(a) Try the dispatch anyway** — one command, two possible outcomes, both informative | ~30 min of runner if it starts; an instant 422 if it does not | Either the run `#34` needs, or a measured confirmation that a new workflow is undispatchable before its first merge — which is itself a process finding worth writing down |
   | **(b) Land `e2e-silver.yml` on `main` in a tiny separate PR first**, then dispatch, then merge #57 | one extra PR, one extra review | The run exists before the merge, with no change to #57's content. **Recommended if (a) returns 422** |
   | **(c) Drop `Closes #34` to `Refs #34` and merge** | `#34` stays open until the first real run | Zero extra work now; honest, and consistent with how `#45`/`#56`/`#35` are already handled at `docs/pr-body-sdlc-e2e-review.md:373` |

3. On a **yes to (a)**, the exact command — it runs the workflow as defined on this branch,
   bringing up ClickHouse, running the full generator → collector → bronze → silver pipeline,
   the 18 silver SQL assertions, the generator integration suite and the role-grant checks,
   budgeted at 30 minutes:

   ```sh
   gh workflow run e2e-silver.yml --ref origin/sdlc-e2e-review
   ```

   (`origin/sdlc-e2e-review` is the *remote branch name*, not a remote prefix — confirmed by
   `gh pr view 57 --json headRefName`.)

4. Watch it, and capture the id:

   ```sh
   gh run list --workflow=e2e-silver.yml --limit 1 \
     --json databaseId,event,status,conclusion,createdAt
   gh run watch <id>
   ```

5. **If it flakes or fails**, apply the Commander's own standing instruction: remove the
   `push: branches: [main]` trigger at `.github/workflows/e2e-silver.yml:30-31`, leaving
   `workflow_dispatch` + `schedule`, so a week of scheduled runs accumulates before the
   workflow can ever be the thing that reports on a merge. Record the reason in
   `docs/ci-gates.md` in the `e2e-silver` row (line 40 of that file).

6. Hand the outcome — run id and conclusion, or "422, option (b)/(c) taken" — to F02–F05.

**Proof.** One of:

```sh
# (a) succeeded
gh run view <id> --json databaseId,event,conclusion,jobs \
  --jq '{id:.databaseId,event:.event,conclusion:.conclusion,
         jobs:[.jobs[]|{name,conclusion,steps:(.steps|length)}]}'
# must show event=workflow_dispatch, steps > 0, and a real duration — NOT a zero-step stub
```

```sh
# (a) refused — the 422 text itself is the proof, and it justifies (b)/(c)
gh workflow run e2e-silver.yml --ref origin/sdlc-e2e-review   # expected: HTTP 422
```

**Judgement.** Whether a 30-minute job that has never run is allowed to be the thing that
closes `#34` is a Captain/Commander call, not a test outcome. The ticket records the choice;
it does not make it.

---

### F02 — `docs/sdlc.md` still says the heavy lane is red

**Blocked by** F01

**Why.** The weekly lane went green on run `37923509295` (`workflow_dispatch`, 2026-10-09, all
seven jobs success, `docker-build` 22 m 05 s). **[E]** `docs/ci-gates.md` was updated for it;
`docs/sdlc.md` was not. Two live documents now contradict each other about the same run, and
`docs/sdlc.md` is the one a new person is told to read first.

**One new fact F02 must also carry. [E]** There has been a *later* weekly run, and it is red —
but on `main`, not on this branch:

```
$ gh run view 38266048240 --json displayTitle,headSha,conclusion,jobs
rust-ci 1aa8d92c failure        (event: schedule, 2026-10-12, branch main)
  release build                     -> success
  docker-build (distroless image)   -> success
  integration (ClickHouse round-trip) -> success
  gates (fmt · clippy · test)       -> success
  supply-chain (cargo deny)         -> failure
```

That is `main`'s older copy of `rust-ci.yml` (note the job is named
`integration (ClickHouse round-trip)`, and there is no `musl TLS spike` leg), failing on the
`RUSTSEC-2025-0134` advisory that **this branch already fixes** with the scoped, dated ignore in
`services/collector-rust/deny.toml`. It is worth a sentence because it is the cleanest argument
for merging: the scheduled lane on `main` is red today and this PR is the fix.

**Files** — `~ docs/sdlc.md` (114 lines total). Five edits. **Work them bottom-up.**

| Line(s) | What is wrong now | What it should say |
|---|---|---|
| **82–83** | "the weekly lane has run exactly once, by hand, and came back red on three of its four jobs" | it has run three times: red (`37875017554`), **green on all seven jobs** (`37923509295`), and red again on `main`'s *older* workflow copy (`38266048240`, `cargo deny` only). The regression window argument in the surrounding paragraph still stands and should be kept |
| **74** | `e2e-silver` row: "**not yet executed** — its only six runs are outage stubs" | keep the stub sentence (it is accurate and measured), and append F01's outcome: the dispatched run id, or "undispatchable until the workflow is on `main` — see F01" |
| **73** | `docker stop` (#45) row: "**still not executed** — the 2026-10-09 dispatch reached the job, but the amd64+arm64 build hit `timeout-minutes: 20`" | **executed and passing** in run `37923509295`: `docker stop -t 10: exit 0 after 0s (budget 5s)` / `PASS the image handles SIGTERM and exits cleanly inside the grace period`. The timeout is now 45 minutes, set from the measured 22 m 05 s |
| **53** | stage 9 cell: "**Today: half of it is reachable**" … "the **weekly lane ran once, on 2026-10-09, and it is red**: run `37875017554` … `release build` passed; `integration` failed, `musl TLS spike` failed on both targets, and `docker-build` was cut off by its own 20-minute timeout" | PR lane green **and** weekly lane green on `37923509295`; the only never-executed check is `e2e-silver` (plus F01's outcome); branch protection still absent (#35), so the green is still advisory |
| **15–30** | the opening box: "The **weekly lane ran for the first time on 2026-10-09 and came back red**" … "issue #45's `docker stop` proof *still* has no run" | both lanes green; `#45`'s proof is on the record; what remains is `e2e-silver` and branch protection. Keep the Compose-version lesson at lines 27–29 verbatim — it is still true and it is the most useful sentence in the box |

**Steps.**

1. Re-locate every target before editing:
   `grep -n "37875017554\|came back red\|still not executed\|not yet executed\|20-minute" docs/sdlc.md`
2. Edit lines **82–83**, then **74**, then **73**, then **53**, then **15–30** — bottom-up, so
   earlier line numbers stay valid.
3. Do **not** touch `docs/ci-gates.md` in this ticket except for F01 step 5's one row; it is
   already correct and re-editing it risks desynchronising the two again.
4. Keep every run id. The value of these documents is that each claim names the run it came
   from; replacing a stale id with prose loses that.

**Proof.** All three greps return nothing:

```sh
grep -n "weekly lane ran once\|came back red\|still not executed" docs/sdlc.md   # → empty
grep -n "timeout-minutes: 20\b" docs/sdlc.md                                     # → empty
grep -c "37923509295" docs/sdlc.md                                               # → ≥ 1
```

and the two live documents agree:

```sh
diff <(grep -o '379235[0-9]*' docs/sdlc.md | sort -u) \
     <(grep -o '379235[0-9]*' docs/ci-gates.md | sort -u)   # → no output
```

---

### F03 — `prompts/03-plan-to-tdd.md` carries the same stale paragraph

**Blocked by** F01

**Why.** The same red-lane claim is duplicated in the prompt that every TDD leg is started
from, so an agent reading it is told the weekly lane is red before it does any work.
**[E]** `prompts/03-plan-to-tdd.md:30-39`.

**Files** — `~ prompts/03-plan-to-tdd.md:33-39`

Current text, verbatim (lines 33–39):

> Actions runs again as of 2026-10-08 and the **PR lane** (`gates`, `lint`, the pytest matrix,
> both supply-chain jobs, `invariants`, `linked-issue`) now proves something. The **weekly lane**
> proves much less: it was dispatched by hand for the first time on 2026-10-09 (run
> `37875017554`) and came back red — only `release build` passed, `integration` and both
> `musl TLS spike` legs failed, `docker-build` hit its 20-minute timeout, and `e2e-silver`
> has still never executed. Treat a weekly job as unproven until you have read its run. A ticket is Done
> when its checks are green **in CI** and the code is on `main`; until then it is *Done (local)*.

**Steps.**

1. Keep lines **30–32 unchanged** — the Compose-version lesson is the reason this paragraph
   exists and it has not expired.
2. Replace lines 33–38 with: PR lane green; weekly lane green on `37923509295`, including the
   first-ever pass of `integration` and the `docker stop` proof for `#45`; `e2e-silver` is the
   one job still unexecuted (plus F01's outcome).
3. Keep the final sentence at lines 38–39 (`A ticket is Done when its checks are green in CI
   and the code is on main`) **verbatim** — it is the rule, not a status report.
4. Keep "Treat a weekly job as unproven until you have read its run." It is now *more* useful,
   not less: `38266048240` shows a weekly job going red on `main` four days after going green
   on a branch.

**Proof.**

```sh
grep -n "came back red\|37875017554" prompts/03-plan-to-tdd.md   # → empty
grep -c "37923509295" prompts/03-plan-to-tdd.md                  # → ≥ 1
grep -c "Done (local)" prompts/03-plan-to-tdd.md                 # → ≥ 1   (rule preserved)
```

---

### F04 — `README.md` §7 says five workflows, and §8 says the lane is red

**Blocked by** F01

**Why.** **[E]** Two separate defects in the same file.

*(i)* `README.md:338` — "**CI is five workflows**" and then names five:
`rust-ci`, `python-ci`, `repo-invariants`, `release`, `pr-linked-issue`. There are **seven**
files in `.github/workflows/` on this branch; the two missing from the sentence are
`e2e-silver.yml` (T20) and `image-scan.yml` (T24) — both of which the same README documents in
§8. The sentence also describes `rust-ci` as "(gates · integration · cargo-deny ·
docker-build)", omitting `release build` and `musl TLS spike`, and says nothing about the
two-lane PR/weekly split that PR #59 introduced and `docs/ci-gates.md` is built around.

```
$ ls .github/workflows/
e2e-silver.yml  image-scan.yml  pr-linked-issue.yml  python-ci.yml
release.yml     repo-invariants.yml                  rust-ci.yml
```

*(ii)* `README.md:394-397` — the paragraph justifying why all 43 tickets read `Done (local)`
says "the weekly CI lane's first and only run (`37875017554`) came back red". That is now
contradicted **by the same file**: `README.md:499-505` already says "**The weekly CI lane is
green.** Run `37923509295` …". Line 396 is the older of the two and is the one to fix.

**Files** — `~ README.md:338` · `~ README.md:394-397`

**Steps.**

1. Edit **line 394–397 first**, then line 338 (bottom-up).
2. Line 394–397: keep the conclusion (**every ticket stays `Done (local)`**) and replace only
   the reason. The surviving reason is sufficient on its own: *nothing is merged to `main`
   yet*, which is half of stage 11's two-part test. Do not weaken the conclusion — the merge
   has not happened, so `Done (local)` is still correct.
3. Line 338: "CI is **seven** workflows", listing all seven with their lane, matching
   `docs/ci-gates.md`'s two-lane table. Link `e2e-silver.yml` and `image-scan.yml` the way the
   other five are linked.
4. **Do not** restate the per-job results here. `docs/ci-gates.md` is the single place those
   live; duplicating them is how §7 and §8 drifted apart in the first place.

**Proof.**

```sh
grep -n "five workflows" README.md                      # → empty
ls .github/workflows/*.yml | wc -l                      # → 7
grep -c "seven workflows" README.md                     # → 1
grep -n "e2e-silver.yml\|image-scan.yml" README.md | sed -n '1,4p'   # both appear in §7
grep -n "first and only run" README.md                  # → empty
```

and the file no longer contradicts itself:

```sh
grep -n "weekly.*lane.*red\|came back red" README.md    # → empty
```

---

### F05 — PR #57's body: the counts, "Still not run", and the `Refs #45` line

**Blocked by** F01

**Why.** The PR body is maintained as a checked-in file and pushed from it. **[E]** The live
body and `docs/pr-body-sdlc-e2e-review.md` are the same text
(`gh pr view 57 --json body` → 26,531 chars; the file is 460 lines). Three claims in it have
expired.

*(i)* **Line 7** — "**72 commits, 131 files changed** — 71 and 131 measured at `3405b68`".
Measured now at `f573efb` against the real base:

```
$ git rev-parse origin/main
1aa8d92c214da1b393930cf5e3d4e6fa00a11143
$ git rev-list --count origin/main..HEAD
74
$ git diff --name-only origin/main...HEAD | wc -l
131
```

74, not 72; files unchanged at 131. **[V]** Re-measure at the actual head when F05 runs — this
branch is still receiving commits, and F02/F03/F04/F06/F07 each add one.
**Note:** the local `main` ref in this worktree is stale at `3af2ee7`; measuring against
`main` instead of `origin/main` gives 76/132 and is wrong. Always use `origin/main`.

*(ii)* **Line 172** — "**Still not run:** `make test-silver` and `make test-hyperdx` (Docker),
and the `docker stop` assertion itself, which has only been exercised down its skip and
`REQUIRE_DOCKER=1` paths — its first real run is the weekly `docker-build` job." The
`docker stop` clause is false as of run `37923509295`, which printed
`docker stop -t 10: exit 0 after 0s (budget 5s)` / `PASS`. `make test-silver` and
`make test-hyperdx` remain genuinely unrun in CI and stay in the sentence.

*(iii)* **Lines 262 and 373-380** — the `Refs #45` block explains that `#45` is `Refs` not
`Closes` because "`docker-build` … **skips on PRs** … Its first real execution is a weekly run
that has not happened yet." That has happened. The *decision* to keep it at `Refs` is still
right — `docs/pr-body-sdlc-e2e-review.md:257` already says "The issue stays **open** pending
sign-off" and the Commander's post-merge list keeps "Close #45 once the proof is reviewed" —
but the stated **reason** must change from *has not run* to *has run and awaits human sign-off*.
Line 262 ("`e2e-silver` … has still never run") takes F01's outcome.

**Files** — `~ docs/pr-body-sdlc-e2e-review.md:7` · `:172` · `:262` · `:373-380`
(and `:361`, "this branch is 72 commits ahead of `main`", the same stale count a second time)

**Steps.**

1. `grep -n "72 commits\|Still not run\|still never run\|Refs #45" docs/pr-body-sdlc-e2e-review.md`
   to relocate.
2. Edit bottom-up: `373-380`, then `361`, then `262`, then `172`, then `7`.
3. Re-measure the counts at the real head immediately before editing line 7, with the two
   commands above, and keep the body's own convention of naming the commit the figure was
   measured at. Leave the `<details>` block at lines 12–69 alone — it is an explanation of
   *historical* figures and is a record, not a status claim (G4).
4. Push the body only when the Commander approves:
   `gh pr edit 57 --body-file docs/pr-body-sdlc-e2e-review.md` (G7 — this is a remote write).

**Proof.**

```sh
# the file agrees with the tree
test "$(grep -oE '\*\*[0-9]+ commits' docs/pr-body-sdlc-e2e-review.md | grep -oE '[0-9]+')" \
     = "$(git rev-list --count origin/main..HEAD)" && echo COUNT-OK

grep -n "72 commits" docs/pr-body-sdlc-e2e-review.md     # → empty
grep -n "docker stop. assertion itself" docs/pr-body-sdlc-e2e-review.md   # → empty
grep -c "Refs #45" docs/pr-body-sdlc-e2e-review.md       # → ≥ 1  (decision preserved)
```

```sh
# the live body matches the file, after the push
diff <(gh pr view 57 --json body --jq .body) docs/pr-body-sdlc-e2e-review.md   # → no output
```

---

### F06 — One setup line in `docs/sdlc.md` for the skill plugin, with the pinned version

**Blocked by** — (startable immediately)

**Why.** `docs/sdlc.md:9-13` names the method — "the **Matt Pocock skill chain**
(`mattpocock-skills@claude-plugins-official`, installed at user scope …)" — but never says how
to install it or which version. A new person on a clean laptop reaches stage 0 and has nothing
to run. `docs/sdlc.md:100-106` then references `/grilling`, `/to-spec`, `/to-tickets`,
`/implement`, `/tdd`, `/code-review` as if they were already present.

**Measured, so the pin is a fact and not a guess. [E]**

```
$ jq '.plugins["mattpocock-skills@claude-plugins-official"]' \
     ~/.claude/plugins/installed_plugins.json
[{ "scope": "user",
   "installPath": ".../claude-plugins-official/mattpocock-skills/1.2.3",
   "version": "1.2.3",
   "installedAt": "2026-10-02T03:42:02.283Z",
   "gitCommitSha": "c55ee46073ed923f86ce59a5eb3b6d895095d1b7" }]

$ jq -r '.source.repo' <<<"$(jq '.["claude-plugins-official"]' \
     ~/.claude/plugins/known_marketplaces.json)"
anthropics/claude-plugins-official
```

All six skills the page names are present in that install, and so is
`setup-matt-pocock-skills`, which is the skill that wrote `CLAUDE.md` → *Agent skills* and
`docs/agents/{issue-tracker,triage-labels,domain}.md`:

```
$ jq -r '.skills[]' .../mattpocock-skills/1.2.3/.claude-plugin/plugin.json
./skills/engineering/to-spec
./skills/engineering/to-tickets
./skills/engineering/implement
./skills/engineering/tdd
./skills/engineering/code-review
./skills/engineering/setup-matt-pocock-skills
./skills/productivity/grilling
./skills/productivity/grill-me
...  (25 in total)
```

**The one thing the setup line must say that is not obvious.** `to-spec`, `to-tickets`,
`implement`, `grill-me` and `setup-matt-pocock-skills` carry
`disable-model-invocation: true` in their frontmatter, so they **do not appear in an agent's
skill list at all** and cannot be auto-invoked — they are slash commands a human types.
`docs/sdlc.md:112-114` already says this, correctly. It must stay, and the setup line should
sit above it, because the natural first conclusion of someone who does not see them listed is
that they are not installed. They are.

**Files** — `~ docs/sdlc.md`, insert after line 13 (the end of the existing plugin paragraph,
before the `>` block that opens at line 15)

**Steps.**

1. Insert a short fenced block — one command, pinned, plus the two one-liners that *prove* the
   install rather than assuming it:

   ```sh
   # once per machine, from a clean laptop
   /plugin marketplace add anthropics/claude-plugins-official
   /plugin install mattpocock-skills@claude-plugins-official   # pinned: 1.2.3

   # then, once per repository — writes CLAUDE.md § Agent skills and docs/agents/*
   /setup-matt-pocock-skills
   ```

2. Add one sentence recording the pin and how to re-check it:
   `jq -r '.plugins["mattpocock-skills@claude-plugins-official"][0].version' ~/.claude/plugins/installed_plugins.json` → `1.2.3`.
3. Add one sentence: the five `disable-model-invocation` skills are invisible to an agent's
   skill list by design; absence from that list is **not** evidence they are missing — point at
   lines 112–114.
4. **[V]** Confirm the two `/plugin` command spellings against the Claude Code version the team
   is on before merging. The *version*, the *marketplace repo* and the *skill inventory* above
   are measured; the exact CLI syntax is not, and a setup line that does not work is worse than
   none.
5. Do **not** vendor the plugin into the repo in this PR. That is on the Commander's post-merge
   issue list (§5 item 4) and it is a real decision — a user-scope install is not reproducible
   across the crew, but vendoring a third-party skill set has its own cost.

**Proof.**

```sh
grep -n "1.2.3" docs/sdlc.md                                  # → ≥ 1
grep -n "setup-matt-pocock-skills" docs/sdlc.md               # → ≥ 1
grep -n "disable-model-invocation" docs/sdlc.md               # → ≥ 1  (lines 112-114 intact)
```

and the pin in the page matches the machine:

```sh
test "$(grep -oE '1\.2\.3' docs/sdlc.md | head -1)" \
   = "$(jq -r '.plugins["mattpocock-skills@claude-plugins-official"][0].version' \
        ~/.claude/plugins/installed_plugins.json)" && echo PIN-OK
```

---

### F07 — `prompts/04-feature-before-pr.md` is an empty untracked file

**Blocked by** — (startable immediately)

**Why.** **[E]** `prompts/04-feature-before-pr.md` exists, is **0 bytes**, and is untracked:

```
$ git status --porcelain prompts/
 M prompts/00-grill-to-intent.md
?? prompts/04-feature-before-pr.md
```

An empty `prompts/04-*` next to four written prompts reads as a stage that exists and has no
instructions. `docs/sdlc.md:98-110` has no row for a stage 4-prompt, so nothing references it.
Either it ships with content or it does not ship.

A second, smaller item in the same directory: `prompts/00-grill-to-intent.md` is **modified and
uncommitted**, and its first line now reads "Use `/grill-with-docs` e taskspec init …" while
`docs/sdlc.md:100` names stage 0's skill as `/grilling`. `grill-with-docs` is a real skill in
the 1.2.3 install (`./skills/engineering/grill-with-docs`), so this is a genuine divergence
between the prompt and the stage table, not a typo in one of them.

**Files** — `+ prompts/04-feature-before-pr.md` **or** `- prompts/04-feature-before-pr.md` ·
`~ docs/sdlc.md:100` (only if the stage-0 skill is realigned)

**Steps.**

1. Ask the Commander which: write it, or delete it. `prompts/04` is presumably the "how does
   feature 2 enter" prompt that `docs/questions_answered_before_pr.md` Q1 proposes a home for —
   if so, it should be written *after* Q1 is ruled on, not guessed at now.
2. If it ships empty-handed, `rm prompts/04-feature-before-pr.md` — nothing references it.
3. Decide whether `prompts/00`'s uncommitted change is intended. If `/grill-with-docs` is now
   stage 0's skill, `docs/sdlc.md:100` must say so (G3 — same PR). If it was exploratory,
   revert it: `git checkout -- prompts/00-grill-to-intent.md`.

**Proof.**

```sh
# no zero-byte prompt ships
find prompts -name '*.md' -size 0 | grep . && echo FAIL || echo OK

# nothing uncommitted is left in prompts/
git status --porcelain prompts/        # → empty, or only intentional, staged changes

# prompt and stage table name the same stage-0 skill
grep -o '/grill[a-z-]*' prompts/00-grill-to-intent.md | sort -u
grep -o '/grill[a-z-]*' docs/sdlc.md   | sort -u       # → the two sets must match
```

---

### F08 — Pre-merge verification sweep

**Blocked by** F01, F02, F03, F04, F05, F06, F07

**Why.** G5: the ten invariants are whole-tree properties, so even a documentation-only batch
can break one (invariant `04-no-plaintext-secrets` greps the tree; `09-local-compose-boundary`
greps the `Makefile`). And this whole batch exists because two live documents drifted apart
inside a day — the sweep is the check that they now agree.

**Files** — none. This ticket only reads.

**Steps, in order.**

1. The invariant harness — note the path is `scripts/ci/run-invariants.sh`:

   ```sh
   bash scripts/ci/run-invariants.sh
   ```

   **[E]** Expect `10 run, 0 failed`. Record the Compose version alongside it
   (`docker compose version`): `docs/ci-gates.md` records that v5.1.4 passes 10/10 where
   v2.27.0 and v2.39.4 failed 2/10 on a conflict v5.1.4 tolerates. A green local run is only
   evidence about CI if the versions match.

2. The cross-document consistency sweep — every stale claim this batch removes, in one pass:

   ```sh
   git ls-files '*.md' | xargs grep -ln "came back red\|first and only run\|five workflows\|72 commits\|still not executed"
   ```

   Expect **nothing live**. Hits under `docs/adr/`, `intent/`, `spec/`, `docs/proposals/`,
   `docs/research/` are records and are correct as they stand (G4) — if any appear, name them
   and leave them.

3. The run ids cited across the live set must be the same set:

   ```sh
   for f in docs/sdlc.md docs/ci-gates.md README.md prompts/03-plan-to-tdd.md \
            docs/pr-body-sdlc-e2e-review.md; do
     echo "$f: $(grep -oE '3[0-9]{10}' "$f" | sort -u | tr '\n' ' ')"
   done
   ```

   Every id printed must resolve: `gh run view <id> --json conclusion`.

4. The three unit suites and the lints, to confirm a docs batch broke nothing
   (`make test` includes `test-hyperdx`, Makefile line 362 — Docker required):

   ```sh
   make test
   make lint
   ```

5. The PR lane, on the real pushed head:

   ```sh
   gh pr checks 57
   ```

**Proof.** Quoted output, not summarised (`docs/sdlc.md` stage 6):

```
bash scripts/ci/run-invariants.sh      → 10 run, 0 failed
git ls-files '*.md' | xargs grep -ln "came back red\|five workflows\|72 commits"   → (empty)
make test                              → all suites pass
make lint                              → all clean
gh pr checks 57                        → the PR lane green
```

**Judgement.** Step 4 needs a Docker daemon. On a machine without one, `make test` is a skip,
not a pass, and must be reported as such — the repo's own standard
(`docs/pr-body-sdlc-e2e-review.md:160`, "environment has no Docker daemon").

---

## 4. Execution order, one line

```
F01 ─┬─► F02 ─► F03 ─► F04 ─► F05 ─┐
     │                             ├─► F08 ─► merge
F06 ─┴─────────────────────────────┤
F07 ────────────────────────────────┘
```

Start **F01** first: it is the only ticket with a remote round-trip and a 30-minute run, and
four other tickets write a sentence whose truth depends on its outcome. **F06** and **F07** are
independent and can run in parallel with F01's wait.

---

## 5. To file, not to do — the post-merge issue list

**Nothing in this section is work in PR #57.** These are the issues the Commander said they
would file *after* merge, recorded here so the list survives the session and so no one mistakes
them for tickets above. Per `docs/agents/issue-tracker.md` and G7, issues are **proposed, never
created unprompted** — this is the proposal; the Commander creates them.

Branch protection (#35) is turned on first, from the required-check set in `docs/ci-gates.md`.
That is the Commander's stated first post-merge action, and it is what turns every "no" in that
table's *Required today* column into a "yes".

| # | To file | Why it is post-merge, not now | Related |
|---|---|---|---|
| 1 | **T24 image scan: keep warn-only, or set a blocking threshold** | A policy call, not a test. `docs/ci-gates.md` already carries the calibration: `python:3.12-slim` gives 44 HIGH / 0 CRITICAL unfiltered and 0/0 with `--ignore-unfixed`, and the fixable count moved 0→1→0 within fifteen minutes on 2026-10-08 as `CVE-2026-103111` gained and lost a published fix. Flipping `IMAGE_SCAN_EXIT_CODE` to `1` in `scripts/ci/audit-images.sh` is the whole change | T24 · REQ-H-12 |
| 2 | **Make `e2e-silver (live ClickHouse)` a *required* check, after a week of real PR runs** | It is already a PR-lane check (unfiltered `pull_request` trigger, first PR-event run `38843684967`, green, 3 m 45 s), so nothing is left to build. What remains is the branch-protection setting, which is GitHub state and only exists post-merge. `SPEC §16` names it the likeliest to flake, so read the flake rate across a week of PRs first: a flaky required check blocks every merge | #34 · #35 · `docs/ci-gates.md` |
| 3 | **Close #45 once the `docker stop` proof is reviewed** | The proof exists (run `37923509295`, both the two cargo flush tests and the PID-1 `docker stop` assertion). What is missing is a human reading it — which is exactly why the PR says `Refs #45`, not `Closes #45` | #45 |
| 4 | **Vendor or pin the skill chain in the repo** | Today the chain is a **user-scope** install at `1.2.3` on one laptop (F06's evidence). Nothing in the repository pins it, so two crew members can run `/to-tickets` at different versions and get different output. The options — vendor into `.claude/`, pin in a committed manifest, or document-and-accept — are a decision, not a doc fix | F06 · `docs/sdlc.md:9-13` |
| 5 | **Name Pod owners in `docs/sdlc.md`** | **Captain half closed on 2026-10-16:** the Commander named Adilson Cesar, recorded in `docs/sdlc.md` and `.claude/CLAUDE.md`. **Pod half still open:** `.claude/CLAUDE.md` § Crew B layout lists **B1, B3 and B4 as `TBD`**, so stages 2a and 3 (owner *Pod*) point at roles nobody currently holds. See `docs/questions_answered_before_pr.md` Q3 | #56 · `docs/sdlc.md` |
| 6 | **Signed commits and `leg/` branch names from the next PR on** | Both are WoW rules (`.claude/CLAUDE.md` § Working agreement; ADR-0009 R4) and neither is met by this branch: it is named `sdlc-e2e-review`, not `leg/<area>/<task>-v<n>`. Changing it now would rewrite 74 commits for no gain | ADR-0009 |
| 7 | **Wire `make test-hyperdx` into CI** | The target exists (`Makefile:407`) and `make test` already depends on it (`Makefile:362`), but `python-ci.yml`'s `test` job runs `make test-generator` and `make test-flow-ui` **only** — HyperDX's suite runs nowhere in CI. ADR-0011 is `Proposed` and HyperDX is post-cycle, outside T01–T48, so adding a CI job is new work | ADR-0011 · `python-ci.yml:66-85` |
| 8 | **Refresh the #56 tracker body** | `[TASK] sdlc-e2e-review cycle: CI gates, supply chain, migrations, silver coverage` is `OPEN` with `phase:build`. After merge the cycle is landed and its body describes a plan rather than an outcome | #56 |

One more worth adding to that list, found while writing F02 — **`main`'s scheduled `rust-ci`
is red**. Run `38266048240` (`schedule`, 2026-10-12, `main` at `1aa8d92`) failed on
`supply-chain (cargo deny)`. Merging PR #57 is the fix, since this branch carries the scoped
`RUSTSEC-2025-0134` ignore in `services/collector-rust/deny.toml`. **[V]** Confirm the next
scheduled run on `main` goes green after the merge, rather than assuming it; if it does not,
that is a new issue, not a known one.
