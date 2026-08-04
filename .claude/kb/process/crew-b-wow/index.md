---
title: Crew B Way of Working
last_updated: 2026-07-14
confidence: 0.95
---

# Crew B Way of Working

> **MCP Validated:** 2026-06-01
> **Agent Git governance web-validated:** 2026-07-14
> Sources: Sync 01 deck, Sync 02 transcript (2026-05-26), `bem-vindos.md` (Commander's intro), `.claude/docs/CREW_B_GLOSSARY.md`.

This is the canonical process reference for Sentinel Crew B. Every Astronaut, every PR, and every weekly sync follows what is written here. When this file and a Discord message disagree, this file wins.

---

## Roles

### Commander

Luan Moreno. Owns the mission vision, opens architecture-level GitHub Issues, merges to `main`, leads the weekly Zoom sync. Not a sprint facilitator — that is the Captain hat.

### Astronaut(a)

Any member of Crew B. Eight total. (Portuguese: *astronauta* — same word, used interchangeably in the repo.)

### Captain

A *hat*, not a separate role. The Astronaut wearing it this sprint:

- Plans and owns the sprint backlog
- Triages PRs Wednesday and Friday
- Runs a weekly 15-minute 1:1 with the Commander
- Pre-tags `good-first-issue` (5-10 items per sprint, pre-sprint)
- Writes the cohort status update at sprint end

Time split: approximately 60-70% Individual Contributor, 30-40% leadership overhead. The hat rotates every sprint — confirmed at the Tuesday Zoom.

### Pod

The unit of work within Crew B. Two Astronautas per Pod. A Pod owns one feature end-to-end: from contract definition through CI-green merge. Pods are the atomic accountability unit — if a feature slips, the owning Pod is the first call.

---

## Pod Assignments (Sync 02, 2026-05-26)

| Pod | Watcher scope | Astronautas |
|-----|---------------|-------------|
| B1  | Arrival (W01) + Parse (W02) | TBD |
| B2  | OTel Collector (Pod 2 — Generator→ClickHouse middle layer) | Alex Botelho, Victor Urquiola, Ruan Pomponet |
| B3  | Volume (W03) + Schema (W04) / Latency (W05) + Storage (W06) | TBD |
| B4  | Action Dispatcher | TBD |

Pod B2 is Victor's Pod. It owns the OTel Collector: receives OTLP gRPC on `:4317`, validates contracts, converts, and exports to ClickHouse. A Rust vs Go bake-off is in progress (see ADR-0004 on `feat/rust-otel-collector`).

> Naming note: "Hotel Collector" in AI transcripts = OTel Collector. "Hotel" is a Portuguese-pronunciation transcription artifact. Use "OTel Collector" in all written artifacts.

---

## Sprint Cadence

### Weekly Sync

- **When:** Tuesday, Zoom, approximately 60 minutes
- **Who facilitates:** The Captain for that sprint
- **Standing agenda:** Pod assignments confirmed, first PRs reviewed live, ADR progress, blockers surfaced

### Sprint 1 Is Not Coding

The Commander's explicit framing from `bem-vindos.md`. Sprint 1 runs five steps in strict order:

```
1. Market Finding  →  2. Discuss what to build  →  3. Architecture sketch
    →  4. Backlog  →  5. First slice to main
```

No code merges to `main` until all five steps are done. The sprint ends when the first real slice lands. ADRs are the primary output of steps 2-3.

### Async Channels

| Channel | Purpose | NOT for |
|---------|---------|---------|
| Discord `#crew-b` | Async chat, questions, links | Decisions that matter in 6 months |
| WhatsApp | Urgent sync only | Documentation, design discussion |
| GitHub Issues | Every work item, bugs, spikes | Casual chat |
| GitHub Projects | Kanban board (backlog → done) | Free-form discussion |

The rule of thumb: if you would quote it in an ADR or PR description, write it in GitHub, not Discord.

---

## ADR Flow

Architecture Decision Records are the primary design artifact for Sentinel.

### File location

```
docs/adr/NNNN-<kebab-title>.md
```

Numbers are monotonically increasing. Zero-padded to four digits. Companion research (exploration briefs, benchmarks, data) lives in `docs/research/` and is referenced from the ADR.

### Status lifecycle

```
Proposed  →  Accepted
           →  Rejected
           →  Superseded (links to the superseding ADR)
```

Status is a field in the ADR frontmatter. Captain and Commander review before status moves to Accepted.

### Sprint 1 ADRs (due end of Sprint 1)

Three foundational ADRs were assigned in `bem-vindos.md`:

| ADR | Title | Core question |
|-----|-------|---------------|
| ADR-001 | Blast Radius | What levels of remediation exist (T0/T1/T2) and which may auto-execute? |
| ADR-002 | Baseline Definition | What is "normal" — rolling 7-day window, pre-trained model, or external OTel stream? |
| ADR-003 | Primary User | Who is Sentinel built for first — the data engineer, the SRE, or the pipeline owner? |

ADR-0004 (Collector implementation language: Rust vs Go) is live on `feat/rust-otel-collector` and is active beyond Sprint 1.

---

## PR Flow (8 Steps)

For agent-authored changes, the eight steps run inside the isolation and governance rules in [`concepts/agent-git-governance.md`](concepts/agent-git-governance.md): one Issue, agent task, worktree, short-lived branch, and PR per independently reviewable outcome. Agents never share a mutable checkout or bypass GitHub merge controls.

```mermaid
flowchart TD
    A[Branch off main\nfeat/area-short] --> B[Conventional Commits\n+ attribution trailers]
    B --> C[Push signed commits]
    C --> D{7 CI gates pass?}
    D -- No --> E[Fix locally. CI fail = no human review.]
    D -- Yes --> F[CODEOWNERS auto-routes\nto reviewer]
    F --> G[Optional: /claude review]
    G --> H[Peer approval #1]
    H --> I[Captain approval #2]
    I --> J[Squash-merge to main]
```

### Step 1 — Branch naming

```
feat/<area>-<short-description>
fix/<area>-<short-description>
chore/<area>-<short-description>
docs/<area>-<short-description>
```

Examples: `feat/collector-otlp-receiver`, `docs/adr-0004-go-rust-bakeoff`, `fix/b2-grpc-shutdown`.

### Step 2 — Conventional Commits + attribution

Every commit message follows the Conventional Commits specification:

```
<type>(<scope>): <description>

[optional body]

Co-Authored-By: Human Name <email>
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
Reviewed-by: CodeRabbit <bot@coderabbit.ai>
```

The `Co-Authored-By` trailers for human and LLM are **mandatory**. `Reviewed-by` for CodeRabbit is optional but encouraged. These appear in `git log` forever — that is the attribution contract.

**Tool freedom:** Astronautas may use any agentic coding tool — Claude Code, Cursor, Codex CLI, Aider, Zed AI, Kimi K2, Cline, Windsurf, or propose another. The non-negotiable is honest attribution on the output.

### Step 3 — Signed commits

All commits must be GPG-signed (`git commit -S`). `main` enforces this at the branch protection level.

### Step 4 — 7 CI gates

CI runs on every push. All gates must be green before human review is requested:

| Gate | What it checks | Language |
|------|---------------|----------|
| `ruff` | Lint + format | Python |
| `mypy --strict` | Type safety | Python |
| `pytest >80%` | Unit + integration coverage | Python |
| `bandit + safety` | Security scan (SAST + dep vulns) | Python |
| `markdownlint` | Docs format consistency | All |
| `CodeRabbit` | AI code review (automated first pass) | All |
| `Docker build` | Container builds clean | All |

For Rust services (Pod B2), the per-language profile extends the above:

| Additional gate | What it checks |
|----------------|----------------|
| `cargo fmt --check` | Format (rustfmt.toml) |
| `cargo clippy -- -D warnings` | Lint (strict) |
| `cargo nextest run` | Test runner (replaces `cargo test`) |
| `cargo audit` | Dependency security audit |

Full Rust setup: `.claude/docs/RUST_PROJECT_STANDARDS.md`.

### Steps 5-6 — CODEOWNERS + optional Claude review

`CODEOWNERS` automatically routes the PR to the owning Pod's Astronautas. Optionally invoke the `code-reviewer` agent via `/claude review` for a structured pre-human pass before requesting approvals.

### Steps 7-8 — 2 approvals + squash-merge

Two approvals required: first from a peer Astronaut, second from the Captain. Squash-merge to `main`. The squash commit retains the attribution trailers from the constituent commits in its body.

---

## GitHub Issues

Every work item — feature, bug, spike, or research task — lives as a GitHub Issue. Rules:

- Issues are the single source of truth for scope; Discord messages are not.
- Every Issue is tagged (area, type, priority) and linked to its ADR when relevant.
- Issues are closed by a merged PR, not by hand.
- `good-first-issue` is the sacred tag. Captain pre-tags 5-10 per sprint before the Tuesday sync. These are the entry points for Astronautas picking up new work.

---

## Lego Principle

Every component (Watcher, stage of the eight-stage spine, or the Collector itself) declares an explicit input/output contract:

- **Python:** Pydantic models (versioned semver)
- **Go / Rust:** Protobuf schemas (versioned semver)

"Build it like Lego" means the internals of a component can change completely as long as the contract boundary holds. This is what enables Pod-level ownership — Pod B2 can rewrite the Collector in Rust without breaking Pod B1's generator output or Pod B3's ClickHouse schema.

Contract spec for Pod 1 output: `contract/schema/otlp_output.schema.json` on `001-otel-data-generator` branch (JSON Schema v1.0.0, signal_type discriminated log/span/metric, Sentinel-specific resource attrs required).

---

## Anti-patterns

| Anti-pattern | Why it is wrong |
|---|---|
| Merging directly to `main` | `main` is protected. No exceptions. |
| Requesting human review with red CI | CI fail = no human review. Fix the gate first. |
| Omitting `Co-Authored-By` trailers | Breaks the attribution contract. Every commit. |
| Using "Hotel" for the Collector | Transcription artifact. Always "OTel Collector." |
| Making architectural decisions in Discord | Discord is ephemeral. ADRs are permanent. |
| Skipping `good-first-issue` pre-tagging | Blocks new Astronautas from picking up work. |
| Writing an ADR without companion research | ADRs need evidence. Companion in `docs/research/`. |
| "Self-healing" without specifying blast radius | Meaningless until ADR-001 ships the T0/T1/T2 taxonomy. |

---

## See also

- [`concepts/agent-git-governance.md`](concepts/agent-git-governance.md) — three agent execution models and Sentinel's Git/GitHub control standard
- `.claude/CLAUDE.md` — full project context, architecture summary, KB routing table
- `.claude/docs/CREW_B_GLOSSARY.md` — canonical definitions for all Sentinel terms
- `.claude/docs/RUST_PROJECT_STANDARDS.md` — Rust CI profile, workspace layout, `cargo` toolchain
- `docs/adr/` — all Architecture Decision Records (start with ADR-001, ADR-002, ADR-003)
- `docs/research/` — research briefs companion to ADRs
- `../../../victor_docs/bem-vindos.md` — Commander's intro (Sprint 1 framing, five-step order)
- `kb/contracts/` — Pydantic and Protobuf contract patterns (Lego principle detail)
- `kb/telemetry/otel-collector/` — OTel Collector architecture (Pod B2's scope)
- `kb/languages/rust/` — Rust async patterns (tokio, tonic) for Pod B2
- `kb/languages/go/` — Go concurrency + OTel Collector internals for the bake-off
