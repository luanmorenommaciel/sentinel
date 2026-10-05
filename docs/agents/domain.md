# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring
the codebase. Sentinel is **single-context**: one `CONTEXT.md` at the root (not yet written)
plus the shared `docs/adr/`.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — the glossary of domain terms.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. Start from
  [`docs/adr/README.md`](../adr/README.md) for the index.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't
suggest creating them upfront. The `/domain-modeling` skill creates them lazily when terms or
decisions actually get resolved.

## File structure

```
/
├── CONTEXT.md                 ← not yet written
├── docs/adr/                  ← all decisions, system-wide
│   ├── README.md
│   ├── 0004-collector-implementation-language.md
│   └── …
└── services/
    ├── collector-rust/        ← own Cargo.toml, no own CONTEXT.md
    ├── flow-ui/
    └── generator-python/
```

`services/*` each keep a native toolchain, but they are **not** separate domain contexts: no
per-service `CONTEXT.md` or `docs/adr/`. If that changes, add a root `CONTEXT-MAP.md` and
re-run `/setup-matt-pocock-skills`.

Related context, not a substitute for the above:

- [`CLAUDE.md`](../../CLAUDE.md) — pipeline, layout, conventions, gotchas, live status
- [`.claude/docs/CREW_B_GLOSSARY.md`](../../.claude/docs/CREW_B_GLOSSARY.md) — team and
  process vocabulary, including the anti-glossary (OTel is never "Hotel")
- [`contracts/`](../../contracts/) — the contract registry is the authority on boundary
  terms (`bronze.*`, the Pod 1 → Pod 2 input contract)

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis,
a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary
explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing
language the project doesn't use (reconsider) or there's a real gap (note it for
`/domain-modeling`).

## Flag ADR conflicts — never rewrite them

If your output contradicts an existing ADR, surface it explicitly rather than silently
overriding:

> _Contradicts ADR-0007 (bronze = canonical contract), but worth reopening because…_

**ADRs are history, not live state.** Per
[`.claude/rules/pre-pr-discipline.md`](../../.claude/rules/pre-pr-discipline.md), `docs/adr/0*`,
`.claude/sdd/**` and `docs/proposals/` record decisions as they were taken. ADR-0004 weighing
Rust against Go is *correct* even though `collector-go` is gone — rewriting it destroys what
makes the decision readable. Several ADRs also carry a stale `Proposed` status; see the
*Known doc drift* table in [`CLAUDE.md`](../../CLAUDE.md) before treating a status as current.
Only documents asserting the **present** are in scope for updates.
