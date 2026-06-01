//! ClickHouse round-trip integration test — requires a running ClickHouse instance.
//!
//! # How to run
//!
//! 1. Start ClickHouse. The compose file mounts `infra/clickhouse/ddl/` into
//!    `/docker-entrypoint-initdb.d`, so the schema is auto-applied on first boot
//!    — no manual `clickhouse-client < …` steps needed:
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
//! - `CLICKHOUSE_URL` — defaults to `http://localhost:8123` if unset.
//!
//! # Why one combined test (not several)
//!
//! All scenarios share the same external resource (the live ClickHouse tables)
//! and each starts by truncating. `cargo test` runs test fns in PARALLEL by
//! default, so multiple tests truncating + inserting into the same tables would
//! race (48 + 48 = 96 logs, etc.). Rather than depend on `--test-threads=1`
//! being remembered, the scenarios are folded into a single sequential test.
//!
//! # Why tests are `#[ignore]`d
//!
//! This test requires a live ClickHouse instance. Running it in CI without
//! Docker Compose available would cause spurious failures. The `#[ignore]`
//! attribute excludes it from `cargo test` (the gate the parent checks) while
//! keeping it runnable on demand via `-- --ignored`.

// Tests are allowed to unwrap/expect — failing fast with a diagnostic is the
// whole point. Production code is governed by `unwrap_used = deny` in Cargo.toml.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;

/// Resolve the path to the golden fixture from the crate's manifest directory.
/// Tests run from `services/collector-rust/`; the fixture lives two levels up.
fn golden_path() -> PathBuf {
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.push("..");
    p.push("..");
    p.push("contract");
    p.push("golden");
    p.push("baseline_seed42.jsonl");
    p
}

/// Strip TTL on all three tables so the 2023-11-14-dated golden fixture is not
/// purged on the first background merge.
///
/// # Why this is necessary
///
/// The golden fixture (`baseline_seed42.jsonl`) is timestamped **2023-11-14**
/// — roughly 2.5 years before the current date. ClickHouse evaluates TTL
/// against *event time* (the `Timestamp` column), so any row with a timestamp
/// older than `NOW() - INTERVAL 30/90 DAY` is eligible for purging immediately
/// after the next background merge or `OPTIMIZE`. Inserting expired data makes
/// `count()` return the right number for a moment, then drop to 0 after the
/// first merge.
///
/// We extend the TTL to 100 years in the test session so we can `OPTIMIZE
/// FINAL` (to fire the materialized view) without losing the rows. The
/// production TTL is NOT changed — this only modifies the tables within the
/// test ClickHouse instance.
///
/// See `docs/research/clickhouse-schema-pod2.md` § "Day-4 gotcha: TTL vs. the
/// golden fixture's timestamp" for the full analysis.
async fn strip_ttl(client: &clickhouse::Client) {
    for table in &["otel_logs", "otel_traces", "otel_metrics"] {
        client
            .query(&format!(
                "ALTER TABLE {table} MODIFY TTL toDate(Timestamp) + INTERVAL 100 YEAR"
            ))
            .execute()
            .await
            .unwrap_or_else(|e| panic!("failed to strip TTL on {table}: {e}"));
    }
    // otel_metrics_1m inherits TTL via its own DDL — strip it too so OPTIMIZE
    // doesn't purge the MV rollup.
    client
        .query("ALTER TABLE otel_metrics_1m MODIFY TTL toDate(window_start) + INTERVAL 100 YEAR")
        .execute()
        .await
        .unwrap_or_else(|e| panic!("failed to strip TTL on otel_metrics_1m: {e}"));
}

/// Truncate all three signal tables and the rollup table.
///
/// Called at the start of each test for idempotency — re-running the test
/// suite on a live ClickHouse does not accumulate stale rows.
async fn truncate_tables(client: &clickhouse::Client) {
    for table in &[
        "otel_logs",
        "otel_traces",
        "otel_metrics",
        "otel_metrics_1m",
    ] {
        client
            .query(&format!("TRUNCATE TABLE IF EXISTS {table}"))
            .execute()
            .await
            .unwrap_or_else(|e| panic!("failed to truncate {table}: {e}"));
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

/// End-to-end round-trip, run as a single sequential scenario (see the
/// module-level note on why this is one test, not several).
///
/// Phase A — parse the golden fixture, export to ClickHouse, verify per-table
/// row counts and that the materialized view fired.
/// Phase B — export a second time and verify the append-only MergeTree doubles
/// the row count (documents the no-deduplication semantics).
///
/// Expected counts from Pod 1's published golden distribution (2026-06-01):
///   - `otel_logs`:    48 rows
///   - `otel_traces`:  48 rows
///   - `otel_metrics`: 183 rows
#[ignore]
#[tokio::test]
async fn golden_fixture_round_trip() {
    let client = sentinel_collector::clickhouse_exporter::client_from_env();

    // Start from a clean slate, then strip TTL so the 2023-dated golden rows
    // survive the OPTIMIZE FINAL below (see strip_ttl docs for the why).
    truncate_tables(&client).await;
    strip_ttl(&client).await;

    // ── Phase A: single export → exact counts + MV fired ─────────────────────

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
    let metric_count = count_rows(&client, "otel_metrics").await;

    assert_eq!(log_count, 48, "otel_logs must contain exactly 48 rows");
    assert_eq!(trace_count, 48, "otel_traces must contain exactly 48 rows");
    assert_eq!(
        metric_count, 183,
        "otel_metrics must contain exactly 183 rows"
    );

    // Force merge so the MV blocks are committed to otel_metrics_1m.
    // OPTIMIZE TABLE FINAL is safe in tests — we never call it in production.
    client
        .query("OPTIMIZE TABLE otel_metrics_1m FINAL")
        .execute()
        .await
        .expect("OPTIMIZE otel_metrics_1m must succeed");

    let mv_count = count_rows(&client, "otel_metrics_1m").await;
    assert!(
        mv_count > 0,
        "otel_metrics_1m must have at least one row after OPTIMIZE (MV must have fired on INSERT)"
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
