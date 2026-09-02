# Sentinel — Claude Code Project Context

> Last updated: 2026-09-02

## Mission

**Sentinel = autonomous observability + remediation for data pipelines.** Self-healing where safe, page where it matters. One mission: *no downstream user finds the bug before Sentinel does.*

Open-source. Built by **Crew B** of the DataShip Mission 2026 mentorship program led by **Luan Moreno** (Commander). Upstream repo: <https://github.com/luanmorenommaciel/sentinel>.

## Architecture (Phase 1)

```text
Generator ──▶ OTel Collector ──▶ ClickStack (ClickHouse)
              │
              └─ OTLP gRPC :4317
```

First cloud target: **GCP**. Python was ruled out for the Collector (perf). The Rust-vs-Go bake-off is **settled in practice: Rust was selected** and `services/collector-go/` was removed from the repo in PR #28 (merged 2026-08-12). ⚠️ [ADR-0004](../docs/adr/0004-collector-implementation-language.md) still reads `Proposed` and still frames the bake-off as open — the decision was taken by merge, not by ADR. Closing that record is a Pod 2 action item.

**Eight-stage spine (vendor-agnostic):**

```text
otel_core → rolling_stats → tiered_engine → cross_watcher → policy_engine → remediation → audit_log → feedback_loop
   SIGNAL       LEARN          DETECT          DETECT          DECIDE          ACT          ATTEST       LEARN
```

**6 Watcher Crews:** Arrival · Parse · Volume · Schema · Latency · Storage.
**3-tier detection cascade:** Statistical (z-scores) → Pattern (signature) → LLM (Haiku→Sonnet→Opus). *Cheapest tier wins. Opus only when Sonnet confidence is low AND blast radius is high.*

## What exists today

Three services and two data layers, all verified running:

| | | |
|---|---|---|
| `services/generator-python` | Pod 1 — OTLP generator | 178 pytest |
| `services/collector-rust` | Pod 2 — OTLP → `bronze.*` | 92 inline + 4 integration |
| `services/flow-ui` | the pipeline watching itself · `:8080` · read-only | 63 pytest |
| `bronze.*` | ADR-0007 · 4 live tables + 3 empty by contract | applied on ClickHouse boot |
| `silver.*` | ADR-0010 · 3 typed models + 6 read views | 60 SQL asserts |

**flow-ui** (merged in PR #31) has four boards over the collector's `/metrics` and a read-only
view of bronze: *Flow* (the path, expandable in place), *Health*, *Contract* (what would be
dropped under `strict`, and which producers violate), *Watchers* (rows/min per producer against
a band, where the band drawn **is** the alerting rule). Nothing in the pipeline depends on it.
It now reads `silver.service_health_1m` for per-producer latency and error rate — drawn on
each ORIGIN node as **declared → measured**, beside the latency `topology.yaml` claims — and
draws Silver itself as the fourth box on the Flow board, linked to Bronze by a **derivation,
not a pipe**: ADR-0010's materialized views fire inside ClickHouse on the same insert, so
there is no hop to draw. It still derives contract violations, volume bands and call edges
from Bronze: those MVs do not `POPULATE`, so moving them across would drop the history they
depend on ([#37](https://github.com/luanmorenommaciel/sentinel/issues/37)).
How it is built — stack, cadences, module map, six Mermaid diagrams — is
[`services/flow-ui/ARCHITECTURE.md`](../services/flow-ui/ARCHITECTURE.md).

**Silver is defined but not necessarily deployed**: the DDL runs on ClickHouse boot, so a
volume older than the merge will not have it, and the MVs do not `POPULATE` — they see new
inserts only.

## Current state (Pod 2 — `collector-rust`)

> Source of truth: [README §8](../README.md) + the contract docs below. This block is the quick orientation; don't let it drift.

- **Rust is the selected collector**; `services/collector-go/` was deleted in PR #28 (merged 2026-08-12). `services/collector-rust/` is the only ingestion path in the repo.
- **Collector-rust writes the bronze schema directly** into ClickHouse database `bronze` (`otel_logs / otel_traces / otel_metrics_gauge / otel_metrics_sum`, otel-collector-contrib v0.105.0 style). Both ingest paths verified: OTLP gRPC `:4317` and file/NDJSON (golden `baseline_seed42.jsonl` → 48 logs / 48 spans / 183 metrics).
- **Latest E2E snapshot (2026-08-04):** 233,100 signals in 4.5s (~51.4k signals/s), 0 rejected / 0 dropped / 0 export errors, avg ClickHouse export latency 32.3ms, 100% of flush attempts ≤80ms. A reproducible local snapshot — *not* a production SLO.
- **gRPC receive-boundary validation** is policy-gated via `contract.grpc_validation` (`off` / `warn` / `strict`, **default `warn`**). File mode uses `contract.strict` (all-or-nothing). Foreign OTLP legitimately lacks the 5 `sentinel.*` keys → `strict` would drop it, hence the `warn` default. Code: `src/grpc.rs` (`apply_validation`), `src/config.rs`.
- **Pod 1 → Pod 2 input contract:** `v1.0.0` **frozen**, at [`contracts/generator/v1/`](../contracts/generator/v1/).
- **Pod 2 → Pod 3 read contract:** **`v1.0.0.1`** — the bronze DDL is the contract (ADR-0007 supersedes ADR-0005). Agreed boundary; Pod 3 sign-off still pending. Doc: [`contracts/collector/v1/pod2-pod3-read-contract.md`](../contracts/collector/v1/pod2-pod3-read-contract.md).
- **ADR status:** 0004 (language) `Proposed` — stale, see above · ~~0005~~ superseded by 0007 · 0006 (optional-ID) `Proposed`, refined by 0007 · 0007 (bronze = canonical contract) `Proposed`, Pod 3 sign-off pending · 0008 (contracts registry by producing Pod) `Proposed`, in effect on `main`.
- **README Phase-1 realignment is landed** (PR #26, merged 2026-06-30; refined by #28). README §1/§2 follow the original proposal (`victor_docs/Sentinel-Spec-diagram.png`): **Phase 1 = telemetry foundation** (POD1 generate → POD2 ingest/transform → POD3 storage / data-modelling / consumption); **Watchers · Detection · CrewAI · Remediation = future phase**. Contract ② is drawn **after** ClickHouse (it *is* the CH schema). ⚠️ **Still not ratified — do not propagate:** the **Crew B layout below still lists B3 = Volume/Schema/Latency/Storage watchers**, which diverges from the README's POD3 = storage/read-layer framing. Realign this file only after Captain/Commander sign off on the Pod↔layer mapping. ClickHouse operational ownership stays unassigned.

## Crew B layout (you are here)

Crew B has 8 Astronautas in 4 Pods. The Pod is the unit of work — owns a feature end-to-end.

| Pod | Owns | Astronautas |
|---|---|---|
| B1 | Arrival + Parse (W01, W02) | TBD |
| B2 | **OTel Collector** (Hotel name was transcription artifact — use OTel Collector) | Alex Botelho · Victor Urquiola · Ruan Pomponet |
| B3 | Volume + Schema (W03, W04) / Latency + Storage (W05, W06) | TBD |
| B4 | Action Dispatcher | TBD |

Pods are confirmed at Sync 02 each sprint; the assignment above is from the latest sync.

## Directory layout

```text
sentinel/
├── docs/
│   ├── adr/                       # Architecture Decision Records (numbered, versioned)
│   └── research/                  # Companion research briefs (referenced by ADRs)
├── services/
│   ├── collector-rust/            # Rust collector — SELECTED implementation (Pod 2)
│   └── generator-python/          # Python data generator, otelgen CLI (Pod 1)
├── contracts/                     # contract registry, namespaced by producing Pod
│   ├── generator/v1/              #   Pod 1 → Pod 2 input contract
│   └── collector/v1/              #   Pod 2 → Pod 3 read contract (bronze)
├── infra/                         # ClickHouse bootstrap + Pod-3-owned bronze DDL (init.d/)
├── .claude/
│   ├── CLAUDE.md                  # This file
│   ├── agents/                    # Specialized subagents (16) + _schema.json + _template.md.example
│   ├── skills/                    # Slash commands (10) + _template.md.example
│   ├── kb/                        # Knowledge bases (11 seed KBs) + _templates/ + _index.yaml
│   ├── docs/                      # Internal standards (6 — OCR, ingestion, roadmap, glossary, Rust standards, agentic gitflow)
│   └── rules/                     # Path-scoped instruction files (1 — kb-enrichment)
└── README.md
```

## Agents (16 specialized)

| Category | Agents |
|---|---|
| Code Quality | code-reviewer · code-documenter · test-generator · shell-script-specialist |
| Communication | adaptive-explainer · meeting-analyst · architecture-visualization-reviewer |
| Workflow | the-planner |
| Telemetry | otel-collector-specialist |
| Storage | clickhouse-engineer |
| Detection | anomaly-detection-engineer |
| Languages | rust-specialist · python-developer |
| Cloud | gcp-engineer |
| Exploration | kb-architect · codebase-explorer |

Each agent has its own `.md` under `.claude/agents/<category>/<name>.md`. All agents have a `Use PROACTIVELY when …` trigger line so auto-invocation fires consistently. The frontmatter schema is documented in [`.claude/agents/_schema.json`](agents/_schema.json) (recommended-not-required at bootstrap).

## Skills (10 slash commands)

| Skill | Purpose |
|---|---|
| `/arch-review` | Audit how a repo communicates its architecture (READMEs, ADRs, diagrams, contracts) against the 7 architecture-communication principles |
| `/create-agent` | Author a new specialized subagent from the standard template |
| `/create-kb` | Create a new knowledge-base section |
| `/create-skill` | Create a new slash command from the standard skill template |
| `/enrich-kb` | Write web search / MCP findings back into the KB |
| `/readme-maker` | Generate comprehensive README.md from a codebase scan |
| `/update-kbs` | Refresh existing KBs with latest documentation |
| `/ingest-doc` | Process a document (PDF, slide deck, transcript) into the KB (handles scanned PDFs via vision) |
| `/adr` | Open a new ADR using the Sentinel template |
| `/day-1-rust` | Pod-2 onboarding: install toolchain · verify scaffold · generate `contract.rs` from Pod 1's schema · open first parser PR |

Skill frontmatter follows [`.claude/skills/_template.md.example`](skills/_template.md.example).

## Rules (2 path-scoped files)

| Rule | Scope | Purpose |
|---|---|---|
| [`pre-pr-discipline.md`](rules/pre-pr-discipline.md) | all | Two checks before a PR: does an issue cover this (propose, never create unprompted), and which documents describe what changed. Both detect-and-propose. Written after #40 found a merged service with zero mentions in the README. |
| [`kb-enrichment.md`](rules/kb-enrichment.md) | all | Policy: knowledge discovered during sessions must flow back into `.claude/kb/` via `/enrich-kb` or `/create-kb`. Defines the decision tree for KB vs. CLAUDE.md placement and the dating + confidence convention. |

## Knowledge Base (11 seed KBs)

| Category | KB | What it covers |
|---|---|---|
| Communication | `kb/communication/architecture-diagramming/` | Architecture communication — visual hierarchy, contracts-as-nodes, ownership seams, storytelling, diagram-review framework, 7 anti-patterns |
| Telemetry | `kb/telemetry/opentelemetry/` | OTel core concepts, OTLP `:4317`, three signal types |
| Telemetry | `kb/telemetry/otel-collector/` | Collector architecture (receiver/processor/exporter), what we're building |
| Storage | `kb/storage/clickhouse/` | Schema, native vs HTTP, ClickStack, OTel schema in CH |
| Cloud | `kb/cloud/gcp-telemetry/` | Cloud Monitoring, Cloud Logging, PubSub formats |
| Languages | `kb/languages/rust/` | Tokio, tonic, error handling, async patterns |
| Languages | `kb/languages/go/` | Concurrency, channels, OTel Collector internals *(retained as reference; the Go collector was removed in PR #28)* |
| Contracts | `kb/contracts/` | Pydantic (Python), Protobuf (Go/Rust), versioning, boundary validation |
| Detection | `kb/detection/anomaly-detection/` | Statistical baselines, z-scores, rolling windows |
| Process | `kb/process/crew-b-wow/` | Sentinel WoW: syncs, ADRs, PR flow, attribution, CI gates |
| Patterns | `kb/patterns/agentic-architecture/` | Packt *Agentic Architectural Patterns* book index — when to consult |

Browse `.claude/kb/README.md` for the full index with decision frameworks.

## Lookup policy (KB-first)

**Always check `.claude/kb/` before querying MCP or searching the web.**

Escalation ladder (stop at the first hit):
1. **KB** — read the relevant `index.md` or `quick-reference.md`
2. **MCP validate** — confirm with Context7 / Exa / Ref only if KB answer is uncertain
3. **Web search** — only if KB + MCP both miss; **immediately run `/enrich-kb <technology>` after to capture the finding** for future sessions

KB routing:

| Task | KB path |
|---|---|
| OTLP, OTel signal types | `kb/telemetry/opentelemetry/` |
| OTel Collector design, receivers/processors/exporters | `kb/telemetry/otel-collector/` |
| ClickHouse schema, native protocol, performance | `kb/storage/clickhouse/` |
| GCP telemetry shapes (logs/metrics/traces) | `kb/cloud/gcp-telemetry/` |
| Rust async (tokio, tonic) | `kb/languages/rust/` |
| Go concurrency, OTel Collector internals *(reference only — no Go in the repo)* | `kb/languages/go/` |
| Pydantic / Protobuf contract validation | `kb/contracts/` |
| Anomaly detection (z-scores, rolling windows) | `kb/detection/anomaly-detection/` |
| Crew B WoW, ADRs, PR flow | `kb/process/crew-b-wow/` |
| Agentic patterns (CrewAI, multi-agent design) | `kb/patterns/agentic-architecture/` |
| Architecture communication, diagram review, contract/ownership visualization | `kb/communication/architecture-diagramming/` |

## Working agreement (WoW)

Per Sync 01 + `bem-vindos.md`:

- **`main` is protected.** Feature branches: `feat/<area>-<short>`, `fix/`, `chore/`, `docs/`.
- **Agent fleets follow [ADR-0009](../docs/adr/0009-agentic-gitflow.md)** — *seam → swimlane → leg → task*: one `git worktree` per agent (`leg/<area>/<task>-v<n>` in `.worktrees/`), legs declaring **disjoint paths**, 1 review to squash into the swimlane, 2 approvals + a **merge commit** into `main` so per-leg attribution survives. Mechanics: [`AGENTIC_GITFLOW.md`](docs/AGENTIC_GITFLOW.md). ⚠️ The merge-commit rule amends the WoW below and is **pending ratification**.
- **Conventional Commits.** `<type>(<scope>): <description>`
- **Signed commits.** `git commit -S`.
- **Mandatory attribution trailer** on every commit: `Co-Authored-By: <human>`, `Co-Authored-By: <LLM model>`, optional `Reviewed-by: <bot>`.
- **CI gates.** ⚠️ Two workflows exist — `rust-ci.yml` and `pr-linked-issue.yml`. The seven the WoW names (ruff · mypy --strict · pytest >80% · bandit + safety · markdownlint · CodeRabbit · Docker build) are a **target, not a description**: none runs, and the four Python/Silver suites gate nothing ([#34](https://github.com/luanmorenommaciel/sentinel/issues/34)). ⚠️ This is the *agreement* from Sync 01, not the current state: only [`rust-ci.yml`](../.github/workflows/rust-ci.yml) is implemented today.
- **2 approvals** required: first peer, second Captain. Squash-merge to main *(ADR-0009 proposes a merge commit for swimlane→main — pending ratification)*.
- **Weekly sync** Tuesday Zoom ~60min.
- **Tool freedom on input, rigor on output.** Pick any LLM coding tool (Claude Code, Cursor, Codex CLI, Aider, etc.); the contract is honest attribution + 7-gate CI.

Full WoW: `kb/process/crew-b-wow/index.md`.

## Quick reference

| Task | Tool |
|---|---|
| Start a new ADR | `/adr <title>` |
| Author a new agent | `/create-agent <name>` |
| Author a new KB section | `/create-kb <technology>` |
| Author a new slash command | `/create-skill <name>` |
| Refresh KBs with latest docs | `/update-kbs` |
| Write web findings back to KB | `/enrich-kb <topic>` |
| Generate / refresh a README | `/readme-maker` |
| Process a document (PDF, transcript) into KB | `/ingest-doc <path>` |
| Onboard a new Astronaut to Pod 2's Rust path | `/day-1-rust` |
| Run an agent fleet across parallel legs | [`docs/AGENTIC_GITFLOW.md`](docs/AGENTIC_GITFLOW.md) |
| Design OTel Collector pipeline | otel-collector-specialist agent |
| Design ClickHouse schema | clickhouse-engineer agent |
| Optimize Rust async code | rust-specialist agent |
| Statistical anomaly detection | anomaly-detection-engineer agent |
| Architecture / multi-step planning | the-planner agent |
| Code review | code-reviewer agent · `/review` |
| Generate tests | test-generator agent |
| Generate docs | code-documenter agent |
| Explain something to a non-technical audience | adaptive-explainer agent |
| Analyze meeting transcripts | meeting-analyst agent |
| Author / fix shell scripts | shell-script-specialist agent |
| Map an unfamiliar codebase area | codebase-explorer agent |
| Review how a diagram / README / ADR communicates architecture | architecture-visualization-reviewer agent · `/arch-review` |
| Real GCP OTLP / Cloud Monitoring / Workload Identity | gcp-engineer agent |
| Python (Pod 1's generator, contracts, pytest) | python-developer agent |
| Design a new KB | kb-architect agent · `/create-kb` |

## Terminology guardrails

- The component at `:4317` is the **OTel Collector** — never "Hotel" (that's the AI mishearing the Portuguese pronunciation of "OTel"; the meeting summaries preserved the artifact).
- **Astronaut(a)** = team member. **Captain** = sprint facilitator (a *hat*, not a permanent role — rotates each sprint). **Commander** = Luan Moreno.
- **Crew B** = the 8 of us. **Pod** = unit of work within a crew, owns a feature.
- **Watcher** = a detection feature (Arrival, Parse, Volume, Schema, Latency, Storage).
- **good-first-issue** = the sacred tag — Captain pre-tags 5-10 per sprint.

## See also

- Spec: `../docs/sentinel.pdf` (in `victor_docs/`, local-only)
- Welcome: `../victor_docs/bem-vindos.md` (Commander's intro)
- Sync 01 notes: `../victor_docs/Sync 01.md`
- Sync 02 notes: `../victor_docs/2026-05-26-weekly-sync-crew-b-sentinel.pdf`
- ADR index: `../docs/adr/README.md`
- OCR strategy: `./docs/OCR_STRATEGY.md`
- Roadmap: `./docs/ROADMAP.md`
- Agentic gitflow: `./docs/AGENTIC_GITFLOW.md` (mechanics) + `../docs/adr/0009-agentic-gitflow.md` (the decision)
- Glossary: `./docs/CREW_B_GLOSSARY.md`

---

*Built with specialized agents, validated knowledge, confident execution. Strong opinions, weakly defended.*
