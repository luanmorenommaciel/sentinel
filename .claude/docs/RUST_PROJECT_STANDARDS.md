# Rust Project Standards — the UV-equivalent setup for Sentinel

> Last updated: 2026-06-01
> Goal: deliver the same simple, standardized contributor experience for Rust services in Sentinel that `uv` delivers for our Python projects.

## Why this doc exists

Our Python projects (briefing-hub, duck-quant, pkos, …) all share the same UV-powered shape:

- `pyproject.toml` (PEP 621) for metadata + deps
- `uv.lock` committed for reproducibility
- `[project.optional-dependencies] dev = [...]` for tooling
- `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` co-located in pyproject.toml
- `src/<pkg>/` layout, `tests/` at root
- `uv sync` to bootstrap, `uv run` to execute

**One file. One tool. Everything in one place.**

Rust delivers the same posture differently: most of it is built into `cargo` from day one. The "UV-equivalent" is mostly a matter of **picking the right defaults and writing them down** so every Rust service in Sentinel feels the same to a contributor.

## The mapping at a glance

| UV / `pyproject.toml` | Rust equivalent | Where it lives |
|---|---|---|
| `[project]` metadata | `[package]` | `Cargo.toml` |
| `dependencies = [...]` | `[dependencies]` | `Cargo.toml` |
| `[project.optional-dependencies] dev` | `[dev-dependencies]` | `Cargo.toml` |
| `requires-python = ">=3.11"` | `rust-version = "1.75"` + `rust-toolchain.toml` | `Cargo.toml` + repo root |
| `uv.lock` | `Cargo.lock` (auto-generated) | repo root (binaries: commit; libs: gitignore) |
| `uv sync` | `cargo build` | (built into cargo) |
| `uv run <script>` | `cargo run --bin <name>` | (built into cargo) |
| `uv add <pkg>` | `cargo add <pkg>` | (built into cargo) |
| `uv pip install -e .` | `cargo build -p <pkg>` (workspace) | (built into cargo) |
| `[tool.ruff]` (lint) | `[lints]` in `Cargo.toml` + `clippy.toml` | `Cargo.toml` + repo root |
| `[tool.ruff.format]` | `rustfmt.toml` | repo root |
| `[tool.mypy]` | — (Rust types are checked by the compiler) | n/a |
| `[tool.pytest.ini_options]` | `#[test]` + `cargo test` or `cargo nextest` | (built into cargo) |
| `pre-commit` config | same `pre-commit` framework, Rust hooks | `.pre-commit-config.yaml` |
| `.venv/` | `target/` (build artefacts, gitignored) | n/a |
| `.python-version` | `rust-toolchain.toml` | repo root |
| `uv workspace` | `[workspace]` in root `Cargo.toml` | repo root |
| `make dev` / `just test` | `just` (same as Python) or `cargo make` | `justfile` at repo root |

## The Sentinel Rust project layout

For any Rust service in this repo (`services/collector-rust/`, future `services/X-rust/`):

```text
sentinel/
├── Cargo.toml                       # WORKSPACE root — see below
├── Cargo.lock                       # committed (we ship binaries, not libs)
├── rust-toolchain.toml              # toolchain pin (Rust + components)
├── rustfmt.toml                     # format rules
├── clippy.toml                      # extra lint config (when needed)
├── deny.toml                        # cargo-deny: license + security policy
├── justfile                         # task runner — same as Python projects
├── .pre-commit-config.yaml          # fmt + clippy + audit hooks
└── services/
    └── collector-rust/
        ├── Cargo.toml               # CRATE — depends on workspace
        ├── src/
        │   ├── main.rs              # binary entry
        │   ├── lib.rs               # library entry (optional, for testability)
        │   └── ...
        ├── tests/                   # integration tests
        │   └── e2e_otlp_receive.rs
        ├── benches/                 # criterion benchmarks (opt-in)
        │   └── ingest_throughput.rs
        └── README.md
```

Mirrors the Python layout: `src/<pkg>/` is `services/<name>/src/`; `tests/` at the service root is `services/<name>/tests/`.

## Root `Cargo.toml` — the workspace

The workspace is the Rust equivalent of UV's monorepo support:

```toml
[workspace]
resolver = "2"
members = [
    "services/collector-rust",
    # add future Rust services here: services/X-rust, libs/Y-rust
]

# Workspace-level dependency declarations — every crate inherits these
# versions when it adds `<dep>.workspace = true` (the "DRY across crates" pattern).
[workspace.dependencies]
# Async runtime
tokio = { version = "1.40", features = ["full"] }

# gRPC
tonic = "0.12"
prost = "0.13"

# OTel
opentelemetry = "0.27"
opentelemetry_sdk = { version = "0.27", features = ["rt-tokio"] }
opentelemetry-otlp = { version = "0.27", features = ["grpc-tonic", "trace", "metrics", "logs"] }
opentelemetry-proto = { version = "0.27", features = ["gen-tonic", "trace", "metrics", "logs"] }

# Storage
clickhouse = { version = "0.13", features = ["lz4", "time"] }

# Observability
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "json"] }

# Serde + config
serde = { version = "1", features = ["derive"] }
serde_yaml = "0.9"
serde_json = "1"

# Errors
anyhow = "1"
thiserror = "1"

# Testing
tokio-test = "0.4"

# Workspace-level lint policy — applies to every crate
[workspace.lints.rust]
unsafe_code = "forbid"
missing_docs = "warn"

[workspace.lints.clippy]
pedantic = { level = "warn", priority = -1 }
nursery = { level = "warn", priority = -1 }
unwrap_used = "deny"          # forbid .unwrap() in production code
expect_used = "warn"          # tolerate .expect() but call it out
missing_errors_doc = "warn"
must_use_candidate = "warn"

# Release profile — optimized for binary size + cold start
[profile.release]
lto = "thin"
codegen-units = 1
strip = true
panic = "abort"

# Profile for the bake-off benchmarks — same as release but with debug symbols
[profile.bench-release]
inherits = "release"
debug = true
strip = false
```

Then each crate's `Cargo.toml` is short:

```toml
[package]
name = "sentinel-collector"
version = "0.1.0-alpha"
edition = "2021"
rust-version = "1.75"
license = "Apache-2.0"

[dependencies]
tokio = { workspace = true }
tonic = { workspace = true }
opentelemetry = { workspace = true }
# ...

[dev-dependencies]
tokio-test = { workspace = true }

[lints]
workspace = true
```

The same `cargo add tokio` works inside any crate — but the version is governed once, at the workspace level. This is the DRY win UV gets via shared groups.

## `rust-toolchain.toml` — the `.python-version` equivalent

```toml
[toolchain]
channel = "1.83.0"                   # pin the Rust version exactly
components = [
    "rustfmt",
    "clippy",
    "rust-docs",
    "rust-analyzer",                 # IDE / LSP — every contributor gets it
]
targets = ["x86_64-unknown-linux-musl"]  # for distroless container builds
profile = "minimal"
```

A contributor running `cd sentinel/services/collector-rust && cargo build` automatically gets Rust 1.83.0 installed by `rustup`. No "what version are you running?" debates.

## `rustfmt.toml` — formatting

```toml
edition = "2021"
max_width = 100
hard_tabs = false
tab_spaces = 4
newline_style = "Unix"
imports_granularity = "Crate"
group_imports = "StdExternalCrate"
reorder_imports = true
reorder_modules = true
use_field_init_shorthand = true
use_try_shorthand = true
```

Equivalent of `[tool.ruff.format]`. Run with `cargo fmt`.

## `clippy.toml` — extra lint nuance

Most clippy config lives in `[workspace.lints.clippy]` (above). Use `clippy.toml` only when you need lint configuration that isn't an enable/disable:

```toml
# Allow very long single-line strings in tests
max-single-char-names = 4

# Cognitive complexity threshold (default is 25)
cognitive-complexity-threshold = 30

# Disallow specific functions
disallowed-methods = [
    { path = "std::env::var", reason = "Use the `figment` config loader instead" },
]
```

## `deny.toml` — `cargo-deny` config (security + license policy)

`cargo-deny` is roughly `pip-audit` + `pip-licenses` rolled into one. Install once: `cargo install cargo-deny --locked`.

```toml
[advisories]
db-path = "~/.cargo/advisory-db"
db-urls = ["https://github.com/rustsec/advisory-db"]
vulnerability = "deny"
unmaintained = "warn"
yanked = "deny"
notice = "warn"
ignore = []  # add advisory IDs here only with an Issue link

[licenses]
unlicensed = "deny"
allow = ["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unicode-DFS-2016"]
copyleft = "deny"  # no GPL/LGPL/AGPL — license-incompatible with most internal use
allow-osi-fsf-free = "neither"
confidence-threshold = 0.93

[bans]
multiple-versions = "warn"
wildcards = "deny"  # no `version = "*"` in Cargo.toml
deny = []  # add bans like { name = "openssl", version = "*", reason = "use rustls instead" }
```

## `justfile` — the task runner (same as Python)

UV projects use `make` or `just`. We standardize on `just`. Every Rust service supports the same `just` targets a Python service does:

```makefile
# Default: list targets
default:
    @just --list

# Install toolchain + system deps + dev tools
setup:
    rustup component add rustfmt clippy rust-analyzer
    cargo install --locked cargo-nextest cargo-deny cargo-audit cargo-watch

# Build (debug)
build:
    cargo build

# Build (release, what CI ships)
build-release:
    cargo build --release

# Run the main binary
run *args:
    cargo run -- {{args}}

# Run tests — uses nextest for parallel + better output
test *args:
    cargo nextest run {{args}}

# Format check (CI gate 1)
fmt-check:
    cargo fmt --all -- --check

# Format apply (local)
fmt:
    cargo fmt --all

# Lint (CI gate 2)
lint:
    cargo clippy --all-targets --all-features -- -D warnings

# Security audit (CI gate 3)
audit:
    cargo audit

# License + dependency policy (CI gate 4)
deny:
    cargo deny check

# Docs build (CI gate 5 — catches broken intra-doc links)
doc:
    cargo doc --no-deps --document-private-items

# All CI gates locally
ci: fmt-check lint test audit deny doc

# Watch mode for development
watch:
    cargo watch -x check -x 'nextest run'

# Clean build artefacts
clean:
    cargo clean
```

A Sentinel contributor types `just setup` after cloning, then `just ci` before opening a PR. Same muscle memory as `uv sync && pytest && ruff check && mypy` in Python land.

## CI mapping to the Crew B 7-gate spec

The Crew B WoW defines 7 CI gates. Per-language profiles map them:

| Crew B gate | Python (via UV) | Rust |
|---|---|---|
| 1. Linter (style) | `ruff check` | `cargo clippy --all-targets -- -D warnings` |
| 2. Type check | `mypy --strict` | (built into `cargo build`) |
| 3. Tests | `pytest >80%` | `cargo nextest run` (+ `cargo-llvm-cov` for coverage) |
| 4. Security scan | `bandit + safety` | `cargo audit` + `cargo deny check` |
| 5. Markdown lint | `markdownlint` | `markdownlint` (same tool — language-agnostic) |
| 6. AI review | CodeRabbit | CodeRabbit (same — language-agnostic) |
| 7. Build | `uv build` | `cargo build --release` + Docker multi-stage |

GitHub Actions example (see `.github/workflows/rust-ci.yml` when added):

```yaml
- uses: dtolnay/rust-toolchain@stable
  with:
    components: rustfmt, clippy
- uses: Swatinem/rust-cache@v2
- run: just ci
```

## `.pre-commit-config.yaml` — local fast-feedback (Rust hooks added)

Same `pre-commit` framework as Python; just add Rust hooks:

```yaml
repos:
  # Python hooks (unchanged from briefing-hub etc.)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.0
    hooks:
      - id: ruff
      - id: ruff-format

  # Rust hooks
  - repo: https://github.com/doublify/pre-commit-rust
    rev: v1.0
    hooks:
      - id: fmt
        args: ["--all", "--", "--check"]
      - id: clippy
        args: ["--all-targets", "--all-features", "--", "-D", "warnings"]

  # Markdown (same as Python projects)
  - repo: https://github.com/igorshubovych/markdownlint-cli
    rev: v0.42.0
    hooks:
      - id: markdownlint
```

## Lock file policy

| What | Lock file behaviour |
|---|---|
| Workspace ships a binary (the Collector) | **Commit `Cargo.lock`** — reproducible deployments |
| Workspace ships only libraries | Don't commit `Cargo.lock` — downstream picks versions |
| Sentinel today | Commit. The Collector is a deployable binary. |

This mirrors UV's `uv.lock` commit policy.

## Dependency management

- **Pin in workspace `[workspace.dependencies]`** — single source of truth, like UV's `[project]`.
- **`cargo update` weekly** — bump dependencies, run `just ci`, open a PR.
- **Renovate / Dependabot** — `.github/dependabot.yml` for automated updates, same cadence as Python projects.
- **Major version bumps** are PRs (not auto-merge), need 2 approvals like everything else.

## Common cargo plugins to install (one-time `just setup`)

These are the "ecosystem" tools — equivalent to UV's "what you do after installing UV":

| Tool | Purpose | Python equivalent |
|---|---|---|
| `cargo-nextest` | Faster, prettier test runner | `pytest-xdist` |
| `cargo-deny` | License + advisory policy | `pip-licenses` + `pip-audit` |
| `cargo-audit` | Security advisories | `pip-audit` |
| `cargo-watch` | Re-run on file change | `watchfiles` / `pytest-watch` |
| `cargo-machete` | Find unused dependencies | `deptry` |
| `cargo-llvm-cov` | Coverage reporting | `pytest-cov` |
| `cargo-expand` | Expand macros for debugging | (n/a) |
| `cargo-flamegraph` | Profiling | `py-spy` |

Most install with `cargo install --locked <name>` once. CI uses a fresh runner so it installs them per-job (cached via `Swatinem/rust-cache`).

## Migrations from cargo defaults

A few non-default decisions worth knowing about:

- **`resolver = "2"`** — required for workspace feature unification with edition 2021. Already the default in new workspaces but not in old ones; we set it explicitly.
- **`panic = "abort"` in release profile** — kills the panic-unwind machinery in release builds. Smaller binary, faster startup, no need for the catch_unwind safety net in a server we restart on panic anyway.
- **`lto = "thin"`** — link-time optimization. Catches more dead code, shrinks binaries. Costs ~30 seconds of build time per release build.
- **`unsafe_code = "forbid"`** at the workspace level — Sentinel does not need unsafe Rust. If you genuinely do (FFI to a C lib), opt in per-crate with an explicit `#![allow(unsafe_code)]` and an Issue explaining why.

## The contributor experience (`just setup` to `just ci`)

This is what we promise a contributor (any contributor — Crew B, an outsider opening a good-first-issue, future-you):

```bash
git clone https://github.com/luanmorenommaciel/sentinel
cd sentinel

# One-time: installs Rust toolchain + cargo plugins
just setup

# Develop
just watch                  # re-runs check + test on every save
just run                    # runs the binary

# Before opening a PR
just ci                     # fmt-check + clippy + test + audit + deny + doc
```

Three minutes from clone to running the Collector. Same vibe as `uv sync && uv run chainlit run` in Python land.

## Open questions (decide in `#crew-b`)

1. **`cargo nextest` vs built-in `cargo test`?** Nextest is faster + nicer output but adds a one-time install. Recommendation: yes — small cost, large quality-of-life win.
2. **`just` vs `cargo make` vs plain `Makefile`?** All work. `just` is what our Python projects use, so the answer is `just` for consistency.
3. **Pin `Cargo.lock` for the workspace, or per-crate?** Workspace-level commit. Single lock file at root.
4. **Acceptable MSRV (minimum supported Rust version)?** `1.75` for the Collector (tonic 0.12 requires it). Stay 1 version behind stable for breathing room. Bump quarterly.
5. **What about `wasm-pack` for a future web UI / dashboard?** Out of scope for Phase 1. Re-open if/when a UI ships.

## See also

- `services/collector-rust/Cargo.toml` — the canonical example crate manifest
- `services/collector-rust/README.md` — the canonical example service README
- `docs/adr/0004-collector-implementation-language.md` — why we're doing Rust at all
- `kb/languages/rust/` — deeper Rust technique KB (idioms, tokio patterns, error handling, async lifetimes)
- `kb/process/crew-b-wow/` — the 7 CI gates this maps to
- Python equivalent in our other projects: `briefing-hub/pyproject.toml`, `duck-quant/pyproject.toml`
