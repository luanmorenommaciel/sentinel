Replace `<TICKET>` below with the ticket ID you are executing from `plan/core-plan.md`
(`T01`…`T48`). Work the frontier order in that file; never a hard-coded "Task 1".

### Prompt 1 (RED Phase — write the failing test first):

Let's begin `<TICKET>` from `plan/core-plan.md`. Run the `/implement` skill to write a failing
test for that ticket's **Proof** criteria, touching only the paths the ticket declares. Do not
write feature implementation code yet — run the test runner and confirm that it fails first,
and paste the failing output.

### Prompt 2 (GREEN Phase — implement & pass the test):

Now write the minimal implementation code to make the failing test pass. Use the test runner
output as a feedback loop to iterate until the test succeeds.

### Prompt 3 (Three green checks verification):

Run the full verification checks for `<TICKET>`. Do not report done until all three pass, with
the command output quoted, not summarised:

1. **Tests pass** — `make test` (generator + flow-ui + HyperDX pytest, collector cargo), plus
   `make test-silver` when the ticket touches `migrations/` or `silver.*`.
2. **Linting passes with zero errors** — `make lint` (ruff over both Python services,
   `cargo fmt --check` + clippy for the collector).
3. **The project compiles cleanly** — `make build`.

Then run `scripts/ci/run-invariants.sh`: the ten repository invariants are properties of the
whole tree, so any ticket can break one.

**Do not mark a ticket Done on the strength of a local run alone.** A local green is evidence
about a laptop, not about CI: during the 2026-10-05–10-08 Actions outage `run-invariants.sh`
passed 10/10 here while failing 2/10 on the runner, purely on a Compose version difference.
Actions runs again as of 2026-10-08 and the **PR lane** (`gates`, `lint`, the pytest matrix,
both supply-chain jobs, `invariants`, `linked-issue`) now proves something. The **weekly lane**
proves it too, as of run `37923509295` (`workflow_dispatch`, 2026-10-09): all seven jobs green,
including the first-ever pass of `integration` and issue #45's `docker stop` proof. `e2e-silver`
is green on run `38833172124` (2026-10-16) — ten steps, 3 m 35 s, the real pipeline and 34
silver SQL assertions — its first real run after six zero-step outage stubs.

Neither lane runs on a PR, and both reached green only after a red run exposed a real defect
(`37875017554`; `38831986773`, which died inside `make up`). A *later* scheduled run on `main`,
`38266048240`, then went red on `cargo deny`. Treat a weekly job as unproven until you have read
its run. A ticket is Done
when its checks are green **in CI** and the code is on `main`; until then it is *Done (local)*.
