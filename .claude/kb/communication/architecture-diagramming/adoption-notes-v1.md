# Architecture-Review Framework — v1 Adoption Notes

> **Status:** Stabilized (v1) · 2026-06-09
> **Baseline assessment of record:** the `/arch-review README.md` audit (REVISE verdict) is the official baseline for Sentinel's README. The README is intentionally **left unchanged** for the upcoming project review; the audit documents the gap without acting on it.
> **Stance going forward:** stop refining. The next step is *use*, not improvement. Reopen only when real-world usage on a new project exposes a gap the framework misses or mis-fires on.

---

## 1. What it was created to solve

Architecture artifacts (diagrams, READMEs, ADRs, decks) habitually **over-emphasize the implementation that was just built and under-emphasize the contracts, boundaries, and ownership that are the durable product.** The Sentinel Pod 2 README showed this exactly: a Rust collector painted as the hero, two versioned contracts demoted to arrow labels. The framework turns the ad-hoc review that caught this into a **repeatable, severity-rated, project-agnostic capability** — so the same judgment runs the same way every time, by anyone, on any repo.

## 2. Lessons from the Sentinel case study

- **Color was the bug.** Encoding *build status* in color (green = done) spent the strongest perceptual channel on the least durable variable, leaving no channel for "this is the contract." → *One channel, one meaning.*
- **Contracts must be nodes, not edges.** The most valuable, longest-lived assets were the least visible thing on the page. → P3.
- **The framework's own origin repo disproved its first draft.** ADR-0004 (the Rust-vs-Go bake-off) is *implementation-decisive* — there the implementation legitimately is the architecture. This forced the **contract-primacy safeguard** and the **P0 classify-before-critique gate**: contract-first is a default for boundary diagrams, not a law.
- **The dangerous boundary is usually invisible.** The `:4317` trust boundary (where untrusted OTLP enters) sat inside Pod 2's ownership zone and was undrawn. → the boundary taxonomy (ownership ≠ trust ≠ network ≠ consistency).
- **A self-review beat the manual review.** v1 reproduced every original finding *and* surfaced three the human pass missed (A11 trust boundary, A10 legend, A4 unlabeled storage read) — while its safeguards correctly suppressed false positives. Calibration improved too: REWORK → REVISE.

## 3. When to use it

- Before an architecture- or project-review presentation.
- When a diagram, README, ADR, or architecture doc is **added or materially changed**.
- When a **contract or trust boundary** is being drawn or described.
- When you need to answer "does this communicate the right thing / at the right altitude?"
- As a CI/PR check on architecture surfaces (future roadmap item — drift automation).

## 4. When NOT to use it

- To decide whether the architecture is **correct** (that's `the-planner` / a domain SME).
- To **author** a README or explanation from scratch (that's `/readme-maker` / `adaptive-explainer`).
- To review **code** (that's `/code-review`).
- On an **implementation-decisive** artifact expecting it to demand contracts — it won't, by design (the safeguard). That's correct behavior, not a limitation.
- As a style-only linter — it judges *communication of architecture*, not prose polish.

## 5. Known limitations & roadmap

**Limits (v1):** Strongest on boundary/flow + C4-container diagrams for multi-team systems. Per-type rubrics for sequence/state/ER/deployment/dependency are concise, not exhaustive. Empirically grounded on **N=1 case + one self-review**; the 15-second test is *simulated*, not measured — treat `judgment`-tagged findings as opinion.

**Roadmap (by leverage, do only if real use demands it):**
1. Deepen per-type rubrics (one concept file each).
2. **Drift automation** — promote A7 from manual eyeballing to a CI / pre-commit gate diffing diagram labels vs the contract/ADR registry.
3. Automated accessibility lint (grayscale + palette + redundant-encoding).
4. Calibration corpus + scoring model (retire the simulated 15-second test; address N=1).
5. De-Sentinel-ize examples (parametrize Pod/Watcher/glossary for clean cross-repo port).

## 6. How it relates to the neighbouring agents/skills

The four form a **plan → author → review** loop. Each owns a distinct verb; none duplicates another.

| Capability | Verb | Owns | Hands off to |
|---|---|---|---|
| **the-planner** | *decide / sequence* | architecture **correctness** & strategy, ADR drafting, multi-step plans | author tools, once a decision is made |
| **/readme-maker** | *generate* | producing the README **artifact** (via codebase-explorer + code-documenter) | the reviewer, to audit the result |
| **adaptive-explainer** | *author for an audience* | calibrated **explanations** (altitude, analogy, Mermaid) | the reviewer, to critique what it wrote |
| **architecture-visualization-reviewer** | *critique* | how architecture is **communicated** (P0→P7); findings, not edits | back to author/planner with a change set |

**The two easy-to-confuse pairs:**
- **reviewer vs adaptive-explainer** — *critique vs author.* The explainer writes the diagram/doc at an altitude; the reviewer judges whether it lands. They never do both in one pass — the reviewer emits findings; the explainer (or you) acts on them.
- **reviewer vs the-planner** — *communication vs correctness.* The reviewer asks "is the right claim visible?"; the planner asks "is the claim true / is this the right design?" A reviewer finding that "the decision looks wrong" is escalated to the-planner, not resolved in-diagram.

Typical flow: `the-planner` frames a decision → `/readme-maker` or `adaptive-explainer` produces the artifact → `architecture-visualization-reviewer` (`/arch-review`) audits it → author applies the change set. The review is the loop's quality gate, run before the artifact goes outward.

---

## See also

- [`index.md`](index.md) — the P0→P7 framework + the contract-primacy safeguard
- [`concepts/diagram-type-rubrics.md`](concepts/diagram-type-rubrics.md) — the P0 gate
- [`concepts/boundary-types.md`](concepts/boundary-types.md) — the boundary taxonomy
- [`../../../agents/communication/architecture-visualization-reviewer.md`](../../../agents/communication/architecture-visualization-reviewer.md)
- [`../../../skills/arch-review/SKILL.md`](../../../skills/arch-review/SKILL.md)
