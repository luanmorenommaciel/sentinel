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

## Next planned step

**V2.1 · Contract Health** — the counters already exist (`signals_rejected_total{signal,reason}`,
the `grpc_validation` policy) and nothing renders them as a board. Rationale and the rest of
the shortlist are in `docs/research/data-observability-competitive-landscape.md`, which is
**not to be committed yet**.
