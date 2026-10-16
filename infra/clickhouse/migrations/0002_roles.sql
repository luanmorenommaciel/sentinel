-- Least-privilege ClickHouse roles and users (SPEC §14.1, REQ-H-03, REQ-H-04).
--
-- A migration, not an init script, so it applies identically to a local volume
-- and to a managed instance where `docker-entrypoint-initdb.d` does not exist
-- (SPEC §12.2).
--
-- EXPAND ONLY (T17). These roles and users are created *beside* the untouched
-- passwordless `default`, so nothing changes posture and nothing breaks.
-- T19 added the user drop at the bottom and deleted the `::/0` network override
-- in the same pull request this file first ships in. That ordering matters: once a
-- migration has been applied anywhere, it is append-only and the runner refuses a
-- changed checksum with exit 3. Editing this file was only safe because T17 and
-- T19 land together and it had never run outside a throwaway container. A later
-- change to this posture needs a new migration, not an edit here.
--
-- The password arrives as the query parameter `{pw:String}`, never as a literal:
-- migration files are in git. `migrate.sh` reads it from a mounted secret file
-- and prepends `SET param_pw` to this file's statement stream, so the value
-- travels on **stdin** and never on a command line — `ps` shows an argv to every
-- user on the box, which is the same reason the runner keeps the connection
-- password out of `CH_CLIENT`.
--
-- Roles first, users second: the role is the reviewable artifact and it survives
-- a credential rotation.

-- ── the collector writes bronze, and must also read it ─────────────────────
-- DS-09 says the collector issues no DDL and reads nothing back, and SPEC §14.1
-- grants it INSERT alone on that basis — while stating that the list "is
-- explicitly not asserted to be complete" and that REQ-H-06 makes the live job
-- the oracle.
--
-- The oracle ran on 2026-10-06 and INSERT alone is not enough. With INSERT only,
-- every export failed:
--
--   Code: 497 … sentinel_collector_u: Not enough privileges. To execute this
--   query, it's necessary to have the grant SELECT(TraceId, Timestamp) ON
--   bronze.otel_traces. (ACCESS_DENIED)
--
-- The `clickhouse` Rust crate reads the target's column types before streaming
-- RowBinary, so SELECT on the inserted columns is a hard requirement of the
-- client, not a convenience. Granted at database scope rather than enumerating
-- every column of nine tables, which would be unmaintainable and would break on
-- the next DDL change.
--
-- This is a real widening of the collector's privilege over what §14.1 drafted,
-- and it is recorded here rather than quietly applied: the collector can now read
-- bronze. It still cannot write silver, touch `system.parts`, or issue any DDL.
CREATE ROLE IF NOT EXISTS sentinel_collector;
GRANT INSERT ON bronze.* TO sentinel_collector;
GRANT SELECT ON bronze.* TO sentinel_collector;

-- ── the reader reads bronze, silver, and two system tables ──────────────────
-- The `system.tables` / `system.columns` grants are NOT optional: flow-ui draws
-- the Silver box on the Flow board from them (`clickhouse.py:429, 503, 505`).
-- Omit them and the fourth box silently disappears, which reads as a design
-- choice rather than a missing grant.
CREATE ROLE IF NOT EXISTS sentinel_reader;
GRANT SELECT ON bronze.*       TO sentinel_reader;
GRANT SELECT ON silver.*       TO sentinel_reader;
GRANT SELECT ON system.tables  TO sentinel_reader;
GRANT SELECT ON system.columns TO sentinel_reader;

-- ── the migrator owns DDL, and is the only holder of system.parts ───────────
-- `system.parts` is the backfill's partition authority (§6.5) and it leaks the
-- shape of the data, so the reader does not get it.
CREATE ROLE IF NOT EXISTS sentinel_migrator;
GRANT CREATE DATABASE, CREATE TABLE, CREATE VIEW, ALTER, DROP, SELECT, INSERT
  ON bronze.* TO sentinel_migrator;
GRANT CREATE DATABASE, CREATE TABLE, CREATE VIEW, ALTER, DROP, SELECT, INSERT
  ON silver.* TO sentinel_migrator;
GRANT CREATE DATABASE, CREATE TABLE, SELECT, INSERT ON _meta.* TO sentinel_migrator;
GRANT SELECT ON system.parts TO sentinel_migrator;

-- ── users, one per role ─────────────────────────────────────────────────────
-- `sha256_password`, never the plaintext auth variant.
CREATE USER IF NOT EXISTS sentinel_collector_u IDENTIFIED WITH sha256_password BY {pw:String};
GRANT sentinel_collector TO sentinel_collector_u;

CREATE USER IF NOT EXISTS sentinel_reader_u IDENTIFIED WITH sha256_password BY {pw:String};
GRANT sentinel_reader TO sentinel_reader_u;

CREATE USER IF NOT EXISTS sentinel_migrator_u IDENTIFIED WITH sha256_password BY {pw:String};
GRANT sentinel_migrator TO sentinel_migrator_u;

-- ── contract step (T19, REQ-H-01) ───────────────────────────────────────────
-- The vestigial user carried a committed plaintext password and `ALL` on both
-- `bronze.*` and `default.*`. It existed for the Go collector's DSN, which went
-- with PR #28 on 2026-08-12; nothing has used it since. Dropped last so the
-- replacement roles above already exist when it goes.
DROP USER IF EXISTS otelgen;
