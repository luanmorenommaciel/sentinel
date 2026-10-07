#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
today="$(date +%F)"
from="$(date -v-2d +%F 2>/dev/null || date -d '2 days ago' +%F)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cat > "$tmp/clickhouse" <<'CLIENT'
#!/usr/bin/env bash
sql="$(cat)"
printf '%s\n' "$sql" >> "$CH_LOG"
if [[ "$sql" == *"today()"* ]]; then
    date +%F
elif [[ "$sql" == *"SELECT count() FROM silver.log_events"* ]]; then
    printf '73\n'
elif [[ "$sql" == *"INSERT INTO silver."* ]]; then
    printf 'unexpected insert\n' >&2
    exit 91
else
    printf '0\n'
fi
CLIENT
chmod +x "$tmp/clickhouse"

export CH_LOG="$tmp/queries.log"
before=73
if CH_CLIENT="$tmp/clickhouse" bash "$root/infra/clickhouse/backfill/backfill.sh" \
    FROM="$from" TO="$today" PHASE=1 >"$tmp/out" 2>&1; then
    echo "expected live-partition refusal" >&2
    exit 1
fi
grep -qi 'live partition' "$tmp/out"
after="$(printf 'SELECT count() FROM silver.log_events\n' | "$tmp/clickhouse")"
[[ "$before" == "$after" ]]
! grep -q 'INSERT INTO silver.' "$CH_LOG"
grep -q "status.*refused" "$CH_LOG"
! grep -qE -- '--force|FORCE|ALLOW_LIVE' "$root/infra/clickhouse/backfill/backfill.sh"
echo "runner live-partition refusal passed"
