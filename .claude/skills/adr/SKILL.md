---
name: adr
description: Open a new Architecture Decision Record using the Sentinel template (status Proposed, numbered monotonically, Captain + Commander review). Use whenever a decision will outlive the sprint it was made in (architecture, language pick, contract, blast radius, baseline source, user persona).
---

# /adr

Scaffolds `docs/adr/NNNN-<kebab-title>.md` with the standard Sentinel ADR template, in `Proposed` status. The ADR is committed on its own feature branch and reviewed via the standard 8-step PR flow (signed commits, 2 approvals, 7 CI gates).

## Usage

```text
/adr <title>
```

Examples:
- `/adr blast-radius-self-healing` (ADR-001)
- `/adr collector-implementation-language` (ADR-004 — already opened)
- `/adr clickhouse-retention-policy` (next available number)

## What it does

1. **Looks up the next ADR number** by scanning `docs/adr/NNNN-*.md` (monotonic — first PR merged wins ties).
2. **Creates a feature branch** (`docs/adr-NNNN-<short>`).
3. **Writes the ADR file** with the full Sentinel template (Context, Decision, Options, Trade-offs, Consequences, Risks, Next steps, References).
4. **Pre-fills** the frontmatter table: status (Proposed), date (today), proposer (you), related Sync / Issue refs (asks if not obvious).
5. **Updates** `docs/adr/README.md` index with the new ADR row.
6. **(Optional)** If the ADR's decision warrants research receipts, creates a paired `docs/research/<kebab-title>.md` and links it from the ADR.

## ADR statuses

| Status | Meaning |
|---|---|
| Proposed | In discussion. PR open. |
| Accepted | Merged. The decision is canonical. |
| Rejected | Closed without merge. Kept in the repo for context. |
| Superseded by ADR-NNNN | Replaced by a later ADR. Link forward. |

## ADR rules

1. **One decision per ADR.** If you're documenting two decisions, that's two ADRs.
2. **Honest options.** Every ADR must lay out the alternatives you considered, with pros/cons — not just the winner.
3. **Status starts at Proposed.** Promoted to Accepted only after Captain + Commander review.
4. **Companion research goes in `docs/research/`.** Keeps the ADR scannable.
5. **Numbering is monotonic.** Don't renumber merged ADRs. Don't reuse numbers from Rejected ones.

## When NOT to use

- Decisions that won't outlive the sprint (e.g., "we'll use `--release` for this benchmark") — those go in the PR or Issue.
- Style choices already covered by the WoW (e.g., conventional commits) — those are baseline, not architecture.
- One-engineer preferences (e.g., "I prefer `match` over `if let`") — those go in the agent / lint config.

## Related

- `docs/adr/README.md` — the index + template + rules
- `docs/research/` — companion receipts for heavy ADRs
- `kb/process/crew-b-wow/` — full PR flow (8 steps)
- The 3 Sprint 1 ADRs assigned by the Commander (`bem-vindos.md`): blast radius, baseline, primary user
