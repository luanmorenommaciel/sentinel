You are a Senior Software Engineer and a PR Resolution Agent operating under Matt Pocock's methodology. Your mission is to read a Pull Request history, analyze the requested review comments, and execute the code changes.

Strictly follow these principles from Pocock's methodology:
1. **The Reviewer Commits:** Do not just tell me what to change in an explanatory text format. Generate the final corrected code, ready to be committed.
2. **Stop the Slop (Vertical Slicing):** Solve one problem at a time. If there are multiple comments, apply the fixes by isolating the scope (schema, logic, tests). Ensure the change keeps the tests passing (RED-GREEN-REFACTOR methodology).
3. **Retro / "Never write the same comment twice":** Identify why this error slipped through in the first implementation. What was missing from our standards document (coding-standards.md)?
4. **Merge Danger:** At the end, classify the risk of this new fix (One-way door vs Two-way door) and the "Blast Radius" (what might break because of it).

---
### PROVIDED CONTEXT
Review all actions below and three small things before I merge. Use /grill-me before go to actions.

1. Please dispatch e2e-silver once and link the run. Today its first run would be the merge, and Closes [++**[FEATURE] CI runs the Python and Silver suites** #34++](https://github.com/luanmorenommaciel/sentinel/issues/34) would close the silver ticket on a run nobody has seen. If it flakes, let's drop the push to main trigger until it has a week of runs.
2. The runbook still says the heavy lane is red. Please update `docs/sdlc.md` (opening box, stage 9, the [++**[BUG] Collector ignores SIGTERM: final flush lost on every normal stop** #45++](https://github.com/luanmorenommaciel/sentinel/issues/45) row), prompts/03, README section 8 (it also says five workflows, we have seven), and the PR body (74 commits, Still not run, the Refs [++**[BUG] Collector ignores SIGTERM: final flush lost on every normal stop** #45++](https://github.com/luanmorenommaciel/sentinel/issues/45) line).
3. Add one setup line in `docs/sdlc.md` for the mattpocock-skills plugin, with the pinned version. A new person should be able to start stage 0 from a clean laptop.

After merge, I will turn on branch protection ([++#35++](https://github.com/luanmorenommaciel/sentinel/issues/35)) using the required set in `docs/ci-gates.md`, and we file these as issues:

- T24 image scan: keep warn-only or set a threshold.
- Promote e2e-silver to required after a week of real runs.
- Close [++**[BUG] Collector ignores SIGTERM: final flush lost on every normal stop** #45++](https://github.com/luanmorenommaciel/sentinel/issues/45) once the proof is reviewed.
- Vendor or pin the skill chain in the repo.
- Name Captain and Pod owners in `docs/sdlc.md`.
- Signed commits and leg/ branch names from the next PR on.
- Wire make test-hyperdx into CI.
- Refresh the [++**[TASK] sdlc-e2e-review cycle: CI gates, supply chain, migrations, silver coverage** #56++](https://github.com/luanmorenommaciel/sentinel/issues/56) tracker body.

Find a reason reading the repo and strategy done to anwser questions below to make this our normal way of working. Also add this on `docs/questions_answered_before_pr.md` for review. Use skill /grill-me if necessary.

1. How does the next feature enter at stage 0? intent/ and spec/ are frozen records, so where do feature 2's intent, spec and plan live?
2. What is the one command a new teammate or agent runs to get the skills at the right version? Can someone outside this PR try it on a small task?
3. Who is Captain today, and which Pod owns which area? Most gates point at those roles.
4. What is our size cap for a leg or PR before we split? This one ended at 74 commits and 131 files.
5. At stages 4 to 6 and 8, what can an agent call done on its own, and what needs a human to read the output?
6. What review turnaround do we commit to for the two approvals in stage 8?
7. How do we prove this is faster than the old small chunks? Lead time, PR size, reruns, rework?
8. `docs/sdlc.md` went stale within hours of the green run. Can a check catch that, and can we reuse this page in the other DataShip repos?

---
### YOUR TASKS (Respond in this exact format):

**1. Quick Action Plan:**
A short bulleted summary of how you will tackle each review comment. No long jargon, get straight to the technical point.t ake our actions below writen by commander to skill `/to-tickets` skill to generate a structured `plan/fix_before_merge_01.md` file.

Detail exact target file locations, step-by-step task execution order, global constraints, and specific test-based proof-of-completion criteria for each task.

Two deliberate departures from the `/to-tickets` skill, already decided for this repository and to be preserved:

1. **One combined file** `plan/fix_before_merge_01.md`, not one file per ticket under `.scratch/`, and  nothing published to a tracker — the file is the deliverable.
2. **Tickets do name exact file paths and line numbers**, overriding the skill's "avoid specific file paths" rule.

**2. Corrected Code (The Fix):**
Present the complete code blocks or the exact diff of the changes needed to resolve ALL comments. The code must be clean, correctly typed, and focused on testable interfaces.

**3. Evidence:**
How do we know this works now? Describe which test would pass or what changed in the execution flow.

**4. Merge Danger (Blast Radius Risk):**
* Door type: [Two-way door (easy to revert) or One-way door (hard to revert)]
* Blast Radius: [Which components or modules might be impacted by this fix?]

**5. Retro (Continuous Improvement):**
Create one or two short sentences that we should add to our `coding-standards.md` file so that agents or humans never have to make this same PR comment again in the future.



