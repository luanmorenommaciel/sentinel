# Crew B Glossary

> Last updated: 2026-06-01

Sentinel uses program-specific terminology that doesn't always map cleanly to industry conventions. This glossary keeps everyone (and every agent) on the same page.

## Roles & people

| Term | Meaning |
|---|---|
| **Commander** | Program lead — Luan Moreno. Owns vision, opens architecture Issues, merges to main. Tier-1 in the Formation Tree. |
| **Crew** | A team of 8 Astronautas building one product. Sentinel is Crew B. Sibling crews: A (Apex), C (Oteru), D (AgentSpec). |
| **Astronaut(a)** | A crew member. (Portuguese: *astronauta*. Same word, used interchangeably.) |
| **Captain** | A *hat*, not a separate role. The Astronaut wearing it that sprint plans the backlog, triages PRs Wed/Fri, runs a 15-min weekly 1:1 with the Commander, pre-tags `good-first-issue`, and writes the cohort status update. Still ships code (60–70% IC, 30–40% leadership). Hat rotates each sprint. |
| **Pod** | The unit of work within a Crew. 2 Astronautas per Pod, owns one feature end-to-end. Crew B has 4 Pods. |
| **Pod 2 (Collector)** | Where Victor is. Alex Botelho · Victor Urquiola · Ruan Pomponet. Owns the OTel Collector (the Generator→ClickHouse middle layer). |

## Components & architecture

| Term | Meaning |
|---|---|
| **OTel Collector** | The Generator→ClickHouse middle component owned by Pod 2. Receives OTLP gRPC on `:4317`, validates contracts, converts, exports. **Do not call it "Hotel"** — that's a Portuguese-pronunciation artifact from the AI transcript of Sync 02 ("OTel" sounds like *ô-tél* → "hotel"). The component's real name is the OTel Collector. |
| **Generator (Hotel Gen — also pronounced *ô-tél*)** | The Python/Go program owned by Pod 1 that emits synthetic OTLP. Same naming caveat applies — "Hotel Gen" in the transcripts is "OTel Gen." Use the canonical name. |
| **ClickStack** | The ClickHouse-based storage tier. Encompasses ClickHouse plus the schema, ingestion config, retention policy. Owned (initially) by Pod 3 / infrastructure. |
| **Watcher** | A detection feature (one signal class). Six Watchers: Arrival (W01), Parse (W02), Volume (W03), Schema (W04), Latency (W05), Storage (W06). Each emits anomaly events with contracts. |
| **Watcher Crew** | The Sentinel concept of a CrewAI multi-agent group attached to a Watcher signal class. Not to be confused with Crew B (the people). |
| **3-tier cascade** | Detection logic per Watcher: Tier 1 statistical (z-scores, rolling window) → Tier 2 pattern (signature library) → Tier 3 LLM (Haiku→Sonnet→Opus). Cheapest tier that resolves wins. |
| **Blast radius** | The scope of a remediation action. T0 = reversible (replay a partition), T1 = bounded (skip a record), T2 = destructive (rewrite a Delta table — never auto). ADR-001 owes the canonical definition. |
| **Baseline** | The "what's normal" reference each Watcher compares against. Rolling 7-day window? Pre-trained model? OTel stream from Oteru? ADR-002 owes the answer. |

## Process

| Term | Meaning |
|---|---|
| **ADR** | Architecture Decision Record. Markdown file at `docs/adr/NNNN-<title>.md`, version-controlled, Captain + Commander reviewed. Status: Proposed → Accepted / Rejected / Superseded. |
| **Sprint 1 ADRs** | The three foundational ADRs assigned in `bem-vindos.md`: ADR-001 (blast radius), ADR-002 (baseline), ADR-003 (primary user). All owed by end of Sprint 1. |
| **good-first-issue** | The sacred tag for backlog items suitable as an Astronaut's first PR of the sprint. Captain pre-tags 5–10 per sprint. Closed by PR, not by hand. |
| **Weekly Sync** | Tuesday, Zoom, ~60 minutes. Pod assignments confirmed, first PRs reviewed live, ADRs progressed. |
| **The 7 CI gates** | Required green-light checks before human review: ruff · mypy --strict · pytest >80% · bandit + safety · markdownlint · CodeRabbit · Docker build. CI fail = no human review. |
| **The Contract** (capital C) | Every commit on `sentinel` declares its contributors via mandatory `Co-Authored-By:` trailers — human, LLM model, and bot (CodeRabbit `Reviewed-By:`). Visible in `git log --author` forever. |
| **Tool freedom** | The Astronaut picks any agentic coding tool (Claude Code, Cursor, Codex CLI, Aider, Zed AI, Kimi K2, Cline, Windsurf, or propose another). The non-negotiable is *attribution*. |
| **Lego principle** | Every component declares input/output contracts (Pydantic in Python, Protobuf in Go/Rust). Components are swappable — change what's inside the boundary; the contract holds. |

## Process artifacts

| Artifact | Where it lives | Source of truth for |
|---|---|---|
| **GitHub Projects** | Built into `sentinel` repo | The Kanban — sprint backlog, in-progress, in-review, done |
| **GitHub Issues** | `sentinel` repo | Every work item — Bug / Feature / Spike. Tagged + linked to ADR. Closed by PR. |
| **`docs/adr/`** | `sentinel` repo | Markdown ADRs. Reviewed by Captain + Commander. |
| **Discord `#crew-b`** | External | Async chat. *Not* where decisions that matter in 6 months live. |
| **WhatsApp** | External | Urgent sync only. *Not* documentation. |
| **`.claude/`** | `sentinel` repo (this PR) | The Claude Code environment. Skills, agents, KBs, internal docs. |

## Anti-glossary (terms we explicitly don't use)

- ❌ **"Hotel"** — transcription artifact for "OTel" (Portuguese pronunciation). The component is the OTel Collector.
- ❌ **"Spark History"** — the cautionary tale from Sync 02 (a prior crew burned 2 weeks building the wrong generator). Mentioned only as a lesson.
- ❌ **"Self-healing"** without qualifying the blast radius — a big word with no agreed meaning until ADR-001 ships.
- ❌ **"Real-time"** without specifying ingestion vs. analysis. Sync 02 was explicit: ingestion is real-time, analysis isn't (yet).
- ❌ **"AI" as a hand-wave** — agents are specific (the 3-tier LLM cascade, the Watcher CrewAI groups). "AI somewhere" isn't a design.

## See also

- `bem-vindos.md` (in `victor_docs/`) — the Commander's intro with the original framing of these terms
- Sync 01 deck (`crew-b-sync-01.pdf`) — formal definitions for Captain, Pod, Astronaut
- Sync 02 transcript (`Weekly Sync Up _ Crew B_ Sentinel_transcript-26-05.txt`) — where Hotel/OTel and Lego/contracts come from
- `.claude/CLAUDE.md` — current project context with cross-links
