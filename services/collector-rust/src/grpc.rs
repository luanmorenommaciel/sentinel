//! OTLP gRPC server (Day 8 — skeleton).
//!
//! Implements the three OpenTelemetry collector services (Trace / Logs /
//! Metrics) on a single tonic server, conventionally bound to `:4317`. All
//! three share one [`CollectorService`] and one H2 connection pool.
//!
//! **Day 8 scope:** accept an `Export*ServiceRequest`, log what arrived, and
//! acknowledge with the empty success response. **Day 9** will wire the
//! handlers into the ClickHouse exporter (the service will then hold an
//! `Arc<clickhouse::Client>` and translate OTLP proto → [`crate::Signal`] →
//! `INSERT`).
//!
//! The proto types come from the `opentelemetry-proto` crate's `gen-tonic`
//! feature (already enabled in `Cargo.toml`).

use std::net::SocketAddr;

use tokio::net::TcpListener;
use tokio_stream::wrappers::TcpListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};
use tracing::info;

use opentelemetry_proto::tonic::collector::logs::v1::{
    logs_service_server::{LogsService, LogsServiceServer},
    ExportLogsServiceRequest, ExportLogsServiceResponse,
};
use opentelemetry_proto::tonic::collector::metrics::v1::{
    metrics_service_server::{MetricsService, MetricsServiceServer},
    ExportMetricsServiceRequest, ExportMetricsServiceResponse,
};
use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_server::{TraceService, TraceServiceServer},
    ExportTraceServiceRequest, ExportTraceServiceResponse,
};

/// The OTLP collector service.
///
/// Day 8: stateless — each handler logs receipt and acknowledges. The `Clone`
/// derive lets tonic hand a copy to each connection (Day 9's `Arc` state will
/// clone cheaply).
#[derive(Clone, Default)]
pub struct CollectorService;

#[tonic::async_trait]
impl TraceService for CollectorService {
    async fn export(
        &self,
        request: Request<ExportTraceServiceRequest>,
    ) -> Result<Response<ExportTraceServiceResponse>, Status> {
        let req = request.into_inner();
        let spans: usize = req
            .resource_spans
            .iter()
            .flat_map(|rs| rs.scope_spans.iter())
            .map(|ss| ss.spans.len())
            .sum();
        info!(
            signal = "trace",
            resource_spans = req.resource_spans.len(),
            spans,
            "OTLP export received"
        );
        Ok(Response::new(ExportTraceServiceResponse::default()))
    }
}

#[tonic::async_trait]
impl LogsService for CollectorService {
    async fn export(
        &self,
        request: Request<ExportLogsServiceRequest>,
    ) -> Result<Response<ExportLogsServiceResponse>, Status> {
        let req = request.into_inner();
        let logs: usize = req
            .resource_logs
            .iter()
            .flat_map(|rl| rl.scope_logs.iter())
            .map(|sl| sl.log_records.len())
            .sum();
        info!(
            signal = "logs",
            resource_logs = req.resource_logs.len(),
            logs,
            "OTLP export received"
        );
        Ok(Response::new(ExportLogsServiceResponse::default()))
    }
}

#[tonic::async_trait]
impl MetricsService for CollectorService {
    async fn export(
        &self,
        request: Request<ExportMetricsServiceRequest>,
    ) -> Result<Response<ExportMetricsServiceResponse>, Status> {
        let req = request.into_inner();
        let metrics: usize = req
            .resource_metrics
            .iter()
            .flat_map(|rm| rm.scope_metrics.iter())
            .map(|sm| sm.metrics.len())
            .sum();
        info!(
            signal = "metrics",
            resource_metrics = req.resource_metrics.len(),
            metrics,
            "OTLP export received"
        );
        Ok(Response::new(ExportMetricsServiceResponse::default()))
    }
}

/// Register all three OTLP services onto a fresh tonic server builder.
fn builder() -> Server {
    Server::builder()
}

/// Serve OTLP on `addr` until `shutdown` resolves (e.g. Ctrl-C).
///
/// # Errors
///
/// Returns a [`tonic::transport::Error`] if the address cannot be bound or the
/// server terminates abnormally.
pub async fn serve(
    addr: SocketAddr,
    shutdown: impl std::future::Future<Output = ()>,
) -> Result<(), tonic::transport::Error> {
    let svc = CollectorService;
    info!(%addr, "OTLP gRPC server listening");
    builder()
        .add_service(TraceServiceServer::new(svc.clone()))
        .add_service(LogsServiceServer::new(svc.clone()))
        .add_service(MetricsServiceServer::new(svc))
        .serve_with_shutdown(addr, shutdown)
        .await
}

/// Serve OTLP on an already-bound [`TcpListener`] until `shutdown` resolves.
///
/// Used by the smoke test to bind an ephemeral port (`127.0.0.1:0`) without a
/// bind race.
///
/// # Errors
///
/// Returns a [`tonic::transport::Error`] if the server terminates abnormally.
pub async fn serve_with_listener(
    listener: TcpListener,
    shutdown: impl std::future::Future<Output = ()>,
) -> Result<(), tonic::transport::Error> {
    let svc = CollectorService;
    builder()
        .add_service(TraceServiceServer::new(svc.clone()))
        .add_service(LogsServiceServer::new(svc.clone()))
        .add_service(MetricsServiceServer::new(svc))
        .serve_with_incoming_shutdown(TcpListenerStream::new(listener), shutdown)
        .await
}
