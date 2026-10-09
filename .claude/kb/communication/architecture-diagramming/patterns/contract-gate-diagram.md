# Pattern: Contract-Gate + Ownership-Zone Diagram

> **Purpose**: A reusable Mermaid encoding that makes contracts the visual hero, ownership explicit, and implementations visibly interchangeable.
> **Confidence**: 0.90 (first-party; proven on the Sentinel Pod 2 README)
> **Added**: 2026-06-09
> **First production use**: Sentinel README §1, `feat/rust-otel-collector`, 2026-06-09

## When to Use

- A system where multiple teams hand work across versioned interfaces.
- A component with multiple/interchangeable implementations behind one contract.
- A README or review deck where contracts and ownership are the message.

## When NOT to Use

This pattern is **only** for the *flow/boundary* row of the [diagram-type rubric](../concepts/diagram-type-rubrics.md). Do **not** reach for it when:

- **The subject is the implementation, not the boundary** — a language/runtime bake-off (Sentinel ADR-0004), build-vs-buy (ADR-0005), or a performance argument. Gold-plating a contract here buries the actual decision; let the implementation be the hero (see the [contract-primacy safeguard](../index.md#the-contract-primacy-safeguard)).
- **The diagram type is non-boundary** — sequence/timing (use `sequenceDiagram`; messages belong on edges), state machine, ER/data model, dependency graph. Forcing nodes-not-edges here is anti-pattern **A8 Diagram-Type Mismatch**.
- **The decisive boundary is trust/network, not ownership** — use a deployment/trust render with a distinct perimeter line (see [boundary-types](../concepts/boundary-types.md)); contract gates won't show where untrusted input enters.
- A **single-owner, single-implementation** internal module (no handoff to show).
- An **exec one-liner** where even zones are too much detail (show only the gates).

## The encoding

| Element | Mermaid construct | Style class |
|---|---|---|
| Ownership zone | `subgraph` labeled `POD/TEAM — owns <X>` | muted slate |
| Contract gate | hexagon node `{{...}}` on the seam | gold, 4px border, bold |
| Implementation | rectangle, pale | white, faint border |
| Reference impl | rectangle, dark **outline** only | outline = "current" |
| Conformance | dashed edge `-. conforms to .->` | faint grey |
| Contract flow | thick edge `==>` | gold via `linkStyle` |
| Status | glyph ✅ 🔶 ⏳ in the label | never color |

## Template (copy, then fill the ALL-CAPS slots)

```mermaid
flowchart LR
    subgraph UP["TEAM A — owns SOURCE"]
        direction TB
        SRC["PRODUCER"]
    end

    C1{{"◆ CONTRACT BOUNDARY ◆<br/><b>A → B · INPUT</b><br/>SCHEMA_NAME<br/><b>vX.Y.Z · STATUS_GLYPH</b><br/>━━━━━━━━<br/>KEY GUARANTEES"}}

    subgraph MID["TEAM B — owns GATEWAY"]
        direction TB
        NOTE["<b>Interchangeable implementations</b><br/><i>same contract in → identical contract out</i>"]
        IMPL1["impl-primary · reference ✅"]
        IMPL2["impl-alt · planned ⏳"]
    end

    C2{{"◆ CONTRACT BOUNDARY ◆<br/><b>B → C · OUTPUT / READ MODEL</b><br/>CONTRACT_NAME<br/><b>vX.Y.Z · STATUS_GLYPH</b><br/>━━━━━━━━<br/>materialized in DATASTORE:<br/>TABLE_A · TABLE_B<br/>guarantees: ..."}}

    subgraph DOWN["TEAM C — owns CONSUMER"]
        direction TB
        CONS["CONSUMER"]
    end

    IMPL1 -. conforms to .-> NOTE
    IMPL2 -. conforms to .-> NOTE
    UP   ==> C1
    C1   ==> MID
    MID  ==> C2
    C2   ==> DOWN

    classDef contract fill:#fde68a,stroke:#b45309,stroke-width:4px,color:#3a2f00;
    classDef zone     fill:#f1f5f9,stroke:#94a3b8,color:#0f172a;
    classDef impl     fill:#ffffff,stroke:#cbd5e1,color:#334155;
    classDef refimpl  fill:#ffffff,stroke:#475569,stroke-width:2px,color:#1e293b;
    classDef note     fill:#f8fafc,stroke:#e2e8f0,color:#475569,font-style:italic;

    class C1,C2 contract;
    class UP,MID,DOWN zone;
    class IMPL2 impl;
    class IMPL1 refimpl;
    class NOTE,SRC,CONS note;

    linkStyle 0,1 stroke:#cbd5e1,stroke-width:1px;
    linkStyle 2,3,4,5 stroke:#b45309,stroke-width:4px;
```

## Configuration

| Setting | Default | Description |
|---|---|---|
| Orientation | `LR` | left→right reads as a value stream (Receive → Deliver) |
| Contract shape | `{{...}}` hexagon | reads as a gate/checkpoint, not a component |
| Contract color | `#fde68a` / `#b45309` | reserved gold; the only saturated color |
| `linkStyle` indices | count edges in source order | dashed conformance first, gold flow after |

> **Gotcha — `linkStyle` indices.** Edges are numbered by order of appearance in the source, across subgraph boundaries. Declare the dashed `conforms to` edges first so they are indices `0..k-1`, then the gold flow. Recount after adding/removing any edge.

## Trade-offs

| Pro | Con |
|---|---|
| Contracts unmistakably the hero | Hexagon labels get tall with many guarantees |
| Interchangeability shown structurally | More verbose than a plain pipeline |
| Status decoupled from color (stable visuals) | Requires a legend for first-time readers |

## Alternatives

| Alternative | When to prefer it |
|---|---|
| C4 model (Structurizr) | Formal, multi-level system documentation |
| Plain `flowchart` with edge labels | Throwaway sketch where contracts aren't the point |
| `sequenceDiagram` | The message is timing/ordering, not boundaries |

## See Also

- [`../index.md`](../index.md) — the seven principles
- [`../concepts/contract-first-visualization.md`](../concepts/contract-first-visualization.md) — the why
- [`../quick-reference.md`](../quick-reference.md) — legend + checklist

## Sources

- First-use: Sentinel README §1 architecture diagram, `feat/rust-otel-collector`, 2026-06-09
