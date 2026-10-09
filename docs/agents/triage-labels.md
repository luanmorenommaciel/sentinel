# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the label
strings that **actually exist** on `luanmorenommaciel/sentinel`.

## Correction, 2026-10-05

The first version of this file claimed the five canonical labels (`needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix`) existed here unchanged. **Four of the five do
not exist.** Verified with `gh label list`: only `wontfix` is present. Any skill that trusted the
old table would have failed on `gh issue edit --add-label`, or silently applied nothing.

This repo uses a dimensional scheme instead — `type:*`, `phase:*`, `priority:*`, `crew-*` — which
carries more information than the five flat roles. The mapping below projects the roles onto it.

## The repo's actual vocabulary

| Dimension | Labels |
| --- | --- |
| Type | `type:task` `type:feature` `type:epic` `type:component` `type:adr` `type:blocker` `type:commander-attention` |
| Phase | `phase:spec` `phase:design` `phase:backlog` `phase:build` `phase:review` `phase:ship` |
| Priority | `priority:p0` `priority:p1` `priority:p2` |
| Crew | `crew-a` `crew-b` `crew-c` `crew-d` |
| Other | `bug` `blocked` `documentation` `enhancement` `question` `good first issue` `help wanted` `no-issue` `duplicate` `invalid` `wontfix` |

## Role mapping

| Role in mattpocock/skills | Apply here | Meaning |
| --- | --- | --- |
| `needs-triage` | `phase:backlog` | Filed, not yet evaluated or prioritised |
| `needs-info` | `question` + `blocked` | Waiting on the reporter; cannot proceed |
| `ready-for-agent` | `phase:build` + `type:task` | Fully specified, an agent can take it as written |
| `ready-for-human` | `phase:build` + `help wanted` | Needs human implementation; use `type:commander-attention` instead when what's needed is a *decision*, not code |
| `wontfix` | `wontfix` | Will not be actioned |

**These are approximations, not equivalences.** `phase:backlog` says "not yet started", which is
weaker than "a maintainer must look at this"; `phase:build` says "in the build phase", which does
not by itself assert the issue is fully specified. Where a skill's behaviour depends on the
distinction, read the issue body rather than trusting the label.

Always pair with `crew-b` and a `priority:*` — every issue on this repo carries both.

## If you would rather have the canonical labels

Creating them is a one-off, and makes the mapping exact:

```sh
gh label create needs-triage    --description "Maintainer needs to evaluate this issue"
gh label create needs-info      --description "Waiting on reporter for more information"
gh label create ready-for-agent --description "Fully specified, ready for an AFK agent"
gh label create ready-for-human --description "Requires human implementation"
```

They would then sit **alongside** `type:*`/`phase:*` rather than replacing them, so decide whether
two overlapping schemes are worth the ambiguity before running this.
