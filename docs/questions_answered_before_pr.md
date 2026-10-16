# Eight questions, answered before the PR

> **What this is.** `docs/sdlc.md` describes a process that was reverse-engineered from one
> cycle that had already happened. Running it a *second* time — as the normal way of working
> rather than as a retrospective — turns up eight questions the page does not answer. This
> file answers each from evidence in this repository, and ends each with a **proposed norm**:
> one sentence that could be adopted and then pointed at.
>
> **Where the repo genuinely does not answer, it says so.** Three of the eight (Q3, Q6, Q7)
> have no answer in the tree. Each of those proposes the *smallest* decision that would close
> it rather than inventing a figure, because a made-up SLA in a process document is worse than
> an admitted gap — `plan/decisions/README.md`'s evidence tags exist for exactly this reason.
>
> Status: **for review.** Nothing here is ratified. Measured at `f573efb`, 2026-10-15.

---

## Q1 — How does the next feature enter at stage 0?

**`intent/` and `spec/` are frozen records, so where do feature 2's intent, spec and plan live?**

### What the repo says

The chain for cycle 1 is four singular files: `intent/core-intent.md`,
`intent/design-spec.md`, `spec/core-spec.md`, `plan/core-plan.md`. "Core" is doing the work
of a cycle name, and `docs/sdlc.md:42-44` names those exact paths as the artifact of stages
0, 1 and 2 — so a literal second run overwrites cycle 1's record.

The repo is explicit that it must not. `.claude/rules/pre-pr-discipline.md` separates
documents that **assert the present** from documents that are **history**, and names
`intent/` and `spec/` in the second group; `docs/sdlc.md` stage 7 repeats it
("`docs/adr/`, `intent/`, `spec/`, `docs/proposals/` are records — left alone"). But the same
rule puts `plan/` in the *first* group: "`plan/core-plan.md` is the live ticket registry and
`plan/decisions/` are live briefs … Amend those; don't freeze them" (`CLAUDE.md`, final
paragraph of *Status & what's next*).

So the three stages split cleanly, and the repo has already demonstrated both halves:

- **Frozen per cycle** — `intent/`, `spec/`. `plan/core-plan.md:1-13` shows the pattern: it
  did not rewrite its tickets when scope changed, it added a dated superseding header pointing
  at `plan/decisions/DEC-2026-10-06-local-scope.md`.
- **Live across cycles** — `plan/`, `plan/decisions/`, `docs/ci-gates.md`, `README §8`,
  `docs/adr/`.

### Answer

Feature 2 gets its **own directory per frozen stage, named for the cycle, not for "core"**,
and **reuses** the live registries. There is already a precedent for the naming: this very
batch of pre-merge work is `plan/fix_before_merge_01.md`, numbered rather than "core".

```
intent/sdlc-e2e-review/core-intent.md      ← cycle 1, moved, unchanged
intent/sdlc-e2e-review/design-spec.md
spec/sdlc-e2e-review/core-spec.md
plan/core-plan.md                          ← stays; live registry, gains T49…

intent/<cycle-2-slug>/intent.md            ← cycle 2 starts here
spec/<cycle-2-slug>/spec.md
plan/decisions/DEC-*.md                    ← shared, never per-cycle
```

Ticket IDs keep counting (`T49…`), because `README §8`'s registry and every `Blocked by` edge
in `plan/core-plan.md` are keyed on them; restarting at `T01` would make two tickets share an
ID across the two documents that cite them.

**One caveat, named rather than hidden.** Moving cycle 1's files breaks every inbound link —
`README.md:384`, `plan/core-plan.md:15-20`, `docs/sdlc.md:42-44`, `prompts/01`, `prompts/02`
all point at the current paths. The cheaper variant is to leave cycle 1 where it is and only
*new* cycles get a directory. That is uglier and it is probably right; it is a Captain call.

### Proposed norm

> Each cycle gets `intent/<cycle>/` and `spec/<cycle>/`, frozen on the day its PR merges and
> never edited again. `plan/core-plan.md`, `plan/decisions/`, `docs/ci-gates.md` and
> `README §8` are shared and are amended. Ticket IDs are monotonic across all cycles.
> `prompts/00`–`03` are templates and are parameterised by the cycle slug, not copied.

---

## Q2 — What is the one command a new teammate or agent runs to get the skills at the right version?

**And can someone outside this PR try it on a small task?**

### What the repo says, and what is actually installed

`docs/sdlc.md:9-13` names the method — "the **Matt Pocock skill chain**
(`mattpocock-skills@claude-plugins-official`, installed at user scope …)" — and never gives a
command or a version. That is the whole gap.

Measured, so the answer is a fact rather than a claim:

```
$ jq '.plugins["mattpocock-skills@claude-plugins-official"]' ~/.claude/plugins/installed_plugins.json
[{ "scope": "user",
   "version": "1.2.3",
   "installPath": ".../cache/claude-plugins-official/mattpocock-skills/1.2.3",
   "gitCommitSha": "c55ee46073ed923f86ce59a5eb3b6d895095d1b7",
   "installedAt": "2026-10-02T03:42:02.283Z" }]

$ jq -r '.["claude-plugins-official"].source.repo' ~/.claude/plugins/known_marketplaces.json
anthropics/claude-plugins-official
```

**The whole chain `docs/sdlc.md` claims is installed, is installed.** `to-spec`, `to-tickets`,
`implement`, `tdd`, `code-review`, `grilling`, `grill-me` and `setup-matt-pocock-skills` are
all in that 1.2.3 manifest (25 skills in total). This is worth stating plainly because it is
easy to conclude the opposite: five of them carry `disable-model-invocation: true` in their
frontmatter, which means they **do not appear in an agent's skill list at all** and an agent
cannot reach for them. They are slash commands a human types. `docs/sdlc.md:112-114` already
records this and is correct.

### Answer

Two commands, not one, and the split is load-bearing: one is per machine, one is per
repository.

```sh
# per machine
/plugin marketplace add anthropics/claude-plugins-official
/plugin install mattpocock-skills@claude-plugins-official   # pinned: 1.2.3

# per repository — writes CLAUDE.md § Agent skills and docs/agents/{issue-tracker,triage-labels,domain}.md
/setup-matt-pocock-skills
```

`CLAUDE.md` § *Agent skills* already records that `/setup-matt-pocock-skills` ran here, and
`docs/agents/triage-labels.md` is its most useful output: it records that **four of the five
canonical triage label strings do not exist in this repo**, projecting them onto the real
`type:*`/`phase:*`/`priority:*` scheme. A newcomer who skips that step will have `/to-tickets`
try to apply labels that are not there.

**Can someone outside this PR try it on a small task? Yes, and that is the right first use.**
`.claude/CLAUDE.md` § Terminology guardrails names **good-first-issue** "the sacred tag —
Captain pre-tags 5-10 per sprint". A good-first-issue is one `/to-spec` → `/to-tickets` →
`/implement` pass with a blast radius of one file. Two cautions, both measured: `1.2.3` is
installed at **user scope on one laptop** and nothing in this repository pins it, so two
people can run `/to-tickets` at different versions and get different output (this is item 4
on the post-merge issue list); and the five human-only skills mean a newcomer who expects an
agent to auto-invoke `/to-tickets` will wait forever.

### Proposed norm

> `docs/sdlc.md` carries the two setup commands and the pinned version, and the pin is
> re-checked with `jq -r '.plugins[…][0].version'` whenever the page is edited. A newcomer's
> first use of the chain is a `good-first-issue`, not a cycle. Until the chain is vendored or
> pinned in-repo, every cycle's PR body states the plugin version it was run at.

---

## Q3 — Who is Captain today, and which Pod owns which area?

### The repo does not answer this, and that is the finding

**Captain is defined as a rotating hat with no current holder.** `.claude/CLAUDE.md`
§ Terminology guardrails: "**Captain** = sprint facilitator (a *hat*, not a permanent role —
rotates each sprint)." No file names who wears it this sprint.

**Three of the four Pods have no members.** `.claude/CLAUDE.md` § Crew B layout:

| Pod | Owns | Astronautas |
|---|---|---|
| B1 | Arrival + Parse (W01, W02) | **TBD** |
| B2 | OTel Collector | Alex Botelho · Victor Urquiola · Ruan Pomponet |
| B3 | Volume + Schema / Latency + Storage | **TBD** |
| B4 | Action Dispatcher | **TBD** |

**And the Pod↔layer mapping itself is unratified.** `CLAUDE.md` § *Known doc drift* lists it
as live drift: README's POD3 = storage/read-layer versus `.claude/CLAUDE.md`'s B3 = four
Watcher crews. `.claude/CLAUDE.md` carries its own do-not-propagate warning on that table.
Resolution owner: "Captain / Commander" — which is circular, since naming the Captain is the
thing that is missing.

### Why it matters more than it looks

`docs/sdlc.md:40-56` assigns an owner to all twelve stages. Count them: **Captain owns stages
0, 1, 2, 10 and 11** and co-owns 2b and 8; **Pod** owns 2a and 3; **Commander** owns 9's
setting and co-owns 2b. Of the twelve, only stage 4–7 (leg agent, author) have an owner who
exists today. Stage 11 — "a ticket moves to Done only when…" — is Captain-owned, which is why
43 tickets have sat at `Done (local)` with nobody empowered to move them. Separately,
`.claude/CLAUDE.md` § Working agreement requires "2 approvals: first peer, second Captain" and
PR #57 has **zero reviews** after nine days open.

### Proposed norm — the smallest decision that closes it

Not an org chart. Two lines in `docs/sdlc.md`, under the existing *Owner vocabulary* block at
line 36:

> **Captain this sprint:** `<name>`, from `<date>` to `<date>`. **Pod owners:** B1 `<name>` ·
> B2 Alex Botelho · B3 `<name>` · B4 `<name>`. Changed at Sync 02 each sprint; a stale name
> here is a bug.

And one rule: **a stage whose owner is `TBD` falls to the Commander by default**, so no gate
is unowned. Ratifying the Pod↔layer mapping is a *separate*, larger decision and should not
block naming a Captain — the drift table can keep carrying it.

---

## Q4 — What is our size cap for a leg or PR before we split?

**This one ended at 74 commits and 131 files.**

### What the repo says

ADR-0009 defines the unit hierarchy and gives each level a **duration**, never a size:
"**Leg** | one parallelizable chunk of a swimlane … hours–days, disposable" and "**Task** …
minutes–hours" (`docs/adr/0009-agentic-gitflow.md:44-45`). R1 caps a leg by *path
disjointness*, not by diff size. ADR-0009 § *When not to use legs* says the structure "costs a
branch, a worktree, a PR, a review" — a cost argument for a floor, not a ceiling.

So: **there is no cap anywhere in the repo.** But there is a distribution, and it is the
better evidence.

```
$ gh pr list --state merged --limit 12 --json number,changedFiles,commits
#59  2 files    1 commit      #43 12 files  20 commits    #41 15 files   2 commits
#39  6 files    5 commits     #32 46 files  17 commits    #31 28 files   9 commits
#30  7 files    2 commits     #29 15 files   3 commits    #28 51 files   4 commits
#27 40 files    3 commits     #26 233 files 16 commits
```

Median merged PR: **15 files**. PR #57 at **131 files / 74 commits / +14,644 −1,507** is the
second-largest in the repository's history, behind only #26 (the 233-file README realignment,
which was almost entirely one new document).

### What the oversize actually cost — measured, not asserted

The repo paid for it in ways that are on the record:

- **The PR body needs a `<details>` block to explain its own size.**
  `docs/pr-body-sdlc-e2e-review.md:12-69` reconciles four different file counts (131, 207,
  215, 218) and two commit counts, because different measures disagreed. That block is ~58
  lines of arithmetic about the diff rather than about the change.
- **Nine days open, zero reviews** (created 2026-10-06; `reviews: []`). Compare #31/#32/#39/
  #41/#43, all of which were created and merged the same day at 6–46 files.
- **A 1,291-line plan file and a 114-line process page landed in the same PR as the code they
  describe**, which is DEC-I2 working as designed but also means a reviewer cannot read the
  process and the implementation separately.

### Answer

A cap on *files* is the wrong instrument — #26 was 233 files and was easy to review, because
231 of them were one document. The reviewable unit is **the number of independent things a
reviewer must hold in their head at once**, which maps to the plan's own structure.

### Proposed norm

> **One wave per PR, and a wave is capped at ~40 files or ~20 commits, whichever comes first.**
> `plan/core-plan.md` already groups T01–T48 into four waves; this cycle merged all four at
> once. Past that line, either split at the next wave boundary or write one paragraph in the
> PR body naming why it could not be split. The number is calibrated to the repo's own
> history — the merged median is 15 files and the largest same-day review was 46 — not to an
> industry figure. Revisit after three cycles with real review-time data.

---

## Q5 — At stages 4 to 6 and 8, what can an agent call done on its own, and what needs a human?

### What the repo already decides

The repo's rule is not "agents are untrusted". It is sharper: **an agent may close anything
whose criterion is a command's exit status; a human must read anything whose criterion is a
judgement.** It is already written in two places.

`plan/core-plan.md:35-39` defines the ticket fields and says **Judgement** is present "*only*
where a criterion cannot be proven by a test". That field *is* the human-attention marker, and
it is per ticket rather than per stage.

`docs/adr/0009-agentic-gitflow.md:211-216` (R3) then places human attention by blast radius:

| Fan-in | Review | Merge |
|---|---|---|
| leg → swimlane | **1 reviewer (may be the `code-reviewer` agent)** | squash |
| swimlane → main | **2 approvals: peer + Captain** | merge commit |

An agent reviewer is explicitly sufficient at the inner fan-in and explicitly insufficient at
the outer one.

### Answer, stage by stage

| Stage | Agent can close alone | Needs a human to read the output |
|---|---|---|
| **4 RED** | Yes, fully. The criterion is mechanical: a test exists, it was run, it failed, the failing output is quoted (`docs/sdlc.md:48`, `prompts/03` prompt 1). Nothing here is a judgement | Only if the agent cannot make the test fail — which usually means the ticket's **Proof** is not a proof |
| **5 GREEN** | Yes. "The previously failing test passes" (`docs/sdlc.md:49`) is an exit status | — |
| **6 Three green checks** | Yes for the *running*: `make test`, `make lint`, `make build`, `bash scripts/ci/run-invariants.sh`, all quoted | **Yes for one thing, and it is the lesson of the outage.** A green local run is not evidence about CI unless the toolchain matches: `run-invariants.sh` passed 10/10 locally under Compose v5.1.4 while failing 2/10 on the runner (`docs/ci-gates.md`). A human — or a CI run — must confirm the environment, and a ticket stops at ***Done (local)*** until then |
| **8 Code review** | **The Standards axis, yes.** `/code-review` runs two axes and Standards is "does the code follow this repo's documented coding standards" — checkable against `.claude/docs/RUST_PROJECT_STANDARDS.md`, `make lint`, the invariants | **The Spec axis, no.** "Does it do what the ticket's REQ asked" is a judgement about intent. And two of the four open decision briefs are explicitly non-delegable: `DEC-I2` says "**No recommendation.** The choice is which rule yields; engineering evidence cannot rank two repo rules" |

The three things in this cycle that no agent could have closed, as a sanity check on the
table: the DEC-A1/A2/A4 rulings (a Commander's authorization), the T24 blocking threshold
("T24 rules the blocking threshold a policy call rather than a test",
`docs/ci-gates.md`), and signing off issue #45's proof.

### Proposed norm

> An agent closes a stage when every criterion is a command's exit status, and quotes the
> output rather than summarising it. A human reads the output whenever (i) the ticket carries
> a **Judgement** field, (ii) the evidence is local-only and the gate is a CI gate, or
> (iii) the question is *should we*, not *does it*. Stage 8's Standards axis may be an agent;
> its Spec axis may not. `docs/sdlc.md`'s stage table gains an **Agent-closable?** column so
> this is readable without this page.

---

## Q6 — What review turnaround do we commit to for the two approvals in stage 8?

### The repo does not answer this either

`.claude/CLAUDE.md` § Working agreement requires "2 approvals … first peer, second Captain"
and sets a cadence for *meetings* — "Weekly sync Tuesday Zoom ~60min" — but names no review
SLA. `docs/sdlc.md:52` restates the two approvals with no time attached.

The observed distribution, which is the only evidence available:

| PR | Created → merged | Files |
|---|---|---|
| #59, #43, #41, #39, #32, #31 | **same day** | 2–46 |
| #26 | 7 days | 233 |
| #28 | 8 days | 51 |
| #27 | 13 days | 40 |
| #29, #30 | **15 days** | 15, 7 |
| **#57 (this one)** | **9 days and counting, zero reviews** | 131 |

Two readings, and they do not agree: turnaround is same-day when someone is actively working
the queue, and a fortnight when nobody is. That is not a process, it is availability. #29 and
#30 took 15 days at 15 and 7 files, so **size is not what predicts the wait** — attention is.
Which puts this question back on Q3: there is no SLA because there is no named Captain to
carry one.

### Proposed norm — deliberately modest

A commitment nobody can keep is worse than none, and this crew is a mentorship cohort with
weekly contact, not a full-time team. So the norm is tied to the cadence that already exists:

> **First response within two working days; both approvals by the next weekly sync.** "First
> response" means a review posted — including "I can't get to this, reassign" — not a merge.
> A PR that misses the sync goes on that sync's agenda by default. The Captain of the sprint
> owns the queue; if no Captain is named, it falls to the Commander (Q3's default rule).
>
> Measure it from the next cycle: `gh pr list --state merged --json createdAt,mergedAt`.
> Three cycles of data, then set a real number. Until then this is a target, and
> `docs/ci-gates.md`'s own distinction applies — **a target, not a description**.

---

## Q7 — How do we prove this is faster than the old small chunks?

**Lead time, PR size, reruns, rework?**

### The honest starting point: the repo cannot prove it today

There is no baseline, and the comparison as posed is not well-formed. Before this cycle the
repo had **one workflow** (`rust-ci.yml`) and no CI for Python or silver — issue #34 is exactly
that: "235 tests and 60 SQL asserts existed, were green, and gated nothing"
(`docs/pr-body-sdlc-e2e-review.md:370-372`). And for three of this cycle's days Actions was
dead account-wide (2026-10-05 → 10-08), so no cycle-time figure spanning that window means
anything. Comparing a cycle with gates against a cycle with no gates on *lead time* will make
the gated cycle look slower while being the point of the exercise.

### What the repo can prove, and the four numbers to actually track

Three of the four metrics the question names are already derivable from `gh`, and the fourth
is the only one that needs a new habit.

| Metric | Command | Baseline that exists today |
|---|---|---|
| **Lead time** | `gh pr list --state merged --json createdAt,mergedAt` | Median same-day; tail 15 days (#29, #30). High variance, driven by attention not size — see Q6 |
| **PR size** | `gh pr list --state merged --json changedFiles,commits` | Median **15 files**; max 233 (#26); this cycle 131 (#57) — see Q4 |
| **Reruns** | `gh run list --json conclusion,event,headBranch` | Measurable from now. The one real signal already visible: `e2e-silver` has 6 recorded runs and **all six are zero-step outage stubs**, so the rerun count was 100% noise until 2026-10-08 |
| **Rework** | — | **Not derivable.** Nothing in the repo distinguishes a commit that adds behaviour from one that fixes behaviour added earlier in the same branch |

### The metric that would actually settle it

Not speed. **Escaped-defect count: how many defects a cycle's gates caught that the previous
shape would have shipped.** This cycle has a real number for it, and it is the strongest
argument in the whole PR:

- `invariants` found a **Compose portability defect** that passed 10/10 locally and failed
  2/10 on the runner (`docs/ci-gates.md`) — it had already reached `main` unnoticed.
- `cargo deny` found `RUSTSEC-2025-0134`.
- `bandit` found B110 ×3, a real silent-`except: pass` smell, now fixed.
- The first heavy-lane run (`37875017554`) found three defects plus a design flaw in the
  concurrency group — "none was findable without an actual run"
  (`docs/pr-body-sdlc-e2e-review.md:270-272`).
- `integration` **had never passed before** run `37923509295`, and issue #45's `docker stop`
  proof had never executed by any path.

That is **seven defects** this shape caught and the old shape could not have. Against it, the
cost is honest and should be stated with it: 131 files, 9 days without a review, and a
documentation set that went stale within hours of the green run (Q8).

### Proposed norm

> Each cycle's PR body ends with a four-line **Cycle metrics** block: lead time (created →
> merged), PR size (files / commits), CI reruns to green, and **defects caught by a gate that
> the previous cycle's gates would have missed**. The first three come from `gh`; the fourth
> is written by hand, one line each, as the cycle runs. Three cycles of these replace the
> argument with a table. Until then, the claim is "this shape catches more", **not** "this
> shape is faster" — the repo has evidence for the first and none for the second.

---

## Q8 — `docs/sdlc.md` went stale within hours of the green run. Can a check catch that, and can we reuse this page in the other DataShip repos?

### Part A — can a check catch it?

**What happened, precisely.** Run `37923509295` turned the weekly lane green on 2026-10-09.
`docs/ci-gates.md` was updated in the same push. `docs/sdlc.md` was not — so two live
documents, in the same directory, written by the same cycle, disagreed about the same run id.
`README.md` then disagreed with **itself**: line 396 says the weekly lane "came back red"
while line 499 says "The weekly CI lane is green". These are the F02 and F04 tickets in
`plan/fix_before_merge_01.md`.

**Yes, and the mechanism already exists.** `scripts/ci/run-invariants.sh` runs every executable
assert in `scripts/ci/invariants.d/` in filename order, and its header says adding one is a
new file rather than an edit to a shared one, "so two legs never collide on a path". There are
ten asserts; all ten are infrastructure properties. **None looks at documentation.** An
eleventh would be the first, and it is cheap.

Three candidate asserts, in increasing order of ambition. The first is the one that would have
caught *this* failure:

1. **`11-run-ids-resolve.sh`** — every `3[0-9]{10}` run id cited in the live doc set
   (`docs/sdlc.md`, `docs/ci-gates.md`, `README.md`, `prompts/*.md`,
   `docs/pr-body-sdlc-e2e-review.md`) must resolve via `gh run view`, and **two documents
   citing the same run must not disagree about its conclusion**. Needs network + `gh`, so it
   runs in CI and skips cleanly offline — the same skip-with-exit-0 pattern
   `services/collector-rust/tests/docker-stop.test.sh` already uses for a missing Docker
   daemon, with `REQUIRE_GH=1` in CI turning the skip into a failure.
2. **`12-no-contradiction.sh`** — a small deny-list of phrase pairs that cannot both be true in
   the live set (`came back red` beside `the weekly lane is green`; a workflow count beside
   `ls .github/workflows/*.yml | wc -l`). Blunt, but it is exactly the class of failure
   observed, and the "five workflows" defect (F04) is a one-line grep.
3. **A freshness header** — each live doc carries `<!-- live: verified <date> -->` and the
   assert fails if a doc in the live set was changed without its date moving. Weakest of the
   three: it proves someone touched the date, not that they re-read the page.

`docs/ci-gates.md`'s own framing applies to all three: a check that cannot tell *clean* from
*never ran* is worse than no check. So assert 11 must fail loudly when `gh` is unavailable in
CI, not pass quietly.

### Part B — can this page be reused in the other DataShip repos?

Partly, and the split is clean. Read `docs/sdlc.md` as two layers:

| Layer | Portable? | Why |
|---|---|---|
| **The twelve-stage spine** (stage → artifact → gate → owner) and the skill chain it wraps | **Yes.** Nothing in it is Sentinel-specific. The `prompts/00`–`03` templates travel with it | It is the Matt Pocock chain plus a gate column; another crew would fill the same table differently |
| **ADR-0009's seam → swimlane → leg → task**, R1–R4 | **Yes**, with the caveat that R1 is only worth the cost at 2+ concurrent agents | ADR-0009 § *When not to use legs* already says so |
| **The ten invariants** | **No.** `01-single-clickhouse-image`, `07-silver-mv-determinism`, `10-hyperdx-is-read-only` are properties of *this* pipeline | The **harness** (`run-invariants.sh` + drop-in `invariants.d/`) is fully portable; the asserts are not |
| **§2's gate inventory and every run id** | **No.** It is a status report on this repo | Copying it is how a page goes stale on arrival |
| **The two-lane PR/weekly split** | **Yes as a pattern**, no as a configuration | The reasoning in *Why the heavy jobs are weekly* generalises; the five named jobs do not |

**One thing worth exporting above everything else**, because it is this repo's hardest-won
lesson and it cost three days: *a green local run is not evidence about CI unless the
toolchain matches* (Compose v5.1.4 passing 10/10 where v2.27.0 failed 2/10). That sentence is
portable to any repo with a local harness.

**And one caution about reuse.** This page was written *after* the cycle it describes, from a
tree that had already been built. Dropping it into a repo that has not run a cycle would
produce a page describing gates that do not exist — which is precisely what
`.claude/CLAUDE.md` § Working agreement already warns about its own seven-gate list: "a
**target, not a description**: none runs".

### Proposed norm

> **(a)** Add `scripts/ci/invariants.d/11-run-ids-resolve.sh` in the next cycle, and treat the
> live documentation set as a declared list inside that script, so adding a live doc is a
> one-line change. Start with assert 1; add 2 only if a contradiction recurs.
>
> **(b)** Extract `docs/sdlc.md` into two files before reusing it: `docs/sdlc.md` (the
> portable spine, the stage table, the owner vocabulary, the skill-chain setup) and
> `docs/sdlc-status.md` (§2's gate inventory, every run id, every "today:"). Only the first
> travels to another DataShip repo; the second is regenerated per repo. The staleness that
> prompted this question was entirely in the second kind of content living inside the first
> kind of file.

---

## What this file does not settle

- **Q3 and Q6 are genuinely blocked on a person, not on evidence.** No amount of reading the
  tree names a Captain or sets a review SLA. Both proposals are the smallest possible
  decision, and Q6's depends on Q3's.
- **Q7's "faster" cannot be answered at all yet** — there is no baseline, and the three days
  of Actions outage poison any lead-time figure spanning this cycle. The proposal replaces the
  question with one the repo can answer.
- **Q1's migration has a cost that is not estimated here** — moving `intent/` and `spec/`
  breaks five known inbound links and possibly more.
- **Q8's assert 11 is a sketch, not a reviewed script.** It needs `gh` auth on the runner and
  the `actions: read` permission to call `gh run view`. Only `pr-linked-issue.yml` uses `gh`
  today, and it declares `contents: read` + `pull-requests: read`; `repo-invariants.yml`
  declares no `permissions:` block at all, so adding this assert changes that workflow's
  token scope — a small but real decision, not a drop-in.
