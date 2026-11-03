#!/usr/bin/env bash
#
# REQ-A-15 / REQ-A-05 — one source of DDL, two apply paths.
#
# `infra/clickhouse/migrations/` is the source. `init.d/` exists so the local
# stack keeps its zero-step `make up`, and its entries are **symlinks** into
# migrations/ rather than copies. That is the whole mechanism: a copy can drift,
# and a drifted copy means `make up` and `make migrate` build different schemas
# while both report success — the failure this assert exists to make impossible.
#
# Numbered 06, not the 05 the ticket (T16) asked for: 05 is already
# `05-flow-ui-is-read-only.sh`, landed with T01.
#
# Checked per entry rather than by diffing contents, because identical bytes are
# not the property. Two files that happen to match today can be edited apart
# tomorrow; a symlink cannot.

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
INITD="$ROOT/infra/clickhouse/init.d"
MIGRATIONS="$ROOT/infra/clickhouse/migrations"

rc=0
checked=0

if [[ ! -d "$INITD" ]]; then
    echo "missing: infra/clickhouse/init.d"
    exit 1
fi

shopt -s nullglob
for entry in "$INITD"/*.sql; do
    rel="${entry#"$ROOT"/}"
    checked=$((checked + 1))

    if [[ ! -L "$entry" ]]; then
        echo "$rel is a regular file; it must be a symlink into migrations/ (REQ-A-15)"
        rc=1
        continue
    fi

    target="$(readlink "$entry")"
    resolved="$(cd "$INITD" && cd "$(dirname "$target")" 2>/dev/null && pwd)/$(basename "$target")"

    if [[ ! -e "$resolved" ]]; then
        echo "$rel points at $target, which does not exist"
        rc=1
        continue
    fi

    case "$resolved" in
        "$MIGRATIONS"/*) ;;
        *)
            echo "$rel points outside migrations/: $target"
            rc=1
            continue
            ;;
    esac
done

if [[ "$checked" -eq 0 ]]; then
    echo "no *.sql entries in infra/clickhouse/init.d — the local stack would boot with no schema"
    exit 1
fi

# Every migration the boot path is expected to apply must be reachable through a
# symlink. `0002` (roles) and `0003` (the ledger) are deliberately NOT in init.d:
# roles need a password from a mounted file and the ledger bootstraps itself, so
# both are `make migrate`'s business only.
for want in 0001_bronze_otel.sql 0004_silver_layer.sql; do
    if [[ ! -e "$MIGRATIONS/$want" ]]; then
        echo "missing migration: infra/clickhouse/migrations/$want"
        rc=1
        continue
    fi
    if ! find "$INITD" -maxdepth 1 -type l -lname "*$want" | grep -q .; then
        echo "no init.d symlink resolves to $want, so \`make up\` would not apply it"
        rc=1
    fi
done

[[ "$rc" -eq 0 ]] && echo "init.d is $checked symlink(s) into migrations/; one DDL source, two apply paths"
exit "$rc"
