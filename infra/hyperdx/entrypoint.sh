#!/bin/sh
# Wraps the image's own entrypoint so the ClickHouse password stays a file path.
#
# HyperDX bootstraps its first connection from the DEFAULT_CONNECTIONS env var, whose
# JSON carries the password inline. This script builds that value at container start
# from CLICKHOUSE_PASSWORD_FILE, so the secret is never in the Compose file, the
# image, or `docker inspect`; it exists only in this process's environment.
set -eu

: "${CLICKHOUSE_URL:?CLICKHOUSE_URL is required}"
: "${CLICKHOUSE_USER:?CLICKHOUSE_USER is required}"
: "${CLICKHOUSE_PASSWORD_FILE:?CLICKHOUSE_PASSWORD_FILE is required}"

[ -r "$CLICKHOUSE_PASSWORD_FILE" ] || {
    echo "hyperdx: $CLICKHOUSE_PASSWORD_FILE is not readable (cp infra/secrets/ch_password.example infra/secrets/ch_password)" >&2
    exit 1
}

DEFAULT_CONNECTIONS="$(node -e '
  const fs = require("fs");
  const e = process.env;
  process.stdout.write(JSON.stringify([{
    name: "Sentinel ClickHouse",
    host: e.CLICKHOUSE_URL,
    username: e.CLICKHOUSE_USER,
    password: fs.readFileSync(e.CLICKHOUSE_PASSWORD_FILE, "utf8").replace(/\r?\n$/, ""),
  }]));
')"
DEFAULT_SOURCES="$(cat /etc/hyperdx/sources.json)"
export DEFAULT_CONNECTIONS DEFAULT_SOURCES

exec sh /etc/local/entry.sh
