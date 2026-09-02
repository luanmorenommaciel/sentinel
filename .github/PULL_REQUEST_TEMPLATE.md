## What

<!-- One or two sentences: what changes. Not how. -->

## Why

Closes #

<!-- The issue carries the why. No issue? Say why here and add the `no-issue` label. -->

## Tests / evidence

<!-- What you ran and what it showed.

     "make test passes" is a claim. The output is the evidence:

         make test      → 178 + 57 pytest, 92 cargo, 60 silver asserts, all green
         make lint      → exit 0

     For anything visual, a screenshot. For a fix, the numbers before and after. -->

## What could this break, and how did you check?

<!-- A different question from "does it work", and the one a green suite does not answer.

     Name what you touched that something else depends on — a contract, a shared query, a
     schema, a column something reads, a public path — and say how you checked it still
     holds. "Nothing depends on this" is a good answer when it is true.

     Until CI runs every suite (#34), this section is the only thing standing between a
     regression and `main`. -->

---

<!-- Before requesting review:
     - [ ] commits are signed (`git commit -S`) — `main` requires it
     - [ ] commit messages follow Conventional Commits
     - [ ] `Co-Authored-By:` trailers for every human and LLM that contributed  -->
