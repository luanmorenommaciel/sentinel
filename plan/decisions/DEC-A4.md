# DEC-A4 — TLS termination: in the collector, or at the platform edge

**Owner** Pod 2 · **Unblocks** T42 (and only T42)

Tags: **[M]** measured this session · **[S]** per spec §11.1 · **[D]** document assertion · **[R]** reasoned · **[M2]** measured 2026-10-06, T04's spike run locally.

## 1. The question

Does the collector terminate TLS itself (server TLS on `:4317` and/or client TLS to ClickHouse), or does the platform terminate it, and if a hop must be in-process, is the pure-Rust static-musl property worth giving up or worth a sidecar?

## 2. Why it's open

- `services/collector-rust/Dockerfile:3-6` states the tree is "pure Rust (cityhash-rs + lz4_flex, no `*-sys` / OpenSSL / ring)" and that this is why a fully static musl binary on `gcr.io/distroless/static-debian12:nonroot` works. `intent/core-intent.md` §5 calls that image the strongest single artifact in the baseline's security posture. NFR-02 requires an ADR for any change adding a shell, package manager or dynamic libc.
- Two hops are different problems. Hop 1 (generator to collector `:4317`) can be avoided in-process: the generator already has `--otlp-secure`, `--otlp-api-key`, `--otlp-header` **[D]** `spec` §14.3. Hop 2 (collector to ClickHouse) has no edge to terminate it; it is **forced** if DEC-A2 picks managed ClickHouse (`spec` §14.3, REQ-H-07/H-10).
- Adding rustls pulls a crypto provider (`ring` or `aws-lc-rs`), neither pure Rust **[D]** `spec` §12.6.

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **Edge termination** (hop 1 only) | Collector gains no peer identity; needs a platform edge (DEC-A1). Does nothing for hop 2 | Nothing; zero collector code change |
| **In-process client TLS for hop 2** (and optionally server TLS) | Breaks the `Dockerfile:3-6` claim, which must be rewritten in the same PR (REQ-H-10); may need `deny.toml` licence additions; static aarch64 build is untested | The "no `*-sys`/ring" property; any remedy that keeps shipping (dynamic linking, non-distroless base) weakens exactly what T42 is meant to improve |
| **TLS-terminating sidecar** | Second image, config and patch surface | Single-container simplicity; preserves purity exactly |

**No recommendation: this is Pod 2's call and the facts it needs do not yet exist.** T04 is a *prerequisite spike*, not part of the decision: it produces whether a TLS-enabled static musl binary builds on x86_64 **and** aarch64 and whether `cargo deny` passes. Do not decide before T04 reports. What would break the tie: T04 passing on both targets (then the cost is the lost property and a licence review) versus failing on aarch64 (then in-process pushes toward the weakening fixes, and a sidecar looks better).

## 4. Established facts

- **[M]** `services/collector-rust/Cargo.lock` (180 packages) contains none of `ring`, `openssl`, `openssl-sys`, `aws-lc-rs`, `aws-lc-sys`, `rustls`, `native-tls`, `hyper-rustls`, `tokio-rustls`, `reqwest`; it does contain `cityhash-rs` and `lz4_flex`. The Dockerfile claim is currently true.
- **[M]** `deny.toml` licence allow-list: Apache-2.0 (and LLVM-exception), MIT, BSD-2/3-Clause, ISC, Unicode-DFS-2016, Unicode-3.0, Zlib. `[bans] deny = []`. Whether a crypto provider's licences fit is **[R]** unmeasured; T04 measures it.
- **[M]** `rust-toolchain.toml:17` lists only `x86_64-unknown-linux-musl`; `rust-ci.yml:119-132` builds no arm64. The Dockerfile already maps `TARGETARCH` to each musl triple (`Dockerfile:22-35`), so the image build handles arm64 locally but CI never exercises it (`spec` §4 row 8).
- **[D]** The recorded E2E snapshot is arm64, so an arm64 TLS failure breaks the team's own machines first (`spec` §10).
- Which `clickhouse` 0.13 crate feature enables TLS, and which provider it selects, was **not checked**. T04 must record it.

**[M2] T04 has now reported, and the prerequisite is satisfied on both targets.** The brief said
"do not decide before T04 reports". T04's job (`rust-ci.yml:musl-tls-spike`) landed in this cycle
but has never run, because GitHub Actions has been failing account-wide since 2026-10-05. Its exact
command was therefore run locally on 2026-10-06, in `rust:1.96` containers with `musl-tools`:

| Target | `cargo build --release --locked --features tls-spike` | `file` says | Static? |
|---|---|---|---|
| `aarch64-unknown-linux-musl` | exit 0, 19.1 s (native on arm64) | `ELF 64-bit … statically linked, stripped` | yes |
| `x86_64-unknown-linux-musl` | exit 0, 55.4 s (emulated amd64) | `ELF 64-bit … static-pie linked, stripped` | yes |

So **a TLS-enabled static musl binary builds on both targets**, and the tie-breaker the brief named
— "failing on aarch64 … a sidecar looks better" — does not obtain. aarch64 is the target that
passed most cleanly.

Two details the decision should carry:

- **The TLS provider resolved is rustls, not OpenSSL.** `tonic/tls` pulled `tokio-rustls 0.26.5` and
  `rustls-webpki 0.103.15`; no `openssl-sys` entered the graph. That narrows the licence review the
  brief anticipates to Apache-2.0 / ISC / MIT, and it is *why* static musl survives — there is no C
  TLS library to link against.
- **T04's own verification step was reporting a false negative on x86_64.** It ran
  `file … | grep -q "statically linked"`, which does not match `static-pie linked` — the spelling
  `file` uses for a position-independent static executable, which has no dynamic loader and is no
  less static. Had Actions been running, the x86_64 leg would have reported failure for a binary
  that is genuinely static, and this decision would have been taken on it. Fixed in the same commit
  that recorded this table; the pattern now accepts both spellings.

**[R]** `cargo deny` over the TLS feature is *not* covered by the above: the spike job does not run
it, and the `supply-chain (cargo deny)` job builds without `--features tls-spike`. So the licence
and advisory status of the rustls subtree is still unmeasured, and remains a precondition the brief
correctly lists.

## 5. What it unblocks

T42, which is also blocked by T04 and T40. `spec` §14.3 makes hop 2 TLS conditional on DEC-A2, so if A2 selects self-hosting without TLS, T42 may shrink to documentation (hop-2 requirement then comes from REQ-H-07 alone, which says all four hops MUST be encrypted in a deployed environment: self-hosting does not exempt it).

## 6. What it cannot settle

- Whether edge termination exists at all depends on DEC-A1.
- Hop 2 has no edge-termination option, so "edge" alone cannot satisfy REQ-H-07 for the ClickHouse hop. A sidecar or in-process choice is needed there regardless **[R]**, unless ClickHouse is reached over a platform-private transport the platform itself encrypts (not asserted in any document).
- Peer identity (mTLS) is out of scope for all three options.
