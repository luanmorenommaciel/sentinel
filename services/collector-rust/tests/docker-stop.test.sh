#!/usr/bin/env bash
# `docker stop` on the collector image must exit 0, well inside the grace period.
#
# Issue #45's original evidence was the opposite: `docker stop -t 12` took the
# full 12 s and then exited 137 (SIGKILL), because only SIGINT was handled. The
# Rust fix (src/main.rs `shutdown_signal`) selects on SIGTERM as well, and
# tests/shutdown_signals.rs proves that against the bare binary. This script
# closes the remaining half of the acceptance criteria, which the cargo tests
# structurally cannot reach: PID 1 inside a distroless container, stopped the
# way Docker, Kubernetes and systemd actually stop it.
#
# Why a shell script and not a #[test]: the subject is the *image*, so the test
# has to exist outside the thing being tested. A cargo test runs the host
# binary, which is never PID 1 and never receives Docker's signal.
#
# Exit 0 = pass or skip. Exit 1 = the image ignored SIGTERM.
set -euo pipefail

IMAGE="${IMAGE:-sentinel-collector:ci}"
GRACE="${GRACE:-10}"   # docker stop default
BUDGET="${BUDGET:-5}"  # must exit well inside GRACE, not at the edge of it

skip() {
  echo "SKIP  docker-stop.test.sh — $1"
  echo "      set REQUIRE_DOCKER=1 to make this a failure instead (CI does)."
  [ "${REQUIRE_DOCKER:-0}" = "1" ] && { echo "::error::$1"; exit 1; }
  exit 0
}

command -v docker >/dev/null 2>&1 || skip "no docker client on PATH"
docker info >/dev/null 2>&1        || skip "no reachable docker daemon"
docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || skip "image $IMAGE not present — build it first (rust-ci docker-build, or docker build -t $IMAGE services/collector-rust)"

work="$(mktemp -d)"
name="sentinel-stop-check-$$"
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

# Log-only mode: no ClickHouse. The signal path under test is the same one the
# buffered exporter's final flush hangs off, and tests/shutdown_signals.rs
# covers the flush itself against a live ClickHouse. What is being measured
# here is purely "does PID 1 act on SIGTERM".
cat > "$work/config.yaml" <<'YAML'
grpc:
  listen: '0.0.0.0:4317'
metrics:
  listen: '0.0.0.0:9090'
contract:
  grpc_validation: off
YAML
chmod a+r "$work/config.yaml"

docker run -d --name "$name" \
  -v "$work/config.yaml:/etc/sentinel/config.yaml:ro" \
  "$IMAGE" /etc/sentinel/config.yaml >/dev/null

# Wait for the gRPC listener to be up; a process stopped before it installed
# its handlers would pass for the wrong reason.
for _ in $(seq 1 50); do
  if docker logs "$name" 2>&1 | grep -qi "listening\|serving\|grpc"; then break; fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$name")" != "true" ]; then
    echo "::error::collector exited during startup"
    docker logs "$name" 2>&1 | tail -20
    exit 1
  fi
  sleep 0.2
done

start="$(date +%s)"
docker stop -t "$GRACE" "$name" >/dev/null
elapsed=$(( $(date +%s) - start ))
code="$(docker inspect -f '{{.State.ExitCode}}' "$name")"

echo "docker stop -t ${GRACE}: exit ${code} after ${elapsed}s (budget ${BUDGET}s)"

fail=0
if [ "$code" != "0" ]; then
  # 137 = 128+9 = SIGKILL: the grace period expired and Docker killed it. That
  # is the exact symptom issue #45 recorded.
  echo "::error::expected exit 0, got $code$([ "$code" = "137" ] && echo ' (SIGKILL — SIGTERM was ignored)')"
  fail=1
fi
if [ "$elapsed" -gt "$BUDGET" ]; then
  echo "::error::took ${elapsed}s, over the ${BUDGET}s budget — it is riding the grace period, not handling the signal"
  fail=1
fi
[ "$fail" = "0" ] || exit 1
echo "PASS  the image handles SIGTERM and exits cleanly inside the grace period"
