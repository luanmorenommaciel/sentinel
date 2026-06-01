//! Pod 1 → Pod 2 OTLP output contract — Rust mirror.
//!
//! This module is the Rust counterpart to Pod 1's published JSON Schema at
//! `contract/schema/otlp_output.schema.json` (v1.0.0) and the Pydantic models
//! at `src/otelgen/contract/models.py` on the `001-otel-data-generator`
//! branch upstream.
//!
//! Mapping derived from the `python-developer` agent's analysis on
//! 2026-06-01. See `docs/research/learning-roadmap-pod2-rust.md` for the
//! sprint context and `docs/research/contract-review-pod1-v1.0.0.md` for
//! Pod 2's review of the v1.0.0 contract (notably blockers B1–B4).
//!
//! ## Design decisions
//!
//! - **Discrimination on `signal_type`** via `#[serde(tag = ...)]`. Each
//!   variant carries its own fields; common fields are duplicated across
//!   structs rather than flattened, because the field sets diverge enough
//!   that flattening would obscure intent.
//!
//! - **Timestamps as `i64`.** JSON has no unsigned integer type and
//!   `i64::MAX` (≈ 9.2 × 10¹⁸) is well above 2262-era nanos. Negative
//!   values are illegal per the schema's `minimum: 0` and are rejected at
//!   the `Signal::validate()` boundary, not at the type level.
//!
//! - **Trace/span IDs as `String`.** v1 simplicity. A future `TraceId` /
//!   `SpanId` newtype would enforce hex-validation at the type level; for
//!   now, validation happens in `Signal::validate()` to keep the parser
//!   zero-overhead.
//!
//! - **Attributes as `HashMap<String, String>`.** Mirrors Pod 1's
//!   string-only attribute encoding (contract review B1 — flagged but
//!   binding for v1.0.0).
//!
//! - **`MetricType::Histogram` is intentionally absent.** Pod 1's
//!   `model.py` lists it but the schema enum forbids it and the
//!   serializer never emits it. Adding the variant here would let invalid
//!   data through. When Pod 1 bumps to a contract version that supports
//!   histograms, this enum gets the variant.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;

/// Compiled-in contract version. Bumped in lockstep with Pod 1's
/// `CONTRACT_VERSION` in `src/otelgen/contract/output_schema.py`.
pub const CONTRACT_VERSION: &str = "1.0.0";

/// Five resource-attribute keys Pod 1 guarantees on every signal.
pub const REQUIRED_RESOURCE_KEYS: &[&str] = &[
    "sentinel.synthetic",
    "sentinel.scenario",
    "sentinel.run_id",
    "cloud.provider",
    "service.name",
];

/// A single OTLP signal, discriminated on the `signal_type` tag.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "signal_type", rename_all = "lowercase")]
pub enum Signal {
    Log(LogSignal),
    Span(SpanSignal),
    Metric(MetricSignal),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LogSignal {
    pub contract_version: String,
    pub time_unix_nano: i64,
    pub severity_text: String,
    pub severity_number: i32,
    pub service_name: String,
    pub body: String,
    /// Nullable per the schema; non-null in every observed golden record.
    #[serde(default)]
    pub trace_id: Option<String>,
    #[serde(default)]
    pub span_id: Option<String>,
    pub attributes: HashMap<String, String>,
    pub resource_attributes: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SpanSignal {
    pub contract_version: String,
    pub trace_id: String,
    pub span_id: String,
    /// Always emitted by Pod 1's serializer (key present, value possibly null).
    #[serde(default)]
    pub parent_span_id: Option<String>,
    pub name: String,
    pub service_name: String,
    pub start_unix_nano: i64,
    pub end_unix_nano: i64,
    pub status_code: StatusCode,
    pub attributes: HashMap<String, String>,
    pub resource_attributes: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MetricSignal {
    pub contract_version: String,
    pub time_unix_nano: i64,
    pub name: String,
    /// Maps to JSON's `type` field; renamed to avoid shadowing the Rust keyword.
    #[serde(rename = "type")]
    pub metric_type: MetricType,
    pub value: f64,
    pub service_name: String,
    pub attributes: HashMap<String, String>,
    pub resource_attributes: HashMap<String, String>,
}

/// Wire values: `"OK"` and `"ERROR"`.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum StatusCode {
    Ok,
    Error,
}

/// Wire values: `"gauge"` and `"sum"`. Histogram intentionally not modeled —
/// see module-level docs and the contract review B2.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum MetricType {
    Gauge,
    Sum,
}

/// Validation errors at the receive boundary. These are the constraints the
/// JSON Schema describes but that serde alone does not enforce. Pod 2 mirrors
/// these on every signal as the upstream's belt-and-braces partner.
#[derive(Debug, Error, PartialEq)]
pub enum ContractError {
    #[error("contract_version mismatch: expected {expected}, got {got}")]
    VersionMismatch { expected: String, got: String },

    #[error("contract_version not semver: {0}")]
    InvalidSemver(String),

    #[error("service_name must be non-empty")]
    EmptyServiceName,

    #[error("time_unix_nano must be >= 0, got {0}")]
    NegativeTimestamp(i64),

    #[error("start_unix_nano ({start}) must be <= end_unix_nano ({end})")]
    InvalidSpanInterval { start: i64, end: i64 },

    #[error("trace_id does not match ^[0-9a-f]{{32}}$: {0}")]
    InvalidTraceId(String),

    #[error("span_id does not match ^[0-9a-f]{{16}}$: {0}")]
    InvalidSpanId(String),

    #[error("missing required resource_attribute: {0}")]
    MissingResourceKey(String),

    #[error("metric name must be non-empty")]
    EmptyMetricName,
}

impl Signal {
    /// Validate the constraints the JSON Schema enforces but serde cannot.
    /// Cheap: a handful of regex matches + presence checks. Called once per
    /// received record at the boundary.
    ///
    /// Strict by default: `contract_version` must equal [`CONTRACT_VERSION`].
    /// Soft-warn (log + continue) belongs in the caller, not here.
    pub fn validate(&self) -> Result<(), ContractError> {
        match self {
            Signal::Log(log) => log.validate(),
            Signal::Span(span) => span.validate(),
            Signal::Metric(metric) => metric.validate(),
        }
    }

    /// The contract version on this signal (for routing, logging, error
    /// messages) without unwrapping the variant.
    pub fn contract_version(&self) -> &str {
        match self {
            Signal::Log(s) => &s.contract_version,
            Signal::Span(s) => &s.contract_version,
            Signal::Metric(s) => &s.contract_version,
        }
    }
}

impl LogSignal {
    fn validate(&self) -> Result<(), ContractError> {
        validate_contract_version(&self.contract_version)?;
        validate_service_name(&self.service_name)?;
        if self.time_unix_nano < 0 {
            return Err(ContractError::NegativeTimestamp(self.time_unix_nano));
        }
        validate_required_resource_keys(&self.resource_attributes)?;
        // Log trace_id / span_id are unconstrained by schema; intentionally
        // not validated here.
        Ok(())
    }
}

impl SpanSignal {
    fn validate(&self) -> Result<(), ContractError> {
        validate_contract_version(&self.contract_version)?;
        validate_service_name(&self.service_name)?;
        if self.start_unix_nano < 0 {
            return Err(ContractError::NegativeTimestamp(self.start_unix_nano));
        }
        if self.end_unix_nano < self.start_unix_nano {
            return Err(ContractError::InvalidSpanInterval {
                start: self.start_unix_nano,
                end: self.end_unix_nano,
            });
        }
        if !is_hex_32(&self.trace_id) {
            return Err(ContractError::InvalidTraceId(self.trace_id.clone()));
        }
        if !is_hex_16(&self.span_id) {
            return Err(ContractError::InvalidSpanId(self.span_id.clone()));
        }
        if let Some(parent) = &self.parent_span_id {
            if !is_hex_16(parent) {
                return Err(ContractError::InvalidSpanId(parent.clone()));
            }
        }
        validate_required_resource_keys(&self.resource_attributes)?;
        Ok(())
    }
}

impl MetricSignal {
    fn validate(&self) -> Result<(), ContractError> {
        validate_contract_version(&self.contract_version)?;
        validate_service_name(&self.service_name)?;
        if self.time_unix_nano < 0 {
            return Err(ContractError::NegativeTimestamp(self.time_unix_nano));
        }
        if self.name.is_empty() {
            return Err(ContractError::EmptyMetricName);
        }
        validate_required_resource_keys(&self.resource_attributes)?;
        Ok(())
    }
}

fn validate_contract_version(got: &str) -> Result<(), ContractError> {
    if !is_semver(got) {
        return Err(ContractError::InvalidSemver(got.to_string()));
    }
    if got != CONTRACT_VERSION {
        return Err(ContractError::VersionMismatch {
            expected: CONTRACT_VERSION.to_string(),
            got: got.to_string(),
        });
    }
    Ok(())
}

/// Match `X.Y.Z` where each part is non-empty digits. No regex dep needed.
fn is_semver(s: &str) -> bool {
    let parts: Vec<&str> = s.split('.').collect();
    parts.len() == 3
        && parts
            .iter()
            .all(|p| !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()))
}

fn validate_service_name(name: &str) -> Result<(), ContractError> {
    if name.is_empty() {
        return Err(ContractError::EmptyServiceName);
    }
    Ok(())
}

fn validate_required_resource_keys(attrs: &HashMap<String, String>) -> Result<(), ContractError> {
    for key in REQUIRED_RESOURCE_KEYS {
        if !attrs.contains_key(*key) {
            return Err(ContractError::MissingResourceKey((*key).to_string()));
        }
    }
    Ok(())
}

/// Lowercase-hex check with fixed length. The schema requires exactly 32
/// chars for `trace_id` and 16 for `span_id`/`parent_span_id`. Uppercase
/// hex is rejected (the schema's lowercase-only pattern is deliberate;
/// flagged in the contract review as N4 but binding for v1.0.0).
fn is_hex_32(s: &str) -> bool {
    is_lowercase_hex(s, 32)
}

fn is_hex_16(s: &str) -> bool {
    is_lowercase_hex(s, 16)
}

fn is_lowercase_hex(s: &str, expected_len: usize) -> bool {
    s.len() == expected_len && s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

#[cfg(test)]
mod tests {
    // Tests are explicitly allowed to unwrap/expect — failing fast with a
    // diagnostic is the whole point. Production code is governed by the
    // `unwrap_used = deny` lint in Cargo.toml.
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    fn req_attrs() -> HashMap<String, String> {
        let mut m = HashMap::new();
        for k in REQUIRED_RESOURCE_KEYS {
            m.insert((*k).to_string(), "x".to_string());
        }
        m
    }

    #[test]
    fn signal_type_discrimination_log() {
        let json = r#"{"signal_type":"log","contract_version":"1.0.0","time_unix_nano":1,"severity_text":"INFO","severity_number":9,"service_name":"s","body":"b","attributes":{},"resource_attributes":{"sentinel.synthetic":"true","sentinel.scenario":"x","sentinel.run_id":"r","cloud.provider":"gcp","service.name":"s"}}"#;
        let sig: Signal = serde_json::from_str(json).expect("parses");
        assert!(matches!(sig, Signal::Log(_)));
        assert_eq!(sig.contract_version(), "1.0.0");
        sig.validate().expect("valid");
    }

    #[test]
    fn signal_type_discrimination_metric_renamed_type_field() {
        let json = r#"{"signal_type":"metric","contract_version":"1.0.0","time_unix_nano":1,"name":"latency","type":"gauge","value":1.0,"service_name":"s","attributes":{},"resource_attributes":{"sentinel.synthetic":"true","sentinel.scenario":"x","sentinel.run_id":"r","cloud.provider":"gcp","service.name":"s"}}"#;
        let sig: Signal = serde_json::from_str(json).expect("parses");
        match &sig {
            Signal::Metric(m) => assert_eq!(m.metric_type, MetricType::Gauge),
            _ => panic!("expected metric variant"),
        }
        sig.validate().expect("valid");
    }

    #[test]
    fn histogram_metric_type_is_rejected() {
        let json = r#"{"signal_type":"metric","contract_version":"1.0.0","time_unix_nano":1,"name":"x","type":"histogram","value":1.0,"service_name":"s","attributes":{},"resource_attributes":{}}"#;
        let err = serde_json::from_str::<Signal>(json).unwrap_err();
        assert!(err.to_string().contains("histogram") || err.to_string().contains("variant"));
    }

    #[test]
    fn version_mismatch_is_detected() {
        let log = LogSignal {
            contract_version: "2.0.0".to_string(),
            time_unix_nano: 1,
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "s".to_string(),
            body: "b".to_string(),
            trace_id: None,
            span_id: None,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(
            log.validate(),
            Err(ContractError::VersionMismatch {
                expected: "1.0.0".to_string(),
                got: "2.0.0".to_string(),
            })
        );
    }

    #[test]
    fn missing_required_resource_key_is_detected() {
        let log = LogSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: 1,
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "s".to_string(),
            body: "b".to_string(),
            trace_id: None,
            span_id: None,
            attributes: HashMap::new(),
            resource_attributes: HashMap::new(),
        };
        match log.validate() {
            Err(ContractError::MissingResourceKey(_)) => {}
            other => panic!("expected MissingResourceKey, got {:?}", other),
        }
    }

    #[test]
    fn invalid_trace_id_is_detected() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "BADID".to_string(),
            span_id: "0123456789abcdef".to_string(),
            parent_span_id: None,
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: 1,
            end_unix_nano: 2,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert!(matches!(
            span.validate(),
            Err(ContractError::InvalidTraceId(_))
        ));
    }

    #[test]
    fn span_interval_must_be_monotonic() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "0".repeat(32),
            span_id: "0".repeat(16),
            parent_span_id: None,
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: 100,
            end_unix_nano: 50,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert!(matches!(
            span.validate(),
            Err(ContractError::InvalidSpanInterval { .. })
        ));
    }

    // --- Day-2: negative / edge-case tests ---

    // `is_semver` requires exactly X.Y.Z with digit-only parts, checked before
    // the version-equality comparison. "v1.0.0" and "1.0" fail the format test;
    // "2.0.0" is well-formed so it reaches VersionMismatch (already covered).
    #[test]
    fn invalid_semver_is_detected() {
        for bad_version in &["1.0", "v1.0.0", "1.0.x", "1..0", ""] {
            let log = LogSignal {
                contract_version: (*bad_version).to_string(),
                time_unix_nano: 1,
                severity_text: "INFO".to_string(),
                severity_number: 9,
                service_name: "s".to_string(),
                body: "b".to_string(),
                trace_id: None,
                span_id: None,
                attributes: HashMap::new(),
                resource_attributes: req_attrs(),
            };
            assert!(
                matches!(log.validate(), Err(ContractError::InvalidSemver(_))),
                "expected InvalidSemver for contract_version = {:?}",
                bad_version
            );
        }
    }

    // service_name is checked after contract_version, so version must be valid.
    #[test]
    fn empty_service_name_is_detected() {
        let log = LogSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: 1,
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "".to_string(),
            body: "b".to_string(),
            trace_id: None,
            span_id: None,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(log.validate(), Err(ContractError::EmptyServiceName));
    }

    // timestamp check is third in Log's ordering, so version + service_name must be valid.
    #[test]
    fn negative_timestamp_is_detected_log() {
        let log = LogSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: -1,
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "s".to_string(),
            body: "b".to_string(),
            trace_id: None,
            span_id: None,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(log.validate(), Err(ContractError::NegativeTimestamp(-1)));
    }

    // Metric has its own validate() path; NegativeTimestamp must be covered there too.
    #[test]
    fn negative_timestamp_is_detected_metric() {
        let metric = MetricSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: -1,
            name: "latency".to_string(),
            metric_type: MetricType::Gauge,
            value: 1.0,
            service_name: "s".to_string(),
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(metric.validate(), Err(ContractError::NegativeTimestamp(-1)));
    }

    // Span uses start_unix_nano for the NegativeTimestamp guard (not time_unix_nano).
    #[test]
    fn negative_start_is_detected_span() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "0".repeat(32),
            span_id: "0".repeat(16),
            parent_span_id: None,
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: -1,
            end_unix_nano: 1,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(span.validate(), Err(ContractError::NegativeTimestamp(-1)));
    }

    // trace_id must be valid (32 lowercase hex) so validation reaches the span_id check.
    #[test]
    fn invalid_span_id_is_detected() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "a".repeat(32),
            span_id: "xyz".to_string(), // wrong length + non-hex
            parent_span_id: None,
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: 1,
            end_unix_nano: 2,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert!(matches!(
            span.validate(),
            Err(ContractError::InvalidSpanId(_))
        ));
    }

    // parent_span_id is a separate branch from span_id; both must be covered.
    // trace_id + span_id are valid here so validation reaches the parent check.
    #[test]
    fn invalid_parent_span_id_is_detected() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "a".repeat(32),
            span_id: "a".repeat(16),
            parent_span_id: Some("BADPARENT".to_string()),
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: 1,
            end_unix_nano: 2,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert!(matches!(
            span.validate(),
            Err(ContractError::InvalidSpanId(_))
        ));
    }

    // name is checked fourth in Metric's ordering; version, service_name, and
    // timestamp must all be valid to reach this guard.
    #[test]
    fn empty_metric_name_is_detected() {
        let metric = MetricSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: 1,
            name: "".to_string(),
            metric_type: MetricType::Sum,
            value: 0.0,
            service_name: "s".to_string(),
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(metric.validate(), Err(ContractError::EmptyMetricName));
    }

    // --- Boundary / positive tests ---

    // The rule is end < start → error; equal timestamps must succeed (zero-duration spans
    // are valid in OTLP, e.g. point-in-time events).
    #[test]
    fn span_with_equal_start_and_end_is_valid() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "a".repeat(32),
            span_id: "a".repeat(16),
            parent_span_id: None,
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: 100,
            end_unix_nano: 100,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(span.validate(), Ok(()));
    }

    // time_unix_nano == 0 is valid (epoch origin); the constraint is strictly < 0.
    #[test]
    fn zero_timestamp_is_valid() {
        let log = LogSignal {
            contract_version: "1.0.0".to_string(),
            time_unix_nano: 0,
            severity_text: "INFO".to_string(),
            severity_number: 9,
            service_name: "s".to_string(),
            body: "b".to_string(),
            trace_id: None,
            span_id: None,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(log.validate(), Ok(()));
    }

    // The schema's lowercase-only pattern is deliberate (contract review N4).
    // Uppercase hex is structurally plausible but must be rejected.
    #[test]
    fn uppercase_hex_trace_id_is_rejected() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "A".repeat(32), // correct length, valid hex digits — but uppercase
            span_id: "a".repeat(16),
            parent_span_id: None,
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: 1,
            end_unix_nano: 2,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert!(matches!(
            span.validate(),
            Err(ContractError::InvalidTraceId(_))
        ));
    }

    // Positive partner to the hex-rejection tests: exact-length lowercase hex
    // IDs must be accepted without error.
    #[test]
    fn exact_length_lowercase_hex_ids_are_valid() {
        let span = SpanSignal {
            contract_version: "1.0.0".to_string(),
            trace_id: "0123456789abcdef".repeat(2), // 32 chars
            span_id: "0123456789abcdef".to_string(), // 16 chars
            parent_span_id: None,
            name: "n".to_string(),
            service_name: "s".to_string(),
            start_unix_nano: 1,
            end_unix_nano: 2,
            status_code: StatusCode::Ok,
            attributes: HashMap::new(),
            resource_attributes: req_attrs(),
        };
        assert_eq!(span.validate(), Ok(()));
    }

    // Off-by-one on trace_id length: 31 or 33 chars of otherwise valid lowercase hex
    // must fail even though every character is individually legal.
    #[test]
    fn trace_id_wrong_length_is_rejected() {
        for bad_id in &[
            "a".repeat(31), // one short
            "a".repeat(33), // one long
        ] {
            let span = SpanSignal {
                contract_version: "1.0.0".to_string(),
                trace_id: bad_id.clone(),
                span_id: "a".repeat(16),
                parent_span_id: None,
                name: "n".to_string(),
                service_name: "s".to_string(),
                start_unix_nano: 1,
                end_unix_nano: 2,
                status_code: StatusCode::Ok,
                attributes: HashMap::new(),
                resource_attributes: req_attrs(),
            };
            assert!(
                matches!(span.validate(), Err(ContractError::InvalidTraceId(_))),
                "expected InvalidTraceId for trace_id of length {}",
                bad_id.len()
            );
        }
    }
}
