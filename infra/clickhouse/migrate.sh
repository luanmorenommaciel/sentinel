#!/usr/bin/env bash
#
# ClickHouse DDL migration runner (REQ-A-04, A-09, A-13, A-14, D-11).
#
# Applies `migrations/NNNN_*.sql` in filename order and records every applied
# version in `_meta.schema_migrations`, so "what schema is deployed?" is a
# SELECT rather than a `SHOW CREATE TABLE` safari.
#
# Bash + clickhouse-client, nothing else (NFR-11). The same mechanism
# `Makefile:72` already uses, and it needs no `docker-entrypoint-initdb.d` — which
# is the point: a managed ClickHouse has no init.d (spec §12.2).
#
# Usage
#   bash infra/clickhouse/migrate.sh [migrations_dir]
#
# The client command is injected, never guessed, because getting it wrong means
# migrating the wrong database:
#
#   CH_CLIENT="docker compose exec -T clickhouse clickhouse-client" …   # local stack
#   CH_CLIENT="clickhouse-client --host=ch.internal --secure \
#              --user=sentinel_migrator_u --password=$(cat /run/secrets/pw)" … # deployed
#
# `--multiquery` is passed by this script and is not optional: the 24.3 client
# rejects a multi-statement `-q` with `Code: 62` where 25.4 accepts it (measured,
# #46), and every migration file holds more than one statement.
#
# Idempotence lives in the LEDGER, not in the statements. That is what admits a
# `CREATE OR REPLACE VIEW` in a migration (REQ-D-11) — a statement that is not
# `IF NOT EXISTS`-shaped is still applied exactly once.
#
# Exit codes are part of the contract (spec §6.2):
#   0  every file applied or skipped
#   1  usage / environment error
#   2  cannot reach ClickHouse
#   3  a recorded file's checksum changed — migrations are append-only
#   4  a migration failed; nothing was recorded, so the next run retries it

set -uo pipefail

MIGRATIONS_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/migrations}"

# shellcheck disable=SC2206  # intentional word splitting: CH_CLIENT is a command line
CLIENT=(${CH_CLIENT:-clickhouse-client})
CLIENT+=(--multiquery)

log() { printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }

# Run SQL from stdin. Every statement in this runner goes through here, so there
# is one place the client is invoked and one place its args are set.
ch() { "${CLIENT[@]}"; }

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        err "migrate: neither sha256sum nor shasum is available"
        exit 1
    fi
}

# Milliseconds since the epoch. `date +%s%3N` is GNU-only and `date +%s` alone
# rounds every migration to 0 ms, which is the one value `duration_ms` must not
# always hold. Bash 5's EPOCHREALTIME is `seconds.microseconds` in the C locale
# and needs no external binary; pre-5 shells fall back to whole seconds.
now_ms() {
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        local whole="${EPOCHREALTIME%%[.,]*}"
        local frac="${EPOCHREALTIME#"$whole"}"
        frac="${frac#[.,]}"
        frac="${frac}000000"
        printf '%s%s' "$whole" "${frac:0:3}"
    else
        printf '%s000' "$(date +%s)"
    fi
}

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
    err "migrate: no migrations directory at $MIGRATIONS_DIR"
    exit 1
fi

# ── reachability (exit 2) ────────────────────────────────────────────────────
if ! probe="$(printf 'SELECT 1\n' | ch 2>&1)"; then
    err "migrate: cannot reach ClickHouse with '${CLIENT[*]}'"
    err "${probe}"
    exit 2
fi

# ── the ledger bootstraps itself (step 1) ────────────────────────────────────
# Migration 0003 declares `_meta` as well, and records itself through this
# runner; the two are byte-compatible because both are `IF NOT EXISTS`.
if ! out="$(ch <<'SQL' 2>&1
CREATE DATABASE IF NOT EXISTS _meta;
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
SQL
)"; then
    err "migrate: could not create the ledger"
    err "$out"
    exit 2
fi

# ── what is already recorded (step 2) ───────────────────────────────────────
if ! recorded="$(printf "SELECT version, checksum FROM _meta.schema_migrations FORMAT TSV\n" | ch 2>&1)"; then
    err "migrate: could not read _meta.schema_migrations"
    err "$recorded"
    exit 2
fi

recorded_checksum() {
    printf '%s\n' "$recorded" | awk -F'\t' -v v="$1" '$1 == v { print $2; exit }'
}

APPLIED_BY="${APPLIED_BY:-$(git -C "$MIGRATIONS_DIR" rev-parse HEAD 2>/dev/null || echo unknown)}"
RUNNER_HOST="$(hostname 2>/dev/null || echo unknown)"

applied=0
skipped=0

# ── apply in filename order (step 3) ────────────────────────────────────────
shopt -s nullglob
for file in "$MIGRATIONS_DIR"/[0-9][0-9][0-9][0-9]_*.sql; do
    filename="$(basename "$file")"
    version="${filename%%_*}"
    checksum="$(sha256 "$file")"
    prior="$(recorded_checksum "$version")"

    if [[ -n "$prior" ]]; then
        if [[ "$prior" == "$checksum" ]]; then
            log "already applied  $filename"
            skipped=$((skipped + 1))
            continue
        fi
        log "CHECKSUM DIVERGENCE  $filename"
        log "  recorded: $prior"
        log "  on disk:  $checksum"
        err "migrate: $filename changed after it was applied. Migrations are append-only —"
        err "          add a new migration instead of editing $filename. No further file attempted."
        exit 3
    fi

    log "applying         $filename"
    started="$(now_ms)"
    if ! out="$(ch < "$file" 2>&1)"; then
        err "migrate: $filename failed; nothing recorded, so the next run retries it"
        err "$out"
        exit 4
    fi
    duration_ms=$(( $(now_ms) - started ))
    # `duration_ms` is UInt32; a backwards clock would otherwise fail the INSERT.
    if (( duration_ms < 0 )); then
        duration_ms=0
    fi

    if ! out="$(printf "INSERT INTO _meta.schema_migrations (version, filename, checksum, applied_by, duration_ms, runner_host) VALUES ('%s', '%s', '%s', '%s', %d, '%s')\n" \
        "$version" "$filename" "$checksum" "$APPLIED_BY" "$duration_ms" "$RUNNER_HOST" | ch 2>&1)"; then
        err "migrate: $filename applied but the ledger row could not be written"
        err "$out"
        exit 4
    fi
    applied=$((applied + 1))
done

if [[ $((applied + skipped)) -eq 0 ]]; then
    err "migrate: no NNNN_*.sql files in $MIGRATIONS_DIR"
    exit 1
fi

log "migrate: $applied applied, $skipped already applied"
