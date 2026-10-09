# `.claude/` Roadmap

> **Looking for the product roadmap?** It is
> [`docs/research/data-observability-competitive-landscape.md`](../../docs/research/data-observability-competitive-landscape.md)
> §6 — the ranked V2 shortlist for `services/flow-ui`, with what has shipped tracked in
> [`services/flow-ui/STATUS.md`](../../services/flow-ui/STATUS.md). **This file is not that.**
>
> Evolution plan for Sentinel's Claude Code knowledge system.
> Last updated: 2026-08-18

The `.claude/` environment isn't shipped once and forgotten — it grows as the project does. This roadmap maps the four growth phases to the Sentinel program's 20-week DataShip Mission 2026 timeline.

## Phase 0 — Bootstrap (now)

**Status:** ✅ Complete (2026-06-01, this PR)

**Delivered:**
- `.claude/CLAUDE.md` — project context with full lookup tables
- 8 skills at bootstrap: `create-agent`, `create-kb`, `create-skill`, `enrich-kb`, `readme-maker`, `update-kbs`, `ingest-doc`, `adr` *(now 10 — `arch-review` and `day-1-rust` added since)*
- 12 specialized agents across 8 categories *(now 16)*
- 10 seed KBs covering OTel, ClickHouse, Rust, Go, GCP telemetry, contracts, anomaly detection, agentic patterns, Crew B WoW *(now 11 — `communication/architecture-diagramming` added)*
- 4 internal docs: `OCR_STRATEGY.md`, `INGESTION_WORKFLOW.md`, `ROADMAP.md` (this file), `CREW_B_GLOSSARY.md`
- Path-scoped rules for KB enrichment and attribution

**Done is not done if:**
- An agent doesn't have a "Use PROACTIVELY when …" trigger sentence
- A KB doesn't have at least one cross-reference from a sibling KB
- A skill doesn't have a "Related" section pointing to the agents/KBs it consumes

## Phase 1 — Sprint 1 alignment (Weeks 1–2)

**Goal:** the `.claude/` env directly supports the three Sprint 1 ADRs and Pod 2's Collector bake-off.

**Backlog:**
- **ADR-001 / ADR-002 / ADR-003 in `docs/adr/`** — opened by the Commander, drafted by Crew B. The `/adr` skill produces the scaffold; `kb-architect` validates references.
- ~~**Bake-off harness KB** at `kb/process/bakeoff/`~~ — **dropped.** The Rust-vs-Go comparison was settled in-repo (Rust selected, PR #28, merged 2026-08-12) without a standalone harness KB.
- **First weekly sync ingest** via `/ingest-doc` of the next Tuesday transcript → `kb/process/crew-b-wow/syncs/`.
- **Captain's status template** — possibly a `/status` skill if the Captain (whoever wears the hat) wants to automate it.

**Exit criteria:** Every artifact a Pod 2 PR references lives somewhere in `.claude/` (an agent, a KB entry, a doc) or in `docs/adr/` (the canonical decision record).

## Phase 2 — Watcher fleet (Weeks 3–8)

**Goal:** as each of the 6 Watchers comes online, the env grows a Watcher-specific agent + KB pair.

**Per Watcher (Arrival → Parse → Schema → Volume → Latency → Storage):**
- `kb/detection/watchers/<name>/` — signals, thresholds, false-positive patterns, contracts with upstream/downstream
- `.claude/agents/detection/<name>-watcher.md` — domain expert that consumes the KB and proposes detection rules

**Backlog by week:**
| Week | Watcher (Sprint goal per spec) | New artifacts |
|---|---|---|
| 3 | Arrival end-to-end (v0.1.0 alpha goal) | `kb/detection/watchers/arrival/`, `agents/detection/arrival-watcher.md` |
| 4 | Parse | `kb/detection/watchers/parse/`, `agents/detection/parse-watcher.md` |
| 5–6 | Volume + Schema | 2 KBs + 2 agents |
| 7 | Latency | 1 KB + 1 agent |
| 8 | Storage | 1 KB + 1 agent |

**Exit criteria:** Six Watcher KBs + six Watcher agents. Each agent has been dispatched at least once on a real PR.

## Phase 3 — LLM cascade + policy engine (Weeks 9–14)

**Goal:** the 3-tier detection cascade (Statistical → Pattern → LLM) and the policy/blast-radius engine each get a KB + agent.

**Backlog:**
- `kb/detection/llm-cascade/` — Haiku→Sonnet→Opus routing, cost gates, confidence thresholds
- `agents/detection/llm-router-engineer.md` — designs the cascade for a given Watcher
- `kb/detection/policy-engine/` — blast-radius gating, T0/T1/T2 classification (from Phase 0 discovery)
- `agents/detection/policy-engineer.md`
- `kb/detection/audit-log/` — attestation schema, replay format
- `agents/process/runbook-author.md` — turns remediation runs into KB entries (the feedback loop)

**Exit criteria:** Every box on the 8-stage architecture diagram has a KB.

## Phase 4 — Production + open-source (Weeks 15–20)

**Goal:** the env stops growing and starts curating. Becomes the open-source docs surface.

**Backlog:**
- **Public `.claude/` audit** — every agent / KB / skill reviewed for clarity, accuracy, freshness. `/update-kbs` runs end-to-end.
- **README.md generation** for the repo root via `/readme-maker` — shows the world what we built.
- **Contribution guide** — `.claude/docs/CONTRIBUTING.md` derived from Crew B WoW, but written for outside contributors.
- **`agents/process/release-notes-author.md`** — turns merged PRs into release notes (a real Crew B "receipt" for the cohort).
- **Drop dead agents** — anything dispatched fewer than 3 times across the program is a candidate for removal. Keep the env lean.

**Exit criteria:** A first-time external contributor can clone the repo, read `.claude/CLAUDE.md`, dispatch the right agent for their question, and open a useful PR — without ever talking to Crew B.

## Cross-cutting maintenance

- **Monthly `/update-kbs`** — Captain owns the cadence.
- **Per-sprint review** — at Sync 02, the Captain confirms which Phase-N items moved from "pending" to "done" in this roadmap.
- **Drift audit** — if an ADR's referenced KB diverges from the ADR's claims, the ADR is amended (don't quietly mutate the KB).
- **Memory hygiene** — at user level, project memories about Sentinel get updated when the cross-section of the project changes (new pod, new architecture decision, new tool).

## Open questions

- **Does the env get pushed to upstream `luanmorenommaciel/sentinel`?** Default: yes (this PR proposes it). Alternative: keep `.claude/` gitignored as personal scaffolding. Decided by the Crew at Sync 03.
- **Does the env get shared with other Crews (A / C / D)?** Default: maybe — the skills and agents are 80% portable; the KBs are 50% portable. A sibling repo `dataship-mission-2026/.claude-common/` could host the portable bits if there's appetite.
- **Does the env become its own contribution to the open-source community?** Probably not until end of program — and only if the architecture has stabilized enough to be exemplary.

## See also

- `.claude/CLAUDE.md` — current state
- `kb/process/crew-b-wow/` — WoW that governs how artifacts land in `.claude/`
- `/update-kbs` — the freshness-keeping skill
- The Sentinel spec (`victor_docs/sentinel.pdf`) — the 20-week roadmap this `.claude/` roadmap is paced against
