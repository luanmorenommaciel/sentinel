# DEC-D1 — Typed Sentinel keys in silver

**Owner** Pod 3 + Pod 2 · **Unblocks** nothing in the dependency table (the plan says it "must stay undecided; see T28")

Tags: **[M]** measured this session · **[S]** per spec §11.1 · **[D]** document assertion · **[R]** reasoned.

## 1. The question

Should Pod 3's *new* D read models (`resource_key_presence_1m`, `volume_1m`) key or filter by typed Sentinel-key columns, or stay key-list agnostic over the `resource_attributes` Map?

The question as the documents word it ("does silver materialise typed Sentinel keys", `README.md:260`, `design-spec.md` §9 ADR-D1) is **already answered in shipped code** (see Established facts), so it is restated to what is genuinely still open.

## 2. Why it's open

- ADR-0007 recorded the five keys moving to `Map` in bronze and said Pod 3 "can recover the fast path with materialized columns in silver if Watcher latency requires it" (`docs/adr/0007-bronze-canonical-contract.md`, Trade-offs and Risks). `README.md:260` lists it "Open".
- REQ-D-06: the required-key list "MUST NOT gain a third copy"; flow-ui's copy is the reader's authority (`clickhouse.py:34-45`, "duplicated deliberately").
- Spec §6.3c and T28 choose a key-agnostic presence rollup precisely so as not to decide D1.

## 3. Options

| Option | Costs | Forecloses |
|---|---|---|
| **Key-agnostic rollup over the Map** (spec/plan) | `key_counts` as `sumMap`; read cost is a Map scan of a small rollup; can't recover "rows missing any key" (T28 Judgement) | Typed, index-friendly presence columns in the rollup |
| **Typed presence columns in the rollup** (e.g. one `has_<key>` per contract key) | The key list is baked into new DDL; every contract change is a migration | REQ-D-06 as worded; flow-ui drawing "what the collector enforces" |
| **Typed columns in bronze** | Contract change to `collector/v1`, which `CLAUDE.md` says is Candidate F territory | Verbatim contrib dump (ADR-0007 option C was deferred for this reason) |

**Recommendation: no change to what the plan already does**, which is to proceed key-agnostic and leave D1 open. The evidence supports that narrowly: measured below, typed columns cannot answer the presence question, which is the one D-04 exists for. This does not decide the broader question.

## 4. Established facts

- **[M] Silver already materialises the keys as typed columns.** `infra/clickhouse/init.d/02-silver-layer.sql` defines `scenario`, `run_id`, `cloud_provider`, `is_synthetic`, `service_name` (and `contract_version`) as typed columns on all three base tables (e.g. `:17-20, 70-73, 120-123`), populated from `ResourceAttributes['sentinel.scenario']`, `['sentinel.run_id']`, `['cloud.provider']`, `lower(['sentinel.synthetic']) = 'true'` (`:48-51, 99-102, 148-151, 170-173`). `scenario` is the first `ORDER BY` column on all three (`:39, 91, 139`), and `idx_run_id` is a bloom-filter index (`:35, 86, 135`). The five contract keys are therefore already typed in silver; the file's own header says its purpose is that "Watchers do not probe attribute Maps" (`:3-5`).
- **[M] The key list already has three copies.** `collector-rust/src/contract.rs:49-52` (`REQUIRED_RESOURCE_KEYS`), `flow-ui/src/flow_ui/clickhouse.py:39-45`, and the silver DDL above. REQ-D-06 and T28 treat "a third copy" as a future risk; by inventory it exists. Spec §6.3c's "would be a **third** copy" is wrong in fact; the intent of D-06 (new DDL adds no fourth) is still meaningful.
- **[M] Typed columns lose presence.** `clickhouse-local` 25.4: `map('a','b')['x'] = ''` is `1` (absent key reads as empty string), `mapContains(map('a','b'),'x')` is `0`, and `map('x','')['x'] = ''` is also `1`. So `scenario = ''` cannot distinguish "key absent" from "key present but empty", and `is_synthetic` collapses absent to `false`. Answering "which producers are missing key k" needs `mapContains` over the Map, as the key-agnostic rollup does.
- **[D]** The Map probe over four live bronze tables measured 1.26 s over ~6 M rows; `ARRAY JOIN` form 6.4 s (`clickhouse.py:191-196`). Not re-measured.
- **[S]** `[V-2]` (`SimpleAggregateFunction(sumMap, Map(...))`) passed on both versions.

## 5. What it unblocks

Nothing: the plan's index lists "—", and T28 only needs D1 to remain undecided. Deciding it later would affect whether a future `rows_missing_any` column exists (T28 Judgement, T38).

## 6. What it cannot settle

- Whether the typed columns' query-latency benefit has ever been measured on real Watcher queries (ADR-0007: "if Watcher latency requires it"; no Watchers exist).
- Whether D1 should be closed by recording that silver already did it, with the open part restated as "do rollups add presence columns". That is a documentation correction for Pod 3 + Pod 2 to ratify; this brief does not make it.
- A spec/plan wording defect to correct regardless: the claim that D1 is undecided in silver conflicts with `02-silver-layer.sql`.
