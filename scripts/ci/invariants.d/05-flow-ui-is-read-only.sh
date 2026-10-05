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
hits="$(
    grep -rn --include='*.py' -E '\b(INSERT|ALTER TABLE|ALTER DATABASE|CREATE TABLE|CREATE DATABASE|CREATE MATERIALIZED VIEW|DROP TABLE|DROP DATABASE|TRUNCATE)\b' \
        "$SRC" 2>/dev/null | sed "s#^$ROOT/##" || true
)"

if [[ -n "$hits" ]]; then
    echo "flow-ui must not write; found:"
    printf '%s\n' "$hits" | sed 's/^/  /'
    exit 1
fi

echo "flow-ui issues no write statement"
