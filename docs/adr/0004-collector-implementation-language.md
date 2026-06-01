# ADR-0004 · Collector Implementation Language

| Field | Value |
|---|---|
| Status | **Proposed** — discussion open in `#crew-b` |
| Date | 2026-06-01 |
| Owners | Pod 2 (Collector) — Alex Botelho, Ruan Pomponet, Victor Urquiola |
| Proposer | Victor Urquiola |
| Supersedes | — |
| Related | Sync 02 (2026-05-26) decisions D1, D4; action items A6, A7 |
| ADR-001 (blast radius), ADR-002 (baseline), ADR-003 (primary user) | independent |

> Spirit of this ADR: a **strong opinion, weakly defended.** It exists to put Rust on the bake-off table that A7 already scheduled. If the bake-off picks Go, that's a good outcome — what we want is a *decided* trade-off, not a default.

## Context

Sync 02 locked the Phase 1 data flow:

```text
Generator → OTel Collector → ClickStack (ClickHouse)
```

The Collector sits in the middle and **owns protocol conversion**: it receives OTLP gRPC on `:4317`, validates contracts, transforms (if needed), and exports to ClickHouse. It is the canonical ingestion path; direct generator→ClickHouse writes were explicitly rejected (Sync 02 D6) so the Collector becomes the swap point when we later replace the synthetic generator with a real cloud connection.

**Sync 02 left the implementation language undecided** (A7): Python ruled out for performance; Go strongly favored; Java floated jokingly; *"build the three and stress-test if time allows"* was the closing line.

This ADR makes the case for **Rust** being part of "the three" — and not as a token alternative, but as the language with the best long-tail fit for what the Collector actually does.

## What the Collector actually does (informs language choice)

1. **OTLP gRPC server** on `:4317` — high-fanout, many small messages, latency-sensitive.
2. **Protocol conversion** — OTLP → ClickHouse insert format (JSON / native binary / Arrow).
3. **Batching + backpressure** — buffer events, flush on size/time thresholds, push back when ClickHouse is slow.
4. **ClickHouse client** — async, connection-pooled, ideally Native protocol (not HTTP) for throughput.
5. **Contract validation at boundary** — schema enforcement on receive, mirror at export.
6. **Observability of itself** — emit its own OTel signals (meta-telemetry) so Sentinel can watch Sentinel.

All six are I/O-heavy, concurrency-heavy, allocation-sensitive. This is the workload class where Rust's zero-cost abstractions and Go's mature OTel ecosystem genuinely compete head-to-head — and where Python is correctly ruled out.

## Decision

**Propose Rust as the Collector implementation language, with a time-boxed bake-off against Go.**

Concretely:

- Build the **same minimum-viable Collector** (OTLP gRPC receive → ClickHouse export, no transforms) in both Rust and Go, ~1 week each.
- Stress-test on the shared 8 GB VM: throughput (events/s sustained), p99 latency, RSS at steady state, container image size, cold-start time.
- **Decision criteria** (in priority order):
  1. Pod 2 team velocity (we ship this, we maintain it)
  2. p99 latency under realistic generator load
  3. Memory footprint at ClickHouse-saturating throughput
  4. Ecosystem maturity for OTLP + ClickHouse
  5. Container image size (matters for cold start in CI / preview envs)
- Pick the winner at end of Sprint 2.

## Options considered

### Option A — Go (current default)

**Pros**
- Upstream OTel Collector itself is Go → reference implementations everywhere, blessed `clickhouseexporter`, every receiver/processor/exporter has a Go example to copy from.
- Largest OTel community by far. Stack Overflow, GitHub issues, blog posts — all Go-first.
- Goroutines + channels are a near-perfect fit for the receiver→batcher→exporter pipeline.
- Compiles fast, simple deployment (single static binary), low ramp-up for engineers new to it.
- `clickhouse-go` is mature, supports the Native protocol.

**Cons**
- GC pauses are real. At ClickHouse-saturating throughput, p99 latency tail is the first thing to fail.
- Higher RSS than Rust for the same workload (typically 2-3× in steady state for high-fanout I/O services).
- "It works because everyone else does it" is a weaker argument than it sounds — we lose the chance to learn the language that pays off when scaling out.

### Option B — Rust (this proposal)

**Pros**
- Zero GC. p99 latency stays flat as p50 scales. Critical when the Collector is in the hot path of every signal Sentinel ever sees.
- 2-3× lower RSS at saturation → more headroom on the shared 8 GB VM and on every astronaut's laptop running the full stack locally.
- `opentelemetry-rust` reached 1.0 in 2024 ([opentelemetry.io/docs/languages/rust](https://opentelemetry.io/docs/languages/rust/)) — past the "moving target" era.
- `tonic` (gRPC) + `tokio` (async runtime) are the same primitives Cloudflare, Discord, AWS use for their highest-throughput services. Battle-tested at scales we'll never reach.
- `clickhouse-rs` / `klickhouse` support Native protocol; ClickHouse itself is Rust-adjacent in spirit (C++ but the ecosystem leans systems-language).
- Sentinel ships in containers — Rust images are 5-20 MB scratch images vs Go's 15-50 MB. Doesn't matter at idle, matters at fleet scale and cold-start time.
- **Learning lever.** Per the Commander's notes (Sync 01): *"engineers who got reps in this way of working will be the ones companies fight to hire."* Same logic for the language: Rust + OTel in 2026 is a scarce skill set.

**Cons**
- Smaller OTel community than Go → fewer drop-in receivers/processors/exporters. We may have to write what Go imports.
- Steeper ramp-up for the team. Borrow checker, async lifetimes, `Pin`, `Send + Sync` bounds — these are real time costs in Week 1-2.
- Longer compile times (mitigated by `cargo check` workflows and incremental builds, but real on CI).
- `opentelemetry-rust` is 1.0 stable but the periphery (some exporters, semantic conventions crates) still moves.
- Hiring substitution risk: if Pod 2 changes hands, the next Astronauta needs Rust.

### Option C — Python (rejected at Sync 02)

Out per Sync 02 D6 + transcript: "Python is too slow for the Collector." Keeping here for the record. Python remains viable for the Generator, where dev velocity beats raw throughput.

### Option D — Hybrid (not recommended)

Rust core + Python plug-ins via PyO3. Initially attractive for "Rust speed, Python flexibility," but adds two-language complexity to a single component for no clear ingestion-layer win. The plug-in story belongs in the Watcher fleet (Phase 2), not the Collector.

## Trade-off summary

| Criterion | Go | Rust | Weight |
|---|---|---|---|
| Time-to-first-event-ingested | 🟢 days | 🟡 1–2 weeks | High in Sprint 1 |
| p99 latency at saturation | 🟡 GC tail | 🟢 flat | High at scale |
| RSS at saturation | 🟡 higher | 🟢 lower | Medium (shared VM constraint) |
| OTel ecosystem coverage | 🟢 huge | 🟡 growing | Medium |
| ClickHouse client maturity | 🟢 `clickhouse-go` | 🟢 `clickhouse-rs` | Equal |
| Team velocity (Pod 2 today) | 🟢 known | 🟡 ramp-up | High in Sprint 1, low long-term |
| Hiring / learning lever | 🟡 commodity | 🟢 differentiated | Per Commander framing: high |
| Container image size | 🟡 15–50 MB | 🟢 5–20 MB scratch | Low |
| Long-tail maintenance | 🟡 GC tuning | 🟢 deterministic | Medium |

**Net read:** Go wins Sprint 1. Rust wins everything past Sprint 4 *if* Pod 2 absorbs the ramp-up cost early.

## Why we shouldn't just default to Go

Two reasons that aren't about Rust:

1. **The Commander's frame.** Sync 01 was explicit: *"Tool freedom on input, rigor on output."* That frame applies to LLMs in this ADR (and we get it from the spec), but the same logic applies to languages — we're not here to ship the obvious thing. We're here to ship the *defensible* thing.
2. **Phase 2 will dominate.** Sync 02 said Phase 2 (Crew AI / Watcher fleet) will consume far more time than Phase 1. If the Collector is built right *once*, it disappears as a concern. The case for paying a 1-2 week ramp cost in Sprint 1 to never revisit Collector perf again is exactly the bet Sentinel's architecture is making everywhere else.

## What changes if we pick Rust

- **Pod 2 ramp-up week.** First 5 days are explicit Rust onboarding (`rustlings`, `tokio` async basics, `tonic` worked example) — *not* feature work. This goes on the Sprint 1 backlog as a learning slice, with a recoverable exit (we know what we'd cut if we fall behind).
- **CI gates change.** Replace `ruff`/`mypy` for the Collector with `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test`. The 7-gate spec (Sync 01 — ruff, mypy, pytest, bandit, markdownlint, CodeRabbit, Docker) needs a per-language profile. The Generator stays Python; the Collector goes Rust.
- **Docker image strategy.** Multi-stage build, distroless or scratch final image. Faster cold-start in CI.
- **Attribution stays the same.** `Co-Authored-By: Claude` trailers, signed commits, 2 approvals.

## What changes if we pick Go (and Rust loses the bake-off)

- We adopt the upstream OTel Collector binary + a custom `clickhouseexporter` config rather than building from scratch. Saves 2-4 weeks.
- This ADR closes as `Superseded by ADR-0005 · Collector: upstream OTel Collector + ClickHouse exporter`.

## Risks

- **Ramp-up overrun.** If Pod 2 doesn't have a working Rust OTLP receiver by end of Sprint 2, we cut and go to Go. Track via a single hard gate: *"does it accept an OTLP gRPC payload on :4317 and write a single span to ClickHouse?"* — if no by Day 14, switch.
- **Ecosystem gaps.** A receiver/processor we need in Phase 2 may not exist in Rust. Mitigation: the Collector boundary is contractual (Sync 02 D8) — we can always front a Rust core with a Go sidecar for one component without breaking the contract.
- **Team velocity vs cohort optics.** Other Crews ship Go/Python. Crew B shipping Rust will look slower in Week 1. Communicate the bet up-front; the Commander's frame supports it.

## Consequences

- A `services/collector-rust/` scaffold exists in the repo (this PR).
- A parallel `services/collector-go/` scaffold should be opened by Pod 2 in a sibling PR so the bake-off is symmetric.
- ADR-005 will follow with the bake-off results and the *accepted* language choice. This ADR closes as either *Accepted* (Rust wins) or *Rejected* (Go wins) at that point.

## Next steps

1. **PR review** — Pod 2 + Captain + Commander discuss in `#crew-b` and the PR thread.
2. If accepted as a bake-off plan: open `feat/go-otel-collector` with a symmetric Go scaffold.
3. Add 5-day Rust ramp-up tasks to Sprint 1 backlog (Captain owns).
4. Define the bake-off harness (shared load generator, same VM, same metrics) — likely an ADR-0006.
5. Bake-off runs Sprint 1 Week 2 → Sprint 2 Week 1. Decision at Sync 04.

## References

- Spec: `sentinel.pdf` — *6 Watcher Crews, 3-tier detection, One mission.*
- Sync 02 (2026-05-26) decisions D1, D4, D6; action items A6, A7
- `opentelemetry-rust` — <https://github.com/open-telemetry/opentelemetry-rust>
- `opentelemetry-collector` (Go upstream) — <https://github.com/open-telemetry/opentelemetry-collector>
- `tonic` (Rust gRPC) — <https://github.com/hyperium/tonic>
- `clickhouse-rs` — <https://github.com/suharev7/clickhouse-rs>
- `klickhouse` (alternative ClickHouse Rust client) — <https://github.com/Protryon/klickhouse>
- Commander framing — `bem-vindos.md` ("strong opinions, weakly defended") + Sync 01 *Why we're here* ("AI-Native, not AI-augmented")

---

*Companion research: `docs/research/rust-otel-collector.md` · Skeleton: `services/collector-rust/`*
