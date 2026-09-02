# flow-ui — working state

*2026-09-02 · branch `feat/flow-ui-silver-read` · V1–V2.3 merged to `main` in PR #31*

## Where things are

On `main` since PR #31. In flight on this branch: Silver as the fourth box on the Flow board.

Run: `make up` → `make ui` → `make generate-stream DURATION=20m`.
Tests: `cd services/flow-ui && .venv/bin/python -m pytest tests -q` → 63 passing.

## What V1 does

**Flow** — one pan/zoom canvas. ORIGIN / COLLECTOR-RUST / BRONZE expand **in place**; the
others stay put and the particles keep flowing. Selecting a service filters bronze figures to
it and lists which metrics it emits. `⌂ + −` bottom right, wheel zooms on the cursor, drag
pans, `Esc` resets.

**Health** — a verdict (`ok/warn/fail/idle`) with the sentence behind it, four 120 s rolling
series with avg and peak, export latency p50/p90/p99 against an 80 ms ceiling, a mode
timeline, and rejections split by reason.

Two palettes (command / substrate) switched by one attribute; nothing in the CSS names a
colour. Design recorded in [`DESIGN.md`](DESIGN.md).

## Solved: the outcome rows now read as coming from their stage

The fifth attempt worked, and not by moving the rows. Two changes did it:

1. **What falls down a tap is drawn as what failed.** `signals_rejected_total` carries BOTH a
   `signal` and a `reason` label, so the `signal × reason` cross-product is measured data —
   `prom.Sample.sum_over_pair` reads it into `Snapshot.reject_matrix`. A metrics rejection now
   falls amber and a log rejection green. The previous version ran one hard-coded pool per
   tap, which painted **every** rejection of every type amber: right by accident for metrics,
   wrong for the other two.
2. **Each outcome's RETURN is drawn, and the asymmetry is the content.** Under `warn` the
   contract row sends a line back up into `buffer` — it really is exported anyway; under
   `strict` that line is absent, which is the only place the policy difference is visible at
   all. Backpressure sends a *control* line back into `receive` (dotted, no particles: what
   travels back is a gRPC status, not the batch). Dropped has none, so `⊣` became information
   rather than decoration.

The open container widened 452 → 500 to open a 20px return channel down each margin, and the
stage row centres itself inside it. Earlier attempts failed because three identical rows with
three identical taps told one story three times; the fix was to make the three stories differ.

Still not settled: opening a box does not refit the viewport, so collector + bronze + datasheet
all open runs off the right edge until you pan or press ⌂. Pre-existing, and refitting would
move the canvas under the reader mid-inspection.

## Facts the drawing must not contradict

Read from `collector-rust/src/`, not assumed:

- Strict order `receive → validate → buffer`. Nothing enters mid-chain; only `buffer` writes.
- `contract` rejection happens in `validate`. Under the default **`warn`** policy the signal
  is counted and **exported anyway** — it still reaches bronze. Only `strict` discards it.
- `backpressure` is `buffer.enqueue` refusing a full batch, answered with `resource_exhausted`.
  Nothing is lost; the producer retries.
- `dropped` is the flush loop after 3 retries. **No dead-letter queue, no disk spill, no
  requeue.** The path ends.
- Bronze routes on **data-point type**, never on producer, so every service reaches all four
  tables. The metric *mix* is the only per-service difference.
- Live rates carry a `signal` label and **no service label**, so per-service throughput does
  not exist upstream of ClickHouse. Bronze figures can be filtered; rates cannot.

## Known gaps, deliberate

No language selector (V1 is English; it ships with the demo) · the *observed* topology is not
yet derived from `ParentSpanId` and compared against the declared one · a service present in
bronze but absent from `topology.yaml` would be invisible in ORIGIN · the look has been
reviewed only by the owner, because headless capture cannot hold an SSE page still.

## Shipped: V2.1 · Contract Health

A third board, from two sources whose split is the design. The collector knows **how many**
violated and **how** (`signals_rejected_total{signal,reason}`) but never **who** — its
counters carry no service label. Bronze knows who, because under the default `warn` policy a
violating signal is exported anyway and the evidence lands in the table.

- **The counterfactual is the headline.** Under `warn` the collector counts what it would
  have dropped and exports it anyway, so that number *is* the answer to "what happens if we
  promote to strict" — measured, not modelled.
  **Four ways that number can be zero, and only one is good news:** `off` (nothing is
  checked), `unknown` (the policy could not be read), `idle` (nothing arrived to check), and
  clean (traffic came through and passed). Each gets its own headline and its own tone;
  collapsing them into one green all-clear is the failure this board exists to prevent, and
  the first version did it — it showed "nothing failing the contract" over a dead pipeline.
- **Violation rate per signal over the window**, because `signals_rejected_total` is labelled
  by both `signal` and `reason` and a single total would hide which type is failing.
- **Who is violating**, from bronze: rows missing a required key, per producer, per key.
  `contract_violations()` counts with `countIf` per key rather than `ARRAY JOIN`-ing the five
  names — the array form multiplies every row by five before filtering, measured 6.4s against
  1.26s over the same ~6M rows. Its own 30s lane; it probes an unindexed Map.

**Two things V2.1 asked for that are not here, on purpose:**

- **Contract-version adoption per producer — impossible.** `collector-rust/src/otlp.rs`
  injects `CONTRACT_VERSION` into every signal it builds ("OTLP carries no
  `contract_version` field"), so every producer reads back the collector's own constant. The
  panel would show `1.0.0` for everyone and mean nothing.
- **A state timeline of validation mode — degenerate.** The policy is config read at
  collector startup and is not exposed as a metric, so it cannot change mid-window. The board
  states it and says why, instead of drawing a strip over a constant.

**Bug this surfaced:** `topology.CONTRACT["validation"]` was hard-coded to the literal string
`"grpc_validation"` — the config *key*, not its value — and every board rendered it where it
meant the mode. It is now read from the collector's own config, mounted read-only, and
reports `unknown` rather than guessing `warn` (the collector's default, and so exactly the
wrong thing to assume). Two regression tests pin it.

## Shipped: V2.2 · Volume watcher

A fourth board. Rows per minute per producer, judged against a band — and **the band drawn
is the alerting rule**, both from `pipeline.volume_state`, one place, one set of numbers.
Metaplane shipped a version where they were computed separately and publicly called
reconciling them a "simplification"; there was no reason to repeat it.

**The method is published on the board**, because that is the differentiator the survey
found: Acceldata discloses nothing, Bigeye names no model families, Metaplane publishes the
reasoning but not the estimator. Threshold is Elementary's documented z = 3.0; the estimator
is what changes — median and MAD × 1.4826, so one bad bucket cannot widen the band meant to
catch it. Dual severity (3σ warn, 5σ fail). Sliding, not cumulative: theirs is cumulative, so
*"a long problem covers its own tracks"*.

**The bucket is a minute, not a day.** Elementary's documented baseline is a 1-day bucket
over 14 days; at this pipeline's cadence that would hold one point. Same method, scaled to
the data, and the board says which.

**Four states, and grey is `not observed`, never `fine`** — and the two alerting severities
are told apart by their labels (`alerting ≥3σ` / `≥5σ`), not by colour alone, which this
repo's own rule forbids and the first version did. (Bigeye's distinction, and the
same rule as the contract board's four zeros):

- The current bucket is excluded — it is partial, and comparing a half-filled bucket to a
  band built from full ones alarms every tick.
- **The estimator is chosen by whether its band fits, not by MAD being non-zero.** The first
  version used `mad * 1.4826 or sd`, which is a cliff: on a producer alternating full minutes
  (2850 rows) with partial ones (600–1600) the median sits on the dominant mode, MAD measures
  that mode against itself (50, against a true spread of 699), and the instant MAD crossed
  zero σ moved 74 → 699 between two consecutive ticks — flipping all eight producers from
  passing to alerting on one new bucket. Caught on screen, not in review.
  Now a cascade with a validity test at each step: a band that rejects more than
  `MAX_OOB_SHARE` of the window it was **built from** is describing one mode of it, not the
  series. MAD is tried first, stddev next, and if neither fits the series is declared not
  single-mode. On the measured data the MAD band excluded 14 of its own 31 buckets; stddev
  excludes 3% and is used. Two regression tests pin it.
- A perfectly regular producer has **MAD = 0 and a zero-width band** in which every value is
  infinitely anomalous — the same conclusion by a different route, and the generator produces
  exactly that case too.
- Under `MIN_BUCKETS` there is no distribution and a band drawn from three points is
  theatre.

**Absence is its own axis**, not a band violation: buckets in which the estate received
something and this producer did not. Computed against the estate rather than a clock, so it
needs no schedule model. This is the survey's strongest idea — a tool reading a table at rest
sees a stale table, never the write that failed to happen — and it falls out of being
pipeline-centric.

### The Arrival watcher is not here, and not because of effort

**Bronze has no arrival timestamp.** `otel_logs` carries `Timestamp` (event time) and two
columns derived from it, and nothing else; there is nowhere to read *when* a row showed up.
Freshness over event time would answer a different question, and the backfill writes history,
so it would answer it wrongly. Adding an ingestion column is a collector change against a
read contract that is Authoritative at `1.0.0.1` — an ADR, not a UI session.

What landed instead is the half of Arrival that *is* answerable from this data: the absence
signal above.

## Shipped: V2.3 · the flow DAG carries health, on measured edges

Contract and Watchers were separate boards, so the view people actually look at knew nothing
about either. Every producer node in ORIGIN now carries a **fused state** — the worst of its
volume verdict, the buckets it was silent for, and the rows it wrote missing a contract key —
as a mark on the node and, when it has something to say, on its border. The reason travels in
the `aria-label`, so it is not colour-only. The closed card carries the same answer, because
state you can only reach by opening the box that contains it is not an answer.

**A finding that changed what the feature is worth.** Building it surfaced that
`legacy-billing-api` and `third-party-agent` — the only two producers with problems — are
**not in Pod 1's declared topology at all**. The DAG draws what is declared, so no node exists
to carry their state, and per-node health would have been structurally blind to exactly the
producers that need it. Undeclared is now its own finding, reported apart from the graph
because it has no position in the graph: nothing declared them, so nothing told them the
contract, so they are missing required keys. The correlation is not a coincidence.

**Edge thickness and colour are now measured, and getting there was a one-field fix in Pod 1.**
The first pass reported them as unbuildable — "no per-edge measurement anywhere" — which was
true of the data and wrong about why. The chain was intact end to end: `ScenarioEngine`
assembles correlated traces by walking `depends_on`, the model carries `parent_span_id`,
`otlp_output.schema.json` declares it, the read contract documents `ParentSpanId` as `''`
*for root spans*, the collector parses it and its exporter writes it, both with tests. Only
`generator-python/src/otelgen/exporters/otlp.py` built `ReadableSpan` with a context and no
`parent`, so `trace_id` reached the wire and the parent did not — measured live, traces
arrived correlated (8.5 spans each, 30k spanning more than one service) while 1,491,881 of
1,491,881 landed as roots. A call graph that existed in the generator and nowhere downstream.
Two regression tests in Pod 1 pin it; **that file wants Pod 1's review on the PR.**

With the parent on the wire, `ClickHouse.call_edges()` joins child to parent and the two
`ServiceName`s are the edge: pipe width from spans traced, casing colour from the error rate
on that edge (≥1% / ≥5%, printed in the legend). The join needs `TraceId` as well as
`ParentSpanId = SpanId` — a fixed `--seed` repeats span ids between runs, and the id alone
invented eight edges the topology does not contain.

**Declared and measured are drawn as different claims.** `spark_streaming → processed_bucket`
and `spark_streaming → k8s-api-gateway` are declared and carry no span, because the engine
parents every child to `depends_on[0]` and never to the second dependency. They are drawn
dashed and dim — declared, never traced — rather than at a width that would imply traffic.

**Still not built:** the per-node state timeline needs per-service history, which nothing
retains, and Grafana node-graph frames.

## Two rules the review and the reader forced out

**One channel each: the border is interaction, the mark is state.** Per-producer health took
the node border, in the same `--sec` the hover uses, so a warning node and a pointed-at node
were indistinguishable and the pointer stopped meaning anything. Hover and selection own the
border; state lives in the mark beside the name.

**Silence has to be material.** `absent > 0` raised every producer to warn, because a run's
first and last minute are partial and everyone misses a bucket at the edges — seven of seven
amber over 1 of 14. It now takes at least two buckets *and* 10% of the estate's.

**Only the trunk is the widest thing on the canvas.** Measured edge widths scaled to 20
against a 13px standard gauge, so a service dependency drew fatter than the feeders and the
bronze fan. What those edges carry is relative, so the range tops out *at* the standard gauge.

## Shipped: Silver, as an addition rather than a migration

`silver.service_health_1m` gives per-producer latency quantiles and error rate, and each
ORIGIN node now draws **declared → measured**: what `topology.yaml` claims a component's
latency is, beside what its operations actually took. The two agreeing is the baseline; the
two diverging is the finding. flow-ui had no per-service latency at all before this — the
Health board's quantiles are the collector's *export* latency, a different question.

**The three Bronze queries did not move, and should not have.** Measured on the stack the day
Silver landed: `bronze.otel_traces` held 1,703,050 rows over 36 hours, `silver.
operation_executions` held 12,849 over 12 minutes, because ADR-0010's materialized views do
not `POPULATE`. Migrating `contract_violations` would have reported nothing and lost the
`legacy-billing-api` finding — 104,610 rows missing four required keys. Migrating
`volume_band` would have left every producer below `MIN_BUCKETS` and shown the whole Watchers
board grey. #37 stays open for the half that needs a backfill first.

Silver also cannot answer one question Bronze can: `is_synthetic` is materialized as
`lower(...) = 'true'`, so an **absent** `sentinel.synthetic` key is indistinguishable from an
explicit `false`. Contract violation counting needs the key's absence, so it belongs on the
retained Map either way.

`service_health()` returns `[]` when `silver.*` is missing, which is the normal state of any
stack whose ClickHouse volume predates the DDL. The node then shows the declared figure
alone, as it always did.

## Shipped: Silver on the graph — and drawn as a derivation, not a hop

Silver was being *read* and was nowhere on the picture, so the one board people look at
claimed the pipeline ended at bronze. It is now the fourth box, and the link into it is
deliberately **not a pipe**.

Everything else on this canvas transports something: a pipe has a casing, a bore, mouths at
both ends, and particles inside it, because a signal really does leave one place and arrive at
another. Bronze to Silver moves nothing — ADR-0010's materialized views fire *inside*
ClickHouse on the same insert that writes bronze. Drawing a run between them would claim a hop
that never happens and invite the question that follows from it ("what is the latency of that
hop?"), which has no answer. So it is a short double bar with a tip, captioned `derived` /
`on insert`, and no particle ever enters it.

**Three states, and the box says which.** Absent (no `silver` database — a volume older than
the DDL), present and empty (the normal state of a stack nobody has streamed into: the MVs do
not `POPULATE`), and populated. `silver_state()` reads `system.tables`, so it is metadata —
0.025 s, never scans a row — and the same distinction `counts()` makes for the same reason.

Open, it lists the three models with their row counts and the six read views, with
`service_health_1m` marked as the only one this service actually consumes — so the panel does
not imply flow-ui reads six things it does not read. Six tests pin the parsing, including the
present-but-empty vs absent split and an unreachable ClickHouse reading as absent rather than
taking the board down.

### Silver is a DAG now, and the DAG is the database's shape — not a list in the code

Three boxes and a list of six names said nothing about what separates them, and the question
it produced was the right one: *what is the difference between a table and a view?* Every
object in `silver` is now its own box, in three columns, with the lineage drawn between them.

**Three kinds, and the confusion is worth naming.** ClickHouse puts all three in one database
and the words mislead:

| | | on the board |
|---|---|---|
| **MergeTree** | a table — stores rows, has a sort key and a TTL | solid border, a row count |
| **MaterializedView** | *not* a stored result set. An **insert trigger**: rows land in its source, it runs its SELECT over that block and inserts into its target. Stores nothing | dashed border, `on insert`, no count |
| **View** | a named query, run at read time. No rows exist until someone asks | dotted border, its grain, `—` |

That distinction is why Silver only holds what arrived after the DDL did — the MVs do not
`POPULATE` — and it is the thing this board had been hiding.

**The edges are not all the same edge.** `bronze → mv → table` carries particles, because rows
really do move on that insert. `table → view` carries none: nothing flows there until a reader
runs the query, and animating it would draw a stream that does not exist. Colour is the source
table's signal type throughout, so lineage stays followable either way.

**Nothing here enumerates the schema.** `silver_graph()` reads `system.tables`, classifies by
engine, and parses lineage out of `create_table_query` — `TO x.y` is an MV's target, every
other `bronze.`/`silver.` reference is a source. The old `DERIVES` constant, four bronze→model
pairs typed into `app.js`, was a fourth copy of the DDL after the SQL, the MV definitions and
`system.tables`; it is now computed. The box's own footprint is measured from the graph rather
than typed in.

**Columns are DAG depth, not kind.** Kind decided the column first and it was wrong the
moment the schema stopped being a straight line, which is what "what if a new MV is born in
the middle?" was really asking. A second-stage MV — one reading a *silver* table rather than a
bronze one, which is how an hourly rollup is built — belongs between two tables; by kind it
landed back in column 0 and its edge ran right to left, drawing a dependency that reads
backwards. Depth puts every node after everything it reads, whatever it happens to be, and the
kind moved to the border style with a key to explain it. The walk is guarded against cycles:
ClickHouse will let you build one.

**Verified against the live database three times, by creating the awkward cases and looking:**

| Case | Result |
|---|---|
| `CREATE VIEW silver.error_budget_1m … FROM silver.operation_executions` | appeared beside the table it reads, wired in that table's colour, box grown a row — **no code edited** |
| A second-stage MV: `silver.log_events → silver.log_events_hourly` | landed in a **fourth column** that did not exist before, after the table it reads |
| A table nothing feeds (`manual_annotations`) | column 0 with the sources, no incoming edge — correct: nothing produces it |

**Kind is on the GROUND, and the first attempt at it was measurably fake.** The channel is
right — a filled area beats a 1px stroke as a signal, so a reader sees the kind before reading
the name — but the first version used `--raise` / transparent / `--sunk`, which measure
**1.03:1 apart**. Three names for one colour, with the border doing all the work while the
comment claimed otherwise. Contrast ratio is a poor guide this close to black, so the fix was
picked by rendering candidates and looking, then checked against the numbers:

| | command | substrate |
|---|---|---|
| `--k-table` lit — the rows are in here | `#1B2614` | `#12283A` |
| `--k-mv` dim — a trigger; rows pass through | `#0E1309` | `#0A121C` |
| `--k-view` dark — a query, run when read | `#050703` | `#020407` |

Hue is still not the channel: `--pri`, `--sec` and `--ter` mean logs, traces and metrics on
every edge and particle here, and a box borrowing one would make the same channel say two
things. Border style stays as the redundant second reading, so the distinction survives
greyscale and a colour-blind reader.

**The key is a legend, and it was being read as three checkboxes.** A 12×12 rounded square
beside a label is the shape of something you tick, so it invited a click it could not answer.
It is a wide flat bar now — a miniature of the node it describes, which is what it actually is
— and `pointer-events:none`, so it never takes a cursor either.

It does answer the pointer, from the other end: **selecting a node lights the swatch for that
node's kind** in `--sec`, and the other two stay dim. The legend stops being dead chrome and
starts saying *the thing you just picked is one of these*. Amber because that is already what
selection means everywhere else here — `.nd.sel`, the hover border, the OPEN/CLOSE cue.

**The first version of that highlight was invisible, and the test said it worked.** It only
nudged `stroke-width` and the text fill, and the assertion checked that the `.on` class was
applied — which it was. The class being right is not the question a reader asks. It is now
verified at the pixel level instead: the swatch's computed stroke goes from `rgb(46,110,136)`
to `rgb(255,197,61)` and its opacity from 0.5 to 1, while the other two do not move.

**Two bugs a running stream found that a still page could not.**

*The MV → table runs had particles that were never revealed.* `spawn` fills `pools`, and
nothing in the tick showed the `sv-*` ones, so the one real movement inside SILVER existed
with every dot at opacity 0 — bronze fed the MVs and then the board went still. The gate is
the growth of the bronze table the chain started from, resolved **through the graph**, so a
second-stage MV reading a silver table finds its root instead of guessing.

*Opening a box blacked the board out for a second.* `render` creates every dot at opacity 0
and the tick read `if (repaint()) return`, skipping the `density` call that reveals them — so a
structural change left the whole canvas empty until the next frame arrived, then filled it all
at once. Read as every particle restarting, and reported as exactly that. Every structural
repaint outside the tick now goes through `repaintNow`, which re-applies the current density
immediately: 69 dots are visible the instant the click completes, not a second later.

*Clicking a row restarted every dot on the board.* Selection went through `repaint`, which
rebuilds the whole stage; rebuilding recreates every `animateMotion`, and an `animateMotion`
keeps its progress on the node itself, so each dot jumped back to the mouth of its pipe. That
invariant is [the reason this page has no framework](ARCHITECTURE.md) — and it was being broken
by its own click handler. A selection changes no geometry (the sheets sit below their box and
are narrower than it, so nothing moves), so it now redraws only the sheet layer, the `.sel`
classes and the key. Verified by **object identity**, not by counting: the same 89 circle nodes
survive both a model click and a table click.

**The two still edges now carry dots, which reverses a call I made twice.** The collapsed
`bronze ⇒ silver` bar and the `table → view` reads were drawn motionless on the argument that
neither is a hop. The argument holds for the *shape* — the bar keeps its rails and no bore, the
reads keep their dashes — but not for the stillness: both counts climb while the stream runs,
and a dead line between two rising numbers says the opposite of what is happening. The bar's
dots run down a `.track`, a path with no stroke that exists only for `animateMotion` to follow,
so the rails stay two rails. A read's dots are smaller and slower than a pipe's, so the
difference in claim survives as a difference in weight. Each read edge is gated on the growth
of the table being *read*, resolved back to its bronze root: a view over a silent table has
nothing new to answer with.

**Every run is capped at both ends now.** The `collector → bronze` trunk had lips at
departure and arrival from the start; every run added after it got one only where it landed,
so a pipe grew out of a flat box edge at one end and met a lip at the other — on the bronze
tables' exits, on the MVs' exits, and on the collapsed `bronze ⇒ silver` bar, which had none
at all. A lip marks where a run *meets a box*: it is a termination, not a claim about what
travels, so putting one on the derivation bar does not undo it carrying nothing. The dashed
read edges still have none, because they are not pipes.

**And adding the kind strokes silently took the selected border away from every silver node.**
`.nd.sel` and `.sub-nd.k-mv` are both two classes, so the cascade falls back to source order,
and the kind rules were written below. Selection now comes after them. The same trap as the
presentation-attribute-versus-stylesheet one the pipes hit months earlier: equal specificity is
decided by position, and position is easy to move by accident. The selected border keeps its
dash pattern, so picking a node does not hide what kind it is.

**A silent failure mode worth knowing:** `el(tag, attrs, text)`'s third argument is text, not
children. Passing elements there sets the group's `textContent` and the child is never created
— no error, no warning, just a legend with no swatches in it.

**And it surfaced a contrast bug that predates it.** Substrate's `--dim` was `#3D5A72`, putting
every `.sub` label at **2.8:1** on the old panel and 2.09 on the new lit ground — under the 3:1
floor for small text, on labels that are not decoration: `on insert`, `stored`, `per minute`,
each producer's declared latency, the volume band's reason. Raised to `#57748F`, where the
worst case on this board is 3.09. Command's was already above the line.

**Kind was on two channels, and neither is hue.** Hue is spoken for: `--pri`, `--sec` and
`--ter` mean logs, traces and metrics everywhere on this canvas, and a box borrowing one would
make the same channel say two things. The **ground** was free, and there the difference is
literal rather than a code to memorise — a table is *filled* because it holds something, an MV
is *hollow* because rows pass through it and it stores nothing, a view is *sunk* because it is
a window onto the rows below. Border style is the redundant second channel, so the distinction
survives a colour-blind reader and greyscale, which this repo's own rule requires. Strokes stay
inside the structural family (`--dim2` / `--viaS` / `--rule-arrow`), defined per palette, so
both worlds keep their own version. The key swatches wear the real classes, so the legend
cannot drift from what it describes.

**Two defects that only a real object could have found**, and they were the same defect twice:
`SummingMergeTree` — the obvious engine for a rollup — did not match the literal string
`"MergeTree"`, so the table was **invisible** in `silver_graph` and **absent from `models`** in
`silver_state`, leaving the board drawing a table it had no count for. Anything that is not one
of the two view engines stores rows. Both readings now classify identically, and a test pins
that they agree.

### Silver's models have datasheets too — read from ClickHouse, not restated

Clicking a silver model opens a sheet under the box, the same shape as bronze's. The
provenance is deliberately different, and the asymmetry is the point:

- **Bronze's sheet is hand-written** in `topology.TABLE_DOCS` because the read contract makes
  a *subset* claim — only some columns are populated, the rest sit at their ClickHouse default
  by design (§2) — and no DDL can express that.
- **Silver makes no such claim.** The DDL is the whole definition, so its columns come live
  from `system.columns` and cannot drift from the deployed schema. Restating them in Python
  would only create something to go stale.

Only the one-line purpose per model is written by hand, because a type is metadata and a
purpose is a claim. An MV's columns are skipped, because they *are* its target's — listing
them says the same thing twice. (An earlier version tried to filter this in SQL and could not:
ClickHouse 24.3 rejects `IN (SELECT … FROM system.tables)` with *"Not-ready Set is passed as
the second argument for function 'in'"*.)

**And the six read views now say what they are.** A bare list of names is a list, not
information — a reader cannot tell a view from a table, or guess that `run_summary` is one row
per run. Each carries its grain and what it answers, under a line saying a view stores nothing
and is a query over the models above. They are on two lines each because side by side a
22-character name and a 43-character answer need 455 units against 278 of usable width, and
the first version simply drew them on top of each other.

**Both sheets toggle, and both start closed.** BRONZE opened with `otel_logs` selected and no
way to deselect it, so its sheet was a permanent fixture of the open box rather than an answer
to a question the reader asked. Click a row for its sheet, click it again to put it away.

**And ⌂ was resetting a stale list.** It cleared `origin`, `collector`, `bronze` and the table
selection, and knew nothing about `silver` or the selected model — the same defect as the
`repaint()` key, in a second hand-maintained list of the same boxes. Both now enumerate every
expandable box and every selection.

### Open, the derivation becomes per-table — because the mapping is not 1:1

Closed, one double bar is the honest summary. Open, the reader is asking a lineage question —
*which bronze table becomes which silver model* — and that question has an answer worth
drawing, because it is 4 → 3:

```
otel_logs          → log_events
otel_traces        → operation_executions
otel_metrics_gauge ─┐
otel_metrics_sum   ─┴→ metric_observations
```

Nothing else on the board says that gauge and sum both land in one model. The four strands
carry particles in the type colours, and each strand runs on the growth of *its own* bronze
table — a silent source is a still strand, the same rule the bronze fan already follows.
The dots depart on the same batch arrival that fills the bronze row, because the MVs fire on
that insert; they are not a second hop after it. The mapping is read off the four
`CREATE MATERIALIZED VIEW … TO silver.x … FROM bronze.y` statements in the DDL, not inferred
from the names, and each silver row also states its source in text so a reader who never
opens both boxes still gets the answer.

**The rows are ordered by their source, not by `system.tables`.** In the catalogue's order
the four strands crossed inside a 52px gap, and a crossing is a claim about routing this
mapping does not make. In source order they run essentially straight across, and the two
metrics strands visibly converge — the merge reads as a merge.

**Three defects this surfaced, all found by looking:**

- **The datasheet covered SILVER.** Drawn 40px right of BRONZE, it landed exactly where the
  new box sits — a detail panel over the nodes it explains, the third time that class of
  defect has reached the reader. Moving it past SILVER cleared the overlap and cost more:
  at 320 wide it took the canvas from 1080 to 1682 units, and `fit()` scales to the widest
  thing, so every box shrank to 58% to make room for a panel. It now sits **below** BRONZE,
  directly under the table it describes, where at 320 against bronze's own 318 it adds no
  width at all.
- **SILVER's rows did not answer the pointer.** They were plain rects next to a BRONZE box
  whose every row lit up, so the box read as inert. They are `.hit` groups now, with the
  source named in the `aria-label`.
- **`open.silver` was missing from `repaint()`'s key.** The click flipped the state, the key
  did not change, repaint returned early and the box never opened — a dead click with no
  error. That key is a dependency list maintained by hand; every expandable box belongs in it.

## Next planned step

Tier 1 is now closed to the limit of the data. What remains:

* **V2.5 · alert-noise budget**, which the shortlist flags as *not retrofittable* — the
  strongest remaining candidate for that reason alone.
* **V2.6 · schema watcher** with ordinal-position awareness.
* **V2.4 · freshness/arrival lag** and the **Arrival watcher**, both blocked on the same
  prerequisite: an arrival timestamp at the collector's write path. Worth an ADR, not UI work.
* A **geometry test**. Two layout collisions and one overlap reached the reader today; the
  63 tests cover the backend and the pure logic and nothing about where things land.
* **The rest of V2.3**, which is two pieces, not four: a per-node state timeline (needs
  per-service history retained, which nothing does today) and Grafana node-graph frames.
  Edge thickness by throughput and edge colour by violation rate are not pending — there is
  no per-edge measurement to draw them from.
* **V2.10 · language selector (PT-BR · ES · EN)**, a Crew decision rather than a survey
  finding. Its real work is a reason-code refactor: `health_note`, `volume_state.why` and the
  contract notes are composed server-side as finished English sentences, and the figures are
  rendered before any script runs, so the locale has to be known at render time.

Rationale and the rest of the shortlist are in
[`docs/research/data-observability-competitive-landscape.md`](../../docs/research/data-observability-competitive-landscape.md).
