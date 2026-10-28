#!/usr/bin/env bash
#
# Repo invariant harness.
#
# Runs every executable assert in invariants.d/ in filename order, prints one
# PASS/FAIL line per assert, and exits non-zero if any failed. Each assert is a
# standalone script taking no arguments; it exits 0 when the invariant holds and
# non-zero with a message naming the offending file when it does not.
#
# One assert per file is deliberate: a leg that needs a new invariant adds a new
# file instead of editing a shared one, so two legs never collide on a path
# (ADR-0009).
#
# Asserts may use $REPO_ROOT (absolute) and must not depend on the caller's cwd.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REPO_ROOT

ASSERT_DIR="$REPO_ROOT/scripts/ci/invariants.d"

if [[ ! -d "$ASSERT_DIR" ]]; then
    echo "run-invariants: no assert directory at $ASSERT_DIR" >&2
    exit 1
fi

failed=0
ran=0

for assert in "$ASSERT_DIR"/*.sh; do
    [[ -e "$assert" ]] || continue
    name="$(basename "$assert")"
    ran=$((ran + 1))
    if output="$(bash "$assert" 2>&1)"; then
        echo "PASS  $name"
        [[ -n "$output" ]] && echo "$output" | sed 's/^/      /'
    else
        echo "FAIL  $name"
        [[ -n "$output" ]] && echo "$output" | sed 's/^/      /'
        failed=$((failed + 1))
    fi
done

echo
echo "$ran assert(s) run, $failed failed"

[[ "$failed" -eq 0 ]]
