"""The poller: one background task that turns two data sources into a stream of snapshots.

The browser never polls anything. This task scrapes the collector and ClickHouse on a
fixed cadence, derives per-second rates, and pushes a snapshot to every open SSE
subscriber. One poller regardless of how many people have the page open.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass, field

import httpx

from flow_ui import prom, topology
from flow_ui.clickhouse import EMPTY_BY_CONTRACT, LIVE_TABLES, ClickHouse
from flow_ui.config import Settings

log = logging.getLogger("flow_ui.pipeline")

M_INGESTED = "sentinel_signals_ingested_total"
M_ACCEPTED = "sentinel_signals_accepted_total"
M_REJECTED = "sentinel_signals_rejected_total"
M_STORAGE = "sentinel_storage_signals_total"
M_FLUSH = "sentinel_batch_flush_total"
M_FLUSH_COUNT = "sentinel_batch_flush_size_count"
M_FLUSH_SUM = "sentinel_batch_flush_size_sum"
M_ERRORS = "sentinel_export_errors_total"
M_LAT_COUNT = "sentinel_export_latency_seconds_count"
M_LAT_SUM = "sentinel_export_latency_seconds_sum"

#: Flush cadence that separates the two delivery shapes. Measured on this pipeline:
#: `--mode stream` settles at 1.03 flushes/s carrying 500–1000 records each, while
#: `--mode backfill` runs at 6.6 flushes/s (min 4, max 8) carrying ~2534. Three sits in
#: the empty gap between the two distributions rather than at either edge.
BATCH_FLUSH_RATE = 3.0

#: A batch that big never appears in stream mode — it is the second, independent tell, so
#: a burst is still read as batch even if a poll lands mid-cadence.
BATCH_RECORDS_PER_FLUSH = 1500.0

MODE_IDLE, MODE_STREAM, MODE_BATCH = "idle", "stream", "batch"

#: Volume watcher. The threshold is Elementary's documented one — plain z-score at 3.0 — and
#: the *estimator* is what changes: median and MAD rather than mean and stddev, so a single
#: bad bucket does not widen the band that is supposed to catch it. Dual severity, because
#: one number cannot both page someone and merely be noted.
Z_WARN, Z_ERROR = 3.0, 5.0

#: Scales MAD into a stddev-equivalent for normally distributed data, so `Z_WARN` keeps its
#: usual meaning instead of being a magic number tied to a different estimator.
MAD_TO_SIGMA = 1.4826

#: Below this many buckets there is no distribution to speak of, and a band drawn from three
#: points is theatre. Reported as unmonitored — Bigeye's grey — never as healthy.
MIN_BUCKETS = 8

#: A band that rejects more than this share of the window it was BUILT FROM is not describing
#: the data; it is describing one mode of it. Measured here: a producer alternating between
#: full minutes (2850 rows) and partial ones (600–1600) has a median on the dominant mode and
#: a MAD of 50 against a true spread of 699, so the 3σ band excluded 14 of its own 31
#: training buckets — and then alerted. Three-sigma on a series this estimator actually fits
#: excludes a few percent; 15% means the model is wrong, not the data.
MAX_OOB_SHARE = 0.15


def _oob_share(series: list, med: float, scale: float) -> float:
    """Share of the training window that falls outside the band built from it."""
    if not series:
        return 0.0
    lo, hi = med - Z_WARN * scale, med + Z_WARN * scale
    return sum(1 for _, n in series if n < lo or n > hi) / len(series)


def volume_state(row: dict) -> dict:
    """One producer's volume verdict, and the band it was judged against.

    **The band returned here is the threshold.** Metaplane shipped a version where the drawn
    area and the alerting rule were computed separately, then publicly called reconciling
    them a "simplification": *"if you see a value outside the green area, Metaplane sent an
    alert."* Computing both in one place is how that stays true.

    Four states, not two — the distinction most health widgets lose:

    * `passing`     — inside the band.
    * `warn`/`fail` — outside it, at 3σ and 5σ.
    * `unmonitored` — too few buckets, or no dispersion to model at all. A perfectly regular
      producer has MAD = 0 and a zero-width band in which every value is infinitely
      anomalous; stddev is tried next, and if that is also flat the series is declared
      unmodellable rather than alarmed on. Grey means *not observed*, never *fine*.

    `absent` is a separate axis, not a band violation: buckets in which the estate received
    something and this producer did not. A tool reading a table at rest sees a stale table;
    only a pipeline-centric one can see the write that never happened.
    """
    med, mad, sd = row["median"], row["mad"], row["sd"]
    seen, estate, latest = row["seen"], row["estate"], row["latest"]
    series = row.get("series") or []
    absent = max(0, estate - seen)
    base = {**row, "absent": absent}
    grey = {**base, "scale": 0.0, "estimator": "none", "lo": med, "hi": med, "z": 0.0,
            "state": "unmonitored"}

    if estate < MIN_BUCKETS:
        return {**grey, "why": f"only {estate} buckets in the window"}

    # A cascade with a validity test at each step, not a switch on `mad > 0`. The switch was
    # a cliff: MAD crossing zero moved σ from 74 to 699 between two consecutive ticks and
    # flipped every producer from passing to alerting on one new bucket. Which estimator to
    # use is not a property of MAD being non-zero — it is whether the band it produces
    # actually contains the window.
    for name, scale in (("mad", mad * MAD_TO_SIGMA), ("stddev", sd)):
        if scale <= 0:
            continue
        share = _oob_share(series, med, scale)
        if share > MAX_OOB_SHARE:
            continue
        z = abs(latest - med) / scale
        state = "fail" if z >= Z_ERROR else "warn" if z >= Z_WARN else "passing"
        return {**base, "estimator": name, "scale": round(scale, 2), "state": state,
                "z": round(z, 2), "oob": round(share, 3),
                "lo": round(med - Z_WARN * scale, 1), "hi": round(med + Z_WARN * scale, 1),
                "why": f"{z:.1f}σ from a median of {med:.0f}"}

    if mad <= 0 and sd <= 0:
        return {**grey, "why": "no dispersion to model"}
    # Both estimators produced a band that rejects its own window. That is a multi-modal
    # series — here, full minutes and partial ones — which no single band describes. Saying
    # so is the honest output; alerting eight producers at once is not.
    return {**grey, "why": "no band fits this window — the series is not single-mode"}


@dataclass
class Snapshot:
    """One tick. Everything the page needs, already reduced to numbers it can draw."""

    ts: float = 0.0
    mode: str = MODE_IDLE
    collector_up: bool = False
    clickhouse_up: bool = False

    #: Per-second rates at the gRPC receive boundary, by signal type. The three types are
    #: distinguishable *only* here — see `flushes` below.
    ingest_rate: dict[str, float] = field(default_factory=dict)
    accept_rate: dict[str, float] = field(default_factory=dict)
    reject_rate: dict[str, float] = field(default_factory=dict)

    #: Rejections split by *reason*, which the per-signal view loses. The collector emits
    #: two and they are different problems with different destinations:
    #:   `contract`     — validation failed. Under `warn` the signal is counted and
    #:                    **exported anyway**, so it still reaches bronze. Only `strict`
    #:                    discards it.
    #:   `backpressure` — the buffer was full, so the whole batch was refused and the
    #:                    producer told (`resource_exhausted`). It can retry; nothing is
    #:                    lost yet.
    reject_by_reason: dict[str, float] = field(default_factory=dict)

    #: The cross-product the two views above each throw away: ``{reason: {signal: rate}}``.
    #: `signals_rejected_total` is labelled with BOTH `signal` and `reason` at the
    #: increment site, so *which* signal type failed *which* way is measured, not guessed
    #: — and it is the only place upstream of the buffer where that stays true. The page
    #: draws the falling dot in that type's colour off the back of this.
    reject_matrix: dict[str, dict[str, float]] = field(default_factory=dict)

    #: From the buffer onward the collector labels everything `signal="all"`: the
    #: `BufferedExporter` enqueues every signal variant into one combined channel and
    #: flushes a mixed batch, so no per-type flush boundary exists to label. This is
    #: documented as deliberate in `collector-rust/src/metrics.rs`, not a gap to fill —
    #: which is why the page draws three lanes into the buffer and one lane out of it.
    flush_rate: float = 0.0
    records_per_flush: float = 0.0

    #: Mean, and the tail the mean hides. Measured on this pipeline: a 24.5 ms average
    #: sits over a 79 ms p99 — three times higher — so a single number cannot answer
    #: whether export is healthy.
    export_latency_ms: float = 0.0
    export_latency_p50: float = 0.0
    export_latency_p90: float = 0.0
    export_latency_p99: float = 0.0

    #: A verdict with the evidence behind it, decided in one place so the rule is testable
    #: rather than scattered through the page.
    health: str = "idle"
    health_note: str = "no traffic"
    persist_rate: float = 0.0
    drop_rate: float = 0.0

    #: Cumulative, for the ledger lines.
    totals: dict[str, float] = field(default_factory=dict)
    export_errors: float = 0.0

    #: Bronze — row counts and their per-second growth (deltas of `count()`).
    bronze: dict[str, int] = field(default_factory=dict)
    bronze_rate: dict[str, float] = field(default_factory=dict)
    bronze_empty: list[str] = field(default_factory=lambda: list(EMPTY_BY_CONTRACT))
    lineage: list[dict] = field(default_factory=list)

    #: Which named metrics each service emits, keyed by destination table. This is the
    #: only per-service distinction that exists downstream: bronze routes by data-point
    #: type, never by producer, so every service reaches every table. What differs is the
    #: metric mix — and that is what makes one service's gauge:sum split 3:1 and another's
    #: 1:2. Refreshed on the slow lane; the inventory is effectively static.
    metrics_by_service: dict = field(default_factory=dict)
    scenario: str = "—"

    #: What Silver holds — `{present, models, views, mvs}`. `present` is load-bearing: a
    #: volume created before the Silver DDL has no `silver` database, and an absent Silver is
    #: a different statement from an empty one. Empty is normal on a fresh stack, because the
    #: MVs do not `POPULATE` and only see inserts made after the DDL was applied.
    silver: dict = field(default_factory=dict)

    #: Per-producer latency and error rate, read from `silver.service_health_1m`. The first
    #: thing this service reads out of Silver rather than deriving from Bronze — and an
    #: addition, not a migration: Silver's MVs do not `POPULATE`, so it only knows what
    #: arrived after its DDL was applied. Empty when Silver is not deployed.
    service_health: list[dict] = field(default_factory=list)

    #: The call graph as traced: `{src, dst, spans, errors}`. The only per-edge measurement
    #: in the pipeline — it exists because a child span carries its parent, so the two rows
    #: join and the two `ServiceName`s are the edge. Compared against the *declared* topology
    #: in the UI, because the two disagreeing is itself the finding.
    call_edges: list[dict] = field(default_factory=list)

    #: Volume watcher, per producer: the band and the verdict it was judged against.
    volume: list[dict] = field(default_factory=list)

    #: Contract health, per producer — the one thing the receive boundary cannot answer.
    #: `signals_rejected_total` has `signal` and `reason` but no service label, so it says
    #: how many violated and how, never *who*. Bronze can, because under `warn` a violating
    #: signal is exported anyway and the evidence lands in the table. Slow lane; see
    #: `Settings.contract_interval_s`.
    contract_violations: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class Broadcaster:
    """Fan one snapshot out to every open SSE connection.

    Each subscriber gets its own bounded queue: a slow reader drops its own frames rather
    than stalling the poller or any other viewer.
    """

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, snap: Snapshot) -> None:
        for q in list(self._subs):
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(snap)

    @property
    def subscribers(self) -> int:
        return len(self._subs)


class Poller:
    """Scrapes both sources on a cadence and publishes snapshots."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._ch = ClickHouse(settings.clickhouse_url, settings.clickhouse_database)
        self._http = httpx.AsyncClient(timeout=3.0)
        self.broadcaster = Broadcaster()
        self.latest = Snapshot()
        self._prev: prom.Sample | None = None
        self._prev_t: float = 0.0
        self._prev_bronze: dict[str, int] = {}
        self._prev_bronze_t: float = 0.0
        self._flush_rates: deque[float] = deque(maxlen=5)
        #: A rolling window of what each tick looked like. Kept on the server so a page
        #: opened now still gets the last few minutes instead of an empty chart, and so
        #: two viewers see the same history.
        self.history: deque[dict] = deque(maxlen=settings.history)
        self._signals = ("logs", "trace", "metrics")
        #: `None` until the first scrape, because the collector's `export_errors_total` is
        #: cumulative over its whole life: treating 0 as the baseline made every batch it had
        #: ever lost look like a fresh loss, and the page opened on FAIL.
        self._errors_seen: float | None = None
        #: Read from the collector's own config rather than assumed. It was hard-coded to
        #: `warn`, so under `strict` the health note said contract failures were "exported
        #: anyway" when they had been discarded at the boundary.
        self._policy: str = topology.grpc_validation()
        self._task: asyncio.Task | None = None
        #: Retained so `stop()` can cancel them. Unheld, they outlived the poller and went on
        #: querying an httpx client that had already been closed.
        self._slow: list[asyncio.Task] = []

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        for task in self._slow:
            task.cancel()
        for task in self._slow:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._slow.clear()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._ch.aclose()
        await self._http.aclose()

    async def _scrape(self) -> prom.Sample | None:
        try:
            resp = await self._http.get(self._s.collector_metrics_url)
            resp.raise_for_status()
            return prom.parse(resp.text)
        except httpx.HTTPError as exc:
            log.debug("collector scrape failed: %s", exc)
            return None

    def _detect_mode(self, flush_rate: float, per_flush: float, ingest: float) -> str:
        """Which delivery shape the pipeline is running, inferred from the buffer.

        Nobody tells this app whether the generator was started in stream or backfill
        mode — the flush cadence is the tell, and it is unambiguous because the two modes
        differ by ~6x in rate and ~3x in batch size at the same time.
        """
        if ingest <= 0 and flush_rate <= 0:
            return MODE_IDLE
        smoothed = max(self._flush_rates) if self._flush_rates else flush_rate
        if smoothed >= BATCH_FLUSH_RATE or per_flush >= BATCH_RECORDS_PER_FLUSH:
            return MODE_BATCH
        return MODE_STREAM

    async def _tick(self) -> None:
        now = time.monotonic()
        sample = await self._scrape()
        snap = Snapshot(ts=time.time(), collector_up=sample is not None)

        if sample is not None and self._prev is not None:
            dt = now - self._prev_t
            prev = self._prev

            def by_signal(metric: str) -> dict[str, float]:
                cur = sample.sum_over(metric, "signal")
                old = prev.sum_over(metric, "signal")
                # Union of both scrapes' keys: a family that only just appeared has no
                # previous entry, and one that vanished should still report zero.
                return {
                    k: round(prom.rate(cur.get(k, 0.0), old.get(k, 0.0), dt), 1)
                    for k in set(cur) | set(old)
                }

            snap.ingest_rate = by_signal(M_INGESTED)
            snap.accept_rate = by_signal(M_ACCEPTED)
            snap.reject_rate = by_signal(M_REJECTED)
            cur_r, old_r = sample.sum_over(M_REJECTED, "reason"), prev.sum_over(M_REJECTED, "reason")
            snap.reject_by_reason = {
                k: round(prom.rate(cur_r.get(k, 0.0), old_r.get(k, 0.0), dt), 2)
                for k in set(cur_r) | set(old_r)
            }
            cur_m = sample.sum_over_pair(M_REJECTED, "reason", "signal")
            old_m = prev.sum_over_pair(M_REJECTED, "reason", "signal")
            snap.reject_matrix = {
                reason: {
                    sig: round(prom.rate(cur_m.get(reason, {}).get(sig, 0.0),
                                         old_m.get(reason, {}).get(sig, 0.0), dt), 2)
                    for sig in set(cur_m.get(reason, {})) | set(old_m.get(reason, {}))
                }
                for reason in set(cur_m) | set(old_m)
            }

            fc, fc0 = sample.value(M_FLUSH_COUNT), prev.value(M_FLUSH_COUNT)
            fs, fs0 = sample.value(M_FLUSH_SUM), prev.value(M_FLUSH_SUM)
            snap.flush_rate = round(prom.rate(fc, fc0, dt), 2)
            d_flush, d_recs = fc - fc0, fs - fs0
            snap.records_per_flush = round(d_recs / d_flush, 0) if d_flush > 0 else 0.0

            lc, lc0 = sample.value(M_LAT_COUNT), prev.value(M_LAT_COUNT)
            ls, ls0 = sample.value(M_LAT_SUM), prev.value(M_LAT_SUM)
            snap.export_latency_ms = round((ls - ls0) / (lc - lc0) * 1000, 1) if lc > lc0 else 0.0
            for q, attr in ((0.5, "p50"), (0.9, "p90"), (0.99, "p99")):
                setattr(snap, f"export_latency_{attr}",
                        round(prom.quantile(sample, "sentinel_export_latency_seconds", q) * 1000, 1))

            storage_now = sample.sum_over(M_STORAGE, "outcome")
            storage_old = prev.sum_over(M_STORAGE, "outcome")
            snap.persist_rate = round(prom.rate(
                storage_now.get("persisted", 0.0), storage_old.get("persisted", 0.0), dt), 1)
            snap.drop_rate = round(prom.rate(
                storage_now.get("dropped", 0.0), storage_old.get("dropped", 0.0), dt), 1)

            self._flush_rates.append(snap.flush_rate)
            snap.mode = self._detect_mode(
                snap.flush_rate, snap.records_per_flush, sum(snap.ingest_rate.values()))

        if sample is not None:
            snap.totals = {
                "ingested": sample.value(M_INGESTED),
                "accepted": sample.value(M_ACCEPTED),
                "rejected": sample.value(M_REJECTED),
                "flushes": sample.value(M_FLUSH_COUNT),
                "records": sample.value(M_FLUSH_SUM),
                "persisted": sample.sum_over(M_STORAGE, "outcome").get("persisted", 0.0),
            }
            snap.export_errors = sample.value(M_ERRORS)
            self._prev, self._prev_t = sample, now

        # Bronze counts every tick (metadata-only, ~4ms); lineage on the slow cadence.
        counts = await self._ch.counts()
        snap.clickhouse_up = any(counts.values()) or await self._ch.ping()
        snap.bronze = counts or dict.fromkeys(LIVE_TABLES, 0)
        if self._prev_bronze and counts:
            dtb = now - self._prev_bronze_t
            snap.bronze_rate = {
                t: round(prom.rate(counts.get(t, 0), self._prev_bronze.get(t, 0), dtb), 1)
                for t in LIVE_TABLES
            }
        if counts:
            self._prev_bronze, self._prev_bronze_t = counts, now

        snap.health, snap.health_note = self._verdict(snap)
        self.history.append({
            "t": round(snap.ts, 1),
            "in": round(sum(snap.ingest_rate.values()), 1),
            "fl": snap.flush_rate,
            "lat": snap.export_latency_ms,
            "st": snap.persist_rate,
            "rj": round(sum(snap.reject_rate.values()), 2),
            # Rejections split by reason AND signal, so the contract board can chart which
            # type was failing which way over the window. The aggregate `rj` above cannot
            # be decomposed after the fact.
            "rc": [snap.reject_matrix.get("contract", {}).get(k, 0.0) for k in self._signals],
            "rb": [snap.reject_matrix.get("backpressure", {}).get(k, 0.0) for k in self._signals],
            "dr": snap.drop_rate,
            "m": snap.mode,
        })
        snap.lineage = self.latest.lineage
        snap.metrics_by_service = self.latest.metrics_by_service
        snap.scenario = self.latest.scenario
        snap.contract_violations = self.latest.contract_violations
        snap.volume = self.latest.volume
        snap.call_edges = self.latest.call_edges
        snap.service_health = self.latest.service_health
        snap.silver = self.latest.silver
        self.latest = snap
        self.broadcaster.publish(snap)

    #: The measured ceiling for this pipeline: every flush attempt landed at or under
    #: 80 ms in the reference run, so a p99 above it means the tail has changed shape.
    LATENCY_CEILING_MS = 80.0

    def _verdict(self, snap: Snapshot) -> tuple[str, str]:
        """One state and the reason for it. Colour is never the only carrier — the note is
        the sentence a reader acts on."""
        if not snap.collector_up:
            return "fail", "collector unreachable"
        if not snap.clickhouse_up:
            return "fail", "clickhouse unreachable"
        # First scrape establishes the baseline; a lifetime total is not a fresh loss.
        lost = 0.0 if self._errors_seen is None else snap.export_errors - self._errors_seen
        self._errors_seen = snap.export_errors
        if snap.drop_rate > 0 or lost > 0:
            return "fail", f"{snap.drop_rate:.2g}/s dropped · {snap.export_errors:.0f} batches lost"
        back = snap.reject_by_reason.get("backpressure", 0.0)
        if back > 0:
            # Not data loss: the producer was refused and can retry. But it means the
            # collector could not keep up, which is a different alarm from a bad payload.
            return "warn", f"{back:.2g}/s refused — buffer saturated, producer told to retry"
        contract = snap.reject_by_reason.get("contract", 0.0)
        if contract > 0:
            policy = "exported anyway" if self._policy == "warn" else "discarded"
            return "warn", f"{contract:.2g}/s failing the contract · {policy}"
        if snap.export_latency_p99 > self.LATENCY_CEILING_MS:
            return "warn", f"export p99 {snap.export_latency_p99:.0f} ms over {self.LATENCY_CEILING_MS:.0f} ms"
        if sum(snap.ingest_rate.values()) <= 0:
            return "idle", "no traffic"
        return "ok", "flowing, nothing rejected or lost"

    async def _refresh_lineage(self) -> None:
        while True:
            try:
                lineage = await self._ch.lineage()
                scenario = await self._ch.scenario()
                inventory = await self._ch.metric_inventory()
                band = await self._ch.volume_band(self._s.volume_window_min)
                edges = await self._ch.call_edges()
                health = await self._ch.service_health()
                silver = await self._ch.silver_state()
                self.latest.lineage = lineage
                self.latest.scenario = scenario
                self.latest.metrics_by_service = inventory
                self.latest.volume = [volume_state(r) for r in band]
                self.latest.call_edges = edges
                self.latest.service_health = health
                self.latest.silver = silver
            except Exception as exc:                      # noqa: BLE001 — never kill the loop
                log.debug("lineage refresh failed: %s", exc)
            await asyncio.sleep(self._s.lineage_interval_s)

    async def _refresh_contract(self) -> None:
        """Contract health on its own, slower lane — it scans an unindexed Map across every
        live table, so it must not share the lineage cadence."""
        while True:
            try:
                self.latest.contract_violations = await self._ch.contract_violations()
            except Exception as exc:                      # noqa: BLE001 — never kill the loop
                log.debug("contract refresh failed: %s", exc)
            await asyncio.sleep(self._s.contract_interval_s)

    async def _run(self) -> None:
        self._slow = [asyncio.create_task(self._refresh_lineage()),
                      asyncio.create_task(self._refresh_contract())]
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:                      # noqa: BLE001
                log.warning("poll tick failed: %s", exc)
            await asyncio.sleep(self._s.poll_interval_s)
