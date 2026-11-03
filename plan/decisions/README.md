# W0 decision briefs

**Current-cycle rulings (2026-10-06):** see [DEC-2026-10-06-local-scope.md](DEC-2026-10-06-local-scope.md)
for the Commander decisions on local Docker/Make scope, deferred TLS, and same-PR docs.

One brief per decision ticket in `plan/core-plan.md` §1 (Wave 0). Each brief has six sections: the question, why it is open, options, established facts, what it unblocks, what it cannot settle.

Evidence tags used in every brief: **[M]** measured in the 2026-10-05 session that wrote these briefs · **[S]** measured per `spec/core-spec.md` §11.1 and not re-run · **[D]** asserted in a repo document, not independently verified · **[R]** reasoned. Probe commands and raw output are summarised in each brief; nothing here relies on invented cost, SLA, vendor or capacity figures.

| ID | Question | Owner | Unblocks (direct; transitive count) |
|---|---|---|---|
| [DEC-A1](DEC-A1.md) | Local Docker + Make only for this cycle; remote platform remains open | Captain / Commander | T40, T43; local scope resolved |
| [DEC-A2](DEC-A2.md) | Local-only Docker/ClickHouse; deployed owner/provider remains open | Commander | T30, T40; local scope resolved |
| [DEC-A3](DEC-A3.md) | What applies DDL where `docker-entrypoint-initdb.d` does not exist? | Pod 3 (Pod 2 consulted) | T05 form only; 0 |
| [DEC-A4](DEC-A4.md) | TLS deferred for this cycle; design remains open | Pod 2 | T42 deferred |
| [DEC-I1](DEC-I1.md) | Which single ClickHouse version, and is the generator Compose file deleted? | Pod 1 (file) / Pod 3 (version) | T12; 26 |
| [DEC-I2](DEC-I2.md) | Documentation updates in each implementation PR | Captain / Commander | T45–T48 absorbed |
| [DEC-D1](DEC-D1.md) | Typed Sentinel keys in silver? (already partly answered in the DDL) | Pod 3 + Pod 2 | none |
| [DEC-V3a](DEC-V3a.md) | *Folded into DEC-I1:* refreshable MV or scheduled INSERT for `call_edges_1m`? Ungated on 25.4, so a consequence of DEC-I1 | Pod 3 (follows DEC-I1) | T29 via DEC-I1; 0 independent |

Transitive counts come from the plan's ticket table (`plan/core-plan.md` §1), following `Blocked by` edges to a DEC node. **The counts below are the 2026-10-05 state and are superseded.** They read 33 of 48 tickets behind a decision and 15 behind none; after the 2026-10-06 rulings almost nothing is: DEC-A1/A2 settled local scope, DEC-A4 deferred T42, DEC-I2 dissolved T45–T48 into same-PR docs, and DEC-I1 was acted on for the 25.4 pin and the Compose unification. What remains open blocks almost nothing — **DEC-A3** touches only T05's form and **DEC-D1** is deliberately left open until T28. The historical figures: 33 of 48 behind at least one decision (36 before T22's DEC-A1 blocker was removed on 2026-10-05); 15 (T01-T11, T22-T24, T35) behind none.

Related probe result: `infra/clickhouse/README.md` (T03 / `[V-4]`).
