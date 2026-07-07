---
name: ingest-doc
description: Process a document (PDF, slide deck, transcript, image) into structured knowledge — detecting scanned PDFs, applying OCR when necessary, extracting text, preserving metadata, summarizing, and routing the result into the KB. Use whenever a new piece of project documentation needs to enter the knowledge system.
---

# /ingest-doc

The canonical pipeline for taking *anything* — a meeting transcript, a slide deck PDF, a research paper, an image of a whiteboard, a Zoom recording's auto-summary — and turning it into KB-ready structured knowledge.

Built for Sentinel's specific reality: the project's docs include scanned PDFs (where `pdftotext` returns 21 bytes for a 21-page deck), image-only exports, and AI-transcribed meeting notes that can carry phonetic artifacts (see [[transcript-artifact-validation]]).

## Usage

```text
/ingest-doc <path> [--kind <kind>] [--target-kb <kb-path>]
```

- `<path>` — local file path (PDF / TXT / MD / PNG / JPG)
- `--kind` — one of: `spec`, `slide-deck`, `transcript`, `summary`, `research`, `whiteboard`. Auto-detected if omitted.
- `--target-kb` — KB path to write findings into (e.g., `kb/process/crew-b-wow/`). If omitted, the skill proposes a path.

## What it does

1. **Detect document type and text-extractability** — see [decision tree below](#decision-tree-text-vs-image).
2. **Extract text** using the right tool:
   - Text-extractable PDF → `pdftotext` (fast, free)
   - Image-only PDF → Claude vision Read (no install, no OCR engine needed)
   - Image file → Claude vision Read
   - Transcript (TXT/MD) → direct read
3. **Preserve metadata** — title, page count, creator, date, language, source URL (if external).
4. **Detect transcription artifacts** — flag suspicious patterns (e.g., parenthetical nicknames that may be phonetic mishearings — `OTel ("Hotel")`). User confirms before adopting.
5. **Structure the content** — depending on `--kind`:
   - `spec` → mission, architecture, watchers, stack, roadmap
   - `slide-deck` → act-by-act outline, key decisions, calls to action
   - `transcript` → participants, decisions, action items, open questions, key insights
   - `summary` → same as transcript but lighter (the meeting already pre-structured)
   - `research` → claims, citations, applicability
   - `whiteboard` → diagram description + extracted text
6. **Summarize** at three depths: TL;DR (2 sentences), executive (5 bullets), full (Markdown-structured).
7. **Route to the KB** — writes to the chosen `--target-kb` path with a dated entry, source link, and confidence score.
8. **Cross-link** — adds backlinks from related KBs to the new entry.

## Decision tree: text vs. image

```text
                ┌──────────────────────────────────────┐
                │  pdfinfo <file> → Pages count        │
                │  pdftotext <file> - | wc -c          │
                └──────────────────────────────────────┘
                                  │
                                  ▼
                ┌──────────────────────────────────────┐
                │  text bytes / page count > 100?      │
                └──────────────────────────────────────┘
                       │ YES                  │ NO
                       ▼                      ▼
            ┌──────────────────┐    ┌──────────────────────────┐
            │  pdftotext path  │    │  Image-only path:        │
            │  (free, fast)    │    │  Claude vision Read      │
            └──────────────────┘    │  (no install, no OCR)    │
                                    └──────────────────────────┘
                                                  │
                                                  ▼
                                    ┌──────────────────────────┐
                                    │  >50 pages?              │
                                    └──────────────────────────┘
                                          │ YES        │ NO
                                          ▼            ▼
                              ┌──────────────────┐  ┌─────────────┐
                              │  Suggest         │  │  Vision     │
                              │  tesseract       │  │  Read       │
                              │  install for     │  │  (chunks    │
                              │  batch (opt-in)  │  │  of 20 pages)│
                              └──────────────────┘  └─────────────┘
```

See `.claude/docs/OCR_STRATEGY.md` for the full rationale.

## Output schema (proposed KB entry)

```markdown
> **Ingested 2026-06-01 · Source: <path> · Confidence 0.85 · Kind: <kind>**
>
> **TL;DR:** <2 sentences>
>
> **Decisions:** <bulleted>
> **Action items:** <bulleted with owners>
> **Open questions:** <bulleted>
> **Key insights:** <bulleted>
>
> **Transcription artifacts flagged:** <list, or "none">
>
> **Cross-references:** <links to related KBs / ADRs>
```

## Conventions

- **Never adopt a parenthetical nickname as canonical** without explicit confirmation — see [[transcript-artifact-validation]] (Hotel→OTel).
- **Preserve original document** in `victor_docs/` (private) — the ingested version is a derivative.
- **Date the entry.** Stale ingests are visible in `/update-kbs`.
- **Confidence ≤ 0.80** triggers a follow-up review item.

## Related

- `meeting-analyst` agent — the worker for transcript-shaped docs
- `code-documenter` agent — the worker for code-shaped docs
- `kb-architect` agent — used when the ingested content seeds a new KB
- `.claude/docs/OCR_STRATEGY.md` — when to use which extraction path
- `.claude/docs/INGESTION_WORKFLOW.md` — broader doc lifecycle (incoming → triaged → ingested → archived)
