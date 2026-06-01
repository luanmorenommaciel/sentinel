---
name: create-skill
description: Create a new slash command from the standard skill template. Use when a workflow becomes recurring enough to deserve its own /command (e.g., /sync-status, /open-watcher, /run-bakeoff).
---

# /create-skill

Authors a new slash command under `.claude/skills/<name>/SKILL.md` using the project's standard skill template.

## Usage

```text
/create-skill <name>
```

Examples:
- `/create-skill run-bakeoff` (orchestrate the Collector language bake-off)
- `/create-skill open-watcher` (scaffold a new Watcher crew folder + Issue)
- `/create-skill sync-summary` (auto-generate the Captain's weekly status)

## What it does

1. **Asks 3-4 scoping questions** about the skill's trigger, what it produces, and whether it needs agent dispatch or pure tool calls.
2. **Picks a single-noun lowercase name** (kebab-case).
3. **Reads [`.claude/skills/_template.md.example`](../_template.md.example)** as the canonical shape.
4. **Writes `SKILL.md`** by filling the template with mandatory frontmatter (`name`, `description`, optional `argument-hint`) and a body covering: usage, what it does, execution steps, conventions, examples, related.
5. **Adds the skill to `.claude/CLAUDE.md`** under the Skills table.

## Required SKILL.md sections

- **Frontmatter:** `name`, `description` (one sentence + trigger condition — "Use when …").
- **# /skill-name** — the slash command header.
- **# Usage** — exact syntax + 2-3 examples.
- **# What it does** — numbered list of steps the skill performs.
- **# Conventions** — file paths, naming, formats it produces.
- **# Related** — pointers to sibling skills, agents, KBs.

## Conventions

- **One concern per skill.** If `/sync-status` also opens PRs, it's two skills.
- **Idempotent by default.** Re-running the skill should converge to the same state, not duplicate.
- **State files explicit.** If the skill maintains state, document the file path and format in `# What it does`.
- **Description triggers matter.** The `description:` field is what Claude Code reads to decide whether to invoke the skill — be specific about the trigger.

## Related

- `/create-agent` — author a new specialized subagent (which a skill might dispatch)
- `/create-kb` — author a KB the skill might read
- `kb/process/crew-b-wow/` — review process for adding skills (PR + 2 approvals)
