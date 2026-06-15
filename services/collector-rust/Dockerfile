# Sentinel OTel Collector — multi-stage build (Day 7).
#
# Our dependency tree is pure Rust (cityhash-rs + lz4_flex, no *-sys / OpenSSL /
# ring), so we cross-compile a FULLY STATIC musl binary and ship it on
# distroless/static — no libc, no shell, ~the binary only. Smallest + safest
# attack surface.
#
# Build (from the crate dir):  docker build -t sentinel-collector:dev services/collector-rust
# Or via the full-stack compose: docker compose -f infra/docker-compose.yml \
#                                  -f infra/docker-compose.collector.yml up --build

# ─── builder ──────────────────────────────────────────────────────────────────
FROM rust:1.96-slim-bookworm AS builder

# The musl target gives us a static binary. The base image pins the compiler to
# 1.96; we deliberately do NOT copy rust-toolchain.toml here so rustup doesn't
# pull the heavy components it lists (rust-analyzer et al.) into the builder.
RUN rustup target add x86_64-unknown-linux-musl

WORKDIR /build

# Dependency layer caching: copy the manifests and build a throwaway lib so the
# (slow) dependency compile is cached unless Cargo.toml/lock change.
COPY Cargo.toml Cargo.lock ./
RUN mkdir src \
    && echo 'fn main() {}' > src/main.rs \
    && echo '' > src/lib.rs \
    && cargo build --release --target x86_64-unknown-linux-musl --locked \
    && rm -rf src

# Now the real sources. `touch` is REQUIRED: Docker COPY preserves the original
# (older) source mtimes, so without it cargo would consider the dummy build
# up-to-date and ship the throwaway `fn main(){}` binary. Bumping the mtimes
# forces a recompile of the crate (deps stay cached).
COPY src ./src
RUN find src -name '*.rs' -exec touch {} + \
    && cargo build --release --target x86_64-unknown-linux-musl --locked \
    && cp target/x86_64-unknown-linux-musl/release/sentinel-collector /sentinel-collector

# ─── runtime ──────────────────────────────────────────────────────────────────
# distroless/static: no libc, no shell, no package manager. Runs as nonroot.
FROM gcr.io/distroless/static-debian12:nonroot

COPY --from=builder /sentinel-collector /usr/local/bin/sentinel-collector

# Config is supplied at runtime (mount or bake). With no argument the binary
# uses built-in defaults (count mode against the golden fixture, which is not
# present in this image — supply a config that points at real input).
ENTRYPOINT ["/usr/local/bin/sentinel-collector"]
