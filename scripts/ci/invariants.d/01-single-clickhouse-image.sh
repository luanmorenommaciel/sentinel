#!/usr/bin/env bash
#
# REQ-I-01 — exactly one ClickHouse version is pinned across the repository.
#
# Authored to the post-T15 state: today three Compose files pin their own image
# (root 24.3, services/collector-rust/infra 25.4, services/generator-python 24.3),
# so this assert FAILS until the single definition (T12) replaces them and the
# generator Compose file is deleted (T15).
#
# Two holes closed 2026-10-06, both of which would have let it pass while more
# than one ClickHouse version was pinned:
#
#   1. `clickstack-all-in-one` bundles a ClickHouse server, so it *is* a pinned
#      version (generator compose `:39`, `:latest`). Matching only
#      `clickhouse-server:` made it invisible. Today both pins die together with
#      T15, which masked it — but REQ-I-06 moves the ClickStack examples into
#      `services/generator-python/README.md`, and if one ever came back as a
#      Compose file this assert would have called the repo single-pinned with two
#      ClickHouse versions in it.
#   2. `.github/workflows/` was out of scope. No workflow pins a ClickHouse image
#      today (CI goes through `services/collector-rust/infra/docker-compose.yml`,
#      which is in scope), but a `services:` container added to a workflow later
#      is exactly the divergence DEC-I1 exists to end, and it would not have been
#      seen.
#
# Markdown is deliberately still out of scope: REQ-I-06's documentation snippets
# are prose, not a definition something runs.

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

hits="$(
    grep -rn --include='*.yml' --include='*.yaml' \
        -E '^[[:space:]]*image:[[:space:]]*.?clickhouse/(clickhouse-server|clickstack-all-in-one)[:@]' \
        "$ROOT/docker-compose.yml" "$ROOT/infra" "$ROOT/services" "$ROOT/.github" 2>/dev/null |
        sed "s#^$ROOT/##" || true
)"

n="$(printf '%s' "$hits" | grep -c . || true)"

if [[ "$n" -ne 1 ]]; then
    echo "expected exactly 1 clickhouse-server image pin, found $n:"
    printf '%s\n' "$hits" | sed 's/^/  /'
    exit 1
fi

# Trailing quote or inline comment must not read as part of the tag, or
# `:latest  # pinned` would slip past the check below as a "version".
tag="${hits##*[:@]}"
tag="${tag%%[\"\' 	#]*}"
if [[ -z "$tag" || "$tag" == "latest" ]]; then
    echo "the single clickhouse-server pin must name a version, not '${tag:-<empty>}': $hits"
    exit 1
fi

echo "single pin: $hits"
