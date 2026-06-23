# Contract-First Visualization

> **Purpose**: Draw the architecture so interfaces (the durable assets) outrank implementations (the disposable details).
> **Confidence**: 0.90 (first-party; distilled from the Sentinel Pod 2 review)
> **Added**: 2026-06-09

## The premise: interfaces outlive implementations

In a multi-team or multi-language system, the **contract is the architecture**; the implementation is a detail behind it. Languages get swapped (Rust ↔ Go), services get rewritten, databases get migrated — but the *interface* is what every other team builds against, so it changes slowly and breaks expensively. A diagram that emphasizes the implementation is emphasizing the part most likely to be thrown away.

**The Interface Is the Asset, the Implementation Is Disposable.** Treat any box you could rewrite next quarter as low-salience; treat any contract another team depends on as high-salience.

## Contracts Are First-Class Nodes (P3)

The habitual mistake is rendering a contract as an **arrow label** (`→ v1.0.0 →`). That buries the most valuable artifact in the weakest channel (edge text). Instead, promote it to a **node**:

- Distinct **shape** (a hexagon / gate reads as a checkpoint, not a component).
- Standout **color** (the reserved "asset" color — see [visual-hierarchy](visual-hierarchy.md)).
- Explicit **version + status** in the label (`v1.0.0 · FROZEN`, `v1.0.0-rc.1 · build now`).
- The **guarantees** it makes, summarized (e.g. "5 keys always present; `''`=absent; Duration ns").

A reviewer should be able to point at a single object and say "that's the contract, it's at version X, team A owns it, team B consumes it."

## Fold storage/schema into the contract (kills A4)

A datastore that sits on a team boundary is not neutral infrastructure — it **is** the read contract, materialized. Drawing it as a separate cylinder off to the side (the **Storage-Box Orphan**, A4) hides that. Instead, render the schema/tables *inside* the output-contract node.

**Sentinel example.** The `otel_logs / otel_traces / otel_metrics` tables plus the `otel_metrics_1m` rolling-stats MV are the Pod 2 → Pod 3 read contract. In the fixed diagram they live inside the gold output gate, with the per-column guarantees listed — not as a blue "ClickHouse" box between two Pods.

## Show interchangeability explicitly

If multiple implementations sit behind one contract, *prove* it on the page: draw each implementation as a uniform pale box with a dashed **"conforms to"** edge into the single contract node. The visual message — "N implementations collapse to one output contract" — is the interchangeability claim made undeniable.

**Sentinel example.** `collector-rust` (reference), `collector-go` (bake-off), `collector-<lang>` (future) all conform to the same output contract. The diagram shows three boxes fanning into one gate, so swapping the language is visibly a no-op for Pod 3.

## The Receive · Guarantee · Deliver frame (P5)

For each boundary, the contract node should let a reader answer:

- **Receive** — what shape/version comes in (the upstream contract).
- **Guarantee** — what invariants the producer promises (and the explicit *non*-guarantees).
- **Deliver** — what shape/version goes out (the downstream contract).

Listing **non-guarantees** is a maturity signal — it tells consumers what *not* to couple to (e.g. "Map iteration order is not guaranteed").

## When this principle does NOT apply

Contract-first is the default for **boundary/handoff** diagrams — it is *not* universal. Per the [contract-primacy safeguard](../index.md#the-contract-primacy-safeguard), suppress it when P0 finds the diagram's subject *is* the implementation:

- language/runtime/framework selection (Sentinel ADR-0004: Rust vs Go);
- build-vs-buy / adopt-vs-roll (ADR-0005: hand-roll vs OTel-native schema);
- a performance argument where the mechanism is decisive;
- a module-internals / threading / class view for implementers.

In those cases the implementation is legitimately the hero, and flagging "Implementation Centrism" (A1) would be the false positive. The irony worth remembering: this KB's own origin repo contains ADR-0004, where the *implementation choice is the architecture* — proof that "the interface is the asset" is a strong default, not a law.

## Self-check

1. Can you point at the contract as a single object? If not → **A3 Edge-Label Contracts**.
2. Is a boundary datastore drawn as separate infra? → **A4 Storage-Box Orphan**.
3. Is the shipped implementation more salient than the contract? → **A1 / A6**.

## See Also

- [`../index.md`](../index.md) — the seven principles
- [`visual-hierarchy.md`](visual-hierarchy.md) — why contracts win the salience budget
- [`../patterns/contract-gate-diagram.md`](../patterns/contract-gate-diagram.md) — the reusable encoding
- Related ADR: ADR-0005 (schema-as-contract), ADR-0006 (optional-ID representation)

## Sources

- First-party: Sentinel Pod 2 README diagram review, 2026-06-09
- `contracts/pod2-pod3-read-contract.md` — the worked read-contract
