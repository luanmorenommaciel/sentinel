---
name: create-agent
description: Create a new specialized subagent from the standard template. Use when adding a new domain expert to .claude/agents/ (e.g., a watcher specialist, a new language helper).
---

# /create-agent

Authors a new subagent under `.claude/agents/<category>/<name>.md` using the project's standard agent template. Subagents are dispatched via the `Agent` tool with `subagent_type=<name>`.

## Usage

```text
/create-agent <name>
```

Examples:
- `/create-agent volume-watcher-engineer`
- `/create-agent kafka-bridge-specialist`
- `/create-agent slack-routing-expert`

## What it does

1. **Asks 3-4 scoping questions** about the agent's domain, when it should fire proactively, and which KBs it consumes.
2. **Picks the right category folder** under `.claude/agents/` (creates one if needed).
3. **Writes the agent .md** with mandatory frontmatter (`name`, `description`, `model`, `tools`) and a body covering: role, when to use proactively, KB routing, output format, escalation rules.
4. **Adds the agent to `.claude/CLAUDE.md`** under the Agents table.

## Required template sections

Every agent .md must contain:

- **Frontmatter:** `name`, `description` (one sentence + "Use PROACTIVELY when …" trigger), `model` (haiku/sonnet/opus per `kb/process/model-selection/`), `tools` (explicit list, no wildcards).
- **# Role** — one paragraph: what this agent does.
- **# When to use** — bullet list of "Use PROACTIVELY when …" triggers. Without this, auto-dispatch is unreliable.
- **# Knowledge sources** — KB paths the agent reads before acting (KB-first policy).
- **# Output format** — what the agent returns: code, structured report, decision, etc.
- **# Escalation** — when to defer to a human or another agent.

## Conventions

- **Filename:** `kebab-case.md`, e.g., `otel-collector-specialist.md`.
- **Category folders:** `ai-ml/`, `code-quality/`, `communication/`, `data/`, `detection/`, `exploration/`, `process/`, `storage/`, `telemetry/`, `workflow/`, `languages/`.
- **Trigger sentence is non-negotiable.** Every agent's `description:` field must contain "Use PROACTIVELY when …" — Claude Code's heuristic dispatch depends on it.
- **No wildcards in `tools:`** — list each tool explicitly. Easier to audit.

## Related

- `/create-kb` — author the KB the agent will consume
- `/create-skill` — turn the agent's common workflow into a slash command
- `kb/process/crew-b-wow/` — review process for adding a new agent (PR + 2 approvals)
- `.claude/agents/exploration/kb-architect.md` — the agent that authors KBs (you might dispatch it after creating a new specialist agent)
