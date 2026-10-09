# OCR & Document-Extraction Strategy

> Last reviewed: 2026-09-02 · unchanged since 2026-06-01 — describes a process, not repo state

## Why this doc exists

Sentinel's source documents arrive in three shapes — and each shape needs a different extraction path. Picking the wrong one wastes hours (OCR-ing a text PDF) or money (LLM-reading a 500-page Packt book). This doc is the routing logic.

## The reality

The first wave of `victor_docs/` revealed:

| File | Pages | `pdftotext` bytes | Diagnosis | Path |
|---|---|---|---|---|
| `sentinel.pdf` | 1 | 213 | Image-only (the spec is rendered as an image) | Vision Read |
| `crew-b-sync-01.pdf` | 21 | 21 | Image-only (slide deck) | Vision Read |
| `crew-b-sync-02.pdf` | 15 | 15 | Image-only (slide deck) | Vision Read |
| `output.pdf` | 3 | 3 | Image-only | Vision Read |
| `2026-05-25-brainstorming-sync-02.pdf` | 5 | 8,022 | Text-extractable (Markdown→PDF via Chrome headless) | `pdftotext` |
| `2026-05-26-weekly-sync-crew-b-sentinel.pdf` | 9 | 15,928 | Text-extractable | `pdftotext` |
| `book-agentic-architectural-patterns-multi-agent-systems.pdf` | 574 | 1,137,580 | Text-extractable (WeasyPrint output) | `pdftotext` (with chunking) |
| `phase 1.png`, `Sentinel-Spec-diagram.png` | — | — | Image | Vision Read |
| `Weekly Sync Up _ Crew B_ Sentinel_transcript-*.txt` | — | — | Text | Direct read |

**Rule:** `text bytes / page count > 100` → text PDF. Below → image PDF requiring vision Read or OCR.

## The three paths

### Path 1 — `pdftotext` (free, fast, mature)

```bash
pdfinfo input.pdf | grep Pages          # sanity check
pdftotext input.pdf -                   # extract to stdout
pdftotext -layout input.pdf -           # preserve column layout (slower)
```

**Use when:** `text bytes / page count > 100`.
**Cost:** Free. Local. Milliseconds.
**Limitations:** Loses figures, diagrams, slide-layout context.

### Path 2 — Claude vision `Read` tool (multimodal LLM)

```text
Read(file_path="/abs/path/to/scan.pdf", pages="1-10")
```

Claude Code's `Read` tool natively handles PDFs *and* images by rendering pages as images and feeding them to the multimodal model. No OCR engine required.

**Use when:**
- The PDF is image-only (scanned, screenshot-based, or designer-built)
- The document mixes text + diagrams and you need both interpreted together
- Document is ≤ ~20 pages (chunk larger docs with the `pages` parameter)

**Cost:** LLM tokens per page (call it ~$0.01–0.05/page on Sonnet, more on Opus).
**Limitations:** Doesn't scale to a 500-page book; expensive for repeated re-reads.
**Wins:** Zero install, handles diagrams perfectly, parses semi-structured slides correctly.

### Path 3 — `tesseract` + `pdf2image` (opt-in)

For batch jobs where vision Read is too expensive (e.g., the Packt book, archived training material, scanned client docs).

```bash
# One-time install (opt-in)
sudo apt-get install -y tesseract-ocr libtesseract-dev poppler-utils
pip install pdf2image pytesseract pillow

# Use
pdftoppm input.pdf out -png -r 300        # rasterize at 300 DPI
for f in out-*.png; do tesseract "$f" "${f%.png}" -l eng pdf; done
pdfunite out-*.pdf merged.pdf             # reassemble searchable PDF
```

**Use when:**
- Document is >50 pages AND image-only AND likely to be referenced repeatedly
- Vision Read cost would exceed ~$25 over the document's lifetime
- You need a searchable PDF artefact (not just extracted text)

**Cost:** Free at run-time after one-time install. Tens of seconds per page.
**Limitations:** OCR errors on stylized fonts (especially the spec's serif headlines), no semantic understanding.

### Path 4 — Direct read (TXT, MD)

```text
Read(file_path="/abs/path/to/transcript.txt")
```

Trivially handles `.txt`, `.md`, transcript dumps. No special handling.

## The router

The `/ingest-doc` skill encodes this logic. Quick reference:

```text
Is it .txt/.md?                 → Direct Read
Is it an image (.png/.jpg)?     → Vision Read
Is it a PDF?                    → pdfinfo + pdftotext probe
  text/page > 100?              → pdftotext
  text/page ≤ 100 and ≤20p?     → Vision Read
  text/page ≤ 100 and >20p?     → Suggest tesseract install for batch
```

## Special case — transcription artifacts

AI-generated meeting transcripts and summaries can preserve phonetic mishearings as if they were nicknames. The canonical Sentinel example: Luan speaks "OTel" in Portuguese (sounds like *ô-tél*) and the engine writes "hotel" — then the Granola summary preserved it as `OTel Collector ("Hotel")`, and a future reader took "Hotel" as a team nickname.

**Rule:** when ingesting any AI-generated transcript or summary, the `/ingest-doc` pipeline flags suspicious parenthetical nicknames and asks the user before adopting them.

See [[transcript-artifact-validation]] in personal memory for the full pattern.

## What's installed locally right now

- ✅ `pdftotext` (poppler-utils — `/usr/bin/pdftotext`)
- ✅ `pdfinfo` (`/usr/bin/pdfinfo`)
- ✅ Claude Code vision `Read` (multimodal)
- ❌ `tesseract` (not installed)
- ❌ `pdf2image` / `pytesseract` (not installed)

**Decision (Phase 1):** defer tesseract. Vision Read covers all current `victor_docs/` image-only PDFs. Document the install procedure here so the path is opt-in for whoever needs batch OCR.

## What lives where

| Document state | Path | Tracked? |
|---|---|---|
| Raw incoming | `victor_docs/` | No (gitignored — personal research) |
| KB-routed digest | `.claude/kb/<category>/<topic>/` | Yes (committed) |
| Searchable archive (if tesseract is run) | `victor_docs/_ocr/` | No (gitignored) |

## When to revisit this strategy

- If `tesseract`-equivalent quality becomes available as a lighter MCP server, switch.
- If Crew B starts ingesting >100 docs/month, install tesseract + automate.
- If the Packt book becomes a real reference (not just a one-time skim), tesseract it once into a searchable PDF.

## See also

- `/ingest-doc` — the skill that uses this routing
- `.claude/docs/INGESTION_WORKFLOW.md` — the broader doc lifecycle (incoming → triaged → ingested → archived)
- `.claude/skills/ingest-doc/SKILL.md` — the implementation detail
