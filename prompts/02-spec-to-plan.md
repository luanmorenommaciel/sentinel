Take our `intent/core-intent.md`, `intent/design-spec.md` and `spec/core-spec.md` files and use
the `/to-tickets` skill to generate a structured `plan/core-plan.md` file.

Detail exact target file locations, step-by-step task execution order, global constraints, and
specific test-based proof-of-completion criteria for each task.

Two deliberate departures from the `/to-tickets` skill, already decided for this repository and
to be preserved:

1. **One combined file** (`plan/core-plan.md`), not one file per ticket under `.scratch/`, and
   nothing published to a tracker — the file is the deliverable.
2. **Tickets do name exact file paths and line numbers**, overriding the skill's "avoid specific
   file paths" rule.

Give every ticket a stable ID (`T01`…), its leg (ADR-0009), its declared disjoint paths, its
blocking edges, and a runnable proof. Any question that must be answered by a human before a
ticket can start becomes a `DEC-*` brief under `plan/decisions/`, not a ticket.
