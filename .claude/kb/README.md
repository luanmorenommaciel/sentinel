# Sentinel Knowledge Base

> The technical reference manual the agents read before answering. KB-first lookup policy: check here before MCP, web search, or asking the user.

## Browse by category

### Telemetry
| KB | What it covers |
|---|---|
| [`telemetry/opentelemetry/`](telemetry/opentelemetry/index.md) | OTel core, OTLP `:4317`, the three signal types (traces, metrics, logs), semantic conventions |
| [`telemetry/otel-collector/`](telemetry/otel-collector/index.md) | OTel Collector architecture (receiver/processor/exporter), backpressure, what Sentinel builds vs configures |

### Storage
| KB | What it covers |
|---|---|
| [`storage/clickhouse/`](storage/clickhouse/index.md) | ClickHouse + ClickStack — schema, native protocol, performance, OTel storage tables |

### Cloud
| KB | What it covers |
|---|---|
| [`cloud/gcp-telemetry/`](cloud/gcp-telemetry/index.md) | GCP telemetry surfaces (Cloud Logging, Monitoring, Trace), resource attributes per service, OTLP integration |

### Languages
| KB | What it covers |
|---|---|
| [`languages/rust/`](languages/rust/index.md) | Rust idioms — tokio async, tonic gRPC, error handling, lifetimes (project setup is in [`.claude/docs/RUST_PROJECT_STANDARDS.md`](../docs/RUST_PROJECT_STANDARDS.md)) |
| [`languages/go/`](languages/go/index.md) | Go idioms — goroutines, channels, context, OTel Collector upstream internals |

### Contracts
| KB | What it covers |
|---|---|
| [`contracts/`](contracts/index.md) | Pydantic (Python) + Protobuf (Go/Rust) + JSON Schema, versioning, boundary validation |

### Detection
| KB | What it covers |
|---|---|
| [`detection/anomaly-detection/`](detection/anomaly-detection/index.md) | Tier 1 statistical methods — z-scores, rolling windows, drift detection, false-positive control |

### Process
| KB | What it covers |
|---|---|
| [`process/crew-b-wow/`](process/crew-b-wow/index.md) | Crew B Way of Working — roles, sprints, ADRs, 8-step PR flow, 7 CI gates, attribution contract |

### Communication
| KB | What it covers |
|---|---|
| [`communication/architecture-diagramming/`](communication/architecture-diagramming/index.md) | Architecture *communication* — visual hierarchy, contracts-as-first-class-nodes, ownership seams, technical storytelling, the diagram-review framework, and the seven visualization anti-patterns |

### Patterns
| KB | What it covers |
|---|---|
| [`patterns/agentic-architecture/`](patterns/agentic-architecture/index.md) | Index into the Packt *Agentic Architectural Patterns* book — when to consult which chapter |

## How to navigate

**Looking for a quick answer?** Open the relevant `index.md`. Each one has a "quick-reference" section at the end with copy-paste-ready patterns.

**Looking for deep context?** Each KB follows this canonical shape (see [`_templates/`](_templates/) for the source files):

```text
kb/<category>/<topic>/
├── index.md              # overview + decision framework (always present)
├── quick-reference.md    # patterns + snippets + gotchas (added on demand)
├── concepts/             # deeper conceptual files — one per concept, <150 lines each
└── patterns/             # production-proven patterns — added via /enrich-kb after first real use
```

`concepts/` and `patterns/` start as `.gitkeep` stubs and grow on demand. The [`_templates/`](_templates/) directory holds the canonical file shapes: `index.md.template`, `quick-reference.md.template`, `concept.md.template`, `pattern.md.template`, `domain-manifest.yaml.template`. The [`_index.yaml`](_index.yaml) is the machine-readable registry consumed by skills (`/create-kb`, `/enrich-kb`, `/update-kbs`) and the `kb-architect` agent — domain paths, confidence scores, Sentinel touch points, related agents/ADRs.

**Looking for a technology that's not here?** Two options:
1. **If it'll come back** — run `/create-kb <technology>` to scaffold a new KB section.
2. **If it's a one-off** — search the web, do the task, then close the loop with `/enrich-kb <technology>` if the finding is reusable.

## Lookup policy

1. Open the relevant `index.md` here.
2. If the answer isn't here but the KB is the right place, check `quick-reference.md` or `concepts/`.
3. If still not found, query MCP (Context7 / Exa / Ref) — only then go to web search.
4. **After any successful web search, run `/enrich-kb <topic>`** to capture the finding. The KB grows from real use.

See [`.claude/rules/kb-enrichment.md`](../rules/kb-enrichment.md) for the full enrichment policy.

## Confidence scoring

Every KB entry is dated and tagged with a confidence level:

- **0.95** — KB + MCP agree; matches official docs
- **0.85** — MCP-validated only (newer than the local KB)
- **0.75** — KB-only (no recent re-validation)
- **0.50** — Conflict between sources; needs human review

Re-validate periodically via `/update-kbs` (suggested monthly cadence).

## Decision frameworks (cross-KB)

These are the "when do I use what" decisions that come up most often:

| Decision | KB(s) to consult |
|---|---|
| Collector implementation language (Rust vs Go) | `languages/rust/` + `languages/go/` + ADR-0004 |
| Anomaly detection method (z-score vs robust z vs IQR) | `detection/anomaly-detection/` |
| ClickHouse schema for a new Watcher signal | `storage/clickhouse/` + Pod 3 owner |
| Contract design (JSON Schema vs Proto vs Pydantic) | `contracts/` |
| When to add an LLM step to a pipeline | `patterns/agentic-architecture/` + the 3-tier cascade in CLAUDE.md |
| Which Watcher consumes which signal | `telemetry/opentelemetry/` |

## See also

- [`.claude/CLAUDE.md`](../CLAUDE.md) — project context with the master lookup tables
- [`.claude/docs/RUST_PROJECT_STANDARDS.md`](../docs/RUST_PROJECT_STANDARDS.md) — Rust setup (UV-equivalent)
- [`.claude/docs/CREW_B_GLOSSARY.md`](../docs/CREW_B_GLOSSARY.md) — terminology + anti-glossary
- [`.claude/skills/create-kb/SKILL.md`](../skills/create-kb/SKILL.md) — how to add a new KB
- [`.claude/skills/enrich-kb/SKILL.md`](../skills/enrich-kb/SKILL.md) — how to flow findings back to KB
- [`.claude/skills/update-kbs/SKILL.md`](../skills/update-kbs/SKILL.md) — how to refresh KBs
