# Architecture Diagramming Quick Reference

> Fast lookup. Principles in [index.md](index.md); the P0 gate in [concepts/diagram-type-rubrics.md](concepts/diagram-type-rubrics.md).

## Step 0 — classify before you critique (P0)

Answer all four, or escalate (don't guess):

1. **Type** — flow/boundary · sequence · state · ER/data · deployment · dependency · C4 level · status.
2. **Audience & altitude** — exec / reviewer / engineer.
3. **Intended claim** — the one sentence the viewer should leave with.
4. **What's decisive** — contract · implementation · topology · trust boundary · timing.

→ If "decisive = implementation," apply the **contract-primacy safeguard**: the impl may be the hero; do **not** flag A1. → If type ≠ flow/boundary, do **not** apply the contract-gate pattern.

## The 15-second test (P1)

Show it for 15s, take it away, ask "what's the main claim?" If the answer ≠ your intended claim, the hierarchy is wrong — not their attention.

## Color legend + accessibility (P2)

| Tier | Means | Color (primary) | **Redundant channel (required)** |
|---|---|---|---|
| Contract / boundary | the durable asset | gold `#fde68a` / `#b45309` 4px | **hexagon shape + thick border** |
| Ownership zone | the "who" | muted slate `#f1f5f9` | **subgraph label "owns X"** |
| Implementation | the "how, for now" | white `#ffffff` | small, uniform |
| Reference impl | today's realization | white | **dark outline** (not fill) |
| Status | done/WIP/planned | — | **glyph ✅ 🔶 ⏳** (never color) |

**One channel, one meaning. Never rely on color alone** — desaturate (grayscale test); if the hierarchy dies, that's **A10 Color-Only Encoding**. **Legend mandatory.**

## Boundary taxonomy (P4) — draw them distinctly

| Boundary | Crosses when… | Render |
|---|---|---|
| Ownership | accountability → another team | labeled subgraph |
| **Trust / security** | threat model changes (authN/Z, tenant, untrusted input) | **distinct perimeter line, not a team box** |
| Network / deployment | process/host/VPC/region changes | nested zones |
| Consistency | atomicity/consistency guarantees end | aggregate ring / annotation |

Trust ≠ ownership. An ownership-only diagram that hides where untrusted input enters is **A11 Invisible Trust Boundary**.

## Severity + verdict (P6)

- **REWORK** — P0 mismatch (wrong type/altitude) or wrong claim is visible (P1 fails).
- **REVISE** — claim lands but ≥1 blocker/major remains.
- **PASS** — claim lands, salience matches value, boundaries (incl. trust) drawn, encoding redundant, no major anti-pattern.

Severity: **blocker** (wrong claim / wrong type / missing trust boundary that changes the reading) · **major** (decision-relevant asset under-weighted; color-only encoding) · **minor** (polish). Tag each finding **structural** (high confidence) or **judgment** (opinion; defer to author).

## Anti-pattern catalogue (P7)

| # | Anti-pattern | Tell | Fix |
|---|---|---|---|
| A1 | Implementation Centrism | replaceable component is the hero *(only if impl isn't the subject)* | demote impls; or invoke the safeguard |
| A2 | Status-Color Collision | color = build status | move status to glyphs *(except status/roadmap diagrams)* |
| A3 | Edge-Label Contracts | interface is arrow text | promote to versioned node *(boundary diagrams only)* |
| A4 | Storage-Box Orphan | DB on a seam = neutral infra | fold schema into the output contract node |
| A5 | Ownership Soup | no clear owner per region | label each zone `owns <X>` |
| A6 | Hero Box | brightest = "done", not "matters" | recolor by value, not progress |
| A7 | Drift Diagram | contradicts README/ADR/code | re-sync; single source of truth |
| A8 | Diagram-Type Mismatch | wrong rubric / wrong type for the message | reclassify (P0); switch diagram type |
| A9 | Altitude Smear | C4 levels mixed in one diagram | split per level |
| A10 | Color-Only Encoding | meaning carried by color alone | add shape/border/label redundancy |
| A11 | Invisible Trust Boundary | trust crossing undrawn / inside an ownership box | draw a distinct trust perimeter |

## Contract-gate pattern — do NOT use when…

implementation is the subject (bake-off/perf) · type is non-boundary (sequence/state/ER/dependency) · the decisive boundary is trust/network · single-owner module · exec one-liner. See [pattern § When NOT to use](patterns/contract-gate-diagram.md#when-not-to-use).

## Sentinel-specific gotchas

| Context | Gotcha | Workaround |
|---|---|---|
| `collector-rust` | tempting to highlight (shipped) | "reference impl" by outline only |
| ADR-0004 diagram | impl-decisive → contract-primacy safeguard | feature the impl; suppress A1 |
| ClickHouse tables | read as storage | fold into the Pod 2→Pod 3 gate (boundary view) |
| `:4317` ingest | trust boundary hidden in Pod 2's zone | draw a distinct trust perimeter (A11) |
| Mermaid status colors | green-for-done collides with gold | glyphs ✅/🔶/⏳; keep classDefs for value |

## Related

| Topic | Path |
|---|---|
| The P0 gate | `concepts/diagram-type-rubrics.md` |
| Boundary taxonomy | `concepts/boundary-types.md` |
| Hierarchy + accessibility | `concepts/visual-hierarchy.md` |
| The reusable template | `patterns/contract-gate-diagram.md` |
