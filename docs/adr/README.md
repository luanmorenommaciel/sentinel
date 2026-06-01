# Architecture Decision Records

This directory holds Sentinel's ADRs. Per the [Crew B WoW spec](../../README.md), markdown ADRs are version-controlled, reviewed by Captain + Commander, and become the durable memory of *why* the architecture is what it is.

## Index

| # | Title | Status | Owner |
|---|---|---|---|
| 0001 | Blast radius of self-healing | _Pending_ | Crew B (Sprint 1) |
| 0002 | Where the baseline lives | _Pending_ | Crew B (Sprint 1) |
| 0003 | Primary user of Sentinel | _Pending_ | Crew B (Sprint 1) |
| 0004 | [Collector implementation language](0004-collector-implementation-language.md) | **Proposed** | Pod 2 |

ADRs 0001–0003 are the three Sprint 1 ADRs the Commander assigned (`bem-vindos.md`). ADR-0004 is a Pod 2 proposal opening the Collector language bake-off (Sync 02 action A7).

## Template

```markdown
# ADR-NNNN · <Title>

| Field | Value |
|---|---|
| Status | Proposed / Accepted / Rejected / Superseded |
| Date | YYYY-MM-DD |
| Owners | <names> |
| Proposer | <name> |
| Supersedes | — |
| Related | <issue / sync / ADR refs> |

## Context

## Decision

## Options considered

## Trade-offs

## Consequences

## Risks

## Next steps

## References
```

## Rules

1. **Status starts at Proposed.** Promoted to Accepted only after Captain + Commander review + 2 approvals on the PR.
2. **One decision per ADR.** If you're documenting two decisions, that's two ADRs.
3. **Supersession is explicit.** New ADR points back; old ADR's status flips to Superseded with a link forward.
4. **Number monotonically.** Reserve a number by opening the file in your PR; first-PR-merged wins ties.
5. **Companion research is fine.** Heavy receipts go in `docs/research/<topic>.md` so the ADR stays scannable.
