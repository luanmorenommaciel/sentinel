-- Root orchestrator ClickHouse bootstrap (docker-entrypoint-initdb.d).
--
-- Creates the `bronze` database, and deliberately does NOT touch the passwordless
-- `default` user that the Rust collector uses over HTTP :8123.
--
-- The `otelgen` user below is VESTIGIAL: it existed for the Go collector's DSN
-- (clickhouse://otelgen:otelgen_secret@clickhouse:9000/bronze), and the Go collector was
-- removed in PR #28 (merged 2026-08-12). Nothing uses it today — safe to drop.
--
-- This is orchestration glue only — it creates a user/database, not table schemas.
-- The bronze table DDL is owned by init.d/01-bronze-otel.sql.

CREATE DATABASE IF NOT EXISTS bronze;

CREATE USER IF NOT EXISTS otelgen IDENTIFIED WITH plaintext_password BY 'otelgen_secret';
GRANT ALL ON bronze.*  TO otelgen;
GRANT ALL ON default.* TO otelgen;
