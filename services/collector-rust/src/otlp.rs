//! OTLP proto → [`Signal`] transform — Day 9.
//!
//! Converts `Export*ServiceRequest` proto messages (received over gRPC) into
//! the crate-internal [`Signal`] enum so that the existing
//! [`crate::clickhouse_exporter::export`] path can be reused without change.
//!
//! # Design decisions and impedance-mismatch handling
//!
//! ## `contract_version` synthesis
//!
//! OTLP carries no `contract_version` field — that field belongs to Pod 1's
//! JSON-over-NDJSON contract, not to the OTLP wire format. Every
//! [`Signal`] produced here gets [`CONTRACT_VERSION`] injected so that the
//! exporter rows carry the same version tag as file-mode signals. This is a
//! Pod-2-internal implementation choice; no ADR is warranted.
//!
//! ## Missing `sentinel.*` resource keys
//!
//! Real OTLP traffic from arbitrary senders will not carry the five
//! `sentinel.*` / `cloud.*` / `service.name` resource keys that Pod 1
//! guarantees. The gRPC path deliberately **skips `Signal::validate()`** so
//! this absence is not an error. The exporter's [`crate::clickhouse_exporter`]
//! `hoist()` helper defaults each missing key to an empty string, resulting in
//! empty `SentinelScenario`, `SentinelRunId`, etc. columns. The
//! `service.name` key is handled separately: [`service_name`] falls back to
//! `"unknown_service"` (the OTLP convention for anonymous services) so at
//! least that column is never blank.
//!
//! ## Histogram / ExponentialHistogram / Summary metrics
//!
//! Pod 1's contract v1.0.0 defines only `gauge` and `sum` metric types. The
//! [`Signal`] / [`crate::contract::MetricType`] enum has no `Histogram`
//! variant. OTLP `Histogram`, `ExponentialHistogram`, and `Summary` data
//! points are therefore **silently skipped** at the metric level (the entire
//! OTLP `Metric` message is dropped, not just individual points). Handlers
//! log the received vs. exported metric counts so the skip is observable. A
//! future contract bump that adds `MetricType::Histogram` will need a
//! companion update here.
//!
//! ## `AsInt` data points
//!
//! `NumberDataPoint::Value::AsInt(i64)` is cast to `f64` via `i as f64`.
//! For values ≤ 2^53 this is lossless; larger integers would lose precision,
//! but Pod 1's contract v1.0.0 stores all metric values as `f64` (`value:
//! f64` in [`crate::contract::MetricSignal`]) so the same trade-off already
//! applies on the file-mode path.
//!
//! ## Timestamp narrowing
//!
//! OTLP timestamps are `u64` nanoseconds. The [`Signal`] types store `i64`.
//! The cast `u64 as i64` is used (wraps on values > `i64::MAX`, circa year
//! 2554). This matches the contract's documented `i64` choice: real telemetry
//! timestamps are well within range.

use std::collections::HashMap;

use opentelemetry_proto::tonic::collector::logs::v1::ExportLogsServiceRequest;
use opentelemetry_proto::tonic::collector::metrics::v1::ExportMetricsServiceRequest;
use opentelemetry_proto::tonic::collector::trace::v1::ExportTraceServiceRequest;
use opentelemetry_proto::tonic::common::v1::{any_value, AnyValue, KeyValue};
use opentelemetry_proto::tonic::metrics::v1::{metric, number_data_point};

use crate::contract::{
    LogSignal, MetricSignal, MetricType, Signal, SpanSignal, StatusCode, CONTRACT_VERSION,
};

// ─────────────────────────────────────────────────────────────────────────────
// Low-level helpers
// ─────────────────────────────────────────────────────────────────────────────

/// Encode a byte slice as a lowercase hexadecimal string.
///
/// No external `hex` crate: each byte is formatted with `{:02x}`. Suitable
/// for trace/span IDs (16 bytes → 32 chars, 8 bytes → 16 chars).
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Convert an [`AnyValue`] to a `String` representation.
///
/// Scalars are converted naturally. Complex types (arrays, key-value lists,
/// bytes) and the empty/unset case return an empty string because the
/// [`crate::contract::LogSignal`] `body` and attribute values are typed
/// `String` — there is no structured-value slot in the v1.0.0 contract.
fn any_value_to_string(v: &AnyValue) -> String {
    match &v.value {
        Some(any_value::Value::StringValue(s)) => s.clone(),
        Some(any_value::Value::BoolValue(b)) => {
            if *b {
                "true".to_string()
            } else {
                "false".to_string()
            }
        }
        Some(any_value::Value::IntValue(i)) => i.to_string(),
        Some(any_value::Value::DoubleValue(d)) => d.to_string(),
        // Arrays, KV-lists, bytes, and None → empty; no v1.0.0 representation.
        _ => String::new(),
    }
}

/// Build a `HashMap<String, String>` from a slice of OTLP [`KeyValue`] pairs.
///
/// Entries whose `value` is `None` (the proto optional is unset) are skipped.
/// All values are stringified via [`any_value_to_string`].
fn kv_to_map(attrs: &[KeyValue]) -> HashMap<String, String> {
    attrs
        .iter()
        .filter_map(|kv| {
            kv.value
                .as_ref()
                .map(|v| (kv.key.clone(), any_value_to_string(v)))
        })
        .collect()
}

/// Extract `service.name` from a resource-attribute map, falling back to
/// `"unknown_service"` when the key is absent.
///
/// This follows the OTLP convention for anonymous services and ensures the
/// `ServiceName` ClickHouse column is never blank for OTLP-sourced rows.
fn service_name(resource_attrs: &HashMap<String, String>) -> String {
    resource_attrs
        .get("service.name")
        .cloned()
        .unwrap_or_else(|| "unknown_service".to_string())
}

// ─────────────────────────────────────────────────────────────────────────────
// Top-level transforms
// ─────────────────────────────────────────────────────────────────────────────

/// Convert an [`ExportTraceServiceRequest`] into a flat [`Vec<Signal>`].
///
/// Iterates `resource_spans → scope_spans → spans`. Resource attributes from
/// each `ResourceSpans` are merged into every span it contains.
///
/// # Mapping
///
/// | OTLP field | `SpanSignal` field | Notes |
/// |---|---|---|
/// | `resource.attributes` | `resource_attributes` | merged into each span |
/// | `span.trace_id` bytes | `trace_id` | lowercase hex |
/// | `span.span_id` bytes | `span_id` | lowercase hex |
/// | `span.parent_span_id` | `parent_span_id` | `None` when all-zero or empty |
/// | `span.name` | `name` | |
/// | `span.start_time_unix_nano` | `start_unix_nano` | `u64 as i64` |
/// | `span.end_time_unix_nano` | `end_unix_nano` | `u64 as i64` |
/// | `span.status.code == 2` | `StatusCode::Error` | all other codes → `Ok` |
/// | `span.attributes` | `attributes` | KV → stringified map |
/// | `service.name` resource attr | `service_name` | falls back to `"unknown_service"` |
/// | synthetic | `contract_version` | injected as [`CONTRACT_VERSION`] |
pub fn trace_request_to_signals(req: ExportTraceServiceRequest) -> Vec<Signal> {
    let mut signals = Vec::new();

    for resource_span in req.resource_spans {
        let resource_attrs: HashMap<String, String> = resource_span
            .resource
            .as_ref()
            .map(|r| kv_to_map(&r.attributes))
            .unwrap_or_default();

        let svc = service_name(&resource_attrs);

        for scope_span in resource_span.scope_spans {
            for span in scope_span.spans {
                // Empty parent_span_id (all-zero bytes or zero-length) → None.
                let parent_span_id = if span.parent_span_id.iter().all(|&b| b == 0)
                    || span.parent_span_id.is_empty()
                {
                    None
                } else {
                    Some(hex(&span.parent_span_id))
                };

                // OTLP Status code 2 == Error; 0 (Unset) and 1 (Ok) → Ok.
                let status_code = match span.status.as_ref().map(|s| s.code) {
                    Some(2) => StatusCode::Error,
                    _ => StatusCode::Ok,
                };

                let sig = SpanSignal {
                    contract_version: CONTRACT_VERSION.to_string(),
                    trace_id: hex(&span.trace_id),
                    span_id: hex(&span.span_id),
                    parent_span_id,
                    name: span.name,
                    service_name: svc.clone(),
                    start_unix_nano: span.start_time_unix_nano as i64,
                    end_unix_nano: span.end_time_unix_nano as i64,
                    status_code,
                    attributes: kv_to_map(&span.attributes),
                    resource_attributes: resource_attrs.clone(),
                };
                signals.push(Signal::Span(sig));
            }
        }
    }

    signals
}

/// Convert an [`ExportLogsServiceRequest`] into a flat [`Vec<Signal>`].
///
/// Iterates `resource_logs → scope_logs → log_records`. Resource attributes
/// from each `ResourceLogs` are merged into every record it contains.
///
/// # Mapping
///
/// | OTLP field | `LogSignal` field | Notes |
/// |---|---|---|
/// | `resource.attributes` | `resource_attributes` | merged into each record |
/// | `log.time_unix_nano` | `time_unix_nano` | `u64 as i64` |
/// | `log.severity_number` | `severity_number` | cast from proto enum `i32` |
/// | `log.severity_text` | `severity_text` | |
/// | `log.body` | `body` | stringified; empty string when `None` |
/// | `log.trace_id` bytes | `trace_id` | `None` when all-zero or empty |
/// | `log.span_id` bytes | `span_id` | `None` when all-zero or empty |
/// | `log.attributes` | `attributes` | KV → stringified map |
/// | `service.name` resource attr | `service_name` | falls back to `"unknown_service"` |
/// | synthetic | `contract_version` | injected as [`CONTRACT_VERSION`] |
pub fn logs_request_to_signals(req: ExportLogsServiceRequest) -> Vec<Signal> {
    let mut signals = Vec::new();

    for resource_log in req.resource_logs {
        let resource_attrs: HashMap<String, String> = resource_log
            .resource
            .as_ref()
            .map(|r| kv_to_map(&r.attributes))
            .unwrap_or_default();

        let svc = service_name(&resource_attrs);

        for scope_log in resource_log.scope_logs {
            for record in scope_log.log_records {
                // All-zero or empty bytes → treat as absent.
                let trace_id =
                    if record.trace_id.iter().all(|&b| b == 0) || record.trace_id.is_empty() {
                        None
                    } else {
                        Some(hex(&record.trace_id))
                    };

                let span_id = if record.span_id.iter().all(|&b| b == 0) || record.span_id.is_empty()
                {
                    None
                } else {
                    Some(hex(&record.span_id))
                };

                let body = record
                    .body
                    .as_ref()
                    .map(any_value_to_string)
                    .unwrap_or_default();

                let sig = LogSignal {
                    contract_version: CONTRACT_VERSION.to_string(),
                    time_unix_nano: record.time_unix_nano as i64,
                    severity_text: record.severity_text,
                    severity_number: record.severity_number,
                    service_name: svc.clone(),
                    body,
                    trace_id,
                    span_id,
                    attributes: kv_to_map(&record.attributes),
                    resource_attributes: resource_attrs.clone(),
                };
                signals.push(Signal::Log(sig));
            }
        }
    }

    signals
}

/// Convert an [`ExportMetricsServiceRequest`] into a flat [`Vec<Signal>`].
///
/// Only `Gauge` and `Sum` data are mapped. `Histogram`, `ExponentialHistogram`,
/// and `Summary` are skipped (no `Signal` representation in contract v1.0.0).
/// One `MetricSignal` is produced **per `NumberDataPoint`** — a metric with N
/// points becomes N signals, each carrying the metric name and type.
///
/// Data points whose `value` oneof is `None` are also skipped.
///
/// Returns the signals alongside a count of skipped (non-gauge/sum) OTLP
/// `Metric` messages so callers can log the skip.
pub fn metrics_request_to_signals(req: ExportMetricsServiceRequest) -> (Vec<Signal>, usize) {
    let mut signals = Vec::new();
    let mut skipped_metrics: usize = 0;

    for resource_metric in req.resource_metrics {
        let resource_attrs: HashMap<String, String> = resource_metric
            .resource
            .as_ref()
            .map(|r| kv_to_map(&r.attributes))
            .unwrap_or_default();

        let svc = service_name(&resource_attrs);

        for scope_metric in resource_metric.scope_metrics {
            for metric in scope_metric.metrics {
                let metric_name = metric.name.clone();

                // Resolve data points and MetricType; skip unsupported shapes.
                let (data_points, metric_type) = match metric.data {
                    Some(metric::Data::Gauge(g)) => (g.data_points, MetricType::Gauge),
                    Some(metric::Data::Sum(s)) => (s.data_points, MetricType::Sum),
                    // Histogram, ExponentialHistogram, Summary have no Signal representation.
                    Some(_) | None => {
                        skipped_metrics += 1;
                        continue;
                    }
                };

                for dp in data_points {
                    // Skip data points with no value (degenerate but possible).
                    let value = match dp.value {
                        Some(number_data_point::Value::AsDouble(d)) => d,
                        Some(number_data_point::Value::AsInt(i)) => i as f64,
                        None => continue,
                    };

                    let sig = MetricSignal {
                        contract_version: CONTRACT_VERSION.to_string(),
                        time_unix_nano: dp.time_unix_nano as i64,
                        name: metric_name.clone(),
                        metric_type: metric_type.clone(),
                        value,
                        service_name: svc.clone(),
                        attributes: kv_to_map(&dp.attributes),
                        resource_attributes: resource_attrs.clone(),
                    };
                    signals.push(Signal::Metric(sig));
                }
            }
        }
    }

    (signals, skipped_metrics)
}

// ─────────────────────────────────────────────────────────────────────────────
// Unit tests (no ClickHouse, no network)
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use opentelemetry_proto::tonic::collector::logs::v1::ExportLogsServiceRequest;
    use opentelemetry_proto::tonic::collector::metrics::v1::ExportMetricsServiceRequest;
    use opentelemetry_proto::tonic::collector::trace::v1::ExportTraceServiceRequest;
    use opentelemetry_proto::tonic::common::v1::{any_value, AnyValue, KeyValue};
    use opentelemetry_proto::tonic::logs::v1::{LogRecord, ResourceLogs, ScopeLogs};
    use opentelemetry_proto::tonic::metrics::v1::{
        Gauge, Metric, NumberDataPoint, ResourceMetrics, ScopeMetrics, Sum,
        {metric, number_data_point},
    };
    use opentelemetry_proto::tonic::resource::v1::Resource;
    use opentelemetry_proto::tonic::trace::v1::{ResourceSpans, ScopeSpans, Span, Status};

    use crate::contract::{MetricType, Signal, StatusCode, CONTRACT_VERSION};

    use super::*;

    // ── hex() ────────────────────────────────────────────────────────────────

    #[test]
    fn hex_encodes_bytes_as_lowercase_hex() {
        assert_eq!(hex(&[0xab, 0x01]), "ab01");
        assert_eq!(hex(&[0x00, 0xff]), "00ff");
        assert_eq!(hex(&[]), "");
    }

    // ── any_value_to_string() ─────────────────────────────────────────────────

    #[test]
    fn any_value_string_variant_passthrough() {
        let v = AnyValue {
            value: Some(any_value::Value::StringValue("hello".to_string())),
        };
        assert_eq!(any_value_to_string(&v), "hello");
    }

    #[test]
    fn any_value_bool_true_becomes_true_string() {
        let v = AnyValue {
            value: Some(any_value::Value::BoolValue(true)),
        };
        assert_eq!(any_value_to_string(&v), "true");
    }

    #[test]
    fn any_value_bool_false_becomes_false_string() {
        let v = AnyValue {
            value: Some(any_value::Value::BoolValue(false)),
        };
        assert_eq!(any_value_to_string(&v), "false");
    }

    #[test]
    fn any_value_int_becomes_decimal_string() {
        let v = AnyValue {
            value: Some(any_value::Value::IntValue(42)),
        };
        assert_eq!(any_value_to_string(&v), "42");
    }

    #[test]
    fn any_value_double_becomes_decimal_string() {
        let v = AnyValue {
            value: Some(any_value::Value::DoubleValue(1.5)),
        };
        assert_eq!(any_value_to_string(&v), "1.5");
    }

    #[test]
    fn any_value_none_becomes_empty_string() {
        let v = AnyValue { value: None };
        assert_eq!(any_value_to_string(&v), "");
    }

    // ── service_name() ────────────────────────────────────────────────────────

    #[test]
    fn service_name_extracted_from_resource_attrs() {
        let mut attrs = HashMap::new();
        attrs.insert("service.name".to_string(), "my-service".to_string());
        assert_eq!(service_name(&attrs), "my-service");
    }

    #[test]
    fn service_name_defaults_to_unknown_service_when_absent() {
        let attrs = HashMap::new();
        assert_eq!(service_name(&attrs), "unknown_service");
    }

    // ── trace_request_to_signals() ────────────────────────────────────────────

    fn make_resource(service: &str) -> Resource {
        Resource {
            attributes: vec![KeyValue {
                key: "service.name".to_string(),
                value: Some(AnyValue {
                    value: Some(any_value::Value::StringValue(service.to_string())),
                }),
            }],
            dropped_attributes_count: 0,
        }
    }

    fn make_trace_request(
        trace_id: Vec<u8>,
        span_id: Vec<u8>,
        parent_span_id: Vec<u8>,
        status_code: i32,
        start: u64,
        end: u64,
    ) -> ExportTraceServiceRequest {
        ExportTraceServiceRequest {
            resource_spans: vec![ResourceSpans {
                resource: Some(make_resource("test-svc")),
                scope_spans: vec![ScopeSpans {
                    scope: None,
                    spans: vec![Span {
                        trace_id,
                        span_id,
                        parent_span_id,
                        name: "test-span".to_string(),
                        start_time_unix_nano: start,
                        end_time_unix_nano: end,
                        status: Some(Status {
                            code: status_code,
                            message: String::new(),
                        }),
                        attributes: vec![],
                        ..Span::default()
                    }],
                    schema_url: String::new(),
                }],
                schema_url: String::new(),
            }],
        }
    }

    #[test]
    fn trace_request_produces_span_signal_with_correct_hex_trace_id() {
        let trace_bytes = vec![
            0xab, 0xcd, 0xef, 0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0x01, 0x23, 0x45,
            0x67, 0x89,
        ]; // 16 bytes = 32 hex chars
        let span_bytes = vec![0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]; // 8 bytes = 16 hex chars

        let req = make_trace_request(
            trace_bytes.clone(),
            span_bytes.clone(),
            vec![0u8; 8], // all-zero → None
            0,
            1_900_000_000_000_000_000,
            1_900_000_001_000_000_000,
        );

        let signals = trace_request_to_signals(req);
        assert_eq!(signals.len(), 1);

        match &signals[0] {
            Signal::Span(s) => {
                assert_eq!(s.trace_id, "abcdef0123456789abcdef0123456789");
                assert_eq!(s.span_id, "0102030405060708");
                assert_eq!(s.parent_span_id, None, "all-zero parent → None");
                assert_eq!(s.start_unix_nano, 1_900_000_000_000_000_000_i64);
                assert_eq!(s.end_unix_nano, 1_900_000_001_000_000_000_i64);
                assert_eq!(s.service_name, "test-svc");
            }
            other => panic!("expected Signal::Span, got {other:?}"),
        }
    }

    #[test]
    fn status_code_error_maps_to_status_code_error() {
        let req = make_trace_request(
            vec![0u8; 16],
            vec![0u8; 8],
            vec![0u8; 8],
            2, // OTLP Error
            100,
            200,
        );
        let signals = trace_request_to_signals(req);
        match &signals[0] {
            Signal::Span(s) => assert_eq!(s.status_code, StatusCode::Error),
            other => panic!("expected Signal::Span, got {other:?}"),
        }
    }

    #[test]
    fn status_code_ok_and_unset_map_to_status_code_ok() {
        for code in [0i32, 1i32] {
            let req = make_trace_request(vec![0u8; 16], vec![0u8; 8], vec![0u8; 8], code, 1, 2);
            let signals = trace_request_to_signals(req);
            match &signals[0] {
                Signal::Span(s) => assert_eq!(
                    s.status_code,
                    StatusCode::Ok,
                    "code={code} should map to Ok"
                ),
                other => panic!("expected Signal::Span, got {other:?}"),
            }
        }
    }

    #[test]
    fn non_zero_parent_span_id_is_some() {
        let parent = vec![0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11];
        let req = make_trace_request(vec![0u8; 16], vec![0u8; 8], parent.clone(), 0, 1, 2);
        let signals = trace_request_to_signals(req);
        match &signals[0] {
            Signal::Span(s) => assert_eq!(s.parent_span_id, Some(hex(&parent))),
            other => panic!("expected Signal::Span, got {other:?}"),
        }
    }

    #[test]
    fn contract_version_is_injected_on_span() {
        let req = make_trace_request(vec![0u8; 16], vec![0u8; 8], vec![0u8; 8], 0, 1, 2);
        let signals = trace_request_to_signals(req);
        match &signals[0] {
            Signal::Span(s) => assert_eq!(s.contract_version, CONTRACT_VERSION),
            other => panic!("expected Signal::Span, got {other:?}"),
        }
    }

    // ── logs_request_to_signals() ─────────────────────────────────────────────

    fn make_logs_request(body_str: &str) -> ExportLogsServiceRequest {
        ExportLogsServiceRequest {
            resource_logs: vec![ResourceLogs {
                resource: Some(make_resource("log-svc")),
                scope_logs: vec![ScopeLogs {
                    scope: None,
                    log_records: vec![LogRecord {
                        time_unix_nano: 1_900_000_000_000_000_000,
                        severity_number: 9,
                        severity_text: "INFO".to_string(),
                        body: Some(AnyValue {
                            value: Some(any_value::Value::StringValue(body_str.to_string())),
                        }),
                        trace_id: vec![0u8; 16],
                        span_id: vec![0u8; 8],
                        ..LogRecord::default()
                    }],
                    schema_url: String::new(),
                }],
                schema_url: String::new(),
            }],
        }
    }

    #[test]
    fn logs_request_produces_log_signal_with_correct_body() {
        let signals = logs_request_to_signals(make_logs_request("hello world"));
        assert_eq!(signals.len(), 1);
        match &signals[0] {
            Signal::Log(l) => {
                assert_eq!(l.body, "hello world");
                assert_eq!(l.service_name, "log-svc");
                assert_eq!(l.severity_text, "INFO");
                assert_eq!(l.severity_number, 9);
                // all-zero trace_id and span_id → None
                assert_eq!(l.trace_id, None);
                assert_eq!(l.span_id, None);
                assert_eq!(l.contract_version, CONTRACT_VERSION);
            }
            other => panic!("expected Signal::Log, got {other:?}"),
        }
    }

    #[test]
    fn log_with_non_zero_trace_span_ids_are_some() {
        let trace = vec![0x01u8; 16];
        let span_bytes = vec![0x02u8; 8];
        let req = ExportLogsServiceRequest {
            resource_logs: vec![ResourceLogs {
                resource: Some(make_resource("s")),
                scope_logs: vec![ScopeLogs {
                    scope: None,
                    log_records: vec![LogRecord {
                        time_unix_nano: 1,
                        trace_id: trace.clone(),
                        span_id: span_bytes.clone(),
                        ..LogRecord::default()
                    }],
                    schema_url: String::new(),
                }],
                schema_url: String::new(),
            }],
        };
        let signals = logs_request_to_signals(req);
        match &signals[0] {
            Signal::Log(l) => {
                assert_eq!(l.trace_id, Some(hex(&trace)));
                assert_eq!(l.span_id, Some(hex(&span_bytes)));
            }
            other => panic!("expected Signal::Log, got {other:?}"),
        }
    }

    // ── metrics_request_to_signals() ─────────────────────────────────────────

    fn make_gauge_request(data_points: Vec<NumberDataPoint>) -> ExportMetricsServiceRequest {
        ExportMetricsServiceRequest {
            resource_metrics: vec![ResourceMetrics {
                resource: Some(make_resource("metric-svc")),
                scope_metrics: vec![ScopeMetrics {
                    scope: None,
                    metrics: vec![Metric {
                        name: "test.gauge".to_string(),
                        data: Some(metric::Data::Gauge(Gauge { data_points })),
                        ..Metric::default()
                    }],
                    schema_url: String::new(),
                }],
                schema_url: String::new(),
            }],
        }
    }

    fn make_dp_double(value: f64, time_unix_nano: u64) -> NumberDataPoint {
        NumberDataPoint {
            time_unix_nano,
            value: Some(number_data_point::Value::AsDouble(value)),
            ..NumberDataPoint::default()
        }
    }

    fn make_dp_int(value: i64, time_unix_nano: u64) -> NumberDataPoint {
        NumberDataPoint {
            time_unix_nano,
            value: Some(number_data_point::Value::AsInt(value)),
            ..NumberDataPoint::default()
        }
    }

    #[test]
    fn gauge_with_two_data_points_produces_two_signals() {
        let req = make_gauge_request(vec![
            make_dp_double(1.0, 1_900_000_000_000_000_001),
            make_dp_double(2.0, 1_900_000_000_000_000_002),
        ]);
        let (signals, skipped) = metrics_request_to_signals(req);
        assert_eq!(signals.len(), 2);
        assert_eq!(skipped, 0);

        for sig in &signals {
            match sig {
                Signal::Metric(m) => {
                    assert_eq!(m.metric_type, MetricType::Gauge);
                    assert_eq!(m.name, "test.gauge");
                    assert_eq!(m.service_name, "metric-svc");
                    assert_eq!(m.contract_version, CONTRACT_VERSION);
                }
                other => panic!("expected Signal::Metric, got {other:?}"),
            }
        }
    }

    #[test]
    fn as_int_data_point_value_cast_to_f64() {
        let req = make_gauge_request(vec![make_dp_int(42, 1_900_000_000_000_000_001)]);
        let (signals, _) = metrics_request_to_signals(req);
        assert_eq!(signals.len(), 1);
        match &signals[0] {
            Signal::Metric(m) => assert_eq!(m.value, 42.0_f64),
            other => panic!("expected Signal::Metric, got {other:?}"),
        }
    }

    #[test]
    fn histogram_metric_produces_zero_signals_and_one_skipped() {
        use opentelemetry_proto::tonic::metrics::v1::Histogram;
        let req = ExportMetricsServiceRequest {
            resource_metrics: vec![ResourceMetrics {
                resource: Some(make_resource("s")),
                scope_metrics: vec![ScopeMetrics {
                    scope: None,
                    metrics: vec![Metric {
                        name: "hist.metric".to_string(),
                        data: Some(metric::Data::Histogram(Histogram {
                            data_points: vec![],
                            aggregation_temporality: 0,
                        })),
                        ..Metric::default()
                    }],
                    schema_url: String::new(),
                }],
                schema_url: String::new(),
            }],
        };
        let (signals, skipped) = metrics_request_to_signals(req);
        assert_eq!(signals.len(), 0, "histogram produces no signals");
        assert_eq!(skipped, 1, "histogram counts as one skipped metric");
    }

    #[test]
    fn sum_metric_produces_signals() {
        let req = ExportMetricsServiceRequest {
            resource_metrics: vec![ResourceMetrics {
                resource: Some(make_resource("s")),
                scope_metrics: vec![ScopeMetrics {
                    scope: None,
                    metrics: vec![Metric {
                        name: "sum.metric".to_string(),
                        data: Some(metric::Data::Sum(Sum {
                            data_points: vec![make_dp_double(99.0, 1_000)],
                            aggregation_temporality: 0,
                            is_monotonic: false,
                        })),
                        ..Metric::default()
                    }],
                    schema_url: String::new(),
                }],
                schema_url: String::new(),
            }],
        };
        let (signals, skipped) = metrics_request_to_signals(req);
        assert_eq!(signals.len(), 1);
        assert_eq!(skipped, 0);
        match &signals[0] {
            Signal::Metric(m) => {
                assert_eq!(m.metric_type, MetricType::Sum);
                assert_eq!(m.value, 99.0);
            }
            other => panic!("expected Signal::Metric, got {other:?}"),
        }
    }

    #[test]
    fn service_name_absent_from_resource_becomes_unknown_service() {
        // A request with a resource that has no service.name attribute.
        let req = ExportTraceServiceRequest {
            resource_spans: vec![ResourceSpans {
                resource: Some(Resource {
                    attributes: vec![], // no service.name
                    dropped_attributes_count: 0,
                }),
                scope_spans: vec![ScopeSpans {
                    scope: None,
                    spans: vec![Span {
                        name: "s".to_string(),
                        ..Span::default()
                    }],
                    schema_url: String::new(),
                }],
                schema_url: String::new(),
            }],
        };
        let signals = trace_request_to_signals(req);
        match &signals[0] {
            Signal::Span(s) => assert_eq!(s.service_name, "unknown_service"),
            other => panic!("expected Signal::Span, got {other:?}"),
        }
    }
}
