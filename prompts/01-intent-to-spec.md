Read our `intent/core-intent.md` (the verified As-Is baseline produced by `00-grill-to-intent.md`)
and convert it into a formal `spec/core-spec.md` document using the `/to-spec` skill.

Define the exact technical requirements, data models / schema changes, endpoint interfaces,
state management changes, and security protocols required. Number every requirement
(`REQ-<area>-<n>`) so the plan and the PR description can cite it.

Capture the design rationale — options weighed, trade-offs taken, and anything you could not
satisfy — in `intent/design-spec.md` (`DSP §n`), beside the spec rather than inside it.
Describe clearly any areas of concern, especially where you cannot satisfy contradicting
policies.

Scope guard: `plan/decisions/DEC-2026-10-06-local-scope.md` rules this cycle local, Docker +
Make only. Do not specify a remote platform, a hosted ClickHouse provider, or TLS.
