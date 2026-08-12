//! ClickHouse exporter for Sentinel OTel Collector — Day 4.
//!
//! Converts parsed [`Signal`] values into typed Row structs and writes them to the
//! bronze tables in database `bronze`: `otel_logs`, `otel_traces`, and the per-type
//! `otel_metrics_gauge` / `otel_metrics_sum`.
//!
//! # Connection model
//!
//! The `clickhouse` 0.13 crate speaks **HTTP on port 8123** (RowBinary over
//! HTTP — not the native TCP protocol on 9000). The client URL is read from
//! `CLICKHOUSE_URL` (default `http://localhost:8123`). Database is `bronze`.
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
//! # Resource attributes (bronze)
//!
//! For the bronze tables, only `service.name` is copied into the typed `ServiceName`
//! column; ALL resource attributes (incl. the
//! `sentinel.*` / `cloud.provider` keys and the synthesized `contract_version`) are
//! retained in `ResourceAttributes`, matching the contrib/bronze convention — bronze
//! has no typed columns for them. See [`service_name_and_resource`].

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

/// Build a [`clickhouse::Client`] targeting the given URL, database `bronze`.
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
    build_client_with_database(url, "bronze")
}

/// Build a [`clickhouse::Client`] targeting `url` and a specific `database`.
///
/// Used by the config-driven binary path so `clickhouse.database` from
/// `config.yaml` is honoured. [`build_client`] is the `database = "bronze"`
/// convenience wrapper.
pub fn build_client_with_database(url: &str, database: &str) -> clickhouse::Client {
    clickhouse::Client::default()
        .with_url(url)
        .with_database(database)
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
    build_client(&url_from_env().unwrap_or_else(|| DEFAULT_CLICKHOUSE_URL.to_string()))
}

/// Read the `CLICKHOUSE_URL` env var, returning `None` when it is unset.
///
/// Used by the binary entry point to decide between **export mode** (URL set →
/// parse + write to ClickHouse) and **count mode** (URL unset → parse only, no
/// ClickHouse dependency). Returning `Option` keeps the "is export configured?"
/// decision out of `main` while keeping the single `std::env` access in this
/// module (the `disallowed_methods` lint forbids it elsewhere in library code;
/// real config will move to the Sentinel config loader — see ADR-0004 follow-ups).
#[must_use]
pub fn url_from_env() -> Option<String> {
    // The one sanctioned `std::env::var` call site in the library. Binary +
    // test callers rely on this rather than reading the environment directly.
    #[allow(clippy::disallowed_methods)]
    std::env::var("CLICKHOUSE_URL").ok()
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

/// Copy `service.name` into the typed `ServiceName` bronze column and return the
/// FULL resource map — every key retained, matching the contrib/bronze convention —
/// as a sorted `Vec`, with the synthesized `contract_version` folded in.
///
/// The `sentinel.*` / `cloud.provider` keys are NOT stripped: the bronze tables have
/// no typed columns for them, so they are preserved inside `ResourceAttributes`.
fn service_name_and_resource(
    mut resource: HashMap<String, String>,
    contract_version: String,
) -> (String, Vec<(String, String)>) {
    let service_name = resource.get("service.name").cloned().unwrap_or_default();
    resource.insert("contract_version".to_string(), contract_version);
    (service_name, map_to_sorted_vec(resource))
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

/// One row in the bronze `otel_logs` table (`bronze.*`, OTel-contrib v0.105.0 shape).
///
/// Named-column INSERT: bronze columns this collector does not produce (TraceFlags,
/// Scope*, schema URLs, TimestampDate/Time) take their ClickHouse defaults. Sentinel
/// metadata (`sentinel.*`, `cloud.provider`, `contract_version`) is carried inside
/// `ResourceAttributes`, not as typed columns (bronze has none).
#[derive(clickhouse::Row, Serialize, Debug)]
pub struct OtelLogRow {
    #[serde(
        rename = "Timestamp",
        with = "clickhouse::serde::time::datetime64::nanos"
    )]
    pub timestamp: OffsetDateTime,
    #[serde(rename = "ServiceName")]
    pub service_name: String,
    #[serde(rename = "SeverityText")]
    pub severity_text: String,
    /// Bronze `SeverityNumber` is `UInt8` (OTLP severity is 0..=24).
    #[serde(rename = "SeverityNumber")]
    pub severity_number: u8,
    #[serde(rename = "Body")]
    pub body: String,
    /// `''` when absent (ADR-0006); consistent with bronze's plain-`String` ID columns.
    #[serde(rename = "TraceId")]
    pub trace_id: String,
    #[serde(rename = "SpanId")]
    pub span_id: String,
    #[serde(rename = "LogAttributes")]
    pub log_attributes: Vec<(String, String)>,
    #[serde(rename = "ResourceAttributes")]
    pub resource_attributes: Vec<(String, String)>,
}

/// One row in the bronze `otel_traces` table (`bronze.*`, OTel-contrib v0.105.0 shape).
///
/// Named-column INSERT: bronze columns this collector does not produce (TraceState,
/// SpanKind, Scope*, StatusMessage, Events.*, Links.*) take their ClickHouse defaults.
/// Sentinel metadata + `contract_version` live in `ResourceAttributes`.
#[derive(clickhouse::Row, Serialize, Debug)]
pub struct OtelTraceRow {
    #[serde(
        rename = "Timestamp",
        with = "clickhouse::serde::time::datetime64::nanos"
    )]
    pub timestamp: OffsetDateTime,
    #[serde(rename = "TraceId")]
    pub trace_id: String,
    #[serde(rename = "SpanId")]
    pub span_id: String,
    /// `''` for root spans (ADR-0006).
    #[serde(rename = "ParentSpanId")]
    pub parent_span_id: String,
    #[serde(rename = "SpanName")]
    pub span_name: String,
    #[serde(rename = "ServiceName")]
    pub service_name: String,
    /// `end_unix_nano - start_unix_nano` (nanoseconds).
    #[serde(rename = "Duration")]
    pub duration: i64,
    #[serde(rename = "StatusCode")]
    pub status_code: String,
    #[serde(rename = "SpanAttributes")]
    pub span_attributes: Vec<(String, String)>,
    #[serde(rename = "ResourceAttributes")]
    pub resource_attributes: Vec<(String, String)>,
}

/// One row in the bronze metric tables `otel_metrics_gauge` / `otel_metrics_sum`
/// (`bronze.*`, OTel-contrib v0.105.0 shape). The datapoint type selects the table
/// (see [`export`]) — there is no `MetricType` column. Named-column INSERT, so bronze
/// columns this collector does not produce (Scope*, MetricDescription/Unit,
/// StartTimeUnix, Flags, Exemplars.*, AggregationTemporality, IsMonotonic) take
/// ClickHouse defaults. Sentinel metadata + `contract_version` live in
/// `ResourceAttributes`.
#[derive(clickhouse::Row, Serialize, Debug)]
pub struct OtelMetricRow {
    #[serde(rename = "ServiceName")]
    pub service_name: String,
    #[serde(rename = "MetricName")]
    pub metric_name: String,
    #[serde(
        rename = "TimeUnix",
        with = "clickhouse::serde::time::datetime64::nanos"
    )]
    pub time_unix: OffsetDateTime,
    #[serde(rename = "Value")]
    pub value: f64,
    #[serde(rename = "Attributes")]
    pub attributes: Vec<(String, String)>,
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
        let (service_name, resource_attributes) =
            service_name_and_resource(signal.resource_attributes, signal.contract_version);
        let log_attributes = map_to_sorted_vec(signal.attributes);

        Ok(Self {
            timestamp,
            service_name,
            severity_text: signal.severity_text,
            // Bronze SeverityNumber is UInt8; OTLP severity is 0..=24.
            severity_number: u8::try_from(signal.severity_number).unwrap_or(0),
            body: signal.body,
            // None → '' per ADR-0006 (empty-string sentinel for optional IDs).
            trace_id: signal.trace_id.unwrap_or_default(),
            span_id: signal.span_id.unwrap_or_default(),
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
        let (service_name, resource_attributes) =
            service_name_and_resource(signal.resource_attributes, signal.contract_version);
        let span_attributes = map_to_sorted_vec(signal.attributes);

        // "Ok"/"Error" matches the contrib bronze StatusCode convention (R3). OTLP "Unset"
        // is collapsed to "Ok" upstream (otlp.rs), so this collector never emits "Unset".
        let status_code = match signal.status_code {
            StatusCode::Ok => "Ok".to_string(),
            StatusCode::Error => "Error".to_string(),
        };

        Ok(Self {
            timestamp,
            trace_id: signal.trace_id,
            span_id: signal.span_id,
            parent_span_id: signal.parent_span_id.unwrap_or_default(),
            span_name: signal.name,
            service_name,
            duration,
            status_code,
            span_attributes,
            resource_attributes,
        })
    }
}

impl OtelMetricRow {
    /// Convert a [`MetricSignal`] to a row. The datapoint type is consumed by
    /// [`export`] to pick the gauge/sum table; it is not stored as a column.
    pub fn try_from_signal(signal: MetricSignal) -> Result<Self, ExporterError> {
        let time_unix = nanos_to_offset_dt(signal.time_unix_nano)?;
        let (service_name, resource_attributes) =
            service_name_and_resource(signal.resource_attributes, signal.contract_version);
        let attributes = map_to_sorted_vec(signal.attributes);

        Ok(Self {
            service_name,
            metric_name: signal.name,
            time_unix,
            value: signal.value,
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
/// Partitions signals by destination table, converts each to the appropriate Row
/// struct, and performs one batched `INSERT` per non-empty table — logs, traces, and
/// the per-type metric tables `otel_metrics_gauge` / `otel_metrics_sum`. Returns
/// per-type counts of successfully written rows.
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
    // Partition signals by destination table. Metrics fan out to the bronze per-type
    // tables — the datapoint type selects gauge vs sum.
    let mut log_rows: Vec<OtelLogRow> = Vec::new();
    let mut trace_rows: Vec<OtelTraceRow> = Vec::new();
    let mut gauge_rows: Vec<OtelMetricRow> = Vec::new();
    let mut sum_rows: Vec<OtelMetricRow> = Vec::new();

    for signal in signals {
        match signal {
            Signal::Log(log) => {
                log_rows.push(OtelLogRow::try_from_signal(log)?);
            }
            Signal::Span(span) => {
                trace_rows.push(OtelTraceRow::try_from_signal(span)?);
            }
            Signal::Metric(metric) => {
                let is_gauge = metric.metric_type == MetricType::Gauge;
                let row = OtelMetricRow::try_from_signal(metric)?;
                if is_gauge {
                    gauge_rows.push(row);
                } else {
                    sum_rows.push(row);
                }
            }
        }
    }

    // Independent destination inserts run concurrently, matching Go's
    // per-stream flush goroutines and removing four serialized HTTP round trips
    // from every mixed batch.
    let insert_logs = async {
        if !log_rows.is_empty() {
            let mut insert = client.insert("otel_logs")?;
            for row in &log_rows {
                insert.write(row).await?;
            }
            insert.end().await?;
        }
        Ok::<(), ExporterError>(())
    };
    let insert_traces = async {
        if !trace_rows.is_empty() {
            let mut insert = client.insert("otel_traces")?;
            for row in &trace_rows {
                insert.write(row).await?;
            }
            insert.end().await?;
        }
        Ok::<(), ExporterError>(())
    };
    let insert_gauges = async {
        if !gauge_rows.is_empty() {
            let mut insert = client.insert("otel_metrics_gauge")?;
            for row in &gauge_rows {
                insert.write(row).await?;
            }
            insert.end().await?;
        }
        Ok::<(), ExporterError>(())
    };
    let insert_sums = async {
        if !sum_rows.is_empty() {
            let mut insert = client.insert("otel_metrics_sum")?;
            for row in &sum_rows {
                insert.write(row).await?;
            }
            insert.end().await?;
        }
        Ok::<(), ExporterError>(())
    };

    tokio::try_join!(insert_logs, insert_traces, insert_gauges, insert_sums)?;

    Ok(Counts {
        logs: log_rows.len(),
        spans: trace_rows.len(),
        metrics: gauge_rows.len() + sum_rows.len(),
        ..Counts::default()
    })
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
    use crate::contract::{MetricType, StatusCode};

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

    // ── Test 3: sentinel.* + contract_version land in ResourceAttributes ──────
    // Bronze otel_logs/otel_traces have no typed Sentinel columns; the values are
    // preserved (not stripped) inside the ResourceAttributes Map.

    #[test]
    fn sentinel_keys_and_contract_version_kept_in_resource_attributes() {
        let signal = make_log_signal(None, None, req_resource(&[]));
        let row = OtelLogRow::try_from_signal(signal).expect("conversion succeeds");
        let ra: HashMap<String, String> = row.resource_attributes.iter().cloned().collect();
        assert_eq!(
            ra.get("sentinel.scenario").map(String::as_str),
            Some("baseline")
        );
        assert_eq!(
            ra.get("sentinel.run_id").map(String::as_str),
            Some("run-001")
        );
        assert_eq!(
            ra.get("sentinel.synthetic").map(String::as_str),
            Some("true")
        );
        assert_eq!(ra.get("cloud.provider").map(String::as_str), Some("gcp"));
        assert_eq!(
            ra.get("contract_version").map(String::as_str),
            Some("1.0.0")
        );
        // service.name is copied to the typed column AND retained in the map.
        assert_eq!(row.service_name, "test-service");
        assert_eq!(
            ra.get("service.name").map(String::as_str),
            Some("test-service")
        );
    }

    // ── Test 4: metric row maps to the bronze gauge/sum shape ─────────────────
    // MetricType is no longer a column — the datapoint type selects the table in
    // export(); sentinel.* + contract_version live in ResourceAttributes.

    #[test]
    fn metric_row_maps_to_bronze_shape() {
        let signal = make_metric_signal(MetricType::Gauge, req_resource(&[]));
        let row = OtelMetricRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.metric_name, "test.metric");
        assert_eq!(row.value, 42.0);
        assert_eq!(row.service_name, "test-service");
        let ra: HashMap<String, String> = row.resource_attributes.iter().cloned().collect();
        assert_eq!(
            ra.get("sentinel.scenario").map(String::as_str),
            Some("baseline")
        );
        assert_eq!(
            ra.get("contract_version").map(String::as_str),
            Some("1.0.0")
        );
    }

    // ── Test 5: StatusCode string conversion ──────────────────────────────────

    #[test]
    fn status_code_ok_becomes_string_ok() {
        let mut signal = make_span_signal(1, 2, None, req_resource(&[]));
        signal.status_code = StatusCode::Ok;
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.status_code, "Ok");
    }

    #[test]
    fn status_code_error_becomes_string_error() {
        let mut signal = make_span_signal(1, 2, None, req_resource(&[]));
        signal.status_code = StatusCode::Error;
        let row = OtelTraceRow::try_from_signal(signal).expect("conversion succeeds");
        assert_eq!(row.status_code, "Error");
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
    fn full_log_row_maps_to_bronze_shape() {
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
        assert_eq!(row.severity_number, 17u8);
        assert_eq!(row.body, "connection refused");
        assert_eq!(row.trace_id, "0".repeat(32));
        assert_eq!(row.span_id, "0".repeat(16));
        // service.name → typed ServiceName column (from the resource map, not the signal field).
        assert_eq!(row.service_name, "test-service");
        // LogAttributes: 1 entry (component.name)
        assert_eq!(row.log_attributes.len(), 1);
        assert_eq!(
            row.log_attributes[0],
            ("component.name".to_string(), "receiver".to_string())
        );
        // ResourceAttributes retains ALL resource keys (nothing stripped) + contract_version.
        let ra: HashMap<String, String> = row.resource_attributes.iter().cloned().collect();
        assert_eq!(
            ra.get("service.name").map(String::as_str),
            Some("test-service")
        );
        assert_eq!(
            ra.get("cloud.account.id").map(String::as_str),
            Some("proj-xyz")
        );
        assert_eq!(
            ra.get("sentinel.scenario").map(String::as_str),
            Some("baseline")
        );
        assert_eq!(
            ra.get("contract_version").map(String::as_str),
            Some("1.0.0")
        );
    }
}
