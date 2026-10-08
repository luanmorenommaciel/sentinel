
# Project Intent Document

> **Scope of this document.** A reverse-engineered baseline of the `sentinel` repository as it
> stands on branch `origin/sdlc-e2e-review` (HEAD `3af2ee7`, 2026-10-05), written to anchor the
> next SDLC cycle. Every factual claim below is traceable to a file path in this repository.
> Where a statement is an interpretation rather than a reading, it is marked **(inferred)**.
> Section 3 is deliberately mostly `[TBD]` — the new intent is the owner's to declare.
>
> **One correction to the framing that produced this document.** The request described a
> repository "already built and deployed in production." The code is built; it is **not
> deployed**. There is no infrastructure-as-code, no orchestration manifest, no deployment
> pipeline and no cloud account referenced anywhere in the tree. See §1 *Current State* and
> §2 *Infrastructure* for the evidence. Nothing in this document invents a production estate
> to satisfy the template.

---

## 1. Executive Summary

* **Project Name:**

  **Sentinel** — an open-source, OTel-native observability and data-pipeline anomaly-detection
  platform. Upstream: `https://github.com/luanmorenommaciel/sentinel` (the sole configured git
  remote). Built by "Crew B" of the DataShip Mission 2026 mentorship programme; work is
  organised into four **Pods**, each owning one component end to end
  (`README.md` §2, `CLAUDE.md`).

* **Business Objective:**

  Stated mission, verbatim from `.claude/CLAUDE.md` (read from git history — see the note under
  *Current State*): *"autonomous observability + remediation for data pipelines. Self-healing
  where safe, page where it matters. One mission: no downstream user finds the bug before
  Sentinel does."*

  The intended long-run design is an eight-stage, vendor-agnostic spine —
  `otel_core → rolling_stats → tiered_engine → cross_watcher → policy_engine → remediation →
  audit_log → feedback_loop` — fed by six "Watcher" crews (Arrival, Parse, Volume, Schema,
  Latency, Storage) and a three-tier detection cascade (statistical z-scores → pattern
  signature → LLM escalation Haiku→Sonnet→Opus).

  **Only the first stage of that spine exists in code.** Stages 2 onwards (detection, policy,
  remediation, audit, feedback) have no implementation in this tree: a repository-wide search
  finds no module, table or service for any of them. They are a roadmap, documented as a
  future phase in `README.md` §1 and `.claude/CLAUDE.md`.

  The realistic, currently-pursued objective is therefore narrower and is what Phase 1 names:
  **build the telemetry foundation** — generate representative synthetic pipeline telemetry,
  ingest it losslessly over OTLP, land it in a contract-governed ClickHouse medallion
  (bronze → silver), and prove the whole path end to end behind versioned contracts.

* **Current State:**

  **The baseline is a local Docker Compose development stack. No deployed cloud
  infrastructure exists.** This is the single most important fact about the baseline, and it is
  established by absence as much as by presence, so the search is recorded explicitly:

  | Searched for | Result |
  |---|---|
  | `*.tf`, `*.tfvars`, `*.tfstate`, `*.tfbackend` (Terraform) | **none** |
  | `Pulumi*` | **none** |
  | Kubernetes manifests, `k8s/`, `kubernetes/`, `kustomization*`, `Chart.yaml`, `helm/`, `charts/` | **none** |
  | `cloudbuild*`, `app.yaml`, `cloudrun*`, `service.yaml` (GCP deploy surfaces) | **none** |
  | `skaffold*`, `serverless*`, `ansible/`, `.circleci/` | **none** |
  | GitHub Actions workflows | exactly **two**: `.github/workflows/rust-ci.yml`, `.github/workflows/pr-linked-issue.yml` |
  | Workflow that pushes an image to a registry | **none** — `rust-ci.yml:129` sets `push: false` |
  | Workflow that deploys anything anywhere | **none** |

  What does exist: four Compose services in the root `docker-compose.yml` (ClickHouse, the Rust
  collector, flow-ui, and an on-demand generator), three `Dockerfile`s built locally and tagged
  `:dev`, and a `Makefile` of 20 targets that is the real operator interface. One git tag
  exists (`v0.0.1`); there is no release pipeline behind it.

  **"First cloud target: GCP" is an intent, not a deployment.** The phrase appears in
  `.claude/CLAUDE.md`. The only GCP presence in the code is *simulated*: the generator's
  provider profile `services/generator-python/config/provider_profiles/gcp.yaml` and a topology
  of GCP-shaped component names (`cloud-composer-etl`, `dataproc-spark-batch`,
  `gcs-raw-bucket`, … in `services/generator-python/config/topology/default.yaml`). These are
  strings used to synthesise plausible telemetry. No GCP project, credential, API client,
  Workload Identity binding or service account appears anywhere in the tree.

  **Functional maturity is nevertheless real.** The ingest path is implemented and verified
  end to end: `README.md` §8 records a reproducible local snapshot (2026-08-04) of 233,100
  signals in 4.5s, 0 rejected / 0 dropped / 0 export errors, 32.3 ms average ClickHouse export
  latency, and a golden file-mode round-trip of 48 logs / 48 spans / 183 metrics. The README
  itself qualifies this as *"a reproducible local snapshot, not a production SLO"* — a honest
  caveat worth preserving rather than upgrading.

  **Decision records lag the code, and the repository says so.** `CLAUDE.md` carries a
  *Known doc drift* table; six of the seven ADRs under `docs/adr/` still read `Proposed`
  (verified by reading each file's status row). Most consequentially, ADR-0004 still frames
  Rust-vs-Go as an open bake-off (`docs/adr/0004-collector-implementation-language.md:5`)
  although the Go collector was deleted in PR #28 and Rust is the only ingestion path. Treat
  ADR status in this repo as a *paperwork* signal, not a signal about what is settled.

  **One directory is mid-reconstruction.** `.claude/` (89 files: agent definitions, skills,
  knowledge bases, internal standards) is deleted in the working tree and is being recreated by
  the owner. Its contents were read for this analysis from git (`git show HEAD:.claude/...`).
  Its absence is a workflow state, not an architectural fact, and this document makes no
  recommendation about it.

---

## 2. Baseline Architecture (As-Is)

The pipeline, as defined by `docker-compose.yml`:

```
generator (otelgen, on-demand)
   │  OTLP gRPC :4317
   ▼
collector-rust ──── HTTP :8123 (RowBinary) ────▶ ClickHouse ──▶ bronze.*  ──(MVs)──▶ silver.*
   │                                                              │                    │
   └── Prometheus /metrics :9090 ──────┐                          └── /play UI :8123 ──┘
                                       ▼
                          flow-ui :8080 (read-only reader of /metrics + bronze.* + silver.*)
```

* **Application Components:**

**1. `services/generator-python` — Pod 1, the synthetic OTLP generator (`otelgen`).**

Python ≥3.10 packaged with setuptools (`services/generator-python/pyproject.toml`), exposing a
Typer CLI as the console script `otelgen`. Dependencies: `opentelemetry-sdk` and
`opentelemetry-exporter-otlp` ≥1.24, `pydantic` ≥2.7 (contract models), `clickhouse-connect`
≥0.7 (the direct-write path), `typer`, `pyyaml`. 22 modules under `src/otelgen/`.

It is **config-driven, not hard-coded**. Four config families ship in
`services/generator-python/config/` and are baked into the image at `/app/contract`
(`Dockerfile`), overridable by bind mount:
- `topology/default.yaml` — a declared DAG of 8+ GCP-shaped pipeline components, each with
  `type`, `service_name`, `depends_on`, `base_rate`, `base_latency_ms`, `error_ratio`. This file
  is the *declared* truth that flow-ui later draws measured values against.
- `scenarios/` — five scenarios: `baseline`, `black_friday`, `failure_spike`,
  `latency_degradation`, `stalled_job`. Scenarios compose via `extends` + `phases`.
- `provider_profiles/gcp.yaml` — the cloud-attribute shape being imitated.
- `clickhouse_schema.yaml` — schema for the legacy direct-write path.

CLI surface (`src/otelgen/cli.py`): `--mode backfill|stream`, `--delivery otlp|direct`,
`--scenario`, `--window`, `--step`, `--rate`, `--duration`, `--seed` (determinism),
`--dry-run`, `--init-schema`, plus OTLP transport flags (`--otlp-protocol grpc|http/protobuf`,
`--otlp-insecure/--otlp-secure`, `--otlp-api-key`, `--otlp-header`). Runs as non-root
`appuser`. In Compose it has **no long-running command** — it is invoked on demand via
`docker compose run --rm generator` from `make generate` / `make generate-stream`.

**2. `services/collector-rust` — Pod 2, the OTLP→ClickHouse collector. The selected
implementation.**

Rust 2021, crate `sentinel-collector` v0.1.0-alpha, toolchain pinned to **1.96.0** via
`services/collector-rust/rust-toolchain.toml` (with the `x86_64-unknown-linux-musl` target
added). ~3,900 lines across 10 modules in `src/`, plus 4 integration test files. Key
dependencies (`Cargo.toml`): `tonic` 0.12 + `prost` 0.13 (gRPC), `opentelemetry` /
`opentelemetry_sdk` / `opentelemetry-otlp` / `opentelemetry-proto` 0.27, `tokio` 1.40
(`features = ["full"]`), `clickhouse` 0.13 (`lz4`, `time`), `hyper` 1.x + `hyper-util` for the
`/metrics` server, `prometheus` 0.13 with `default-features = false`, `tracing` +
`tracing-subscriber`, `serde`/`serde_yaml`, `anyhow`/`thiserror`.

Module map: `grpc.rs` (OTLP receiver + `apply_validation`), `otlp.rs` (wire→`Signal`
transformation, the largest module at 804 lines), `contract.rs` (contract model +
`Signal::validate`), `buffer.rs` (bounded buffered export), `clickhouse_exporter.rs`
(RowBinary insert), `config.rs`, `metrics.rs` + `metrics_server.rs`, `lib.rs`, `main.rs`.

**Run modes are selected by config shape, not by a flag** (`src/main.rs:60-64` — `match
config.grpc { Some(_) => serve_grpc, None => run }`). This is a real operational trap worth
naming:
- **SERVER mode** — a `grpc:` section is present → long-running OTLP gRPC receiver. This is
  what `config.docker.yaml` selects.
- **FILE mode** — no `grpc:` section → read `input` once, process, exit.
- Orthogonally, **export vs count/log-only**: a `clickhouse:` section (or `CLICKHOUSE_URL`)
  present → write to ClickHouse; absent → parse and tally only.

**Receive-boundary contract validation is policy-gated**, and the two paths use *different*
policies — a subtlety to carry forward:
- gRPC path: `contract.grpc_validation` is a three-valued enum (`src/config.rs:208-227`) —
  `off` (skip), `warn` (**default**, verified by the unit test
  `grpc_validation_defaults_to_warn` at `src/config.rs:547`), `strict` (validate and **drop**
  violators).
- File path: `contract.strict` is a boolean, all-or-nothing — any violation aborts the run
  before export (`src/config.rs:184`).

`warn` is the deliberate default because foreign OTLP legitimately lacks Sentinel's five
`sentinel.*` resource keys, and `strict` would silently discard it. Live config
(`config.docker.yaml`) sets `expected_version: "1.0.0"`, `grpc_validation: warn`, JSON logging
at `info`.

Exposed Prometheus metrics (`src/metrics.rs:307-311`): `sentinel_signals_ingested_total`,
`sentinel_batch_flush_total`, `sentinel_batch_flush_size`, `sentinel_export_errors_total`,
`sentinel_export_latency_seconds`.

**3. `services/flow-ui` — "the pipeline watching itself".**

FastAPI ≥0.115 + Uvicorn on `:8080` (`services/flow-ui/pyproject.toml`, hatchling-built,
Python ≥3.11). Dependencies deliberately minimal: `fastapi`, `uvicorn[standard]`, `jinja2`,
`httpx`, `pyyaml`. **No front-end framework, no bundler, no `package.json`** — ~1.7k lines of
plain ES2020 + SVG in `src/flow_ui/static/app.js`, one hand-written stylesheet where (per
`ARCHITECTURE.md`) no CSS value names a colour, so a two-palette switch re-tests every colour
decision.

Architecture (`services/flow-ui/ARCHITECTURE.md`): one `Poller` (`pipeline.py`) is the sole
writer of a single in-memory `Snapshot`, running **three cadences** chosen by query cost — 1 s
against the collector's `/metrics`, 5 s and 30 s against ClickHouse. Jinja2 renders the full
figure server-side *before any script runs*, then SSE (`/stream`, 1 frame/s) pushes
subsequent ticks. Routes (`src/flow_ui/main.py`): `GET /`, `GET /stream`, `GET /api/snapshot`,
`GET /api/graph`, `GET /api/history`, `GET /healthz`.

**Read-only posture, and it is structural rather than merely intended.** flow-ui issues no
writes. It reads the collector's `/metrics`, queries `bronze.*` and `silver.*`, and reads two
files mounted **`:ro`** in Compose: Pod 1's `config/` (the declared topology) and the
collector's own `config.docker.yaml`. Reading the config files rather than restating their
contents is what prevents the drawn picture from drifting from the thing it draws — notably
`contract.grpc_validation`, which is not exposed as a metric and can only be learned from the
file that sets it. The browser never contacts ClickHouse or the collector directly: neither
sets a CORS header, so a cross-origin fetch would be blocked — documented in
`docker-compose.yml` and pinned by a test. Four boards: *Flow*, *Health*, *Contract* (what
`strict` would drop, and which producers violate), *Watchers* (rows/min per producer against a
band, where the drawn band **is** the alerting rule). `silver.service_health_1m` supplies
per-producer latency and error rate, drawn as *declared → measured* against what
`topology.yaml` claims.

Nothing in the pipeline depends on flow-ui being up.

**4. `contracts/` — the contract registry, namespaced by producing Pod.**

Not an application component, but architecturally load-bearing, so it belongs here. Two
boundaries, versioned independently by directory:

| Boundary | Location | Version | State |
|---|---|---|---|
| Pod 1 → Pod 2 (OTLP input) | `contracts/generator/v1/` | `1.0.0` | **frozen** |
| Pod 2 → Pod 3 (bronze read) | `contracts/collector/v1/pod2-pod3-read-contract.md` | **`1.0.0.1`** | authoritative boundary; **Pod 3 sign-off still pending** |

`generator/v1` holds `schema/otlp_output.schema.json` (the JSON Schema) and
`golden/baseline_seed42.jsonl` (the canonical golden fixture, seed 42, baseline scenario) used
by the collector's golden and round-trip tests. Consumers resolve it through `CONTRACTS_DIR`
(`/contracts/generator/v1` in containers; `./contracts:/contracts:ro` in Compose) — one copy,
no per-service duplicates.

The Pod 2 → Pod 3 contract is unusual and worth preserving as a pattern: the **DDL is the
contract** (ADR-0007, superseding ADR-0005). `infra/clickhouse/init.d/01-bronze-otel.sql` is the
structural source of truth; the markdown document is the *semantic* layer on top of it — which
columns Pod 2 populates and guarantees, where Sentinel metadata lives, and the conventions raw
DDL cannot express. Because it is expressed in terms of the schema rather than the
implementation, it survives a collector swap.

* **Infrastructure & Cloud Resources:**

**There are no cloud resources. There is no IaC. The baseline infrastructure is
`docker-compose.yml` on a developer's machine.** The evidence table in §1 is the whole of it.

**Compute** — four Compose services, no replicas, no resource limits, no restart policies:

| Service | Image | Ports (host:container) | Depends on |
|---|---|---|---|
| `clickhouse` | `clickhouse/clickhouse-server:24.3` (upstream) | `8123:8123` (HTTP + `/play`) | — |
| `collector-rust` | built locally → `sentinel-collector-rust:dev` | `4317:4317` (OTLP gRPC), `9090:9090` (Prometheus) | `clickhouse` (`service_healthy`) |
| `flow-ui` | built locally → `sentinel-flow-ui:dev` | `8080:8080` | `clickhouse` healthy + `collector-rust` started |
| `generator` | built locally → `sentinel-generator:dev` | none | — (on-demand `run --rm`) |

**Networking** — the Compose default bridge network only. `collector-rust` carries the network
alias `collector`, which is why `http://collector:4317` and `http://collector:9090/metrics`
resolve for the generator and flow-ui. The collector binds `[::]:4317` — all interfaces
(`config.docker.yaml`). Three ports are published to the host; no reverse proxy, no ingress, no
service mesh, no TLS terminator.

**Storage** — one named Docker volume, `clickhouse_data`, mounted at `/var/lib/clickhouse`.
That is the entirety of persistence. No backup, no snapshot, no replication, no off-host copy.
`make reset` (`docker compose down -v`) destroys it.

**Health checking** — only ClickHouse has a healthcheck (`wget --spider` against
`/?query=SELECT+1`, 5 s interval, 3 s timeout, 20 retries). Neither the collector nor flow-ui
declares one, although flow-ui serves `/healthz` and could. `collector-rust` is gated only on
`service_started`, not readiness **(inferred: a cold-start race is possible but has not been
observed in the recorded snapshots)**.

**ClickHouse bootstrap** — three SQL files bind-mounted read-only into
`/docker-entrypoint-initdb.d/`, applied in filename order **on first boot of an empty volume
only**:
1. `infra/clickhouse-init.sql` → `CREATE DATABASE bronze` + the vestigial `otelgen` user.
2. `infra/clickhouse/init.d/01-bronze-otel.sql` → the bronze layer.
3. `infra/clickhouse/init.d/02-silver-layer.sql` → the silver layer.

Plus `infra/clickhouse-users.d/zz-default-network.xml` mounted into
`/etc/clickhouse-server/users.d/`, which overrides the image's localhost-only restriction on
the `default` user (see §5).

**Two additional, non-canonical Compose files exist and are a drift hazard**
(**inferred** — nothing marks them superseded):
- `services/collector-rust/infra/docker-compose.yml` — a standalone ClickHouse **25.4** (vs
  24.3 at root), exposing both `8123` and native `9000`. It *is* load-bearing: `rust-ci.yml`
  starts the integration job from it.
- `services/generator-python/docker-compose.yaml` — the generator's own older stack: ClickHouse
  with the `otelgen`/`otelgen_secret` credentials, plus a `clickhouse/clickstack-all-in-one`
  (HyperDX) service that bundles its own ClickHouse + collector + UI on port 8080, colliding
  with flow-ui's port. Three ClickHouse definitions and three versions across the repo.

**Data layers.**

*Bronze* (`infra/clickhouse/init.d/01-bronze-otel.sql`) — raw OTel landing tables, pinned
column-for-column to `opentelemetry-collector-contrib` v0.105.0 (`SHOW CREATE TABLE`, captured
2026-06-09), with metrics split by data-point type. All `MergeTree`, 30-day TTL, ZSTD + Delta
codecs, `ttl_only_drop_parts = 1`. Eight objects:

| Object | Populated? |
|---|---|
| `bronze.otel_traces` | **live** |
| `bronze.otel_logs` | **live** |
| `bronze.otel_metrics_gauge` | **live** |
| `bronze.otel_metrics_sum` | **live** |
| `bronze.otel_traces_trace_id_ts` + `_mv` | live (trace-id index) |
| `bronze.otel_metrics_histogram` | **empty by contract** |
| `bronze.otel_metrics_exponential_histogram` | **empty by contract** |
| `bronze.otel_metrics_summary` | **empty by contract** |

The three empty tables are a *known gap*, not a defect: contract v1.0.0 defines no
histogram/summary type, so the generator never emits one (README §9 item 5).

Ownership policy: the DDL is **Pod-3-owned** and the collector issues **no DDL** — it only
`INSERT`s. The repo calls this `create_schema:false`, borrowing the contrib exporter's flag
name; `CLAUDE.md` is explicit that it is not a literal key in the Rust config. Attribute values
arrive stringified inside `Map(LowCardinality(String), String)` — the exporter's wire contract;
typing happens in silver.

*Silver* (`infra/clickhouse/init.d/02-silver-layer.sql`, ADR-0010) — three typed tables
(`operation_executions`, `log_events`, `metric_observations`), four materialized views feeding
them, and six read views (`metric_rollup_1m`, `service_health_1m`, `log_health_1m`,
`trace_summary`, `telemetry_coverage_1m`, `run_summary`).

**Two caveats on silver that must survive into any deployment plan**, both stated in the DDL
header and in `.claude/CLAUDE.md`:
1. **The MVs do not `POPULATE`.** They see new inserts only. The file's own guidance: deploy
   this DDL *before* enabling ingestion; for existing bronze data use an explicit, range- and
   dedup-controlled backfill. A real observed consequence is recorded in
   `services/flow-ui/src/flow_ui/clickhouse.py:366` — `bronze.otel_traces` held 1,703,050 rows
   over 36 hours while `silver.operation_executions` held 12,849 over 12 minutes.
2. **"Defined" ≠ "deployed."** The DDL runs on ClickHouse *first* boot. A volume predating the
   merge will not have silver at all. flow-ui is written to tolerate this: its silver reader
   returns `[]` when `silver.*` is absent, which it calls "the normal state of any stack whose
   volume predates the merge."

This is also why flow-ui still derives contract violations, volume bands and call edges from
bronze rather than silver — moving them would forfeit the history they depend on
(tracked as issue #37).

* **Deployment & Delivery (CI/CD):**

**There is no delivery. There is CI, for one of three services, and it ships nothing.**

The real operator interface is the `Makefile` — 20 targets, every one of which runs inside
Docker so no host toolchain is required (`DK_RUN := docker run --rm --user $(id -u):$(id -g) -v
"$(CURDIR)":/w`):

| Target | What it actually does |
|---|---|
| `up` | `docker compose up -d --build clickhouse collector-rust` |
| `init` | **a no-op** — echoes that bronze auto-applies on ClickHouse boot |
| `generate` | `compose run --rm generator` → backfill, `SCENARIO`/`SEED`/`WINDOW` |
| `generate-stream` | wall-clock-paced run — `DURATION`/`STEP`/`RATE` |
| `e2e` | `up` + `init` + `generate` |
| `ui` | `compose up -d --build flow-ui` |
| `ps` / `logs` / `down` | status · tail collector · stop |
| `reset` | `docker compose down -v` — **drops the volume** |
| `build` | `docker compose build` (local tags only; no push) |
| `test` | `test-generator` + `test-collector-rust` + `test-flow-ui` |
| `test-silver` | pipes `infra/clickhouse/tests/02-silver-layer.test.sql` into `clickhouse-client` |
| `sample-silver` | prints representative silver rows |
| `lint` | `lint-generator` + `lint-collector-rust` + `lint-flow-ui` |

Defaults: `SCENARIO=baseline`, `SEED=42`, `WINDOW=5m`, `DURATION=60s`, `STEP=1s`, `RATE=200`.

**What actually gates a pull request — exactly two workflows:**

`.github/workflows/rust-ci.yml`, path-filtered to `services/collector-rust/**`, `infra/**` and
itself (so a Python-only or docs-only PR does not trigger it), with `concurrency` cancelling
superseded runs. Four jobs:
1. **gates** — `cargo fmt --all -- --check`; `cargo clippy --all-targets --all-features -D
   warnings`; `cargo test --locked`; `cargo build --release --locked`.
2. **integration** — brings up a real ClickHouse from
   `services/collector-rust/infra/docker-compose.yml --wait`, then runs
   `cargo test --test clickhouse_roundtrip -- --ignored`, then tears it down `if: always()`.
3. **supply-chain** — `EmbarkStudios/cargo-deny-action@v2`, `check --all-features`.
4. **docker-build** — builds the distroless image with buildx and GHA cache, **`push: false`**.

`.github/workflows/pr-linked-issue.yml` — requires a PR to close an issue, reading
`closingIssuesReferences` (so a bare `#n` mention does not satisfy it; that trap is the point),
with a `no-issue` label as a deliberate, attributable escape hatch. It re-runs on `edited` and
`labeled`, so a PR fixed after failing goes green.

**What does not gate anything.** The team's working agreement names seven CI gates (ruff ·
mypy --strict · pytest >80% · bandit + safety · markdownlint · CodeRabbit · Docker build).
`.claude/CLAUDE.md` is blunt about the discrepancy: those seven are *"a target, not a
description: none runs."* Concretely, **no workflow executes any Python test or lint.** The
generator's 175 pytest functions, flow-ui's 71, the ruff configs, and the silver SQL assertion
suite all gate **nothing** — tracked as issue #34. README §7 names the missing Python gate as
an open item. There is no `pre-commit` configuration in the tree.

**Image delivery:** none. All three images are built locally and tagged `:dev`
(`sentinel-collector-rust:dev`, `sentinel-flow-ui:dev`, `sentinel-generator:dev`). No registry
is referenced anywhere; CI explicitly does not push. There is no versioning scheme tying an
image to a commit **(inferred from the absence of any tagging logic)**.

Build strategies per Dockerfile:
- `services/collector-rust/Dockerfile` — multi-stage, multi-arch (`TARGETARCH` → musl triple),
  dependency-layer caching via a throwaway `fn main(){}` build, a `touch` on the real sources
  (documented in-file as *required*, or cargo would ship the dummy binary), producing a fully
  static musl binary on `gcr.io/distroless/static-debian12:nonroot` — no libc, no shell, no
  package manager, non-root. The dependency tree is deliberately pure Rust (`prometheus` with
  `default-features = false`; no `*-sys`, OpenSSL or ring) precisely so this is possible. This
  is the strongest single artifact in the baseline's security posture.
- `services/generator-python/Dockerfile` and `services/flow-ui/Dockerfile` —
  `python:3.12-slim`, `pip install --no-cache-dir .`, both creating and dropping to a non-root
  `appuser`. Single-stage, unpinned base tag.

**Branching and review** (`README.md` §7, `.claude/CLAUDE.md`, ADR-0009): `main` protected;
`feat/|fix/|chore/|docs/` branches; Conventional Commits; signed commits (`-S`); mandatory
attribution trailers naming both the human and the LLM model; 2 approvals (peer + Captain).
ADR-0009 adds an agent-fleet flow — *seam → swimlane → leg → task*, one `git worktree` per
agent under `.worktrees/`, branches `leg/<area>/<task>-v<n>`, every leg declaring **disjoint
paths** before it opens, and a **merge commit** into `main` so per-leg attribution survives.
That merge-commit rule amends the WoW's squash-to-main rule and is **pending ratification**.
Whether branch protection is actually configured on the remote is not determinable from the
tree — `[TBD]`.

* **Observability:**

Sentinel observes itself, which makes this section unusually substantive for a project at this
stage — and also the clearest demonstration of the gap between *instrumented* and *monitored*.

**Metrics.** The collector exposes Prometheus text on `:9090/metrics` via a hand-rolled hyper
1.x server (`src/metrics_server.rs`, 249 lines): `sentinel_signals_ingested_total`,
`sentinel_batch_flush_total`, `sentinel_batch_flush_size`, `sentinel_export_errors_total`,
`sentinel_export_latency_seconds`. One shared Prometheus registry is threaded through the gRPC
handlers, the buffered exporter's flush loop and the HTTP server (`src/main.rs`). **There is no
Prometheus server, no Grafana, no Alertmanager, and no scrape configuration in this
repository.** The only consumer is flow-ui, polling every second. Nothing stores the series;
history exists only in flow-ui's in-memory `Snapshot` and dies with the process.

**Logging.** Structured `tracing` + `tracing-subscriber` with the `json` and `env-filter`
features; `config.docker.yaml` sets `level: info, format: json`. Logs go to container stdout
and are read with `docker compose logs` / `make logs`. **No log aggregation, no retention, no
shipping.** The generator and flow-ui use standard Python logging (`--log-level` on the
generator CLI).

**Tracing.** Sentinel ingests OTLP traces as its *subject matter* — `bronze.otel_traces`,
`silver.operation_executions`, `silver.trace_summary`. It does **not** emit traces about its own
operation. Note the asymmetry: the collector has the `opentelemetry-otlp` exporter in its
dependency tree, but self-instrumentation is metrics-only.

**The self-watching layer.** flow-ui is the de facto monitoring surface, and its design makes a
point worth carrying into the next cycle: on the *Watchers* board, the band drawn around
rows/min per producer **is** the alerting rule, not a picture of one; on the ORIGIN nodes,
`topology.yaml`'s *declared* latency sits beside the *measured* value from
`silver.service_health_1m`. Silver is drawn as a **derivation, not a pipe** — ADR-0010's MVs
fire inside ClickHouse on the same insert, so there is no hop to draw.

**What is missing, stated plainly.** No alerting of any kind. No paging, no on-call, no SLOs,
no error budgets, no uptime monitoring, no distributed tracing of Sentinel itself, no metrics
persistence. `/healthz` on flow-ui is the only health endpoint in the stack and nothing polls
it — not even Compose, which declares no healthcheck for that service. This is coherent for a
local development baseline and would be the first gap to close on any path toward a deployed
system.

---

## 3. The New Intent (To-Be)

* **Scope of Changes:**

  **`[TBD]` — this is the owner's to declare, and this document deliberately does not guess
  it.** Nothing in the repository states what the next SDLC cycle contains.

  What follows is **not a proposed roadmap**. It is an inventory of work the repository *itself*
  already names as unfinished, gathered so that scoping can start from evidence rather than
  from recall. Each item cites where the repo names it. **Every one is a candidate awaiting a
  decision; none is in scope until the owner puts it there.**

  *Candidate A — Close the deployment gap (not named by the repo; the largest structural gap).*
  There is no IaC, no orchestration, no deployment pipeline and no registry. If "production"
  is genuinely the destination, this is the precondition for most of the rest of §5 and §6
  being answerable at all. `.claude/CLAUDE.md` names GCP as the first cloud target; nothing
  commits to a compute form (GKE, Cloud Run, VMs), and `README.md` §7 records that **ClickHouse
  operational ownership is still unassigned** — on a managed-ClickHouse-vs-self-hosted
  question, that unassigned ownership is the blocker, not the technology choice.

  *Candidate B — CI coverage for the two Python services (repo-named: issue #34, README §9
  item 6).* 246 Python test functions and three lint configs gate nothing today. This is the
  cheapest high-value item in the list **(inferred)**: the suites, the Docker-based runners and
  the Make targets already exist; only workflow files are missing.

  *Candidate C — Resolve the documented decision-record drift (repo-named: `CLAUDE.md` *Known
  doc drift* table, README §9 items 1, 2 and 7).* Specifically: ADR-0004 → `Accepted` with a
  Rust-selection note; ADR-0007 Pod 3 sign-off (which is what gates the Pod 2 → Pod 3 contract
  moving from "agreed boundary" to accepted); ADR-0006/0008/0010 ratification; the unratified
  Pod↔layer mapping (README's POD3 = storage/read-layer vs `.claude/CLAUDE.md`'s B3 =
  watchers); and ADR-0009's merge-commit amendment to the WoW. Note that the drift table
  assigns each of these an owner — these are not unowned.

  *Candidate D — Pod 3 silver completion (repo-named: `CLAUDE.md` "Open", README §8).* The DDL
  and read views exist; the rolling-stats rollup and the read models for the first Watchers are
  marked in progress.

  *Candidate E — Silver backfill, and migrating flow-ui's bronze-derived boards (repo-named:
  issue #37).* The MVs do not `POPULATE`; the DDL asks for an explicit range- and
  dedup-controlled backfill. Until that exists, moving flow-ui's contract-violation, volume-band
  and call-edge derivations off bronze would drop the history they depend on.

  *Candidate F — Histogram / summary / exponential-histogram metrics (repo-named: README §9
  item 5).* Three bronze tables are empty by contract because v1.0.0 defines no such type.
  Filling them is a **contract change**, which under the registry's own rule means
  `contracts/generator/v2/` for a breaking change, or an additive edit to `v1` with the
  schema's `version` and the generator's `CONTRACT_VERSION` kept in sync.

  *Candidate G — The detection spine beyond stage 1 (repo-named as a future phase).* Watchers,
  the three-tier cascade, policy engine, remediation, audit log, feedback loop. This is the
  stated product; it is also by far the largest item, and the one most dependent on the
  Pod↔layer mapping in Candidate C being ratified first **(inferred)**.

  *Candidate H — Baseline security hardening.* See §5; the repo names the individual facts
  (dev-only auth, vestigial user) but does not frame them as a work item.

  *Candidate I — Housekeeping with real drift risk.* Drop the vestigial `otelgen` ClickHouse
  user (`infra/clickhouse-init.sql` marks it *"safe to drop"*); reconcile the three ClickHouse
  definitions across three Compose files on two versions (24.3 vs 25.4), including the HyperDX
  service whose port 8080 collides with flow-ui.

* **Out of Scope:**

  **`[TBD]`** — a scope cannot be bounded before it is declared.

  Two things are worth recording as *standing* exclusions, because both are repository policy
  rather than cycle-specific choices, and both are easy for a new contributor (or an agent) to
  violate while trying to be helpful:

  1. **Historical records are not to be "fixed."** `CLAUDE.md`, `.claude/rules/pre-pr-discipline.md`
     and the files themselves all say so: `docs/adr/0*`, `.claude/sdd/**`, `docs/proposals/`,
     `docs/research/` and `docs/clickhouse-schema-divergence*.md` are point-in-time artifacts.
     They mention the Go collector *by design* and carry superseded banners. An ADR that weighs
     Go against Rust remains correct even though `services/collector-go/` was deleted in PR #28;
     rewriting it destroys what makes the decision readable. Only documents asserting the
     **present** are ever in scope.
  2. **flow-ui stays a reader.** Its read-only posture is load-bearing — nothing in the
     pipeline depends on it being up, which is what makes it safe to break.

---

## 4. Technical Requirements & Dependencies

* **Required Integrations:**

  **Internal (all four exist and are exercised):**

  | Integration | Transport / contract | Evidence |
  |---|---|---|
  | generator → collector | OTLP **gRPC `:4317`**, validated against `contracts/generator/v1` v1.0.0 (frozen) | `docker-compose.yml`, `src/grpc.rs` |
  | collector → ClickHouse | **HTTP `:8123`**, RowBinary via the `clickhouse` 0.13 crate | `src/clickhouse_exporter.rs`, `config.docker.yaml` |
  | collector → flow-ui | Prometheus text on `:9090/metrics`, polled at 1 s | `src/metrics_server.rs`, `pipeline.py` |
  | ClickHouse → flow-ui | HTTP `:8123`, read-only TSV queries over `bronze.*` + `silver.*` at 5 s / 30 s | `src/flow_ui/clickhouse.py` |

  **A port gotcha worth restating because it has bitten before** (`CLAUDE.md` *Gotchas*): the
  `clickhouse` crate speaks RowBinary over **HTTP :8123**, *not* native `:9000`, despite the
  wire format being ClickHouse's binary format rather than JSON. The root Compose therefore
  publishes only `8123`.

  **Third-party runtime dependencies:** exactly one external image —
  `clickhouse/clickhouse-server:24.3` from Docker Hub. Everything else is built from source in
  this repository. Base images pulled at build time: `rust:1.96-slim-bookworm`,
  `gcr.io/distroless/static-debian12:nonroot`, `python:3.12-slim`. CI additionally pulls
  `ghcr.io/astral-sh/ruff:latest` (via the Make targets) and GitHub Actions
  (`actions/checkout@v4`, `Swatinem/rust-cache@v2`, `EmbarkStudios/cargo-deny-action@v2`,
  `docker/setup-buildx-action@v3`, `docker/build-push-action@v6`).

  **No external APIs are called.** No SaaS, no cloud SDK, no LLM provider, no secrets backend,
  no identity provider. The LLM tiers in the detection cascade and the `OTELGEN_OTLP_API_KEY` /
  `--otlp-api-key` hooks (for a HyperDX-style ingestion endpoint in the generator's own legacy
  Compose) are *capabilities*, unconfigured and unused.

  **Cloud integrations: none.** Restating it because the framing invites the opposite
  assumption — GCP appears in this repository exclusively as *imitated attribute shapes*
  (`provider_profiles/gcp.yaml`, GCP-flavoured service names in `topology/default.yaml`).

* **Prerequisites:**

  **Tooling — the baseline is deliberately a one-dependency setup.** Docker (with Compose v2
  and BuildKit) and `make`. That is all: every build, test and lint target runs inside a
  container as the invoking UID/GID, so **no host toolchain is required** — a stated convention
  in `CLAUDE.md` and visible in every `Makefile` target. This is a genuine strength of the
  baseline and worth not regressing.

  Optional, for working outside Docker: Rust **1.96.0** (auto-installed in
  `services/collector-rust/` by `rust-toolchain.toml`, with `rustfmt`, `clippy`, `rust-docs`,
  `rust-analyzer` and the `x86_64-unknown-linux-musl` target); Python ≥3.10 for the generator
  and ≥3.11 for flow-ui; `cargo install --locked cargo-deny`; `just` (the collector ships a
  `justfile`). Multi-arch image builds need `docker buildx` (the Dockerfile documents
  `--platform linux/amd64,linux/arm64`).

  **Access rights:** a GitHub account with push access to
  `github.com/luanmorenommaciel/sentinel`; a GPG/SSH signing key (commits are signed, `-S`);
  and, under the WoW, two approvals per PR (peer + Captain). **No cloud credentials exist or
  are needed** — there is nothing to authenticate to.

  **Cluster resources: `[TBD]` / not applicable.** There is no cluster. The local stack's
  footprint is one ClickHouse container plus two or three small services; no resource limits or
  requests are declared anywhere, so there is no sizing statement to report. A `[TBD]` here is
  the honest answer, not a placeholder for one.

  **Operational prerequisites that will bite if skipped:**
  - **Stale ClickHouse volume.** `CREATE TABLE IF NOT EXISTS` will not update a changed schema.
    After any DDL change: `make reset` **before** `make up`, or inserts fail with
    `NO_SUCH_COLUMN` (`CLAUDE.md` *Gotchas*).
  - **Silver ordering.** Deploy the silver DDL *before* enabling ingestion, or backfill
    explicitly — the MVs do not `POPULATE` (`02-silver-layer.sql:1-9`).
  - **Collector mode.** A config without a `grpc:` section runs FILE mode (read `input` once,
    exit) rather than failing — a silent misconfiguration, not a loud one.
  - **Agent fleets.** Export a shared `CARGO_TARGET_DIR` before running one, or N worktrees
    means N cold Rust builds (`CLAUDE.md`).

---

## 5. Security & Compliance

Framed as the template asks, with one unavoidable adjustment: **there is no IAM or RBAC today,
so there are no "changes" to describe.** What follows is the *baseline posture* and what would
have to exist. The "changes" line is `[TBD]` pending §3.

* **Access Control:**

  **Changes to IAM / RBAC: `[TBD]`** — undeterminable until the new intent is declared, and
  meaningless until a deployment target exists. No IAM policy, RBAC rule, service account,
  Workload Identity binding, OIDC trust or role definition exists anywhere in the tree.

  **Baseline findings — stated as findings, not as a design:**

  1. **ClickHouse `default` user is passwordless and opened to the whole Docker network.**
     The official image ships `users.d/default-user.xml` restricting `default` to `::1` and
     `127.0.0.1`. `infra/clickhouse-users.d/zz-default-network.xml` overrides that with
     `<networks replace="replace"><ip>::/0</ip></networks>` so the collector can connect as
     `default` over `http://clickhouse:8123`. The file labels itself *"Dev/local only — do not
     expose this ClickHouse beyond the compose network."* Credit where due: the constraint is
     documented at the point of override rather than discovered later. It is still the single
     most load-bearing security assumption in the baseline — the whole posture rests on the
     stack never leaving a laptop.

  2. **A vestigial privileged user with a plaintext password is committed to the repository.**
     `infra/clickhouse-init.sql:15-17` creates `otelgen` `IDENTIFIED WITH plaintext_password BY
     'otelgen_secret'` and grants it `ALL ON bronze.*` **and** `ALL ON default.*`. The file
     documents that it existed for the deleted Go collector's DSN and is *"safe to drop."*
     Nothing uses it today. The same credential is hard-coded in
     `services/generator-python/docker-compose.yaml:17,63`. Low real risk (dev-only, no
     deployment, well-known value) — but it is a committed plaintext credential that outlived
     its consumer, which is exactly the shape of thing that survives into a first deployment.

  3. **No authentication, authorization or transport security on any service boundary.**
     - OTLP `:4317` — plaintext gRPC, no TLS, no token, no mTLS. A repository-wide grep for
       `tls`, `ServerTlsConfig` or `certificate` in `src/grpc.rs`, `src/config.rs` and
       `src/clickhouse_exporter.rs` returns **zero matches**. Anything that can reach the port
       can inject telemetry. The collector binds `[::]:4317` (all interfaces) and the port is
       published to the host.
     - ClickHouse `:8123` — published to the host, passwordless `default`, HTTP not HTTPS. The
       `/play` UI is reachable at `http://localhost:8123/play` with no credential.
     - flow-ui `:8080` — no auth. It is read-only, so exposure is disclosure rather than
       mutation; its SSE stream and `/api/*` routes will serve pipeline topology and metrics to
       anyone who can reach the port.
     - The collector's `/metrics` `:9090` — no auth.

  4. **No secrets management of any kind.** No Secret Manager, Vault, SOPS, sealed-secrets or
     `.env` convention. Configuration is plaintext YAML bind-mounted read-only; the only
     credential in the system is the one in item 2.

  **What the baseline does well, and should be preserved rather than rediscovered:**
  - **Distroless static runtime for the collector** — `gcr.io/distroless/static-debian12:nonroot`
    with a fully static musl binary: no libc, no shell, no package manager, non-root. Near-zero
    runtime attack surface, and the pure-Rust dependency tree (no `*-sys`, OpenSSL or ring) is
    what makes it achievable.
  - **All three services run as non-root.** Both Python images create and drop to `appuser`;
    the collector image uses the distroless `nonroot` user.
  - **Supply-chain gating on the Rust path** — `cargo-deny` in CI with `deny.toml`:
    `yanked = "deny"`, an explicit license allow-list (Apache-2.0, MIT, BSD-2/3, ISC,
    Unicode-DFS-2016, Unicode-3.0, Zlib — copyleft denied by omission),
    `confidence-threshold = 0.93`, `wildcards = "deny"`, registry restricted to crates.io, and
    advisories ignorable only with an issue link. Both `Cargo.lock` and `--locked` builds are
    used throughout.
  - **A lint policy with teeth** — `unsafe_code = "forbid"` and `clippy::unwrap_used = "deny"`
    (with `expect_used = "warn"`) in `Cargo.toml`; `cargo clippy -D warnings` in CI; and a
    notable custom rule in `clippy.toml` that **disallows `std::env::var` in production code**
    so configuration must flow through the auditable config loader. `pedantic`/`nursery`/
    `missing_docs` are present but commented out, honestly labelled *aspirational* pending a
    cleanup PR for ~50 existing warnings.
  - **All eight config and contract bind mounts are `:ro`.**
  - **The `generator-python` image bakes config and the generator reads contracts read-only**,
    so a container cannot rewrite the contract it validates against.

  **Supply-chain asymmetry worth naming:** the Rust path has advisory, license and ban gating
  in CI; the Python path has **none** — no `pip-audit`, no `safety`, no `bandit`, and unpinned
  dependency floors (`>=`) with no lockfile for either Python service. The WoW names `bandit +
  safety` as a gate; it does not run (issue #34).

* **Data Handling:**

  **Encryption:** none, anywhere. No TLS in transit on any of the four hops (OTLP gRPC,
  collector→ClickHouse HTTP, flow-ui→ClickHouse HTTP, flow-ui→`/metrics` HTTP). No encryption at
  rest — the `clickhouse_data` Docker volume is plain disk. Data is *compressed* (ZSTD(1) with
  Delta codecs throughout bronze and silver), which is a storage property, not a security one.

  **Privacy: the baseline's strongest compliance fact is that all data is synthetic.** Every
  row originates from `otelgen` running a declared topology and scenario against a seeded RNG
  (`--seed`, default 42 in the Makefile). There is no real user data, no PII, no customer
  telemetry, and no third-party data in the system. Signals carry a `sentinel.is_synthetic`
  marker (surfaced as `is_synthetic Bool` in `silver.operation_executions`). **That property
  holds only until the synthetic-to-real swap** — the first ingestion of real GCP telemetry
  changes the compliance position of this entire section at once, and nothing in the current
  design would flag that transition.

  **Retention:** a **30-day rolling TTL**, uniform across bronze and silver
  (`TTL toDateTime(...) + toIntervalDay(30)`, `SETTINGS ttl_only_drop_parts = 1`, attributed to
  ADR-002 in the bronze DDL header). Ownership is explicit: retention lives in the DDL, not in
  collector config. No tiering, no archival, no cold storage.

  **Data classification, residency, DSR/erasure handling, audit logging of access:** `[TBD]` —
  none exist, and none are required for synthetic data on a laptop. All four become live
  questions at the moment real telemetry is ingested.

  **Deletion:** `make reset` (`docker compose down -v`) destroys the volume and all data
  irrecoverably. There is no backup, so this is both the reset mechanism and the data-loss
  mechanism.

  **Data-integrity controls that do exist**, and are the baseline's real compliance-adjacent
  machinery: contract validation at the receive boundary (`off`/`warn`/`strict`, default
  `warn`); a frozen v1.0.0 input contract with a golden fixture; a versioned read contract whose
  source of truth is the DDL itself; and the audited-configuration rule enforced by the
  `std::env::var` ban.

---

## 6. SDLC & Deployment Strategy

* **Testing Plan:**

  **What exists today** (counted directly from the tree; the slight differences from the counts
  in `CLAUDE.md` — 178 / 92+4 / 63 — reflect counting test *functions* rather than
  pytest-collected cases, which parametrisation expands):

  | Suite | Size | Runner | **Gates CI?** |
  |---|---|---|---|
  | `services/generator-python/tests/unit/` (10 files) | **175** test fns | `make test-generator` (pytest in Docker) | **No** |
  | `services/generator-python/tests/integration/` | ClickHouse E2E | pytest (skip-guarded) | **No** |
  | `services/collector-rust/src/**` inline | **92** `#[test]`/`#[tokio::test]` | `make test-collector-rust` (`cargo test --locked`) | **Yes** — `gates` job |
  | `services/collector-rust/tests/` (4 files) | **7** tests, **5** `#[ignore]`d | `cargo test`; ignored ones need a live DB | **Yes** — `gates` + `integration` jobs |
  | `services/flow-ui/tests/` (5 files) | **71** test fns | `make test-flow-ui` (pytest in Docker) | **No** |
  | `infra/clickhouse/tests/02-silver-layer.test.sql` | **18** `throwIf` assertions | `make test-silver` (needs a running stack) | **No** |

  Notable coverage shapes: the collector's integration tests cover a golden-fixture parse
  (`golden_parse.rs`), a gRPC smoke test (`grpc_smoke.rs`), a full gRPC export round-trip
  (`grpc_export_roundtrip.rs`, 311 lines) and a live ClickHouse round-trip
  (`clickhouse_roundtrip.rs`, run `--ignored` in the dedicated CI job against a real
  ClickHouse). The generator's suite includes `test_golden.py` and `test_output_contract.py` —
  contract-regression tests pinned to the frozen v1.0.0 schema and the seed-42 fixture, which
  is the mechanism that makes "frozen" mean something.

  **Lint / static analysis:** `cargo fmt --check` + `cargo clippy -D warnings` (CI-gated);
  ruff on all three Python-adjacent targets — generator `src`, flow-ui `src tests scripts` —
  with `line-length = 120` and `select = ["E","F","I","UP"]` (**not** CI-gated).

  **Security testing: `cargo-deny` only** (advisories, licenses, bans — Rust path, CI-gated).
  No SAST, no DAST, no dependency scanning on the Python path, no container-image scanning, no
  secret scanning configured in the repo.

  **Load testing: none as an automated suite.** The §8 snapshot (233,100 signals in 4.5 s,
  ~51.4k signals/s, 0 loss, 32.3 ms average export latency, 100% of flush attempts ≤80 ms) was
  produced by a manual `make generate` run and is explicitly caveated in the README as *"not a
  production SLO or a substitute for sustained-load benchmarking on target infrastructure."*
  A `bench-release` cargo profile exists (release optimisations + debug symbols for
  flamegraphs), so the intent to benchmark is scaffolded but unexercised.

  **The one honest gap to carry into planning:** 246 Python test functions and 18 SQL
  assertions currently gate nothing. Issue #34. Closing it needs workflow files, not tests —
  the suites, the Docker runners and the Make targets already exist **(inferred, but the
  Makefile makes it near-certain: `make test` and `make lint` already run everything in Docker
  with no host toolchain)**.

  **Additions for the new intent:** `[TBD]` — depends on §3. The shape of what is missing is
  determinate; what gets built is not.

* **Rollout Strategy:**

  **`[TBD]` — and not merely unstated: currently inapplicable.** Blue/Green, Canary and Rolling
  Update are all strategies for replacing running instances of a deployed service. There are no
  running instances, no orchestrator to roll, no load balancer to shift traffic and no
  registry of versioned images to roll between. Choosing among them is premature until
  Candidate A in §3 (or whatever replaces it) is decided.

  **The de facto rollout today**, documented so there is an accurate starting point:

  ```
  make build        # build all images locally, tagged :dev
  make up           # ClickHouse (healthcheck-gated) → collector-rust
  make generate     # on-demand generator run → OTLP :4317
  make ui           # optional: flow-ui on :8080
  # or, in one step:
  make e2e          # up + init (no-op) + generate
  ```

  Three properties of the local path are genuinely relevant to a future real rollout and worth
  carrying forward rather than re-deriving:
  1. **Ordering is enforced where it matters** — the collector waits on ClickHouse's
     `service_healthy` condition, because the bronze tables must exist before it connects
     (`create_schema:false`; the collector issues no DDL).
  2. **Schema-before-ingest is a hard requirement, not a preference** — the silver MVs do not
     `POPULATE`, so the DDL must land before ingestion is enabled or data is silently missed.
     Any future rollout sequence must apply DDL as a distinct, earlier step.
  3. **flow-ui is safe to deploy independently and in any order** — nothing depends on it.

  Open prerequisites for any real rollout, all `[TBD]`: target platform; image registry and
  tagging scheme; a ClickHouse migration tool (today's `IF NOT EXISTS` initdb scripts run on
  *first boot only* and cannot alter an existing schema — this is the single biggest obstacle
  to a non-destructive deployment, see *Rollback* below); configuration and secret delivery;
  and **ClickHouse operational ownership, which README §7 records as unassigned.**

* **Rollback Plan:**

  **`[TBD]` for a deployed system** — nothing to revert to, and no deployment history to revert
  through.

  **The de facto rollback for the local stack today is destructive, and that is the central
  finding of this section:**

  ```
  make down     # stop all services; the clickhouse_data volume survives
  make reset    # docker compose down -v — stop AND DROP THE VOLUME
  make up       # fresh boot: all three initdb SQL files re-apply from scratch
  ```

  `make reset` is the *only* reliable way to apply a changed schema, and it works by destroying
  all data. The mechanism, from `CLAUDE.md` *Gotchas*: the init scripts use `CREATE TABLE IF
  NOT EXISTS` and run only on first boot of an empty volume, so a changed DDL is silently
  ignored on an existing volume and inserts then fail with `NO_SUCH_COLUMN`. There is no
  migration tool, no versioned schema history, no `ALTER` path and no backup — so there is no
  non-destructive rollback for a schema change. For synthetic data this costs nothing. For real
  data it would be unacceptable, which makes a migration strategy a hard prerequisite for any
  deployment, not a later refinement.

  **Code rollback** is ordinary git: `main` is protected, history is preserved, and ADR-0009's
  merge-commit rule for swimlane→`main` (pending ratification) exists specifically so per-leg
  attribution survives — which also means a bad leg is revertable as a unit. One tag exists
  (`v0.0.1`) but there is no release process behind it and no image is tied to a commit, so
  "roll back to the previous version" has no artifact to name. Establishing commit-pinned image
  tags is the cheapest precondition for a real rollback plan **(inferred)**.

  **For the new intent:** `[TBD]`. Minimum viable rollback plan, once a target exists, would
  need: commit-pinned immutable image tags; a ClickHouse migration tool with forward and
  backward steps; a backup/restore path for `clickhouse_data` (today there is none); and a
  documented decision on whether bronze's 30-day TTL means a restore window shorter than the
  data's own lifetime.

---

## Appendix — Evidence index

Primary sources read for this baseline, in the order a reviewer would most usefully retrace
them:

| Claim area | Files |
|---|---|
| Topology, ports, volumes, mounts, healthchecks | `docker-compose.yml` |
| Operational entrypoints | `Makefile` |
| Collector deps, lint policy, profiles | `services/collector-rust/Cargo.toml`, `clippy.toml`, `deny.toml`, `rust-toolchain.toml` |
| Collector run modes, validation policy | `services/collector-rust/src/main.rs:60-64`, `src/config.rs:184-227,547`, `src/grpc.rs`, `src/metrics.rs:307-311` |
| Collector image strategy | `services/collector-rust/Dockerfile` |
| Generator CLI, deps, config surface | `services/generator-python/pyproject.toml`, `src/otelgen/cli.py`, `config/**`, `Dockerfile` |
| flow-ui stack, cadences, routes, read-only posture | `services/flow-ui/pyproject.toml`, `ARCHITECTURE.md`, `src/flow_ui/main.py`, `src/flow_ui/clickhouse.py:362-387,522`, `Dockerfile` |
| Contracts | `contracts/README.md`, `contracts/generator/v1/README.md` + `schema/` + `golden/`, `contracts/collector/v1/pod2-pod3-read-contract.md` |
| Data layers | `infra/clickhouse/init.d/01-bronze-otel.sql`, `02-silver-layer.sql`, `infra/clickhouse/tests/02-silver-layer.test.sql`, `infra/clickhouse/queries/02-silver-sample.sql` |
| ClickHouse bootstrap + auth | `infra/clickhouse-init.sql`, `infra/clickhouse-users.d/zz-default-network.xml` |
| CI reality | `.github/workflows/rust-ci.yml`, `.github/workflows/pr-linked-issue.yml`, `.github/PULL_REQUEST_TEMPLATE.md` |
| Status, open items, drift | `README.md` §7–§9, `CLAUDE.md` (*Known doc drift*) |
| ADR statuses (all read individually) | `docs/adr/0004`–`0010`, `docs/adr/README.md` |
| Process, mission, WoW | `.claude/CLAUDE.md`, `.claude/rules/pre-pr-discipline.md`, `.claude/rules/kb-enrichment.md` (read via `git show HEAD:…` — deleted in the working tree) |
| Non-canonical Compose files | `services/collector-rust/infra/docker-compose.yml`, `services/generator-python/docker-compose.yaml` |

*Baseline captured 2026-10-05 from branch `origin/sdlc-e2e-review` at `3af2ee7`.*
