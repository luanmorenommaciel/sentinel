# flow-ui — working state

*2026-09-01 · branch `feat/flow-ui` · **nothing committed***

## Where things are

Working tree only. `git status`:

```
 M Makefile                    generate-stream + ui targets
 M docker-compose.yml          flow-ui service + generator-config mount
?? services/flow-ui/           the whole service
?? docs/research/data-observability-competitive-landscape.md   (not to be committed yet)
```

Run: `make up` → `make ui` → `make generate-stream DURATION=20m`.
Tests: `cd services/flow-ui && .venv/bin/python -m pytest tests -q` → 47 passing.

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

## Next planned step

**V2.4 · Freshness/arrival lag as a first-class signal**, which now has a prerequisite: an
arrival timestamp at the collector's write path. Worth an ADR before any UI work.
Alternatively **V2.5 · alert-noise budget**, which the shortlist flags as *not
retrofittable*.

Rationale and the rest of the shortlist are in
`docs/research/data-observability-competitive-landscape.md`, which is **not to be committed
yet**.
