#!/usr/bin/env bash
#
# REQ-I-05 — no host port is published twice.
#
# Two checks:
#   (a) within one Compose file, no host port is published by two services
#       (the `8080:8080` twice case);
#   (b) services/generator-python/docker-compose.yaml publishes no host port the
#       root stack also publishes — 8080 (clickstack vs flow-ui), 4317
#       (clickstack vs collector) and 8123 (its own ClickHouse vs the root one).
#
# services/collector-rust/infra/docker-compose.yml is excluded from (b) by
# design: it is a single-service alternative stack that rust-ci.yml runs on its
# own, never beside the root stack, and after T13/T14 both take their ClickHouse
# from the same shared definition.
#
# Authored to the post-T15 state: check (b) FAILS until the generator Compose
# file is deleted (T15).

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required: published ports are read from merged 'docker compose config' output"
    exit 1
fi

# Merged config of one Compose file, or non-zero with the error on stdout.
#
# Separated from port extraction on 2026-10-06. It used to be one function that
# swallowed `config` failures with `2>/dev/null`, so an unparseable Compose file
# produced no ports, no ports produced no duplicates, and the assert printed "no
# host port published twice" and exited 0. Measured: a file with broken YAML
# passed. A check that cannot tell "clean" from "could not be evaluated" is
# indistinguishable from no check, so the failure is now loud — the same reason
# the image scan in release.yml carries no `continue-on-error`.
compose_config() {
    local path="$1"
    (cd "$(dirname "$path")" && docker compose -f "$(basename "$path")" config 2>&1)
}

# Published host ports from merged config text, one per line. `docker compose
# config` normalises every short-form mapping to long form, so one grep covers
# all shapes.
ports_of() {
    grep -E '^[[:space:]]*published:' |
        sed -E 's/.*published:[[:space:]]*"?([0-9]+)"?.*/\1/'
}

rc=0

# (a) intra-file duplicates
while IFS= read -r path; do
    rel="${path#"$ROOT"/}"
    if ! cfg="$(compose_config "$path")"; then
        echo "docker compose config failed for $rel:"
        printf '%s\n' "$cfg" | sed 's/^/    /'
        rc=1
        continue
    fi
    dupes="$(printf '%s\n' "$cfg" | ports_of | sort | uniq -d)"
    if [[ -n "$dupes" ]]; then
        echo "$rel publishes the same host port more than once: $(tr '\n' ' ' <<<"$dupes")"
        rc=1
    fi
done < <(
    find "$ROOT" \( -name '.git' -o -name 'node_modules' -o -name '.worktrees' \) -prune -o \
        -type f \( -name 'docker-compose*.yml' -o -name 'docker-compose*.yaml' \
        -o -name 'compose*.yml' -o -name 'compose*.yaml' \) -print | sort
)

# (b) the generator Compose file vs the root stack
GEN="$ROOT/services/generator-python/docker-compose.yaml"
if [[ -f "$GEN" ]]; then
    if ! root_cfg="$(compose_config "$ROOT/docker-compose.yml")"; then
        echo "docker compose config failed for docker-compose.yml:"
        printf '%s\n' "$root_cfg" | sed 's/^/    /'
        exit 1
    fi
    if ! gen_cfg="$(compose_config "$GEN")"; then
        echo "docker compose config failed for services/generator-python/docker-compose.yaml:"
        printf '%s\n' "$gen_cfg" | sed 's/^/    /'
        exit 1
    fi
    root_ports="$(printf '%s\n' "$root_cfg" | ports_of | sort -u)"
    gen_ports="$(printf '%s\n' "$gen_cfg" | ports_of | sort -u)"
    overlap="$(comm -12 <(echo "$root_ports") <(echo "$gen_ports"))"
    if [[ -n "$overlap" ]]; then
        echo "services/generator-python/docker-compose.yaml collides with the root stack on host port(s): $(tr '\n' ' ' <<<"$overlap")"
        rc=1
    fi
fi

[[ "$rc" -eq 0 ]] && echo "no host port published twice"
exit "$rc"
