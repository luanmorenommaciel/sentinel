//! Sentinel OTel Collector — library crate.
//!
//! Hosts the contract module, the parser pipeline, and the ClickHouse
//! exporter. The binary (`src/main.rs`) is a thin wrapper that calls [`run`]
//! from CLI args. Integration tests (`tests/`) consume this library directly.
//!
//! # Module layout
//!
//! - [`contract`] — the `Signal` enum and all contract types (mirrors Pod 1's
//!   v1.0.0 JSON Schema). No I/O — pure data types and validation logic.
//! - [`clickhouse_exporter`] — Row structs, `From<Signal>` conversions, and
//!   the async [`clickhouse_exporter::export`] entry point. Requires a running
//!   ClickHouse instance to do I/O; the parse path (`run`) does not.
//!
//! # Design
//!
//! `run()` is kept stateless and side-effect-free (file I/O and logging only)
//! so the golden-parse integration test never needs a ClickHouse instance.
//! The exporter path is additive: `run_and_export` reuses the same parse
//! logic and adds the ClickHouse write.

use anyhow::{Context, Result};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;
use tracing::warn;

pub mod clickhouse_exporter;
pub mod config;
pub mod contract;
pub mod grpc;
pub mod otlp;

pub use contract::{ContractError, MetricType, Signal, StatusCode, CONTRACT_VERSION};

/// Per-signal-type tally plus error counts. Returned by [`run`].
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Counts {
    pub logs: usize,
    pub spans: usize,
    pub metrics: usize,
    pub parse_errors: usize,
    pub validation_errors: usize,
}

impl Counts {
    pub fn record(&mut self, sig: &Signal) {
        match sig {
            Signal::Log(_) => self.logs += 1,
            Signal::Span(_) => self.spans += 1,
            Signal::Metric(_) => self.metrics += 1,
        }
    }

    pub fn total_ok(&self) -> usize {
        self.logs + self.spans + self.metrics
    }

    pub fn has_errors(&self) -> bool {
        self.parse_errors > 0 || self.validation_errors > 0
    }
}

/// Parse every line of `path` as an NDJSON-encoded [`Signal`] and return the
/// validated signals together with error tallies.
///
/// This is the shared parse kernel used by both [`run`] (count-only, no I/O to
/// ClickHouse) and [`run_and_export`] (parse + write). Factoring it out means
/// neither caller duplicates the parse loop.
///
/// # Errors
///
/// Returns an error only when the file cannot be opened or a read syscall
/// fails. Per-line parse and validation errors are accumulated in the returned
/// [`Counts`] and logged via `tracing::warn` — they do NOT short-circuit the
/// parse.
pub fn parse_file(path: &Path) -> Result<(Vec<Signal>, Counts)> {
    let file = File::open(path).with_context(|| format!("opening {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut counts = Counts::default();
    let mut signals: Vec<Signal> = Vec::new();

    for (line_no, line) in reader.lines().enumerate() {
        let line_no = line_no + 1;
        let line = line.with_context(|| format!("reading line {line_no}"))?;
        if line.trim().is_empty() {
            continue;
        }

        let signal: Signal = match serde_json::from_str(&line) {
            Ok(s) => s,
            Err(err) => {
                warn!(line = line_no, error = %err, "parse error");
                counts.parse_errors += 1;
                continue;
            }
        };

        if let Err(err) = signal.validate() {
            warn!(line = line_no, error = %err, "validation error");
            counts.validation_errors += 1;
            continue;
        }

        counts.record(&signal);
        signals.push(signal);
    }

    Ok((signals, counts))
}

/// Parse every line of `path` as an NDJSON-encoded [`Signal`] and tally the
/// results.
///
/// This is the original Day-1 entry point. It does **not** touch ClickHouse —
/// `cargo test` and the golden-parse integration test use this path and do not
/// require a running ClickHouse instance.
///
/// # Errors
///
/// Returns an error only when the file cannot be opened or a read syscall
/// fails. Per-line parse and validation errors are accumulated in [`Counts`]
/// and logged via `tracing::warn` — they do NOT short-circuit the run.
pub fn run(path: &Path) -> Result<Counts> {
    let (_signals, counts) = parse_file(path)?;
    Ok(counts)
}

/// Parse `path` and export the validated signals to ClickHouse.
///
/// This is the Day-4 additive path. It calls [`parse_file`] to get a
/// `Vec<Signal>` and then calls [`clickhouse_exporter::export`] to write them.
/// The returned [`Counts`] reflects only successfully exported rows (parse and
/// validation errors are in `counts.parse_errors` / `counts.validation_errors`
/// but export errors cause an early return).
///
/// # Errors
///
/// - `anyhow::Error` wrapping file I/O failures from [`parse_file`].
/// - `anyhow::Error` wrapping [`clickhouse_exporter::ExporterError`] on insert
///   failure.
///
/// # Example
///
/// ```no_run
/// # tokio_test::block_on(async {
/// let client = sentinel_collector::clickhouse_exporter::client_from_env();
/// let counts = sentinel_collector::run_and_export(
///     std::path::Path::new("contract/golden/baseline_seed42.jsonl"),
///     &client,
/// )
/// .await
/// .expect("export failed");
/// println!("exported {} logs, {} spans, {} metrics", counts.logs, counts.spans, counts.metrics);
/// # });
/// ```
pub async fn run_and_export(path: &Path, client: &clickhouse::Client) -> Result<Counts> {
    let (signals, mut counts) = parse_file(path)?;

    let export_counts = clickhouse_exporter::export(client, signals)
        .await
        .with_context(|| "clickhouse export failed")?;

    // Merge the export counts back into the parse counts so the caller gets a
    // single unified tally (parse errors + export row counts in one struct).
    counts.logs = export_counts.logs;
    counts.spans = export_counts.spans;
    counts.metrics = export_counts.metrics;

    Ok(counts)
}

#[cfg(test)]
mod tests {
    // Tests are explicitly allowed to unwrap/expect — see contract.rs::tests
    // for the rationale.
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn counts_record_increments_log_variant() {
        let mut c = Counts::default();
        let log_json = r#"{"signal_type":"log","contract_version":"1.0.0","time_unix_nano":1,"severity_text":"INFO","severity_number":9,"service_name":"s","body":"b","attributes":{},"resource_attributes":{}}"#;
        let sig: Signal = serde_json::from_str(log_json).unwrap();
        c.record(&sig);
        assert_eq!(c.logs, 1);
        assert_eq!(c.spans, 0);
        assert_eq!(c.metrics, 0);
        assert_eq!(c.total_ok(), 1);
    }

    #[test]
    fn counts_has_errors_only_when_set() {
        let mut c = Counts::default();
        assert!(!c.has_errors());
        c.parse_errors = 1;
        assert!(c.has_errors());
    }
}
