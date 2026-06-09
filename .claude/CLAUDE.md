# Sentinel — Claude Code Project Context

> Last updated: 2026-06-09

## Mission

**Sentinel = autonomous observability + remediation for data pipelines.** Self-healing where safe, page where it matters. One mission: *no downstream user finds the bug before Sentinel does.*

Open-source. Built by **Crew B** of the DataShip Mission 2026 mentorship program led by **Luan Moreno** (Commander). Upstream repo: <https://github.com/luanmorenommaciel/sentinel>.

## Architecture (Phase 1)

```text
Generator ──▶ OTel Collector ──▶ ClickStack (ClickHouse)
              │
              └─ OTLP gRPC :4317
```

First cloud target: **GCP**. Python is OUT for the Collector (perf); Go and Rust are on the bake-off table (see [ADR-0004](../docs/adr/0004-collector-implementation-language.md)).

**Eight-stage spine (vendor-agnostic):**

```text
otel_core → rolling_stats → tiered_engine → cross_watcher → policy_engine → remediation → audit_log → feedback_loop
   SIGNAL       LEARN          DETECT          DETECT          DECIDE          ACT          ATTEST       LEARN
```

**6 Watcher Crews:** Arrival · Parse · Volume · Schema · Latency · Storage.
**3-tier detection cascade:** Statistical (z-scores) → Pattern (signature) → LLM (Haiku→Sonnet→Opus). *Cheapest tier wins. Opus only when Sonnet confidence is low AND blast radius is high.*

## Current state (Pod 2 — `collector-rust`)

> Source of truth: [README §8](../README.md) + the contract docs below. This block is the quick orientation; don't let it drift.

- **Collector-rust is functional end-to-end** (verified live 2026-06-09): both ingest paths land in ClickHouse — file/NDJSON (golden `baseline_seed42.jsonl` → 48 logs / 48 spans / 183 metrics) and OTLP gRPC `:4317`.
- **gRPC receive-boundary validation** is policy-gated via `contract.grpc_validation` (`off` / `warn` / `strict`, **default `warn`**). File mode still uses `contract.strict` (all-or-nothing). Foreign OTLP legitimately lacks the 5 `sentinel.*` keys → `strict` would drop it, hence `warn` default. Code: `src/grpc.rs` (`apply_validation`), `src/config.rs`.
- **Pod 1 → Pod 2 input contract:** `v1.0.0` **frozen**; local `contract/schema/otlp_output.schema.json` verified byte-identical to upstream `001-otel-data-generator`.
- **Pod 2 → Pod 3 read contract:** **`v1.0.0-rc.1`** — *authoritative release candidate* (build against it), not frozen. Freeze gates open: ADR-0005 + ADR-0006 acceptance, Pod 3 sign-off (Pod 3/B3 still unstaffed). Day-4 round-trip gate ✅. Doc: [`docs/contracts/pod2-pod3-read-contract.md`](../docs/contracts/pod2-pod3-read-contract.md).
- **ADR-0004/0005/0006 all still `Proposed`.** ADR-0004 (language bake-off) does **not** block the read-contract freeze.

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
│   ├── collector-rust/            # Rust collector scaffold (ADR-0004)
│   ├── collector-go/              # Go collector scaffold (sibling, pending)
│   └── generator/                 # Python data generator (Pod 1)
├── infra/                         # ClickHouse, Docker compose, deployment configs
├── .claude/
│   ├── CLAUDE.md                  # This file
│   ├── agents/                    # Specialized subagents (15) + _schema.json + _template.md.example
│   ├── skills/                    # Slash commands (9) + _template.md.example
│   ├── kb/                        # Knowledge bases (10 seed KBs) + _templates/ + _index.yaml
│   ├── docs/                      # Internal standards (5 — OCR, ingestion, roadmap, glossary, Rust standards)
│   └── rules/                     # Path-scoped instruction files (1 — kb-enrichment)
└── README.md
```

## Agents (15 specialized)

| Category | Agents |
|---|---|
| Code Quality | code-reviewer · code-documenter · test-generator · shell-script-specialist |
| Communication | adaptive-explainer · meeting-analyst |
| Workflow | the-planner |
| Telemetry | otel-collector-specialist |
| Storage | clickhouse-engineer |
| Detection | anomaly-detection-engineer |
| Languages | rust-specialist · python-developer |
| Cloud | gcp-engineer |
| Exploration | kb-architect · codebase-explorer |

Each agent has its own `.md` under `.claude/agents/<category>/<name>.md`. All agents have a `Use PROACTIVELY when …` trigger line so auto-invocation fires consistently. The frontmatter schema is documented in [`.claude/agents/_schema.json`](agents/_schema.json) (recommended-not-required at bootstrap).

## Skills (9 slash commands)

| Skill | Purpose |
|---|---|
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

## Rules (1 path-scoped file)

| Rule | Scope | Purpose |
|---|---|---|
| [`kb-enrichment.md`](rules/kb-enrichment.md) | all | Policy: knowledge discovered during sessions must flow back into `.claude/kb/` via `/enrich-kb` or `/create-kb`. Defines the decision tree for KB vs. CLAUDE.md placement and the dating + confidence convention. |

## Knowledge Base (10 seed KBs)

| Category | KB | What it covers |
|---|---|---|
| Telemetry | `kb/telemetry/opentelemetry/` | OTel core concepts, OTLP `:4317`, three signal types |
| Telemetry | `kb/telemetry/otel-collector/` | Collector architecture (receiver/processor/exporter), what we're building |
| Storage | `kb/storage/clickhouse/` | Schema, native vs HTTP, ClickStack, OTel schema in CH |
| Cloud | `kb/cloud/gcp-telemetry/` | Cloud Monitoring, Cloud Logging, PubSub formats |
| Languages | `kb/languages/rust/` | Tokio, tonic, error handling, async patterns |
| Languages | `kb/languages/go/` | Concurrency, channels, OTel Collector internals |
| Contracts | `kb/contracts/` | Pydantic (Python), Protobuf (Go/Rust), versioning, boundary validation |
| Detection | `kb/detection/anomaly-detection/` | Statistical baselines, z-scores, rolling windows |
| Process | `kb/process/crew-b-wow/` | Sentinel WoW: syncs, ADRs, PR flow, attribution, 7 CI gates |
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
| Go concurrency, OTel Collector internals | `kb/languages/go/` |
| Pydantic / Protobuf contract validation | `kb/contracts/` |
| Anomaly detection (z-scores, rolling windows) | `kb/detection/anomaly-detection/` |
| Crew B WoW, ADRs, PR flow | `kb/process/crew-b-wow/` |
| Agentic patterns (CrewAI, multi-agent design) | `kb/patterns/agentic-architecture/` |

## Working agreement (WoW)

Per Sync 01 + `bem-vindos.md`:

- **`main` is protected.** Feature branches: `feat/<area>-<short>`, `fix/`, `chore/`, `docs/`.
- **Conventional Commits.** `<type>(<scope>): <description>`
- **Signed commits.** `git commit -S`.
- **Mandatory attribution trailer** on every commit: `Co-Authored-By: <human>`, `Co-Authored-By: <LLM model>`, optional `Reviewed-by: <bot>`.
- **7 CI gates** (all must pass before human review): ruff · mypy --strict · pytest >80% · bandit + safety · markdownlint · CodeRabbit · Docker build.
- **2 approvals** required: first peer, second Captain. Squash-merge to main.
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
- Glossary: `./docs/CREW_B_GLOSSARY.md`

---

*Built with specialized agents, validated knowledge, confident execution. Strong opinions, weakly defended.*
