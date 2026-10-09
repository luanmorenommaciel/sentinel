#!/usr/bin/env bash
#
# REQ-H-12 (T24) — image vulnerability scanning, without a registry.
#
# T24 was written as a step inside `release.yml` that scans the digest it has
# just pushed. That proof is unreachable: `release.yml` is gated to
# `workflow_dispatch` because no registry exists, and DEC-A1/A2 leave remote
# deployment unauthorized, so the pushed digest the ticket wants to scan is
# never produced. A scan, though, does not need a push — only bytes. This script
# applies the same discipline to bytes we already have locally, which is what
# makes the gate run for real instead of waiting on a platform decision.
#
# Two target sets, matching the two CI lanes (docs/ci-gates.md):
#
#   bases  (default, PR lane)   the shipped base image of every service, pulled
#                               straight from its registry. Derived from the LAST
#                               `FROM` in each services/*/Dockerfile — the stage
#                               that actually ships — so the list cannot drift
#                               from the Dockerfiles the way a hard-coded YAML
#                               list would. Builder stages are excluded on
#                               purpose: `rust:1.96-slim-bookworm` is thrown away
#                               by the multi-stage build and is not part of the
#                               deployed artifact's attack surface.
#
#   tars <dir>  (weekly lane)   `docker save` tarballs of the images as actually
#                               built, scanned with `--input`. This is the half
#                               that sees our OWN layers: the pip-installed
#                               Python packages in generator/flow-ui, which a
#                               base-image scan cannot see.
#
# Policy (REQ-H-12 is SHOULD; the threshold is a policy call, not a test — T24):
#
#   IMAGE_SCAN_SEVERITY        HIGH,CRITICAL
#   IMAGE_SCAN_IGNORE_UNFIXED  true   — see "why unfixed is ignored" below
#   IMAGE_SCAN_EXIT_CODE       0      — WARN-ONLY. *** Flip this one default to
#                                       1 to make the gate blocking. ***
#
# Why unfixed findings are ignored, measured 2026-10-08 against
# `python:3.12-slim` (the real base of two of the three images):
#
#   --severity HIGH,CRITICAL                    ->  44 HIGH,  0 CRITICAL
#   --severity HIGH,CRITICAL --ignore-unfixed   ->   0 HIGH,  0 CRITICAL
#
# All 44 carry no patched upstream version (`fix_deferred` / `affected`). A
# blocking gate counting those would be red on day one with nothing any author
# could do about it, which is how a gate gets switched off. Ignoring them is not
# ignoring the risk: IMAGE_SCAN_IGNORE_UNFIXED=false prints the full set, and
# the number above is the calibration T24 asks for before the flip.
#
# The verdict is taken from the REPORT, not from trivy's exit status. Measured
# while writing this: a transient `docker pull` failure against Docker Hub
# (`TLS handshake timeout`, exit 125 — the same flakiness the Makefile's
# DOCKER_BUILD_RETRIES comment documents for gcr.io) came back indistinguishable
# from "findings found" when the exit code was the only signal. Trivy itself
# overloads exit 1 for both an internal error and a policy hit. So every scan
# writes JSON, a missing or empty report is a HARD failure that says the scan
# could not run, and the finding counts come from that file. A gate that cannot
# tell "clean" from "never ran" is worse than no gate.
#
# The teeth assertion always runs last, in every mode. A scanner configured so
# permissively that nothing can fail it is not a gate, and a warn-only default
# is exactly the condition that invites it — so every run re-proves, against a
# digest-pinned deliberately vulnerable base image, that the CURRENT policy
# still finds something. T24 asks for that negative proof once; making it
# continuous costs one small scan with the DB already warm.

set -uo pipefail

ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.75.0}"
IMAGE_SCAN_SEVERITY="${IMAGE_SCAN_SEVERITY:-HIGH,CRITICAL}"
IMAGE_SCAN_IGNORE_UNFIXED="${IMAGE_SCAN_IGNORE_UNFIXED:-true}"
IMAGE_SCAN_EXIT_CODE="${IMAGE_SCAN_EXIT_CODE:-0}"
PULL_RETRIES="${PULL_RETRIES:-3}"

# Both platforms the repo actually ships (rust-ci.yml's docker-build builds
# linux/amd64 AND linux/arm64), because a Debian package snapshot is per-arch:
# the two variants of one tag can carry different installed versions, so one
# arch can be clean while the other is not. Only `bases` mode loops — a
# docker-save tarball holds exactly one platform, whichever built it.
IMAGE_SCAN_PLATFORMS="${IMAGE_SCAN_PLATFORMS:-linux/amd64 linux/arm64}"

# python:3.9-slim as resolved on 2026-10-08. A multi-arch index digest, so it is
# the same bytes on an amd64 runner and on an arm64 laptop, and immutable — the
# finding set can only grow, never silently empty out the way a moving tag can.
# One token away from the real base (`python:3.12-slim`), which is the mistake
# the gate exists to catch. Measured under the policy above: 72 HIGH,
# 6 CRITICAL, every one of them with a fixed version available.
TEETH_REF="${TEETH_REF:-python@sha256:2d97f6910b16bd338d3060f261f53f144965f755599aab1acda1e13cf1731b1b}"
TEETH_LABEL="python:3.9-slim (digest-pinned)"

mode="${1:-bases}"
tar_dir="${2:-}"
TAR_ABS=""

# One cache directory for the whole invocation: trivy downloads its vulnerability
# DB once and every later scan reuses it. Without this, N targets means N
# downloads of ~60 MB.
CACHE="$(mktemp -d)"
# shellcheck disable=SC2329  # invoked indirectly, by the EXIT trap on the next line
cleanup() { rm -rf "$CACHE"; }
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
    echo "audit-images: docker is required (trivy runs as $TRIVY_IMAGE)" >&2
    exit 1
fi

# `trivy` is the image's entrypoint, so arguments start at the subcommand. The
# cache is a host directory owned by the invoking user, which is why --user is
# safe to pass; --input targets are read from the same /tars mount.
run_trivy() {
    if [[ -n "$TAR_ABS" ]]; then
        docker run --rm --user "$(id -u):$(id -g)" \
            -v "$CACHE":/cache -v "$TAR_ABS":/tars:ro \
            "$TRIVY_IMAGE" --cache-dir /cache "$@"
    else
        docker run --rm --user "$(id -u):$(id -g)" \
            -v "$CACHE":/cache \
            "$TRIVY_IMAGE" --cache-dir /cache "$@"
    fi
}

# Pulled up front, and retried, for the reason in the header: an unpulled
# scanner is a registry problem and must never be reported as a finding.
pull_scanner() {
    local attempt=1 pause=5
    while :; do
        if docker image inspect "$TRIVY_IMAGE" >/dev/null 2>&1; then
            return 0
        fi
        if docker pull --quiet "$TRIVY_IMAGE" >/dev/null; then
            return 0
        fi
        if [[ "$attempt" -ge "$PULL_RETRIES" ]]; then
            echo "::error::audit-images: could not pull $TRIVY_IMAGE after $attempt attempt(s). This is a registry failure, not a scan result — nothing was scanned." >&2
            return 1
        fi
        echo "audit-images: pull of $TRIVY_IMAGE failed (attempt $attempt/$PULL_RETRIES); retrying in ${pause}s" >&2
        sleep "$pause"
        attempt=$((attempt + 1))
        pause=$((pause * 2))
    done
}

# Each entry is "<label>|<trivy target argument(s)>|<slug>". Keeping them in one
# string avoids parallel arrays with a variable stride, which is where a
# `--input <path>` pair would otherwise desynchronise from its label.
declare -a entries=()

case "$mode" in
bases)
    tar_dir=""
    for dockerfile in "$ROOT"/services/*/Dockerfile; do
        [[ -e "$dockerfile" ]] || continue
        service="$(basename "$(dirname "$dockerfile")")"
        base="$(awk 'toupper($1) == "FROM" { ref = $2 } END { print ref }' "$dockerfile")"
        if [[ -z "$base" ]]; then
            echo "audit-images: no FROM in ${dockerfile#"$ROOT"/}" >&2
            exit 1
        fi
        for platform in $IMAGE_SCAN_PLATFORMS; do
            entries+=("$service ships $base [$platform]|--platform $platform $base|$service-${platform//\//-}")
        done
    done
    ;;
tars)
    if [[ -z "$tar_dir" || ! -d "$tar_dir" ]]; then
        echo "audit-images: tars mode needs a directory of docker-save tarballs" >&2
        exit 1
    fi
    TAR_ABS="$(cd "$tar_dir" && pwd)"
    shopt -s nullglob
    for tar in "$TAR_ABS"/*.tar; do
        name="$(basename "$tar" .tar)"
        entries+=("built image $name|--input /tars/$(basename "$tar")|$name")
    done
    ;;
*)
    echo "audit-images: unknown mode '$mode' (expected: bases | tars <dir>)" >&2
    exit 1
    ;;
esac

if [[ "${#entries[@]}" -eq 0 ]]; then
    echo "audit-images: no scan targets in mode '$mode' — the gate would silently no-op" >&2
    exit 1
fi

blocking="(WARN-ONLY)"
[[ "$IMAGE_SCAN_EXIT_CODE" != "0" ]] && blocking="(BLOCKING)"

echo "── image vulnerability scan (REQ-H-12 / T24) ─────────────────────────────"
echo "   scanner          $TRIVY_IMAGE"
echo "   mode             $mode"
echo "   severity         $IMAGE_SCAN_SEVERITY"
echo "   ignore-unfixed   $IMAGE_SCAN_IGNORE_UNFIXED"
echo "   exit-code        $IMAGE_SCAN_EXIT_CODE $blocking"
echo

pull_scanner || exit 1

declare -a policy=(image --scanners vuln --severity "$IMAGE_SCAN_SEVERITY" --quiet)
[[ "$IMAGE_SCAN_IGNORE_UNFIXED" == "true" ]] && policy+=(--ignore-unfixed)

# Scan one target into JSON. A non-zero status or an empty report is fatal and
# named as "could not run"; --exit-code 0 here is deliberate, so the only
# non-zero status this can produce IS an error.
scan_to_json() {
    local slug="$1"
    shift
    run_trivy "${policy[@]}" --exit-code 0 --format json --output "/cache/$slug.json" "$@"
    local status=$?
    if [[ "$status" -ne 0 || ! -s "$CACHE/$slug.json" ]]; then
        echo "::error::audit-images: the scan of '$slug' could not run (status $status). This is not a clean result." >&2
        return 1
    fi
    return 0
}

count_severity() { grep -c "\"Severity\": \"$2\"" "$CACHE/$1.json"; }

rc=0
findings=0
declare -a seen=()

for entry in "${entries[@]}"; do
    label="${entry%%|*}"
    rest="${entry#*|}"
    target="${rest%%|*}"
    slug="${rest#*|}"

    # Two services share `python:3.12-slim`; scanning identical bytes twice buys
    # a second copy of the same table.
    dup=0
    for s in ${seen[@]+"${seen[@]}"}; do
        [[ "$s" == "$target" ]] && dup=1
    done
    if [[ "$dup" -eq 1 ]]; then
        echo "── $label — identical to a target already scanned above"
        echo
        continue
    fi
    seen+=("$target")

    echo "── $label"
    # shellcheck disable=SC2086  # $target is one or two deliberate words
    if ! scan_to_json "$slug" $target; then
        rc=1
        echo
        continue
    fi

    # `--scanners vuln` on the convert too: without it trivy warns "No enabled
    # scanners found" and drops the Report Summary box, so a clean target would
    # print nothing at all and the step would look like it had not run.
    # `--table-mode detailed` prints the per-CVE tables and drops trivy's
    # per-target summary box, which on a built Python image is one row per
    # site-package — forty rows of "0" ahead of the finding that matters. Clean
    # targets therefore print nothing here, which is why the count line below is
    # unconditional: it is what shows the step ran. The flag is marked
    # EXPERIMENTAL by trivy; TRIVY_IMAGE is version-pinned, so if a later version
    # drops it the convert fails loudly on the bump rather than silently.
    run_trivy convert --format table --table-mode detailed --scanners vuln "/cache/$slug.json"
    crit="$(count_severity "$slug" CRITICAL)"
    high="$(count_severity "$slug" HIGH)"
    echo "   $high HIGH, $crit CRITICAL at or above the policy threshold"
    if [[ "$((crit + high))" -gt 0 ]]; then
        findings=$((findings + crit + high))
    fi
    echo
done

# ── teeth ────────────────────────────────────────────────────────────────────
echo "── teeth: the current policy must still find a vulnerable base image"
echo "   fixture  $TEETH_LABEL"
if ! scan_to_json teeth "$TEETH_REF"; then
    echo "::error::teeth: the fixture could not be scanned, so this run proves nothing about whether the gate still has teeth" >&2
    exit 1
fi
teeth_crit="$(count_severity teeth CRITICAL)"
if [[ "$teeth_crit" -eq 0 ]]; then
    echo "::error::teeth: $TEETH_LABEL produced 0 CRITICAL findings under the current policy. The gate has no teeth — IMAGE_SCAN_SEVERITY / IMAGE_SCAN_IGNORE_UNFIXED have been loosened past the point where anything can fail it." >&2
    exit 1
fi
echo "   $teeth_crit fixable CRITICAL on the fixture — the policy bites"
echo

if [[ "$rc" -ne 0 ]]; then
    echo "image scan: at least one target could not be scanned (see above)" >&2
    exit 1
fi

if [[ "$findings" -eq 0 ]]; then
    echo "image scan: clean — 0 findings at or above $IMAGE_SCAN_SEVERITY across ${#seen[@]} distinct target(s)."
    exit 0
fi

if [[ "$IMAGE_SCAN_EXIT_CODE" == "0" ]]; then
    echo "image scan: $findings finding(s) at or above $IMAGE_SCAN_SEVERITY, reported and NOT blocking (IMAGE_SCAN_EXIT_CODE=0)."
    exit 0
fi

echo "image scan: $findings finding(s) at or above $IMAGE_SCAN_SEVERITY, and IMAGE_SCAN_EXIT_CODE=$IMAGE_SCAN_EXIT_CODE makes them blocking" >&2
exit 1
