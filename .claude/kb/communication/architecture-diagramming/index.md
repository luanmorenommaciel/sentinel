---
title: Architecture Diagramming & Communication
last_updated: 2026-06-09
confidence: 0.90
---

# Architecture Diagramming & Communication Knowledge Base

> **Purpose**: Communicate architecture so the *durable, decision-relevant assets* outrank the *incidental details* — in diagrams, READMEs, ADRs, and review decks. The default-but-not-universal asset is the **contract**; the safeguard is to **classify before you critique** (P0) so the framework never forces contract-primacy onto a diagram whose real subject is something else.
> **MCP Validated**: 2026-06-09 (first-party; distilled from the Sentinel Pod 2 README review, then hardened by a self-review that found the original draft over-fit to multi-team contract-bounded systems)
> **Sentinel context**: Born from the Pod 2 `feat/rust-otel-collector` diagram review, where the diagram over-emphasized `collector-rust` and under-represented the two versioned contracts. The **counter-case lives in the same repo**: ADR-0004 is a language bake-off where the *implementation choice* is the architecture — see [P0](#p0--classify-before-you-critique-gating) and the [contract-primacy safeguard](#the-contract-primacy-safeguard).

Tool- and project-agnostic. Mermaid is the worked example because Sentinel standardizes on it; every principle applies to any diagram (Excalidraw, C4, slides, whiteboard).

---

## How to read this KB

The framework is a **gate, then a ladder, then a catalogue**:

1. **P0 — gate.** Classify the artifact (diagram type · audience · intended claim · what's architecturally decisive). This decides *which* rubric applies and prevents false positives.
2. **P1–P6 — ladder.** The communication principles, applied through the lens P0 selected.
3. **P7 — catalogue.** The named anti-patterns to lint against.

The [`architecture-visualization-reviewer`](../../agents/communication/architecture-visualization-reviewer.md) agent and the [`/arch-review`](../../skills/arch-review/SKILL.md) skill execute exactly this order.

---

## The principles

Each has a **name**, an **explanation**, **how it applied to Sentinel**, and **how it generalizes**.

### P0 · Classify Before You Critique *(gating — added in v1)*

**Explanation.** Before any judgment, establish four things: (1) **diagram type** — flow/boundary, sequence, state, ER/data, deployment, dependency, or a C4 level; (2) **audience & altitude**; (3) the **intended one-sentence claim**; (4) **what is architecturally decisive here** — the contract, the implementation, the topology, the trust boundary, the timing? The rest of the framework is applied *through* these answers. If any is unknowable, escalate — do not guess. See [`concepts/diagram-type-rubrics.md`](concepts/diagram-type-rubrics.md).

**Applied to Sentinel.** The README diagram is a **boundary/flow** diagram for a **multi-team handoff**, so contract-primacy is correct there. ADR-0004's bake-off, by contrast, is **implementation-decisive** — classifying it first stops the framework from "fixing" a diagram that *should* feature the implementation.

**Generalizes.** P0 is the safeguard that makes the whole framework portable: it converts "contracts are the asset" from a hard-coded prior into a *conditional* applied only where it fits.

### P1 · The Load-Bearing Claim *(architecture communication)*

**Explanation.** Every artifact makes exactly one primary claim, extractable in ~15 seconds, at the audience's altitude (P0 supplies both). If the visible claim ≠ the intended claim, the artifact has failed before any detail is judged.

**Applied to Sentinel.** Visible claim was *"Pod 2 built a Rust collector."* Intended: *"two versioned contracts decouple three teams; the collector is one of N interchangeable implementations."*

**Generalizes.** Write the sentence the viewer should say back to you, then design the path of least cognitive resistance toward it.

### P2 · Salience Follows Value *(visual hierarchy)*

**Explanation.** The most decision-relevant element (per P0) carries the most visual weight. Two corollaries:
- **One Channel, One Meaning** — never let one channel (especially color) encode two variables. If color means "asset," it cannot also mean "build status."
- **Redundant Encoding / Never Rely on Color Alone** *(accessibility, added in v1)* — every meaning carried by color must *also* be carried by a second channel (shape, border weight, label, position). Required for color-blind readers, grayscale print, and projector washout. A legend is mandatory, not optional.

**Applied to Sentinel.** Color was encoding *build status* (green=done) on the least durable box. Fix: gold reserved for contracts; status moved to glyphs (✅/🔶/⏳); contracts also marked by *shape* (hexagon) and *border weight*, so the hierarchy survives in grayscale.

**Generalizes.** Audit every diagram for channel collisions and color-only encoding. The replaceable thing should never be the brightest thing — and "brightest" must never be the *only* signal.

### P3 · Contracts Are First-Class Nodes *(contract-first — now scoped)*

**Explanation.** Where a boundary/handoff is the subject (P0), promote interfaces from edge labels to **versioned nodes** (shape + color + version + status + guarantees). Corollary — **The Interface Is the Asset, the Implementation Is Disposable**. **Scope limit:** this principle is conditional, not universal — see the [contract-primacy safeguard](#the-contract-primacy-safeguard) and [`patterns/contract-gate-diagram.md` § When NOT to use](patterns/contract-gate-diagram.md#when-not-to-use).

**Applied to Sentinel.** `①②` edge labels → gold hexagon gates; the ClickHouse read model folded *into* the output-contract node (it is the materialization of the contract, not separate infra).

**Generalizes.** Any API/event/data contract on a team boundary should be a first-class object with a version — *when the diagram's job is to show the boundary*.

### P4 · The Boundary Taxonomy *(ownership + trust + network + consistency)*

**Explanation.** A boundary is most informative where *something changes hands*. But "boundary" is not one thing — diagrams routinely conflate distinct kinds, and the most dangerous one is usually invisible. Distinguish, and draw, the four (detail in [`concepts/boundary-types.md`](concepts/boundary-types.md)):

| Boundary | Crosses when… | Often missed because… |
|---|---|---|
| **Ownership** | accountability moves to another team | implied by subgraphs, not labeled |
| **Trust / security** | the threat model changes (authN/Z, tenant, network zone) | it rarely coincides with ownership, so it's omitted |
| **Network / deployment** | process / host / VPC / region changes | collapsed into logical flow |
| **Consistency / transaction** | atomicity or consistency guarantees end | invisible until an incident |

**One Box, One Owner** still holds for the ownership layer. **The trust boundary is a first-class, separate category** — never assume it tracks ownership.

**Applied to Sentinel.** Ownership seams are the Pod-to-Pod gates. The *trust* boundary is elsewhere and currently undrawn: the OTLP `:4317` receive edge is where untrusted/foreign telemetry enters (the reason `grpc_validation` defaults to `warn`) — a security boundary that does **not** sit on a Pod seam. A complete diagram would mark it distinctly.

**Generalizes.** Conway's law made visible for ownership; threat model made visible for trust. Most architecture diagrams show ownership and hide trust — flag the omission.

### P5 · Receive · Guarantee · Deliver *(architecture storytelling)*

**Explanation.** Narrate every component as a value stream: what it **receives**, what it **guarantees** (and explicitly does *not*), what it **delivers**, and where **ownership/trust transfers**.

**Applied to Sentinel.** Input gate (receive) → Pod 2 zone (process) → output gate listing guarantees + non-guarantees (deliver).

**Generalizes.** "What do you guarantee?" is the question that separates an implementation description from an architecture description.

### P6 · The Tells-vs-Should-Tell Audit *(review methodology)*

**Explanation.** State (1) the story it tells, (2) the story it should tell (given P0), (3) the **emphasis delta**, then prescribe the minimal change set. Rate with the rubric below.

**Severity:** **blocker** (visible claim ≠ intended, or wrong diagram type for the message, or a missing trust boundary that changes the reading) · **major** (a decision-relevant asset under-represented; color-only encoding) · **minor** (polish).

**Rating rule:**
- **REWORK** — P0 mismatch (wrong type/altitude) or P1 fails (wrong claim is visible).
- **REVISE** — claim lands but ≥1 blocker/major finding remains.
- **PASS** — claim lands, salience matches value, boundaries (incl. trust where relevant) are drawn, encoding is redundant, no major anti-pattern.

**Confidence basis (this domain).** Not MCP-agreement. Tag each finding **structural** (channel collision, edge-label contract, color-only encoding → high confidence, 0.9+) or **judgment** (altitude fit, "is this the right claim" → flagged as opinion, ≤0.8, defer to author intent).

**Applied to Sentinel.** "Tells: Rust-impl story. Should tell: contract story. Over-weighted: `collector-rust`. Under-weighted: contracts, read model." Verdict: REWORK.

**Generalizes.** Turns "I don't like this diagram" into an auditable, severity-rated findings table.

### P7 · The Visualization Anti-Pattern Catalogue

Full catalogue with tells + fixes in [`quick-reference.md`](quick-reference.md):

| # | Anti-pattern | One-line tell |
|---|---|---|
| A1 | **Implementation Centrism** | the replaceable component is the visual hero *(only a smell if P0 says the impl isn't the subject)* |
| A2 | **Status-Color Collision** | color encodes build status, colliding with semantic meaning |
| A3 | **Edge-Label Contracts** | interfaces relegated to thin arrow text *(boundary diagrams only)* |
| A4 | **Storage-Box Orphan** | a datastore on a team seam drawn as neutral infra |
| A5 | **Ownership Soup** | no single owner per region |
| A6 | **Hero Box** | brightest because it's *done*, not because it *matters* |
| A7 | **Drift Diagram** | contradicts README / ADR / code (versions, statuses, names) |
| A8 | **Diagram-Type Mismatch** *(v1)* | wrong rubric applied, or wrong diagram type for the message (e.g. a flowchart where a sequence diagram is needed) |
| A9 | **Altitude Smear** *(v1)* | C4 levels mixed in one diagram (context + code together) |
| A10 | **Color-Only Encoding** *(v1)* | meaning carried by color alone; dies in grayscale / for color-blind readers |
| A11 | **Invisible Trust Boundary** *(v1)* | a security/trust crossing is undrawn or hidden inside an ownership zone |

---

## The contract-primacy safeguard

**Contract-first (P3) is the default for boundary/handoff diagrams — not a universal law.** When P0 determines the artifact's subject *is* the implementation choice, the implementation is legitimately the hero and contracts become context.

Apply this safeguard when the diagram supports any of:

- a **language/runtime/framework selection** (Sentinel ADR-0004: Rust vs Go — GC pauses, RSS, p99 are the point);
- a **build-vs-buy / adopt-vs-roll-your-own** decision (ADR-0005: hand-roll vs OTel-native schema);
- a **performance/scalability** argument where the mechanism is decisive;
- an **internal-module / threading / class** view whose audience is the implementers.

In those cases: do **not** flag A1 Implementation Centrism; do **not** demand gold contract gates; *do* still apply P1 (one claim), P2 (salience + redundant encoding), and P6 (the audit). The reviewer must establish "what's decisive" in P0 and state it, so contract-primacy is never applied by reflex.

---

## Quick Navigation

### Concepts (< 150 lines each)

| File | Purpose |
|------|---------|
| [concepts/diagram-type-rubrics.md](concepts/diagram-type-rubrics.md) | **The P0 gate** — per-type rubric: what's the asset, which principles/anti-patterns apply, whether contract-gate fits |
| [concepts/boundary-types.md](concepts/boundary-types.md) | **P4 taxonomy** — ownership vs trust/security vs network vs consistency, and how to draw each |
| [concepts/visual-hierarchy.md](concepts/visual-hierarchy.md) | Perceptual channels, channel-collision, status-vs-value, redundant encoding |
| [concepts/contract-first-visualization.md](concepts/contract-first-visualization.md) | Why interfaces outlive implementations — and when they don't |

### Patterns (< 200 lines each)

| File | Purpose |
|------|---------|
| [patterns/contract-gate-diagram.md](patterns/contract-gate-diagram.md) | The reusable boundary-diagram Mermaid template — with an explicit "When NOT to use" |

### Quick Reference

- [quick-reference.md](quick-reference.md) — classify-first checklist, legend (incl. accessibility), boundary taxonomy, severity rubric, anti-pattern catalogue.

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Classify-before-critique (P0)** | Establish type/audience/claim/decisive-asset before judging |
| **Contract gate** | A boundary interface promoted to a versioned, standout node — *for boundary diagrams* |
| **Boundary taxonomy** | Ownership · trust/security · network · consistency — drawn distinctly |
| **Redundant encoding** | Every color meaning also carried by shape/border/label |
| **Emphasis delta** | The gap between visual weight given and decision-relevance held |
| **Contract-primacy safeguard** | Relax P3 when the implementation choice is the architecture |

---

## Sentinel Touch Points

| Pod / Component | How this KB applies |
|---|---|
| README §1 diagram | Boundary diagram → contract gates + ownership zones + (todo) trust boundary at `:4317` |
| ADR-0004 (language) | **Implementation-decisive** → contract-primacy safeguard; impl is the hero |
| ADR-0005/0006 | Schema-as-contract; fold storage into the output gate |
| Pod 1↔2, 2↔3 handoffs | Receive·Guarantee·Deliver; trust boundary at the foreign-OTLP edge |

---

## Known limitations & roadmap (v1)

**v1 scope.** Strong on boundary/flow and C4-container diagrams for multi-team systems. The P0 gate now *routes* other diagram types to the right rubric, but the per-type rubrics in [`diagram-type-rubrics.md`](concepts/diagram-type-rubrics.md) are concise, not exhaustive.

**Empirical grounding.** Derived from one case (Sentinel Pod 2) + one self-review. The 15-second test is *simulated* by the agent, not measured against real viewers. Treat **judgment**-tagged findings as opinion.

**Roadmap (ranked by leverage):**
1. Deepen per-type rubrics (sequence, state, ER, deployment, dependency) — each toward its own concept file.
2. **Drift automation** — promote A7 from manual eyeballing to a CI / pre-commit gate diffing diagram labels against the contract/ADR registry.
3. Accessibility lint — automated grayscale + palette + redundant-encoding check.
4. Calibration corpus + scoring model — replace simulated 15-second test; address the N=1 grounding.
5. De-Sentinel-ize examples (parametrize Pod/Watcher/glossary) for clean cross-repo port.
6. Generate↔review loop with `/readme-maker`; collaboration protocol with `adaptive-explainer` (author vs critique).

---

## Agent Usage

| Agent | Primary Files | Use Case |
|-------|---------------|----------|
| architecture-visualization-reviewer | this index + quick-reference.md + concepts/ | Reviewing READMEs/ADRs/diagrams/contracts via P0→P7 |
| adaptive-explainer | concepts/ | Authoring at a target altitude (P1) — the complement, not a duplicate |

---

## See also

- [`.claude/CLAUDE.md`](../../CLAUDE.md) — project context
- [`.claude/kb/README.md`](../README.md) — KB index
- [`.claude/agents/communication/architecture-visualization-reviewer.md`](../../agents/communication/architecture-visualization-reviewer.md) — the reviewer agent
- [`.claude/skills/arch-review/SKILL.md`](../../skills/arch-review/SKILL.md) — the review skill
- Related KBs: `contracts/`, `process/crew-b-wow/`
- Related ADRs: ADR-0004 (the contract-primacy counter-case), ADR-0005, ADR-0006
