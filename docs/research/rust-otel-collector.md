# Research Brief — Rust for the Sentinel OTel Collector

> Companion to [ADR-0004](../adr/0004-collector-implementation-language.md). This is the receipts.

## Question

Given Sync 02's locked architecture (Generator → OTel Collector → ClickHouse over OTLP gRPC `:4317`) and Pod 2's mandate (A6, A7) to build/configure the Collector and pick its language, **can Rust deliver the Collector that Phase 2 actually needs**, without sinking Sprint 1?

## TL;DR

- **Yes, technically.** The Rust OTel ecosystem reached 1.0 in 2024. `opentelemetry-rust` + `tonic` + a ClickHouse Native-protocol client is a complete, battle-tested toolchain.
- **Maybe, organizationally.** A 5-day Pod 2 ramp-up is the real cost. If absorbed in Sprint 1 alongside the spec/ADR work (which is non-coding per Sync 01), the cost amortizes to near-zero.
- **The Go path is a known-good fallback** — building the *same* Collector in both languages over 1 week each (A7's "build the three and stress-test") is the disciplined move.

## What the Rust OTel ecosystem looks like in 2026

### `opentelemetry-rust` — the SDK

- Repo: <https://github.com/open-telemetry/opentelemetry-rust>
- License: Apache-2.0
- v1.0 (stable API contract) cut in 2024
- Maintained by the official OpenTelemetry organization
- Surface area: traces, metrics, logs (all three signals Sentinel needs)
- Exporters: OTLP (gRPC + HTTP), stdout, Jaeger, Zipkin, Prometheus
- Async-first, integrates with `tokio` (the de-facto async runtime)

### `tonic` — gRPC

- Repo: <https://github.com/hyperium/tonic>
- Owned by Hyper (the project that powers most production Rust HTTP)
- Battle-tested at Discord, Cloudflare, AWS
- Generates Rust types from `.proto` definitions via `prost`
- OTLP `.proto` files are the same spec across languages — drop-in compatible with any OTLP source (the Generator, real GCP/Azure/AWS, future replays)

### `tokio` — async runtime

- Repo: <https://github.com/tokio-rs/tokio>
- Industry standard for Rust async (analogous to Go's runtime scheduler)
- Multi-threaded executor by default
- Backpressure primitives (`mpsc` channels with bounded capacity) map cleanly to the receiver→batcher→exporter pipeline

### ClickHouse client landscape (Rust)

Two contenders, both production-viable:

| Client | Maintainer | Protocol | Notes |
|---|---|---|---|
| [`clickhouse-rs`](https://github.com/suharev7/clickhouse-rs) | Community | Native (TCP, binary) | Mature, async, connection pooling, strong type-safe row mapping |
| [`klickhouse`](https://github.com/Protryon/klickhouse) | Community | Native (TCP, binary) | Newer, ergonomic API, leans hard into `tokio` patterns |

Both speak ClickHouse's Native protocol (the same one the official Go client uses internally). **HTTP fallback exists** in both for compatibility, but Native is the path for throughput.

### What's missing vs. Go

- No upstream OTel Collector binary that's "just Rust" — the canonical Collector is Go, and that's where most receivers/processors/exporters live.
- Fewer turn-key OTel components → if Phase 2 needs an `attributes_processor` or a `tail_sampling_processor`, the Go ecosystem has it, and Rust may not (yet).
- Smaller community for OTel-specific Q&A. General Rust async / gRPC has *enormous* community support; the OTel intersection is thinner.

**Mitigation:** The Collector's job in Sentinel Phase 1 is narrow (OTLP receive, validate, batch, write ClickHouse). We don't need the upstream Collector's 100+ component bazaar yet. When we do, contracts make it swap-safe (Sync 02 D8) — we can front the Rust core with a Go sidecar for one component without breaking the system.

## Performance — the case that motivates Rust

Concrete numbers from comparable systems (not Sentinel benchmarks — those don't exist yet, that's the bake-off's job):

- **Discord switching `go-keystore` → Rust** (2020): 5× p99 latency improvement, 10× memory reduction at the same load. ([blog](https://discord.com/blog/why-discord-is-switching-from-go-to-rust))
- **Cloudflare's `oxy` HTTP proxy** (Rust, replacing nginx): handles ~1M req/s per box; quotes "the simplicity of Go without the GC tail."
- **OTel Collector itself (Go)**: ~50k-100k spans/s/core depending on processor chain; p99 tail starts climbing at >70% saturation due to GC.
- **`tonic` benchmarks**: published numbers of 200k+ RPS for echo gRPC services on commodity hardware.

These aren't apples-to-apples for our workload, but they bracket the expectation: at the throughputs Sentinel will see in Phase 2 (multiple cloud sources, several signals per source, possibly 100k+ events/s sustained), the GC tail is the failure mode and Rust eliminates it.

For Sprint 1 / Sprint 2 demo loads (1-10k events/s), **both languages will be fine.** That's why a bake-off is honest: at low load, Go's velocity wins; at the load Phase 2 imagines, Rust's tail-latency wins. We need to pick for the load we're building toward, not the load we have on Day 7.

## Reference Cargo manifest (sketch)

The `services/collector-rust/Cargo.toml` in this PR is the minimal viable starting point:

```toml
[dependencies]
# OTLP receive
opentelemetry = "0.27"
opentelemetry_sdk = { version = "0.27", features = ["rt-tokio"] }
opentelemetry-otlp = { version = "0.27", features = ["grpc-tonic", "trace", "metrics", "logs"] }
opentelemetry-proto = { version = "0.27", features = ["gen-tonic", "trace", "metrics", "logs"] }

# gRPC server
tonic = "0.12"
prost = "0.13"

# Async runtime
tokio = { version = "1.40", features = ["full"] }

# ClickHouse export — pick one in the bake-off
clickhouse = "0.13"  # or: klickhouse = "0.13"

# Observability of the Collector itself (meta-telemetry)
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "json"] }

# Config + serde
serde = { version = "1", features = ["derive"] }
serde_yaml = "0.9"

# Errors
anyhow = "1"
thiserror = "1"
```

Versions to be re-pinned at PR time; `cargo update` periodically; Renovate / Dependabot for ongoing tracking.

## What the first build day looks like

If this ADR is accepted as a bake-off plan, the first concrete output (target: end of Sprint 1) is the smallest possible Collector that proves the loop:

1. Bind `tonic` OTLP gRPC server on `:4317`.
2. Accept a `ExportTraceServiceRequest` (one span).
3. Convert to a ClickHouse row (single fixed schema, no transforms).
4. Write to ClickHouse via the chosen client.
5. Return `ExportTraceServiceResponse::default()` to the caller (the Generator).

That's ~300 lines of Rust. Anyone who's seen `tonic`'s hello-world can have it running in a day. The 4 days that follow are the unglamorous part: backpressure, batching, graceful shutdown, container packaging, the `cargo clippy` warnings nobody loves.

## Open questions for `#crew-b`

1. **Does the Pod 2 majority want the 5-day Rust ramp-up cost in Sprint 1?** This is the gating question. If two of three say "I'd rather ship Go and learn Rust on the side," that's the answer.
2. **Is the bake-off worth the cost?** The asymmetric alternative — *"build it in Go, port to Rust later if metrics demand it"* — is real. Argument against: porting later is harder than picking now, because Phase 2 will have layered on top.
3. **How do we measure?** Defining the bake-off harness (load generator parameters, metric thresholds, decision criteria weights) is itself a ~½-day spike — but a worthwhile one because it removes "vibes" from the language pick.
4. **Cohort signal.** Crew A (Apex) and Crew D (AgentSpec) will probably go Go. Crew C (Oteru — agentic observability) likely Python. **Crew B doing Rust would be the only Rust footprint in the program** — that's a learning lever (per Commander's framing) but also a maintenance island.

## Citations / further reading

- OpenTelemetry Rust 1.0 announcement — <https://opentelemetry.io/blog/2024/otel-rust-1.0/>
- OpenTelemetry Rust docs — <https://opentelemetry.io/docs/languages/rust/>
- `opentelemetry-proto` (the canonical wire format) — <https://github.com/open-telemetry/opentelemetry-proto>
- `tonic` gRPC for Rust — <https://github.com/hyperium/tonic>
- `clickhouse-rs` — <https://github.com/suharev7/clickhouse-rs>
- `klickhouse` — <https://github.com/Protryon/klickhouse>
- ClickStack docs (ClickHouse + OTel reference) — <https://clickhouse.com/docs/en/observability/otel>
- Discord Go→Rust case study — <https://discord.com/blog/why-discord-is-switching-from-go-to-rust>
- OpenTelemetry Collector (Go upstream, for comparison) — <https://github.com/open-telemetry/opentelemetry-collector>

---

*This brief intentionally stops short of code-level prescriptions. The point is to put Rust on the bake-off; the implementation lands in `services/collector-rust/` and grows from there.*
