# Diagram-Type Rubrics — the P0 gate

> **Purpose**: Classify a diagram *before* critiquing it, then apply the rubric that fits its type. This is the safeguard that stops the framework from forcing boundary/contract conventions onto diagrams whose job is something else.
> **Confidence**: 0.90 (first-party; added in v1 after the self-review found mono-modality)
> **Added**: 2026-06-09

## Why classify first

The original framework assumed every diagram was a multi-team boundary/flow diagram and that contracts were always the asset. That assumption produces **false positives** on sequence diagrams (messages-on-edges is correct, not "Edge-Label Contracts"), on module-internals diagrams (the implementation *is* the subject), and on status/roadmap views (status-on-color is the point). P0 removes the assumption: identify the type, then judge by that type's rubric.

## The four classification questions (P0)

1. **Type** — which of the rubrics below?
2. **Audience & altitude** — exec / reviewer / engineer; which C4 level?
3. **Intended claim** — the one sentence the viewer should leave with.
4. **What's decisive** — contract, implementation, topology, trust boundary, or timing? (Drives the [contract-primacy safeguard](../index.md#the-contract-primacy-safeguard).)

If any is unknowable from the artifact, **escalate** — ask, don't guess.

## The rubric table

| Diagram type | What's the asset (gets salience) | Contract-gate (P3)? | Type-specific watch-outs |
|---|---|---|---|
| **Flow / boundary** (≈ C4 container) | contracts + ownership/trust boundaries | **Yes** — its home turf | A1–A7, A11; the origin pattern |
| **Sequence** | ordering, timing, round-trips | **No** — messages belong on edges | don't "promote messages to nodes"; watch missing error/timeout paths |
| **State machine** | legal states + transitions + guards | No | watch unreachable/dead states, missing terminal state |
| **ER / data model** | entities, relationships, **cardinality**, keys | No | keys/cardinality are the asset, not color; watch missing cardinality |
| **Deployment / infra** | runtime nodes, **network + trust boundaries**, zones | Partial — boundaries yes, contracts no | A11 Invisible Trust Boundary is the prime risk |
| **Dependency graph** | coupling, **cycles**, fan-in/out | No | watch A4-style "big ball of arrows"; cycles must be visible |
| **C4 (context/container/component/code)** | altitude-appropriate detail | Yes at container level | A9 Altitude Smear — never mix levels in one diagram |
| **Status / roadmap** | progress state | No | here status-on-color is *correct*; do **not** flag A2 |

## How the type changes the verdict

- **Wrong type for the message** → REWORK (A8 Diagram-Type Mismatch). Example: a flowchart used to argue about request timing should have been a sequence diagram.
- **Right type, wrong rubric applied by the reviewer** → the reviewer's error; P0 prevents it.
- **Implementation-decisive subject** (any type) → apply the contract-primacy safeguard; the implementation may be the hero.

## Worked examples (Sentinel)

- README §1 → **flow/boundary**, multi-team, contract-decisive → contract-gate rubric (correct).
- ADR-0004 diagram → could be flow, but **implementation-decisive** → safeguard; feature the impl, suppress A1.
- A future OTLP-`:4317` ingest diagram → **deployment/trust** lens → draw the trust boundary (A11) where foreign telemetry enters.

## See Also

- [`../index.md`](../index.md) — P0 in the principle ladder
- [`boundary-types.md`](boundary-types.md) — the boundary taxonomy several rubrics reference
- [`../patterns/contract-gate-diagram.md`](../patterns/contract-gate-diagram.md) — the pattern that only applies to the flow/boundary row

## Sources

- First-party: Sentinel Pod 2 review + v1 self-review, 2026-06-09
- C4 model — <https://c4model.com> (levels + the "don't smear altitudes" rule)
