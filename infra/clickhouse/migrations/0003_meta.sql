-- 0003_meta.sql — the migration ledger and the backfill ledger (SPEC §6.2).
--
-- `migrate.sh` bootstraps `_meta.schema_migrations` itself before reading any
-- file: it cannot record a migration into a table the migration has not created
-- yet. Both definitions are `IF NOT EXISTS` and identical, so 0003 records
-- itself through the runner like any other file.

CREATE DATABASE IF NOT EXISTS _meta;

-- Three absences are deliberate and must survive future tidying: no PARTITION BY
-- (tens of rows for the project's lifetime), no TTL (an audit record that expires
-- cannot answer "when did 0005 land"), and ORDER BY version alone — admitting
-- applied_at to the key would permit two rows per version and turn the runner's
-- checksum refusal into a no-op.
CREATE TABLE IF NOT EXISTS _meta.schema_migrations
(
    `version`     String,
    `filename`    String,
    `checksum`    FixedString(64),
    `applied_at`  DateTime DEFAULT now(),
    `applied_by`  LowCardinality(String),
    `duration_ms` UInt32,
    `runner_host` LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY version;

-- The backfill runner's own state: REQ-E-04's phase gate, REQ-D-10's ledger gate
-- and REQ-E-11's checksum evidence. `status = 'refused'` is recorded rather than
-- only logged: REQ-E-12's refusal of a live partition must leave a trace.
CREATE TABLE IF NOT EXISTS _meta.backfill_runs
(
    `run_id`              String,
    `phase`               Enum8('phase1' = 1, 'phase2' = 2),
    `target_table`        LowCardinality(String),
    `partition_id`        String,
    `bronze_rows_before`  UInt64,
    `bronze_rows_after`   UInt64,
    `silver_rows_written` UInt64,
    `content_hash`        UInt64,
    `expected_hash`       UInt64,
    `started_at`          DateTime,
    `finished_at`         DateTime,
    `status`              Enum8('running' = 1, 'ok' = 2, 'failed' = 3, 'refused' = 4)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (target_table, partition_id, started_at);
