-- A generic, documented, read-only account for poking at the local stack by hand.
--
-- LOCAL DEVELOPMENT ONLY. The stack is loopback-bound with TLS deferred
-- (DEC-2026-10-06-local-scope, DEC-A4), and this login's password is a published
-- default (`SENTINEL_DEV_PASSWORD`, `.env.example`). It is not a deployment
-- credential: a managed ClickHouse should not run this migration with that
-- default, and the account can be removed with `DROP USER sentinel_dev_u`.
--
-- Why it exists: `default` is localhost-only inside the container (0002 deleted the
-- `::/0` override), and a browser or `curl` on the host reaches ClickHouse through
-- the Docker port mapping, so it arrives from the bridge gateway and `default` is
-- refused. The three service users could be borrowed, but their password is a
-- gitignored file nobody is meant to type, and each is attributable to one service
-- in `system.query_log`. This one is the account a human is meant to type into
-- ClickHouse Play (`/play`) or `clickhouse-client`.
--
-- Role `sentinel_dev`, user `sentinel_dev_u`: a role and a user cannot share a name,
-- and `_u` is the convention of 0002 and 0007.
--
-- EXPAND ONLY, and a new file rather than an edit to an applied migration: the
-- runner refuses a changed checksum with exit 3.
--
-- SELECT only, over what a person looks at: bronze, silver, and the two system
-- tables every other reader here already gets for table and column discovery.
-- Deliberately absent: any write, any DDL, ACCESS MANAGEMENT, and `system.parts`
-- (the backfill's partition authority, held by the migrator alone, 0002).
-- `readonly = 2` refuses every write and DDL statement but still lets Play and the
-- client attach their per-query settings, which `readonly = 1` rejects (same
-- reasoning as 0007); under 2 the user cannot lift the restriction itself.
--
-- The password arrives as `{dev_pw:String}` from `SENTINEL_DEV_PASSWORD`, which
-- `migrate.sh` prepends as `SET param_dev_pw` on stdin, never a literal here and
-- never on a command line. It is a separate parameter from `{pw:String}` because
-- it is a different secret: the service password stays in a gitignored file, this
-- one is meant to be known. `IF NOT EXISTS` means a changed
-- `SENTINEL_DEV_PASSWORD` does not rotate an existing user; use
-- `ALTER USER sentinel_dev_u IDENTIFIED WITH sha256_password BY '...'`.
CREATE ROLE IF NOT EXISTS sentinel_dev;
GRANT SELECT ON bronze.*       TO sentinel_dev;
GRANT SELECT ON silver.*       TO sentinel_dev;
GRANT SELECT ON system.tables  TO sentinel_dev;
GRANT SELECT ON system.columns TO sentinel_dev;

CREATE USER IF NOT EXISTS sentinel_dev_u IDENTIFIED WITH sha256_password BY {dev_pw:String}
  SETTINGS readonly = 2;
GRANT sentinel_dev TO sentinel_dev_u;
