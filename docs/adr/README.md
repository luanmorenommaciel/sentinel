# Architecture Decision Records

This directory holds Sentinel's ADRs. Per the [Crew B WoW spec](../../README.md), markdown ADRs are version-controlled, reviewed by Captain + Commander, and become the durable memory of *why* the architecture is what it is.

## Index

| # | Title | Status | Owner |
|---|---|---|---|
| 0001 | Blast radius of self-healing | _Pending_ | Crew B (Sprint 1) |
| 0002 | Where the baseline lives | _Pending_ | Crew B (Sprint 1) |
| 0003 | Primary user of Sentinel | _Pending_ | Crew B (Sprint 1) |
| 0004 | [Collector implementation language](0004-collector-implementation-language.md) | **Proposed** ⚠️ *stale — Rust selected in practice* | Pod 2 |
| 0005 | [ClickHouse storage schema for OTLP signals](0005-clickhouse-storage-schema.md) | **Superseded by 0007** | Pod 2 |
| 0006 | [Optional trace/span ID representation](0006-optional-id-representation.md) | **Proposed** (refined by 0007) | Pod 2 |
| 0007 | [Bronze = canonical Pod 2 → Pod 3 contract](0007-bronze-canonical-contract.md) | **Proposed** | Pod 2 · Pod 3 |
| 0008 | [Contracts registry namespaced by producing Pod](0008-contracts-registry-by-producing-pod.md) | **Proposed** | Pod 1 · Pod 2 |
| 0009 | [Agentic gitflow — seam → swimlane → leg → task](0009-agentic-gitflow.md) | **Proposed** | Crew B (all Pods) |
| 0010 | [Silver v1 operational model](0010-silver-v1-operational-model.md) | **Proposed** | Pod 3 |

ADRs 0001–0003 are the three Sprint 1 ADRs the Commander assigned (`bem-vindos.md`). ADR-0004 is a Pod 2 proposal opening the Collector language bake-off (Sync 02 action A7). ⚠️ **It is out of date:** Rust was selected and `services/collector-go/` was removed from the repo in PR #28 (merged 2026-08-12). The decision was taken by merge, not by ADR — promoting 0004 to **Accepted** with a selection note is an open Pod 2 action. ADRs 0005–0006 are Pod 2's Day-3 storage-schema decisions, gating the [Pod 2 → Pod 3 ClickHouse read contract](../../contracts/collector/v1/pod2-pod3-read-contract.md). **ADR-0007 supersedes 0005**: Pod 3's otel-collector-contrib bronze schema (database `bronze`, `bronze.*` — renamed from `sentinel` per [ADR-0007's 2026-07-21 amendment](0007-bronze-canonical-contract.md), which disambiguates it from the `sentinel.*` attribute keys) is now the canonical read contract, and the Rust collector writes directly into it (validated end-to-end). **ADR-0008** records the `contracts/` registry structure — namespaced by producing Pod (`generator/` + `collector/`), implementation-agnostic, versioned per boundary. **ADR-0009** is the first *process* ADR: the branching model for agent fleets (seam → swimlane → leg → task, one git worktree per agent), with a practical guide at [`.claude/docs/AGENTIC_GITFLOW.md`](../../.claude/docs/AGENTIC_GITFLOW.md). It amends the WoW's merge rules, so it needs explicit ratification.

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
