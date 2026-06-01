//! Sentinel OTel Collector — library crate.
//!
//! Hosts the contract module and the parser pipeline. The binary
//! (`src/main.rs`) is a thin wrapper that calls [`run`] from CLI args.
//! Integration tests (`tests/`) consume this library directly.
//!
//! Design: keep this crate stateless and side-effect-free (file I/O and
//! logging only). All ClickHouse, gRPC, and runtime concerns live in
//! later phases per `docs/research/learning-roadmap-pod2-rust.md`.

use anyhow::{Context, Result};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;
use tracing::warn;

pub mod contract;

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

/// Parse every line of `path` as an NDJSON-encoded [`Signal`] and tally the
/// results.
///
/// # Errors
///
/// Returns an error only when the file cannot be opened or a read syscall
/// fails. Per-line parse and validation errors are accumulated in [`Counts`]
/// and logged via `tracing::warn` — they do NOT short-circuit the run.
pub fn run(path: &Path) -> Result<Counts> {
    let file = File::open(path).with_context(|| format!("opening {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut counts = Counts::default();

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
    }

    Ok(counts)
}

#[cfg(test)]
mod tests {
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
