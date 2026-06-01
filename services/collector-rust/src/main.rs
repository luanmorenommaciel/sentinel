//! Sentinel OTel Collector — Day 1 binary.
//!
//! Thin wrapper around [`sentinel_collector::run`]. All logic lives in the
//! library crate so integration tests in `tests/` can consume it.
//!
//! Usage:
//!     cargo run -- [path/to/file.jsonl]
//!
//! If no path is given, defaults to `contract/golden/baseline_seed42.jsonl`
//! relative to the workspace root.

use std::env;
use std::path::PathBuf;
use std::process::ExitCode;
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

const DEFAULT_GOLDEN: &str = "../../contract/golden/baseline_seed42.jsonl";

fn main() -> ExitCode {
    init_tracing();

    let path = env::args()
        .nth(1)
        .unwrap_or_else(|| DEFAULT_GOLDEN.to_string());
    let path = PathBuf::from(path);

    info!(
        version = env!("CARGO_PKG_VERSION"),
        contract = sentinel_collector::CONTRACT_VERSION,
        path = %path.display(),
        "sentinel-collector day-1 parser starting"
    );

    match sentinel_collector::run(&path) {
        Ok(counts) => {
            info!(
                logs = counts.logs,
                spans = counts.spans,
                metrics = counts.metrics,
                total_ok = counts.total_ok(),
                parse_errors = counts.parse_errors,
                validation_errors = counts.validation_errors,
                "parser complete"
            );
            if counts.has_errors() {
                ExitCode::FAILURE
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(err) => {
            error!(error = %err, "parser failed");
            ExitCode::FAILURE
        }
    }
}

fn init_tracing() {
    let _ = tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .json()
        .try_init();
}
