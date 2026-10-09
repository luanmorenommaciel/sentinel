# Boundary Types — ownership is not the only seam

> **Purpose**: Distinguish the four boundary kinds a diagram can show, so the most dangerous one (trust) isn't hidden inside the most obvious one (ownership).
> **Confidence**: 0.90 (first-party; added in v1)
> **Added**: 2026-06-09

## The premise

"Boundary" is overloaded. Architecture diagrams almost always draw **ownership** boundaries (team subgraphs) and almost always omit **trust** boundaries — yet in security-relevant systems the trust boundary is the most important line on the page. P4 of the framework requires treating these as **separate categories**, drawn distinctly.

## The four boundaries

| Boundary | Crosses when… | Why it matters | Typical render |
|---|---|---|---|
| **Ownership** | accountability moves to another team/Pod | who you page; where a contract is needed | labeled subgraph / swimlane |
| **Trust / security** | the threat model changes — authN/Z, tenant isolation, internet↔internal, validated↔unvalidated input | where attacks enter; where validation must happen | a distinct dashed/red perimeter line, *not* a team box |
| **Network / deployment** | process / host / container / VPC / region changes | latency, failure domains, partition tolerance | nested deployment nodes / zones |
| **Consistency / transaction** | atomicity or consistency guarantees end | where "it'll be eventually consistent" begins | aggregate/service ring; annotation |

## They do not coincide — that's the point

The classic mistake is assuming the trust boundary tracks the ownership boundary. It usually doesn't:

- A single team (one ownership zone) can straddle the internet-facing trust boundary.
- A contract boundary between two internal teams may carry **no** trust boundary (both trusted), while the *real* trust boundary is the external client edge owned by neither.

So a diagram that shows only ownership can hide exactly where untrusted input enters — anti-pattern **A11 Invisible Trust Boundary**.

## Drawing them without clutter

- Pick **one** boundary type as primary per diagram (P0 audience drives the choice); show others only if they change the reading.
- Use a **different channel** for each (ownership = subgraph fill; trust = a labeled perimeter line; network = nested nodes) — and label them, per the redundant-encoding rule.
- If two boundaries genuinely coincide, say so explicitly ("ownership = trust here") rather than letting the reader assume it.

## Sentinel application

- **Ownership:** the Pod-to-Pod gates (well drawn).
- **Trust:** the OTLP `:4317` receive edge is where **foreign / untrusted** telemetry enters — the reason `contract.grpc_validation` defaults to `warn` and file mode uses `strict`. This trust boundary sits *inside* Pod 2's ownership zone, not on a Pod seam, so an ownership-only diagram hides it. A complete README diagram would mark `:4317` with a distinct trust perimeter.
- **Consistency:** the `otel_metrics_1m` MV is eventually-merged (`AggregatingMergeTree`) — a consistency boundary Pod 3 must respect (re-aggregate on read). Worth annotating where Pod 3-facing diagrams are drawn.

## See Also

- [`../index.md`](../index.md) — P4 in the principle ladder
- [`diagram-type-rubrics.md`](diagram-type-rubrics.md) — deployment/infra diagrams center trust + network boundaries
- Related ADR: ADR-0006 (optional-ID `''` sentinel — a consistency/validation invariant)

## Sources

- First-party: Sentinel Pod 2 v1 self-review, 2026-06-09
- Threat-modeling trust-boundary convention (STRIDE / data-flow diagrams)
