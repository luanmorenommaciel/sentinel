# DEC-V3a — Refreshable materialized views vs scheduled-INSERT fallback for `call_edges_1m`

**Owner** Pod 3 · **Unblocks** T29 directly; transitively T33, T34, T37, T39, T46, T47

Tags: **[M]** measured this session · **[S]** per spec §11.1, not re-run · **[D]** document assertion · **[R]** reasoned.

## 1. The question

Does `silver.call_edges_1m` use a `REFRESH EVERY 1 MINUTE` materialized view (`call_edges_1m_rmv`), or a scheduled `INSERT` plus partition swap?

## 2. Why it's open

- It "cannot be an incremental MV": an MV sees one insert block, and a call edge joins a child span to its parent across blocks (`spec` §6.3d; `clickhouse.py:311-331`: joining on `SpanId` alone invented eight phantom edges, 27.6x fan-out without the collapse) **[D]**.
- Spec §11.1 `[V-3a]` records the feature as experimental-gated on both versions and therefore prefers the fallback "or accept the flag as an explicit, recorded risk". The decision exists because of that probe.
- **My re-probe disagrees with it for 25.4** (below), which changes what this decision is.

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **Refreshable MV** | Depends on version (below); full replace of a trailing 24 h per refresh; the one non-deterministic silver object (`now()`), excluded by name from REQ-D-12's determinism assert | Nothing, provided the pinned version does not gate it |
| **Scheduled INSERT + partition swap** | A scheduler per environment, including local `make up` which has none **[R]**; non-atomic across the two UTC-day partitions a trailing 24 h window spans **[R]**; the spec says it "reuses the backfill's primitive", but REQ-E-12 makes `backfill.sh` refuse any range reaching `today()` with no override, and this table is always live **[R]** (a separate script, not `backfill.sh`, would be needed) | The "no new moving part" property |
| **Refreshable MV with `allow_experimental_refreshable_materialized_view=1` on 24.3** | The flag becomes a recorded risk on a version DEC-I1 may drop anyway | Nothing, but it is only relevant if DEC-I1 picks 24.3 |

**Recommendation: refreshable MV, conditional on DEC-I1 picking 25.4 or later.** Evidence supports it as measured: on 25.4.13.22 no setting is needed, the setting is reported `Obsolete`, and the refresh populates the target. The fallback is not free: it needs a scheduler everywhere and cannot reuse `backfill.sh` as specified. The condition that flips this: DEC-I1 choosing 24.3, or DEC-A2 choosing a managed provider whose version gates the feature.

## 4. Established facts

- **[M] Version-dependent gate.** `CREATE MATERIALIZED VIEW p.rmv REFRESH EVERY 1 HOUR TO p.rd AS SELECT count() a FROM p.rt`: 24.3.18.7 fails (`Code: 344 … experimental`); 25.4.13.22 and 26.8.6.5 succeed with `allow_experimental_refreshable_materialized_view` at `1`, `changed=0`, description "Obsolete setting, does nothing". `SYSTEM REFRESH VIEW` on 25.4 wrote 2 rows to `p.rd`.
- **[S, contradicted]** Spec §11.1 says CREATED "only under `allow_experimental_refreshable_materialized_view=1`" on both versions. On 25.4 I could not reproduce that. I do not know how the §11.1 probe was run (image tag, profile, client settings); `design-spec.md:604-612` ("experimental in 24.x, production in later 25.x") agrees with my result, so the spec and its own source disagree.
- **[M]** Not measured: that the refresh *body* in spec §6.3d is correct (it joins `silver.operation_executions`, which my bare probe did not load), that refresh cost stays small on real volume, or behaviour under replicated/shared engines.
- **[D]** Refresh semantics: no `APPEND` means atomic replace of the target (`spec` §6.3d). Not tested here beyond one refresh.
- "Obsolete" shows the *flag* was retired, not that the feature is production-grade; no document or probe measured maturity.

## 5. What it unblocks

T29 ("Do not implement before DEC-V3a"), and via T29: T33, T34, T37, T39, T46, T47.

## 6. What it cannot settle

- Re-run `[V-3a]` on 25.4 inside CI (T29's proof can include the statement without any setting) so that the spec's table is corrected by evidence rather than by this brief.
- Refreshable MV behaviour on `SharedMergeTree` / replicated engines (DEC-A2).
- If the fallback is chosen: where the scheduler runs in each environment (Cloud Run Job or cron on GKE, per DEC-A1) and how `now()`-based swaps handle UTC midnight.
