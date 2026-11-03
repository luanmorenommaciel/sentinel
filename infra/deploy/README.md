# Deployment artifacts

> **Scope decision (2026-10-06):** this repository is authorized for local execution
> with Docker Compose and Make only. No cloud or remote-host deployment is implemented
> here. T40–T44 below remain a future deployment scope; the runnable local workflow is
> documented in the root README and `docker-compose.yml`. TLS is deferred by DEC-A4.

What `release.yml` publishes, and what a future Google Cloud deployment would require.

This covers the part of the deployment story that is **invariant to the compute form**
(`design-spec.md` §A.2): the registry, the tags, provenance, the SBOM, signing and the
federated credential. DEC-A1 (compute form) and DEC-A2 (ClickHouse hosting) gate the
*deploy* side — T40–T44 — not this. Nothing here names a runtime.

## Registry layout (REQ-A-01)

One Artifact Registry repository, `sentinel`, holding three images:

```
${AR_LOCATION}-docker.pkg.dev/${GCP_PROJECT_ID}/sentinel/collector-rust:<git-sha>
${AR_LOCATION}-docker.pkg.dev/${GCP_PROJECT_ID}/sentinel/generator:<git-sha>
${AR_LOCATION}-docker.pkg.dev/${GCP_PROJECT_ID}/sentinel/flow-ui:<git-sha>
```

Each also carries a channel tag — `:main` on a merge to `main`, `:vX.Y.Z` on a `v*` tag.

**The full git SHA tag is the only thing a deployment ever names.** Channel tags are for
humans reading a registry listing. There is no `:latest` and no `:dev`: `metadata-action`
runs with `flavor: latest=false`, because it would otherwise add `:latest` on a semver tag.

Both architectures ship in one manifest (`linux/amd64,linux/arm64`).

## Required repository configuration

Set on the GitHub repository before the first run. None of these is a credential.

| Kind | Name | Value |
|---|---|---|
| Variable | `AR_LOCATION` | Artifact Registry location, e.g. `europe-west1` |
| Variable | `GCP_PROJECT_ID` | the project holding the `sentinel` repository |
| Variable | `DEPLOY_SERVICE_ACCOUNT` | the deploy SA's email |
| Secret | `WIF_PROVIDER` | the full Workload Identity provider resource name |

`WIF_PROVIDER` is a secret by convention, not by necessity — a provider resource name is
not sensitive. Nothing grants access without the repository's own OIDC token matching the
provider's attribute condition.

## The credential (REQ-A-03)

GitHub OIDC → Workload Identity Federation → a deploy service account. **No long-lived
service-account JSON key exists anywhere**, which is the project's first real IAM
(`core-intent.md` §5 records that none existed).

The provider's attribute condition must pin `assertion.repository` to this repository, or
any GitHub repository on the internet can mint a token for it. The deploy SA needs
`roles/artifactregistry.writer` on the `sentinel` repository and nothing else.

Asserted by grep, since the absence of a key is the requirement:

```sh
grep -rn "GOOGLE_APPLICATION_CREDENTIALS\|_json_key\|service-account-key" .github/workflows/
# -> 0 hits
```

## Provenance, SBOM, signing (REQ-A-02)

`docker/build-push-action` runs with `provenance: mode=max` and `sbom: true`, so BuildKit
attaches a SLSA provenance attestation and an SPDX SBOM to the image index. cosign then
signs **the digest** — never a tag, since a tag is mutable and a tag signature says
nothing about which bytes were signed — keyless, using the same OIDC identity that
authenticated the push.

Verifying a published digest:

```sh
IMG=${AR_LOCATION}-docker.pkg.dev/${GCP_PROJECT_ID}/sentinel/collector-rust
D=$(crane digest "$IMG:<git-sha>")

cosign verify "$IMG@$D" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github\.com/luanmorenommaciel/sentinel/'
```

> **Unverified.** The two attestation checks in T22's proof — `cosign verify-attestation
> --type slsaprovenance` and `cosign download sbom` — are written against
> cosign-*attached* artifacts. What this workflow produces is a **BuildKit** attestation
> in the image index, which is a different storage idiom; `cosign download sbom` in
> particular is deprecated and reads the legacy `.sbom` tag. The attestations are attached
> either way, but the exact verification command may need to be
> `cosign verify-attestation --type slsaprovenance` *or* a `docker buildx imagetools
> inspect --format '{{json .Provenance}}'`. **This has not been run against a real
> registry** — no registry, project or WIF provider exists yet. Confirm on the first
> publish and correct this section.

## Vulnerability scanning (REQ-H-12)

`release.yml` scans each image by digest, between the push and the signature, and is
**warn-only**: `exit-code: "0"` is the single flag to flip. The same warn-then-promote
reasoning as REQ-B-07 applies — a base image acquires a new CVE with no change from us,
so a gate that is blocking on day one turns unrelated pushes red and gets switched off.
Promotion to blocking, and the severity threshold that blocks, are policy and belong to
T21's required-check set.

> **It does not gate the push, despite REQ-H-12's wording.** The scan runs *after*
> `push: true`, so by the time a finding is printed the bytes are already in the registry.
> A multi-arch manifest cannot be `load`ed into the runner's daemon to be scanned before
> pushing, so the pre-push scan REQ-H-12 literally asks for is not available in this shape.
> Two honest options when the gate flips: push the SHA tag only, scan, then apply the
> channel tags on a clean result; or leave the push ungated and gate the **promotion** hop
> below, which is where an unscanned image is actually stopped from reaching an
> environment. Unresolved — it is a policy call, not a test.

## Promotion by digest (REQ-A-07)

`main` → `:staging`, a `v*` tag → `:prod`. The `promote` job contains no build step; it
re-points a channel tag at a digest that already exists:

```sh
crane tag "$IMG@$D" staging
```

Before it moves anything it runs `cosign verify` on the source digest, so an unsigned
digest fails **before** a tag moves — the publish-side half of REQ-A-02. After it moves,
it re-reads the tag and asserts the digest is unchanged; digest equality is the whole
assertion.

**A tag push sources prod from `:staging`, not from its own build.** A `v*` push re-runs
`publish`, and that rebuild is not guaranteed bit-reproducible — `provenance: mode=max`
plus a warm `type=gha` cache can land on a different digest for the same commit. Sourcing
prod from the SHA tag would then promote bytes that never sat in staging. The job
cross-checks `crane digest "$IMG:staging"` against `crane digest "$IMG:<sha>"` and fails
loudly on a mismatch rather than swapping silently.

Verifying a promotion by hand:

```sh
D1=$(crane digest "$IMG:<git-sha>")
D2=$(crane digest "$IMG:prod")
[ "$D1" = "$D2" ] && echo same-bytes
```

> **Unverified.** No registry, project or WIF provider exists yet, so neither the promote
> job nor the `crane tag` idiom has run against a real Artifact Registry. Two things to
> confirm on the first real run: that `crane tag` moves a tag on a **multi-arch index**
> as expected, and that the rebuild-on-tag mismatch described above is real rather than
> theoretical. If rebuilds turn out to be reproducible, the cross-check becomes redundant
> — delete it rather than leaving a check nobody can trip.

## Not here yet

- **Signature verification before admission** — the *admission* half of REQ-A-02 is only
  provable once a platform exists, and is asserted in T40 behind DEC-A1. The promote job
  above covers the publish-side half only: nothing yet stops a deployer naming an
  unverified digest directly.
- **The contents of `config/<env>/`** — the location is decided, the shape is T40's.

## Why there is no `make` target

S4 has no Make target by design (`SPEC §8.4`). A target would imply a laptop can run this,
and the only way a laptop authenticates to a registry is a long-lived credential — the
thing REQ-A-03 deletes. `rust-ci.yml`'s `docker-build` job keeps `push: false` as the
PR-time build check, so a pull request from a fork can never publish.
