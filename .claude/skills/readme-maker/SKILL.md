---
name: readme-maker
description: Generate a comprehensive, production-ready README.md by analyzing the codebase with explorer + documenter agents. Use when a service/component needs a real README (not the one-line placeholder), or when scope has drifted from the existing README.
---

# /readme-maker

Produces a complete `README.md` for a service or the repo root by dispatching `codebase-explorer` to map the code, then `code-documenter` to write the README from that map.

## Usage

```text
/readme-maker [<path>]
```

- No argument → repo-root README.md
- Path argument → README.md for that service (e.g., `/readme-maker services/collector-rust`)

## What it does

1. **Scope check** — confirms the target path exists and has enough code to document (refuses to over-document an empty scaffold).
2. **Dispatch `codebase-explorer`** — maps the code: entry points, key modules, public API, config surface, dependencies.
3. **Dispatch `code-documenter`** — writes the README from the map, following the Sentinel README convention (see below).
4. **Cross-link** — adds backlinks to relevant ADRs, KBs, and sibling services.
5. **Diagram** — if architecture is non-trivial, includes a Mermaid diagram (never ASCII art).

## Sentinel README convention

Every service README contains (in order):

1. **One-line tagline** — what this service is, in plain English
2. **Status badge** — scaffold / alpha / beta / stable
3. **Why this exists** — the ADR or sync that birthed it
4. **Prerequisites** — toolchain + system deps
5. **Build & run**
6. **Lint + format gates** — the CI gates that block PRs
7. **What's next** — ordered backlog if it's pre-stable
8. **Directory layout** — target tree
9. **Contracts & boundaries** — explicit input/output contracts (per Sync 02 D8)
10. **Attribution** — `Co-Authored-By:` trailer convention
11. **See also** — sibling services, KBs, ADRs

## Conventions

- **Mermaid for diagrams** (the project enforces this — see `.claude/rules/`).
- **No emojis** unless the user explicitly opts in.
- **Honesty about state.** A scaffold says "scaffold." An alpha says "alpha." No "production-ready" claims without evidence.
- **Links must work.** Relative paths resolve from the README's own directory.

## Related

- `codebase-explorer` agent — the worker that maps the code
- `code-documenter` agent — the worker that writes the prose
- `kb/process/crew-b-wow/` — the WoW spec that frames "honest attribution"
