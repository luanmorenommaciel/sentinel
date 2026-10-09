---
title: Rust — Idioms + Patterns for Sentinel
last_updated: 2026-06-01
confidence: 0.85
---

> **MCP Validated:** 2026-06-01

> **PROJECT SETUP IS NOT HERE.**
> Workspace layout, `cargo deny`, `just` targets, CI gate mapping, and toolchain pinning
> live in [`.claude/docs/RUST_PROJECT_STANDARDS.md`](../../docs/RUST_PROJECT_STANDARDS.md).
> This KB covers **language patterns** — idioms, async primitives, error handling, and
> Sentinel-specific conventions for writing production-grade Rust.

---

## Rust's role in Sentinel

ADR-0004 (`docs/adr/0004-collector-implementation-language.md`) proposes Rust for Pod 2's
OTel Collector. The bake-off alternative is Go. The decision criteria are:

- **Throughput**: OTLP gRPC ingestion at peak load without a GC pause profile
- **Safety**: `unsafe_code = "forbid"` at the workspace level; the Collector handles untrusted
  payloads from the generator
- **Operational simplicity**: single statically-linked binary, distroless container, cold-start
  under 200ms

Until ADR-0004 is closed, this KB documents patterns that apply to the Rust path. Go patterns
are in `kb/languages/go/`.

---

## Tokio async runtime

### Entry point

```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // tokio::main spawns the multi-threaded runtime by default.
    // For a low-resource single-thread variant: #[tokio::main(flavor = "current_thread")]
    run().await
}
```

`tokio::main` expands to `Runtime::new().block_on(async { ... })`. It is the only acceptable
entry point for async Sentinel binaries. Do not call `Runtime::block_on` manually in `main.rs`.

### Spawning tasks

```rust
use tokio::task::JoinHandle;

let handle: JoinHandle<anyhow::Result<()>> = tokio::spawn(async move {
    do_work().await
});

// Await the handle; propagate panics as Err
handle.await??;  // double ? = JoinError unwrap + inner Result
```

Rules:
- Spawned closures must be `Send + 'static` (see "Send + Sync + 'static" section below).
- Prefer `JoinSet` over `Vec<JoinHandle>` when managing many tasks — it cancels stragglers on
  drop.

### select! for concurrent branches

```rust
tokio::select! {
    result = receiver.recv() => {
        // handle incoming OTLP batch
    }
    _ = shutdown_signal() => {
        // graceful shutdown path
    }
}
```

`select!` races futures and cancels the losers. Cancellation safety matters: if `receiver.recv()`
is not cancellation-safe, buffer the value before entering `select!`. Check the Tokio docs for
each method's cancellation-safety guarantee.

### Bounded mpsc channels for backpressure

```rust
use tokio::sync::mpsc;

// Bound = max in-flight batches; exceeding it blocks the sender.
// Size the bound to ~2x expected burst, not unbounded.
let (tx, mut rx) = mpsc::channel::<OtlpBatch>(256);

// Producer (inside the gRPC handler — see tonic section)
tx.send(batch).await?;  // async: yields if channel is full

// Consumer (pipeline stage)
while let Some(batch) = rx.recv().await {
    process(batch).await?;
}
```

Never use `mpsc::unbounded_channel` in the hot path — it eliminates backpressure and lets the
consumer fall arbitrarily behind. Sentinel's Collector must apply pressure back to the generator.

---

## tonic gRPC server pattern

### Proto-first workflow

Define the contract in `.proto`, generate Rust with `prost` + `tonic-build`:

```rust
// build.rs
fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::configure()
        .build_server(true)
        .build_client(false)  // Collector is server-side only
        .compile(
            &["proto/opentelemetry/proto/collector/trace/v1/trace_service.proto"],
            &["proto/"],
        )?;
    Ok(())
}
```

The generated code lands in `OUT_DIR`; include it with `tonic::include_proto!`.

### Implementing the Service trait

```rust
use tonic::{Request, Response, Status};
use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_server::TraceService,
    ExportTraceServiceRequest, ExportTraceServiceResponse,
};

#[derive(Debug)]
pub struct CollectorService {
    // Arc wrapping allows the service to be cloned per connection.
    tx: tokio::sync::mpsc::Sender<OtlpBatch>,
}

#[tonic::async_trait]
impl TraceService for CollectorService {
    async fn export(
        &self,
        request: Request<ExportTraceServiceRequest>,
    ) -> Result<Response<ExportTraceServiceResponse>, Status> {
        let batch = request.into_inner();
        self.tx
            .send(batch.into())
            .await
            .map_err(|_| Status::resource_exhausted("channel full"))?;
        Ok(Response::new(ExportTraceServiceResponse::default()))
    }
}
```

### Server builder

```rust
use tonic::transport::Server;

Server::builder()
    .add_service(TraceServiceServer::new(svc))
    .add_service(MetricsServiceServer::new(svc.clone()))
    .add_service(LogsServiceServer::new(svc.clone()))
    .serve("[::]:4317".parse()?)
    .await?;
```

All three signal types (traces, metrics, logs) share the same port `:4317`. Register all three
services on one `Server::builder()` so they share the same H2 connection pool.

---

## Error handling: anyhow vs thiserror

### The rule

| Context | Use | Reason |
|---|---|---|
| Binary entry points (`main.rs`, `run()`) | `anyhow` | Aggregates heterogeneous errors, pretty-prints context chain |
| Library functions / `impl` blocks | `thiserror` | Typed errors callers can `match` on |
| gRPC handler return type | `thiserror` variant mapped to `tonic::Status` | gRPC status codes must be explicit |
| Tests | `anyhow` (via `?`) | Convenience; panics are fine in tests |

### anyhow usage

```rust
use anyhow::{Context, Result};

fn load_config(path: &str) -> Result<Config> {
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read config from {path}"))?;
    serde_yaml::from_str(&text).context("config parse failed")
}
```

`.context()` and `.with_context()` add a human-readable frame without allocating if the call
succeeds. Prefer `.with_context(|| ...)` (lazy) for paths involving string formatting.

### thiserror usage

```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum CollectorError {
    #[error("channel send failed: pipeline is shutting down")]
    ChannelClosed,

    #[error("invalid OTLP payload: {0}")]
    InvalidPayload(String),

    #[error("ClickHouse write failed after {attempts} retries")]
    StorageExhausted { attempts: u32 },
}

// Map to gRPC Status
impl From<CollectorError> for tonic::Status {
    fn from(e: CollectorError) -> Self {
        match e {
            CollectorError::ChannelClosed => Status::resource_exhausted(e.to_string()),
            CollectorError::InvalidPayload(_) => Status::invalid_argument(e.to_string()),
            CollectorError::StorageExhausted { .. } => Status::unavailable(e.to_string()),
        }
    }
}
```

### Never .unwrap() in production paths

The workspace lint `unwrap_used = "deny"` (in `Cargo.toml`) **prevents compilation** if `.unwrap()`
appears outside tests. Use:

```rust
// Instead of option.unwrap():
option.ok_or_else(|| CollectorError::InvalidPayload("missing field".into()))?

// Instead of result.unwrap():
result.map_err(CollectorError::from)?

// .expect() is warn, not deny — acceptable only when invariant is documented:
let rt = tokio::runtime::Handle::current();  // only call from async context
```

---

## Send + Sync + 'static for async handlers

### What the bounds mean

| Bound | Meaning |
|---|---|
| `Send` | Value can be moved to another thread |
| `Sync` | Reference to value can be shared across threads |
| `'static` | Value contains no borrowed references with finite lifetimes |

`tokio::spawn` requires `Future: Send + 'static`. The tonic `#[tonic::async_trait]` impl
requires the same.

### How to satisfy them

```rust
// Wrong — Rc is not Send
let state = Rc::new(MyState::new());
tokio::spawn(async move { use_state(&state).await });  // compile error

// Right — Arc is Send + Sync
let state = Arc::new(MyState::new());
tokio::spawn(async move { use_state(&state).await });  // ok
```

Pattern for shared mutable state across async handlers:

```rust
use std::sync::Arc;
use tokio::sync::RwLock;

#[derive(Clone)]
pub struct AppState {
    inner: Arc<RwLock<Inner>>,
}
```

`Arc<RwLock<T>>` is the canonical Sentinel pattern for shared state in async services. Prefer
`RwLock` over `Mutex` when reads heavily outnumber writes (e.g., a config snapshot).

---

## Lifetimes and 'static in async code

### When 'static is required

`tokio::spawn` futures must own their data — no borrowed slices from the stack frame.

```rust
// Does not compile — `batch` borrow escapes
async fn bad(batch: &OtlpBatch) {
    tokio::spawn(async { process(batch).await });  // error: `batch` must be 'static
}

// Correct — clone or Arc before spawning
async fn good(batch: OtlpBatch) {
    tokio::spawn(async move { process(batch).await });
}

// When cloning is expensive — Arc
async fn good_arc(batch: Arc<OtlpBatch>) {
    let b = Arc::clone(&batch);
    tokio::spawn(async move { process(b).await });
}
```

### When borrowed slices work

Borrowed slices (`&[u8]`, `&str`) are fine in `async fn` that are **not** passed to `tokio::spawn`.
Within a single async task's call chain, normal lifetime rules apply.

```rust
// Fine — no spawn, borrow lives for the function duration
async fn parse_headers(buf: &[u8]) -> Result<Headers, CollectorError> { ... }
```

---

## Serde patterns

### Derive for structs

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct OtlpBatch {
    pub signal_type: SignalType,
    pub resource_attrs: ResourceAttrs,
    pub spans: Vec<Span>,
}
```

`#[serde(rename_all = "snake_case")]` matches the OTel JSON wire format without manual field
renames. Use `"camelCase"` if the source is a JavaScript/JSON client.

### OTel timestamp format (Unix nanoseconds as u64)

OTel timestamps are Unix nanoseconds stored as `u64`, serialized as JSON numbers. Chrono
is not needed for simple round-trip:

```rust
#[derive(Serialize, Deserialize)]
pub struct Span {
    #[serde(rename = "startTimeUnixNano")]
    pub start_time_unix_nano: u64,

    #[serde(rename = "endTimeUnixNano")]
    pub end_time_unix_nano: u64,
}
```

When human-readable timestamps are required (e.g., ClickHouse `DateTime64`), convert at the
storage boundary, not in the domain struct:

```rust
fn nanos_to_datetime(nanos: u64) -> chrono::DateTime<chrono::Utc> {
    let secs = (nanos / 1_000_000_000) as i64;
    let sub_nanos = (nanos % 1_000_000_000) as u32;
    chrono::DateTime::from_timestamp(secs, sub_nanos).expect("valid unix timestamp")
}
```

### Flattening and tagging enums

```rust
#[derive(Serialize, Deserialize)]
#[serde(tag = "signal_type", rename_all = "snake_case")]
pub enum OtlpSignal {
    Log(LogRecord),
    Span(SpanRecord),
    Metric(MetricRecord),
}
```

Matches Pod 1's `signal_type` discriminator in `contract/schema/otlp_output.schema.json`.

---

## Testing

### Unit tests (inline)

```rust
#[cfg(test)]
mod tests {
    // REQUIRED when the crate sets `unwrap_used = "deny"` / `expect_used = "warn"`.
    // Tests are allowed to fail-fast with unwrap/expect — that IS the test. Without
    // this inner attribute, `cargo clippy --all-targets -- -D warnings` fails on
    // every `.unwrap()` in this module. Crate-level lints apply to test code too.
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn parse_empty_batch_returns_error() {
        let result = parse_batch(&[]);
        assert!(result.is_err());
    }
}
```

> **Added 2026-06-01 · Confidence 0.95 (verified locally on Rust 1.96.0, Pod 2 Day-2)**
> The `unwrap_used = "deny"` lint in `Cargo.toml` `[lints.clippy]` applies to
> **all** code in the crate, including `#[cfg(test)]` modules. The fix is a
> module-inner `#![allow(clippy::unwrap_used, clippy::expect_used)]` (note the
> `#!` — inner attribute, first line inside the `mod tests { }` body). For
> integration tests under `tests/`, put the same `#![allow(...)]` at the **top
> of the file** (each integration test file is its own crate root). This is why
> the Day-1 scaffold's tests compiled but the Day-2 lint-tightening PR needed
> the allow added in three places: `src/contract.rs`, `src/lib.rs`, and
> `tests/golden_parse.rs`.

### Negative tests against an ordered validator

When testing a `Result`-returning validator that checks fields in a fixed order
and returns on the **first** failure (Sentinel's `Signal::validate()` is the
canonical example), every test must hold all OTHER fields valid so the variant
under test is the one that actually fires:

```rust
#[test]
fn negative_timestamp_is_detected() {
    let log = LogSignal {
        contract_version: "1.0.0".to_string(),  // valid — checked FIRST
        service_name: "s".to_string(),          // valid — checked SECOND
        time_unix_nano: -1,                      // the field UNDER TEST
        resource_attributes: req_attrs(),       // valid — checked LAST
        // ...
    };
    // assert_eq! with the exact payload when it's deterministic and worth pinning
    assert_eq!(log.validate(), Err(ContractError::NegativeTimestamp(-1)));
}
```

The trap: a negative test can pass for the **wrong reason** — an earlier guard
trips before validation reaches the field you meant to test. Mitigations:

- Use `assert_eq!(x.validate(), Err(ContractError::Exact { .. }))` (not just
  `is_err()`) so the *specific* variant is pinned.
- Use `matches!` only when the variant's payload is genuinely incidental:
  `assert!(matches!(x.validate(), Err(ContractError::InvalidTraceId(_))))`.
- Always pair negative tests with **boundary-positive** tests (e.g. `time == 0`
  is valid when the rule is `< 0`; `end == start` is valid when the rule is
  `end < start`) — they catch an over-eager validator that the negatives can't.

> **Added 2026-06-01 · Confidence 0.90 (Pod 2 Day-2, test-generator agent + review)**
> Property-based testing (`proptest`) is a strong fit for hand-rolled string
> parsers like Sentinel's `is_semver` and `is_lowercase_hex` — multi-byte UTF-8,
> NUL bytes, and exhaustive length boundaries are exactly what example-based
> tests miss. Deferred (no `proptest` dev-dependency yet) but flagged for a
> "harden the primitives" pass. Add `proptest = "1"` to `[dev-dependencies]` and
> a separate `#[cfg(test)] mod prop_tests` when picked up.

### Async unit tests

```rust
#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]  // see Unit tests note above

    use super::*;

    #[tokio::test]
    async fn channel_backpressure_blocks_sender() {
        let (tx, mut rx) = tokio::sync::mpsc::channel::<u8>(1);
        tx.send(1).await.unwrap();
        // channel full — try_send should fail
        assert!(tx.try_send(2).is_err());
        rx.recv().await;  // drain
        assert!(tx.try_send(2).is_ok());
    }
}
```

`#[tokio::test]` spins up a fresh single-thread runtime per test. For tests that need the
full multi-thread runtime: `#[tokio::test(flavor = "multi_thread", worker_threads = 2)]`.

### Integration tests

Integration tests live in `services/collector-rust/tests/`. Each file is its own crate:

```
tests/
└── e2e_otlp_receive.rs   # sends real OTLP to the in-process server
```

Run with `cargo nextest run` (see RUST_PROJECT_STANDARDS.md). Nextest runs each integration
test binary in a separate process — no shared state leaks.

### cargo nextest vs built-in cargo test

`cargo nextest` (installed via `just setup`) is required for CI. It is faster (parallel), outputs
structured results, and has per-test retry logic useful for flaky network tests. Use it locally
too; `just test` calls nextest.

---

## Performance: hot-path patterns

### Avoid allocations in hot paths

The Collector's `export()` handler is called for every OTLP batch. Avoid:

```rust
// Allocates a new Vec on every call
fn tag_keys(attrs: &[Attribute]) -> Vec<String> {
    attrs.iter().map(|a| a.key.clone()).collect()
}

// Better — return an iterator; caller decides if allocation is needed
fn tag_keys(attrs: &[Attribute]) -> impl Iterator<Item = &str> {
    attrs.iter().map(|a| a.key.as_str())
}
```

### Bytes vs Vec<u8>

`bytes::Bytes` is a reference-counted, cheaply-cloneable byte buffer. Use it for OTLP wire
payloads that are forwarded through multiple pipeline stages without modification:

```rust
use bytes::Bytes;

// Clone is O(1) — increments ref count
fn forward_payload(payload: Bytes, tx1: &Sender<Bytes>, tx2: &Sender<Bytes>) {
    let _ = tx1.try_send(payload.clone());
    let _ = tx2.try_send(payload);
}
```

`Vec<u8>` is appropriate when you need to mutate the buffer. `Bytes` is appropriate when you
need to fan out immutable references.

### FuturesUnordered for fan-out

When flushing to multiple ClickHouse shards in parallel:

```rust
use futures::stream::{FuturesUnordered, StreamExt};

let mut futs = FuturesUnordered::new();
for shard in &shards {
    futs.push(shard.write(batch.clone()));
}
while let Some(result) = futs.next().await {
    result?;
}
```

`FuturesUnordered` polls futures as they complete, not in insertion order — no head-of-line
blocking. Use it over `join_all` when individual future durations vary significantly.

---

## Quick-reference cheat sheet

| Idiom | Pattern |
|---|---|
| Option to Result | `opt.ok_or_else(\|\| MyError::Missing("field"))` |
| Result context | `result.with_context(\|\| format!("reading {path}"))` |
| Map error type | `result.map_err(CollectorError::from)?` |
| Default on None | `opt.unwrap_or_default()` |
| Early return on None | `let v = opt?;` (in `Option`-returning fn) |
| Shared state | `Arc<RwLock<T>>` |
| Cheap clone of bytes | `bytes::Bytes` (O(1) clone) |
| Fan-out async | `FuturesUnordered` |
| Backpressured queue | `mpsc::channel(N)` |
| Concurrent branches | `tokio::select!` |
| Spawn a task | `tokio::spawn(async move { ... })` |
| Integration test | `tests/<name>.rs` + `cargo nextest run` |
| Unwrap in tests under deny-lint | `#![allow(clippy::unwrap_used, clippy::expect_used)]` inside `mod tests` |
| Pin exact error variant | `assert_eq!(x.validate(), Err(MyError::Exact { .. }))` |
| Serde snake_case | `#[serde(rename_all = "snake_case")]` |
| Discriminated union | `#[serde(tag = "type")]` enum |
| Error with context | `thiserror::Error` + `#[error("...{field}...")]` |
| Anyhow in binary | `fn main() -> anyhow::Result<()>` |

---

## See also

- [RUST_PROJECT_STANDARDS.md](../../docs/RUST_PROJECT_STANDARDS.md) — workspace, `just`, CI gates, toolchain pin, `cargo deny`
- [CREW_B_GLOSSARY.md](../../docs/CREW_B_GLOSSARY.md) — Sentinel terminology (OTel Collector, Pod, Astronaut)
- [kb/telemetry/otel-collector/](../telemetry/otel-collector/) — Collector architecture: receivers, processors, exporters
- [kb/telemetry/opentelemetry/](../telemetry/opentelemetry/) — OTel core concepts, OTLP signal types, `:4317`
- [kb/contracts/](../contracts/) — Pydantic + Protobuf contract patterns, boundary validation
- [kb/languages/go/](../go/) — Go bake-off sibling; concurrency, OTel Collector internals
- `docs/adr/0004-collector-implementation-language.md` — ADR driving this KB
- `services/collector-rust/` — Pod 2's Rust scaffold (canonical usage of every pattern here)
- [.claude/CLAUDE.md](../../CLAUDE.md) — Project context, agent roster, KB routing table
- External: [The Rust Book](https://doc.rust-lang.org/book/) | [Tokio tutorial](https://tokio.rs/tokio/tutorial) | [tonic docs](https://docs.rs/tonic)
