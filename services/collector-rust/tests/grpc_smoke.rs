//! OTLP gRPC server smoke test — the `grpcurl smoke test` from the Day-8 plan,
//! but self-contained (no external tools): it binds the real server on an
//! ephemeral port and drives it with the generated tonic client.
//!
//! Not `#[ignore]`d — it needs no Docker or external service, so it runs as part
//! of the normal `cargo test` gate.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::time::Duration;

use tokio::net::TcpListener;
use tokio::sync::oneshot;

use opentelemetry_proto::tonic::collector::logs::v1::{
    logs_service_client::LogsServiceClient, ExportLogsServiceRequest,
};
use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_client::TraceServiceClient, ExportTraceServiceRequest,
};
use opentelemetry_proto::tonic::logs::v1::{LogRecord, ResourceLogs, ScopeLogs};
use opentelemetry_proto::tonic::trace::v1::{ResourceSpans, ScopeSpans, Span};

/// Start the server on `127.0.0.1:0`, returning its address and a shutdown
/// handle. Binding the listener *before* spawning avoids a connect race.
async fn start_server() -> (
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
        let metrics = sentinel_collector::metrics::Metrics::new_shared()
            .expect("metrics registry registers cleanly");
        sentinel_collector::grpc::serve_with_listener(
            listener,
            shutdown,
            None,
            sentinel_collector::config::GrpcValidation::Off,
            sentinel_collector::buffer::BufferConfig::default(),
            metrics,
        )
        .await
        .expect("server runs cleanly");
    });
    // The listener is already bound, but give the task a tick to enter serve().
    tokio::time::sleep(Duration::from_millis(50)).await;
    (addr, tx, handle)
}

#[tokio::test]
async fn server_accepts_trace_export() {
    let (addr, shutdown, handle) = start_server().await;

    let mut client = TraceServiceClient::connect(format!("http://{addr}"))
        .await
        .expect("client connects to the bound server");

    let request = ExportTraceServiceRequest {
        resource_spans: vec![ResourceSpans {
            resource: None,
            scope_spans: vec![ScopeSpans {
                scope: None,
                spans: vec![Span::default(), Span::default()],
                schema_url: String::new(),
            }],
            schema_url: String::new(),
        }],
    };

    let response = client.export(request).await.expect("export call succeeds");
    // OTLP full-success response carries no partial_success error block.
    assert!(
        response.into_inner().partial_success.is_none(),
        "a clean export must report full success"
    );

    let _ = shutdown.send(());
    handle.await.unwrap();
}

#[tokio::test]
async fn server_accepts_logs_export() {
    let (addr, shutdown, handle) = start_server().await;

    let mut client = LogsServiceClient::connect(format!("http://{addr}"))
        .await
        .expect("client connects");

    let request = ExportLogsServiceRequest {
        resource_logs: vec![ResourceLogs {
            resource: None,
            scope_logs: vec![ScopeLogs {
                scope: None,
                log_records: vec![LogRecord::default()],
                schema_url: String::new(),
            }],
            schema_url: String::new(),
        }],
    };

    let response = client.export(request).await.expect("export call succeeds");
    assert!(response.into_inner().partial_success.is_none());

    let _ = shutdown.send(());
    handle.await.unwrap();
}
