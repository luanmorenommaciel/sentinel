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

# Knowing one literal is not a credential scan: rename the password and this
# assert goes quiet while the posture is unchanged. The checks below look for the
# *shape* of an inline credential instead, so a new one is caught on the day it
# lands rather than the day someone remembers to add it here.
#
# Two shapes, scoped differently on purpose:
#
#   (a) Unambiguous anywhere in the operational tree: a SQL `IDENTIFIED [WITH x]
#       BY <value>`, and a URI carrying `user:pass@`. Neither has an innocent
#       reading, so these run over every scanned file.
#   (b) A `password|passwd|secret` assigned a literal, restricted to the file
#       types that configure a running system (`*.yml`, `*.yaml`, `*.sql`, `*.sh`,
#       `*.conf`, `*.env`). Deliberately NOT `*.rs` or `*.py`: there, the same
#       shape is `password=conn.password` passing a variable, or a test fixture
#       asserting that an inlined secret is rejected — `config.rs` has both, and
#       `deny_unknown_fields` already makes an inline `password` key a parse
#       failure. The value pattern excludes `${...}` interpolation, a `/`-rooted
#       path and an empty value, which is how `password_file:` and
#       `CLICKHOUSE_PASSWORD="$(cat …)"` stay clean.
#
# `*.example` is scanned too: a committed example holding a real password is the
# exact mistake the `infra/secrets/` rule below exists to prevent.
#
# Scope of *paths* is unchanged, and remains the open question in issue #51.
UNAMBIGUOUS='IDENTIFIED[[:space:]]+(WITH[[:space:]]+[a-z_]+[[:space:]]+)?BY[[:space:]]*.[^[:space:]]|://[A-Za-z0-9_.-]+:[^@/[:space:]]+@'
ASSIGNED='(^|[^A-Za-z_])(password|passwd|secret)[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_~+-]{4,}'

shaped="$(
    {
        grep -rnE --binary-files=without-match --exclude-dir='invariants.d' \
            "$UNAMBIGUOUS" \
            "$ROOT/docker-compose.yml" "$ROOT/Makefile" \
            "$ROOT/infra" "$ROOT/services" "$ROOT/scripts" "$ROOT/.github" 2>/dev/null || true
        grep -rniE --binary-files=without-match --exclude-dir='invariants.d' \
            --include='*.yml' --include='*.yaml' --include='*.sql' \
            --include='*.sh' --include='*.conf' --include='*.env' \
            "$ASSIGNED" \
            "$ROOT/docker-compose.yml" "$ROOT/Makefile" \
            "$ROOT/infra" "$ROOT/services" "$ROOT/scripts" "$ROOT/.github" 2>/dev/null || true
    } | sed "s#^$ROOT/##" | sort -u
)"
if [[ -n "$shaped" ]]; then
    echo "inline credential shape present in:"
    printf '%s\n' "$shaped" | sed 's/^/  /'
    rc=1
fi

# Judged on what git TRACKS, not what is on disk. Corrected 2026-10-06: the
# filesystem form failed the moment a developer followed T18 and created the local
# `infra/secrets/ch_password` the root stack mounts — a gitignored file that is
# supposed to exist. The requirement is that a secret is never *committed*, and
# T44's own negative proof says so: "with a committed non-example file as the
# negative proof". `.gitignore` is what prevents the commit; this asserts that the
# ignore is actually effective, which is the part that can regress.
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    tracked="$(git -C "$ROOT" ls-files 'infra/secrets' | grep -v '\.example$' || true)"
    if [[ -n "$tracked" ]]; then
        echo "infra/secrets/ may only COMMIT *.example files; git tracks:"
        printf '%s\n' "$tracked" | sed 's/^/  /'
        rc=1
    fi
else
    echo "not a git repository: cannot tell a committed secret from a local one"
    rc=1
fi

[[ "$rc" -eq 0 ]] && echo "no plaintext credential in the operational tree"
exit "$rc"
