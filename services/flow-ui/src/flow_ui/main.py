"""Sentinel flow UI — the pipeline watching itself.

Server-rendered HTML with an SSE channel on top, in the shape this monorepo's other
Python service already uses. Two things about the layering are deliberate:

**The browser never talks to the collector or to ClickHouse.** Not a style preference — a
constraint. The collector's `/metrics` server sets exactly one response header
(`Content-Type`; see `collector-rust/src/metrics_server.rs`) and ClickHouse has no CORS
header configured in `infra/`, so a cross-origin fetch from the page is blocked by the
browser with no visible error. This service is the only reader; it also means the page
works unchanged whatever host those two move to.

**The figures are in the HTML before any script runs.** The animation is an illustration
of numbers the page already printed — a blocked or slow script costs the motion, never the
reading. Borrowed from a sibling project's design rule: charts illustrate, they never
carry.

Run:  ``uv run uvicorn flow_ui.main:app --host 0.0.0.0 --port 8080``
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from flow_ui import topology
from flow_ui.clickhouse import EMPTY_BY_CONTRACT, ClickHouse
from flow_ui.config import settings
from flow_ui.pipeline import Poller

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
)
# httpx logs one INFO line per request; at one poll a second against two sources that is
# 172,800 lines a day saying the pipeline is fine.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("flow_ui")

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

poller = Poller(settings)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    await poller.start()
    try:
        yield
    finally:
        await poller.stop()


app = FastAPI(title="Sentinel flow", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def asset_v() -> str:
    """Cache-buster keyed to the NEWEST asset's mtime — no build step, no restart.

    Both files, not just the stylesheet: keyed to `app.css` alone, a change that touched
    only `app.js` left the script URL identical and the browser kept the old one.
    """
    newest = 0.0
    for name in ("app.css", "app.js"):
        try:
            newest = max(newest, (BASE / "static" / name).stat().st_mtime)
        except OSError:
            continue
    return str(int(newest))


def fmt(n: float) -> str:
    """Compact figures: a rate of 18,334/s has to fit a tile."""
    n = float(n)
    for unit, div in (("M", 1e6), ("k", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}"
    return f"{n:.0f}" if abs(n) >= 10 or n == int(n) else f"{n:.1f}"


templates.env.filters["fmt"] = fmt
templates.env.globals["asset_v"] = asset_v
templates.env.globals["EMPTY_BY_CONTRACT"] = EMPTY_BY_CONTRACT


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """The page, with the current snapshot already rendered into it."""
    snap = poller.latest
    return templates.TemplateResponse(request, "index.html", {
        "s": snap,
        "ingest_total": sum(snap.ingest_rate.values()),
        "reject_total": sum(snap.reject_rate.values()),
        "poll_ms": int(settings.poll_interval_s * 1000),
        # Server-rendered like every other figure, so the policy is right with JavaScript
        # disabled too — and it is read from the collector's config, never assumed.
        "contract": topology.CONTRACT,
    })


@app.get("/stream")
async def stream(request: Request):
    """Server-sent events: one snapshot per poll tick.

    SSE rather than a WebSocket because the traffic is one-way and SSE reconnects on its
    own — a dropped connection costs a gap in the animation, not a dead page.
    """
    async def events():
        queue = poller.broadcaster.subscribe()
        try:
            # Send the current state immediately so a page that connects between ticks
            # is not blank until the next one.
            yield f"data: {json.dumps(poller.latest.as_dict())}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    snap = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keepalive\n\n"   # keeps proxies from reaping an idle stream
                    continue
                yield f"data: {json.dumps(snap.as_dict())}\n\n"
        finally:
            poller.broadcaster.unsubscribe(queue)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",           # nginx would otherwise buffer the stream
    })


@app.get("/api/snapshot")
def snapshot() -> dict:
    """The latest tick as JSON — for debugging, and for anything that is not this page."""
    return poller.latest.as_dict()


@app.get("/api/graph")
async def graph() -> dict:
    """The static half of the picture: the producer's declared topology and what each
    bronze and silver table holds. Cheap and unchanging, so the page fetches it once at load
    and the SSE stream carries only the numbers that move.

    Silver's schema belongs here and not in the snapshot for the same reason the bronze
    datasheets do: three models of seventeen columns each would be ~3 KB repeated on every
    frame, once a second, to say what it said the tick before.
    """
    return {
        "topology": topology.service_graph(),
        "tables": topology.TABLE_DOCS,
        "silver_graph": await poller.clickhouse.silver_graph(),
        "silver_views": ClickHouse.SILVER_VIEW_DOCS,
        "empty_by_contract": topology.EMPTY_BY_CONTRACT,
        "derived": topology.DERIVED,
        "contract": topology.CONTRACT,
    }


@app.get("/api/history")
def history() -> dict:
    """The rolling window behind the health sparklines.

    Served separately from the SSE snapshot because the window is the same few hundred
    points on every tick — pushing it once a second would send the same data 300 times.
    The page fetches it once and appends each incoming snapshot itself.
    """
    return {"points": list(poller.history), "ceiling_ms": Poller.LATENCY_CEILING_MS}


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "collector": poller.latest.collector_up,
        "clickhouse": poller.latest.clickhouse_up,
        "subscribers": poller.broadcaster.subscribers,
    }
