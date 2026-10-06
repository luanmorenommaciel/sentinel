# Deployment artifacts

What `release.yml` publishes, and what has to exist in Google Cloud before it can.

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

## Not here yet

- **Promotion staging→prod by digest** — T23. Re-tags by digest, never rebuilds;
  per-environment differences will live only in `infra/deploy/config/<env>/`.
- **Vulnerability scanning as the push gate** — T24 (REQ-H-12).
- **Signature verification before admission** — the admission half of REQ-A-02 is only
  provable once a platform exists, and is asserted in T40 behind DEC-A1.

## Why there is no `make` target

S4 has no Make target by design (`SPEC §8.4`). A target would imply a laptop can run this,
and the only way a laptop authenticates to a registry is a long-lived credential — the
thing REQ-A-03 deletes. `rust-ci.yml`'s `docker-build` job keeps `push: false` as the
PR-time build check, so a pull request from a fork can never publish.
