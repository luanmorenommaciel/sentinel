#!/usr/bin/env bash
#
# REQ-I-07 — the ClickHouse service is named `clickhouse` in every stack.
#
# `make test-silver` and `make migrate` reach the database with
# `docker compose exec -T clickhouse …`; a renamed service breaks S1 silently.
#
# The assert inspects MERGED `docker compose config` output, not the source
# files: a local service with the same name as an included one silently wins and
# `config` still exits 0 (measured on Compose v5.1.4, infra/clickhouse/README.md),
# so a source-file grep can pass while the stack runs a different `clickhouse`.
#
# Authored to the post-T13 state: the shared definition does not exist yet, so
# this assert FAILS until T12/T13 land it.

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

# Every Compose file expected to put a ClickHouse on the network, including the
# shared definition itself.
STACKS=(
    "infra/clickhouse/compose.clickhouse.yml"
    "docker-compose.yml"
    "services/collector-rust/infra/docker-compose.yml"
)

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required: this invariant is about merged Compose output, which only Compose can produce"
    exit 1
fi

rc=0
for stack in "${STACKS[@]}"; do
    path="$ROOT/$stack"
    if [[ ! -f "$path" ]]; then
        echo "missing: $stack"
        rc=1
        continue
    fi
    if ! services="$(cd "$(dirname "$path")" && docker compose -f "$(basename "$path")" config --services 2>&1)"; then
        echo "docker compose config failed for $stack:"
        echo "$services" | sed 's/^/    /'
        rc=1
        continue
    fi
    if ! grep -qx "clickhouse" <<<"$services"; then
        echo "$stack defines no service named 'clickhouse' (merged config lists: $(tr '\n' ' ' <<<"$services"))"
        rc=1
    fi
done

[[ "$rc" -eq 0 ]] && echo "all ${#STACKS[@]} stacks expose a service named 'clickhouse'"
exit "$rc"
