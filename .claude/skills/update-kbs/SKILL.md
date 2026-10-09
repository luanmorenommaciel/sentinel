---
name: update-kbs
description: Refresh existing KBs with latest documentation via MCP, audit structure, and track freshness. Use periodically (suggested cadence: monthly, or before a major sprint) to keep KBs from drifting.
---

# /update-kbs

Walks every KB under `.claude/kb/`, checks each entry's age and source, re-validates against authoritative MCP sources where available, and produces a freshness report.

## Usage

```text
/update-kbs [--category <category>] [--dry-run]
```

- No argument → refresh every KB
- `--category telemetry` → only refresh KBs under `kb/telemetry/`
- `--dry-run` → print what would change without writing

## What it does

1. **Inventory** — scans `.claude/kb/` and reads every `index.md` + `quick-reference.md`.
2. **Detect dated entries** — finds lines like `Added YYYY-MM-DD` or `Last verified YYYY-MM-DD`.
3. **Validate against MCP** — for each KB, hits Context7 / Exa / Ref (when available) with a "what's changed since X" query.
4. **Flag drift** — produces a list of KB entries that diverge from upstream docs (breaking changes, deprecated APIs, version bumps).
5. **Propose edits** — for each drift item, drafts the updated text in a structured proposal (does NOT auto-write — proposals are reviewed in PR).
6. **Generates a freshness report** at `.claude/kb/FRESHNESS.md` — every KB tagged with its last-verified date and confidence level.

## When to use

- **Monthly cadence** — keeps drift bounded.
- **Before a major sprint** — ensures the KBs the sprint will rely on are accurate.
- **After a major upstream release** — e.g., when `opentelemetry-rust` cuts 1.1 and our KB still references 1.0 patterns.

## Output: FRESHNESS.md

```markdown
# KB Freshness Report
Generated: 2026-06-01

| KB | Last verified | Confidence | Drift detected |
|---|---|---|---|
| telemetry/opentelemetry/ | 2026-06-01 | 0.95 | — |
| storage/clickhouse/ | 2026-05-15 | 0.85 | One pattern uses deprecated arg |
| ... | | | |
```

## Confidence scoring

Mirrors `/create-kb` and `/enrich-kb`:
- **0.95** — KB matches current MCP source verbatim
- **0.85** — Minor wording differences but semantically equivalent
- **0.75** — Some details outdated but core still valid
- **0.50** — Significant drift; needs human review

## Related

- `/enrich-kb` — write new findings into a KB (the loop closer)
- `/create-kb` — start a new KB from scratch
- `kb-architect` agent — the worker that validates KB content
- `.claude/rules/kb-enrichment.md` — the policy that drives the freshness cadence
