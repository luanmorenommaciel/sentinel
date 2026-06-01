# Sentinel root task runner — language-agnostic coordinator.
#
# Pattern: this file delegates to per-component justfiles. Each Sentinel
# component (services/collector-rust/, services/collector-go/, services/generator/)
# owns its own justfile with language-specific recipes. The root only
# orchestrates cross-component workflows.
#
# Two ways to drive a single component:
#   just rust-ci                        # delegate from root
#   cd services/collector-rust && just ci   # work directly inside the component
#
# Both produce identical results.
#
# See .claude/docs/RUST_PROJECT_STANDARDS.md for the polyglot scoping rule.

# Default: list available recipes
default:
    @just --list

# ── Cross-cutting ──────────────────────────────────────────────────────────

# Lint all markdown files in the repo.
docs-lint:
    @if command -v markdownlint >/dev/null 2>&1; then \
        markdownlint '**/*.md' --ignore node_modules --ignore target --ignore .claude/kb/_templates; \
    else \
        echo "markdownlint not installed; skipping (install: npm i -g markdownlint-cli)"; \
    fi

# ── Rust component (services/collector-rust/) ──────────────────────────────

rust-setup:
    cd services/collector-rust && just setup
rust-build:
    cd services/collector-rust && just build
rust-test *args:
    cd services/collector-rust && just test {{args}}
rust-fmt:
    cd services/collector-rust && just fmt
rust-fmt-check:
    cd services/collector-rust && just fmt-check
rust-lint:
    cd services/collector-rust && just lint
rust-audit:
    cd services/collector-rust && just audit
rust-deny:
    cd services/collector-rust && just deny
rust-ci:
    cd services/collector-rust && just ci

# ── Python component (services/generator/) ─ added once Pod 1 lands ──────
# py-setup:
#     cd services/generator && uv sync
# py-test *args:
#     cd services/generator && uv run pytest {{args}}
# py-ci:
#     cd services/generator && uv run ruff check && uv run mypy --strict && uv run pytest

# ── Go component (services/collector-go/) ─ added post-bake-off if Go wins ──
# go-test:
#     cd services/collector-go && just test
# go-ci:
#     cd services/collector-go && just ci

# ── All components, all gates ──────────────────────────────────────────────

# Bootstrap everything a new contributor needs.
setup: rust-setup
    @echo "Setup complete. See .claude/docs/RUST_PROJECT_STANDARDS.md for next steps."

# Run every component's CI gates + cross-cutting checks.
# Add py-ci / go-ci to this chain when those components land.
ci: rust-ci docs-lint
    @echo "All CI gates passed."
