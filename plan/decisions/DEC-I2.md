# DEC-I2 — `pre-pr-discipline` same-PR doc fixes vs ADR-0009 disjoint leg paths

**Owner** Captain / Commander · **Unblocks** T45 directly (the plan header says T45-T48); the other three docs legs are separately blocked by T29, T39/T34, T44

Tags: **[M]** measured this session · **[D]** document assertion · **[R]** reasoned.

## 1. The question

When a leg invalidates a claim in `README.md` or `CLAUDE.md`, does the repo (a) let a per-wave docs leg fix it later, (b) serialize the legs that touch those files, or (c) amend ADR-0009's R1 to exempt docs from path disjointness?

## 2. Why it's open

- `.claude/rules/pre-pr-discipline.md` check 2: a doc that describes something that no longer exists "is broken by the change that made it wrong"; fix the ones that do not hold "**in the same PR**" (`git show HEAD:.claude/rules/pre-pr-discipline.md`, last reviewed 2026-09-02). That file is deleted in the working tree and being recreated by its owner, so the wording may change.
- ADR-0009 R1: "Two open legs in a swimlane **may not** declare overlapping paths. If they must overlap, they are one leg — or the shared part is extracted into a leg that lands first" (`docs/adr/0009-agentic-gitflow.md:198-201`). ADR-0009 is `Proposed`, not ratified.
- Spec §12.3 and plan §4 pick a per-wave docs leg (T45-T48) and say plainly this violates the letter of check 2. `leg/docs/wave-<n>-v1` satisfies R1 (its paths are disjoint) and breaks rule 2 (docs lag code by one leg).

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **(a) Per-wave docs leg** (spec/plan choice) | Docs are wrong between a leg merging and its wave's docs leg; breaks the letter of rule 2 | Same-PR doc fixes |
| **(b) Serialize legs touching the two files** | Loses parallelism on whichever legs touch them; scope depends on the measurement below | R1's parallel fan-out for those legs |
| **(c) Amend R1: docs exempt from disjointness** | Textual merge conflicts on shared lines land at fan-in; relies on R2's rebase discipline | R1 as an unconditional rule |

**No recommendation.** The choice is which rule yields; engineering evidence cannot rank two repo rules, and the plan says the same (§4, T45 Judgement). What would break the tie: whether the Captain weights "docs and code never disagree on `main`" over "legs never conflict textually". The measurement below lowers the cost of (b) and (c) relative to what the plan assumes.

## 4. Established facts

- **[M] The premise "all nine W1 legs invalidate a claim in `README.md`/`CLAUDE.md`" is not supported by grep.** Today `README.md` (274 lines) and `CLAUDE.md` (102 lines) contain **zero** occurrences of `24.3`, `25.4`, `docker-compose.yaml`, `generator-python/docker-compose`, or `63`. The claims W1 plausibly invalidates are about six lines: `README.md:169` (workflows list: "rust-ci.yml · pr-linked-issue.yml"), `README.md:211` ("Today only `rust-ci.yml`..."), `README.md:263` (open item 6, "Python CI gate... not yet added"), `CLAUDE.md:44-45` (Make target table), `CLAUDE.md:67` (the `default`-user and vestigial `otelgen` gotcha). By leg, that points at roughly `python-gates`, `invariants`, `registry-provenance` and `ch-migrate`, not nine. This is a grep over specific patterns, not an audit; other claims could exist.
- **[M] T45's W1 proofs are already satisfied before any change.** `grep -rn "clickhouse-server:24.3" README.md CLAUDE.md` and `grep -rn "generator-python/docker-compose" README.md` return 0 today, so they prove nothing. The `otelgen` proof is satisfied only by the word in `CLAUDE.md:10,23,52` (the generator's CLI name) and `README.md:163`, and the vestigial-user mention at `CLAUDE.md:67`.
- **[M] The "73-vs-63" test-count gap is not in `CLAUDE.md`.** `63` appears in `services/flow-ui/README.md:95,238` and `services/flow-ui/ARCHITECTURE.md:252`. Plan §10 item 5 and T45 attribute it to `CLAUDE.md`.
- **[D]** Squash vs merge-commit (spec §12.5) is a separate unratified question the same owners must settle; it interacts with how docs-leg attribution survives.
- **[R]** Under (a), a docs leg that collects four legs' claims per wave also needs to know what they changed; each leg's PR description would have to carry its invalidated claims, or the docs leg re-greps. The plan does not say which.

## 5. What it unblocks

T45 (W1 docs leg; blocked by T24 + DEC-I2). Plan header says T45-T48; the ticket table blocks T46-T48 on T29, T39/T34 and T44 only, so they are held by DEC-I2 only in prose. If the ruling is "other way", plan says T45-T48 dissolve and each implementation ticket absorbs its own doc fix (breaking disjointness).

## 6. What it cannot settle

- Which rule is right.
- Whether the six-line measurement generalises to W2-W4 (silver inventory, deployment posture).
- Whether `.claude/rules/pre-pr-discipline.md` is reworded when recreated.
