-- HyperDX read-only role and user (ADR-0011).
--
-- EXPAND ONLY, and a new file rather than an edit to 0002: once a migration has
-- been applied anywhere the runner refuses a changed checksum with exit 3, so a
-- grant added for a new reader is a new migration.
--
-- HyperDX is a second read-layer UI beside flow-ui. It gets its own role and user
-- instead of borrowing `sentinel_reader_u` so that its queries are attributable in
-- `system.query_log`, its grants can change without moving flow-ui's, and revoking
-- the UI is a single DROP USER.
--
-- SELECT only. HyperDX never writes to ClickHouse in this stack: ingestion stays
-- with collector-rust, and the metadata-rollup materialized views HyperDX can
-- offer to create (`metadataMaterializedViews`) are not configured, so it needs no
-- DDL privilege. `system.tables` / `system.columns` are what it reads to list
-- tables and infer column types when a source is edited in the UI.
--
-- `readonly = 2` is the profile HyperDX needs: it forwards per-query settings
-- (result limits, date-time output format) and `readonly = 1` rejects any setting
-- change, while 2 still refuses every write and every DDL statement. The
-- constraint is on the user, not the role, because settings belong to the login.
--
-- The password arrives as `{pw:String}` from the same mounted secret file as the
-- other three users (see 0002 and migrate.sh); it is never a literal here.
CREATE ROLE IF NOT EXISTS sentinel_hyperdx;
GRANT SELECT ON bronze.*       TO sentinel_hyperdx;
GRANT SELECT ON silver.*       TO sentinel_hyperdx;
GRANT SELECT ON system.tables  TO sentinel_hyperdx;
GRANT SELECT ON system.columns TO sentinel_hyperdx;

CREATE USER IF NOT EXISTS sentinel_hyperdx_u IDENTIFIED WITH sha256_password BY {pw:String}
  SETTINGS readonly = 2;
GRANT sentinel_hyperdx TO sentinel_hyperdx_u;
