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

**Do not mark a ticket Done on the strength of a local run alone.** GitHub Actions has not
executed since 2026-10-05 (account-wide failure, jobs end in 1–3 s with no runner assigned), so
no workflow in `.github/workflows/` has proved anything. A ticket is Done when its checks are
green **in CI** and the code is on `main`; until then it is *Done (local)*.
