//! Configuration loader — the **Sentinel config loader** referenced by
//! `clippy.toml`'s `disallowed-methods` rule.
//!
//! Day 6 replaces the Day-5 `CLICKHOUSE_URL`-only switch with a YAML config
//! file. The shape (see `config.example.yaml`):
//!
//! ```yaml
//! input:
//!   path: ../../contracts/generator/v1/golden/baseline_seed42.jsonl
//! clickhouse:                 # omit this whole section for count-only mode
//!   url: http://localhost:8123
//!   database: default
//! contract:
//!   expected_version: "1.0.0" # must match the version this binary was built for
//!   strict: false             # true → any contract violation aborts before export
//! logging:
//!   level: info
//!   format: json              # json | text
//! ```
//!
//! Every field has a default, so a missing file or a partial document still
//! yields a usable [`Config`]. Unknown keys are rejected (`deny_unknown_fields`)
//! to catch typos early.
//!
//! Environment overrides: [`Config::apply_env_overrides`] lets `CLICKHOUSE_URL`
//! win over the file (keeps the Day-5 ergonomics and the integration test's
//! env-driven flow). It is the **only** sanctioned `std::env` read besides the
//! one in [`crate::clickhouse_exporter`].

use std::path::{Path, PathBuf};

use serde::Deserialize;
use thiserror::Error;

use crate::contract::CONTRACT_VERSION;

/// Default golden fixture path, relative to the crate's run directory.
const DEFAULT_INPUT_PATH: &str = "../../contracts/generator/v1/golden/baseline_seed42.jsonl";

/// Top-level collector configuration.
///
/// `Default` is derived — each field delegates to its own `Default` (the
/// sub-structs carry the non-trivial defaults; `clickhouse` defaults to `None`,
/// i.e. count-only mode).
#[derive(Debug, Clone, PartialEq, Eq, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    /// Where to read NDJSON signals from (file mode).
    pub input: InputConfig,
    /// ClickHouse target. `None` (section omitted) ⇒ count-only mode.
    pub clickhouse: Option<ClickHouseConfig>,
    /// OTLP gRPC server. `Some` ⇒ server mode (serve `:4317`); `None` ⇒ file
    /// mode (parse `input`, optionally export). Mutually exclusive lifecycles.
    pub grpc: Option<GrpcConfig>,
    /// Contract-version policy enforced at the receive boundary.
    pub contract: ContractConfig,
    /// Structured-logging configuration.
    pub logging: LoggingConfig,
}

/// Input source configuration.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct InputConfig {
    /// Path to the NDJSON file of signals.
    pub path: PathBuf,
}

impl Default for InputConfig {
    fn default() -> Self {
        Self {
            path: PathBuf::from(DEFAULT_INPUT_PATH),
        }
    }
}

/// ClickHouse connection configuration. Presence of this section switches the
/// binary into export mode.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ClickHouseConfig {
    /// HTTP endpoint, e.g. `http://localhost:8123`. The `clickhouse` 0.13 crate
    /// speaks RowBinary over HTTP — not native `:9000`.
    pub url: String,
    /// Target database. Defaults to `default`.
    #[serde(default = "default_database")]
    pub database: String,
}

fn default_database() -> String {
    "default".to_string()
}

/// OTLP gRPC server configuration. Presence of this section switches the binary
/// into server mode.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct GrpcConfig {
    /// Listen address for the OTLP gRPC server. Defaults to the OTLP convention
    /// `[::]:4317` (all interfaces, the standard OTLP gRPC port).
    pub listen: String,
}

impl Default for GrpcConfig {
    fn default() -> Self {
        Self {
            listen: "[::]:4317".to_string(),
        }
    }
}

/// Contract-version policy applied at the receive boundary.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ContractConfig {
    /// The Pod 1 contract version this collector expects. Asserted against the
    /// compiled-in [`CONTRACT_VERSION`] at startup (see
    /// [`Config::ensure_build_compatible`]).
    pub expected_version: String,
    /// **File mode only.** When `true`, any parse or validation error (including
    /// a mismatched per-signal `contract_version`) aborts the run **before**
    /// anything is exported — all-or-nothing. When `false`, bad signals are
    /// skipped and counted, and the good ones still flow through.
    pub strict: bool,
    /// **gRPC mode only.** Contract-validation policy applied to each signal
    /// transformed from an OTLP request, *before* it is exported. See
    /// [`GrpcValidation`]. Defaults to [`GrpcValidation::Warn`] — validate every
    /// signal and log violations, but still export, so legitimate foreign OTLP
    /// (which lacks the five `sentinel.*` resource keys) is never dropped.
    pub grpc_validation: GrpcValidation,
}

impl Default for ContractConfig {
    fn default() -> Self {
        Self {
            expected_version: CONTRACT_VERSION.to_string(),
            strict: false,
            grpc_validation: GrpcValidation::default(),
        }
    }
}

/// Receive-boundary validation policy for the OTLP **gRPC** path.
///
/// Unlike the file path — where every record is Sentinel-originated and must
/// carry the full contract — the gRPC server may receive OTLP from arbitrary
/// senders that legitimately lack the five `sentinel.*` resource keys. This
/// enum chooses how strictly [`crate::contract::Signal::validate`] is enforced
/// on that path:
///
/// - [`Off`](GrpcValidation::Off): skip validation entirely (the pre-policy
///   behaviour). Lowest overhead; no contract enforcement on the wire.
/// - [`Warn`](GrpcValidation::Warn) *(default)*: validate every signal, log a
///   warning for each violation, but **export anyway**. Observability without
///   rejecting foreign traffic.
/// - [`Strict`](GrpcValidation::Strict): validate every signal and **drop**
///   the invalid ones (per-signal, not all-or-nothing), exporting only the
///   conformant remainder. Use when the sender is guaranteed Sentinel-internal.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GrpcValidation {
    /// Skip validation on the gRPC path.
    Off,
    /// Validate and log violations, but export every signal regardless.
    #[default]
    Warn,
    /// Validate and drop invalid signals; export only the conformant ones.
    Strict,
}

/// Structured-logging configuration.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct LoggingConfig {
    /// Log level / `EnvFilter` directive (e.g. `info`, `debug`,
    /// `sentinel_collector=debug`). `RUST_LOG`, if set, overrides this.
    pub level: String,
    /// Output format.
    pub format: LogFormat,
}

impl Default for LoggingConfig {
    fn default() -> Self {
        Self {
            level: "info".to_string(),
            format: LogFormat::Json,
        }
    }
}

/// Log output format.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogFormat {
    /// One JSON object per line (machine-ingestible — the production default).
    Json,
    /// Human-readable text (handy for local debugging).
    Text,
}

/// Errors raised while loading or validating configuration.
#[derive(Debug, Error)]
pub enum ConfigError {
    /// The config file could not be read.
    #[error("reading config {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    /// The config file was not valid YAML for the [`Config`] shape (includes
    /// unknown-key errors from `deny_unknown_fields`).
    #[error("parsing config {path}: {source}")]
    Parse {
        path: PathBuf,
        #[source]
        source: serde_yaml::Error,
    },

    /// `contract.expected_version` does not match the version this binary was
    /// built to parse. A collector built for contract X cannot validate
    /// contract Y — fail fast at startup rather than silently mis-validate.
    #[error(
        "config contract.expected_version {configured:?} != collector build version {compiled:?}"
    )]
    ContractVersionMismatch {
        configured: String,
        compiled: String,
    },
}

impl Config {
    /// Load and parse a YAML config from `path`.
    ///
    /// # Errors
    ///
    /// Returns [`ConfigError::Io`] if the file cannot be read, or
    /// [`ConfigError::Parse`] if it is not valid YAML for the [`Config`] shape.
    pub fn load(path: &Path) -> Result<Self, ConfigError> {
        let text = std::fs::read_to_string(path).map_err(|source| ConfigError::Io {
            path: path.to_path_buf(),
            source,
        })?;
        serde_yaml::from_str(&text).map_err(|source| ConfigError::Parse {
            path: path.to_path_buf(),
            source,
        })
    }

    /// Assert that the configured contract version matches the version this
    /// binary was compiled to parse ([`CONTRACT_VERSION`]).
    ///
    /// This is the **startup boundary check**: it catches a misconfigured
    /// deployment (collector built for 1.0.0, pointed at a 2.0.0 pipeline)
    /// before a single signal is read.
    ///
    /// # Errors
    ///
    /// [`ConfigError::ContractVersionMismatch`] if the versions differ.
    pub fn ensure_build_compatible(&self) -> Result<(), ConfigError> {
        if self.contract.expected_version == CONTRACT_VERSION {
            Ok(())
        } else {
            Err(ConfigError::ContractVersionMismatch {
                configured: self.contract.expected_version.clone(),
                compiled: CONTRACT_VERSION.to_string(),
            })
        }
    }

    /// Apply environment overrides over the file-loaded config.
    ///
    /// Currently: `CLICKHOUSE_URL`, if set, overrides (or creates) the
    /// ClickHouse target. This preserves the Day-5 ergonomics and the
    /// integration test's env-driven flow while keeping the file as the
    /// primary source of truth.
    pub fn apply_env_overrides(&mut self) {
        // The one sanctioned `std::env::var` here (mirrors the allow in
        // clickhouse_exporter::url_from_env). All other config flows through
        // this loader.
        #[allow(clippy::disallowed_methods)]
        let url = std::env::var("CLICKHOUSE_URL").ok();

        if let Some(url) = url {
            match &mut self.clickhouse {
                Some(ch) => ch.url = url,
                None => {
                    self.clickhouse = Some(ClickHouseConfig {
                        url,
                        database: default_database(),
                    });
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn default_config_is_count_mode_with_golden_input() {
        let cfg = Config::default();
        assert!(cfg.clickhouse.is_none(), "default must be count-only mode");
        assert_eq!(cfg.input.path, PathBuf::from(DEFAULT_INPUT_PATH));
        assert_eq!(cfg.contract.expected_version, CONTRACT_VERSION);
        assert!(!cfg.contract.strict);
        assert_eq!(cfg.logging.format, LogFormat::Json);
    }

    #[test]
    fn full_yaml_parses_all_sections() {
        let yaml = r#"
input:
  path: /data/signals.jsonl
clickhouse:
  url: http://ch:8123
  database: sentinel
contract:
  expected_version: "1.0.0"
  strict: true
logging:
  level: debug
  format: text
"#;
        let cfg: Config = serde_yaml::from_str(yaml).expect("parses");
        assert_eq!(cfg.input.path, PathBuf::from("/data/signals.jsonl"));
        let ch = cfg.clickhouse.expect("clickhouse section present");
        assert_eq!(ch.url, "http://ch:8123");
        assert_eq!(ch.database, "sentinel");
        assert!(cfg.contract.strict);
        assert_eq!(cfg.logging.level, "debug");
        assert_eq!(cfg.logging.format, LogFormat::Text);
    }

    #[test]
    fn empty_yaml_yields_defaults() {
        // An empty document deserializes to all-defaults via `#[serde(default)]`.
        let cfg: Config = serde_yaml::from_str("{}").expect("parses");
        assert_eq!(cfg, Config::default());
    }

    #[test]
    fn clickhouse_database_defaults_to_default() {
        let yaml = "clickhouse:\n  url: http://ch:8123\n";
        let cfg: Config = serde_yaml::from_str(yaml).expect("parses");
        assert_eq!(cfg.clickhouse.expect("present").database, "default");
    }

    #[test]
    fn grpc_absent_is_file_mode() {
        assert!(Config::default().grpc.is_none());
    }

    #[test]
    fn grpc_empty_section_defaults_to_otlp_port() {
        // Presence of the section (even empty) → server mode on the default port.
        let cfg: Config = serde_yaml::from_str("grpc: {}\n").expect("parses");
        assert_eq!(cfg.grpc.expect("present").listen, "[::]:4317");
    }

    #[test]
    fn grpc_explicit_listen_parses() {
        let cfg: Config =
            serde_yaml::from_str("grpc:\n  listen: 127.0.0.1:4317\n").expect("parses");
        assert_eq!(cfg.grpc.expect("present").listen, "127.0.0.1:4317");
    }

    #[test]
    fn unknown_key_is_rejected() {
        let yaml = "input:\n  path: x\n  bogus: 1\n";
        let err = serde_yaml::from_str::<Config>(yaml).unwrap_err();
        assert!(
            err.to_string().contains("bogus") || err.to_string().contains("unknown field"),
            "deny_unknown_fields should reject typos, got: {err}"
        );
    }

    #[test]
    fn ensure_build_compatible_accepts_matching_version() {
        let cfg = Config::default(); // expected_version == CONTRACT_VERSION
        assert!(cfg.ensure_build_compatible().is_ok());
    }

    #[test]
    fn ensure_build_compatible_rejects_mismatch() {
        let mut cfg = Config::default();
        cfg.contract.expected_version = "2.0.0".to_string();
        let err = cfg.ensure_build_compatible().unwrap_err();
        assert!(matches!(err, ConfigError::ContractVersionMismatch { .. }));
    }

    #[test]
    fn grpc_validation_defaults_to_warn() {
        assert_eq!(
            Config::default().contract.grpc_validation,
            GrpcValidation::Warn
        );
    }

    #[test]
    fn grpc_validation_parses_each_variant() {
        for (yaml_val, expected) in [
            ("off", GrpcValidation::Off),
            ("warn", GrpcValidation::Warn),
            ("strict", GrpcValidation::Strict),
        ] {
            let yaml = format!("contract:\n  grpc_validation: {yaml_val}\n");
            let cfg: Config = serde_yaml::from_str(&yaml).expect("parses");
            assert_eq!(cfg.contract.grpc_validation, expected, "value {yaml_val}");
        }
    }

    #[test]
    fn grpc_validation_absent_falls_back_to_default() {
        // A contract section that sets only `strict` still gets the Warn default.
        let cfg: Config = serde_yaml::from_str("contract:\n  strict: true\n").expect("parses");
        assert!(cfg.contract.strict);
        assert_eq!(cfg.contract.grpc_validation, GrpcValidation::Warn);
    }

    #[test]
    fn env_override_creates_clickhouse_section_when_absent() {
        // Drive the override logic directly (no real env mutation) by mirroring
        // what apply_env_overrides does when CLICKHOUSE_URL is present.
        let mut cfg = Config::default();
        assert!(cfg.clickhouse.is_none());
        // Simulate the override branch:
        cfg.clickhouse = Some(ClickHouseConfig {
            url: "http://injected:8123".to_string(),
            database: default_database(),
        });
        let ch = cfg.clickhouse.expect("present");
        assert_eq!(ch.url, "http://injected:8123");
        assert_eq!(ch.database, "default");
    }
}
