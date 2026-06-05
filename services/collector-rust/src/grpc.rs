//! OTLP gRPC server — Day 9.
//!
//! Implements the three OpenTelemetry collector services (Trace / Logs /
//! Metrics) on a single tonic server, conventionally bound to `:4317`.
//!
//! # Modes
//!
//! [`CollectorService`] operates in one of two modes, selected by the
//! `client` field:
//!
//! - **Log-only mode** (`client == None`): the Day-8 behaviour — count
//!   incoming signals, log them, and acknowledge with the empty success
//!   response. No ClickHouse dependency. Used by the smoke test.
//! - **Export mode** (`client == Some(clickhouse::Client)`): transform the
//!   OTLP request into [`crate::Signal`] values via [`crate::otlp`], then
//!   call [`crate::clickhouse_exporter::export`]. On success returns the
//!   full-success response; on `Err` logs the failure and returns
//!   `Status::internal`.
//!
//! The `clickhouse::Client` is Arc-backed internally (the `clickhouse` crate
//! documents that cloning a `Client` is cheap). The `CollectorService`
//! itself derives `Clone` so tonic can hand a copy to each new connection.
//!
//! # Proto types
//!
//! Proto types come from `opentelemetry-proto` 0.27 (`gen-tonic` feature).

use std::net::SocketAddr;

use tokio::net::TcpListener;
use tokio_stream::wrappers::TcpListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};
use tracing::{error, info, warn};

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

use crate::config::GrpcValidation;
use crate::{clickhouse_exporter, otlp, Signal};

/// The OTLP collector service.
///
/// `Clone` is derived so tonic can hand a copy to each connection.
/// `clickhouse::Client` is internally Arc-backed, making each clone O(1).
/// `None` selects log-only mode (no DB, Day-8 compat); `Some` selects export
/// mode.
#[derive(Clone)]
pub struct CollectorService {
    client: Option<clickhouse::Client>,
    validation: GrpcValidation,
}

impl CollectorService {
    /// Create a new `CollectorService`.
    ///
    /// Pass `None` for log-only mode (no ClickHouse dependency) or
    /// `Some(client)` for export mode. `validation` selects the contract
    /// enforcement policy applied to each signal before export (see
    /// [`GrpcValidation`]); it has no effect in log-only mode, where signals
    /// are never transformed or exported.
    pub fn new(client: Option<clickhouse::Client>, validation: GrpcValidation) -> Self {
        Self { client, validation }
    }
}

/// Apply the gRPC receive-boundary validation [`policy`](GrpcValidation) to a
/// batch of transformed signals.
///
/// Returns the signals to export alongside the number that **failed**
/// validation. The returned set depends on the policy:
///
/// - [`GrpcValidation::Off`] → every signal returned, reject count `0` (no
///   validation performed).
/// - [`GrpcValidation::Warn`] → every signal returned; each violation logged
///   and counted, but nothing is dropped.
/// - [`GrpcValidation::Strict`] → only conformant signals returned; each
///   invalid signal is logged, counted, and dropped.
///
/// `signal_kind` (`"trace"` / `"logs"` / `"metrics"`) is attached to the log
/// line so a reader can tell which stream produced the violation.
fn apply_validation(
    signals: Vec<Signal>,
    policy: GrpcValidation,
    signal_kind: &str,
) -> (Vec<Signal>, usize) {
    match policy {
        GrpcValidation::Off => (signals, 0),
        GrpcValidation::Warn => {
            let mut rejected = 0;
            for sig in &signals {
                if let Err(err) = sig.validate() {
                    rejected += 1;
                    warn!(
                        signal = signal_kind,
                        error = %err,
                        mode = "warn",
                        "contract validation failed — exporting anyway"
                    );
                }
            }
            (signals, rejected)
        }
        GrpcValidation::Strict => {
            let mut kept = Vec::with_capacity(signals.len());
            let mut rejected = 0;
            for sig in signals {
                match sig.validate() {
                    Ok(()) => kept.push(sig),
                    Err(err) => {
                        rejected += 1;
                        warn!(
                            signal = signal_kind,
                            error = %err,
                            mode = "strict",
                            "contract validation failed — dropping signal"
                        );
                    }
                }
            }
            (kept, rejected)
        }
    }
}

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

        match &self.client {
            None => {
                // Log-only mode: count, log, ack.
                info!(
                    signal = "trace",
                    resource_spans = req.resource_spans.len(),
                    spans,
                    mode = "log-only",
                    "OTLP export received"
                );
            }
            Some(client) => {
                let signals = otlp::trace_request_to_signals(req);
                let (signals, rejected) = apply_validation(signals, self.validation, "trace");
                let exported = signals.len();
                info!(
                    signal = "trace",
                    received = spans,
                    exported,
                    rejected,
                    "OTLP export → ClickHouse"
                );
                if !signals.is_empty() {
                    if let Err(err) = clickhouse_exporter::export(client, signals).await {
                        error!(error = %err, "ClickHouse export failed for traces");
                        return Err(Status::internal(format!("export failed: {err}")));
                    }
                }
            }
        }

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

        match &self.client {
            None => {
                info!(
                    signal = "logs",
                    resource_logs = req.resource_logs.len(),
                    logs,
                    mode = "log-only",
                    "OTLP export received"
                );
            }
            Some(client) => {
                let signals = otlp::logs_request_to_signals(req);
                let (signals, rejected) = apply_validation(signals, self.validation, "logs");
                let exported = signals.len();
                info!(
                    signal = "logs",
                    received = logs,
                    exported,
                    rejected,
                    "OTLP export → ClickHouse"
                );
                if !signals.is_empty() {
                    if let Err(err) = clickhouse_exporter::export(client, signals).await {
                        error!(error = %err, "ClickHouse export failed for logs");
                        return Err(Status::internal(format!("export failed: {err}")));
                    }
                }
            }
        }

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

        match &self.client {
            None => {
                info!(
                    signal = "metrics",
                    resource_metrics = req.resource_metrics.len(),
                    metrics,
                    mode = "log-only",
                    "OTLP export received"
                );
            }
            Some(client) => {
                let (signals, skipped) = otlp::metrics_request_to_signals(req);
                let (signals, rejected) = apply_validation(signals, self.validation, "metrics");
                let exported = signals.len();
                info!(
                    signal = "metrics",
                    received = metrics,
                    exported,
                    rejected,
                    skipped_unsupported_types = skipped,
                    "OTLP export → ClickHouse"
                );
                if skipped > 0 {
                    info!(
                        skipped,
                        "Histogram/ExponentialHistogram/Summary metrics skipped \
                         (no Signal representation in contract v1.0.0)"
                    );
                }
                if !signals.is_empty() {
                    if let Err(err) = clickhouse_exporter::export(client, signals).await {
                        error!(error = %err, "ClickHouse export failed for metrics");
                        return Err(Status::internal(format!("export failed: {err}")));
                    }
                }
            }
        }

        Ok(Response::new(ExportMetricsServiceResponse::default()))
    }
}

/// Register all three OTLP services onto a fresh tonic server builder.
fn builder() -> Server {
    Server::builder()
}

/// Serve OTLP on `addr` until `shutdown` resolves (e.g. Ctrl-C).
///
/// Pass `client = None` for log-only mode (no ClickHouse dependency) or
/// `client = Some(client)` for export mode. `validation` selects the
/// contract-enforcement policy applied to each signal before export (see
/// [`GrpcValidation`]).
///
/// # Errors
///
/// Returns a [`tonic::transport::Error`] if the address cannot be bound or
/// the server terminates abnormally.
pub async fn serve(
    addr: SocketAddr,
    shutdown: impl std::future::Future<Output = ()>,
    client: Option<clickhouse::Client>,
    validation: GrpcValidation,
) -> Result<(), tonic::transport::Error> {
    let svc = CollectorService::new(client, validation);
    info!(
        %addr,
        mode = if svc.client.is_some() { "export" } else { "log-only" },
        validation = ?validation,
        "OTLP gRPC server listening"
    );
    builder()
        .add_service(TraceServiceServer::new(svc.clone()))
        .add_service(LogsServiceServer::new(svc.clone()))
        .add_service(MetricsServiceServer::new(svc))
        .serve_with_shutdown(addr, shutdown)
        .await
}

/// Serve OTLP on an already-bound [`TcpListener`] until `shutdown` resolves.
///
/// Used by the smoke test and integration tests to bind an ephemeral port
/// (`127.0.0.1:0`) without a bind race. Pass `client = None` for log-only
/// mode or `client = Some(client)` for export mode. `validation` selects the
/// contract-enforcement policy (see [`GrpcValidation`]).
///
/// # Errors
///
/// Returns a [`tonic::transport::Error`] if the server terminates abnormally.
pub async fn serve_with_listener(
    listener: TcpListener,
    shutdown: impl std::future::Future<Output = ()>,
    client: Option<clickhouse::Client>,
    validation: GrpcValidation,
) -> Result<(), tonic::transport::Error> {
    let svc = CollectorService::new(client, validation);
    builder()
        .add_service(TraceServiceServer::new(svc.clone()))
        .add_service(LogsServiceServer::new(svc.clone()))
        .add_service(MetricsServiceServer::new(svc))
        .serve_with_incoming_shutdown(TcpListenerStream::new(listener), shutdown)
        .await
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::collections::HashMap;

    use super::*;
    use crate::contract::{LogSignal, REQUIRED_RESOURCE_KEYS};

    /// A `LogSignal` that passes `validate()` — full required resource keys.
    fn valid_log() -> Signal {
        let mut resource = HashMap::new();
        for k in REQUIRED_RESOURCE_KEYS {
            resource.insert((*k).to_string(), "x".to_string());
        }
        Signal::Log(LogSignal {
            contract_version: crate::CONTRACT_VERSION.to_string(),
            time_unix_nano: 1,
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "svc".to_string(),
            body: "b".to_string(),
            trace_id: None,
            span_id: None,
            attributes: HashMap::new(),
            resource_attributes: resource,
        })
    }

    /// A `LogSignal` that fails `validate()` — this is what the gRPC transform
    /// produces for foreign OTLP that lacks the `sentinel.*` resource keys.
    fn invalid_log() -> Signal {
        Signal::Log(LogSignal {
            contract_version: crate::CONTRACT_VERSION.to_string(),
            time_unix_nano: 1,
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "svc".to_string(),
            body: "b".to_string(),
            trace_id: None,
            span_id: None,
            attributes: HashMap::new(),
            resource_attributes: HashMap::new(), // missing all required keys
        })
    }

    #[test]
    fn off_keeps_everything_and_reports_zero_rejects() {
        let (kept, rejected) = apply_validation(
            vec![valid_log(), invalid_log()],
            GrpcValidation::Off,
            "logs",
        );
        assert_eq!(kept.len(), 2, "Off must not drop anything");
        assert_eq!(
            rejected, 0,
            "Off must not count rejects (no validation run)"
        );
    }

    #[test]
    fn warn_keeps_everything_but_counts_rejects() {
        let (kept, rejected) = apply_validation(
            vec![valid_log(), invalid_log()],
            GrpcValidation::Warn,
            "logs",
        );
        assert_eq!(kept.len(), 2, "Warn exports even invalid signals");
        assert_eq!(rejected, 1, "Warn counts the one invalid signal");
    }

    #[test]
    fn strict_drops_invalid_and_keeps_valid() {
        let (kept, rejected) = apply_validation(
            vec![valid_log(), invalid_log(), valid_log()],
            GrpcValidation::Strict,
            "logs",
        );
        assert_eq!(kept.len(), 2, "Strict drops the invalid signal");
        assert_eq!(rejected, 1, "Strict counts the dropped signal");
        // The two survivors are the valid ones.
        for sig in &kept {
            assert!(sig.validate().is_ok(), "only conformant signals survive");
        }
    }

    #[test]
    fn empty_batch_is_handled() {
        for policy in [
            GrpcValidation::Off,
            GrpcValidation::Warn,
            GrpcValidation::Strict,
        ] {
            let (kept, rejected) = apply_validation(Vec::new(), policy, "logs");
            assert!(kept.is_empty());
            assert_eq!(rejected, 0);
        }
    }
}
