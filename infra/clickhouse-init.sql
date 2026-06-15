-- Root orchestrator ClickHouse bootstrap (docker-entrypoint-initdb.d).
--
-- Creates the `otelgen` user + `sentinel` database that the Go collector expects
-- (CLICKHOUSE_DSN = clickhouse://otelgen:otelgen_secret@clickhouse:9000/sentinel),
-- WITHOUT touching the passwordless `default` user that the Rust collector uses
-- over HTTP :8123. This is orchestration glue only — it creates a user/database,
-- not table schemas. Each collector still owns its own DDL (applied via `make init`).

CREATE DATABASE IF NOT EXISTS sentinel;

CREATE USER IF NOT EXISTS otelgen IDENTIFIED WITH plaintext_password BY 'otelgen_secret';
GRANT ALL ON sentinel.* TO otelgen;
GRANT ALL ON default.*  TO otelgen;
