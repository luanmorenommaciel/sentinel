//! ClickHouse exporter for Sentinel OTel Collector — Day 4.
//!
//! Converts parsed [`Signal`] values into typed Row structs and batches them
//! into three ClickHouse tables: `otel_logs`, `otel_traces`, `otel_metrics`.
//!
//! # Connection model
//!
//! The `clickhouse` 0.13 crate speaks **HTTP on port 8123** (RowBinary over
//! HTTP — not the native TCP protocol on 9000). The client URL is read from
//! `CLICKHOUSE_URL` (default `http://localhost:8123`). Database is `default`.
//!
//! # Map columns
//!
//! ClickHouse `Map(String, String)` columns must be supplied as
//! `Vec<(String, String)>` — the `clickhouse` crate does not accept
//! `HashMap<K, V>`. Entries are sorted by key for deterministic output.
//!
//! # DateTime64(9) columns
//!
//! Timestamp columns are `DateTime64(9, 'UTC')`. The Row field must be
//! `time::OffsetDateTime` annotated with
//! `#[serde(with = "clickhouse::serde::time::datetime64::nanos")]`.
//! Build an `OffsetDateTime` from `i64` nanos:
//! `OffsetDateTime::from_unix_timestamp_nanos(nanos as i128)`.
//! Note the **`i128`** cast — the function signature requires `i128`, not `i64`.
//!
//! # Resource-key hoisting
//!
//! The five keys guaranteed on every signal by [`REQUIRED_RESOURCE_KEYS`] are
//! promoted to typed columns (`ServiceName`, `SentinelScenario`, etc.) for
//! indexed filtering. The remaining resource attributes are kept in
//! `ResourceAttributes Map(String, String)`. See [`hoist`].

use std::collections::HashMap;

use serde::Serialize;
use thiserror::Error;
use time::OffsetDateTime;

use crate::contract::{LogSignal, MetricSignal, MetricType, Signal, SpanSignal, StatusCode};
use crate::Counts;

// ─────────────────────────────────────────────────────────────────────────────
// Error type
// ─────────────────────────────────────────────────────────────────────────────

/// Errors that can occur during the export phase.
///
/// Uses `thiserror` (not `anyhow`) because this is a library-style module —
/// callers need to distinguish network/codec failures from timestamp-conversion
/// failures so they can map to an appropriate gRPC status or retry strategy.
#[derive(Debug, Error)]
pub enum ExporterError {
    /// A ClickHouse insert or flush failed (network, codec, or server error).
    #[error("clickhouse insert failed: {0}")]
    ClickHouse(#[from] clickhouse::error::Error),

    /// A timestamp value could not be converted to `OffsetDateTime`.
    ///
    /// This should only happen if the timestamp is outside the range that
    /// `time::OffsetDateTime` can represent (≈ ±9999 CE). Contract validation
    /// guards against negative values, but an astronomically large positive
    /// value could theoretically trigger this.
    #[error("timestamp out of range: {nanos} nanos — {source}")]
    TimestampOutOfRange {
        nanos: i64,
        #[source]
        source: time::error::ComponentRange,
    },
}

// ─────────────────────────────────────────────────────────────────────────────
// Client constructor
// ─────────────────────────────────────────────────────────────────────────────

/// The default ClickHouse HTTP endpoint used when no URL is provided.
///
/// The `clickhouse` 0.13 crate speaks **RowBinary over HTTP on port 8123** —
/// it does NOT use the native TCP protocol on port 9000.
pub const DEFAULT_CLICKHOUSE_URL: &str = "http://localhost:8123";

/// Build a [`clickhouse::Client`] targeting the given URL, database `default`.
///
/// The URL should be an HTTP address of the form `http://host:8123`. For local
/// development use [`DEFAULT_CLICKHOUSE_URL`]. For environment-driven
/// configuration, read `CLICKHOUSE_URL` in the calling binary and pass the
/// value here — environment access is intentionally kept out of the library so
/// all config paths flow through the Sentinel config loader (see ADR-0004
/// follow-ups and `clippy.toml` `disallowed-methods`).
///
/// # Example
///
/// ```no_run
/// let client = sentinel_collector::clickhouse_exporter::build_client(
///     sentinel_collector::clickhouse_exporter::DEFAULT_CLICKHOUSE_URL,
/// );
/// ```
pub fn build_client(url: &str) -> clickhouse::Client {
    clickhouse::Client::default()
        .with_url(url)
        .with_database("default")
}

/// Convenience wrapper for integration tests and the binary entry point.
///
/// Reads `CLICKHOUSE_URL` from the environment and falls back to
/// [`DEFAULT_CLICKHOUSE_URL`] (`http://localhost:8123`). Call this from
/// `main()` or `#[ignore]`d integration tests — not from library code.
///
/// The `std::env::var` access is explicitly allowed in non-library call sites.
/// Library code must route config through the Sentinel config loader instead
/// (enforced by `clippy::disallowed_methods` in `clippy.toml`).
pub fn client_from_env() -> clickhouse::Client {
    // `std::env::var` is disallowed in lib production code by clippy.toml.
    // This function is intended to be called from test code and the binary
    // crate, where the disallowed-methods restriction is lifted per the
    // clippy.toml note ("Tests can still use it").
    //
    // We use an explicit `#[allow]` here so clippy accepts this one call site
    // within the library module. All other call sites should go through the
    // Sentinel config loader.
    #[allow(clippy::disallowed_methods)]
    let url =
        std::env::var("CLICKHOUSE_URL").unwrap_or_else(|_| DEFAULT_CLICKHOUSE_URL.to_string());
    build_client(&url)
}

// ─────────────────────────────────────────────────────────────────────────────
// Resource-key hoisting helper
// ─────────────────────────────────────────────────────────────────────────────

/// The five keys Pod 1 guarantees on every signal, extracted into typed fields.
///
/// The `clickhouse` 0.13 crate does not accept `HashMap<K, V>` for
/// `Map(String, String)` columns. Both `LogAttributes`/`SpanAttributes`/
/// `Attributes` and `ResourceAttributes` must be supplied as sorted
/// `Vec<(String, String)>`.
struct HoistedKeys {
    service_name: String,
    sentinel_scenario: String,
    sentinel_run_id: String,
    cloud_provider: String,
    /// `"true"` → 1, anything else → 0.
    sentinel_synthetic: u8,
}

/// Extract the five guaranteed resource keys into typed fields and return the
/// **remaining** keys as a sorted `Vec<(String, String)>`.
///
/// The hoisted keys are **not** duplicated into the remainder Vec — each key
/// appears in exactly one place (typed column OR the Map, never both).
///
/// # Panics
///
/// Will not panic in practice: contract validation enforces that all five keys
/// are present before we reach the export stage. If a key is somehow absent
/// (e.g., the caller bypassed validation), the hoisted field defaults to an
/// empty string / 0. This is a deliberate defence-in-depth choice: the exporter
/// should not crash on bad input that passed the receiver.
fn hoist(mut resource: HashMap<String, String>) -> (HoistedKeys, Vec<(String, String)>) {
    // Remove returns the value so we can consume the map without cloning.
    let service_name = resource.remove("service.name").unwrap_or_default();
    let sentinel_scenario = resource.remove("sentinel.scenario").unwrap_or_default();
    let sentinel_run_id = resource.remove("sentinel.run_id").unwrap_or_default();
    let cloud_provider = resource.remove("cloud.provider").unwrap_or_default();
    let synthetic_str = resource.remove("sentinel.synthetic").unwrap_or_default();
    let sentinel_synthetic: u8 = if synthetic_str == "true" { 1 } else { 0 };

    // Whatever is left (cloud.account.id, cloud.region, etc.) goes into the Map.
    let mut remainder: Vec<(String, String)> = resource.into_iter().collect();
    remainder.sort_by(|a, b| a.0.cmp(&b.0)); // deterministic order

    let keys = HoistedKeys {
        service_name,
        sentinel_scenario,
        sentinel_run_id,
        cloud_provider,
        sentinel_synthetic,
    };
    (keys, remainder)
}

/// Convert a `HashMap<String, String>` to a sorted `Vec<(String, String)>`.
///
/// ClickHouse `Map(String, String)` columns require `Vec<(K, V)>` — the
/// `clickhouse` crate does not accept `HashMap`. Sorting ensures deterministic
/// output, which matters for tests and compressed columnar storage.
fn map_to_sorted_vec(map: HashMap<String, String>) -> Vec<(String, String)> {
    let mut v: Vec<(String, String)> = map.into_iter().collect();
    v.sort_by(|a, b| a.0.cmp(&b.0));
    v
}

/// Convert `i64` nanoseconds to `time::OffsetDateTime`.
///
/// The `time` crate's `from_unix_timestamp_nanos` requires `i128` — the caller
/// must cast from `i64`. Returns an [`ExporterError::TimestampOutOfRange`] if
/// the value is outside the representable range (practically impossible for
/// real telemetry data, but the type system demands handling it).
fn nanos_to_offset_dt(nanos: i64) -> Result<OffsetDateTime, ExporterError> {
    OffsetDateTime::from_unix_timestamp_nanos(nanos as i128)
        .map_err(|source| ExporterError::TimestampOutOfRange { nanos, source })
}

// ─────────────────────────────────────────────────────────────────────────────
// Row structs
// ─────────────────────────────────────────────────────────────────────────────
//
// Field ORDER must match the DDL column order exactly — the `clickhouse` crate
// serialises fields positionally (RowBinary format), not by name. A mismatch
// in order silently inserts data into the wrong column.
//
// Field names use `#[serde(rename = "...")]` to map from Rust's snake_case
// convention to the DDL's PascalCase column names.

/// One row in `otel_logs` (14 columns, matching `infra/clickhouse/ddl/001_otel_logs.sql`).
#[derive(clickhouse::Row, Serialize, Debug)]
pub struct OtelLogRow {
    // col 1 — DateTime64(9, 'UTC')
    #[serde(
        rename = "Timestamp",
        with = "clickhouse::serde::time::datetime64::nanos"
    )]
    pub timestamp: OffsetDateTime,

    // col 2–6 — hoisted resource keys
    #[serde(rename = "ServiceName")]
    pub service_name: String,
    #[serde(rename = "SentinelScenario")]
    pub sentinel_scenario: String,
    #[serde(rename = "SentinelRunId")]
    pub sentinel_run_id: String,
    #[serde(rename = "CloudProvider")]
    pub cloud_provider: String,
    /// `"true"` → 1, else → 0. Stored as UInt8.
    #[serde(rename = "SentinelSynthetic")]
    pub sentinel_synthetic: u8,

    // col 7–9 — log-specific
    #[serde(rename = "SeverityText")]
    pub severity_text: String,
    #[serde(rename = "SeverityNumber")]
    pub severity_number: i32,
    #[serde(rename = "Body")]
    pub body: String,

    // col 10–11 — trace correlation ('' when absent)
    #[serde(rename = "TraceId")]
    pub trace_id: String,
    #[serde(rename = "SpanId")]
    pub span_id: String,

    // col 12 — contract metadata
    #[serde(rename = "ContractVersion")]
    pub contract_version: String,

    // col 13 — log-level attributes (Map(String, String) → Vec<(String, String)>)
    #[serde(rename = "LogAttributes")]
    pub log_attributes: Vec<(String, String)>,

    // col 14 — remaining resource attributes
    #[serde(rename = "ResourceAttributes")]
    pub resource_attributes: Vec<(String, String)>,
}

/// One row in `otel_traces` (15 columns, matching `infra/clickhouse/ddl/002_otel_traces.sql`).
#[derive(clickhouse::Row, Serialize, Debug)]
pub struct OtelTraceRow {
    // col 1 — Timestamp (= start_unix_nano)
    #[serde(
        rename = "Timestamp",
        with = "clickhouse::serde::time::datetime64::nanos"
    )]
    pub timestamp: OffsetDateTime,

    // col 2–4 — span identity
    #[serde(rename = "TraceId")]
    pub trace_id: String,
    #[serde(rename = "SpanId")]
    pub span_id: String,
    /// `None` (root span) → `""`. Non-root spans carry a 16-char lowercase hex string.
    #[serde(rename = "ParentSpanId")]
    pub parent_span_id: String,

    // col 5 — span descriptor
    #[serde(rename = "SpanName")]
    pub span_name: String,

    // col 6–10 — hoisted resource keys
    #[serde(rename = "ServiceName")]
    pub service_name: String,
    #[serde(rename = "SentinelScenario")]
    pub sentinel_scenario: String,
    #[serde(rename = "SentinelRunId")]
    pub sentinel_run_id: String,
    #[serde(rename = "CloudProvider")]
    pub cloud_provider: String,
    #[serde(rename = "SentinelSynthetic")]
    pub sentinel_synthetic: u8,

    // col 11 — duration = end_unix_nano - start_unix_nano (nanos, Int64)
    #[serde(rename = "Duration")]
    pub duration: i64,

    // col 12 — status
    #[serde(rename = "StatusCode")]
    pub status_code: String,

    // col 13 — contract metadata
    #[serde(rename = "ContractVersion")]
    pub contract_version: String,

    // col 14 — span-level attributes
    #[serde(rename = "SpanAttributes")]
    pub span_attributes: Vec<(String, String)>,

    // col 15 — remaining resource attributes
    #[serde(rename = "ResourceAttributes")]
    pub resource_attributes: Vec<(String, String)>,
}

/// One row in `otel_metrics` (12 columns, matching `infra/clickhouse/ddl/003_otel_metrics.sql`).
#[derive(clickhouse::Row, Serialize, Debug)]
pub struct OtelMetricRow {
    // col 1 — Timestamp
    #[serde(
        rename = "Timestamp",
        with = "clickhouse::serde::time::datetime64::nanos"
    )]
    pub timestamp: OffsetDateTime,

    // col 2–4 — metric identity
    #[serde(rename = "MetricName")]
    pub metric_name: String,
    #[serde(rename = "MetricType")]
    pub metric_type: String,
    #[serde(rename = "Value")]
    pub value: f64,

    // col 5–9 — hoisted resource keys
    #[serde(rename = "ServiceName")]
    pub service_name: String,
    #[serde(rename = "SentinelScenario")]
    pub sentinel_scenario: String,
    #[serde(rename = "SentinelRunId")]
    pub sentinel_run_id: String,
    #[serde(rename = "CloudProvider")]
    pub cloud_provider: String,
    #[serde(rename = "SentinelSynthetic")]
    pub sentinel_synthetic: u8,

    // col 10 — contract metadata
    #[serde(rename = "ContractVersion")]
    pub contract_version: String,

    // col 11 — metric-level attributes (note: column is named "Attributes" in metrics DDL)
    #[serde(rename = "Attributes")]
    pub attributes: Vec<(String, String)>,

    // col 12 — remaining resource attributes
    #[serde(rename = "ResourceAttributes")]
    pub resource_attributes: Vec<(String, String)>,
}

// ─────────────────────────────────────────────────────────────────────────────
// From impls (contract → Row)
// ─────────────────────────────────────────────────────────────────────────────

impl OtelLogRow {
    /// Convert a [`LogSignal`] to a row.
    ///
    /// Returns `Err` only if `time_unix_nano` is outside the range
    /// representable by `time::OffsetDateTime` — practically impossible for
    /// real telemetry but required for correctness.
    pub fn try_from_signal(signal: LogSignal) -> Result<Self, ExporterError> {
        let timestamp = nanos_to_offset_dt(signal.time_unix_nano)?;
        let (hoisted, resource_attributes) = hoist(signal.resource_attributes);
        let log_attributes = map_to_sorted_vec(signal.attributes);

        Ok(Self {
            timestamp,
            service_name: hoisted.service_name,
            sentinel_scenario: hoisted.sentinel_scenario,
            sentinel_run_id: hoisted.sentinel_run_id,
            cloud_provider: hoisted.cloud_provider,
            sentinel_synthetic: hoisted.sentinel_synthetic,
            severity_text: signal.severity_text,
            severity_number: signal.severity_number,
            body: signal.body,
            // None → empty string, per ADR-0006 (empty-string sentinel for optional IDs)
            trace_id: signal.trace_id.unwrap_or_default(),
            span_id: signal.span_id.unwrap_or_default(),
            contract_version: signal.contract_version,
            log_attributes,
            resource_attributes,
        })
    }
}

impl OtelTraceRow {
    /// Convert a [`SpanSignal`] to a row.
    ///
    /// `Duration` is computed as `end_unix_nano - start_unix_nano` in
    /// nanoseconds. `end_unix_nano` is **not** stored as a column — the
    /// Latency watcher (W05) queries quantiles over `Duration` directly.
    pub fn try_from_signal(signal: SpanSignal) -> Result<Self, ExporterError> {
        let timestamp = nanos_to_offset_dt(signal.start_unix_nano)?;
        let duration = signal.end_unix_nano - signal.start_unix_nano;
        let (hoisted, resource_attributes) = hoist(signal.resource_attributes);
        let span_attributes = map_to_sorted_vec(signal.attributes);

        let status_code = match signal.status_code {
            StatusCode::Ok => "OK".to_string(),
            StatusCode::Error => "ERROR".to_string(),
        };

        Ok(Self {
            timestamp,
            trace_id: signal.trace_id,
            span_id: signal.span_id,
            parent_span_id: signal.parent_span_id.unwrap_or_default(),
            span_name: signal.name,
            service_name: hoisted.service_name,
            sentinel_scenario: hoisted.sentinel_scenario,
            sentinel_run_id: hoisted.sentinel_run_id,
            cloud_provider: hoisted.cloud_provider,
            sentinel_synthetic: hoisted.sentinel_synthetic,
            duration,
            status_code,
            contract_version: signal.contract_version,
            span_attributes,
            resource_attributes,
        })
    }
}

impl OtelMetricRow {
    /// Convert a [`MetricSignal`] to a row.
    pub fn try_from_signal(signal: MetricSignal) -> Result<Self, ExporterError> {
        let timestamp = nanos_to_offset_dt(signal.time_unix_nano)?;
        let (hoisted, resource_attributes) = hoist(signal.resource_attributes);
        let attributes = map_to_sorted_vec(signal.attributes);

        let metric_type = match signal.metric_type {
            MetricType::Gauge => "gauge".to_string(),
            MetricType::Sum => "sum".to_string(),
        };

        Ok(Self {
            timestamp,
            metric_name: signal.name,
            metric_type,
            value: signal.value,
            service_name: hoisted.service_name,
            sentinel_scenario: hoisted.sentinel_scenario,
            sentinel_run_id: hoisted.sentinel_run_id,
            cloud_provider: hoisted.cloud_provider,
            sentinel_synthetic: hoisted.sentinel_synthetic,
            contract_version: signal.contract_version,
            attributes,
            resource_attributes,
        })
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Exporter entry point
// ─────────────────────────────────────────────────────────────────────────────

/// Export a batch of [`Signal`]s to ClickHouse.
///
/// Partitions signals by type, converts each to the appropriate Row struct, and
/// performs one batched `INSERT` per signal type (three inserts total if all
/// three types are present). Returns per-type counts of successfully written
/// rows.
///
/// # Errors
///
/// Returns [`ExporterError::ClickHouse`] if any insert fails. Timestamp
/// conversion errors return [`ExporterError::TimestampOutOfRange`].
///
/// # Batching
///
/// The `clickhouse` crate streams rows into a single HTTP request per
/// `client.insert(...)` call. All rows for a given type are written in one
/// batch — there is no intermediate buffering in this function. For the golden
/// fixture (279 rows: 48 logs, 48 spans, 183 metrics) this is exactly one
/// batch per table.
pub async fn export(
    client: &clickhouse::Client,
    signals: Vec<Signal>,
) -> Result<Counts, ExporterError> {
    // Partition signals by type. We collect into three Vecs to allow separate
    // batched inserts — one INSERT per table, per the clickhouse crate's API.
    let mut log_rows: Vec<OtelLogRow> = Vec::new();
    let mut trace_rows: Vec<OtelTraceRow> = Vec::new();
    let mut metric_rows: Vec<OtelMetricRow> = Vec::new();

    for signal in signals {
        match signal {
            Signal::Log(log) => {
                log_rows.push(OtelLogRow::try_from_signal(log)?);
            }
            Signal::Span(span) => {
                trace_rows.push(OtelTraceRow::try_from_signal(span)?);
            }
            Signal::Metric(metric) => {
                metric_rows.push(OtelMetricRow::try_from_signal(metric)?);
            }
        }
    }

    let mut counts = Counts::default();

    // Insert logs
    if !log_rows.is_empty() {
        let mut insert = client.insert("otel_logs")?;
        for row in &log_rows {
            insert.write(row).await?;
        }
        insert.end().await?;
        counts.logs = log_rows.len();
    }

    // Insert traces
    if !trace_rows.is_empty() {
        let mut insert = client.insert("otel_traces")?;
        for row in &trace_rows {
            insert.write(row).await?;
        }
        insert.end().await?;
        counts.spans = trace_rows.len();
    }

    // Insert metrics
    if !metric_rows.is_empty() {
        let mut insert = client.insert("otel_metrics")?;
        for row in &metric_rows {
            insert.write(row).await?;
        }
        insert.end().await?;
        counts.metrics = metric_rows.len();
    }

    Ok(counts)
}

// ─────────────────────────────────────────────────────────────────────────────
// Unit tests (no ClickHouse required)
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    // Allow unwrap/expect in tests — failing fast with a diagnostic is the
    // point. Production code is governed by `unwrap_used = deny` in Cargo.toml.
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::collections::HashMap;

    use super::*;
    use crate::contract::{MetricType, StatusCode, REQUIRED_RESOURCE_KEYS};

    /// Build a resource_attributes map that contains all five required keys
    /// plus any extras passed in.
    fn req_resource(extras: &[(&str, &str)]) -> HashMap<String, String> {
        let mut m = HashMap::new();
        m.insert("service.name".to_string(), "test-service".to_string());
        m.insert("sentinel.scenario".to_string(), "baseline".to_string());
        m.insert("sentinel.run_id".to_string(), "run-001".to_string());
        m.insert("cloud.provider".to_string(), "gcp".to_string());
        m.insert("sentinel.synthetic".to_string(), "true".to_string());
        for (k, v) in extras {
            m.insert((*k).to_string(), (*v).to_string());
        }
        m
    }

    fn make_log_signal(
        trace_id: Option<String>,
        span_id: Option<String>,
        resource: HashMap<String, String>,
    ) -> LogSignal {
        LogSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: 1_000_000_000, // 1 second into epoch — safe value
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "test-service".to_string(),
            body: "test body".to_string(),
            trace_id,
            span_id,
            attributes: HashMap::new(),
            resource_attributes: resource,
        }
    }

    fn make_span_signal(
        start: i64,
        end: i64,
        parent_span_id: Option<String>,
        resource: HashMap<String, String>,
    ) -> SpanSignal {
        SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "a".repeat(32),
            span_id: "b".repeat(16),
            parent_span_id,
            name: "test-span".to_string(),
            service_name: "test-service".to_string(),
            start_unix_nano: start,
            end_unix_nano: end,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: resource,
        }
    }

    fn make_metric_signal(
        metric_type: MetricType,
        resource: HashMap<String, String>,
    ) -> MetricSignal {
        MetricSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: 1_000_000_000,
            name: "test.metric".to_string(),
            metric_type,
            value: 42.0,
            service_name: "test-service".to_string(),
            attributes: HashMap::new(),
            resource_attributes: resource,
        }
    }

    // ── Test 1: LogSignal with trace_id: None → TraceId == "" ────────────────

    #[test]
    fn log_with_none_trace_id_produces_empty_string() {
        let signal = make_log_signal(None, None, req_resource(&[]));
        let row = OtelLogRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(
            row.trace_id, "",
            "None trace_id must become empty string (ADR-0006 sentinel)"
        );
        assert_eq!(row.span_id, "", "None span_id must become empty string");
    }

    #[test]
    fn log_with_some_trace_id_passes_through() {
        let tid = "a".repeat(32);
        let sid = "b".repeat(16);
        let signal = make_log_signal(Some(tid.clone()), Some(sid.clone()), req_resource(&[]));
        let row = OtelLogRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.trace_id, tid);
        assert_eq!(row.span_id, sid);
    }

    // ── Test 2: SpanSignal duration computation ───────────────────────────────

    #[test]
    fn span_duration_is_end_minus_start() {
        // start=100, end=350 → Duration=250
        let signal = make_span_signal(100, 350, None, req_resource(&[]));
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(
            row.duration, 250,
            "Duration must equal end_unix_nano - start_unix_nano"
        );
    }

    #[test]
    fn span_zero_duration_is_valid() {
        let signal = make_span_signal(100, 100, None, req_resource(&[]));
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.duration, 0);
    }

    #[test]
    fn span_parent_span_id_none_becomes_empty_string() {
        let signal = make_span_signal(1, 2, None, req_resource(&[]));
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.parent_span_id, "");
    }

    #[test]
    fn span_parent_span_id_some_passes_through() {
        let parent = "c".repeat(16);
        let signal = make_span_signal(1, 2, Some(parent.clone()), req_resource(&[]));
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.parent_span_id, parent);
    }

    // ── Test 3: SentinelSynthetic "true"→1, "false"→0 ────────────────────────

    #[test]
    fn sentinel_synthetic_true_becomes_1() {
        // req_resource already sets "sentinel.synthetic" = "true"
        let signal = make_log_signal(None, None, req_resource(&[]));
        let row = OtelLogRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.sentinel_synthetic, 1, "\"true\" must convert to 1u8");
    }

    #[test]
    fn sentinel_synthetic_false_becomes_0() {
        let mut resource = req_resource(&[]);
        resource.insert("sentinel.synthetic".to_string(), "false".to_string());
        let signal = make_log_signal(None, None, resource);
        let row = OtelLogRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.sentinel_synthetic, 0, "\"false\" must convert to 0u8");
    }

    #[test]
    fn sentinel_synthetic_unknown_string_becomes_0() {
        // Defensive: any value that is not exactly "true" maps to 0
        let mut resource = req_resource(&[]);
        resource.insert("sentinel.synthetic".to_string(), "yes".to_string());
        let signal = make_log_signal(None, None, resource);
        let row = OtelLogRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.sentinel_synthetic, 0);
    }

    // ── Test 4: Hoisting separates required keys from remainder ───────────────

    #[test]
    fn hoist_separates_required_keys_from_extras() {
        let resource = req_resource(&[
            ("cloud.account.id", "proj-123"),
            ("cloud.region", "us-central1"),
        ]);

        let (hoisted, remainder) = hoist(resource);

        // Hoisted fields populated correctly
        assert_eq!(hoisted.service_name, "test-service");
        assert_eq!(hoisted.sentinel_scenario, "baseline");
        assert_eq!(hoisted.sentinel_run_id, "run-001");
        assert_eq!(hoisted.cloud_provider, "gcp");
        assert_eq!(hoisted.sentinel_synthetic, 1);

        // Remainder contains ONLY the extras, not the 5 required keys
        let remainder_keys: Vec<&str> = remainder.iter().map(|(k, _)| k.as_str()).collect();
        assert!(
            remainder_keys.contains(&"cloud.account.id"),
            "extra key must be in remainder"
        );
        assert!(
            remainder_keys.contains(&"cloud.region"),
            "extra key must be in remainder"
        );

        // None of the 5 required keys should appear in the remainder
        for required in REQUIRED_RESOURCE_KEYS {
            assert!(
                !remainder_keys.contains(required),
                "required key {:?} must NOT appear in remainder",
                required
            );
        }

        assert_eq!(
            remainder.len(),
            2,
            "only the 2 extra keys must be in remainder"
        );
    }

    #[test]
    fn hoist_with_no_extras_produces_empty_remainder() {
        let resource = req_resource(&[]);
        let (_hoisted, remainder) = hoist(resource);
        assert!(remainder.is_empty(), "no extras → empty remainder Vec");
    }

    // ── Test 5: MetricType and StatusCode string conversion ───────────────────

    #[test]
    fn metric_type_gauge_becomes_string_gauge() {
        let signal = make_metric_signal(MetricType::Gauge, req_resource(&[]));
        let row = OtelMetricRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.metric_type, "gauge");
    }

    #[test]
    fn metric_type_sum_becomes_string_sum() {
        let signal = make_metric_signal(MetricType::Sum, req_resource(&[]));
        let row = OtelMetricRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.metric_type, "sum");
    }

    #[test]
    fn status_code_ok_becomes_string_ok() {
        let mut signal = make_span_signal(1, 2, None, req_resource(&[]));
        signal.status_code = StatusCode::Ok;
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.status_code, "OK");
    }

    #[test]
    fn status_code_error_becomes_string_error() {
        let mut signal = make_span_signal(1, 2, None, req_resource(&[]));
        signal.status_code = StatusCode::Error;
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.status_code, "ERROR");
    }

    // ── Test 6: Map conversion produces sorted Vec ────────────────────────────

    #[test]
    fn map_to_sorted_vec_produces_sorted_output() {
        let mut map = HashMap::new();
        map.insert("zebra".to_string(), "z".to_string());
        map.insert("apple".to_string(), "a".to_string());
        map.insert("mango".to_string(), "m".to_string());

        let sorted = map_to_sorted_vec(map);

        assert_eq!(sorted.len(), 3);
        assert_eq!(sorted[0].0, "apple");
        assert_eq!(sorted[1].0, "mango");
        assert_eq!(sorted[2].0, "zebra");
    }

    #[test]
    fn map_to_sorted_vec_empty_map_is_empty_vec() {
        let sorted = map_to_sorted_vec(HashMap::new());
        assert!(sorted.is_empty());
    }

    // ── Test 7: Timestamp conversion ─────────────────────────────────────────

    #[test]
    fn nanos_to_offset_dt_epoch_plus_one_second() {
        // 1_000_000_000 nanos = exactly 1 second after Unix epoch
        let dt = nanos_to_offset_dt(1_000_000_000).expect("valid timestamp");
        assert_eq!(dt.unix_timestamp(), 1);
    }

    #[test]
    fn nanos_to_offset_dt_zero_is_epoch() {
        let dt = nanos_to_offset_dt(0).expect("valid timestamp");
        assert_eq!(dt.unix_timestamp(), 0);
    }

    // ── Test 8: Full signal-to-row round-trip for a log signal ───────────────

    #[test]
    fn full_log_row_has_correct_column_count_and_values() {
        let mut attrs = HashMap::new();
        attrs.insert("component.name".to_string(), "receiver".to_string());
        let resource = req_resource(&[("cloud.account.id", "proj-xyz")]);

        let signal = LogSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: 1_700_000_000_000_000_000, // 2023-11-14 (golden file epoch)
            severity_text: "ERROR".to_string(),
            severity_number: 17,
            service_name: "pubsub-ingestion-topic".to_string(),
            body: "connection refused".to_string(),
            trace_id: Some("0".repeat(32)),
            span_id: Some("0".repeat(16)),
            attributes: attrs,
            resource_attributes: resource,
        };

        let row = OtelLogRow::try_from_signal(signal).expect("conversion succeeds");

        assert_eq!(row.severity_text, "ERROR");
        assert_eq!(row.severity_number, 17);
        assert_eq!(row.body, "connection refused");
        assert_eq!(row.trace_id, "0".repeat(32));
        assert_eq!(row.span_id, "0".repeat(16));
        assert_eq!(row.contract_version, "1.0.0");
        assert_eq!(row.service_name, "test-service");
        assert_eq!(row.sentinel_scenario, "baseline");
        assert_eq!(row.sentinel_synthetic, 1);
        assert_eq!(row.cloud_provider, "gcp");
        // LogAttributes: 1 entry (component.name)
        assert_eq!(row.log_attributes.len(), 1);
        assert_eq!(
            row.log_attributes[0],
            ("component.name".to_string(), "receiver".to_string())
        );
        // ResourceAttributes: 1 extra (cloud.account.id), 5 hoisted keys removed
        assert_eq!(row.resource_attributes.len(), 1);
        assert_eq!(
            row.resource_attributes[0],
            ("cloud.account.id".to_string(), "proj-xyz".to_string())
        );
    }
}
