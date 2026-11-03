# DEC-I1 — One ClickHouse version, and which Compose files are deleted

**Owner** Pod 1 (the generator Compose file), Pod 3 (the version) · **Unblocks** T12 directly; **26 tickets transitively** (T12–T21, T25–T34, T36–T39, T46, T47). It is the largest blocker in W0, not DEC-A3.

Tags: **[M]** measured this session · **[S]** per spec §11.1 · **[D]** document assertion · **[R]** reasoned · **[X]** external vendor documentation, fetched and dated.

## 1. The question

Which single ClickHouse image tag is pinned across the repo, and is `services/generator-python/docker-compose.yaml` deleted?

## 2. Why it's open

- Three pins today: root `docker-compose.yml:7` is `24.3`; CI's `services/collector-rust/infra/docker-compose.yml:26` is `25.4`; the generator's file `:10` is `24.3`, plus `clickstack-all-in-one:latest` **[M]**. CI tests bronze on an engine the local stack does not run, and CI mounts no silver DDL (`spec` §6.7).
- Pod 1 owns the generator file, Pod 3 the version, so neither can decide alone.
- The version interacts with DEC-A2: a managed provider offers its own version, and `spec` §6.7 says "or the newest pinned minor the hosting choice supports".

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **25.4 everywhere**, `include:`, delete generator file | `make reset` once (data is synthetic). **The 18 assertions are now VERIFIED on 25.4 — see §4** | 24.3 as a local baseline |
| **Pin 24.3** | `call_edges_1m` needs the experimental flag (DEC-V3a); CI moves backwards from what it already tests | Ungated refreshable MVs |
| **Keep the generator file**, banner it, move clickstack off 8080 | Two ClickHouse definitions survive, against REQ-I-02; the file keeps plaintext `otelgen_secret` | REQ-I-02, REQ-H-01 as written |

**Recommendation: 25.4 everywhere, `include:`, delete. The evidence supports it, and as of 2026-10-06 there is no residual.** Measured reasons: (a) CI already runs 25.4; (b) refreshable MVs are experiment-gated on 24.3 and not on 25.4 (below); (c) both DDL files apply on both; (d) the 18 assertions pass on 25.4.13.22 with output byte-identical to 24.3.18.7 (#46, measured 2026-10-05, §4).

**The DEC-A2 residual is dissolved, not answered — this decision no longer waits on it.** The earlier framing was "if a managed provider cannot offer 25.4, revisit". It cannot, and neither can it offer 24.3: ClickHouse Cloud does not expose engine-version pinning at all (**[X]**, §4). So no choice of repo pin can be made to match a managed engine, and waiting for DEC-A2 cannot resolve the pin question — it can only reveal that a managed version drifts on the vendor's schedule.

That separates two things the brief had been treating as one:

- **The repo pin governs local Compose and CI**, which are files we own. It is fully decidable today.
- **The deployed engine version is not a pin but a moving fact**, which T20 must assert against continuously and T40 must tolerate. It belongs to DEC-A2's consequences, not to this decision.

Read that way, 25.4 gets strictly stronger: a managed provider tracks recent releases, so it will sit at or ahead of 25.4 and never behind it. Pinning 24.3 locally would put local and CI *behind every managed option*, and behind the experimental-flag boundary that DEC-V3a depends on.

**Two separate approvals are needed, and they are independent:**

| Owner | The ask | If they say no |
|---|---|---|
| **Pod 3** | Pin `clickhouse/clickhouse-server:25.4` as the single repo-wide tag | Pinning 24.3 re-opens DEC-V3a and leaves CI testing an engine the local stack does not run |
| **Pod 1** | Delete `services/generator-python/docker-compose.yaml`, moving its HyperDX/ClickStack and `--delivery direct --init-schema` examples into `services/generator-python/README.md` (T15, REQ-I-06) | Two ClickHouse definitions survive against REQ-I-02, and the file keeps a plaintext credential against REQ-H-01 |

A yes from Pod 3 alone unblocks T12 and the version chain; a yes from Pod 1 alone unblocks nothing on its own. Both are needed for T15 and therefore T19.

## 4. Established facts

- **[M] Both DDL files apply cleanly on three versions.** Throwaway containers with `infra/clickhouse/init.d` mounted read-only, no `CLICKHOUSE_DB`, no `users.d`: `24.3.18.7`, `25.4.13.22` and `26.8.6.5` each produced 9 `bronze` and 13 `silver` tables. DDL only; no data was loaded and no assertion run.
- **[M] The 18 silver assertions PASS on 25.4.13.22, byte-identical to 24.3.18.7.** Closes #46. Method: throwaway containers per version, `infra/clickhouse/init.d` mounted read-only, both DDL files auto-applied on boot, then synthetic `bronze` rows inserted directly (40 traces / 30 logs / 25 gauge / 20 sum) so the non-`POPULATE` MVs fired — no generator, no collector, shared compose volume untouched. MV propagation was exact: 40 → `operation_executions`, 30 → `log_events`, 25+20=45 → `metric_observations`. `clickhouse-client --multiquery < 02-silver-layer.test.sql` → **exit 0, all 18 `throwIf` returned 0, on both versions.** A first run with wall-clock (`now64()`) timestamps showed differing *window* counts between versions (`metric_rollup_windows` 18 vs 15, `service_health_windows` 30 vs 15); re-running with fixed timestamps (`2026-10-05 12:00:00`) made the entire output **byte-identical**, confirming that difference was a minute-bucket artifact of insert timing, not engine divergence.
- **[M] The 24.3 `clickhouse-client` rejects multi-statement `-q`; 25.4 accepts it.** `-q "TRUNCATE a; TRUNCATE b"` → `Code: 62 Multi-statements are not allowed` on 24.3.18.7, succeeds on 25.4.13.22. Relevant to T05: `migrate.sh` must pass `--multiquery` explicitly, or it will behave differently across the two versions.
- **[M] Refreshable MVs differ by version.** `CREATE MATERIALIZED VIEW … REFRESH EVERY 1 HOUR TO …`: on 24.3.18.7, `Code: 344 Refreshable materialized views are experimental`; on 25.4.13.22 and 26.8.6.5 it created without any setting, and `system.settings` reports `allow_experimental_refreshable_materialized_view` as `Obsolete setting, does nothing`. A manual `SYSTEM REFRESH VIEW` on 25.4 populated the target (2 rows). **This contradicts spec §11.1 `[V-3a]`, which says gated on both versions.** The design-spec (`:604-612`) says "experimental in 24.x, production in later 25.x", which agrees with my result and not with §11.1.
- **[M]** `grep -rn 'generator-python/docker-compose'` over live files (excluding plan/spec/intent/research/proposals) finds no reference: nothing live depends on it. It also publishes `4317`, `4318`, `8080`, `8123`, `9000` (`docker-compose.yaml:12-13,41-43`), so it collides with the root stack on `4317` and `8123` as well as `8080`. REQ-I-05 names only `8080`.
- **[D]** It carries `otelgen`/`otelgen_secret` plaintext (`:7,15-18,62-63`); deleting is in policy because a Compose file "asserts the present" (`spec` §6.8).
- **[X] A managed ClickHouse cannot be pinned to a version at all.** ClickHouse Cloud's upgrade documentation (fetched 2026-10-06) states that customers control *when* an upgrade lands, not *which* version they receive: release channels (`fast` / `regular` / `slow`, the last Enterprise-only) shift timing by roughly two weeks each, and scheduled upgrade windows are Enterprise-only and overridable by security patches. The `compatibility` setting is **not** a version pin — it preserves default values of settings from an earlier version and leaves the engine version alone. Only BYOC or self-hosting gives version control. Consequence for this decision in §3; consequence for DEC-A2: "which version does the provider offer" is not a question a provider can answer stably.

- **[M, see `infra/clickhouse/README.md`]** Compose `v5.1.4`: `include:` resolves relative mounts from the **included** file's directory. So T12's shared file mounts `./init.d/...` relative to itself and every consumer gets the same absolute path. `extends:` rebases identically, so it offers no advantage. The spec's premise that `include:` shifts the base to the including file (REQ-I-08) is false; the effect is benign.
- **[M]** Same-name local service next to an included one: `config` exits 0, local definition wins. REQ-I-07's CI assert must inspect merged `config`, not file contents.

## 5. What it unblocks

T12, and through it T13-T21, T25-T34, T36-T39, T46, T47.

## 6. What it cannot settle

- ~~Whether 25.4 passes the 18 silver assertions~~ — **settled 2026-10-05, PASS (#46)**. T20 still needs to assert it continuously in CI.
- ~~Whether a managed provider offers 25.4 (DEC-A2)~~ — **dissolved 2026-10-06**: a managed provider does not offer a *choosable* version at all (**[X]**, §4), so this was never answerable and never blocked the pin. What remains for DEC-A2 is the different question of how the deployed engine's drift is detected, which is T20's assertion surface and T40's tolerance, not a pin.
- "Production-grade" is a vendor maturity claim; the probe shows the *flag* is gone, not that the feature is mature. Behaviour of refreshable MVs on replicated or shared engines is unmeasured.
- Deleting the generator file loses the HyperDX/ClickStack and `--delivery direct --init-schema` worked examples unless T15 moves them into `services/generator-python/README.md` (REQ-I-06).
