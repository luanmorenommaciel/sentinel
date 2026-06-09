---
name: arch-review
description: Review how a repository communicates its architecture — READMEs, ADRs, Mermaid diagrams, architecture docs, and contracts — against the seven architecture-communication principles, and emit a structured findings report (visual hierarchy · contracts · ownership · storytelling · recommendations). Use before an architecture/project review, when a diagram changes, or to audit any repo's architecture docs.
argument-hint: "[<path>] [--diagram-only] [--fix] [--audience=<exec|engineer|reviewer>]"
---

# /arch-review

Audits how a repository **communicates** its architecture and returns a findings report: does the artifact make its durable assets (contracts, boundaries, ownership) outrank its disposable details (implementations)? Repo-agnostic — runs against Sentinel or any other project.

## Usage

```text
/arch-review                          # audit repo-root README + docs/ + ADRs + contracts
/arch-review <path>                   # audit a specific file or directory
/arch-review --diagram-only           # only the Mermaid/diagram blocks
/arch-review --fix                    # also propose corrected diagrams/labels (diff; no commit)
/arch-review --audience=exec          # judge altitude (P1) against a target audience
```

Examples:
- `/arch-review README.md`
- `/arch-review services/collector-rust --fix`
- `/arch-review docs/adr/0005-clickhouse-storage-schema.md --audience=reviewer`

---

## What it does

1. **Gather** — locate the architecture surface: READMEs, `docs/adr/**`, `docs/contracts/**`, architecture docs, and every fenced `mermaid` block.
2. **Classify (P0)** — for each artifact the agent first establishes diagram type · audience · intended claim · what's decisive, and picks the matching rubric (prevents false positives on non-boundary or implementation-decisive diagrams).
3. **Analyze** — apply the P0→P7 framework + anti-pattern catalogue through the rubric P0 selected.
4. **Report** — emit findings across six lenses (classification · hierarchy+accessibility · contract · ownership+trust boundaries · storytelling · recommendations), each traced to a principle and a `file:line`, severity-rated.

---

## Execution steps

### Step 1: Gather the architecture surface

Resolve scope (arg or repo root), then collect the inputs the report is built from.

```text
Glob("**/README.md"); Glob("docs/adr/**/*.md"); Glob("docs/contracts/**/*.md")
Grep("```mermaid", output_mode="files_with_matches")   # every diagram block
Read(<each candidate>)                                  # READMEs, ADRs, contract docs
```

If no architecture surface is found, stop and say so (don't invent findings).

### Step 2: Run the review

Dispatch the specialist agent with the gathered inputs and the requested flags.

```text
Agent(subagent_type="architecture-visualization-reviewer",
      description="arch-comms audit",
      prompt="Classify each artifact (P0: type, audience, intended claim, what's decisive),
              then apply P0→P7 + the anti-pattern catalogue to <inputs>.
              Audience=<flag or unstated→ask>. diagram_only=<bool>. propose_fix=<bool>.
              Honor the contract-primacy safeguard (don't flag A1 on implementation-decisive
              artifacts) and the boundary taxonomy (flag missing trust boundaries, A11).
              Return the standard findings report (classification, verdict, emphasis delta,
              findings, change set, confidence, open questions).")
```

The agent reads `.claude/kb/communication/architecture-diagramming/` first — starting with the P0 gate (`concepts/diagram-type-rubrics.md`). If the diagram type, intended claim, audience, or what's-decisive is ambiguous, it asks before judging (don't guess intent — that's how false positives happen).

### Step 3: Emit the report

```text
ARCH-REVIEW RESULTS
───────────────────
Classification: type · audience · intended claim · what's decisive  (P0)
Verdict:        PASS | REVISE | REWORK — "tells X, should tell Y"
Emphasis delta: <table: element · decision-relevance · weight · over/under/ok>
Findings:       [Pn / Ax] severity · structural|judgment · file:line · what · why · fix
  • Visual hierarchy + accessibility (salience, channel collisions, color-only/grayscale)
  • Contract analysis (under- OR over-representation, versioning, drift)
  • Ownership + trust boundaries (one-box-one-owner, seams, missing trust perimeter)
  • Storytelling (receive·guarantee·deliver, altitude)
Recommendations: minimal ordered change set (+ corrected Mermaid if --fix)
Confidence:     per major finding (structural = high; judgment = opinion)
```

---

## Flags

| Flag | Description |
|------|-------------|
| `--diagram-only` | Restrict to diagram blocks; skip prose audit |
| `--fix` | Propose corrected diagrams/labels as a diff — does **not** commit |
| `--audience=<role>` | Judge P1 altitude against `exec` / `engineer` / `reviewer` |
| `--type=<kind>` | Hint the P0 classification (`flow`/`sequence`/`state`/`er`/`deployment`/`dependency`/`c4`/`status`) when the artifact is ambiguous |
| `--dry-run` | List what would be reviewed without running the agent |

---

## Conventions

- **Findings, not silent edits.** Default output is a report; artifacts change only under `--fix` with the user's review.
- **Idempotent.** Re-running on an unchanged repo yields the same findings.
- **Mermaid for any proposed diagram** (project rule — never ASCII art).
- **No emojis** in prose; status glyphs (✅/🔶/⏳) are allowed *inside diagram node labels* only.
- **Attribution.** If `--fix` results are committed later, `Co-Authored-By` trailers apply.

---

## Conventions for files this skill produces

| Path pattern | Format | Notes |
|---|---|---|
| (stdout) findings report | text | default — nothing written |
| `<reviewed-file>` (only with `--fix` + approval) | `.md` | corrected diagram/labels patched in place |

---

## Examples

```bash
# Example 1: pre-review audit of the whole repo
/arch-review

# Example 2: fix the README diagram for an architecture review
/arch-review README.md --fix --audience=reviewer

# Example 3: just the diagrams, no prose
/arch-review docs/ --diagram-only
```

---

## When NOT to use

- You want the architecture *designed or validated for correctness* → `the-planner` / domain SME.
- You want a README *written* from scratch → `/readme-maker`.
- You want an audience-calibrated *explanation authored* → `adaptive-explainer` agent.
- You want *code* reviewed → `/code-review` or `code-reviewer`.

---

## Notes

- Repo-agnostic: the KB principles are first-party and project-independent; only the drift checks (terminology, contract versions) use Sentinel-specific sources when present.
- The skill is the thin driver; the `architecture-visualization-reviewer` agent holds the judgment.
- Surfaces a KB gap? Close it with `/enrich-kb architecture-diagramming`.

---

## Related

- `architecture-visualization-reviewer` agent — the worker that holds the review framework
- `/readme-maker` — when the README must be authored, not just reviewed
- `adaptive-explainer` agent — when output must be authored for a specific audience
- `.claude/kb/communication/architecture-diagramming/index.md` — the P0→P7 framework + safeguard
- `.claude/kb/communication/architecture-diagramming/concepts/diagram-type-rubrics.md` — the P0 gate
- `.claude/kb/communication/architecture-diagramming/concepts/boundary-types.md` — ownership/trust/network/consistency
- `.claude/kb/contracts/index.md` — what a contract is (for the contract-representation lens)

---

*Authored from `.claude/skills/_template.md.example`. Update the template when the skill shape evolves.*
