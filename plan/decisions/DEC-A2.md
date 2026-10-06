# DEC-A2 — ClickHouse hosting and operational owner (and the `SharedMergeTree` half of `[V-3]`)

**Owner** Commander · **Unblocks** T30, T40 directly; 12 tickets transitively (T30–T34, T40–T44, T47, T48)

Tags: **[M]** measured this session · **[S]** per spec §11.1, not re-run · **[D]** document assertion · **[R]** reasoned.

## 1. The question

Who operates ClickHouse in a deployed environment, and is it managed or self-hosted, given that the backfill primitive (`REPLACE PARTITION`) is unverified on a managed provider's `SharedMergeTree`?

## 2. Why it's open

- Operational ownership is recorded as unassigned in three places: `docs/proposals/canonical-read-schema.md:123`, `README.md` §7, and `.claude/CLAUDE.md` (`git show HEAD:.claude/CLAUDE.md`). It is a staffing decision; the technology choice follows from it (`design-spec.md:228`).
- The choice changes the engine under every table. Managed offerings substitute `SharedMergeTree` for `MergeTree` **[D]** `design-spec.md` matrix; the backfill (spec §6.5, T30-T33) rests on `ALTER TABLE … REPLACE PARTITION`.
- A managed provider has no `docker-entrypoint-initdb.d`, so it forces the migration runner (DEC-A3) and forces client TLS on hop 2 (DEC-A4, REQ-H-10).

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **Managed ClickHouse** | `[V-3]` `SharedMergeTree` must be verified first; client TLS becomes mandatory (breaks the purity claim unless DEC-A4 picks a sidecar); version is whatever the provider offers (DEC-I1 interacts) | Self-hosted engine control; local-equals-deployed |
| **Self-host (GKE operator or GCE VM) with a named owner** | Someone must build backup/restore (none exists today **[D]**); HA would likely use `Replicated*` engines, whose `REPLACE PARTITION` behaviour is also unmeasured **[R]** | Cheapest ops surface for a team with no owner |
| **Do not deploy storage this cycle** | Ends the deployment story at the registry (T22-T24); T40, T42-T44 lose their target | Any production claim |

**Recommendation: none on technology.** The evidence is neutral because the deciding input (is there a named owner?) is not in any document. A conditional is supportable: if no owner can be named, only the first and third options avoid creating an unowned platform (this is the design-spec's own argument, `:246-251`). What would break the tie: the Commander naming an owner or declining to.

## 4. Established facts

- **[X] A managed version is not a choice, it is a moving target.** ClickHouse Cloud exposes no engine-version pin (documentation fetched 2026-10-06): release channels and Enterprise-only scheduled windows control *when* an upgrade lands, never *which* version arrives, and the `compatibility` setting preserves old setting defaults rather than the engine version. So the option table's "version is whatever the provider offers" is sharper than it reads — there is nothing to ask the provider for, and nothing to agree with DEC-I1 about. DEC-I1 is decidable without this decision (see `DEC-I1.md` §3); what managed hosting actually costs here is a deployed engine that moves under the 18 silver assertions, which T20 must therefore run against the deployed instance and not only a pinned local one.

- **[M] `SharedMergeTree` cannot be tested locally.** On `clickhouse-server:25.4.13.22`: `CREATE TABLE … ENGINE=SharedMergeTree` → `Code: 56 Unknown table engine SharedMergeTree`. The engine list has `MergeTree` and `Replicated*` variants only.
- **[S]** `REPLACE PARTITION` works on plain `MergeTree` (spec §11.1 `[V-3b]`: destination's pre-existing row gone, 2 rows summing to 3). Not re-run by me.
- **[D, contradicted by §11.1]** `design-spec.md` matrix says `REPLACE PARTITION` on managed is "supported **[V-3]**". Spec §11.1 says that half is unverified. The design-spec row asserts what the spec says is unknown.
- **[R]** If `REPLACE PARTITION` differs on `SharedMergeTree`, spec and plan both say E (backfill) loses its primitive with no alternative that leaves the base tables' engine alone (`spec` §11; `plan` §10 item 1). REQ-D-08 forbids altering the base tables' engine, so that alternative is also blocked by a MUST.
- `[V-4]` (Compose `include:`) is irrelevant here; it concerns the local stack only.

## 5. What it unblocks

T30 (backfill runner; its refusal logic is hosting-independent but the plan blocks it anyway), T40 (deploy), and transitively T31-T34, T41-T44, T47, T48.

## 6. What it cannot settle

- **`SharedMergeTree` + `REPLACE PARTITION`.** Choosing a provider does not verify it. The measurement is concrete: run spec §11.1's `[V-3b]` statements (a source table, a destination with a pre-existing row, `ALTER … REPLACE PARTITION`) against an instance of the candidate provider before E's deployed half is implemented. Whether such an instance can be obtained cheaply is unknown.
- Cost, SLA and provider capabilities: none are in the repo; none are asserted here.
- Backup/restore design under any option.
- Plan wording: T30's own edge says "DEC-A2 must settle it before the deployed half". The *local* half of E (T30-T34 against MergeTree) is arguably not blocked by A2 at all; the plan blocks all of T30 on it. A ruling on splitting local from deployed E would un-stall five tickets.
