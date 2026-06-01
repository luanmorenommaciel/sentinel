---
name: enrich-kb
description: Write web-search or MCP findings back into the KB so the same search doesn't recur. Use immediately after a successful web search for any technology that has (or should have) a KB entry.
---

# /enrich-kb

Closes the loop: when a session ends up doing a web search or MCP lookup for a technology, this skill captures the finding into the relevant `.claude/kb/` so future sessions hit the KB first instead of re-searching.

## Usage

```text
/enrich-kb <technology>
```

Examples:
- `/enrich-kb opentelemetry-rust` (after researching the OTel Rust 1.0 release)
- `/enrich-kb clickhouse` (after solving a Native-protocol gotcha)
- `/enrich-kb gcp-monitoring` (after discovering an exact schema field)

## What it does

1. **Locates the KB** matching the technology (or asks if there's no match — and offers `/create-kb` if missing).
2. **Asks: what was the finding?** Pastes the web/MCP excerpt, links the sources, captures the gotcha.
3. **Routes the finding to the right file:**
   - **Quick gotchas / commands** → `quick-reference.md`
   - **Conceptual insights** → `concepts/<topic>.md` (creates if absent)
   - **Production patterns proven once** → `patterns/<pattern>.md` (creates if absent)
4. **Cross-references the source.** Web URLs go into a `## Sources` section so future readers can re-verify.
5. **Updates `index.md`** if the finding changes the KB's decision framework.

## When to use

- After any web search where the result will likely be relevant again
- After an MCP query (Context7 / Exa / Ref) that produces non-obvious detail
- After a debugging session that uncovered a real-world gotcha
- After a successful pattern that hadn't been documented (production-proven)

**Don't enrich for** one-off lookups whose answer won't recur (e.g., a specific version-pinned CVE).

## Confidence + dating

Every enrichment entry is timestamped and tagged with a confidence level:

```markdown
> **Added 2026-06-01 · Confidence 0.90 (Context7 + verified locally)**
> When using `opentelemetry-rust` 0.27 with `tonic` 0.12, …
```

This makes stale entries visible during `/update-kbs`.

## Related

- `/create-kb` — when no KB exists yet for the technology
- `/update-kbs` — refresh all KBs against latest docs (uses dated entries to find drift)
- `.claude/rules/kb-enrichment.md` — the policy that requires this skill be called after every web search
