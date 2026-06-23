//! Integration test: parse every line of Pod 1's golden fixture against the
//! `Signal` enum and verify the counts match Pod 1's published distribution.
//!
//! Per the python-developer agent's mapping report (2026-06-01) and a direct
//! count of `contract/golden/baseline_seed42.jsonl`:
//!
//!   48 spans + 48 logs + 183 metrics = 279 records total
//!
//! Any divergence here means either:
//!   (a) Pod 1 changed the golden fixture (re-run `/day-1-rust` to refresh)
//!   (b) Our `Signal` enum drifted from Pod 1's contract (fix `contract.rs`)
//!   (c) Pod 1 bumped `contract_version` (open a contract-migration PR)

// Tests are explicitly allowed to unwrap/expect — production code is governed
// by `unwrap_used = deny` in Cargo.toml.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;

/// Resolve the path to the golden file from the crate's manifest dir. Tests
/// run from `services/collector-rust/`, the golden lives at the repo
/// root under `contracts/generator/v1/golden/` (the monorepo contract SSOT).
fn golden_path() -> PathBuf {
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.push("..");
    p.push("..");
    p.push("contracts");
    p.push("generator");
    p.push("v1");
    p.push("golden");
    p.push("baseline_seed42.jsonl");
    p
}

#[test]
fn golden_file_exists_and_is_non_empty() {
    let p = golden_path();
    assert!(p.exists(), "golden file missing at {}", p.display());
    let meta = std::fs::metadata(&p).expect("metadata");
    assert!(meta.len() > 0, "golden file is empty");
}

#[test]
fn every_line_parses_into_a_signal() {
    // We use the binary crate's `run()` to exercise the full parse + validate
    // pipeline against the real fixture. A non-trivial smoke that the wire
    // contract and our `Signal` enum agree.
    let counts = sentinel_collector::run(&golden_path()).expect("run");

    assert_eq!(
        counts.parse_errors, 0,
        "expected zero parse errors, got {}",
        counts.parse_errors
    );
    assert_eq!(
        counts.validation_errors, 0,
        "expected zero validation errors, got {}",
        counts.validation_errors
    );
    assert!(counts.total_ok() > 0, "no records parsed");
}

#[test]
fn golden_distribution_matches_pod1_published() {
    let counts = sentinel_collector::run(&golden_path()).expect("run");

    // Counts from a direct `jq` over baseline_seed42.jsonl on 2026-06-01.
    // If Pod 1 regenerates the golden file with a different seed or scenario,
    // these numbers update — but the test failing tells us to look.
    assert_eq!(counts.spans, 48, "span count drift vs Pod 1 golden");
    assert_eq!(counts.logs, 48, "log count drift vs Pod 1 golden");
    assert_eq!(counts.metrics, 183, "metric count drift vs Pod 1 golden");
    assert_eq!(counts.total_ok(), 279, "total record count drift");
}
