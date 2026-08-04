//! OTLP gRPC server — Day 9.
//!
//! Implements the three OpenTelemetry collector services (Trace / Logs /
//! Metrics) on a single tonic server, conventionally bound to `:4317`.
//!
//! # Modes
//!
//! [`CollectorService`] operates in one of two modes, selected by the
//! `buffer` field:
//!
//! - **Log-only mode** (`buffer == None`): the Day-8 behaviour — count
//!   incoming signals, log them, and acknowledge with the empty success
//!   response. No ClickHouse dependency. Used by the smoke test.
//! - **Export mode** (`buffer == Some(buffer::BufferedExporter)`): transform
//!   the OTLP request into [`crate::Signal`] values via [`crate::otlp`], then
//!   **enqueue** them into the buffered exporter (EP2.2) — see the
//!   "Ack semantics" section below. The actual [`clickhouse_exporter::export`]
//!   call happens later, in the buffer's background flush task, not inline
//!   in this handler.
//!
//! # Ack semantics (EP2.2 — read before touching error handling here)
//!
//! Buffering **decouples** the gRPC ack from the ClickHouse INSERT result
//! (see `crate::buffer` module docs, ADR-0011). This handler:
//!
//! - Returns `Status::resource_exhausted` if the buffer is saturated
//!   (ClickHouse cannot drain fast enough) — the "reject for health" gesture
//!   EP3.1 is expected to formalize into a full backpressure/shed policy.
//! - Returns the full-success response as soon as the batch is
//!   **enqueued**, not once it is durably written. Flush failures are
//!   retried and logged in the background; they no longer fail the RPC that
//!   produced the batch (see `crate::buffer`).
//!
//! The `clickhouse::Client` inside `BufferedExporter`'s background task is
//! Arc-backed internally (the `clickhouse` crate documents that cloning a
//! `Client` is cheap); `BufferedExporter` itself wraps a cheap-to-clone
//! `mpsc::Sender`. The `CollectorService` derives `Clone` so tonic can hand a
//! copy to each new connection.
//!
//! # Proto types
//!
//! Proto types come from `opentelemetry-proto` 0.27 (`gen-tonic` feature).

use std::net::SocketAddr;
use std::sync::Arc;

use tokio::net::TcpListener;
use tokio_stream::wrappers::TcpListenerStream;
use tonic::transport::Server;
use tonic::{Request, Response, Status};
use tracing::{debug, error, info, warn};

use opentelemetry_proto::tonic::collector::logs::v1::{
    logs_service_server::{LogsService, LogsServiceServer},
    ExportLogsPartialSuccess, ExportLogsServiceRequest, ExportLogsServiceResponse,
};
use opentelemetry_proto::tonic::collector::metrics::v1::{
    metrics_service_server::{MetricsService, MetricsServiceServer},
    ExportMetricsPartialSuccess, ExportMetricsServiceRequest, ExportMetricsServiceResponse,
};
use opentelemetry_proto::tonic::collector::trace::v1::{
    trace_service_server::{TraceService, TraceServiceServer},
    ExportTracePartialSuccess, ExportTraceServiceRequest, ExportTraceServiceResponse,
};

use crate::buffer::{BufferConfig, BufferedExporter};
use crate::config::GrpcValidation;
use crate::metrics::Metrics;
use crate::{otlp, Signal};

/// The OTLP collector service.
///
/// `Clone` is derived so tonic can hand a copy to each connection —
/// [`BufferedExporter`] is itself cheap to clone (an `mpsc::Sender`). `None`
/// selects log-only mode (no DB, Day-8 compat); `Some` selects export mode
/// (EP2.2 buffered).
#[derive(Clone)]
pub struct CollectorService {
    buffer: Option<BufferedExporter>,
    validation: GrpcValidation,
    /// `sentinel_signals_ingested_total{signal}` — EP3.2. Shared across
    /// every `CollectorService` clone (one per tonic connection) and with
    /// `crate::metrics_server`'s `/metrics` endpoint.
    metrics: Arc<Metrics>,
}

impl CollectorService {
    /// Create a new `CollectorService`.
    ///
    /// Pass `None` for log-only mode (no ClickHouse dependency) or
    /// `Some(buffer)` for export mode. `validation` selects the contract
    /// enforcement policy applied to each signal before export (see
    /// [`GrpcValidation`]); it has no effect in log-only mode, where signals
    /// are never transformed or exported. `metrics` is the shared EP3.2
    /// registry — every `Export` call increments `signals_ingested_total`
    /// on it regardless of mode.
    pub fn new(
        buffer: Option<BufferedExporter>,
        validation: GrpcValidation,
        metrics: Arc<Metrics>,
    ) -> Self {
        Self {
            buffer,
            validation,
            metrics,
        }
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

        self.metrics
            .signals_ingested_total
            .with_label_values(&["trace"])
            .inc_by(u64::try_from(spans).unwrap_or(u64::MAX));

        let mut rejected_count = 0usize;
        match &self.buffer {
            None => {
                // Log-only mode: count, log, ack.
                debug!(
                    signal = "trace",
                    resource_spans = req.resource_spans.len(),
                    spans,
                    mode = "log-only",
                    "OTLP export received"
                );
            }
            Some(buffer) => {
                let signals = otlp::trace_request_to_signals(req);
                let (signals, rejected) = apply_validation(signals, self.validation, "trace");
                rejected_count = rejected;
                let exported = signals.len();
                self.metrics
                    .signals_rejected_total
                    .with_label_values(&["trace", "contract"])
                    .inc_by(u64::try_from(rejected).unwrap_or(u64::MAX));
                debug!(
                    signal = "trace",
                    received = spans,
                    exported,
                    rejected,
                    "OTLP export → buffer"
                );
                if let Err(err) = buffer.enqueue(signals) {
                    self.metrics
                        .signals_rejected_total
                        .with_label_values(&["trace", "backpressure"])
                        .inc_by(u64::try_from(exported).unwrap_or(u64::MAX));
                    warn!(error = %err, signal = "trace", "buffer saturated — rejecting export");
                    return Err(Status::resource_exhausted(format!(
                        "collector buffer saturated: {err}"
                    )));
                }
                self.metrics
                    .signals_accepted_total
                    .with_label_values(&["trace"])
                    .inc_by(u64::try_from(exported).unwrap_or(u64::MAX));
            }
        }

        let partial_success = (self.validation == GrpcValidation::Strict && rejected_count > 0)
            .then(|| ExportTracePartialSuccess {
                rejected_spans: i64::try_from(rejected_count).unwrap_or(i64::MAX),
                error_message: "signals rejected by strict contract validation".to_string(),
            });
        Ok(Response::new(ExportTraceServiceResponse {
            partial_success,
        }))
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

        self.metrics
            .signals_ingested_total
            .with_label_values(&["logs"])
            .inc_by(u64::try_from(logs).unwrap_or(u64::MAX));

        let mut rejected_count = 0usize;
        match &self.buffer {
            None => {
                debug!(
                    signal = "logs",
                    resource_logs = req.resource_logs.len(),
                    logs,
                    mode = "log-only",
                    "OTLP export received"
                );
            }
            Some(buffer) => {
                let signals = otlp::logs_request_to_signals(req);
                let (signals, rejected) = apply_validation(signals, self.validation, "logs");
                rejected_count = rejected;
                let exported = signals.len();
                self.metrics
                    .signals_rejected_total
                    .with_label_values(&["logs", "contract"])
                    .inc_by(u64::try_from(rejected).unwrap_or(u64::MAX));
                debug!(
                    signal = "logs",
                    received = logs,
                    exported,
                    rejected,
                    "OTLP export → buffer"
                );
                if let Err(err) = buffer.enqueue(signals) {
                    self.metrics
                        .signals_rejected_total
                        .with_label_values(&["logs", "backpressure"])
                        .inc_by(u64::try_from(exported).unwrap_or(u64::MAX));
                    warn!(error = %err, signal = "logs", "buffer saturated — rejecting export");
                    return Err(Status::resource_exhausted(format!(
                        "collector buffer saturated: {err}"
                    )));
                }
                self.metrics
                    .signals_accepted_total
                    .with_label_values(&["logs"])
                    .inc_by(u64::try_from(exported).unwrap_or(u64::MAX));
            }
        }

        let partial_success = (self.validation == GrpcValidation::Strict && rejected_count > 0)
            .then(|| ExportLogsPartialSuccess {
                rejected_log_records: i64::try_from(rejected_count).unwrap_or(i64::MAX),
                error_message: "signals rejected by strict contract validation".to_string(),
            });
        Ok(Response::new(ExportLogsServiceResponse { partial_success }))
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

        self.metrics
            .signals_ingested_total
            .with_label_values(&["metrics"])
            .inc_by(u64::try_from(metrics).unwrap_or(u64::MAX));

        let mut rejected_count = 0usize;
        match &self.buffer {
            None => {
                debug!(
                    signal = "metrics",
                    resource_metrics = req.resource_metrics.len(),
                    metrics,
                    mode = "log-only",
                    "OTLP export received"
                );
            }
            Some(buffer) => {
                let (signals, skipped) = otlp::metrics_request_to_signals(req);
                let (signals, rejected) = apply_validation(signals, self.validation, "metrics");
                rejected_count = rejected;
                let exported = signals.len();
                self.metrics
                    .signals_rejected_total
                    .with_label_values(&["metrics", "contract"])
                    .inc_by(u64::try_from(rejected).unwrap_or(u64::MAX));
                debug!(
                    signal = "metrics",
                    received = metrics,
                    exported,
                    rejected,
                    skipped_unsupported_types = skipped,
                    "OTLP export → buffer"
                );
                if skipped > 0 {
                    info!(
                        skipped,
                        "Histogram/ExponentialHistogram/Summary metrics skipped \
                         (no Signal representation in contract v1.0.0)"
                    );
                }
                if let Err(err) = buffer.enqueue(signals) {
                    self.metrics
                        .signals_rejected_total
                        .with_label_values(&["metrics", "backpressure"])
                        .inc_by(u64::try_from(exported).unwrap_or(u64::MAX));
                    warn!(error = %err, signal = "metrics", "buffer saturated — rejecting export");
                    return Err(Status::resource_exhausted(format!(
                        "collector buffer saturated: {err}"
                    )));
                }
                self.metrics
                    .signals_accepted_total
                    .with_label_values(&["metrics"])
                    .inc_by(u64::try_from(exported).unwrap_or(u64::MAX));
            }
        }

        let partial_success = (self.validation == GrpcValidation::Strict && rejected_count > 0)
            .then(|| ExportMetricsPartialSuccess {
                rejected_data_points: i64::try_from(rejected_count).unwrap_or(i64::MAX),
                error_message: "signals rejected by strict contract validation".to_string(),
            });
        Ok(Response::new(ExportMetricsServiceResponse {
            partial_success,
        }))
    }
}

/// Register all three OTLP services onto a fresh tonic server builder.
fn builder() -> Server {
    Server::builder()
}

/// Build the [`CollectorService`] plus, in export mode, the
/// [`BufferedExporter`] handle and its background flush task's
/// [`tokio::task::JoinHandle`].
///
/// `client = None` selects log-only mode: no buffer is spawned, and the
/// returned `Option`s are both `None`. `client = Some(client)` spawns the
/// EP2.2 buffered exporter (see `crate::buffer`) using `buffer_config`.
///
/// The caller retains the returned `BufferedExporter` (a Sender clone
/// distinct from the ones handed to the tonic-managed `svc.clone()`s) and
/// `JoinHandle` specifically so it can drive graceful shutdown: drop the
/// handle to close the channel, then await the task to guarantee the buffer
/// drains before the process exits — see [`drain_on_shutdown`].
fn build_service(
    client: Option<clickhouse::Client>,
    validation: GrpcValidation,
    buffer_config: BufferConfig,
    metrics: Arc<Metrics>,
) -> (
    CollectorService,
    Option<BufferedExporter>,
    Option<tokio::task::JoinHandle<()>>,
) {
    match client {
        Some(client) => {
            let (buffer, task) =
                BufferedExporter::spawn(client, buffer_config, Arc::clone(&metrics));
            let svc = CollectorService::new(Some(buffer.clone()), validation, metrics);
            (svc, Some(buffer), Some(task))
        }
        None => (CollectorService::new(None, validation, metrics), None, None),
    }
}

/// Drop the caller's [`BufferedExporter`] handle (the last `mpsc::Sender`
/// clone once tonic has torn down its own copies after `.await` completes)
/// and await the flush task, guaranteeing every enqueued signal is flushed
/// — or exhausts its retries and is logged — before the server future
/// resolves.
///
/// A no-op in log-only mode (`buffer`/`task` both `None`).
async fn drain_on_shutdown(
    buffer: Option<BufferedExporter>,
    task: Option<tokio::task::JoinHandle<()>>,
) {
    drop(buffer);
    if let Some(task) = task {
        if let Err(err) = task.await {
            error!(error = %err, "buffer flush task panicked during shutdown drain");
        }
    }
}

/// Serve OTLP on `addr` until `shutdown` resolves (e.g. Ctrl-C).
///
/// Pass `client = None` for log-only mode (no ClickHouse dependency) or
/// `client = Some(client)` for export mode, in which case the EP2.2
/// [`BufferedExporter`] is spawned with `buffer_config` (see `crate::buffer`
/// module docs for the batching + ack-semantics tradeoffs). `validation`
/// selects the contract-enforcement policy applied to each signal before
/// export (see [`GrpcValidation`]). `metrics` is the shared EP3.2 Prometheus
/// registry (see `crate::metrics`) — the returned [`CollectorService`] and
/// its [`BufferedExporter`] both record onto it; pass the same `Arc` you
/// hand to `crate::metrics_server::serve` so `/metrics` reflects this
/// server's activity.
///
/// On shutdown, the buffer is drained before this function returns — see
/// [`drain_on_shutdown`].
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
    buffer_config: BufferConfig,
    metrics: Arc<Metrics>,
) -> Result<(), tonic::transport::Error> {
    let (svc, buffer, task) = build_service(client, validation, buffer_config, metrics);
    info!(
        %addr,
        mode = if buffer.is_some() { "export" } else { "log-only" },
        validation = ?validation,
        "OTLP gRPC server listening"
    );
    let result = builder()
        .add_service(TraceServiceServer::new(svc.clone()))
        .add_service(LogsServiceServer::new(svc.clone()))
        .add_service(MetricsServiceServer::new(svc))
        .serve_with_shutdown(addr, shutdown)
        .await;

    drain_on_shutdown(buffer, task).await;
    result
}

/// Serve OTLP on an already-bound [`TcpListener`] until `shutdown` resolves.
///
/// Used by the smoke test and integration tests to bind an ephemeral port
/// (`127.0.0.1:0`) without a bind race. Pass `client = None` for log-only
/// mode or `client = Some(client)` for export mode (spawns the EP2.2
/// [`BufferedExporter`] with `buffer_config`). `validation` selects the
/// contract-enforcement policy (see [`GrpcValidation`]).
///
/// On shutdown, the buffer is drained before this function returns — see
/// [`drain_on_shutdown`].
///
/// # Errors
///
/// Returns a [`tonic::transport::Error`] if the server terminates abnormally.
pub async fn serve_with_listener(
    listener: TcpListener,
    shutdown: impl std::future::Future<Output = ()>,
    client: Option<clickhouse::Client>,
    validation: GrpcValidation,
    buffer_config: BufferConfig,
    metrics: Arc<Metrics>,
) -> Result<(), tonic::transport::Error> {
    let (svc, buffer, task) = build_service(client, validation, buffer_config, metrics);
    let result = builder()
        .add_service(TraceServiceServer::new(svc.clone()))
        .add_service(LogsServiceServer::new(svc.clone()))
        .add_service(MetricsServiceServer::new(svc))
        .serve_with_incoming_shutdown(TcpListenerStream::new(listener), shutdown)
        .await;

    drain_on_shutdown(buffer, task).await;
    result
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
