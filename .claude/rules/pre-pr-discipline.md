# Pre-PR Discipline Rule

> Two checks before a pull request. Both are **detect and propose** — never act alone.
> *Last reviewed: 2026-09-02*

## 1. Does an issue cover this?

**Before starting.** Search open issues for the work about to be done.

- **Found one** → note the number. It goes in the PR as `Closes #<n>`.
- **None** → say so, propose one (title, four labels, two-line body), and **wait for
  confirmation**. Do not create it unprompted: the tracker is shared, and an issue nobody asked
  for is noise with the Commander's name on it.
- **Genuinely needs none** — a typo, a revert, a hotfix — say that instead of inventing one.
  The PR takes the `no-issue` label, which records who decided.

`pr-linked-issue.yml` fails a PR that closes no issue, so this is not optional; the only
question is whether the issue is written before the work or after it. Either is fine — the
check reads the end state, not the order.

## 2. Which documents describe what I changed?

**Before opening the PR.** A document that describes something which no longer exists is
broken by the change that made it wrong, the same as a caller of a deleted function.

```sh
# What mentions the thing you touched?
git ls-files '*.md' | xargs grep -ln "<service, target, table, flag>"

# Does any live doc still claim something you just changed?
git ls-files '*.md' | xargs grep -ln "<the old fact>"
```

For each hit: name it, say whether it still holds, and fix the ones that do not **in the same
PR**. "Nothing describes this" is a good answer when it is true.

**Do not update records to match the present.** `docs/adr/0*`, `.claude/sdd/**` and
`docs/proposals/` are history. An ADR that weighs Go against Rust is correct even though
`collector-go` is gone; rewriting it destroys what makes the decision readable. Only documents
that assert the **present** are in scope.

**Do not blanket-edit to look thorough.** A diff touching twenty markdown files to change a
date is noise that hides the one file that mattered.

## Why this exists

Issue [#40](https://github.com/luanmorenommaciel/sentinel/issues/40) swept 88 markdown files
and found `flow-ui` — a service with four boards and ~4k lines, merged in #31 — with **zero
mentions in the root README**, and nine documents asserting seven CI gates that have never
existed. Both drifted the same way: nobody was asked at the moment the change landed.

## See also

- [`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md) — the same two
  questions, aimed at humans
- [`kb-enrichment.md`](kb-enrichment.md) — the sibling rule, for knowledge that should reach the KB
- [`.claude/kb/process/crew-b-wow/index.md`](../kb/process/crew-b-wow/index.md) — PR flow, step 3b
