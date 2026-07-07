# Sentinel ClickHouse — Local Dev Setup

This directory contains the DDL for Sentinel's three OTel signal tables and
the docker-compose configuration to run ClickHouse locally for Day-3+ development.

---

## Bring it up

```bash
# From the repo root (sentinel/)
docker compose -f infra/docker-compose.yml up -d

# Confirm the container is healthy (wait ~20s on first boot while DDL applies)
docker compose -f infra/docker-compose.yml ps
```

The container is ready when the healthcheck shows `healthy`. Tables are created
automatically from the SQL files in `infra/clickhouse/ddl/` via the
`/docker-entrypoint-initdb.d/` mount.

**Files applied on first boot (alphabetical order):**

| File | Creates |
|---|---|
| `001_otel_logs.sql` | `otel_logs` |
| `002_otel_traces.sql` | `otel_traces` |
| `003_otel_metrics.sql` | `otel_metrics`, `otel_metrics_1m`, `otel_metrics_1m_mv` |

> **Note on re-creation:** init scripts only run on the *first* boot against an
> empty volume. To reset and re-apply: `docker compose -f infra/docker-compose.yml down -v`
> then `up -d`. This drops all data.

---

## Connect

### clickhouse-client (interactive SQL shell)

```bash
# Inside the container
docker exec -it sentinel-clickhouse clickhouse-client

# Or install clickhouse-client locally and connect
clickhouse-client --host localhost --port 9000
```

### HTTP (curl / health probe)

```bash
curl "http://localhost:8123/?query=SELECT+1"
# Returns: 1

curl "http://localhost:8123/?query=SHOW+TABLES"
# Returns: otel_logs\notel_metrics\notel_metrics_1m\notel_traces
```

### DBeaver / Grafana

Use the HTTP driver on port 8123, database `default`, no password.

---

## Verify tables exist

```sql
-- Run in clickhouse-client or via HTTP
SHOW TABLES;
-- Expected: otel_logs, otel_metrics, otel_metrics_1m, otel_traces

SELECT name, engine, partition_key, sorting_key
FROM system.tables
WHERE database = 'default'
ORDER BY name;
```

Expected output:

| name | engine | partition_key | sorting_key |
|---|---|---|---|
| otel_logs | MergeTree | toDate(Timestamp) | ServiceName, Timestamp, TraceId |
| otel_metrics | MergeTree | toDate(Timestamp) | ServiceName, MetricName, Timestamp |
| otel_metrics_1m | SummingMergeTree | toDate(window_start) | ServiceName, MetricName, SentinelScenario, window_start |
| otel_traces | MergeTree | toDate(Timestamp) | ServiceName, Timestamp, TraceId |

---

## Load the golden seed data (manual / Day-4 integration)

Until the Rust Collector exporter is wired (Day 4), you can load the golden
file directly for schema validation:

```bash
# Requires jq and a small transform to match the column layout
# This is a convenience script — not the production path.
# Production path: Generator → OTel Collector → ClickHouse (OTLP gRPC :4317)
cat contract/golden/baseline_seed42.jsonl \
  | python3 infra/clickhouse/scripts/seed_golden.py 2>/dev/null \
  || echo "seed script not yet written — use Day-4 Rust exporter"
```

---

## How this maps to the Rust `clickhouse` crate (0.13)

The `Cargo.toml` for `collector-rust` already pins:

```toml
clickhouse = { version = "0.13", features = ["lz4", "time"] }
```

Key points for Day-4 coding:

**The crate connects over HTTP (port 8123), not native TCP (port 9000).**

Despite the name, `clickhouse` 0.13 uses HTTP transport with ClickHouse's
binary RowBinary format — not the native TCP binary protocol. Your connection
URL must use the HTTP port:

```rust
let client = clickhouse::Client::default()
    .with_url("http://localhost:8123")
    .with_database("default");
```

**Inserting a row requires a `#[derive(Row, Serialize)]` struct.** Example
for a log row (illustrative — does not need to compile today):

```rust
use clickhouse::Row;
use serde::Serialize;
use time::OffsetDateTime;  // enabled by the "time" feature

#[derive(Row, Serialize)]
pub struct OtelLogRow {
    #[serde(with = "clickhouse::serde::time::datetime64::nanos")]
    pub timestamp: OffsetDateTime,
    pub service_name: &'static str,   // or String
    pub sentinel_scenario: String,
    pub sentinel_run_id: String,
    pub cloud_provider: String,
    pub sentinel_synthetic: u8,       // 1 or 0
    pub severity_text: String,
    pub severity_number: i32,
    pub body: String,
    pub trace_id: String,             // "" if absent
    pub span_id: String,              // "" if absent
    pub contract_version: String,
    pub log_attributes: Vec<(String, String)>,       // Map(String,String)
    pub resource_attributes: Vec<(String, String)>,  // Map(String,String)
}

// Inserting a batch:
let mut insert = client.insert("otel_logs")?;
for row in rows {
    insert.write(&row).await?;
}
insert.end().await?;
```

**Type mapping caveats (flag these before Day-4 coding):**

| ClickHouse type | Rust type (clickhouse 0.13) | Notes |
|---|---|---|
| `DateTime64(9, 'UTC')` | `time::OffsetDateTime` | Requires `features = ["time"]`; use `clickhouse::serde::time::datetime64::nanos` |
| `LowCardinality(String)` | `String` | Transparent — crate handles it |
| `Map(String, String)` | `Vec<(String, String)>` | No HashMap support; must pre-convert |
| `UInt8` | `u8` | For `SentinelSynthetic` |
| `Int64` | `i64` | For `Duration` in traces |
| `Float64` | `f64` | For `Value` in metrics |
| `Int32` | `i32` | For `SeverityNumber` |

The `Map(String, String)` → `Vec<(String, String)>` conversion is the most
surprising. When building the Rust Row structs on Day 4, iterate the
`HashMap<String, String>` from `contract.rs` and collect into a sorted Vec
before inserting. See the KB (`kb/storage/clickhouse/`) and the crate docs for
the exact serialization.

---

## See also

- `infra/clickhouse/ddl/` — CREATE TABLE statements with full design rationale
- `services/collector-rust/src/contract.rs` — the Rust structs you are mapping
- `docs/research/clickhouse-schema-pod2.md` — design note with field mapping table
- `.claude/kb/storage/clickhouse/index.md` — ClickHouse KB (engine choice, codecs, gotchas)
