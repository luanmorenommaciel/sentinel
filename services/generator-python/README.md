# OTel Data Generator

> Containerized, config-driven Python CLI that generates synthetic OpenTelemetry telemetry (logs, metrics, traces) with injectable pipeline anomalies and delivers it to ClickStack (ClickHouse) for the Sentinel observability platform.

---

## What It Does and Why

Sentinel's storage layer (ClickStack) and its agent tiers — Detector, Diagnoser, Healer, Auditor — cannot be built, tested, or demonstrated without real telemetry. Real cloud connectors do not exist yet. The OTel Data Generator is the **step-one milestone**: a self-contained data source that populates ClickStack with realistic, OTel-compliant synthetic data so every downstream workstream can proceed in parallel.

Key properties that make it useful beyond a toy script:

- Signals (logs, metrics, traces) are **correlated** — spans and their logs share trace/span IDs; metrics are emitted from the same topology components.
- Every record is **tagged as synthetic** with `sentinel.synthetic=true`, `sentinel.scenario`, and `sentinel.run_id`, so generated data is always distinguishable and filterable.
- **Anomaly scenarios** are injected over a healthy baseline, giving agent tiers realistic pathological data to detect and reason about.
- The entire topology, scenario library, and ClickHouse schema are **declarative YAML files** — the cross-language contract that Go and Rust generator pods will consume without reading Python.

---

## Features

- Produces OTel-compliant logs, metrics, and traces via two delivery paths: **OTLP gRPC on :4317** (default, canonical — to a collector) and a dev-only direct ClickHouse write
- **Correlated distributed traces**: one trace per pipeline run, root-anchored at source components, child spans following the topology `depends_on` graph
- **GCP-faithful telemetry**: resource attributes use OTel/GCP resource-detector conventions and emit real Cloud Monitoring metric descriptors (research-grounded; see the provider profile)
- Two run modes: bounded historical **backfill** (default) and continuous real-time **stream**
- Volume is honored: per-tick emission scales with `base_rate × step`, globally capped by `--rate`
- Five anomaly scenarios out of the box: `baseline`, `failure_spike`, `latency_degradation`, `stalled_job`, `black_friday` (traffic surge + pod autoscale 30→200)
- **Versioned, machine-readable contracts**: every `contract/` YAML carries a `version`, and the Pod 1→Pod 2 OTLP output shape is published as a JSON Schema at `contract/schema/otlp_output.schema.json`
- `--dry-run` validates the contract and estimates per-signal counts without exporting
- Fully config-driven ClickHouse schema (dev-only path) — rename a column in `contract/clickhouse_schema.yaml`, no code change needed
- `--init-schema` prints ready-to-run `CREATE TABLE` DDL derived from that same config
- Deterministic reproducibility via `--seed` (validated by a golden snapshot fixture)
- Structured JSON logging to stdout, run summary with per-signal counts, non-zero exit on failure
- Runs as a non-root user in a slim Python 3.12 Docker image; default `contract/` baked in, overridable by volume mount

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OTel Data Generator (Docker container)                │
│                                                                          │
│  CLI (flags + env)                                                       │
│      │  builds RunConfig (mode, delivery, provider, scenario, seed, …)  │
│      ▼                                                                   │
│  ConfigLoader ──reads──► contract/ (YAML)                               │
│      │                    ├─ topology/default.yaml   (components + deps) │
│      │  validates          ├─ scenarios/*.yaml        (baseline + phases) │
│      │  (pydantic)         ├─ provider_profiles/gcp.yaml                 │
│      │                    └─ clickhouse_schema.yaml  (editable mapping)  │
│      ▼                                                                   │
│  Topology ──► ScenarioEngine ──► SignalFactory ──► [canonical signals]  │
│  (graph)      (clock + anomaly    (OTel-shaped     LogSignal            │
│               injectors)          build + attrs)   MetricSignal         │
│                   ▲                    │            SpanSignal           │
│              RunModeClock         stamps resource attrs:                 │
│           (backfill | stream)     provider profile + sentinel.*         │
│                                        │                                 │
│                                        ▼                                 │
│                                 Exporter (ABC)                           │
│                         ┌─────────────┴────────────┐                    │
│                         ▼                          ▼                     │
│                  OTLPExporter               ClickHouseExporter           │
│                  (default)                  (--delivery=direct)          │
│                         │                          │                     │
│                 RunReporter: per-signal counts / status / exit code     │
└─────────────────────────┼──────────────────────────┼────────────────────┘
                          │ OTLP/gRPC or HTTP         │ clickhouse-connect
                          ▼                           ▼
                    OTel Collector ─────────────► ClickHouse (ClickStack)
                                                        │
                                                        ▼
                                              HyperDX UI + Sentinel agents
```

**Core design:** a single canonical signal model (`LogSignal`, `MetricSignal`, `SpanSignal` frozen dataclasses with explicit nanosecond timestamps) is produced once by `SignalFactory`. Each `Exporter` translates from this model to its own wire format. Both delivery paths always produce equivalent content.

---

## Install

Python 3.10+ is required. The package uses a `src/` layout.

```bash
# Clone and install in editable mode with dev dependencies
git clone <repo-url>
cd sentinel
pip install -e ".[dev]"
```

Verify:

```bash
otelgen --help
# or, without installing:
PYTHONPATH=src python3 -m otelgen.cli --help
```

---

## Quick Start

### Default backfill via OTLP gRPC (24-hour historical window, GCP profile, baseline scenario)

```bash
otelgen \
  --mode backfill \
  --delivery otlp \
  --otlp-endpoint http://localhost:4317 \
  --otlp-protocol grpc \
  --scenario baseline \
  --window 24h \
  --seed 42
```

> gRPC on `:4317` is the canonical transport (meeting D4) and the default — the flags
> above are shown for clarity. Plaintext (`insecure`) is auto-selected for `http://`
> endpoints; use `--otlp-secure` or an `https://` endpoint for TLS. HTTP/protobuf is
> still available via `--otlp-protocol http/protobuf --otlp-endpoint http://localhost:4318`.

### Estimate volume without exporting (dry run)

```bash
otelgen --dry-run --scenario black_friday --window 24h --step 1m --seed 42
```

### Black Friday surge scenario (traffic spike + pod autoscale 30→200)

```bash
otelgen --scenario black_friday --window 24h --step 1m --seed 42
```

### Inject a failure spike (60% error ratio on `orchestration.daily_etl` for 30 minutes)

```bash
otelgen \
  --scenario failure_spike \
  --window 24h \
  --seed 42
```

### Direct write to ClickHouse (dev-only — non-canonical)

> The `direct` path is for local development/testing only. The canonical pipeline is
> OTLP → OTel Collector → ClickStack (meeting D6); the real ClickHouse table schema is
> owned by Pod 3. The generator logs a warning when this path is used.

```bash
export CH_HOST=localhost
export CH_PORT=8123
export CH_USER=default
export CH_PASSWORD=secret

otelgen \
  --delivery direct \
  --scenario latency_degradation \
  --window 12h
```

### Print CREATE TABLE DDL from the schema config and exit

```bash
otelgen --init-schema
```

This emits DDL for all three tables (`otel_logs`, `otel_traces`, `otel_metrics`) derived from `contract/clickhouse_schema.yaml` and exits without writing any data. Pipe it to ClickHouse to bootstrap the schema:

```bash
otelgen --init-schema | clickhouse-client --multiquery
```

### Stream mode (emit at real-time pace for 10 minutes)

```bash
otelgen \
  --mode stream \
  --duration 10m \
  --scenario baseline
```

### Send to HyperDX / ClickStack via OTLP (authenticated)

ClickStack's collector requires an **ingestion API key**. Create a user/team in the
HyperDX UI (`http://localhost:8080`), copy the *Ingestion API Key*, then:

```bash
otelgen \
  --delivery otlp \
  --otlp-endpoint http://localhost:4318 \
  --otlp-api-key <ingestion-key> \
  --scenario failure_spike \
  --window 24h --step 5m
```

The key is sent as the `authorization` header. You can also set it via the
`OTELGEN_OTLP_API_KEY` env var, or add arbitrary headers with repeatable
`--otlp-header key=value`. View the data in the HyperDX UI at `http://localhost:8080`.

---

## Configuration Reference

All options are available as CLI flags. Options marked in the env var column also read from the environment; the CLI flag takes precedence when both are set.

| Flag | Env Var | Default | Description |
|---|---|---|---|
| `--mode` | — | `backfill` | Run mode: `backfill` (historical window) or `stream` (real-time) |
| `--delivery` | — | `otlp` | Delivery path: `otlp` (via OTel Collector) or `direct` (ClickHouse) |
| `--provider` | — | `gcp` | Provider profile to emulate. v1 supports `gcp` only. |
| `--scenario` | — | `baseline` | Scenario name; must match a file under `contract/scenarios/` |
| `--window` | — | `24h` | Backfill window size. Duration format: `24h`, `1h30m`, `45m`. |
| `--step` | — | `10s` | Tick granularity (time between emitted signal batches). |
| `--rate` | — | `200` | Events-per-second cap for emission pacing. |
| `--duration` | — | `5m` | Stream mode run cap. Has no effect in `backfill` mode. |
| `--seed` | — | `0` | Integer RNG seed. Same seed + config = identical output. |
| `--contract-dir` | — | `/app/contract` | Root path of the YAML contract directory. |
| `--otlp-endpoint` | `OTELGEN_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP collector endpoint (canonical: gRPC on :4317). |
| `--otlp-protocol` | — | `grpc` | OTLP transport: `grpc` (default) or `http/protobuf`. |
| `--otlp-insecure / --otlp-secure` | — | _(auto)_ | Plaintext gRPC. Auto: insecure for `http://` endpoints, TLS for `https://`. |
| `--otlp-api-key` | `OTELGEN_OTLP_API_KEY` | _(empty)_ | Ingestion API key sent as the `authorization` header (e.g. HyperDX/ClickStack). |
| `--otlp-header` | — | _(none)_ | Extra OTLP header as `key=value`. Repeatable. |
| `--ch-host` | `CH_HOST` | `localhost` | ClickHouse hostname (direct delivery only). |
| `--ch-port` | `CH_PORT` | `8123` | ClickHouse HTTP port (direct delivery only). |
| `--ch-user` | `CH_USER` | `default` | ClickHouse username (direct delivery only). |
| `--ch-password` | `CH_PASSWORD` | _(empty)_ | ClickHouse password. Pass via env var, not the flag, to avoid shell history. |
| `--ch-database` | `CH_DATABASE` | `default` | ClickHouse database name. |
| `--init-schema` | — | `false` | Print `CREATE TABLE` DDL from `clickhouse_schema.yaml` and exit. |
| `--dry-run` | — | `false` | Validate the contract and print estimated per-signal counts without exporting; exit 0. |
| `--log-level` | — | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

---

## The `contract/` Directory

The `contract/` directory is the cross-language contract. Python, Go, and Rust generator pods all read from the same YAML files; there is no logic embedded in the data. The directory layout is:

```
contract/
├── topology/
│   └── default.yaml              # Component graph: services, types, dependencies, base rates
├── scenarios/
│   ├── baseline.yaml             # Healthy baseline (no anomaly phases)
│   ├── failure_spike.yaml        # 60% error ratio on orchestration.daily_etl for 30 min
│   ├── latency_degradation.yaml  # 4x latency on compute.spark_batch for 1 hour
│   ├── stalled_job.yaml          # Silent stall on orchestration.daily_etl for 45 min
│   └── black_friday.yaml         # Traffic surge + pod autoscale (30→200) + latency
├── provider_profiles/
│   └── gcp.yaml                  # GCP resource-detector attributes + Cloud Monitoring metric catalog
├── schema/
│   └── otlp_output.schema.json   # Published Pod 1→Pod 2 OTLP output contract (JSON Schema)
├── golden/
│   └── baseline_seed42.jsonl     # Deterministic snapshot fixture (reproducibility guard)
└── clickhouse_schema.yaml        # DEV-ONLY ClickHouse schema (direct path); Pod 3 owns the real schema
```

Every top-level file above carries a `version:` (semver). Loading a file without one
is a validation error. The OTLP output shape — what Pod 2's collector receives — is
published as a JSON Schema at `contract/schema/otlp_output.schema.json` and validated in
the test suite, so the producer→consumer contract is machine-checkable.

### `topology/default.yaml`

Defines the component graph. Each component has a name, type, service name, dependencies, base emission rate, base latency, and baseline error ratio. The current default topology emulates a GCP data pipeline:

| Component | Type | Service Name |
|---|---|---|
| `orchestration.daily_etl` | orchestration | `cloud-composer-etl` |
| `compute.spark_batch` | compute | `dataproc-spark-batch` |
| `compute.spark_streaming` | compute | `dataproc-spark-streaming` |
| `storage.raw_bucket` | storage | `gcs-raw-bucket` |
| `storage.processed_bucket` | storage | `gcs-processed-bucket` |
| `messaging.ingestion_topic` | messaging | `pubsub-ingestion-topic` |
| `kubernetes.api_gateway` | kubernetes | `k8s-api-gateway` |

### `scenarios/*.yaml`

Each scenario file has a `name`, an optional `extends` field (inherits all parameters from the named scenario), and a list of `phases`. Each phase targets a specific topology component and injects an anomaly for a bounded time window.

```yaml
name: failure_spike
extends: baseline
phases:
  - type: failure_spike            # injector type; must match one in the v1 catalog
    target: orchestration.daily_etl
    start_offset: "6h"             # how far into the backfill window the anomaly starts
    duration: "30m"
    magnitude: 0.6                 # 0.6 = 60% error ratio during this phase
```

**V1 anomaly injector catalog:**

| Type | Effect | `magnitude` meaning |
|---|---|---|
| `failure_spike` | Raises the error ratio on the target component | Fraction of requests that error (0.0–1.0) |
| `latency_degradation` | Multiplies base latency on the target component | Latency multiplier (e.g. `4.0` = 4x slower) |
| `stalled_job` | Silences emission from the target component entirely | Set to `1.0` (no tuning needed) |
| `traffic_surge` | Multiplies emission volume on the target component | Volume multiplier (e.g. `5.0` = 5x events) |
| `pod_autoscale` | Emits a ramping replica-count gauge (`k8s.deployment.available_replicas`) | Set to `1.0`; reads `params.baseline_replicas` / `params.peak_replicas` |

`pod_autoscale` uses the phase `params` block for its replica bounds, e.g.:

```yaml
  - type: pod_autoscale
    target: kubernetes.api_gateway
    start_offset: "6h"
    duration: "1h"
    magnitude: 1.0
    params:
      baseline_replicas: 30
      peak_replicas: 200
```

### `provider_profiles/gcp.yaml`

Defines GCP-faithful resource attributes following the OpenTelemetry GCP resource-detector
conventions (`cloud.provider`, `cloud.account.id`, `cloud.region`, `cloud.platform`, plus
`k8s.*`/`gcp.*` per platform) — global `resource_attrs` applied to every signal, plus
per-`component_types` overrides. Each component type also lists a `metrics` catalog of real
Cloud Monitoring metric descriptors (name, instrument, unit) that the generator emits. These
attributes are stamped onto every signal alongside the `sentinel.*` synthetic markers.

> The profile is **research-grounded** against published OTel/GCP conventions and flagged
> *unverified* until reconciled against a real GCP OTLP capture (trust-but-verify).

### `clickhouse_schema.yaml`

Defines the ClickHouse table names and the mapping from each canonical signal field to its ClickHouse column name. **This schema is invented for v1** and is fully config-driven: the `ClickHouseExporter` reads column names from this file at runtime; no table or column name is hardcoded.

```yaml
batch_size: 5000
tables:
  logs:
    name: otel_logs
    columns:                        # canonical_field: ClickHouseColumnName
      time_unix_nano: Timestamp
      service_name: ServiceName
      severity_text: SeverityText
      severity_number: SeverityNumber
      body: Body
      trace_id: TraceId
      span_id: SpanId
      attributes: LogAttributes
      resource_attributes: ResourceAttributes
  traces:
    name: otel_traces
    columns:
      start_unix_nano: Timestamp
      trace_id: TraceId
      span_id: SpanId
      parent_span_id: ParentSpanId
      name: SpanName
      service_name: ServiceName
      duration_nano: Duration
      status_code: StatusCode
      attributes: SpanAttributes
      resource_attributes: ResourceAttributes
  metrics:
    name: otel_metrics
    columns:
      time_unix_nano: Timestamp
      name: MetricName
      type: MetricType
      value: Value
      service_name: ServiceName
      attributes: Attributes
      resource_attributes: ResourceAttributes
```

To retarget writes to a different table or column name: change the value in this file and re-run `--init-schema` to regenerate DDL. Zero code changes required.

---

## How to Add a Scenario

Adding a new scenario instance requires no code — only a new YAML file.

1. Create `contract/scenarios/my_scenario.yaml`:

```yaml
name: my_scenario
extends: baseline        # inherit baseline parameters
phases:
  - type: failure_spike
    target: compute.spark_batch
    start_offset: "2h"
    duration: "1h"
    magnitude: 0.4
```

2. Run with `--scenario my_scenario`.

The engine resolves the file by name under `--contract-dir/scenarios/`. The `extends` field merges baseline parameters before applying phases. Multiple phases can appear in a single scenario, in order.

Adding a **new anomaly injector type** (e.g. a memory-leak pattern) requires implementing a new injector class in `src/otelgen/scenarios/anomalies.py` and repeating the same class in Go/Rust pods — the injector library is the only part that is not purely declarative.

---

## Synthetic Markers

Every record produced by the generator carries these resource-level attributes:

| Attribute | Example Value | Meaning |
|---|---|---|
| `sentinel.synthetic` | `true` | Marks the record as generator-produced; use to exclude synthetic data from production queries |
| `sentinel.scenario` | `failure_spike` | The scenario that produced this record |
| `sentinel.run_id` | `a3f2c1…` (UUID4) | Unique per-invocation identifier; use to group all records from a single run |

These attributes appear in `ResourceAttributes` in ClickHouse and in the OTLP resource attributes field on all three signal types.

---

## Docker Usage

A `Dockerfile` is included at the repo root. The image:

- Base: `python:3.12-slim`
- Runs as a non-root user (`appuser`)
- Bakes the default `contract/` into `/app/contract` at build time
- Accepts all runtime configuration via CLI flags and environment variables
- Allows overriding the entire contract directory by mounting a host path at `/app/contract`

### Build

```bash
docker build -t otelgen:latest .
```

### Run with OTLP delivery and default contract

```bash
docker run --rm \
  --network host \
  otelgen:latest \
  --scenario failure_spike \
  --window 24h \
  --seed 42
```

### Run with direct ClickHouse delivery and a custom contract

```bash
docker run --rm \
  -v /path/to/my-contract:/app/contract:ro \
  -e CH_HOST=clickhouse.internal \
  -e CH_USER=sentinel \
  -e CH_PASSWORD=secret \
  otelgen:latest \
  --delivery direct \
  --scenario latency_degradation
```

The volume mount at `/app/contract` replaces the baked-in defaults entirely. This is the recommended way to iterate on topology or scenario YAML without rebuilding the image.

### docker-compose (local E2E)

A `docker-compose.yaml` wiring the generator together with an OTel Collector and ClickHouse for a full local end-to-end run is defined in the project design and will be present at the repo root. To start the full stack:

```bash
docker compose up
```

The collector listens on `4317` (gRPC) and `4318` (HTTP); ClickHouse on `8123`. The generator targets the OTLP HTTP path by default.

---

## Reproducibility

Pass `--seed <integer>` to pin the RNG. Any two invocations with identical `--seed`, `--scenario`, `--window`, `--step`, and `--contract-dir` produce the same canonical signal sequence, in the same order, with the same timestamps and values.

The seed controls all randomness: error ratio sampling, latency jitter, trace/span ID generation, and log body selection.

```bash
# Run 1
otelgen --seed 1234 --scenario failure_spike --window 6h

# Run 2 — produces an identical dataset
otelgen --seed 1234 --scenario failure_spike --window 6h
```

The `sentinel.run_id` will differ between invocations (it is a fresh UUID4 per run), but all signal content is deterministic.

---

## Verifying Data Landed

### Query ClickHouse directly

```sql
-- Count synthetic records grouped by run
SELECT
    ResourceAttributes['sentinel.run_id'] AS run_id,
    ResourceAttributes['sentinel.scenario'] AS scenario,
    count() AS total
FROM otel_logs
WHERE ResourceAttributes['sentinel.synthetic'] = 'true'
GROUP BY run_id, scenario
ORDER BY total DESC
LIMIT 10;

-- Inspect the failure_spike anomaly window
SELECT Timestamp, ServiceName, SeverityText, Body
FROM otel_logs
WHERE ResourceAttributes['sentinel.scenario'] = 'failure_spike'
  AND ServiceName = 'cloud-composer-etl'
ORDER BY Timestamp
LIMIT 100;

-- Find correlated spans for a trace
SELECT Timestamp, TraceId, SpanId, SpanName, StatusCode, Duration
FROM otel_traces
WHERE TraceId = '<trace_id_from_logs>'
ORDER BY Timestamp;
```

### Run summary

At the end of every run the generator prints a summary to stdout:

```
Run complete
  logs:    NNN emitted, 0 failed  (otlp)
  traces:  NNN emitted, 0 failed  (otlp)
  metrics: NNN emitted, 0 failed  (otlp)
Duration: Xs
Exit code: 0
```

A non-zero exit code indicates at least one export failure. The process exits 2 for configuration or contract validation errors, and 1 for runtime failures (unreachable store, export error after retries).

### Connectivity preflight

Before emitting any data the generator performs a connectivity check against the configured target (OTLP endpoint or ClickHouse). If the target is unreachable it prints an actionable error message and exits 1 without writing partial data.

---

## Roadmap and Out of Scope

**Planned for future versions:**

- Go and Rust generator pods consuming the same `contract/` YAML (the shared contract is designed for this from day one)
- AWS, Azure, and Databricks provider profiles (add a new file under `contract/provider_profiles/` and pass `--provider <name>`)
- Additional anomaly injector types beyond the v1 catalog
- Dry-run mode (validate config and estimate signal counts without writing to any store)

**Out of scope for this component:**

- Deploying or operating ClickStack, HyperDX, or the OTel Collector
- Any detection, diagnosis, healing, or auditing logic (the Sentinel agent tiers)
- Guaranteeing the invented ClickHouse schema matches the real ClickStack schema — the schema is config-driven and will be reconciled against the real schema without code changes once infrastructure is captured
- Real cloud connector polling of live provider APIs — this generator is the stand-in until those connectors exist

---

## Development

```bash
# Install with dev extras (pytest, ruff, testcontainers)
pip install -e ".[dev]"

# Run unit tests
pytest tests/unit/

# Run integration tests (requires a reachable ClickHouse)
pytest tests/integration/

# Lint
ruff check src/ tests/
```

### Project layout

```
sentinel/
├── contract/                  # Cross-language YAML contract
│   ├── topology/
│   ├── scenarios/
│   ├── provider_profiles/
│   └── clickhouse_schema.yaml
├── src/
│   └── otelgen/
│       ├── cli.py             # Entry point; all CLI options defined here
│       ├── config.py          # RunConfig dataclass
│       ├── model.py           # Canonical signal dataclasses
│       ├── contract/          # Pydantic models + YAML loader
│       ├── signals/           # SignalFactory
│       ├── scenarios/         # ScenarioEngine + anomaly injectors
│       ├── exporters/         # OTLPExporter, ClickHouseExporter, Exporter ABC
│       ├── runmode.py         # backfill_ticks / stream_ticks generators
│       ├── seeding.py         # Deterministic RNG factory
│       ├── topology.py        # Component graph
│       └── reporting.py       # RunReporter
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile
├── pyproject.toml
└── README.md
```

### Dependencies

| Package | Pinned version | Purpose |
|---|---|---|
| `opentelemetry-sdk` | >=1.24.0 | OTel data model objects and OTLP exporters |
| `opentelemetry-exporter-otlp` | >=1.24.0 | OTLP HTTP and gRPC transport |
| `clickhouse-connect` | >=0.7.0 | Direct ClickHouse HTTP insert |
| `pydantic` | >=2.7.0 | Contract YAML validation |
| `typer` | >=0.12.0 | CLI definition |
| `pyyaml` | >=6.0.1 | YAML loading |
