# `sentinel-collector` · Rust scaffold

The Rust implementation of the Sentinel OTel Collector. Receives OTLP over gRPC on `:4317`, validates, batches, exports to ClickHouse.

> **Status: scaffold.** Does not yet bind a port or write to ClickHouse. It exists to anchor [ADR-0004](../../docs/adr/0004-collector-implementation-language.md), prove the toolchain compiles, and give Pod 2 a starting point for the bake-off against Go.

## Why this exists

Sync 02 (2026-05-26) action A7 scheduled a bake-off for the Collector implementation language. This crate is the Rust corner. The Go corner should land in a sibling PR at `services/collector-go/` (not yet open).

The full case is in [`docs/adr/0004-collector-implementation-language.md`](../../docs/adr/0004-collector-implementation-language.md). The receipts are in [`docs/research/rust-otel-collector.md`](../../docs/research/rust-otel-collector.md). Read those first if you arrived here cold.

## Prerequisites

```bash
# Rust toolchain (stable 1.75+)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup default stable
rustup component add rustfmt clippy

# Verify
cargo --version
rustc --version
```

## Build & run (scaffold only)

```bash
cd services/collector-rust
cargo build
cargo run     # logs a startup line in JSON then exits
cargo test    # runs the scaffold-compiles smoke test
```

Both should succeed before the bake-off properly starts.

## Lint + format gates

These map to the CI gates in the [Crew B WoW spec](../../docs/adr/) (when ADR-0007 — per-language CI profiles — lands):

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

## What's next (in dependency order)

1. **Bind OTLP gRPC server on `:4317`** — `tonic`-based, accepting `ExportTraceServiceRequest`. Smallest possible loop: receive → log → return default response. Goal: prove the wire is alive.
2. **Connect to ClickHouse** — using the `clickhouse` crate (Native protocol via HTTP). Create one table, write one span. Goal: prove the export side works.
3. **Glue receive → export with a bounded `mpsc` channel** — backpressure surface for the bake-off. Goal: load-generator pings the receiver, span lands in ClickHouse.
4. **Batching + flush thresholds** — size + time. Goal: throughput numbers worth measuring.
5. **Container image** — multi-stage build, distroless final. Goal: 5–20 MB image for cold-start advantage.
6. **Meta-telemetry** — the Collector emits its own OTel signals. Goal: Sentinel can watch Sentinel.

Each of these steps is a small PR, reviewed by Pod 2 and merged via the standard 8-step PR flow (signed commits, 2 approvals, 7 CI gates, attribution trailers).

## Directory layout (target)

```text
services/collector-rust/
├── Cargo.toml
├── README.md         # this file
├── src/
│   ├── main.rs       # entry point (scaffold)
│   ├── receiver.rs   # OTLP gRPC server (planned)
│   ├── exporter.rs   # ClickHouse write path (planned)
│   ├── pipeline.rs   # receive → batch → export glue (planned)
│   └── config.rs     # YAML config loader (planned)
└── tests/            # integration tests against a local ClickHouse container
```

## Bake-off harness (cross-language, not in this crate)

The bake-off compares this crate to the eventual `services/collector-go/` against a shared:

- Load generator (the Python data generator that Vinícius pushed — `services/generator/`)
- ClickHouse instance (Docker compose, 8 GB VM)
- Metric collection (Prometheus scraping both Collectors' meta-telemetry)
- Decision criteria (defined in a future ADR-0006)

The harness lives at `bench/collector-bakeoff/` (also not yet open). Either Pod 2 or the Captain will scaffold it once the language ADR is accepted.

## Contract & boundaries

Per Sync 02 D8, every component declares input/output contracts. The Collector's contracts:

| Boundary | Contract | Validation |
|---|---|---|
| **Inbound** (Generator → Collector) | OTLP `ExportTraceServiceRequest` / `ExportMetricsServiceRequest` / `ExportLogsServiceRequest` | `opentelemetry-proto` generated types — protobuf-validated on receive |
| **Outbound** (Collector → ClickHouse) | RAW table schema (per signal type), defined by Pod 3 | Strongly-typed via `clickhouse` crate `Row` derive; schema-version field in every row |

Contracts are versioned. A breaking change opens a new ADR.

## Attribution

This scaffold was authored with `Co-Authored-By: Claude Opus 4.7` per the [Crew B attribution contract](../../docs/adr/) (see Sync 01 *How we ship*).

## See also

- [`docs/adr/0004-collector-implementation-language.md`](../../docs/adr/0004-collector-implementation-language.md) — the ADR this scaffold is paired with
- [`docs/research/rust-otel-collector.md`](../../docs/research/rust-otel-collector.md) — research receipts
- Sentinel spec (`sentinel.pdf` in Crew B docs) — overall mission + Watcher fleet context
