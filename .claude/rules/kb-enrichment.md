# KB Enrichment Rule

> Knowledge discovered during development must flow back into the KB system.
> *Last updated: 2026-06-01*

## When to enrich

After completing any of these activities, check if the knowledge belongs in the KB:

| Activity | Example | KB Action |
|---|---|---|
| Solved a non-obvious problem | A `tonic` lifetime issue, a ClickHouse `INSERT` perf trick | Update the relevant KB `patterns/` or `quick-reference.md` |
| Researched a technology | Web search, MCP query, official docs deep-dive | Run `/enrich-kb <technology>` |
| Discovered a new pattern | A Watcher signal-correlation idiom, a contract migration approach | Add to relevant KB `patterns/` |
| Validated a production approach | Bake-off perf numbers, real GCP OTLP schema confirmed against synthetic | Update KB with the real-world metrics |
| Encountered a breaking change | OTel SDK 0.28 deprecates a builder; ClickHouse 25.x changes a default | Update `concepts/` or `quick-reference.md` |

## Decision flow

```text
Did I learn something non-obvious during this session?
  │
  ├─ YES → Is there an existing KB for this technology?
  │         ├─ YES → Update the relevant KB file (patterns/, concepts/, or quick-reference.md)
  │         └─ NO  → Is it general (applies across the project)?
  │                   ├─ YES → Suggest /create-kb <technology>
  │                   └─ NO  → Leave in project CLAUDE.md only
  │
  └─ NO → Nothing to do
```

## What belongs in KB vs. CLAUDE.md

| KB (general, reusable) | CLAUDE.md (project-specific live state) |
|------------------------|------------------------------|
| "tonic 0.12 requires Rust 1.75+" | "Our Collector pins rust-version = 1.75" |
| "ClickHouse Native protocol > HTTP for ingestion" | "We use clickhouse-rs 0.13 with feature 'time'" |
| "z-score with k=3 is the conventional outlier threshold" | "ADR-002 picks rolling 7-day window for baselines" |
| "OTLP `:4317` is the universal gRPC on-ramp across GCP/Azure/AWS" | "Pod 2 owns the OTel Collector" |

KB = the textbook. CLAUDE.md = the project's current state.

## Integration with `/sync-context`

When `/sync-context` runs (if added later), it should scan for KB gaps as a final step:

1. Scan the project's CLAUDE.md for technology references
2. Compare against existing KB entries
3. Flag any technology used in the project that doesn't have a KB entry
4. Suggest `/create-kb` for each gap

## Dating + confidence

Every enrichment entry is timestamped:

```markdown
> **Added 2026-06-01 · Confidence 0.90 (Context7 + verified locally on Rust 1.83.0)**
> When using `opentelemetry-rust` 0.27 with `tonic` 0.12, the `gen-tonic` feature must be enabled in `opentelemetry-proto` …
```

Stale entries get flagged during `/update-kbs`. Re-validate via MCP or local repro and re-date.

## Special case — transcription artifacts

When ingesting AI-generated meeting transcripts or summaries (Pod syncs, brainstorms), the `/ingest-doc` skill flags suspicious parenthetical nicknames (e.g., `OTel ("Hotel")`) and asks the user before adopting them. See [`.claude/docs/CREW_B_GLOSSARY.md`](../docs/CREW_B_GLOSSARY.md) for the project's anti-glossary.

## See also

- [`.claude/skills/enrich-kb/SKILL.md`](../skills/enrich-kb/SKILL.md) — the skill that does the enrichment
- [`.claude/skills/create-kb/SKILL.md`](../skills/create-kb/SKILL.md) — when no KB exists yet
- [`.claude/skills/update-kbs/SKILL.md`](../skills/update-kbs/SKILL.md) — the refresh cycle
- [`.claude/kb/README.md`](../kb/README.md) — KB index
