# `sentinel-collector` · Rust

The Sentinel OTel Collector — Pod 2's ingestion gateway. Receives OTLP over gRPC on `:4317`
(or reads Pod 1's NDJSON), validates against the Pod 1 → Pod 2 input contract, buffers and
batches, and writes directly into Pod 3's **bronze** ClickHouse schema.

> **Status: selected implementation, validated end-to-end.** After the language bake-off,
> Pod 2 standardized on Rust and `services/collector-go/` was removed from the repo
> (PR #28, merged 2026-08-12). Latest local E2E: 233,100 signals in 4.5s, lossless, avg export
> latency 32.3ms — see [README §8](../../README.md) for the full snapshot.
> ⚠️ [ADR-0004](../../docs/adr/0004-collector-implementation-language.md) still reads
> `Proposed` and has not been updated to record the selection.

## What it does

| Boundary | Contract | Enforcement |
|---|---|---|
| **Inbound** (producer → collector) | [`contracts/generator/v1/schema/otlp_output.schema.json`](../../contracts/generator/v1/schema/otlp_output.schema.json) **v1.0.0** — 3 signal types, 5 guaranteed `sentinel.*`/`cloud.provider` resource keys | gRPC: `contract.grpc_validation` = `off`/`warn`/**`warn` default**/`strict`. File: `contract.strict` (all-or-nothing) |
| **Outbound** (collector → ClickHouse) | the **bronze DDL** ([`infra/clickhouse/init.d/01-bronze-otel.sql`](../../infra/clickhouse/init.d/01-bronze-otel.sql)), documented by the [Pod 2 → Pod 3 read contract](../../contracts/collector/v1/pod2-pod3-read-contract.md) v1.0.0.1 | Typed rows via the `clickhouse` crate. The collector issues **no DDL at all** — Pod 3 owns the table lifecycle (the repo calls this policy `create_schema:false`, after the contrib exporter's flag) |

`warn` is the gRPC default on purpose: foreign OTLP legitimately lacks the five `sentinel.*`
keys, so `strict` would silently drop real traffic. Use `strict` only when the sender is
guaranteed Sentinel-internal.

## Run it

From the repo root (Docker, no host toolchain):

```sh
make e2e        # ClickHouse + collector + generator → bronze.*
make logs       # tail the collector
```

Standalone:

```sh
cd services/collector-rust
cargo run -- config.example.yaml   # FILE mode: read the golden NDJSON, tally, exit
cargo test                         # unit + integration (live-ClickHouse tests are #[ignore]d)
```

**Run modes** are decided by which config sections are present — see
[`config.example.yaml`](config.example.yaml), which documents every key:

| `grpc:` | `clickhouse:` | Mode |
|---|---|---|
| absent | absent | FILE + count only — parse `input.path`, tally, exit |
| absent | present | FILE + export — parse `input.path`, write to ClickHouse, exit |
| present | absent | SERVER + log only — serve `:4317`, count and log requests |
| present | present | SERVER + export — the production path |

`CLICKHOUSE_URL` and `RUST_LOG` override the config file.

## Lint + test gates

These are the gates `.github/workflows/rust-ci.yml` enforces:

```sh
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --locked
cargo test --test clickhouse_roundtrip --locked -- --ignored   # needs a live ClickHouse
cargo deny check                                               # advisories + licenses (deny.toml)
```

CI runs these as four jobs: **gates** (fmt · clippy · test · release build) ·
**integration** (ClickHouse round-trip against a real container) · **supply-chain**
(cargo-deny) · **docker-build** (distroless image).

The enforced lint policy is package-level `[lints]` in `Cargo.toml`: `unsafe_code = "forbid"`,
`unwrap_used = "deny"`, `expect_used = "warn"`. **`pedantic`, `nursery` and `missing_docs` are
deliberately commented out** — aspirational until a dedicated cleanup PR clears the existing
warnings. Don't assume pedantic is on. (It becomes `[workspace.lints]` if a second Rust crate
ever appears.) Full standards:
[`.claude/docs/RUST_PROJECT_STANDARDS.md`](../../.claude/docs/RUST_PROJECT_STANDARDS.md).

## Layout

```text
services/collector-rust/
├── Cargo.toml · rust-toolchain.toml · rustfmt.toml · clippy.toml · deny.toml
├── config.example.yaml     # documented reference config
├── config.docker.yaml      # the compose profile (has `grpc:` → server mode)
├── Dockerfile              # multi-stage → distroless
├── justfile                # local dev recipes
├── src/
│   ├── main.rs             # entry point — picks run mode from config
│   ├── lib.rs              # module root
│   ├── config.rs           # YAML loader; unknown keys rejected
│   ├── contract.rs         # v1.0.0 input-contract validation
│   ├── otlp.rs             # OTLP protobuf → internal `Signal`
│   ├── grpc.rs             # tonic OTLP server (:4317) + `apply_validation`
│   ├── buffer.rs           # bounded buffer, size + interval flush thresholds
│   ├── clickhouse_exporter.rs  # typed bronze writes (RowBinary over HTTP :8123)
│   ├── metrics.rs          # Prometheus counters/histograms
│   └── metrics_server.rs   # `/metrics` on :9090
└── tests/
    ├── golden_parse.rs           # golden fixture → 48 logs / 48 spans / 183 metrics
    ├── grpc_smoke.rs             # server accepts OTLP
    ├── grpc_export_roundtrip.rs  # OTLP in → bronze rows out
    └── clickhouse_roundtrip.rs   # live-ClickHouse export (#[ignore]d by default)
```

**Ports:** OTLP gRPC `:4317` · Prometheus `/metrics` `:9090` · ClickHouse **HTTP `:8123`**
(the `clickhouse` crate speaks RowBinary over HTTP — not native `:9000`).

## Known gaps

- **Histogram / Summary metrics are not emitted** — the v1.0.0 input contract has no such type (`src/otlp.rs`).
- **Sentinel keys live in `ResourceAttributes` `Map`** under bronze, not typed columns. Materializing them is a Pod 3 silver decision ([ADR-0007 §Trade-offs](../../docs/adr/0007-bronze-canonical-contract.md)).

## See also

[ADR-0004](../../docs/adr/0004-collector-implementation-language.md) (language) ·
[ADR-0006](../../docs/adr/0006-optional-id-representation.md) (optional IDs) ·
[ADR-0007](../../docs/adr/0007-bronze-canonical-contract.md) (bronze = canonical contract) ·
[read contract](../../contracts/collector/v1/pod2-pod3-read-contract.md) ·
[research receipts](../../docs/research/rust-otel-collector.md)
