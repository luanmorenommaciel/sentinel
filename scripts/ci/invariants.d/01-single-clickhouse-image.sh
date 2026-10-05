#!/usr/bin/env bash
#
# REQ-I-01 — exactly one ClickHouse version is pinned across the repository.
#
# Authored to the post-T15 state: today three Compose files pin their own image
# (root 24.3, services/collector-rust/infra 25.4, services/generator-python 24.3),
# so this assert FAILS until the single definition (T12) replaces them and the
# generator Compose file is deleted (T15).

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

hits="$(
    grep -rn --include='*.yml' --include='*.yaml' \
        -E '^[[:space:]]*image:[[:space:]]*clickhouse/clickhouse-server:' \
        "$ROOT/docker-compose.yml" "$ROOT/infra" "$ROOT/services" 2>/dev/null |
        sed "s#^$ROOT/##" || true
)"

n="$(printf '%s' "$hits" | grep -c . || true)"

if [[ "$n" -ne 1 ]]; then
    echo "expected exactly 1 clickhouse-server image pin, found $n:"
    printf '%s\n' "$hits" | sed 's/^/  /'
    exit 1
fi

tag="${hits##*clickhouse/clickhouse-server:}"
if [[ -z "$tag" || "$tag" == "latest" ]]; then
    echo "the single clickhouse-server pin must name a version, not '${tag:-<empty>}': $hits"
    exit 1
fi

echo "single pin: $hits"
