### Prompt 1 (RED Phase - Write Failing Test First):
Let's begin Task 1 from `/plan/core-plan.md`. Run the `/implement` skill to write a failing test for this task's proof-of-completion criteria. Do not write feature implementation code yet—run the test runner and confirm that it fails first.

### Prompt 2 (GREEN Phase - Implement &amp; Pass Test):
Now write the minimal implementation code to make the failing test pass. Use the test runner output as a feedback loop to iterate until the test succeeds.

### Prompt 3 (Three Green Checks Verification):
Run the full verification checks for Task 1. Do not report done until all three checks pass: 

1. Tests pass
2. Linting passes with zero errors
3. The project compiles cleanly.