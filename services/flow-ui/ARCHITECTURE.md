# flow-ui — architecture

What this service is made of, and how a number gets from the pipeline to the screen.

For *what the page shows and why it shows it that way*, see [DESIGN.md](DESIGN.md). This
document is the machinery under it.

## In one sentence

A **FastAPI** process that polls two sources on three cadences, keeps one in-memory snapshot,
renders it into HTML server-side, and pushes each subsequent tick over **SSE** to a
**dependency-free** browser page that redraws an SVG.

## The stack, and what is deliberately absent

| Layer | Choice | Why this and not the obvious alternative |
|---|---|---|
| Language | Python 3.12 | Pod 1 is already Python; this is a *reader*, not a hot path. The 730–18,000 signals/s never pass through here — only counters do |
| Web | FastAPI + Uvicorn | Async is the requirement: one SSE connection per viewer, held open, while two pollers run |
| Templating | Jinja2 | Every figure is in the HTML **before any script runs**. A blocked script costs the motion, never the reading |
| Transport | SSE (`text/event-stream`) | One-directional, server→client. WebSockets buy a return channel this page has no use for, and cost reconnection logic the browser gives SSE for free |
| HTTP client | httpx (async) | Both sources speak HTTP: the collector's `/metrics`, ClickHouse's `:8123` |
| Config | PyYAML | Reads Pod 1's `topology.yaml` and the collector's `config.docker.yaml` — *read*, never redrawn, so the picture cannot drift from what emits the telemetry |
| Front end | **none** | ~1.7k lines of plain ES2020 + SVG. No React, no D3, no bundler, no `package.json`, no build step |
| Styling | one hand-written stylesheet | Two palettes switched by one attribute. **Nothing in the CSS names a colour** — every value is a token, so the switch re-tests every colour decision against a second ground |

**Why no front-end framework.** The page is one graph that is never replaced — boxes grow in
place and the particles keep flowing through. React's model is to re-render a tree; this
page's core invariant is that the SVG elements carrying `animateMotion` **must not be
recreated**, or every dot restarts from the mouth of its pipe. Working against that is more
code than the DOM calls it replaces. `asset_v()` cache-busts on file mtime, so there is a
dev loop without a bundler.

## Components

```mermaid
flowchart LR
    subgraph src["sources — flow-ui is the only reader of any of them"]
        direction TB
        COL["collector-rust<br/>:9090/metrics"]
        CLICK[("ClickHouse :8123<br/>bronze.* ⇒ silver.*")]
        YAML["topology.yaml<br/>config.docker.yaml<br/>mounted read-only"]
    end

    subgraph svc["flow-ui — FastAPI :8080"]
        direction TB
        PROM["prom.py<br/>Prometheus text parser"]
        CH["clickhouse.py<br/>HTTP + TSV"]
        TOPO["topology.py<br/>YAML readers"]
        POLL["pipeline.py · Poller<br/>the only writer of Snapshot"]
        SNAP[("Snapshot<br/>one, in memory")]
        MAIN["main.py<br/>routes · Jinja2 render"]
    end

    subgraph browser["browser — no framework, no build step"]
        direction TB
        SVG["app.js · SVG canvas<br/>4 boards · 5 zoom levels"]
        CSS["app.css · 2 palettes<br/>no colour is named"]
    end

    COL -->|"poll 1 s"| PROM --> POLL
    CLICK -->|"poll 5 s / 30 s"| CH --> POLL
    YAML --> TOPO --> MAIN
    POLL --> SNAP --> MAIN
    MAIN ==>|"HTML · pre-rendered"| SVG
    MAIN -.->|"SSE /stream · 1 frame/s"| SVG
    CSS -.- SVG
```

**The browser never talks to the collector or to ClickHouse.** Not a preference — a
constraint. The collector's `/metrics` server sets exactly one response header
(`Content-Type`; see `collector-rust/src/metrics_server.rs`) and ClickHouse has no CORS header
configured under `infra/`, so a cross-origin fetch from the page is blocked with no visible
error. This service is the only reader of either, which also means the page works unchanged
wherever those two move to. A test pins it.

## Three cadences, because the queries cost three different things

The Poller runs one fast loop and two slow tasks. They are separate because sharing a cadence
would make the cheapest reading wait on the most expensive one.

```mermaid
flowchart LR
    F["fast · 1 s<br/>/metrics → mode · rates · verdict"]
    L["lineage · 5 s<br/>count() · GROUP BY ServiceName · volume band<br/>call_edges · service_health · silver_state"]
    C["contract · 30 s<br/>contract_violations"]

    F --> SNAP[("Snapshot<br/>one, in memory")]
    L --> SNAP
    C --> SNAP
    SNAP --> OUT["GET /<br/>GET /stream<br/>GET /api/*"]
```

| Lane | Env | Cost |
|---|---|---|
| fast · 1 s | `FLOW_UI_POLL_INTERVAL` | counters only — constant |
| lineage · 5 s | `FLOW_UI_LINEAGE_INTERVAL` | `count()` and `system.tables` read part metadata; no scan |
| contract · 30 s | `FLOW_UI_CONTRACT_INTERVAL` | probes the **unindexed** `ResourceAttributes` Map — 1.26 s measured |

Each slow task owns its own `while True` and swallows its own exceptions, so a failing
ClickHouse degrades the boards it feeds and never stops the tick. `stop()` cancels and awaits
both, so a reload does not leak them.

**Why the contract lane is 30 s and alone.** `contract_violations()` counts rows missing each
required `sentinel.*` key across every live table. The `ARRAY JOIN` form multiplies every row
by five before filtering — 6.4 s against 1.26 s for `countIf`, over the same ~6M rows. Even at
1.26 s it must not share the 5 s lane.

**Why bronze growth is `count()` deltas and never a time window.** Bronze stores *event* time
— the read contract (§2) defines `Timestamp` as the signal's own timestamp and there is no
ingest-time column. In backfill the generator writes five minutes of history in thirteen
seconds, so `WHERE Timestamp > now() - INTERVAL 10 SECOND` answers "what *happened* recently",
which is a different question. It is also 40,000× the rows: bare `count()` reads 1 row of part
metadata (3.7 ms measured); the windowed form scans the table.

## A tick, end to end

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as main.py
    participant P as Poller
    participant M as collector /metrics
    participant C as ClickHouse

    Note over B,A: first load — nothing is empty
    B->>A: GET /
    A->>A: Jinja2 renders poller.latest into the HTML
    A-->>B: page with every figure already printed
    B->>A: GET /api/history
    A-->>B: server-side rolling window (60 pts)
    B->>A: GET /api/graph
    A-->>B: declared topology + table datasheets (fetched once)
    B->>A: EventSource /stream

    loop every 1 s
        P->>M: GET /metrics
        M-->>P: Prometheus text
        P->>P: parse · detect mode · reject matrix · verdict
        P->>P: publish(Snapshot) to each subscriber queue
        A-->>B: data: {...}
        B->>B: repaint SVG · re-seed particle pools
    end

    loop every 5 s / 30 s
        P->>C: count() · GROUP BY · system.tables
        C-->>P: TSV
        P->>P: mutate Snapshot in place
    end
```

**A full subscriber queue drops its own frames, never the publisher's tick.** One slow tab
must not stall the poll loop or the other viewers; `publish()` discards into a full queue and
moves on. A test pins that too.

## Modules

```mermaid
flowchart TB
    MAIN["main.py — 179<br/>6 routes, Jinja2 globals, lifespan"]
    PIPE["pipeline.py — 530<br/>Poller, Snapshot, volume_state, _verdict"]
    CH["clickhouse.py — 468<br/>every SQL string in the service"]
    PROM["prom.py — 171<br/>Prometheus text → Sample"]
    TOPO["topology.py — 217<br/>topology.yaml + collector config"]
    CFG["config.py — 49<br/>env only, no config file"]

    MAIN --> PIPE
    MAIN --> TOPO
    PIPE --> CH
    PIPE --> PROM
    PIPE --> CFG
    CH --> CFG
```

The split is by **source**, not by feature: one module per thing that can be unreachable.
`prom.py` and `clickhouse.py` each own their failure mode, and `pipeline.py` decides what an
unreachable source means for the verdict.

Two parsing rules worth knowing before changing either reader:

- **An absent metric family is a normal state, not an error.** The collector's labelled
  counters are `IntCounterVec`s, and a `*Vec` exposes nothing until a label combination is
  instantiated. A freshly started collector serves three families; the other five appear when
  traffic does. `Sample.value()` returns `0.0` for anything absent.
- **`Sample.sum_over_pair`, because two separate reads cannot recover a cross-product.**
  `signals_rejected_total` is labelled by both `signal` and `reason`. Reading it once by
  `signal` and once by `reason` loses which type failed which way — which is exactly what
  colours the dot leaving the chain.

## Where the data comes from

```mermaid
flowchart LR
    subgraph measured["measured"]
        M1["collector /metrics<br/>rates · flush cadence · rejections · export latency"]
        M2["bronze.*<br/>row counts · per-service lineage · contract violations · volume band · call edges"]
        M3["silver.service_health_1m<br/>observed p50 latency · error rate"]
        M4["system.tables · system.columns<br/>Silver's own shape — kinds, columns, lineage"]
    end
    subgraph declared["declared"]
        D1["topology.yaml<br/>the service graph, and each component's claimed latency"]
        D2["config.docker.yaml<br/>contract.grpc_validation — off / warn / strict"]
        D3["pod2-pod3-read-contract v1.0.0.1<br/>the bronze datasheets"]
    end
    M3 --> J{"declared → measured<br/>drawn as two claims"}
    D1 --> J
    M4 --> S["the SILVER board draws itself<br/>from the database, not from a list"]
```

The whole point of the ORIGIN board is that seam: `topology.yaml` says what a component's
latency *should* be, `silver.service_health_1m` says what its operations *took*. The two
agreeing is the baseline; the two diverging is the finding. Declared-but-never-traced edges
are drawn dashed rather than at a width that would imply traffic they do not carry.

## Deployment

One container, one process, no state on disk.

```mermaid
flowchart LR
    subgraph compose["docker compose — one network"]
        G["generator<br/>python"] -->|"OTLP gRPC :4317"| CO["collector-rust"]
        CO -->|"HTTP insert"| CH[("clickhouse<br/>:8123 · :9000")]
        CH -.->|"MVs, on insert"| CH
        FU["flow-ui :8080"] -->|":9090/metrics"| CO
        FU -->|":8123"| CH
    end
    U(("browser")) -->|":8080"| FU
```

Configuration is environment only — there is no config file for this service:

| Env | Default |
|---|---|
| `COLLECTOR_METRICS_URL` | `http://localhost:9090/metrics` (compose: `http://collector:9090/metrics`) |
| `CLICKHOUSE_URL` | `http://localhost:8123` (compose: `http://clickhouse:8123`) |
| `CLICKHOUSE_DATABASE` | `bronze` |
| `GENERATOR_CONFIG_DIR` | `/app/generator-config` — Pod 1's config, mounted read-only |
| `FLOW_UI_POLL_INTERVAL` | `1.0` — matches the stream-mode flush cadence |
| `FLOW_UI_LINEAGE_INTERVAL` | `5.0` |
| `FLOW_UI_CONTRACT_INTERVAL` | `30.0` |
| `FLOW_UI_VOLUME_WINDOW_MIN` | `60` |
| `FLOW_UI_HISTORY` | `60` — points in the server-side rolling window |

Scaling note: the Snapshot is **per process**, so more than one replica behind a load balancer
gives two viewers two different pictures a second apart. That is fine for one crew and wrong
for a shared deployment; the fix is a shared store, and nothing here needs it yet.

## What is not tested, and it is the same gap every time

63 tests cover the parsing, the poller's inferences and the pure verdict logic. They cover
**nothing about SVG geometry** — where things land on the canvas is checked by looking, and
that gap has cost real defects: a detail panel drawn over the nodes it described, two header
collisions, and a pipe routed out from under the box it was meant to reach. A geometry test is
on the roadmap in [STATUS.md](STATUS.md).

## See also

- [README.md](README.md) — run it, break it on purpose, endpoints
- [DESIGN.md](DESIGN.md) — the visual grammar and the rules it holds to
- [STATUS.md](STATUS.md) — what shipped, in order, and what is next
- [`contracts/collector/v1/pod2-pod3-read-contract.md`](../../contracts/collector/v1/pod2-pod3-read-contract.md) — the bronze semantics this reads
- [ADR-0010](../../docs/adr/0010-silver-v1-operational-model.md) — the Silver models and their materialized views
