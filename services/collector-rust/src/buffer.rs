//! Buffered ClickHouse exporter — EP2.2 (performance equalization).
//!
//! # Problem
//!
//! Before this module existed, every OTLP gRPC `Export` call turned into an
//! immediate [`crate::clickhouse_exporter::export`] call: **1 Export RPC = 1
//! INSERT = 1 ClickHouse part**. Under streaming OTLP load this produces many
//! small parts, background-merge pressure, and eventually OOM (see
//! `ANALISE.md`). The Go collector does not suffer from this because
//! `internal/chstore/store.go` sits a buffering layer between the receiver
//! and the writer (`flushLoop`, batched by size OR time).
//!
//! This module mirrors that shape for Rust: gRPC handlers enqueue
//! [`crate::Signal`]s into a bounded channel; a single background task
//! accumulates them and calls [`crate::clickhouse_exporter::export`] once per
//! `batch_size` OR `flush_interval`, whichever comes first — collapsing many
//! small Export RPCs into few, large, part-efficient INSERTs.
//!
//! # Ack/export decoupling (ADR-0011 · see also EP3.1)
//!
//! Buffering **breaks the pre-EP2.2 coupling** between the gRPC ack and the
//! ClickHouse INSERT result. Before this change, a `Export` RPC only
//! succeeded once the row was durably written; now the RPC succeeds once the
//! row is durably *enqueued*. Concretely:
//!
//! - **Enqueue rejected** (buffer saturated — ClickHouse cannot drain fast
//!   enough): the RPC fails fast with [`tonic::Status::resource_exhausted`].
//!   This *is* the "reject for health" behaviour EP3.1 is expected to
//!   formalize (backpressure/shed policy); this module only implements the
//!   simplest form of it (hard reject on a full channel).
//! - **Enqueue accepted, flush fails**: the RPC has already returned success
//!   to the caller. Flush failures are retried in the background (bounded
//!   retry with jittered backoff) and, if still failing, logged via
//!   `tracing::error!` and counted (see [`BufferedExporter::flush_failures`],
//!   a hook for the EP3.2 Prometheus exporter) — the batch is then dropped.
//!
//! Per-row error-to-ack fidelity is intentionally **not** preserved. A caller
//! that needs delivery guarantees stronger than "accepted for buffered,
//! best-effort, retried delivery" is out of scope for this module.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use thiserror::Error;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tokio::time::{interval, MissedTickBehavior};
use tracing::{debug, error, warn};

use crate::clickhouse_exporter;
use crate::metrics::Metrics;
use crate::Signal;

/// Label value used for `sentinel_batch_flush_total`/`batch_flush_size`
/// (EP3.2). The buffer merges every [`Signal`] variant into one combined
/// channel and flushes one mixed batch per cycle — there is no per-signal
/// flush boundary to label with, unlike the Go collector's per-channel
/// `flushLoop`. See `crate::metrics` module docs for the full parity table.
const FLUSH_SIGNAL_LABEL: &str = "all";

/// Number of flush attempts per batch before it is logged and dropped.
///
/// Matches the Go collector's `flushLoop` retry count
/// (`services/collector-go/internal/chstore/store.go`).
const MAX_FLUSH_ATTEMPTS: u32 = 3;

/// Base backoff delay for flush retry attempt 1 (doubles each attempt,
/// matching the Go collector's `100ms * 2^attempt` schedule).
const BASE_BACKOFF_MS: u64 = 100;

/// Buffer tunables. Frozen bake-off cell (ADR-0009/0010/0011, `.env.bakeoff`
/// `BATCH_SIZE` / `FLUSH_INTERVAL_MS`): `batch_size = 1000`,
/// `flush_interval = 500ms`. The defaults here match that cell so an
/// unconfigured collector still behaves identically to the bake-off.
#[derive(Debug, Clone, Copy)]
pub struct BufferConfig {
    /// Signals accumulated before a flush is forced.
    pub batch_size: usize,
    /// Maximum time a partial batch waits before being flushed anyway.
    pub flush_interval: Duration,
}

impl Default for BufferConfig {
    fn default() -> Self {
        Self {
            batch_size: 1000,
            flush_interval: Duration::from_millis(500),
        }
    }
}

/// Error returned when the buffer cannot accept a batch right now.
///
/// The gRPC handler maps this to [`tonic::Status::resource_exhausted`] — see
/// the module docs' "Ack/export decoupling" section.
#[derive(Debug, Error)]
pub enum EnqueueError {
    /// The channel does not have capacity for the whole batch. ClickHouse is
    /// not draining fast enough relative to the incoming rate.
    #[error(
        "buffer saturated: {pending} pending signal(s) exceed available channel capacity {available}"
    )]
    Saturated { pending: usize, available: usize },
}

/// Handle for enqueuing signals into the background flush loop.
///
/// Cheap to clone — wraps a [`tokio::sync::mpsc::Sender`] plus a shared
/// failure counter, mirroring the `clickhouse::Client` clone story so
/// [`crate::grpc::CollectorService`] can keep deriving `Clone`.
#[derive(Clone)]
pub struct BufferedExporter {
    tx: mpsc::Sender<Vec<Signal>>,
    flush_failures: Arc<AtomicUsize>,
}

impl BufferedExporter {
    /// Spawn the background flush task and return a handle to enqueue
    /// signals, plus the task's [`JoinHandle`].
    ///
    /// The channel stores 64 indivisible OTLP request envelopes, approximating
    /// Go's aggregate burst headroom for the controlled 500-signal producer
    /// batches while bounding memory.
    ///
    /// The caller (`grpc::serve`) is responsible for graceful shutdown: drop
    /// every clone of the returned [`BufferedExporter`] and then `.await`
    /// the [`JoinHandle`] to guarantee the buffer drains before the process
    /// exits.
    #[must_use]
    pub fn spawn(
        client: clickhouse::Client,
        config: BufferConfig,
        metrics: Arc<Metrics>,
    ) -> (Self, JoinHandle<()>) {
        // One channel item is one indivisible OTLP RPC. The generator's fixed
        // 500-signal outer batches yield roughly 150–300 rows per signal RPC;
        // 64 envelopes therefore approximate Go's 12,000-signal aggregate
        // headroom while preserving all-or-nothing enqueue.
        let capacity = 64;
        let (tx, rx) = mpsc::channel(capacity);
        let flush_failures = Arc::new(AtomicUsize::new(0));
        let task = tokio::spawn(flush_loop(
            client,
            rx,
            config,
            Arc::clone(&flush_failures),
            metrics,
        ));
        (Self { tx, flush_failures }, task)
    }

    /// Enqueue every signal produced by a single OTLP `Export` RPC.
    ///
    /// A no-op (returns `Ok`) for an empty batch. Otherwise, the entire vector
    /// is one channel item: `try_send` either accepts all signals or accepts
    /// none, even when producers race for the final slot.
    ///
    /// # Errors
    ///
    /// Returns [`EnqueueError::Saturated`] if the buffer does not have
    /// capacity for the batch. The caller (the gRPC handler) should map this
    /// to `Status::resource_exhausted` — see the module docs.
    pub fn enqueue(&self, signals: Vec<Signal>) -> Result<(), EnqueueError> {
        if signals.is_empty() {
            return Ok(());
        }
        let available = self.tx.capacity();
        if available == 0 {
            return Err(EnqueueError::Saturated {
                pending: signals.len(),
                available,
            });
        }
        self.tx
            .try_send(signals)
            .map_err(|err| EnqueueError::Saturated {
                pending: err.into_inner().len(),
                available: 0,
            })
    }

    /// Number of batches that exhausted [`MAX_FLUSH_ATTEMPTS`] retries and
    /// were dropped. A hook for the EP3.2 Prometheus exporter — currently
    /// only readable in-process (e.g. from a future `/metrics` handler or a
    /// test assertion).
    pub fn flush_failures(&self) -> usize {
        self.flush_failures.load(Ordering::Relaxed)
    }

    /// Test-only constructor: build a `BufferedExporter` wrapping a
    /// caller-supplied channel, without spawning the real flush task (which
    /// requires a live ClickHouse connection). Used to unit-test
    /// [`enqueue`](Self::enqueue)'s capacity/backpressure behaviour in
    /// isolation.
    #[cfg(test)]
    fn for_test(capacity: usize) -> (Self, mpsc::Receiver<Vec<Signal>>) {
        let (tx, rx) = mpsc::channel(capacity);
        (
            Self {
                tx,
                flush_failures: Arc::new(AtomicUsize::new(0)),
            },
            rx,
        )
    }
}

/// Background task body: accumulate signals from `rx` and flush to `client`
/// once per `config.batch_size` OR `config.flush_interval`, whichever comes
/// first. Drains and flushes any remaining partial batch once `rx` closes
/// (all [`BufferedExporter`] clones dropped) — the graceful-shutdown path.
async fn flush_loop(
    client: clickhouse::Client,
    mut rx: mpsc::Receiver<Vec<Signal>>,
    config: BufferConfig,
    flush_failures: Arc<AtomicUsize>,
    metrics: Arc<Metrics>,
) {
    let mut batch: Vec<Signal> = Vec::with_capacity(config.batch_size);
    let mut ticker = interval(config.flush_interval);
    // The first tick fires immediately; that is fine here (flush() on an
    // empty batch is a no-op), but skip catch-up bursts if the task is ever
    // delayed under load.
    ticker.set_missed_tick_behavior(MissedTickBehavior::Delay);

    loop {
        tokio::select! {
            biased;

            received = rx.recv() => {
                match received {
                    Some(signals) => {
                        batch.extend(signals);
                        if destination_batch_ready(&batch, config.batch_size) {
                            flush(&client, &mut batch, &flush_failures, &metrics).await;
                        }
                    }
                    None => {
                        // All senders dropped — final drain, then exit.
                        flush(&client, &mut batch, &flush_failures, &metrics).await;
                        return;
                    }
                }
            }

            _ = ticker.tick() => {
                flush(&client, &mut batch, &flush_failures, &metrics).await;
            }
        }
    }
}

// `BATCH_SIZE` means rows per destination table, matching Go's independent
// stream buffers. A mixed Rust batch is ready only when one destination reaches
// the configured row count; it may therefore contain up to roughly four times
// `batch_size` signals before partitioning.
fn destination_batch_ready(batch: &[Signal], batch_size: usize) -> bool {
    let mut logs = 0usize;
    let mut spans = 0usize;
    let mut gauges = 0usize;
    let mut sums = 0usize;
    for signal in batch {
        let count = match signal {
            Signal::Log(_) => &mut logs,
            Signal::Span(_) => &mut spans,
            Signal::Metric(metric) if metric.metric_type == crate::contract::MetricType::Gauge => {
                &mut gauges
            }
            Signal::Metric(_) => &mut sums,
        };
        *count += 1;
        if *count >= batch_size {
            return true;
        }
    }
    false
}

/// Flush `batch` to `client`, retrying up to [`MAX_FLUSH_ATTEMPTS`] times
/// with jittered exponential backoff on failure (mirrors the Go collector's
/// `flushLoop` retry schedule). Always leaves `batch` empty on return —
/// either the flush succeeded, or the batch was dropped after exhausting
/// retries.
async fn flush(
    client: &clickhouse::Client,
    batch: &mut Vec<Signal>,
    flush_failures: &AtomicUsize,
    metrics: &Metrics,
) {
    if batch.is_empty() {
        return;
    }
    let count = batch.len();
    let mut payload = std::mem::take(batch);

    for attempt in 1..=MAX_FLUSH_ATTEMPTS {
        let is_last_attempt = attempt == MAX_FLUSH_ATTEMPTS;
        // Retry requires re-sending the batch, and `export` consumes its
        // input — clone for every attempt except the last, which moves
        // `payload` directly and avoids one clone in the common (success on
        // final attempt) case.
        let attempt_payload = if is_last_attempt {
            std::mem::take(&mut payload)
        } else {
            payload.clone()
        };

        let export_started = Instant::now();
        let export_result = clickhouse_exporter::export(client, attempt_payload).await;
        metrics
            .export_latency_seconds
            .observe(export_started.elapsed().as_secs_f64());

        match export_result {
            Ok(counts) => {
                debug!(
                    logs = counts.logs,
                    spans = counts.spans,
                    metrics = counts.metrics,
                    attempt,
                    "batch flushed"
                );
                metrics
                    .batch_flush_total
                    .with_label_values(&[FLUSH_SIGNAL_LABEL, "success"])
                    .inc();
                metrics
                    .storage_signals_total
                    .with_label_values(&[FLUSH_SIGNAL_LABEL, "persisted"])
                    .inc_by(u64::try_from(count).unwrap_or(u64::MAX));
                // Matches the Go collector: size is only observed on a
                // successful flush (`internal/chstore/store.go`).
                #[allow(clippy::cast_precision_loss)]
                metrics.batch_flush_size.observe(count as f64);
                return;
            }
            Err(err) if is_last_attempt => {
                flush_failures.fetch_add(1, Ordering::Relaxed);
                metrics
                    .batch_flush_total
                    .with_label_values(&[FLUSH_SIGNAL_LABEL, "failure"])
                    .inc();
                metrics.export_errors_total.inc();
                metrics
                    .storage_signals_total
                    .with_label_values(&[FLUSH_SIGNAL_LABEL, "dropped"])
                    .inc_by(u64::try_from(count).unwrap_or(u64::MAX));
                error!(
                    error = %err,
                    count,
                    attempts = attempt,
                    "batch flush failed after max attempts — dropping batch"
                );
                return;
            }
            Err(err) => {
                let delay = jittered_backoff(attempt);
                warn!(
                    error = %err,
                    count,
                    attempt,
                    delay_ms = delay.as_millis(),
                    "batch flush failed, retrying"
                );
                tokio::time::sleep(delay).await;
            }
        }
    }
}

/// `100ms * 2^(attempt-1)` base delay (matching the Go collector's
/// `flushLoop`) plus up to half that in jitter, to avoid every collector
/// instance retrying in lockstep. Jitter is derived from the wall-clock
/// sub-second component — sufficient for spreading retries; not
/// cryptographically random, and no `rand` dependency is warranted for this.
fn jittered_backoff(attempt: u32) -> Duration {
    let base_ms = BASE_BACKOFF_MS.saturating_mul(1u64 << (attempt.saturating_sub(1)));
    let jitter_span_ms = base_ms / 2 + 1;
    let jitter_ms = u64::from(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.subsec_millis())
            .unwrap_or(0),
    ) % jitter_span_ms;
    Duration::from_millis(base_ms + jitter_ms)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::collections::HashMap;

    use super::*;
    use crate::contract::LogSignal;

    fn log_signal() -> Signal {
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
            resource_attributes: HashMap::new(),
        })
    }

    #[test]
    fn enqueue_empty_batch_is_a_no_op() {
        let (buffer, _rx) = BufferedExporter::for_test(4);
        assert!(buffer.enqueue(Vec::new()).is_ok());
    }

    #[test]
    fn enqueue_within_capacity_succeeds() {
        let (buffer, mut rx) = BufferedExporter::for_test(4);
        let batch = vec![log_signal(), log_signal()];
        assert!(buffer.enqueue(batch).is_ok());
        let received = rx.try_recv().expect("one atomic request");
        assert_eq!(received.len(), 2);
        assert!(rx.try_recv().is_err());
    }

    #[test]
    fn enqueue_over_capacity_is_rejected_without_partial_send() {
        let (buffer, mut rx) = BufferedExporter::for_test(1);
        assert!(buffer.enqueue(vec![log_signal()]).is_ok());
        let batch = vec![log_signal(), log_signal()];
        let err = buffer.enqueue(batch).expect_err("queue is full");
        assert!(matches!(err, EnqueueError::Saturated { pending: 2, .. }));
        let first = rx.try_recv().expect("first request remains queued");
        assert_eq!(first.len(), 1);
        assert!(rx.try_recv().is_err());
    }

    #[test]
    fn flush_failures_starts_at_zero() {
        let (buffer, _rx) = BufferedExporter::for_test(4);
        assert_eq!(buffer.flush_failures(), 0);
    }

    #[test]
    fn jittered_backoff_grows_with_attempt() {
        let d1 = jittered_backoff(1);
        let d2 = jittered_backoff(2);
        let d3 = jittered_backoff(3);
        // Even with jitter, attempt N's minimum (base, no jitter) must exceed
        // attempt N-1's maximum jitter bound... rather than asserting exact
        // ordering under jitter, assert each stays within its known bounds.
        assert!(d1.as_millis() >= 100 && d1.as_millis() < 100 + 51);
        assert!(d2.as_millis() >= 200 && d2.as_millis() < 200 + 101);
        assert!(d3.as_millis() >= 400 && d3.as_millis() < 400 + 201);
    }
}
