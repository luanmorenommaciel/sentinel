#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
compose="$root/docker-compose.yml"
clickhouse_compose="$root/infra/clickhouse/compose.clickhouse.yml"
makefile="$root/Makefile"

for mapping in '127.0.0.1:${COLLECTOR_OTLP_HOST_PORT:-4317}:4317' '127.0.0.1:9090:9090' '127.0.0.1:8080:8080'; do
  grep -Fq "$mapping" "$compose" || {
    echo "expected loopback-only port mapping: $mapping" >&2
    exit 1
  }
done
grep -Fq 'COLLECTOR_OTLP_HOST_PORT ?= 4317' "$makefile" || {
  echo "make must provide the default collector OTLP host port" >&2
  exit 1
}
grep -Fq '127.0.0.1:8123:8123' "$clickhouse_compose" || {
  echo "ClickHouse host port must bind to loopback" >&2
  exit 1
}

awk '
  /^up:/{ in_up=1; next }
  in_up && /^[^\t #].*:/ { in_up=0 }
  in_up && /clickhouse-client -q "SELECT 1"/ { database_ready=NR }
  in_up && /docker compose up -d --build collector-rust/ { collector=NR }
  in_up && /\$\(MAKE\) migrate/ { migrate=NR }
  END { if (!database_ready || !migrate || !collector || database_ready >= migrate || migrate >= collector) exit 1 }
' "$makefile" || {
  echo "make up must wait for ClickHouse, finish migrations, then start collector-rust" >&2
  exit 1
}

if awk '/^  flow-ui:/{ in_ui=1; next } in_ui && /^  [^ ]/{ in_ui=0 } in_ui && /collector-rust:/{ found=1 } END { exit !found }' "$compose"; then
  echo "flow-ui must not require collector-rust to start" >&2
  exit 1
fi

awk '
  /^ui:/{ in_ui=1; next }
  in_ui && /^[^\t #].*:/ { in_ui=0 }
  in_ui && /curl -fsS http:\/\/127\.0\.0\.1:8080\/healthz/ { readiness=1 }
  END { if (!readiness) exit 1 }
' "$makefile" || {
  echo "make ui must wait for flow-ui /healthz readiness" >&2
  exit 1
}

echo "local Compose boundary and startup ordering: PASS"
