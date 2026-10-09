# Document Ingestion Workflow

> Last reviewed: 2026-09-02 · unchanged since 2026-06-01 — describes a process, not repo state

## Why this exists

Sentinel's documentation arrives unsystematically — meeting transcripts dropped after Tuesday syncs, slide decks shared in Discord, research papers, screenshots of whiteboards. Without a workflow, important context rots in inboxes. With one, every meaningful artifact ends up where Claude Code can find it.

## The lifecycle

```text
┌─────────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
│  Incoming   │───▶│ Triaged  │───▶│ Ingested │───▶│  Archived  │
└─────────────┘    └──────────┘    └──────────┘    └────────────┘
   raw drop         decision         KB entry          searchable
   victor_docs/     point            .claude/kb/       reference
```

### Stage 1 — Incoming (`victor_docs/`)

Raw artifacts land here as-is. Slack downloads, transcript exports, scanned PDFs, photos of whiteboards. Nothing is processed; nothing is committed (the folder is gitignored).

**Owner:** whoever received the artifact.
**SLA:** triage within 7 days or it gets pruned.

### Stage 2 — Triaged

A human decides: *does this belong in the KB?* Three outcomes:

| Outcome | What happens |
|---|---|
| **Ingest** | Goes to Stage 3. |
| **Discard** | Delete from `victor_docs/` (the artifact wasn't important enough). |
| **Archive only** | Move to `victor_docs/_archive/` for personal reference but skip KB ingestion. |

Triage criteria:
- Will future sessions benefit? (Yes → ingest)
- Is it project-specific or generic? (Generic → maybe a KB, project-specific → maybe `kb/process/`)
- Is the source authoritative? (Commander notes > Crew sync notes > random web article)

### Stage 3 — Ingested

`/ingest-doc <path>` does the work:

1. Detects the document type and text-extractability (see [OCR_STRATEGY.md](OCR_STRATEGY.md))
2. Extracts text via the right path (`pdftotext`, vision Read, or direct)
3. Preserves metadata (title, date, source, language)
4. Detects AI-transcription artifacts (e.g., the OTel→Hotel mishearing) and flags them
5. Summarizes at three depths: TL;DR / executive / full
6. Routes the result into the right `.claude/kb/<category>/<topic>/` directory
7. Cross-links from related KBs

Each KB entry is timestamped and confidence-scored.

### Stage 4 — Archived

Original artifact stays in `victor_docs/` (or moves to `victor_docs/_archive/` if old). The KB entry is the live reference; the original is the audit trail. Both are private; only the KB entry is reachable to teammates via the repo (when `.claude/` is shared).

## Routing reference

| Source | Default KB target | Skill |
|---|---|---|
| Weekly sync transcript | `kb/process/crew-b-wow/syncs/<date>.md` | `/ingest-doc <file> --kind transcript` |
| Brainstorm summary | `kb/process/crew-b-wow/brainstorms/<date>.md` | `/ingest-doc <file> --kind summary` |
| Spec / slide deck | `kb/process/crew-b-wow/specs/<name>.md` | `/ingest-doc <file> --kind spec` |
| Research paper | `kb/patterns/<topic>/research/<paper>.md` | `/ingest-doc <file> --kind research` |
| Whiteboard photo | `kb/process/crew-b-wow/whiteboards/<date>-<topic>.md` | `/ingest-doc <file> --kind whiteboard` |
| External documentation | `kb/<tech-category>/<tech>/` (use `/create-kb` if absent) | `/enrich-kb <tech>` |

## Authoring an ADR from an ingest

If the ingested doc surfaces a decision-worthy question (e.g., a Sync transcript debates blast radius), the workflow extends:

```text
Ingest → KB entry → ADR draft → PR
```

The ADR draft is opened with `/adr <title>` and references the KB entry as evidence in its Context section.

## Anti-patterns

- **Don't ingest opinions.** A Slack reaction or a Discord one-liner isn't documentation. Wait for the structured version (sync notes, summary, written argument).
- **Don't ingest twice.** If a transcript and its summary cover the same ground, ingest the summary (denser, structured) and reference the transcript as backup.
- **Don't ingest raw video.** Video → transcript → summary → ingest. The KB shouldn't carry binary blobs.
- **Don't ingest stale.** If the artifact is >30 days old AND nothing has changed in the meantime, the decision is probably already captured elsewhere. Verify before adding.
- **Don't ingest without confidence.** Every KB entry has a confidence score; if you can't justify ≥0.75, the source isn't ready.

## Cadence

- **After each Tuesday sync:** Captain ingests the sync transcript within 48 hours.
- **Weekly:** anyone with new external docs (papers, blog posts) does `/enrich-kb` or `/create-kb`.
- **Monthly:** `/update-kbs` re-validates everything against upstream.

## See also

- `/ingest-doc` skill — the worker
- `/enrich-kb` skill — for finer-grained additions
- `/update-kbs` skill — for refresh cycles
- `OCR_STRATEGY.md` — extraction path routing
- `.claude/rules/kb-enrichment.md` — the policy that closes the loop after every web search
