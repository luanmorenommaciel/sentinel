# Weekly Sync Up | Crew B: Sentinel

| Field | Value |
|-------|-------|
| **Title** | Weekly Sync Up — Crew B: Sentinel |
| **Date** | June 9, 2026 (Tuesday), evening GMT-3 |
| **Project** | Sentinel — autonomous AI-agent-based observability and data-pipeline anomaly-detection platform |
| **Source** | Verbatim transcript export (auto-transcribed; heavy PT/ES code-switching — some speaker attributions inferred) |
| **Duration** | ~50 minutes (estimated) |

## Participants

| Name | Role |
|------|------|
| **Luan Moreno** | Crew leader / facilitator — owns product vision; drove the market/agentic-future discussion |
| **Vinícius Peres** | Engineer (Generator pod) — Python generator; explained the spec→contract→generator decoupling approach |
| **Caio Reis** | Engineer (Generator pod) — built a Go generator from Vinícius's design, with an agent-suggested data-visualization UI |
| **Victor Urquiola** | Engineer (Collector pod) — Rust collector; updated the architecture diagram and contract proposal |
| **Alex Botelho** | Engineer (Collector pod) — built data contracts (JSON + YAML), DDL schema, and a Python collector → ClickHouse with Docker + docs |
| **Adilson** | Infrastructure specialist / SRE — testing ClickHouse on Kubernetes; raised ML-model observability idea |
| **Lucas Tancredi** | Engineer (Infra / data modeling) |
| **Rafael Rodrigues** | Engineer — author of the ontology-layer architecture Luan referenced (to present later) |
| **Ruan Pomponet** | Engineer (Collector pod) |

---

## Executive Summary

A lighter status week — several members traveled over the long holiday, so the **data generator status was largely unchanged** from last sync. The substantive progress: **Caio built a second generator in Go** from Vinícius's Python design, adding an agent-suggested **UI that visualizes each generated OTel event** (trace ID, service, operations, full JSON). Vinícius explained the key insight behind running the same generator in multiple languages: because coding agents over-couple to the chosen technology, the team now **generates a tech-agnostic contract/spec first, then drives each language's generator from that shared spec** so all implementations end up with identical parameters. On the collector side, **Victor (Rust)** refreshed the architecture diagram and contract proposal but hasn't deeply tested output, while **Alex** independently stood up data contracts (JSON + YAML), a DDL schema, and a working **Python collector writing into ClickHouse** via Docker, with step-by-step docs. The agreed near-term plan: each pod spends **1–2 hours this week (deadline Friday)** to finish and clean up its piece, then the three are unified ("fishbone" merge) **into `master` next week**, tagged as a `0.0.x` baseline — the point where shared repo rules (PR approvals, pre-commit checks, CLAUDE.md/context conventions, worktrees) kick in and "nobody writes a line of code by hand" anymore. The back half of the meeting was Luan's extended vision/market briefing: agentic vs. deterministic pipelines, the "Dark Factory" autonomous-agent-fleet goal, context engineering ("less is more"), the SDD slash-command workflow, and a sobering AI-driven labor-market forecast through 2030.

---

## Decisions

| # | Decision | Decided By | Context |
|---|----------|------------|---------|
| D1 | **Generate a tech-agnostic contract/spec first, then drive each language's generator from it** | Vinícius + team | Coding agents over-couple to the chosen tech and are hard to decouple. Generating the generic contract first, then starting each agent from that spec, keeps implementations agnostic and forces the same parameters across Python/Go/Rust. |
| D2 | **Keep all three languages (Python, Go, Rust) for now; consolidate later** | Luan | Put everything in `master` organized and clean first; a single-language decision can come afterward. |
| D3 | **Generators write example output files into a repo folder as the handoff** | Luan | Generated example files live in a folder; the collector consumes them, confirms the contract, and writes natively. The output structure *is* the contract that Lucas/Adilson then model against. |
| D4 | **Unify the three components into `master` next week ("fishbone" merge), then tag a `0.0.x` baseline** | Luan + team | Once the three are mature and independent, open them up and merge to `master`. The baseline tag is the moment shared repo governance begins. |
| D5 | **This week's goal: each member spends 1–2 hours to finish + clean up their piece by Friday** | Luan | Today is Tuesday; close it out by Friday so the raw layer can feed Adilson/Lucas for data modeling and work can move to `master`. |
| D6 | **Repo governance (PR rules, approvals, pre-commit, CLAUDE.md/context conventions) will be set up by the whole team together** | Luan (answering Victor) | Deliberately not owned by one person — everyone configures it jointly to learn the process; revisited over time. |
| D7 | **Adilson to deliver a 1-hour ClickHouse deep-dive session over the next two weeks** | Luan + Adilson | ClickHouse is now mature/efficient; few people use it yet. Luan to open a calendar slot; ties into the ClickHouse MVP program and a possible São Paulo workshop. |
| D8 | **Rafael to present the ontology-layer architecture in a future session** | Luan | Rafa's ontology design (used in Luan's client project) is considered highly valuable to bring to the crew. |

---

## Action Items

| # | Action | Owner | Deadline | Priority |
|---|--------|-------|----------|----------|
| A1 | **Finish + clean up the Python generator** and prepare for the `master` merge | Vinícius | This week (by Fri Jun 12) | High |
| A2 | **Open a proper, replicable PR for the Go generator** (so others can run it locally); extend generation beyond GCP toward Azure/AWS | Caio | This week | High |
| A3 | **Write the collector's output JSON to the repo** so Lucas/Adilson can see the structure and model against it; then explain the under-the-hood Rust behavior next week | Victor | This week / next sync | High |
| A4 | **Polish the Python collector + contracts/DDL, organize docs**, and (optionally) push the Docker setup to `master` for everyone to pull and run locally | Alex | This week | High |
| A5 | **Restructure infra/data-modeling work** around the generators' real output; coordinate directly with Victor on the emitted data shape | Adilson, Lucas | This week | High |
| A6 | **Coordinate the "fishbone" unification** of the three components and the merge into `master` (mini sync among pods, comment on the board) | Generator + Collector pods (jointly) | Next week | Critical |
| A7 | **Schedule the ClickHouse deep-dive session** (open the calendar slot) | Luan | Next 1–2 weeks | Medium |
| A8 | **Stress-test ClickHouse ingestion** (memory/consumption) once real data is flowing and report back | Adilson | After merge | Medium |
| A9 | **Set up shared repo governance together** (branch protection, PR approval rules, pre-commit/quality checks, CLAUDE.md + context conventions, worktree pattern) | Whole team | After baseline tag | High |

---

## Open Questions

| # | Question | Blocker? | Follow-up |
|---|----------|----------|-----------|
| Q1 | **Should the generators also emit telemetry for Azure/AWS, not just GCP?** | No — phased | Caio raised it as a next step; one cloud at a time per the prior sync (GCP first) |
| Q2 | **Can the platform also generate OTel for ML-model observability?** (Adilson's FIAP adaptive-offer-experimentation project — champion-model evaluation) | No — exploratory | Luan: "probably yes"; needs the specific mechanic defined before deciding/automating |
| Q3 | **What exactly is the collector's output contract that infra will model against?** | Yes — blocks A5 | Victor to write the output JSON to the repo; Lucas/Adilson then design the ClickHouse model |
| Q4 | **How should the three components be unified — merge all to `master` then organize, or organize first then merge?** | No — design-time | Either works ("it depends"); decided as the components mature, then "fishbone" them together |
| Q5 | **What shared repo rules (approval count, pre-commit, context/CLAUDE.md updates) will the team adopt?** | No — deferred | To be configured jointly after the baseline tag, in the "second phase" of structuring |

---

## Key Insights

- **Spec/contract first defeats the agent's tech-coupling.** The team discovered that coding agents bake the target technology deep into their output, making cross-language parity hard. The fix: generate a generic, tech-agnostic contract/spec, then start each language's agent *from that spec*. This is what let Caio reproduce Vinícius's Python generator in Go while landing on the same parameters — and is the same swappability principle as the contracts-first design from the prior sync.

- **The agent suggests its own tooling.** Caio noted the agent *proactively* proposed building a visualization UI for the generated data (click to generate more, inspect each event's trace ID / service / operations / full JSON) — something not in the original ask. Useful later as a way to *compare* generated vs. real data, even though the actual pipeline will have the agent read the generated files rather than a human use the UI.

- **Rust impresses on efficiency.** The collector work in Rust drew repeated praise — very low memory consumption under stress tests, so "you can run a ton on the same machine without blowing it up." Aligns with GCP familiarity (logs, Cloud Function calls all map cleanly).

- **A baseline tag is the real starting line.** Luan framed the upcoming `master` merge + `0.0.x` tag as the moment the *interesting* work begins: shared repo, shared rules, multi-person agentic collaboration. "From now on nobody writes a line of code" by hand — everything becomes commands/agents. He flagged this as a first for him too (he's only ever done agentic repos with one other person; 4–6 people is a new organizational challenge).

- **Agentic, not deterministic.** Luan's worked example: an engineer spent a week building a *deterministic* code → Databricks-SQL translator; Luan threw it out in favor of an *agentic* chain — parse → translate to DBSQL (via KB + MCPs) → validate → execute/verify via ClickHouse + CLI → map entities via an ontology KB → write into Lake Flow — all triggered by a single slash command. The point: delegate the intelligence and decisions to the agent fleet, not to hand-written control flow.

- **"Dark Factory" is the end state.** The final stage is a fully autonomous fleet that runs continuously, makes and approves its own decisions, and only surfaces a control panel to the human. The team's job converges toward defining objectives and "selling the product," with agents doing the building.

- **Context engineering: "less is more."** Echoing Boris (Claude Code's creator), Luan argued modern models are smart enough that over-stuffing context hurts — give autonomy, tools, and an objective, and let the model discover the rest. The hard, "magical" part is *which* context to hand the agent for a given task (his example: a 3.7M-line codebase where the agent must read only what's relevant). This is the core craft of the "Dark Factory."

- **SDD slash-command workflow is the orchestration layer.** Luan demoed his setup: commands (`setup`, `define`, `design`, an `auto`/`alto` command that runs the whole pipeline with human-in-the-loop gates, `ship`, etc.), each wrapping subagents and shell scripts. He spent his first month building these commands to translate 36 files; now a single `/auto` pointed at a target does the whole job. "Context engineering + LLM engineering" — command wraps prompt + context + tools.

- **A stark labor-market forecast (Luan's AI-assisted research).** Cited figures: 3.8% unemployment reading (April 2026, highest since the pandemic), ~52k jobs lost, entry-level tech roles down ~67% ("juniors are cooked"), teams shifting from senior+junior to **senior+assistant**. Predicted salary convergence and disruption 2026–2030; **specialists who understand both traditional and agentic systems win big**. Consensus in the room: people here — traditional-systems background *plus* agentic/AI knowledge — are well positioned.

- **PM ↔ engineer roles are converging.** Referencing the Anthropic interview with Kate and Boris (1 year of Claude Code), Luan noted the predicted merge of product and engineering into a single role ("SPM" — increasingly technical PMs), and that the crew is approaching it from the engineering side.

---

## Data Engineering Context

### Component Status (this week)

| Component | Owner(s) | Language | Status |
|-----------|----------|----------|--------|
| **Generator** | Vinícius | Python | Unchanged from last week (holiday); working prototype |
| **Generator** | Caio | Go | New — built from Vinícius's design via shared spec; agent-suggested visualization UI; PR + multi-cloud next |
| **Collector** | Victor | Rust | Architecture diagram + contract proposal refreshed; runs but not deeply tested; needs to emit output JSON |
| **Collector** | Alex | Python | Working collector → ClickHouse (as `sentinel` schema); data contracts in JSON + YAML; DDL schema; Docker + docs |
| **Infra / data model** | Adilson, Lucas | — | ClickHouse validated on Kubernetes; awaiting real generated data to model against |

> **Languages in play:** Python, Go, and Rust — all kept for now (D2), unified into `master` next week, single-language consolidation deferred.

### Spec → Contract → Generator Flow (this sync's refinement)

```
shared tech-agnostic contract/spec
        │  (drives each agent independently)
        ├──► Python generator  ─┐
        ├──► Go generator      ─┤ identical parameters
        └──► (others)          ─┘
                │  emit example output files → repo folder
                ▼
        Collector (Rust / Python) confirms contract, writes natively → ClickHouse
                ▼
        Lucas / Adilson model the raw layer from the observed output structure
```

### ClickHouse Notes

- Now considered **mature and highly efficient** — low memory footprint, validated on Kubernetes; no crashes in testing.
- Historical caveat recalled: past crashes were **storage/history-related (Kafka backlog)**, not ClickHouse itself ("only fell over due to disk space").
- Ecosystem momentum: **ClickHouse MVP program** (being brought to Brazil, telemetry-aligned); two strong Portuguese-language ClickHouse tutorial channels noted as references for Adilson's upcoming session; possible São Paulo workshop.

### Reference: Luan's Client Ontology/RAG Project (cited as the north star)

- Indexed a **3 TB SQL Server** base into a knowledge base; **Rafael's ontology layer** sits on top.
- Cost ~**$15k** in Claude credits for one indexing session; **37 GB** RAG base exposed to agents via **MCP**.
- Goal: capture a 20-year veteran's tacit knowledge so any agent can answer "what does this file/job/table do, how does it relate, when did it fail?" — sourcing truth from the data, not the person.
- Next: index a **30 TB SFTP** source (est. $30–40k).
- Uses **multiple LLMs by job stage** (Kimi for part, Claude for part); testing **Fable 5** (~2× the cost of Opus 4.8) with extra budget.

---

## Logistics / Process Notes

- Light week — multiple members (Vinícius, Adilson, others) traveled over the long holiday, so progress was partial by design.
- **New models:** Fable 5 is now visible in the desktop app; flagged as ~2× the cost of Opus 4.8 ("pick your battles").
- Cadence: **finish individual pieces this week (Tue → Fri)**, then a **dedicated session next week** to sit everyone together and merge to `master`.
- After the baseline tag, the team enters a "second phase" of **structuring**: repo governance, quality-check agents/routines, worktrees for parallel work, knowledge bases, and the agentic build-out toward the "Dark Factory."
- Upcoming sessions queued: **Adilson on ClickHouse** (1 hr) and **Rafael on the ontology layer**.
