//! Sentinel OTel Collector — Day 1–5 binary.
//!
//! Thin wrapper around the library crate. All logic lives in
//! [`sentinel_collector`] so integration tests in `tests/` can consume it.
//!
//! Usage:
//!     cargo run -- [path/to/file.jsonl]
//!
//! If no path is given, defaults to `contract/golden/baseline_seed42.jsonl`
//! relative to the workspace root.
//!
//! # Modes
//!
//! - **Count mode (default):** parse the file and tally per-signal counts. No
//!   ClickHouse dependency — this is what `cargo run` does out of the box.
//! - **Export mode:** if `CLICKHOUSE_URL` is set, parse *and* write every
//!   validated signal to ClickHouse at that URL. The MVP end-to-end path.
//!
//! ```sh
//! cargo run                                            # count mode
//! CLICKHOUSE_URL=http://localhost:8123 cargo run       # export mode
//! ```
//!
//! Proper YAML/figment config lands in Day 6; the env switch is the interim.

use std::env;
use std::path::PathBuf;
use std::process::ExitCode;
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

use sentinel_collector::clickhouse_exporter;

const DEFAULT_GOLDEN: &str = "../../contract/golden/baseline_seed42.jsonl";

#[tokio::main]
async fn main() -> ExitCode {
    init_tracing();

    let path = env::args()
        .nth(1)
        .unwrap_or_else(|| DEFAULT_GOLDEN.to_string());
    let path = PathBuf::from(path);

    info!(
        version = env!("CARGO_PKG_VERSION"),
        contract = sentinel_collector::CONTRACT_VERSION,
        path = %path.display(),
        "sentinel-collector starting"
    );

    // Export mode iff CLICKHOUSE_URL is set; otherwise count-only (no CH dep).
    let result = match clickhouse_exporter::url_from_env() {
        Some(url) => {
            info!(clickhouse_url = %url, "export mode: parsing and writing to ClickHouse");
            let client = clickhouse_exporter::build_client(&url);
            sentinel_collector::run_and_export(&path, &client).await
        }
        None => {
            info!("count mode: CLICKHOUSE_URL unset, parsing only");
            sentinel_collector::run(&path)
        }
    };

    match result {
        Ok(counts) => {
            info!(
                logs = counts.logs,
                spans = counts.spans,
                metrics = counts.metrics,
                total_ok = counts.total_ok(),
                parse_errors = counts.parse_errors,
                validation_errors = counts.validation_errors,
                "run complete"
            );
            if counts.has_errors() {
                ExitCode::FAILURE
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(err) => {
            error!(error = %err, "run failed");
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
