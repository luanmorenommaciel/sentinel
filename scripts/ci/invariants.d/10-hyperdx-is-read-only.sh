#!/usr/bin/env bash
#
# ADR-0011 — HyperDX is a read-layer UI wired straight to ClickHouse.
#
# Four properties that would each break silently if a later edit drifted:
#   1. it authenticates as the SELECT-only user, never a writer or `default`;
#   2. its password is a file path and the wrapper builds the connection from it;
#   3. its host port is loopback-only and its Mongo has no host port at all;
#   4. both images are pinned to a version, not `latest`, and the stack carries no
#      second ClickHouse or OTel collector (the bundled all-in-one images do).

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
compose="$ROOT/docker-compose.yml"
rc=0
fail() { echo "$*"; rc=1; }

service_block() {
    awk -v svc="  $1:" '
        $0 == svc { on = 1; next }
        on && /^  [^ #]/ { on = 0 }
        on && /^[^ ]/ { on = 0 }
        on { print }
    ' "$compose"
}

hyperdx="$(service_block hyperdx)"
mongo="$(service_block hyperdx-mongo)"

[[ -n "$hyperdx" && -n "$mongo" ]] || { echo "docker-compose.yml must define hyperdx and hyperdx-mongo"; exit 1; }

grep -Eq 'CLICKHOUSE_USER:[[:space:]]*sentinel_hyperdx_u[[:space:]]*$' <<<"$hyperdx" ||
    fail "hyperdx must connect as sentinel_hyperdx_u"
grep -Eq 'CLICKHOUSE_PASSWORD_FILE:[[:space:]]*/etc/sentinel/secrets/' <<<"$hyperdx" ||
    fail "hyperdx must take its password as a file path (CLICKHOUSE_PASSWORD_FILE)"
grep -Eq '(^|[[:space:]])(CLICKHOUSE_PASSWORD|DEFAULT_CONNECTIONS):' <<<"$hyperdx" &&
    fail "hyperdx must not carry the password or the connection JSON inline"

while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" == *'127.0.0.1:'* ]] || fail "hyperdx publishes a non-loopback port: $line"
done <<<"$(grep -E '^[[:space:]]+- +"[^"]*:[0-9]+"[[:space:]]*(#.*)?$' <<<"$hyperdx" || true)"
grep -Eq '^[[:space:]]+ports:' <<<"$mongo" && fail "hyperdx-mongo must not publish a host port"

for block in "$hyperdx" "$mongo"; do
    image="$(grep -E '^[[:space:]]+image:' <<<"$block" | head -n1 | sed -E 's/^[[:space:]]+image:[[:space:]]*//')"
    tag="${image##*:}"
    if [[ "$image" != *:* || "$tag" == "latest" ]]; then
        fail "image must be pinned to a version, not '${image:-<none>}'"
    fi
done

bundled="$(grep -rnE --include='*.yml' --include='*.yaml' \
    'image:[[:space:]]*.?(docker\.hyperdx\.io/|clickhouse/)?(hyperdx/(hyperdx-local|hyperdx-all-in-one|hyperdx-otel-collector)|clickhouse/clickstack-)' \
    "$ROOT/docker-compose.yml" "$ROOT/infra" "$ROOT/services" 2>/dev/null | sed "s#^$ROOT/##" || true)"
[[ -z "$bundled" ]] || fail "a bundled ClickStack image would add a second ClickHouse/collector:
$(sed 's/^/  /' <<<"$bundled")"

[[ "$rc" -eq 0 ]] && echo "hyperdx: read-only user, password by file, loopback-only, pinned, nothing bundled"
exit "$rc"
