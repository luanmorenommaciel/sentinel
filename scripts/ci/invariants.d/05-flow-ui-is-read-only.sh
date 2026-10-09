#!/usr/bin/env bash
#
# REQ-E-08 — flow-ui reads and never writes.
#
# Nothing in the pipeline depends on flow-ui being up, and the backfill is not a
# flow-ui responsibility. The guarantee is cheap to keep and expensive to notice
# the loss of, so it is asserted rather than documented.
#
# Holds today: `grep -rn "INSERT\|ALTER TABLE\|CREATE TABLE"
# services/flow-ui/src/flow_ui/` has no hits.

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
SRC="$ROOT/services/flow-ui/src/flow_ui"

if [[ ! -d "$SRC" ]]; then
    echo "missing: services/flow-ui/src/flow_ui"
    exit 1
fi

# Scoped to the Python sources: every ClickHouse read in flow-ui goes through
# `ClickHouse._query`, and the browser asset under static/ cannot reach ClickHouse
# at all (neither ClickHouse nor the collector sets a CORS header), so a write
# could only originate in Python. SQL keywords are written uppercase throughout
# this repo's query strings, so a case-sensitive match avoids flagging English
# prose in a docstring.
#
# The keyword list was an explicit enumeration until 2026-10-06, and 11 of 15
# real ClickHouse writes walked straight through it: `DELETE FROM` (the
# lightweight delete, which `ALTER TABLE ... DELETE` does not cover), `OPTIMIZE`,
# `RENAME`, `ATTACH`, `DETACH`, `SYSTEM`, `GRANT`, `REVOKE`, `KILL`, and every
# `CREATE`/`DROP` object other than the four spelled out — `CREATE VIEW` and
# `DROP VIEW` among them, which matters because flow-ui reads `silver.*` views.
# An enumeration of a DDL surface is a list that silently rots as the engine
# grows statements, so the shape is now: a handful of whole-word verbs, plus
# `CREATE`/`DROP`/`ALTER` followed by any uppercase word, plus `DELETE FROM`.
# Verified 0 hits against the current sources and 15/15 against the writes above.
hits="$(
    grep -rn --include='*.py' -E \
        '\b(INSERT|TRUNCATE|GRANT|REVOKE|KILL|OPTIMIZE|ATTACH|DETACH|RENAME|SYSTEM)\b|\b(CREATE|DROP|ALTER)[[:space:]]+[A-Z]|\bDELETE[[:space:]]+FROM\b' \
        "$SRC" 2>/dev/null | sed "s#^$ROOT/##" || true
)"

if [[ -n "$hits" ]]; then
    echo "flow-ui must not write; found:"
    printf '%s\n' "$hits" | sed 's/^/  /'
    exit 1
fi

echo "flow-ui issues no write statement"
