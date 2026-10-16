# DEC-A3 — What applies DDL in a deployed environment

**Owner** Pod 3, Pod 2 consulted · **Unblocks** T05 (its form only); no ticket depends on it in the dependency table

Tags: **[M]** measured this session · **[S]** per spec §11.1 · **[D]** document assertion · **[R]** reasoned.

## 1. The question

In a deployed environment, where `docker-entrypoint-initdb.d` does not exist, does the repo apply DDL with its own bash runner (spec §6.2), an off-the-shelf migration tool, or provider tooling?

## 2. Why it's open

- Policy is "the collector issues no DDL, it only `INSERT`s" (`CLAUDE.md` Conventions; `01-bronze-otel.sql:1-22`). The mechanism that enforces it locally is the image entrypoint, which a managed ClickHouse does not expose (`spec` §12.2).
- Spec §6.2 specifies a bespoke runner in detail (ledger table, checksums, exit codes 0/2/3/4, no `down`). Whether bespoke is the right long-term tool is flagged as not an engineering call (`spec` §12.2).
- Hosting (DEC-A2) decides whether the runner is a convenience or the only option (`spec` §12.2, last bullet).

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **Bespoke bash + `clickhouse-client` runner** (spec §6.2) | Code the team owns forever; no `down`; reproduces a framework's job (NFR-11 keeps it dependency-light) | Nothing; it works against any reachable ClickHouse |
| **Off-the-shelf migration tool** | A new dependency and image; its checksum/ledger semantics may not match REQ-A-13/A-14 (refuse on checksum drift, sole writer, exit codes) **[R]**; no specific tool was evaluated here | NFR-11 "Bash + clickhouse-client only" |
| **Provider tooling** | Ties DDL to DEC-A2's choice; no local equivalent | Identical local/deployed path (REQ-A-15) |
| **Keep `init.d` only** | No non-destructive deployed path | REQ-A-04/A-09 |

**Recommendation: none that the evidence forces.** T05 is deliberately small and spec REQ-A-15 (one DDL source, `init.d` entries as symlinks into `migrations/`) keeps the files portable across all of the first three options **[R]**. That bounds the cost of choosing wrong: the SQL stays; only the applier changes. What would break the tie: a Pod 3 statement of whether it wants to own a runner, and a one-time check of an off-the-shelf tool against REQ-A-13 and A-14.

## 4. Established facts

- **[M]** Both `01-bronze-otel.sql` and `02-silver-layer.sql` apply cleanly via `docker-entrypoint-initdb.d` on `clickhouse-server` 24.3.18.7, 25.4.13.22 and 26.8.6.5 with no `CLICKHOUSE_DB` and no `users.d` mount: 9 bronze + 13 silver tables each. DDL applies; the 18 silver assertions were not run (they need data).
- **[M]** The DDL files create their own databases (`01-bronze-otel.sql:24`, `02-silver-layer.sql:11`), so a runner needs no database pre-created for these two files.
- **[D]** Idempotence in the spec lives in the ledger, not the statements (REQ-D-11); `0006` uses `CREATE OR REPLACE VIEW`.
- **[D]** Plan §0 marks `0002`'s grants preceding `0004`'s `silver` database as `[I]`/`[V]` and says to verify "in the same throwaway container used for `[V-4]`". T03 uses `config` only and starts no container, so that verification has no owner. Untested.

## 5. What it unblocks

T05 form only. **The plan lists T05 as `Blocked by —` and in the F1 frontier**, so this decision is not a blocker in the dependency table, contrary to the plan's "four W1 blockers in practice" (`plan` line 68). Transitively nothing waits on it.

## 6. What it cannot settle

- Who operates the runner in a deployed environment (DEC-A2).
- A real `down` story. The spec defers it until the first destructive change (`design-spec.md:1097`).
- Whether grants-before-database ordering holds (see facts); this is a one-line probe, cheap, unowned.
