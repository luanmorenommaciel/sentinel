# W0 decision briefs

One brief per decision ticket in `plan/core-plan.md` §1 (Wave 0). Each brief has six sections: the question, why it is open, options, established facts, what it unblocks, what it cannot settle.

Evidence tags used in every brief: **[M]** measured in the 2026-10-05 session that wrote these briefs · **[S]** measured per `spec/core-spec.md` §11.1 and not re-run · **[D]** asserted in a repo document, not independently verified · **[R]** reasoned. Probe commands and raw output are summarised in each brief; nothing here relies on invented cost, SLA, vendor or capacity figures.

| ID | Question | Owner | Unblocks (direct; transitive count) |
|---|---|---|---|
| [DEC-A1](DEC-A1.md) | Which platform runs the collector, flow-ui and the generator job? | Captain / Commander | T40, T43; 6 |
| [DEC-A2](DEC-A2.md) | Who operates ClickHouse, managed or self-hosted, given `SharedMergeTree` + `REPLACE PARTITION` is unverified? | Commander | T30, T40; 12 |
| [DEC-A3](DEC-A3.md) | What applies DDL where `docker-entrypoint-initdb.d` does not exist? | Pod 3 (Pod 2 consulted) | T05 form only; 0 |
| [DEC-A4](DEC-A4.md) | Does the collector terminate TLS, or the platform edge, or a sidecar? | Pod 2 | T42; 1 (after spike T04) |
| [DEC-I1](DEC-I1.md) | Which single ClickHouse version, and is the generator Compose file deleted? | Pod 1 (file) / Pod 3 (version) | T12; 26 |
| [DEC-I2](DEC-I2.md) | Same-PR doc fixes or disjoint leg paths? | Captain / Commander | T45 (plan says T45-T48); 1 |
| [DEC-D1](DEC-D1.md) | Typed Sentinel keys in silver? (already partly answered in the DDL) | Pod 3 + Pod 2 | none |
| [DEC-V3a](DEC-V3a.md) | *Folded into DEC-I1:* refreshable MV or scheduled INSERT for `call_edges_1m`? Ungated on 25.4, so a consequence of DEC-I1 | Pod 3 (follows DEC-I1) | T29 via DEC-I1; 0 independent |

Transitive counts come from the plan's ticket table (`plan/core-plan.md` §1), following `Blocked by` edges to a DEC node. 33 of 48 implementation tickets sit behind at least one decision (36 before T22's DEC-A1 blocker was removed on 2026-10-05); 15 (T01-T11, T22-T24, T35) sit behind none. DEC-A3 blocks no ticket other than T05's form.

Related probe result: `infra/clickhouse/README.md` (T03 / `[V-4]`).
