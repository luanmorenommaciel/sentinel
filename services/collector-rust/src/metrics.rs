//! Prometheus metrics — EP3.2 (performance equalization).
//!
//! Mirrors the Go collector's `internal/chstore/prom.go` metric set so the
//! two collectors expose a comparable `/metrics` surface for the bake-off.
//! See `services/collector-go/internal/chstore/prom.go` and
//! `services/collector-go/internal/chstore/store.go` (the `flushLoop`
//! increment sites) for the reference shape.
//!
//! # Naming and label parity with the Go collector
//!
//! | Metric | Go | Rust (this module) | Notes |
//! |---|---|---|---|
//! | `sentinel_batch_flush_total{signal,status}` | per real signal type (`trace`/`logs`/`metrics`) | `signal="all"` | The Rust [`crate::buffer::BufferedExporter`] enqueues every [`crate::Signal`] variant into a single combined channel and flushes one mixed batch per cycle (see `crate::buffer` module docs) — there is no per-signal flush boundary to label with. `signal="all"` is deliberate, not a placeholder for future work. |
//! | `sentinel_batch_flush_size` | `HistogramVec{signal}` | `Histogram` (no label) | Same combined-queue reason as above. |
//! | `sentinel_ch_insert_errors_total{signal}` | per-signal | `sentinel_export_errors_total` (no label) | Same reason. |
//! | `sentinel_signals_ingested_total{signal}` | *(none — Rust-only addition)* | `signal="trace"\|"logs"\|"metrics"` | Recorded at the gRPC receive boundary in `crate::grpc`, before buffering, so it *is* per-signal-type — the OTLP request itself carries that distinction even though the internal buffer does not. |
//! | `sentinel_export_latency_seconds` | *(none — Rust-only addition, bonus)* | `Histogram` | Wall-clock duration of each `clickhouse_exporter::export` call inside a flush attempt (success or failure), from `crate::buffer::flush`. |
//!
//! # Why `prometheus` with `default-features = false`
//!
//! The `prometheus` crate's default feature set pulls in `protobuf` (for the
//! binary pull format) which is pure Rust but adds an unnecessary
//! `protobuf-codegen` build dependency; `default-features = false` drops it.
//! Text-format rendering ([`Metrics::render`], via [`TextEncoder`]) needs
//! neither `protobuf` (default feature) nor `push`/`process` (optional,
//! already off by default — they pull in `reqwest`/`procfs`+`libc`
//! respectively). What remains (`lazy_static`, `memchr`, `parking_lot`) is
//! pure Rust with no `-sys`/OpenSSL/ring dependency, so it links cleanly
//! into the musl-static, distroless image (see `Dockerfile`,
//! `RUST_PROJECT_STANDARDS.md`).

use std::sync::Arc;

use prometheus::{
    Encoder, Histogram, HistogramOpts, IntCounter, IntCounterVec, Opts, Registry, TextEncoder,
};
use thiserror::Error;

/// The Prometheus namespace applied to every metric in this module —
/// matches the Go collector's `prometheus.CounterOpts{Namespace: "sentinel"}`.
const NAMESPACE: &str = "sentinel";

/// Errors constructing or rendering the metrics registry.
///
/// Both variants wrap [`prometheus::Error`]; the two are kept distinct so a
/// caller (or a test) can tell registration failures (a programmer error —
/// e.g. a duplicate metric name) apart from rendering failures (an
/// exposition-format encoding error, which should be effectively
/// unreachable given [`TextEncoder`] only writes to an in-memory buffer).
#[derive(Debug, Error)]
pub enum MetricsError {
    /// A metric could not be registered onto the [`Registry`] (e.g. a name
    /// collision). Only possible during [`Metrics::new`].
    #[error("registering metric: {0}")]
    Registration(#[source] prometheus::Error),

    /// The registry's gathered metric families could not be encoded to the
    /// Prometheus text exposition format.
    #[error("encoding metrics: {0}")]
    Encoding(#[source] prometheus::Error),
}

/// The collector's self-observability metrics (Prometheus text format).
///
/// Cheap to clone the individual metric handles (each wraps an internal
/// `Arc`), but the struct itself is shared via [`Arc<Metrics>`] across the
/// gRPC handlers (`crate::grpc`), the buffered exporter's flush loop
/// (`crate::buffer`), and the `/metrics` HTTP server
/// (`crate::metrics_server`) so all three observe the same [`Registry`].
pub struct Metrics {
    registry: Registry,

    /// `sentinel_signals_ingested_total{signal}` — OTLP signals received at
    /// the gRPC boundary, before buffering or validation. Incremented in
    /// `crate::grpc`'s three `Export` handlers.
    pub signals_ingested_total: IntCounterVec,

    /// Signals accepted into the in-memory export pipeline.
    pub signals_accepted_total: IntCounterVec,

    /// Signals rejected before enqueue, labeled by reason.
    pub signals_rejected_total: IntCounterVec,

    /// Signals completed by the storage stage, labeled persisted/dropped.
    pub storage_signals_total: IntCounterVec,

    /// `sentinel_batch_flush_total{signal,status}` — batch flush outcomes.
    /// `signal` is always `"all"` (see the module-level table); `status` is
    /// `"success"` or `"failure"`. Incremented in `crate::buffer::flush`.
    pub batch_flush_total: IntCounterVec,

    /// `sentinel_batch_flush_size` — records per successful batch flush
    /// (mirrors the Go collector, which only observes size on success).
    /// Incremented in `crate::buffer::flush`.
    pub batch_flush_size: Histogram,

    /// `sentinel_export_errors_total` — batches that exhausted
    /// `crate::buffer::MAX_FLUSH_ATTEMPTS` and were dropped. Mirrors the Go
    /// collector's `insertErrors` counter (there, per-signal; here,
    /// combined — see the module-level table). Fed from the same site as
    /// [`crate::buffer::BufferedExporter::flush_failures`].
    pub export_errors_total: IntCounter,

    /// `sentinel_export_latency_seconds` — wall-clock duration of each
    /// `clickhouse_exporter::export` call inside a flush attempt (bonus
    /// metric; no Go equivalent). Incremented in `crate::buffer::flush`.
    pub export_latency_seconds: Histogram,
}

impl Metrics {
    /// Build a fresh, independent metrics registry with every collector
    /// registered.
    ///
    /// Independent means: not the global `prometheus::default_registry()`.
    /// Each call returns its own [`Registry`], so tests (and, in principle,
    /// multiple collector instances in one process) never collide on metric
    /// names.
    ///
    /// # Errors
    ///
    /// Returns [`MetricsError::Registration`] if a metric fails to register
    /// (e.g. a duplicate name within this registry) — not expected to occur
    /// with the fixed set defined here, but the `prometheus` API returns
    /// `Result`, so this surfaces it rather than panicking.
    pub fn new() -> Result<Self, MetricsError> {
        let registry = Registry::new();

        let signals_ingested_total = IntCounterVec::new(
            Opts::new(
                "signals_ingested_total",
                "Total OTLP signals received at the gRPC boundary, labeled by signal type.",
            )
            .namespace(NAMESPACE),
            &["signal"],
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(signals_ingested_total.clone()))
            .map_err(MetricsError::Registration)?;

        let signals_accepted_total = IntCounterVec::new(
            Opts::new(
                "signals_accepted_total",
                "OTLP signals accepted into the in-memory export pipeline.",
            )
            .namespace(NAMESPACE),
            &["signal"],
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(signals_accepted_total.clone()))
            .map_err(MetricsError::Registration)?;

        let signals_rejected_total = IntCounterVec::new(
            Opts::new(
                "signals_rejected_total",
                "OTLP signals rejected before enqueue.",
            )
            .namespace(NAMESPACE),
            &["signal", "reason"],
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(signals_rejected_total.clone()))
            .map_err(MetricsError::Registration)?;

        let storage_signals_total = IntCounterVec::new(
            Opts::new(
                "storage_signals_total",
                "Signals completed by the storage stage.",
            )
            .namespace(NAMESPACE),
            &["signal", "outcome"],
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(storage_signals_total.clone()))
            .map_err(MetricsError::Registration)?;

        let batch_flush_total = IntCounterVec::new(
            Opts::new(
                "batch_flush_total",
                "Total number of batch flushes, labeled by signal and status.",
            )
            .namespace(NAMESPACE),
            &["signal", "status"],
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(batch_flush_total.clone()))
            .map_err(MetricsError::Registration)?;

        let batch_flush_size = Histogram::with_opts(
            HistogramOpts::new("batch_flush_size", "Number of records per batch flush.")
                .namespace(NAMESPACE)
                // Matches the Go collector's bucket set (`prom.go`).
                .buckets(vec![
                    1.0, 10.0, 50.0, 100.0, 250.0, 500.0, 750.0, 1000.0, 2000.0, 5000.0,
                ]),
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(batch_flush_size.clone()))
            .map_err(MetricsError::Registration)?;

        let export_errors_total = IntCounter::with_opts(
            Opts::new(
                "export_errors_total",
                "Total ClickHouse insert errors after all retry attempts.",
            )
            .namespace(NAMESPACE),
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(export_errors_total.clone()))
            .map_err(MetricsError::Registration)?;

        let export_latency_seconds = Histogram::with_opts(
            HistogramOpts::new(
                "export_latency_seconds",
                "ClickHouse INSERT latency in seconds, per flush attempt.",
            )
            .namespace(NAMESPACE)
            .buckets(
                prometheus::exponential_buckets(0.005, 2.0, 12)
                    .map_err(MetricsError::Registration)?,
            ),
        )
        .map_err(MetricsError::Registration)?;
        registry
            .register(Box::new(export_latency_seconds.clone()))
            .map_err(MetricsError::Registration)?;

        Ok(Self {
            registry,
            signals_ingested_total,
            signals_accepted_total,
            signals_rejected_total,
            storage_signals_total,
            batch_flush_total,
            batch_flush_size,
            export_errors_total,
            export_latency_seconds,
        })
    }

    /// Build a fresh [`Metrics`] wrapped in an [`Arc`] — the shape every
    /// call site (`crate::grpc`, `crate::buffer`, `crate::metrics_server`,
    /// `main.rs`) actually wants, since the registry is shared.
    ///
    /// # Errors
    ///
    /// See [`Metrics::new`].
    pub fn new_shared() -> Result<Arc<Self>, MetricsError> {
        Ok(Arc::new(Self::new()?))
    }

    /// Render every registered metric in the Prometheus text exposition
    /// format (what `/metrics` serves).
    ///
    /// # Errors
    ///
    /// Returns [`MetricsError::Encoding`] if the text encoder fails to write
    /// the gathered metric families — not expected in practice, since the
    /// encoder here only writes to an in-memory `Vec<u8>`.
    pub fn render(&self) -> Result<Vec<u8>, MetricsError> {
        let encoder = TextEncoder::new();
        let metric_families = self.registry.gather();
        let mut buffer = Vec::new();
        encoder
            .encode(&metric_families, &mut buffer)
            .map_err(MetricsError::Encoding)?;
        Ok(buffer)
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn new_registers_every_metric_without_error() {
        Metrics::new().expect("metric registration must not collide");
    }

    #[test]
    fn render_includes_every_metric_family_name() {
        let metrics = Metrics::new().expect("registers cleanly");
        metrics
            .signals_ingested_total
            .with_label_values(&["trace"])
            .inc();
        metrics
            .batch_flush_total
            .with_label_values(&["all", "success"])
            .inc();
        metrics.batch_flush_size.observe(42.0);
        metrics.export_errors_total.inc();
        metrics.export_latency_seconds.observe(0.01);

        let rendered = metrics.render().expect("renders cleanly");
        let text = String::from_utf8(rendered).expect("valid utf8");

        for name in [
            "sentinel_signals_ingested_total",
            "sentinel_batch_flush_total",
            "sentinel_batch_flush_size",
            "sentinel_export_errors_total",
            "sentinel_export_latency_seconds",
        ] {
            assert!(text.contains(name), "missing metric family: {name}\n{text}");
        }
        assert!(text.contains(r#"signal="trace""#));
        assert!(text.contains(r#"signal="all""#));
        assert!(text.contains(r#"status="success""#));
    }

    #[test]
    fn two_independent_registries_do_not_collide() {
        // Each `Metrics::new()` builds its own `Registry` — proves this by
        // constructing two in the same process (unlike the global
        // `prometheus::default_registry()`, which would panic/error on the
        // second registration of the same metric name).
        let a = Metrics::new().expect("first registry");
        let b = Metrics::new().expect("second registry");
        a.export_errors_total.inc();
        assert_eq!(a.export_errors_total.get(), 1);
        assert_eq!(b.export_errors_total.get(), 0);
    }
}
