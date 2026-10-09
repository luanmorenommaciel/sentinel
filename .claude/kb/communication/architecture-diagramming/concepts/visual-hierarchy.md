# Visual Hierarchy for Architecture Diagrams

> **Purpose**: Make the most architecturally valuable element the most perceptually salient — and stop status from stealing the color channel.
> **Confidence**: 0.90 (first-party; distilled from the Sentinel Pod 2 review)
> **Added**: 2026-06-09

## The perceptual channels

A diagram communicates through a fixed set of channels. Each has a finite "salience budget":

| Channel | Strong signal | Weak signal |
|---|---|---|
| **Color saturation** | bright, warm, high-contrast fill | muted, cool, low-contrast |
| **Border weight** | thick (3–4px), dark | thin (1px), pale |
| **Size** | large node | small node |
| **Shape** | distinctive (hexagon, gate) | default (rectangle) |
| **Position** | center, on a seam, top-left | periphery |
| **Text weight** | bold, larger | regular |

The eye lands first on whatever wins the *most* channels. Architecture communication is the discipline of spending that budget on the elements that matter most.

## The core rule: Salience Follows Value (P2)

Rank the elements by **architectural durability and blast radius**, then spend salience in that order. In most multi-team systems the ranking is:

1. **Contracts / boundaries** — outlive every implementation; a break here ripples across teams.
2. **Ownership zones** — who is accountable; changes rarely.
3. **Implementations** — replaceable by design; change often.
4. **Build status** — changes weekly; lowest durability.

If your salience order doesn't match your value order, you have a hierarchy bug.

## One Channel, One Meaning

The most common failure is **channel overloading**: one channel encoding two unrelated variables. The classic is **color = build status** (green=done, yellow=WIP). The moment you do that, color can no longer mean "this is the asset" — and since color is the strongest channel, you've spent your biggest budget on the *least durable* variable (status).

**Fix:** assign each channel exactly one meaning and write it in a legend.

- Color → value tier (contract / zone / implementation).
- Glyph or text → status (✅ done / 🔶 RC / ⏳ planned).
- Shape → role (hexagon = contract gate, rectangle = component).
- Border weight → "is this the current reference?" (outline, not fill).

Now status can change every sprint without ever recoloring the architecture.

## Redundant Encoding — never rely on color alone *(accessibility)*

Color is the strongest channel and the **least reliable**: ~8% of men are red-green color-blind, diagrams get printed in grayscale, and projectors wash out saturation. So every meaning carried by color must *also* be carried by a second channel:

| Meaning | Color (primary) | Redundant channel (required) |
|---|---|---|
| Contract / asset | gold fill | **shape** (hexagon) + **thick border** |
| Ownership zone | slate fill | **subgraph label** ("owns X") |
| Reference impl | — | **border weight** (outline), not fill |
| Status | — | **glyph** ✅/🔶/⏳ (text, never color) |

**The grayscale test:** screenshot the diagram, desaturate it, and confirm the hierarchy still reads. If the only thing distinguishing the contract from a component was its color, you have **A10 Color-Only Encoding**. A **legend is mandatory**, not optional — it states each channel's single meaning so the encoding is self-documenting.

The Sentinel contract-gate pattern is grayscale-safe *by construction*: contracts are hexagons with 4px borders, so they remain the most prominent element even with all color removed.

## Worked example — the Sentinel inversion

| Element | Before (broken) | After (fixed) |
|---|---|---|
| `collector-rust` | bright green fill (won color + status) | white fill, dark outline only |
| Contracts | thin edge labels `①②` | gold hexagon gates, 4px border, bold |
| ClickHouse | neutral blue orphan box | folded into the gold output gate |
| Pod zones | 4 prominent boxes | muted slate containers, owner-labeled |
| Status | encoded in fill color | ✅/🔶/⏳ glyphs |

The before-diagram answered "what did Pod 2 build?" The after-diagram answers "how are the teams decoupled?" — same components, redistributed salience.

## How to self-check

1. Squint at the diagram (or shrink to thumbnail). What's still visible is what you've emphasized.
2. If the brightest thing is a *replaceable* box, you have **A6 Hero Box** / **A1 Implementation Centrism**.
3. If you can't state each channel's single meaning, you have a channel collision (**A2**).

## See Also

- [`../index.md`](../index.md) — the seven principles
- [`contract-first-visualization.md`](contract-first-visualization.md) — why contracts top the value ranking
- [`../patterns/contract-gate-diagram.md`](../patterns/contract-gate-diagram.md) — the pattern that encodes this hierarchy

## Sources

- First-party: Sentinel Pod 2 `feat/rust-otel-collector` README diagram review, 2026-06-09
- Tufte, *The Visual Display of Quantitative Information* (data-ink / salience budget)
