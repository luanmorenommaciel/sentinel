# Pod 2 Rust Learning + Build Roadmap

| Field | Value |
|---|---|
| Owner | Victor Urquiola (Pod 2) |
| Sprint | Sprint 1 |
| Created | 2026-06-01 |
| Status | Active |
| Risk-out gate | Day 5 (if no end-to-end MVP, switch to Go per ADR-0004) |

> The frame: **don't try to learn Rust then build the Collector. Build the Collector and learn Rust through it.** This document is the day-by-day sequencing that makes that work.

## Sprint deliverable

A working Rust binary that consumes Pod 1's NDJSON output (per `contract/schema/otlp_output.schema.json` v1.0.0) and writes the parsed signals into ClickHouse. End-to-end, tested against the golden fixture (`contract/golden/baseline_seed42.jsonl`), packaged in Docker, passing all 7 CI gates.

OTLP gRPC `:4317` transport is the architectural target but is **out of scope for the MVP**. Week 2 work, after the NDJSON path is solid.

## Phases

### Phase 1 — Toolchain + first parse (Days 1–2)

**Goal:** prove the loop. Read one line of NDJSON, deserialize to a Rust struct, print. Test runs against the golden file.

| Day | Work | Rust concepts you'll meet | Ships |
|---|---|---|---|
| 1 AM | `rustup` install · `cargo build` the existing scaffold · skim Rust Book ch. 1–3 · Rustlings 1–10 | `fn`, `let`, `Result`, `?`, ownership intuition | Scaffold runs locally; you can read a 50-line Rust file |
| 1 PM | Author `src/contract.rs` (serde types matching Pod 1's JSON Schema) — input from the python-developer agent's mapping report | `struct`, `enum`, `#[derive]`, `serde::Deserialize` | One Rust module with all 3 signal-type structs |
| 2 AM | Write a binary that reads the first line of `baseline_seed42.jsonl` and prints it parsed | `std::fs`, `BufReader`, `serde_json::from_str` | `cargo run` prints "parsed: SpanSignal { ... }" |
| 2 PM | Loop over all lines; count by signal type; first test against the golden file | iterators, `match`, `#[cfg(test)]` | `cargo test` passes; goldens decoded |

**Phase 1 exit:** `cargo run` over the golden file outputs counts (e.g., "300 spans, 300 logs, 300 metrics"). `cargo test` passes. You can read every line of code you wrote and explain why each piece is there.

### Phase 2 — ClickHouse write (Days 3–5)

**Goal:** stop printing, start storing. Each parsed signal becomes a row in ClickHouse.

| Day | Work | Rust concepts you'll meet | Ships |
|---|---|---|---|
| 3 | Spin up ClickHouse via Docker compose · add `clickhouse` crate dependency · write one row to a hand-rolled `otel_logs` table | `tokio::main`, async/await, `Result<T, anyhow::Error>` | One log row in ClickHouse from a Rust call |
| 4 | Generalize: write all 3 signal types to per-type tables (logs/traces/metrics) | trait objects vs enum dispatch, error propagation | All 3 signal types persist; visible via `clickhouse-client` SELECT |
| 5 | Integration test against ClickHouse in a Docker container · CI gates clean | `#[tokio::test]`, integration tests in `tests/`, `tracing` for logs | **MVP: NDJSON file → ClickHouse, tested, CI-green** |

**Phase 2 exit (= sprint risk-out gate):** end-to-end runs locally. Reading the golden file produces the expected row counts in ClickHouse. If you can't hit this by EOD Day 5, switch to Go per ADR-0004 — the writeup is already there, swap the binary and keep the architecture.

### Phase 3 — Hardening + OTLP gRPC (Days 6–10)

**Goal:** turn the MVP into a real Collector. Container, config, OTLP gRPC server.

| Day | Work | Rust concepts you'll meet | Ships |
|---|---|---|---|
| 6 | YAML config (`serde_yaml`) · `tracing` structured logging · contract-version validation at the receive boundary | configuration patterns, error newtypes via `thiserror` | Collector reads `config.yaml`; rejects mismatched `contract_version` |
| 7 | Multi-stage Dockerfile (distroless final image) · docker-compose for collector + ClickHouse | none — Rust, just packaging | `docker compose up` brings up the full local stack |
| 8 | `tonic` gRPC server skeleton on `:4317` · accept one `ExportTraceServiceRequest` · log it | `tonic::Service` trait, `prost`-generated types, `opentelemetry-proto` crate | gRPC server binds; `grpcurl` smoke test passes |
| 9 | Wire OTLP gRPC handler → existing ClickHouse exporter path · replace file reader with handler | shared state via `Arc`, `Send + Sync + 'static` | Real OTLP gRPC payload lands in ClickHouse |
| 10 | `cargo clippy --all-targets -- -D warnings` clean · `cargo fmt` · attribution trailers · open the PR for Captain + Commander review | none Rust-specific — workflow | **PR open, CI green, ready to merge** |

**Phase 3 exit:** Sprint deliverable shipped. PR open against `main` with the unified ADR-0004 + Rust scaffold + contract module + ClickHouse exporter + OTLP gRPC receiver.

## How I'll use the lab agents

This is the lookup table I check whenever I'm stuck. From [`.claude/CLAUDE.md`](../../.claude/CLAUDE.md):

| When I... | I dispatch / read |
|---|---|
| Don't understand a Rust compiler error | `rust-specialist` agent — paste the error verbatim |
| Need a Pydantic model translated to Rust | `python-developer` agent (already used on Day 1) |
| Need a ClickHouse schema decision | `clickhouse-engineer` agent |
| Need to understand how the upstream OTel Collector solves a problem | `otel-collector-specialist` agent |
| Need to write a test for a new module | `test-generator` agent |
| Need a Docker compose / dev-script | `shell-script-specialist` agent |
| Need to read the Rust scaffold for the first time | `codebase-explorer` agent |
| Need a code review on my diff | `code-reviewer` agent + `/review` skill |
| Need to plan a multi-step refactor | `the-planner` agent |
| Need to refresh on cargo / clippy / just / rustup | [`.claude/docs/RUST_PROJECT_STANDARDS.md`](../../.claude/docs/RUST_PROJECT_STANDARDS.md) |

## External resources (skim, don't sequentially read)

| Resource | When | Why this one |
|---|---|---|
| [The Rust Book](https://doc.rust-lang.org/book/) ch. 1–4, 8–10, 13 | Days 1–2, 1–2h evenings | Free, official, written for newcomers. Skip ch. 15–17 until Day 8. |
| [Rustlings](https://github.com/rust-lang/rustlings) | Day 1 morning, 2h | Interactive exercises. Calibrates "do I get this?" |
| [Zero to Production in Rust](https://www.zero2prod.com/) | Days 4–6 evenings, $40 | Teaches Rust by building a real production service. Best analog. |
| [Tokio Tutorial](https://tokio.rs/tokio/tutorial) | Day 4 AM, 1h | Async model. Read "Hello Tokio" + "Spawning" + "Shared state" sections. |
| [docs.rs/serde](https://docs.rs/serde) | Days 1–2, look-up | `#[serde(tag = "...")]` is the discriminator pattern |
| [docs.rs/clickhouse](https://docs.rs/clickhouse) | Day 4 | Examples section is the start |

**Avoid:** YouTube Rust tutorials (mostly out of date for the 2024 edition + tokio 1.40). One-week "learn Rust in X days" articles (no time).

## Progress tracker

Check items off as you go. Captain status updates reference this.

### Phase 1 — Parser
- [ ] `rustup` installed, `cargo --version` confirms 1.83+
- [ ] Existing scaffold `cargo build` succeeds
- [ ] `cargo run` and `cargo test` succeed on the scaffold
- [ ] Rustlings 1–10 complete
- [ ] `src/contract.rs` authored (per python-developer mapping)
- [ ] First line of golden file parses into a Rust struct
- [ ] All lines parse; signal type counts match expectation
- [ ] `cargo test` passes with at least 1 golden-file integration test

### Phase 2 — ClickHouse
- [ ] ClickHouse runs via `docker compose up`
- [ ] One log row inserted via the Rust binary
- [ ] All 3 signal-type tables receive rows from the golden file
- [ ] Integration test with ClickHouse in Docker
- [ ] `just ci` passes (fmt + clippy + test + audit + deny + doc)

### Phase 3 — Hardening + gRPC
- [ ] YAML config loaded; `tracing` logs JSON
- [ ] `contract_version` validated; mismatch produces a useful error
- [ ] Multi-stage Dockerfile; image size under 30 MB
- [ ] docker-compose brings up Collector + ClickHouse cleanly
- [ ] `tonic` gRPC server binds `:4317`
- [ ] `grpcurl` smoke test succeeds
- [ ] Real OTLP gRPC payload → ClickHouse path works
- [ ] PR opened against `main`; CI green; awaiting Captain + Commander review

## Escape hatches

If you hit a wall:

1. **Day 5 risk-out** — if MVP isn't end-to-end by EOD Day 5, switch to Go. ADR-0004 has the writeup; opening `feat/go-otel-collector` and porting is ~1 day of work. Sprint deliverable is the Collector, not the language.
2. **Stuck on Rust syntax** — `rust-specialist` agent first, then web search, then `/enrich-kb rust` to capture the resolution for future-you.
3. **Stuck on contract semantics** — DM Vinícius in `#crew-b`; he wrote it. Reference the contract review (`docs/research/contract-review-pod1-v1.0.0.md`) so the conversation has context.
4. **Stuck on ClickHouse schema** — `clickhouse-engineer` agent + check Pod 1's `contract/clickhouse_schema.yaml` for the dev-only reference (Pod 3 owns the canonical schema).
5. **Stuck on async / tokio lifetimes** — paste the compiler error into `rust-specialist`. Don't fight the borrow checker alone for more than 30 min.

## Daily check-in

Every morning, post in `#crew-b`:
- Yesterday: what I shipped (or what blocked)
- Today: which row of the table above I'm working on
- Blockers: anything that needs Vinícius / Captain / Commander

Every Wednesday + Friday: open PR(s) for what's ready. Don't batch a week of work into one massive review.

## See also

- [ADR-0004](../adr/0004-collector-implementation-language.md) — why we're doing Rust
- [Pod 1 contract review](contract-review-pod1-v1.0.0.md) — what to validate at the boundary
- [`.claude/docs/RUST_PROJECT_STANDARDS.md`](../../.claude/docs/RUST_PROJECT_STANDARDS.md) — the project's UV-equivalent Rust setup
- [`services/collector-rust/README.md`](../../services/collector-rust/README.md) — the scaffold's own README with the next-steps list

---

*This document is intentionally personal. It's Victor's working plan, not a Crew B contract. Captain reviews progress; doesn't mandate the path.*
