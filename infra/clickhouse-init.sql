-- Root orchestrator ClickHouse bootstrap (docker-entrypoint-initdb.d).
--
-- Creates the `otelgen` user + `bronze` database that the Go collector expects
-- (CLICKHOUSE_DSN = clickhouse://otelgen:otelgen_secret@clickhouse:9000/bronze),
-- WITHOUT touching the passwordless `default` user that the Rust collector uses
-- over HTTP :8123. This is orchestration glue only — it creates a user/database,
-- not table schemas. The bronze table DDL is owned by init.d/01-bronze-otel.sql.

CREATE DATABASE IF NOT EXISTS bronze;

CREATE USER IF NOT EXISTS otelgen IDENTIFIED WITH plaintext_password BY 'otelgen_secret';
GRANT ALL ON bronze.*  TO otelgen;
GRANT ALL ON default.* TO otelgen;
