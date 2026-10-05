#!/usr/bin/env bash
#
# REQ-H-01 / NFR-10 / spec §14.2 rule 4 — no plaintext credential in the
# operational tree, and nothing but `*.example` under infra/secrets/.
#
# Scope: the files that configure a running system — Compose files, infra/,
# services/, scripts/, .github/, Makefile. The SDLC chain (intent/, spec/, plan/)
# and docs/ are deliberately out of scope: they are point-in-time records that
# quote the offending string in order to require its removal, and NFR-08 forbids
# editing a record. invariants.d/ is excluded because this assert names the
# string it forbids.
#
# Authored to the post-T19 state: `otelgen_secret` is still live in
# infra/clickhouse-init.sql and services/generator-python/docker-compose.yaml, so
# this assert FAILS until migration 0002 replaces them (T17/T19).

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

rc=0

hits="$(
    grep -rl --binary-files=without-match \
        --exclude-dir='invariants.d' 'otelgen_secret' \
        "$ROOT/docker-compose.yml" "$ROOT/Makefile" \
        "$ROOT/infra" "$ROOT/services" "$ROOT/scripts" "$ROOT/.github" 2>/dev/null |
        sed "s#^$ROOT/##" || true
)"
if [[ -n "$hits" ]]; then
    echo "plaintext credential 'otelgen_secret' present in:"
    printf '%s\n' "$hits" | sed 's/^/  /'
    rc=1
fi

if [[ -d "$ROOT/infra/secrets" ]]; then
    leaked="$(find "$ROOT/infra/secrets" -type f ! -name '*.example' | sed "s#^$ROOT/##" || true)"
    if [[ -n "$leaked" ]]; then
        echo "infra/secrets/ may only hold *.example files; found:"
        printf '%s\n' "$leaked" | sed 's/^/  /'
        rc=1
    fi
fi

[[ "$rc" -eq 0 ]] && echo "no plaintext credential in the operational tree"
exit "$rc"
