//! ClickHouse round-trip integration test — file-mode golden fixture → bronze.
//!
//! Proves the Rust collector parses Pod 1's golden fixture and lands it in the
//! official POD 3 bronze schema (`sentinel.*`).
//!
//! # How to run
//!
//! 1. Start ClickHouse with the bronze schema auto-applied. From
//!    `services/collector-rust/`:
//!
//!    ```sh
//!    docker compose -f infra/docker-compose.yml up -d
//!    # wait for the healthcheck to pass (~10 s)
//!    ```
//!
//! 2. Run the ignored test:
//!
//!    ```sh
//!    cd services/collector-rust
//!    CLICKHOUSE_URL=http://localhost:8123 cargo test --test clickhouse_roundtrip -- --ignored
//!    ```
//!
//! # Environment variables
//!
//! - `CLICKHOUSE_URL` — defaults to `http://localhost:8123` if unset. The database
//!   is fixed to `sentinel` (the bronze database).
//!
//! # Why one combined test (not several)
//!
//! All scenarios share the same external resource (the live ClickHouse tables) and
//! each starts by truncating. `cargo test` runs test fns in PARALLEL by default, so
//! multiple tests truncating + inserting into the same tables would race. The
//! scenarios are folded into a single sequential test.
//!
//! # Why tests are `#[ignore]`d
//!
//! This test requires a live ClickHouse instance. The `#[ignore]` attribute
//! excludes it from `cargo test` (the gate the parent checks) while keeping it
//! runnable on demand via `-- --ignored`.

// Tests are allowed to unwrap/expect — failing fast with a diagnostic is the
// whole point. Production code is governed by `unwrap_used = deny` in Cargo.toml.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;

use sentinel_collector::clickhouse_exporter::{
    build_client_with_database, url_from_env, DEFAULT_CLICKHOUSE_URL,
};

/// Resolve the path to the golden fixture from the crate's manifest directory.
/// Tests run from `services/collector-rust/`; the fixture lives two levels up.
fn golden_path() -> PathBuf {
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.push("..");
    p.push("..");
    p.push("contracts");
    p.push("v1");
    p.push("golden");
    p.push("baseline_seed42.jsonl");
    p
}

/// A ClickHouse client targeting the bronze `sentinel` database.
fn bronze_client() -> clickhouse::Client {
    let url = url_from_env().unwrap_or_else(|| DEFAULT_CLICKHOUSE_URL.to_string());
    build_client_with_database(&url, "sentinel")
}

/// Truncate the bronze tables the collector writes, for idempotent re-runs.
async fn truncate_tables(client: &clickhouse::Client) {
    for table in &[
        "otel_logs",
        "otel_traces",
        "otel_metrics_gauge",
        "otel_metrics_sum",
    ] {
        client
            .query(&format!("TRUNCATE TABLE IF EXISTS {table}"))
            .execute()
            .await
            .unwrap_or_else(|e| panic!("failed to truncate {table}: {e}"));
    }
}

/// Relax the 30-day TTL on the bronze tables so the 2023-dated golden rows are not
/// purged before we count them.
///
/// The golden fixture (`baseline_seed42.jsonl`) is timestamped 2023-11-14 — ~2.5
/// years before now — so under the bronze 30-day TTL the rows are eligible for
/// purging on the next background merge (the tables set `ttl_only_drop_parts = 1`).
/// We push the TTL out ~100 years for the test session; production TTL is
/// unaffected. `MODIFY TTL` is idempotent, so re-running the suite is safe.
async fn relax_ttl(client: &clickhouse::Client) {
    for (table, ttl) in [
        ("otel_logs", "TimestampTime + INTERVAL 100 YEAR"),
        ("otel_traces", "toDateTime(Timestamp) + INTERVAL 100 YEAR"),
        (
            "otel_metrics_gauge",
            "toDateTime(TimeUnix) + INTERVAL 100 YEAR",
        ),
        (
            "otel_metrics_sum",
            "toDateTime(TimeUnix) + INTERVAL 100 YEAR",
        ),
    ] {
        client
            .query(&format!("ALTER TABLE {table} MODIFY TTL {ttl}"))
            .execute()
            .await
            .unwrap_or_else(|e| panic!("failed to relax TTL on {table}: {e}"));
    }
}

/// Read a scalar `u64` from a single-column, single-row SELECT.
async fn count_rows(client: &clickhouse::Client, table: &str) -> u64 {
    client
        .query(&format!("SELECT count() FROM {table}"))
        .fetch_one::<u64>()
        .await
        .unwrap_or_else(|e| panic!("count() on {table} failed: {e}"))
}

// ─────────────────────────────────────────────────────────────────────────────

/// End-to-end round-trip into the bronze schema, run as a single sequential
/// scenario (see the module-level note on why this is one test, not several).
///
/// Phase A — parse the golden fixture, export to bronze, verify per-table counts.
/// Phase B — export a second time and verify the append-only MergeTree doubles the
/// row count (documents the no-deduplication semantics).
///
/// Expected counts from Pod 1's published golden distribution (2026-06-01):
///   - `otel_logs`:   48 rows
///   - `otel_traces`: 48 rows
///   - metrics:       183 rows, split across `otel_metrics_gauge` + `otel_metrics_sum`
///
/// Note: the 2023-dated golden rows are not purged during the test window — bronze
/// TTL only fires on background merges, which this test does not trigger.
#[ignore]
#[tokio::test]
async fn golden_fixture_round_trip() {
    let client = bronze_client();

    // Start from a clean slate so re-running the suite does not accumulate rows,
    // then relax the 30-day TTL so the 2023-dated golden rows survive (see relax_ttl).
    truncate_tables(&client).await;
    relax_ttl(&client).await;

    // ── Phase A: single export → exact counts ────────────────────────────────

    let counts = sentinel_collector::run_and_export(&golden_path(), &client)
        .await
        .expect("run_and_export must succeed against a live ClickHouse");

    assert_eq!(
        counts.parse_errors, 0,
        "golden file should have zero parse errors"
    );
    assert_eq!(
        counts.validation_errors, 0,
        "golden file should have zero validation errors"
    );

    let log_count = count_rows(&client, "otel_logs").await;
    let trace_count = count_rows(&client, "otel_traces").await;
    let gauge_count = count_rows(&client, "otel_metrics_gauge").await;
    let sum_count = count_rows(&client, "otel_metrics_sum").await;

    assert_eq!(log_count, 48, "otel_logs must contain exactly 48 rows");
    assert_eq!(trace_count, 48, "otel_traces must contain exactly 48 rows");
    assert_eq!(
        gauge_count + sum_count,
        183,
        "gauge + sum metrics must total exactly 183 rows"
    );

    // ── Phase B: second export doubles the rows (append-only, no dedup) ───────
    //
    // The tables use plain MergeTree with no deduplication key, so re-exporting
    // the same data doubles the row count. This is the expected semantics, NOT a
    // bug. If idempotent re-delivery is added later (ReplacingMergeTree + a
    // version key), update this assertion to expect 48.

    sentinel_collector::run_and_export(&golden_path(), &client)
        .await
        .expect("second export must succeed");

    let log_count_after = count_rows(&client, "otel_logs").await;
    assert_eq!(
        log_count_after, 96,
        "two exports must produce 2×48=96 log rows (MergeTree does not deduplicate)"
    );
}
