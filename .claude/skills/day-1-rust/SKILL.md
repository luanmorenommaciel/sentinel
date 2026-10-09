---
name: day-1-rust
description: Bootstrap a new Astronaut into Pod 2's Rust path — install toolchain, verify the scaffold, generate the contract module from Pod 1's published schema, and open the first parser PR. Use when an Astronaut joins Pod 2 (or any future Rust service in Sentinel) without prior Rust experience.
argument-hint: "[--dry-run] [--branch <branch>]"
---

# /day-1-rust

A one-shot onboarding skill: takes you from "no Rust toolchain" to "first PR open with a working NDJSON parser against Pod 1's golden file" in ~3 hours. Idempotent — re-running on a partially-set-up env converges to the same state.

This is Pod 2's institutional memory: the path Victor walked in Sprint 1 is captured here so future Astronauts joining Pod 2 don't repeat the discovery.

## Usage

```bash
/day-1-rust                          # full flow: install + verify + scaffold + PR
/day-1-rust --dry-run                # report what would change without writing
/day-1-rust --branch <branch-name>   # use a custom branch name (default: feat/rust-day-1)
```

Examples:
- `/day-1-rust` — for an Astronaut on their first day in Pod 2
- `/day-1-rust --dry-run` — for the Captain to verify the skill is sane before merge
- `/day-1-rust --branch feat/<name>-rust-onboard` — for a second Astronaut joining mid-sprint

## What it does

1. **Pre-flight checks** — confirms repo is `sentinel`, current branch is mergeable, working tree is clean.
2. **Toolchain install** — `rustup` (if missing), pinned channel from `rust-toolchain.toml`, components `rustfmt + clippy + rust-analyzer`.
3. **Scaffold verification** — runs `cargo build` + `cargo test` against `services/collector-rust/` to prove the existing scaffold works.
4. **Contract module generation** — fetches Pod 1's `001-otel-data-generator` branch, reads `contract/schema/otlp_output.schema.json`, dispatches `python-developer` to produce a Pydantic→Rust type mapping, then `rust-specialist` to author `src/contract.rs` based on the mapping.
5. **Parser binary** — generates `src/main.rs` that reads `baseline_seed42.jsonl` (vendored from Pod 1) and prints parsed signal counts.
6. **Golden test** — generates `tests/golden_parse.rs` that asserts all NDJSON lines from the golden file parse without errors.
7. **CI verify** — runs `just ci` (fmt-check + clippy + test + audit + deny + doc) locally.
8. **PR prep** — creates a branch, conventional commit with mandatory attribution trailers, optional `gh pr create` if the user opts in.

## Execution steps

### Step 1: Pre-flight

```text
# Confirm context
git rev-parse --show-toplevel     # must end with /sentinel
git status --porcelain            # must be empty (working tree clean)
git branch --show-current         # must NOT be main (main is protected)
```

If preflight fails: refuse with a clear message; do not proceed.

### Step 2: Toolchain install

```bash
# Check rustup
if ! command -v rustup &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

# Use the pinned toolchain
rustup show           # respects rust-toolchain.toml if present
rustup component add rustfmt clippy rust-analyzer
```

### Step 3: Scaffold verify

```bash
cd services/collector-rust
cargo build            # ~3 min on first build (fetches ~150 crates)
cargo test             # the scaffold-compiles smoke test must pass
cargo fmt --check
cargo clippy --all-targets -- -D warnings
```

If any of these fail: stop. Capture the error. Dispatch `rust-specialist` with the error message.

### Step 4: Contract module generation

```text
# Fetch Pod 1's contract branch (if not already fetched)
Bash("git fetch origin 001-otel-data-generator")

# Vendor the contract files into our branch
Bash("git show origin/001-otel-data-generator:contract/schema/otlp_output.schema.json > contract/schema/otlp_output.schema.json")
Bash("git show origin/001-otel-data-generator:contract/golden/baseline_seed42.jsonl > contract/golden/baseline_seed42.jsonl")

# Dispatch python-developer to map Pydantic models to Rust types
Agent(subagent_type="python-developer", prompt="<see .claude/agents/languages/python-developer.md for mapping brief>")

# Dispatch rust-specialist to author src/contract.rs from the mapping
Agent(subagent_type="rust-specialist", prompt="<author serde-derived enum + variants per the mapping; tag = 'signal_type', rename_all = 'lowercase'>")
```

### Step 5: Parser binary

```text
# rust-specialist authors src/main.rs:
#  - reads contract/golden/baseline_seed42.jsonl via BufReader
#  - serde_json::from_str on each line
#  - matches on signal_type variant; increments counter
#  - prints counts to stdout
#  - returns ExitCode::SUCCESS or FAILURE
Agent(subagent_type="rust-specialist", prompt="<author main.rs per the brief>")
```

### Step 6: Golden test

```text
# test-generator authors tests/golden_parse.rs:
#  - reads contract/golden/baseline_seed42.jsonl
#  - parses each line into the contract enum
#  - asserts no errors, asserts expected variant counts
Agent(subagent_type="test-generator", prompt="<integration test that parses every golden line>")
```

### Step 7: CI verify

```bash
cd services/collector-rust
just ci              # runs all 7-equivalent gates locally
```

### Step 8: PR prep

```bash
git add services/collector-rust contract/schema contract/golden
git commit -m "$(cat <<'EOF'
feat(collector): Rust NDJSON parser against Pod 1 golden contract

Generated via /day-1-rust skill — Pod 2 onboarding artifact.

Adds:
- services/collector-rust/src/contract.rs (serde-derived types from
  Pod 1's otlp_output.schema.json v1.0.0)
- services/collector-rust/src/main.rs (golden-file parser binary)
- services/collector-rust/tests/golden_parse.rs (integration test
  against baseline_seed42.jsonl)
- contract/schema/otlp_output.schema.json (vendored from Pod 1)
- contract/golden/baseline_seed42.jsonl (vendored from Pod 1)

CI: just ci passes locally (fmt + clippy + test + audit + deny + doc).

Refs: ADR-0004 (Collector language) · Pod 1 contract v1.0.0
      · docs/research/learning-roadmap-pod2-rust.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"

# Optional: open the PR
gh pr create --base main --title "feat(collector): Rust NDJSON parser (Day 1)" --body-file <(...)
```

## Output

```text
/DAY-1-RUST RESULTS
───────────────────
Toolchain:           rustup 1.27.1, rustc 1.83.0, cargo 1.83.0
Scaffold verified:   cargo build OK, cargo test OK, clippy clean
Contract generated:  src/contract.rs (3 variants: Log, Span, Metric)
Parser:              src/main.rs reads baseline_seed42.jsonl
Test:                tests/golden_parse.rs — 900 lines parsed, 0 errors
CI:                  just ci passes
Branch:              feat/rust-day-1
Commit:              <hash> — feat(collector): Rust NDJSON parser ...
PR:                  https://github.com/luanmorenommaciel/sentinel/pull/<n>
Next:                Day 2 — implement ClickHouse exporter (per roadmap)
───────────────────
```

## Flags

| Flag | Description |
|------|-------------|
| `--dry-run` | Report what would change; no writes, no installs, no commits |
| `--branch <name>` | Override default branch name `feat/rust-day-1` |
| `--no-pr` | Skip `gh pr create`; leave the commit on the local branch |
| `--skip-install` | Assume toolchain is already installed; skip Step 2 |

## Conventions

- **Idempotent.** Re-running converges. If `src/contract.rs` already exists, `rust-specialist` is dispatched to amend rather than overwrite.
- **Vendored, not symlinked.** Pod 1's contract files are copied into this repo at a specific commit — when Pod 1 updates v1.0.0 → v1.1.0, Pod 2 re-runs `/day-1-rust` (or a future `/sync-contract`) to refresh.
- **Attribution.** Commit message includes mandatory `Co-Authored-By:` trailers per the Crew B contract.
- **No emojis.** Per project rule.
- **Mermaid for any diagrams.** Per project rule.

## When NOT to use

- After Day 1 is complete — re-running once `src/contract.rs` exists is a no-op (idempotent), but the value-add is zero. Use `/enrich-kb rust` to capture learnings instead.
- For Go scaffolding — see the planned `/day-1-go` skill (not yet authored; opens when ADR-0004 picks Go).
- For onboarding outside Pod 2 — Pod 1 (Python) and Pod 3 (ClickHouse) have different onboarding paths.

## Notes

- The skill assumes Pod 1's contract is at `001-otel-data-generator` branch; if Pod 1 reorganizes, the skill needs updating.
- The skill bundles a learning roadmap reference (`docs/research/learning-roadmap-pod2-rust.md`) — re-read it as you go through Days 2–10.
- The 3-hour estimate assumes a developer with general programming experience. First-time programmers should budget more.

## Related

- `/create-skill` — meta-skill for authoring slash commands (this file follows that template)
- `/enrich-kb rust` — capture Rust learnings as you go
- `/adr` — open the bake-off-result ADR (ADR-0005) at end of Sprint 1
- `rust-specialist` agent — dispatched during execution
- `python-developer` agent — dispatched for Pydantic→Rust mapping
- `test-generator` agent — dispatched for golden test
- [`.claude/docs/RUST_PROJECT_STANDARDS.md`](../../docs/RUST_PROJECT_STANDARDS.md) — the project's UV-equivalent Rust setup
- [`docs/research/learning-roadmap-pod2-rust.md`](../../../docs/research/learning-roadmap-pod2-rust.md) — the 10-day Pod 2 plan
- [`docs/adr/0004-collector-implementation-language.md`](../../../docs/adr/0004-collector-implementation-language.md) — why Rust
