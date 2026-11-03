#!/usr/bin/env bash
#
# REQ-D-12 — every silver MV body is deterministic, except one named exception.
#
# A non-deterministic body cannot be backfilled or content-checksummed: re-running
# it produces different rows, so REQ-E-03's row-identical guarantee and REQ-E-11's
# checksum both become meaningless for that object.
#
# `call_edges_1m_rmv` is the single exception and it is excluded BY NAME, not by
# pattern. It references `now()` because a call edge joins a child span to its
# parent across insert blocks, which an incremental MV cannot see, so it is a
# refreshable MV over a trailing window. It needs no backfill — each refresh
# recomputes from scratch, which is also its rollback.
#
# Numbered 07: the ticket (T29) asked for 06, which is already
# 06-initd-matches-migrations.sh from T16.
#
# Comments are stripped before matching. A comment that says "this body references
# now()" is documentation of the property, not a violation of it — and the
# migration's header says exactly that about the exception.

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
MIGRATIONS="$ROOT/infra/clickhouse/migrations"

#: The single named exception (REQ-D-12).
EXCEPTION="call_edges_1m_rmv"

#: Functions whose value depends on when, where or in what order a query runs.
NONDETERMINISTIC='now|now64|today|yesterday|rand|randCanonical|generateUUIDv4|generateUUID|hostName|currentDatabase|uptime|_part'

rc=0
checked=0

if [[ ! -d "$MIGRATIONS" ]]; then
    echo "missing: infra/clickhouse/migrations"
    exit 1
fi

shopt -s nullglob
for file in "$MIGRATIONS"/*.sql; do
    rel="${file#"$ROOT"/}"

    # Strip `--` comments and blank lines, then split the file into one record per
    # statement so a hit can be attributed to the object that owns it.
    statements="$(sed 's/--.*$//' "$file" | tr '\n' ' ' | tr ';' '\n')"

    while IFS= read -r stmt; do
        case "$stmt" in
            *"CREATE MATERIALIZED VIEW"*) ;;
            *) continue ;;
        esac
        checked=$((checked + 1))

        name="$(printf '%s' "$stmt" |
            sed -nE 's/.*CREATE MATERIALIZED VIEW( IF NOT EXISTS)? ([A-Za-z0-9_.]+).*/\2/p' |
            head -1)"
        name="${name##*.}"

        if ! hits="$(printf '%s' "$stmt" | grep -oE "\\b(${NONDETERMINISTIC})\\b" | sort -u | tr '\n' ' ')"; then
            hits=""
        fi
        [[ -z "${hits// /}" ]] && continue

        if [[ "$name" == "$EXCEPTION" ]]; then
            echo "note: $name references ${hits% } — the one exception REQ-D-12 names"
            continue
        fi

        echo "$rel: materialized view '$name' is non-deterministic (${hits% })"
        echo "  REQ-D-12 allows exactly one such object, $EXCEPTION, and this is not it."
        echo "  A non-deterministic body cannot be backfilled or content-checksummed."
        rc=1
    done <<<"$statements"
done

if [[ "$checked" -eq 0 ]]; then
    echo "no CREATE MATERIALIZED VIEW statements found in migrations/ — the grep is not matching"
    exit 1
fi

[[ "$rc" -eq 0 ]] && echo "$checked silver MV bodies deterministic, except $EXCEPTION as REQ-D-12 names"
exit "$rc"
