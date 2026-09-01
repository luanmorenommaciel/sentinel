# flow-ui — the pipeline watching itself

A live picture of Sentinel's ingestion path: what is arriving, how the buffer is flushing it,
and what is landing in `bronze.*`. Two boards — **Flow** (how data moves) and **Health**
(what is breaking) — over one semantic zoom.

```
generator ──OTLP :4317──▶ collector-rust ──HTTP──▶ ClickHouse bronze.*
                              │ :9090/metrics          │ :8123
                              └──────────┬─────────────┘
                                      flow-ui  ──SSE──▶ browser
                                       :8080
```

## Run it

Everything runs in Docker. No host toolchain is needed to bring the stack up.

```bash
make up                            # ClickHouse + the Rust collector
make ui                            # this service → http://localhost:8080
make generate-stream DURATION=10m  # real-time telemetry, paced by the wall clock
```

`make ui` builds and starts the container, so re-run it after changing anything under
`src/`. Assets are cache-busted by mtime, so a plain reload is enough in the browser.

`make generate` instead of `generate-stream` delivers a backfilled window as fast as it can.
Watch the page while running each: it looks different, and working out which one is running
is something the page does on its own — nothing tells it.

**A first pass, in the order that makes the pipeline legible:**

| | |
|---|---|
| **Flow**, closed | three lanes in, one trunk out. One dot is 100 signals of that type |
| **Flow** → open `ORIGIN` | the declared service graph, each producer carrying its fused state; pipe width is what was actually traced on that edge |
| **Flow** → open `COLLECTOR-RUST` | `receive → validate → buffer`, and the three ways a signal does not simply arrive |
| **Flow** → open `BRONZE` | the four tables, each strand carrying the type that lands in it |
| **Health** | the verdict and the sentence behind it, over a 120s window |
| **Contract** | the receive boundary: what would be dropped under `strict`, and who is violating |
| **Watchers** | rows per minute per producer against a band — and the band drawn *is* the alerting rule |

The palette switch (top right) is not decoration: it re-tests every colour decision against a
second ground. Nothing in the CSS names a colour.

## See it fail

A healthy pipeline shows every failure path at rest, which is correct and tells you nothing.
Three ways to make them move, in increasing order of violence.

**Contract violations — safe, loses nothing.** Sends foreign OTLP missing a required
`sentinel.*` key. Under the default `warn` policy the collector counts it and exports it
anyway, so it lands in bronze and the Contract board can name the producer.

```bash
docker compose run --rm --entrypoint python \
  -v "$PWD/services/flow-ui/scripts/inject_contract_violations.py:/tmp/inject.py:ro" \
  generator /tmp/inject.py 120 40 300
```

Watch the CONTRACT outcome row in the open collector: the falling dots are coloured by the
type that failed, and the traces lane stays still because this sends none.

**Backpressure — nothing is lost, the producer is told to retry.** Freeze ClickHouse so the
buffer fills:

```bash
docker pause sentinel-clickhouse-1     # ~40s is enough
docker unpause sentinel-clickhouse-1
```

**Dropped batches — this destroys data.** A *paused* container holds the connection open and
the flush hangs, so retries never exhaust; a *stopped* one refuses immediately, the three
attempts run out, and the batch is gone — there is no dead-letter queue.

```bash
docker stop sentinel-clickhouse-1      # ~30s
docker start sentinel-clickhouse-1
```

## Test it

From the repo root, in Docker, with no host toolchain — and wired into the aggregate targets,
so `make test` and `make lint` cover this service too:

```bash
make test-flow-ui     # 57 tests
make lint-flow-ui     # ruff over src, tests and scripts
```

Or against a local venv, which is faster to iterate with:

```bash
cd services/flow-ui
uv venv && uv pip install -e . && uv pip install pytest pytest-asyncio
.venv/bin/python -m pytest tests -q
```

The suite covers the parsing, the poller's inferences and the pure verdict logic — including
the cases that are easy to get confidently wrong: a band whose estimator collapses, a producer
whose every row violates the contract, an estimator chosen by whether its band fits rather
than by MAD being non-zero.

It does **not** cover SVG geometry. Where things land on the canvas is checked by looking, and
that gap has cost real defects: a detail panel drawn over the nodes it describes, two header
collisions, and a pipe routed out from under the box it was meant to reach.

## What it does

**It works out the delivery mode on its own.** Nothing tells the page whether the generator is
streaming or backfilling — the buffer's flush cadence is the tell, and the two do not overlap:

| | `--mode stream` | `--mode backfill` |
|---|---|---|
| signals/s | ~730 | ~18,000 |
| **flushes/s** | **1.03** | **6.6** (min 4, max 8) |
| records per flush | 500–1,000 | ~2,534 |
| export latency | — | 45.3 ms avg |

**Semantic zoom.** Level 0 is three boxes. Click one and it opens:

| Level | Shows | Source |
|---|---|---|
| **Pipeline** | origin → collector → bronze, three lanes in and one out | `/metrics` |
| **Origin** | the seven services as a graph, **declared config beside observed row counts** | `topology.yaml` + bronze |
| **Collector** | where a signal comes from and where it goes, with the three outcomes | `/metrics` |
| **Bronze** | the tables, and the read contract as each one's datasheet | contract v1.0.0.1 |

`Esc` returns to the overview. The legend at the bottom is rebuilt on every level change,
because **a particle means something different at each one** — see [DESIGN.md](DESIGN.md).

**Two palettes.** The switch in the header swaps Command (phosphor) for Substrate (cyan). Same
roles, different values; the choice persists per browser.

## Design rules this service holds to

**The browser never talks to the collector or to ClickHouse.** Not a preference — a
constraint. The collector's `/metrics` server sets exactly one response header
(`Content-Type`; see `collector-rust/src/metrics_server.rs`) and ClickHouse has no CORS header
configured in `infra/`, so a cross-origin fetch from the page is blocked with no visible
error. This service is the only reader of either. A test pins it.

**Every figure is in the HTML before any script runs.** The graph illustrates numbers the page
already printed. A blocked or slow script costs the motion, never the reading.

**An absent metric family is a normal state, not an error.** The collector's labelled counters
are `IntCounterVec`s, and a `*Vec` exposes nothing until a label combination is instantiated.
On a freshly started collector `/metrics` serves only three families; the other five appear
when traffic does. `prom.Sample.value()` returns `0.0` for anything absent.

**Bronze growth is measured with `count()` deltas, never a time window.** Bronze stores *event*
time — the read contract (§2) defines `Timestamp` as the signal's own timestamp, and there is
no ingest-time column. In backfill the generator writes five minutes of history in thirteen
seconds, so `WHERE Timestamp > now() - INTERVAL 10 SECOND` answers "what *happened* recently",
which is not the question. It is also 40,000× the rows: bare `count()` reads 1 row from part
metadata (3.7 ms measured); the windowed form scans the table.

**Where the per-type distinction dies, and where it does not.** At the gRPC boundary
`signals_rejected_total` is labelled by both `signal` and `reason`, so a rejection knows which
of the three types it was — that cross-product is what colours the dot leaving the chain. From
the **buffer** onward every metric is labelled `signal="all"`, because one mixed batch is
flushed and no per-type boundary survives; a dropped batch can therefore only be drawn as a
mixed sphere, ringed to say it was lost. Neither is ever per *trace*: the counts are aggregate.

## Configuration

| Env | Default | |
|---|---|---|
| `COLLECTOR_METRICS_URL` | `http://localhost:9090/metrics` | compose sets `http://collector:9090/metrics` |
| `CLICKHOUSE_URL` | `http://localhost:8123` | compose sets `http://clickhouse:8123` |
| `CLICKHOUSE_DATABASE` | `bronze` | |
| `GENERATOR_CONFIG_DIR` | `/app/generator-config` | Pod 1's config, mounted read-only |
| `FLOW_UI_POLL_INTERVAL` | `1.0` | seconds; matches the stream-mode flush cadence |
| `FLOW_UI_LINEAGE_INTERVAL` | `5.0` | the per-service `GROUP BY` runs on a slower lane |

## Endpoints

| | |
|---|---|
| `GET /` | the page, with the current snapshot rendered in |
| `GET /stream` | SSE, one snapshot per tick |
| `GET /api/graph` | the static half: declared topology + table datasheets. Fetched once |
| `GET /api/snapshot` | the latest tick as JSON, including the per-producer verdicts |
| `GET /api/history` | the server-side rolling window, so a page opened now is not empty |
| `GET /healthz` | liveness + whether each source is reachable |

## Develop

```bash
cd services/flow-ui
uv venv && uv pip install -e . && uv pip install pytest pytest-asyncio
.venv/bin/python -m pytest tests -q
.venv/bin/uvicorn flow_ui.main:app --reload --port 8080
```

## Contracts this reads

- **`contracts/collector/v1/pod2-pod3-read-contract.md` v1.0.0.1** — the bronze semantics. Only
  columns §2 guarantees are shown, absent optional IDs are `''` per §4, grouping is by
  `ServiceName` because §5.6 makes that the one index-accelerated axis, and the unindexed
  `ResourceAttributes` Map probes (§3, §6) stay off the per-tick path.
- **`services/generator-python/config/topology/default.yaml`** — the declared service graph.
  Read, not redrawn, so the picture cannot drift from what emits the telemetry. Edges point
  the way data *flows*: `depends_on: [a]` on `b` means the edge is `a → b`.

## Status

**V2.3.** Pod 2 self-observability plus the bronze read side, four boards, four zoom levels, two
palettes. 37 tests. Verified end to end against a live pipeline on 2026-09-01: mode detection
correct across stream, batch and idle; 1,015,100 signals stored, 0 rejected, 0 export errors.

**Known gaps, deliberate:** no language selector yet (V1 ships English; the selector lands with
the demo) · the *observed* topology is not yet derived from `ParentSpanId` and compared against
the declared one · the look has not been reviewed by anyone but the owner, because headless
capture cannot hold an SSE page still.
