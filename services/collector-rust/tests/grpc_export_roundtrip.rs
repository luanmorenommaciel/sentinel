//! OTLP → ClickHouse round-trip integration test — Day 9.
//!
//! Proves that a real OTLP payload sent over gRPC lands in ClickHouse.
//!
//! # Running
//!
//! This test is `#[ignore]`d — it requires a live ClickHouse instance.
//! Bring up the Sentinel stack first, then run:
//!
//! ```sh
//! # From services/collector-rust/
//! docker compose -f ../../infra/docker-compose.yml up -d clickhouse
//! cargo test --test grpc_export_roundtrip -- --ignored
//! ```
//!
//! `CLICKHOUSE_URL` (default `http://localhost:8123`) and
//! `CLICKHOUSE_DATABASE` (default `default`) may be overridden via
//! environment variables.
//!
//! # Timestamp note
//!
//! All timestamps are set to a 2026-era value (`1_900_000_000_000_000_000`
//! nanoseconds ≈ 2030-03-17). ClickHouse TTL rules in the DDL are configured
//! for data older than N days/months; using a recent timestamp ensures rows
//! do not expire between `INSERT` and `SELECT count()`.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::time::Duration;

use tokio::net::TcpListener;
use tokio::sync::oneshot;

use opentelemetry_proto::tonic::collector::logs::v1::{
    logs_service_client::LogsServiceClient, ExportLogsServiceRequest,
};
use opentelemetry_proto::tonic::collector::metrics::v1::{
    metrics_service_client::MetricsServiceClient, ExportMetricsServiceRequest,
};
use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_client::TraceServiceClient, ExportTraceServiceRequest,
};
use opentelemetry_proto::tonic::common::v1::{any_value, AnyValue, KeyValue};
use opentelemetry_proto::tonic::logs::v1::{LogRecord, ResourceLogs, ScopeLogs};
use opentelemetry_proto::tonic::metrics::v1::{
    Gauge, Metric, NumberDataPoint, ResourceMetrics, ScopeMetrics, {metric, number_data_point},
};
use opentelemetry_proto::tonic::resource::v1::Resource;
use opentelemetry_proto::tonic::trace::v1::{ResourceSpans, ScopeSpans, Span, Status};

use sentinel_collector::clickhouse_exporter;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/// A 2026-era timestamp in nanoseconds. Recent enough that ClickHouse TTL
/// rules (which expire old data) will not delete rows between INSERT and
/// SELECT.
const TIMESTAMP_NANOS: u64 = 1_900_000_000_000_000_000;

/// Build a ClickHouse client from the environment.
///
/// Uses `CLICKHOUSE_URL` (defaults to `http://localhost:8123`) and
/// `CLICKHOUSE_DATABASE` (defaults to `default`).
fn client_from_env() -> clickhouse::Client {
    #[allow(clippy::disallowed_methods)]
    let url =
        std::env::var("CLICKHOUSE_URL").unwrap_or_else(|_| "http://localhost:8123".to_string());
    #[allow(clippy::disallowed_methods)]
    let database = std::env::var("CLICKHOUSE_DATABASE").unwrap_or_else(|_| "default".to_string());
    clickhouse_exporter::build_client_with_database(&url, &database)
}

/// Build a `Resource` carrying `service.name`.
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

/// Start the gRPC server on an ephemeral port in export mode.
///
/// Returns the bound address, a shutdown sender, and the server join handle.
async fn start_export_server(
    ch_client: clickhouse::Client,
) -> (
    std::net::SocketAddr,
    oneshot::Sender<()>,
    tokio::task::JoinHandle<()>,
) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let (tx, rx) = oneshot::channel::<()>();

    let handle = tokio::spawn(async move {
        let shutdown = async {
            let _ = rx.await;
        };
        sentinel_collector::grpc::serve_with_listener(
            listener,
            shutdown,
            Some(ch_client),
            // Transport test: pin to Off so row counts are deterministic and
            // independent of the validation policy (the payload deliberately
            // omits the sentinel.* resource keys).
            sentinel_collector::config::GrpcValidation::Off,
        )
        .await
        .expect("server runs cleanly");
    });

    // Give the spawned task a tick to enter serve().
    tokio::time::sleep(Duration::from_millis(100)).await;
    (addr, tx, handle)
}

// ─────────────────────────────────────────────────────────────────────────────
// Integration test
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::test]
#[ignore = "requires a live ClickHouse instance — run with --ignored"]
async fn otlp_grpc_payload_lands_in_clickhouse() {
    // ── 1. Build a ClickHouse client for the server and for verification ───
    let server_ch = client_from_env();
    let verify_ch = client_from_env();

    // ── 2. TRUNCATE the three tables so we start from a clean slate ────────
    // Using raw SQL queries via the execute() API.
    for table in ["otel_logs", "otel_traces", "otel_metrics"] {
        verify_ch
            .query(&format!("TRUNCATE TABLE {table}"))
            .execute()
            .await
            .unwrap_or_else(|e| panic!("TRUNCATE {table} failed: {e}"));
    }

    // ── 3. Start the gRPC server in export mode ────────────────────────────
    let (addr, shutdown_tx, server_handle) = start_export_server(server_ch).await;
    let base_url = format!("http://{addr}");

    // ── 4. Send a trace request (2 spans) ─────────────────────────────────
    let mut trace_client = TraceServiceClient::connect(base_url.clone())
        .await
        .expect("trace client connects");

    let trace_req = ExportTraceServiceRequest {
        resource_spans: vec![ResourceSpans {
            resource: Some(make_resource("roundtrip-svc")),
            scope_spans: vec![ScopeSpans {
                scope: None,
                spans: vec![
                    Span {
                        // trace_id: 16 bytes → 32 hex chars
                        trace_id: vec![0x01u8; 16],
                        span_id: vec![0x02u8; 8],
                        parent_span_id: vec![0u8; 8], // root
                        name: "span-one".to_string(),
                        start_time_unix_nano: TIMESTAMP_NANOS,
                        end_time_unix_nano: TIMESTAMP_NANOS + 1_000_000,
                        status: Some(Status {
                            code: 1, // Ok
                            message: String::new(),
                        }),
                        ..Span::default()
                    },
                    Span {
                        trace_id: vec![0x03u8; 16],
                        span_id: vec![0x04u8; 8],
                        parent_span_id: vec![0u8; 8],
                        name: "span-two".to_string(),
                        start_time_unix_nano: TIMESTAMP_NANOS + 5_000_000,
                        end_time_unix_nano: TIMESTAMP_NANOS + 10_000_000,
                        status: Some(Status {
                            code: 2, // Error
                            message: String::new(),
                        }),
                        ..Span::default()
                    },
                ],
                schema_url: String::new(),
            }],
            schema_url: String::new(),
        }],
    };

    trace_client
        .export(trace_req)
        .await
        .expect("trace export succeeds");

    // ── 5. Send a logs request (1 log record) ─────────────────────────────
    let mut logs_client = LogsServiceClient::connect(base_url.clone())
        .await
        .expect("logs client connects");

    let logs_req = ExportLogsServiceRequest {
        resource_logs: vec![ResourceLogs {
            resource: Some(make_resource("roundtrip-svc")),
            scope_logs: vec![ScopeLogs {
                scope: None,
                log_records: vec![LogRecord {
                    time_unix_nano: TIMESTAMP_NANOS,
                    severity_number: 9, // INFO
                    severity_text: "INFO".to_string(),
                    body: Some(AnyValue {
                        value: Some(any_value::Value::StringValue(
                            "roundtrip test log".to_string(),
                        )),
                    }),
                    trace_id: vec![0u8; 16], // no trace correlation
                    span_id: vec![0u8; 8],
                    ..LogRecord::default()
                }],
                schema_url: String::new(),
            }],
            schema_url: String::new(),
        }],
    };

    logs_client
        .export(logs_req)
        .await
        .expect("logs export succeeds");

    // ── 6. Send a metrics request (1 gauge metric, 1 data point) ──────────
    let mut metrics_client = MetricsServiceClient::connect(base_url.clone())
        .await
        .expect("metrics client connects");

    let metrics_req = ExportMetricsServiceRequest {
        resource_metrics: vec![ResourceMetrics {
            resource: Some(make_resource("roundtrip-svc")),
            scope_metrics: vec![ScopeMetrics {
                scope: None,
                metrics: vec![Metric {
                    name: "roundtrip.test.gauge".to_string(),
                    data: Some(metric::Data::Gauge(Gauge {
                        data_points: vec![NumberDataPoint {
                            time_unix_nano: TIMESTAMP_NANOS,
                            value: Some(number_data_point::Value::AsDouble(42.0)),
                            ..NumberDataPoint::default()
                        }],
                    })),
                    ..Metric::default()
                }],
                schema_url: String::new(),
            }],
            schema_url: String::new(),
        }],
    };

    metrics_client
        .export(metrics_req)
        .await
        .expect("metrics export succeeds");

    // Give ClickHouse a moment to flush (RowBinary inserts are synchronous in
    // the `clickhouse` crate but a small sleep guards against any async flush
    // in the server task).
    tokio::time::sleep(Duration::from_millis(200)).await;

    // ── 7. Verify row counts in ClickHouse ────────────────────────────────
    let trace_count: u64 = verify_ch
        .query("SELECT count() FROM otel_traces")
        .fetch_one()
        .await
        .expect("SELECT count() FROM otel_traces");

    let log_count: u64 = verify_ch
        .query("SELECT count() FROM otel_logs")
        .fetch_one()
        .await
        .expect("SELECT count() FROM otel_logs");

    let metric_count: u64 = verify_ch
        .query("SELECT count() FROM otel_metrics")
        .fetch_one()
        .await
        .expect("SELECT count() FROM otel_metrics");

    // ── 8. Shut down the server ────────────────────────────────────────────
    let _ = shutdown_tx.send(());
    server_handle.await.expect("server shuts down cleanly");

    // ── 9. Assert ─────────────────────────────────────────────────────────
    assert_eq!(trace_count, 2, "expected 2 spans in otel_traces");
    assert_eq!(log_count, 1, "expected 1 log in otel_logs");
    assert_eq!(metric_count, 1, "expected 1 metric in otel_metrics");
}
