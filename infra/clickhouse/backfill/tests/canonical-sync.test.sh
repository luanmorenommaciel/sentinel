#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
for expected in "$root"/infra/clickhouse/backfill/canonical/*.sql; do
    name="$(basename "$expected")"
    staged="$root/infra/clickhouse/backfill/sql/$name"
    diff -u "$expected" "$staged"
done
if grep -REn 'INSERT[[:space:]]+INTO[[:space:]]+bronze\.otel_traces' "$root/infra/clickhouse/backfill/sql"; then
    echo 'backfill SQL must never replay into bronze.otel_traces' >&2
    exit 1
fi
echo "canonical checksum projections match all staging templates"
