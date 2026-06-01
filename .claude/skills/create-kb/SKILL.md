---
name: create-kb
description: Create a complete KB section from scratch with MCP-validated content. Use when adding documentation for a new technology used by the Sentinel project (e.g., a new Watcher signal source, a new storage backend, a new language).
---

# /create-kb

Authors a complete knowledge-base section under `.claude/kb/<category>/<name>/` by dispatching the **kb-architect** agent. The agent uses Context7 + Exa + Ref MCP servers (when available) to validate content against official docs.

## Usage

```text
/create-kb <technology>
```

Examples:
- `/create-kb kafka` (when Kafka comes back to the architecture)
- `/create-kb pagerduty-routing`
- `/create-kb great-expectations`

## What it does

1. **Asks 2-3 scoping questions:** parent category (`telemetry/`, `storage/`, `cloud/`, etc.), why we need it now (a feature, a Watcher, an integration), and the depth (lightweight pointer vs. full reference KB).
2. **Dispatches `kb-architect`** with a structured brief: scope, current production consumers in the repo, MCP servers to validate against.
3. **kb-architect produces:**
   - `index.md` — overview + decision framework (when to use, when not to)
   - `quick-reference.md` — copy-paste-ready patterns (CLI commands, code snippets, gotchas)
   - `concepts/` — deeper conceptual files for non-obvious topics (only if scope warrants)
   - `patterns/` — production-proven patterns (only after they've been used in the repo at least once — KB enrichment from real work)
4. **Updates `.claude/CLAUDE.md`** lookup table to route the new technology to this KB path.
5. **Returns a confidence score** (KB-only / KB+MCP / web-search fallback) so you know how trustworthy the content is.

## KB structure

```text
.claude/kb/<category>/<technology>/
├── index.md              # Overview, when-to-use, decision framework
├── quick-reference.md    # Patterns, snippets, gotchas
├── concepts/             # Optional deeper dives (one .md per concept)
└── patterns/             # Optional production-proven patterns
```

## When to use vs. just-search-the-web

- **Use `/create-kb`** when the technology will be referenced in at least 3 future sessions / consumed by at least one agent / mentioned in an ADR. The KB pays for itself the second time you would have re-searched.
- **Skip it** for one-off lookups. Use the web search and move on — *unless* the lookup turns out to be foundational (then close the loop with `/enrich-kb`).

## Confidence scoring (kb-architect output)

- **0.95** — KB + MCP agree (execute confidently)
- **0.85** — MCP only (proceed, note as new)
- **0.75** — KB only (proceed with disclaimer)
- **0.50** — Conflict (escalate to user)

## Related

- `/enrich-kb` — append web/MCP findings to an existing KB
- `/update-kbs` — refresh all KBs with latest docs
- `kb-architect` agent — the worker behind this skill
- `.claude/rules/kb-enrichment.md` — when to flow learnings back into KB
