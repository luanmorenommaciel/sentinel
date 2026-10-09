//! Shared ClickHouse wiring for the `#[ignore]`d live integration tests.
//!
//! Exists because of what the first ever run of the `integration` job found
//! (run `37875017554`): every live test connected as `default` with no
//! credential, and `default` no longer answers.
//!
//! The cause is **network, not password**, and that is worth stating plainly
//! because the error message says the opposite. `clickhouse/clickhouse-server`
//! ships `/etc/clickhouse-server/users.d/default-user.xml`, which restricts
//! `default` to `::1` and `127.0.0.1` — *inside the container*. A `cargo test`
//! on the host reaches ClickHouse through Docker's published port, so the
//! connection arrives from the bridge gateway, matches no `<networks>` entry for
//! `default`, and ClickHouse reports the generic
//!
//!   Code: 194 … default: Authentication failed: password is incorrect, or
//!   there is no user with such name. (REQUIRED_PASSWORD)
//!
//! which reads as a wrong password for a user that is in fact simply not
//! reachable from here. Before T19 the repo mounted a `users.d` override opening
//! `::/0` for `default`; T19 deleted it (REQ-B-14) and nothing noticed, because
//! these tests had never run in CI. Verified locally against 25.4.13.22:
//! `clickhouse-client` *inside* the container answers `SELECT 1`, the identical
//! query from the host returns 194.
//!
//! So the fix is a user that is reachable and least-privileged, not a hole in
//! the network ACL: `0002_roles.sql` creates `sentinel_migrator_u` with no
//! `HOST` clause (hence `HOST ANY`) and the grants a schema-owning identity
//! should have. The job provisions it with the repo's own `migrate.sh`.
//!
//! The credential is a **file path**, never a value, matching SPEC §14.2 and the
//! collector's own `clickhouse.password_file` config key — which is what lets
//! `shutdown_signals.rs` hand the same credential to the collector process it
//! spawns, through the sanctioned config loader rather than a fourth env read.
//!
//! No `std::env::var` is added to `src/`: `clippy.toml` bans it there and
//! `plan/core-plan.md` names the only two sanctioned sites. The URL still comes
//! from `clickhouse_exporter::url_from_env()`, one of those two. Everything here
//! is test code, which `clippy.toml`'s own comment exempts.

#![allow(dead_code)] // each test file uses a subset; the rest is not dead overall

use std::path::PathBuf;

use sentinel_collector::clickhouse_exporter::{
    build_client_with_database, url_from_env, DEFAULT_CLICKHOUSE_URL,
};

/// The ClickHouse URL under test, from `CLICKHOUSE_URL` or the local default.
pub fn clickhouse_url() -> String {
    url_from_env().unwrap_or_else(|| DEFAULT_CLICKHOUSE_URL.to_string())
}

/// The user to authenticate as, when the environment names one.
///
/// Unset is a supported configuration and means "send no credential" — the
/// passwordless-`default` path a developer gets from a bare local container.
pub fn clickhouse_user() -> Option<String> {
    #[allow(clippy::disallowed_methods)]
    std::env::var("CLICKHOUSE_USER")
        .ok()
        .filter(|u| !u.is_empty())
}

/// The path of the file holding the password, when the environment names one.
///
/// A path and not a value, so a credential never lands in an argv or in a
/// process listing — the same reasoning `migrate.sh` records for
/// `MIGRATION_PW_FILE`.
pub fn clickhouse_password_file() -> Option<PathBuf> {
    #[allow(clippy::disallowed_methods)]
    std::env::var("CLICKHOUSE_PASSWORD_FILE")
        .ok()
        .filter(|p| !p.is_empty())
        .map(PathBuf::from)
}

/// Read the password out of `CLICKHOUSE_PASSWORD_FILE`, trimming the trailing
/// newline a `>` redirect or an editor leaves behind.
///
/// Panics with the path when the file is named but unreadable: a silent fallback
/// to "no credential" would turn a misconfigured job into a 194 three steps
/// later, which is the exact confusion this module exists to end.
pub fn clickhouse_password() -> Option<String> {
    clickhouse_password_file().map(|path| {
        let raw = std::fs::read_to_string(&path).unwrap_or_else(|e| {
            panic!(
                "cannot read CLICKHOUSE_PASSWORD_FILE {}: {e}",
                path.display()
            )
        });
        raw.trim_end_matches(['\n', '\r']).to_string()
    })
}

/// A client for `database`, carrying the environment's credential when there is
/// one.
pub fn client(database: &str) -> clickhouse::Client {
    let mut client = build_client_with_database(&clickhouse_url(), database);
    if let Some(user) = clickhouse_user() {
        client = client.with_user(user);
    }
    if let Some(password) = clickhouse_password() {
        client = client.with_password(password);
    }
    client
}

/// The `clickhouse:` YAML block for a collector process under test, including
/// `user` / `password_file` when the environment supplies them.
///
/// Built here rather than in the test so the spawned collector authenticates the
/// same way the verifying client does; a mismatch would show up as a flush that
/// silently wrote nothing.
pub fn clickhouse_config_block(url: &str, database: &str, extra: &str) -> String {
    let mut block = format!("clickhouse:\n  url: '{url}'\n  database: {database}\n{extra}");
    if let Some(user) = clickhouse_user() {
        block.push_str(&format!("  user: '{user}'\n"));
    }
    if let Some(path) = clickhouse_password_file() {
        block.push_str(&format!("  password_file: '{}'\n", path.display()));
    }
    block
}
