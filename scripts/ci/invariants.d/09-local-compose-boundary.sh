#!/usr/bin/env bash
#
# The local boundary, and the startup ordering `make up` guarantees.
#
# Rewritten 2026-10-07. It used to assert three *literal* port mappings
# (`127.0.0.1:9090:9090`, `127.0.0.1:8080:8080`) and a literal readiness URL
# (`curl … http://127.0.0.1:8080/healthz`). That pinned the defaults and, worse,
# it passed while the Makefile's probes were hard-coded to those same literals —
# so `make up HYPERDX_HOST_PORT=…` moved the container and left the probe behind,
# and the invariant had nothing to say about it. What matters is the property, not
# the number:
#
#   1. every host-published port in the local stack binds to 127.0.0.1 — the
#      `::/0` routes stay closed (DEC-A4; TLS is deferred, so nothing may listen
#      on a routable interface);
#   2. each one is parameterised as ${VAR:-default}, so a crowded machine can move
#      it without editing a tracked file;
#   3. Make declares and exports a default for each of those VARs;
#   4. no readiness probe in the Makefile hard-codes a host port — every one is
#      derived from the same variable Compose reads, which is what makes the
#      committed Makefile work on an overridden port;
#   5. `make up` waits for ClickHouse, finishes migrations, THEN starts the
#      collector, and ends up waiting on all four host-published services;
#   6. flow-ui never requires collector-rust to start (it degrades, NFR-05).

set -uo pipefail

root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
compose="$root/docker-compose.yml"
clickhouse_compose="$root/infra/clickhouse/compose.clickhouse.yml"
makefile="$root/Makefile"

rc=0
fail() { echo "$*" >&2; rc=1; }

# ── 1 + 2: loopback-only, and parameterised ──────────────────────────────────
#
# Checked against the Compose SOURCE rather than `docker compose config`, because
# the question is whether the tracked file carries the `${VAR:-default}` form —
# merged config has already substituted it away. Assert 03 covers the merged view.
#
# Every list item under a `ports:` key is extracted, whatever it starts with — an
# earlier draft of this assert grepped for a leading digit and so silently skipped
# `- "${FLOW_UI_HOST_PORT:-8080}:8080"`, the very shape it is here to police.
mappings_of() {
    awk '
        match($0, /^[[:space:]]*ports:[[:space:]]*(#.*)?$/) { indent = index($0, "p"); on = 1; next }
        on && /^[[:space:]]*(#.*)?$/ { next }
        on && index($0, "- ") != indent + 2 { on = 0 }
        on {
            line = $0
            sub(/^[[:space:]]*-[[:space:]]*/, "", line)
            sub(/[[:space:]]*#.*$/, "", line)
            gsub(/"/, "", line)
            sub(/[[:space:]]+$/, "", line)
            if (line != "") print line
        }
    ' "$1"
}

for f in "$compose" "$clickhouse_compose"; do
    found_any=0
    while IFS= read -r mapping; do
        [[ -z "$mapping" ]] && continue
        found_any=1
        [[ "$mapping" == 127.0.0.1:* ]] ||
            fail "${f#"$root"/}: host-published port is not loopback-only: $mapping"
        [[ "$mapping" == *'${'*':-'*'}'* ]] ||
            fail "${f#"$root"/}: host port is a hard-coded literal, not \${VAR:-default}: $mapping"
    done <<<"$(mappings_of "$f")"
    [[ "$found_any" -eq 1 ]] ||
        fail "${f#"$root"/}: no published port mapping found — the extractor is broken, not the file"
done

# ── 3: Make owns a default for every host port, and exports it ───────────────
PORT_VARS=(
    CLICKHOUSE_HOST_PORT
    COLLECTOR_OTLP_HOST_PORT
    COLLECTOR_METRICS_HOST_PORT
    FLOW_UI_HOST_PORT
    HYPERDX_HOST_PORT
)
for var in "${PORT_VARS[@]}"; do
    grep -Eq "^${var}[[:space:]]*\?=[[:space:]]*[0-9]+" "$makefile" ||
        fail "Makefile must declare a default host port: ${var} ?= <port>"
    grep -Eq "^export .*\b${var}\b" "$makefile" ||
        fail "Makefile must export ${var} so the Compose files can read it"
done

# ── 4: no readiness probe pins a port ────────────────────────────────────────
#
# A literal `127.0.0.1:<digits>` anywhere in the Makefile is the exact defect this
# assert used to require. Every occurrence must be `127.0.0.1:$(SOME_HOST_PORT)`.
if literals="$(grep -nE '127\.0\.0\.1:[0-9]' "$makefile")"; then
    fail "Makefile pins a host port instead of deriving it from the exported variable:
$(sed 's/^/    /' <<<"$literals")"
fi

# ── 5: ordering, and that `up` waits for every host-published service ────────
awk '
  /^up:/{ in_up=1; next }
  in_up && /^[^\t #].*:/ { in_up=0 }
  in_up && /clickhouse-client -q "SELECT 1"/ { database_ready=NR }
  in_up && /docker compose up -d --build collector-rust/ { collector=NR }
  in_up && /\$\(MAKE\) migrate/ { migrate=NR }
  END { if (!database_ready || !migrate || !collector || database_ready >= migrate || migrate >= collector) exit 1 }
' "$makefile" || fail "make up must wait for ClickHouse, finish migrations, then start collector-rust"

for svc in ClickHouse collector flow-ui HyperDX; do
    awk -v svc="$svc" '
      /^up:/{ in_up=1; next }
      in_up && /^[^\t #].*:/ { in_up=0 }
      in_up && /\$\(call wait_http,/ && index($0, "wait_http," svc ",") { found=1 }
      END { exit !found }
    ' "$makefile" || fail "make up must wait on readiness for '$svc' — a started container is not a ready one"
done

awk '
  /^up:/{ in_up=1; next }
  in_up && /^[^\t #].*:/ { in_up=0 }
  in_up && /docker compose up -d --build --wait .*flow-ui.*hyperdx/ { found=1 }
  END { exit !found }
' "$makefile" || fail "make up must bring up flow-ui and hyperdx together with --wait"

# ── 6: flow-ui must not require the collector ────────────────────────────────
if awk '/^  flow-ui:/{ in_ui=1; next } in_ui && /^  [^ ]/{ in_ui=0 } in_ui && /collector-rust:/{ found=1 } END { exit !found }' "$compose"; then
    fail "flow-ui must not require collector-rust to start"
fi

awk '
  /^ui:/{ in_ui=1; next }
  in_ui && /^[^\t #].*:/ { in_ui=0 }
  in_ui && /\$\(call wait_http,flow-ui,/ { readiness=1 }
  END { exit !readiness }
' "$makefile" || fail "make ui must wait for flow-ui /healthz readiness"

[[ "$rc" -eq 0 ]] && echo "local Compose boundary, parameterised host ports and startup ordering: PASS"
exit "$rc"
