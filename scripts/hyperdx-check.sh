#!/usr/bin/env bash
set -eu
: "${SENTINEL_DEV_EMAIL:?missing local email}"
: "${SENTINEL_DEV_PASSWORD:?missing local password}"
: "${HYPERDX_URL:?missing HyperDX URL}"
umask 077
cookie=$(mktemp)
trap 'unlink "$cookie"' EXIT
code=$(printf '{"email":"%s","password":"%s"}' "$SENTINEL_DEV_EMAIL" "$SENTINEL_DEV_PASSWORD" | curl -sS --max-time 10 -c "$cookie" -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' --data-binary @- "$HYPERDX_URL/api/login/password")
if [ "$code" != 303 ]; then
    echo 'HyperDX login failed. Existing accounts are preserved; supply their credentials and retry make up.' >&2
    exit 1
fi
for path in connections sources; do
    curl -fsS --max-time 10 -b "$cookie" "$HYPERDX_URL/api/$path" | docker compose exec -T hyperdx node -e '
let s=""; process.stdin.on("data", x => s += x); process.stdin.on("end", () => {
  const a = JSON.parse(s); if (!Array.isArray(a)) process.exit(1);
  if (process.argv[1] === "connections" && !a.some(x => x.name === "Sentinel ClickHouse" && x.host === "http://clickhouse:8123" && x.username === "sentinel_hyperdx_u")) process.exit(1);
  if (process.argv[1] === "sources" && !["Logs", "Traces", "Metrics"].every(n => a.some(x => x.name === n && !x.disabled))) process.exit(1);
});' "$path"
done
curl -fsS --max-time 5 "$HYPERDX_URL/api/ready" >/dev/null
docker compose exec -T hyperdx node -e '
const fs = require("fs"), http = require("http");
const password = fs.readFileSync(process.env.CLICKHOUSE_PASSWORD_FILE, "utf8").trim();
const u = new URL(process.env.CLICKHOUSE_URL); u.searchParams.set("query", "SELECT 1");
const req = http.get(u, { headers: { Authorization: "Basic " + Buffer.from(process.env.CLICKHOUSE_USER + ":" + password).toString("base64") }, timeout: 5000 }, res => {
  let body = ""; res.on("data", x => body += x); res.on("end", () => { if (res.statusCode !== 200 || body.trim() !== "1") process.exitCode = 1; });
}); req.on("timeout", () => req.destroy()); req.on("error", () => { process.exitCode = 1; });'
echo 'HyperDX account and configured sources available; ClickHouse reader connection verified.' 
