//! Sentinel OTel Collector — binary entry point (Days 1–6).
//!
//! Thin wrapper around the library crate. All logic lives in
//! [`sentinel_collector`] so integration tests in `tests/` can consume it.
//!
//! # Usage
//!
//! ```sh
//! cargo run                       # built-in defaults: count mode, golden fixture
//! cargo run -- config.yaml        # load a config file (see config.example.yaml)
//! CLICKHOUSE_URL=http://localhost:8123 cargo run    # env override → export mode
//! ```
//!
//! # Modes (Day 6 — config-driven)
//!
//! - **Count mode:** no `clickhouse` section configured → parse and tally only,
//!   no ClickHouse dependency.
//! - **Export mode:** `clickhouse` section present (or `CLICKHOUSE_URL` set) →
//!   parse and write every validated signal to ClickHouse.
//!
//! `contract.strict` controls the receive-boundary policy: when `true`, any
//! parse/validation error aborts the run **before** export (all-or-nothing).

use std::env;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::ExitCode;

use tracing::{error, info};
use tracing_subscriber::EnvFilter;

use sentinel_collector::clickhouse_exporter;
use sentinel_collector::config::{Config, LogFormat, LoggingConfig};

#[tokio::main]
async fn main() -> ExitCode {
    // Load config first so logging is configured before anything is emitted.
    // `std::env::args` is allowed (only `std::env::var` is disallowed).
    let config = match load_config(env::args().nth(1)) {
        Ok(config) => config,
        Err(code) => return code,
    };

    init_tracing(&config.logging);

    // Receive-boundary check #1: this binary must have been built for the
    // contract version the config expects. Fail fast before reading any data.
    if let Err(err) = config.ensure_build_compatible() {
        error!(error = %err, "incompatible contract version");
        return ExitCode::FAILURE;
    }

    // Server mode (gRPC section present) and file mode are mutually exclusive
    // lifecycles: the server runs until Ctrl-C; file mode runs once and exits.
    match config.grpc {
        Some(_) => serve_grpc(&config).await,
        None => run(&config).await,
    }
}

/// Run the OTLP gRPC server until Ctrl-C.
///
/// When `config.clickhouse` is present the server operates in **export mode**:
/// each received OTLP request is transformed to [`sentinel_collector::Signal`]
/// values and flushed to ClickHouse. When absent the server operates in
/// **log-only mode**: signals are counted and logged but not persisted.
async fn serve_grpc(config: &sentinel_collector::config::Config) -> ExitCode {
    let cfg = match &config.grpc {
        Some(g) => g,
        None => {
            error!("serve_grpc called without a grpc config section");
            return ExitCode::FAILURE;
        }
    };

    let addr: SocketAddr = match cfg.listen.parse() {
        Ok(addr) => addr,
        Err(err) => {
            error!(listen = %cfg.listen, error = %err, "invalid grpc.listen address");
            return ExitCode::FAILURE;
        }
    };

    // Build the ClickHouse client when the clickhouse config section is present.
    let client: Option<clickhouse::Client> = config.clickhouse.as_ref().map(|ch| {
        info!(url = %ch.url, database = %ch.database, "export mode: ClickHouse target configured");
        clickhouse_exporter::build_client_with_database(&ch.url, &ch.database)
    });

    if client.is_none() {
        info!("log-only mode: no clickhouse section configured");
    }

    let shutdown = async {
        if tokio::signal::ctrl_c().await.is_ok() {
            info!("shutdown signal received");
        }
    };

    match sentinel_collector::grpc::serve(addr, shutdown, client).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            error!(error = %err, "gRPC server terminated with error");
            ExitCode::FAILURE
        }
    }
}

/// Load config from an optional path argument, applying env overrides.
///
/// `Ok(config)` on success; `Err(exit_code)` if a provided path fails to load
/// (we cannot use the logger yet — it is configured from the very config we are
/// loading — so we print to stderr and surface a failure code).
fn load_config(path_arg: Option<String>) -> Result<Config, ExitCode> {
    let mut config = match path_arg {
        Some(path) => match Config::load(&PathBuf::from(&path)) {
            Ok(config) => config,
            Err(err) => {
                eprintln!("config error: {err}");
                return Err(ExitCode::FAILURE);
            }
        },
        None => Config::default(),
    };
    config.apply_env_overrides();
    Ok(config)
}

/// Parse the configured input and, when a `clickhouse` section is present,
/// export to ClickHouse. Enforces the strict receive-boundary policy.
async fn run(config: &Config) -> ExitCode {
    info!(
        version = env!("CARGO_PKG_VERSION"),
        contract = sentinel_collector::CONTRACT_VERSION,
        input = %config.input.path.display(),
        "sentinel-collector starting"
    );

    let (signals, counts) = match sentinel_collector::parse_file(&config.input.path) {
        Ok(parsed) => parsed,
        Err(err) => {
            error!(error = %err, "parse failed");
            return ExitCode::FAILURE;
        }
    };

    // Receive-boundary check #2: strict mode rejects the whole run on any
    // contract violation, before exporting anything (all-or-nothing).
    if config.contract.strict && counts.has_errors() {
        error!(
            parse_errors = counts.parse_errors,
            validation_errors = counts.validation_errors,
            "strict mode: contract violations present — rejecting run, nothing exported"
        );
        return ExitCode::FAILURE;
    }

    let counts = match &config.clickhouse {
        Some(ch) => {
            info!(url = %ch.url, database = %ch.database, "export mode");
            let client = clickhouse_exporter::build_client_with_database(&ch.url, &ch.database);
            match clickhouse_exporter::export(&client, signals).await {
                Ok(export_counts) => export_counts,
                Err(err) => {
                    error!(error = %err, "clickhouse export failed");
                    return ExitCode::FAILURE;
                }
            }
        }
        None => {
            info!("count mode: no clickhouse section configured");
            counts
        }
    };

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

/// Initialise `tracing` from the logging config. `RUST_LOG`, if set, overrides
/// `logging.level`.
fn init_tracing(cfg: &LoggingConfig) {
    let filter =
        EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new(cfg.level.clone()));
    let builder = tracing_subscriber::fmt().with_env_filter(filter);
    let _ = match cfg.format {
        LogFormat::Json => builder.json().try_init(),
        LogFormat::Text => builder.try_init(),
    };
}
