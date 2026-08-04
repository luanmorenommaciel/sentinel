# Sentinel OTel Collector — multi-stage, multi-arch build (EP4.1).
#
# Our dependency tree is pure Rust (cityhash-rs + lz4_flex, no *-sys / OpenSSL /
# ring), so we cross-compile a FULLY STATIC musl binary and ship it on
# distroless/static — no libc, no shell, ~the binary only. Smallest + safest
# attack surface.
#
# Multi-arch: BuildKit populates TARGETARCH (amd64 | arm64). Each platform builds
# for its OWN musl triple, so there is no host→target cross-link (that path failed
# with `cc: unrecognized command-line option '-m64'` on arm64 hosts). Build both
# arches with buildx:
#
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     -t sentinel-collector-rust:dev services/collector-rust
#
# Single-arch (native) still works with a plain `docker build`.

# ─── builder ──────────────────────────────────────────────────────────────────
FROM rust:1.96-slim-bookworm AS builder

# BuildKit sets TARGETARCH from --platform (defaults to the build host's arch for
# a plain `docker build`). Map Docker's arch names to Rust musl triples.
ARG TARGETARCH
RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) echo "x86_64-unknown-linux-musl"  > /tmp/rust-target ;; \
      arm64) echo "aarch64-unknown-linux-musl" > /tmp/rust-target ;; \
      *) echo "unsupported TARGETARCH=$TARGETARCH" >&2; exit 1 ;; \
    esac

# musl-tools provides musl-gcc, the linker for the *-musl targets. We build each
# arch natively (no cross toolchain), so only the musl target + its std are added.
RUN apt-get update \
    && apt-get install -y --no-install-recommends musl-tools \
    && rm -rf /var/lib/apt/lists/* \
    && rustup target add "$(cat /tmp/rust-target)"

WORKDIR /build

# Dependency layer caching: copy the manifests and build a throwaway lib so the
# (slow) dependency compile is cached unless Cargo.toml/lock change.
COPY Cargo.toml Cargo.lock ./
RUN mkdir src \
    && echo 'fn main() {}' > src/main.rs \
    && echo '' > src/lib.rs \
    && cargo build --release --target "$(cat /tmp/rust-target)" --locked \
    && rm -rf src

# Now the real sources. `touch` is REQUIRED: Docker COPY preserves the original
# (older) source mtimes, so without it cargo would consider the dummy build
# up-to-date and ship the throwaway `fn main(){}` binary. Bumping the mtimes
# forces a recompile of the crate (deps stay cached).
COPY src ./src
RUN find src -name '*.rs' -exec touch {} + \
    && cargo build --release --target "$(cat /tmp/rust-target)" --locked \
    && cp "target/$(cat /tmp/rust-target)/release/sentinel-collector" /sentinel-collector

# ─── runtime ──────────────────────────────────────────────────────────────────
# distroless/static: no libc, no shell, no package manager. Runs as nonroot.
FROM gcr.io/distroless/static-debian12:nonroot

COPY --from=builder /sentinel-collector /usr/local/bin/sentinel-collector

# Config is supplied at runtime (mount or bake). With no argument the binary
# uses built-in defaults (count mode against the golden fixture, which is not
# present in this image — supply a config that points at real input).
ENTRYPOINT ["/usr/local/bin/sentinel-collector"]
