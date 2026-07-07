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

## Scoping principle (polyglot monorepo)

Sentinel is a **polyglot monorepo**: the Collector (Rust) is one of N peer components alongside `services/generator/` (Python/UV), `services/collector-go/` (Go), future watchers, the action dispatcher, and `infra/`. The scoping rule:

- **Language-specific config lives inside the component directory it governs** — `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `rustfmt.toml`, `clippy.toml`, `deny.toml` live at `services/collector-rust/`. Same pattern for `pyproject.toml`/`uv.lock` at `services/generator/` and `go.mod` at `services/collector-go/`.
- **Cross-cutting config lives at the repo root** — `justfile` (delegates per-language), `.pre-commit-config.yaml` (multi-language hooks), `.markdownlint.json`, `.editorconfig`, `.github/workflows/`, top-level `README.md`, `docs/`, `infra/`.

This keeps every component self-contained (`cd services/X && just ci` always works) while letting the root coordinate (`just ci` at root walks every component). It also lets `.github/workflows/rust-ci.yml` use `paths: [services/collector-rust/**]` so a Python-only PR doesn't trigger Rust builds.

> **Note on `rust-toolchain.toml`:** `rustup` walks *up* the directory tree to find it. Keeping it at `services/collector-rust/` scopes the pinned 1.83.0 toolchain to that subtree only — an adjacent Rust tool elsewhere in the repo picks its own toolchain.

> **Note on Cargo workspaces:** Today there is exactly one Rust crate, so a workspace adds zero value. When a second Rust crate appears, promote `services/collector-rust/Cargo.toml` to a `[workspace]` in place, or create `services/Cargo.toml` as a workspace governing multiple Rust members — defer the choice until you actually have N≥2 crates (YAGNI).

## The mapping at a glance

All paths below are relative to `services/collector-rust/` unless noted as **(repo root)**.

| UV / `pyproject.toml` | Rust equivalent | Where it lives |
|---|---|---|
| `[project]` metadata | `[package]` | `Cargo.toml` |
| `dependencies = [...]` | `[dependencies]` | `Cargo.toml` |
| `[project.optional-dependencies] dev` | `[dev-dependencies]` | `Cargo.toml` |
| `requires-python = ">=3.11"` | `rust-version = "1.75"` + `rust-toolchain.toml` | `Cargo.toml` + `rust-toolchain.toml` |
| `uv.lock` | `Cargo.lock` (auto-generated) | `Cargo.lock` (binaries: commit; libs: gitignore) |
| `uv sync` | `cargo build` | (built into cargo) |
| `uv run <script>` | `cargo run --bin <name>` | (built into cargo) |
| `uv add <pkg>` | `cargo add <pkg>` | (built into cargo) |
| `uv pip install -e .` | `cargo build -p <pkg>` (workspace) | (built into cargo) |
| `[tool.ruff]` (lint) | `[lints]` in `Cargo.toml` + `clippy.toml` | `Cargo.toml` + `clippy.toml` |
| `[tool.ruff.format]` | `rustfmt.toml` | `rustfmt.toml` |
| `[tool.mypy]` | — (Rust types are checked by the compiler) | n/a |
| `[tool.pytest.ini_options]` | `#[test]` + `cargo test` or `cargo nextest` | (built into cargo) |
| `pre-commit` config | same `pre-commit` framework, Rust hooks scoped to subtree | `.pre-commit-config.yaml` **(repo root)** |
| `.venv/` | `target/` (build artefacts, gitignored) | n/a |
| `.python-version` | `rust-toolchain.toml` | `rust-toolchain.toml` |
| `uv workspace` | `[workspace]` — defer until N≥2 Rust crates | (future) `services/collector-rust/Cargo.toml` or `services/Cargo.toml` |
| `make dev` / `just test` | `just` recipes split: root delegates, component implements | `justfile` **(repo root)** + `justfile` |

## The Sentinel Rust project layout

For any Rust service in this repo (`services/collector-rust/`, future `services/X-rust/`):

```text
sentinel/
├── justfile                         # ROOT — cross-cutting task runner (delegates per-language)
├── .pre-commit-config.yaml          # ROOT — multi-language hooks (Rust + Python + markdown)
├── .markdownlint.json               # ROOT — cross-cutting
├── .editorconfig                    # ROOT — cross-cutting
├── .github/workflows/
│   ├── rust-ci.yml                  # paths: [services/collector-rust/**]
│   ├── python-ci.yml                # paths: [services/generator/**]
│   └── go-ci.yml                    # paths: [services/collector-go/**]
└── services/
    ├── collector-rust/              # ── Rust component, fully self-contained ──
    │   ├── Cargo.toml               # package manifest (becomes [workspace] if Rust grows to N≥2 crates)
    │   ├── Cargo.lock               # committed (we ship a binary)
    │   ├── rust-toolchain.toml      # rustup pin — only scopes this subtree
    │   ├── rustfmt.toml             # format rules
    │   ├── clippy.toml              # extra lint config (when needed)
    │   ├── deny.toml                # cargo-deny: license + security policy
    │   ├── justfile                 # Rust-specific recipes, invoked by root justfile
    │   ├── src/
    │   │   ├── main.rs              # binary entry
    │   │   ├── lib.rs               # library entry (for testability)
    │   │   └── ...
    │   ├── tests/                   # integration tests
    │   │   └── e2e_otlp_receive.rs
    │   ├── benches/                 # criterion benchmarks (opt-in)
    │   │   └── ingest_throughput.rs
    │   └── README.md
    ├── collector-go/                # ── Go component, sibling (post-bake-off) ──
    │   ├── go.mod / go.sum
    │   ├── .golangci.yml
    │   └── justfile
    └── generator/                   # ── Python component (Pod 1) ──
        ├── pyproject.toml
        ├── uv.lock
        └── justfile
```

Mirrors the Python layout: `src/<pkg>/` is `services/<name>/src/`; `tests/` at the service root is `services/<name>/tests/`. Every component is self-contained — `cd services/X && just ci` works without the root being involved.

## `services/collector-rust/Cargo.toml` — today (single crate)

A plain `[package]` manifest with dependencies declared inline, plus lint and profile config that would normally live at workspace level. This is the *current* shape — see the next section for the workspace promotion when a second Rust crate appears.

```toml
[package]
name = "sentinel-collector"
version = "0.1.0-alpha"
edition = "2021"
rust-version = "1.75"
license = "Apache-2.0"
description = "Sentinel OTel Collector — Rust implementation. OTLP gRPC :4317 → ClickHouse."
publish = false

[dependencies]
# Async runtime
tokio = { version = "1.40", features = ["full"] }
tokio-stream = "0.1"
futures = "0.3"

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

[dev-dependencies]
tokio-test = "0.4"

# Lint policy — `unsafe_code = forbid` and `unwrap_used = deny` are the
# load-bearing rules. Move to [workspace.lints] when the workspace exists.
[lints.rust]
unsafe_code = "forbid"
missing_docs = "warn"

[lints.clippy]
pedantic = { level = "warn", priority = -1 }
nursery = { level = "warn", priority = -1 }
unwrap_used = "deny"
expect_used = "warn"
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

## When you grow to N≥2 Rust crates — the workspace promotion

When a second Rust crate appears (a shared library, a sibling service), promote in place — don't pre-emptively scaffold a workspace today. Two options:

1. **In-place promotion** — `services/collector-rust/Cargo.toml` becomes both `[workspace]` and `[package]`, with nested crates under `services/collector-rust/<sub>/`. Best when the new crate is conceptually part of the Collector (a shared lib, a sidecar).
2. **Promote upward** — create `services/Cargo.toml` with `members = ["collector-rust", "X-rust"]`. Best when the new crate is independent.

Either way, the workspace shape looks like this — `[workspace.dependencies]` becomes the single source of truth, and member crates inherit with `workspace = true`:

```toml
# at the workspace root (services/collector-rust/Cargo.toml or services/Cargo.toml)
[workspace]
resolver = "2"
members = ["collector-rust", "X-rust"]   # paths relative to this Cargo.toml

[workspace.dependencies]
tokio = { version = "1.40", features = ["full"] }
tonic = "0.12"
# ... move every shared dep here

[workspace.lints.rust]
unsafe_code = "forbid"

[workspace.lints.clippy]
unwrap_used = "deny"
# ... move the lint block here

[profile.release]
lto = "thin"
codegen-units = 1
strip = true
panic = "abort"
```

Then each member crate's `Cargo.toml` becomes short:

```toml
[package]
name = "sentinel-collector"
version = "0.1.0-alpha"
edition = "2021"
rust-version = "1.75"

[dependencies]
tokio = { workspace = true }
tonic = { workspace = true }
# ...

[lints]
workspace = true
```

`cargo add tokio` still works inside any member crate, but the version is governed once. This is the DRY win UV gets via shared dependency groups. **Defer this promotion until a second crate actually exists** — the cost to retrofit is ~5 minutes.

## `services/collector-rust/rust-toolchain.toml` — the `.python-version` equivalent

Lives at `services/collector-rust/` (not the repo root) so the toolchain pin scopes to this component's subtree only. `rustup` walks *up* the directory tree to find it, so any `cargo` command run inside `services/collector-rust/` (or below) picks up Rust 1.83.0 automatically; commands elsewhere in the repo use whatever the contributor's default toolchain is.

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

## `services/collector-rust/rustfmt.toml` — formatting

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

Equivalent of `[tool.ruff.format]`. Run with `cargo fmt` (from inside the Rust component).

## `services/collector-rust/clippy.toml` — extra lint nuance

Most clippy config lives in `[lints.clippy]` (or `[workspace.lints.clippy]` post-promotion). Use `clippy.toml` only when you need lint configuration that isn't an enable/disable:

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

## `services/collector-rust/deny.toml` — `cargo-deny` config (security + license policy)

`cargo-deny` is roughly `pip-audit` + `pip-licenses` rolled into one. Install once: `cargo install cargo-deny --locked`. Lives in the Rust component (not at repo root) so each language enforces its own policy.

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

## `justfile` — task runners (root delegates, component implements)

UV projects use `make` or `just`. We standardize on `just`. Two-tier layout:

- **Root `/justfile`** — language-agnostic, delegates per-component. A contributor types `just ci` at the root to run all CI gates across every language.
- **`services/<component>/justfile`** — language-specific recipes. A contributor inside the component can `cd services/collector-rust && just ci` directly without involving the root.

### Root `/justfile` (the coordinator)

```makefile
# Default: list available recipes across all components
default:
    @just --list

# ── Cross-cutting ──
docs-lint:
    markdownlint '**/*.md' --ignore node_modules --ignore target

# ── Rust component (delegates) ──
rust-setup:
    cd services/collector-rust && just setup
rust-build:
    cd services/collector-rust && just build
rust-test *args:
    cd services/collector-rust && just test {{args}}
rust-ci:
    cd services/collector-rust && just ci

# ── Python component (delegates) ──
py-setup:
    cd services/generator && uv sync
py-test *args:
    cd services/generator && uv run pytest {{args}}
py-ci:
    cd services/generator && uv run ruff check && uv run mypy --strict && uv run pytest

# ── All gates, all languages ──
setup: rust-setup py-setup
ci: rust-ci py-ci docs-lint
```

### `services/collector-rust/justfile` (the Rust implementation)

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

# All Rust CI gates locally
ci: fmt-check lint test audit deny doc

# Watch mode for development
watch:
    cargo watch -x check -x 'nextest run'

# Clean build artefacts
clean:
    cargo clean
```

A Sentinel contributor types `just setup` at the root after cloning (which delegates to per-component setups), then `just ci` before opening a PR (runs every component's gates). Working in a single component? `cd services/collector-rust && just ci` is the tighter loop. Same muscle memory as `uv sync && pytest && ruff check && mypy` in Python land — but now polyglot-aware.

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

GitHub Actions — per-language workflows under `.github/workflows/` so a Python-only PR doesn't run Rust gates and vice versa:

```yaml
# .github/workflows/rust-ci.yml
on:
  pull_request:
    paths: [services/collector-rust/**]
jobs:
  ci:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: services/collector-rust
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: services/collector-rust
      - run: just ci
```

## Root `.pre-commit-config.yaml` — local fast-feedback (multi-language)

The pre-commit config is **cross-cutting** and lives at the repo root. The same hook framework drives Python, Rust, and markdown. Rust hooks use `files:` to scope to the Rust subtree:

```yaml
repos:
  # Python hooks (scoped to the Python component)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.0
    hooks:
      - id: ruff
        files: ^services/generator/
      - id: ruff-format
        files: ^services/generator/

  # Rust hooks (scoped to the Rust component)
  - repo: https://github.com/doublify/pre-commit-rust
    rev: v1.0
    hooks:
      - id: fmt
        files: ^services/collector-rust/
        args: ["--manifest-path", "services/collector-rust/Cargo.toml", "--all", "--", "--check"]
      - id: clippy
        files: ^services/collector-rust/
        args: ["--manifest-path", "services/collector-rust/Cargo.toml", "--all-targets", "--all-features", "--", "-D", "warnings"]

  # Markdown — repo-wide
  - repo: https://github.com/igorshubovych/markdownlint-cli
    rev: v0.42.0
    hooks:
      - id: markdownlint
```

## Lock file policy

`Cargo.lock` lives next to its `Cargo.toml`, not at the repo root.

| What | Lock file behaviour |
|---|---|
| Crate ships a binary (the Collector) | **Commit `services/collector-rust/Cargo.lock`** — reproducible deployments |
| Crate ships only libraries | Don't commit `Cargo.lock` — downstream picks versions |
| Sentinel today | Commit. The Collector is a deployable binary. |

This mirrors UV's `uv.lock` commit policy.

## Dependency management

- **Pin in `[dependencies]`** today; promote to `[workspace.dependencies]` post N≥2-crate workspace promotion.
- **`cargo update` weekly** — bump dependencies, run `just ci`, open a PR.
- **Renovate / Dependabot** — `.github/dependabot.yml` for automated updates, with per-component `directory:` entries so updates target the right `Cargo.toml`.
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
- **`unsafe_code = "forbid"`** at the crate level (workspace level post-promotion) — Sentinel does not need unsafe Rust. If you genuinely do (FFI to a C lib), opt in per-crate with an explicit `#![allow(unsafe_code)]` and an Issue explaining why.

## The contributor experience (`just setup` to `just ci`)

This is what we promise a contributor (any contributor — Crew B, an outsider opening a good-first-issue, future-you):

```bash
git clone https://github.com/luanmorenommaciel/sentinel
cd sentinel

# One-time: installs Rust toolchain + Python UV + cargo plugins (delegates per-component)
just setup

# Work in the Rust component (tighter loop)
cd services/collector-rust
just watch                  # re-runs check + test on every save
just run                    # runs the binary

# Before opening a PR, from anywhere in the repo
cd /path/to/sentinel        # back to repo root
just ci                     # runs every component's CI gates + cross-cutting docs lint
```

Three minutes from clone to running the Collector. Same vibe as `uv sync && uv run chainlit run` in Python land — but the polyglot version is honest about which component you're in.

## Open questions (decide in `#crew-b`)

1. **`cargo nextest` vs built-in `cargo test`?** Nextest is faster + nicer output but adds a one-time install. Recommendation: yes — small cost, large quality-of-life win.
2. **`just` vs `cargo make` vs plain `Makefile`?** All work. `just` is what our Python projects use, so the answer is `just` for consistency.
3. **`Cargo.lock` at root or per-crate?** Per-crate — `services/collector-rust/Cargo.lock`. Matches the per-component scoping rule. When Rust grows to a workspace, the lock file moves with the workspace root.
4. **Acceptable MSRV (minimum supported Rust version)?** `1.75` for the Collector (tonic 0.12 requires it). Stay 1 version behind stable for breathing room. Bump quarterly.
5. **What about `wasm-pack` for a future web UI / dashboard?** Out of scope for Phase 1. Re-open if/when a UI ships.

## See also

- `services/collector-rust/Cargo.toml` — the canonical example crate manifest
- `services/collector-rust/README.md` — the canonical example service README
- `docs/adr/0004-collector-implementation-language.md` — why we're doing Rust at all
- `kb/languages/rust/` — deeper Rust technique KB (idioms, tokio patterns, error handling, async lifetimes)
- `kb/process/crew-b-wow/` — the 7 CI gates this maps to
- Python equivalent in our other projects: `briefing-hub/pyproject.toml`, `duck-quant/pyproject.toml`
