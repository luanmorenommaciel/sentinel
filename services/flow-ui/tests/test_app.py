"""The page, asserted by the markup it actually served.

`TestClient` is used without its context manager on purpose: entering it would run the
lifespan and start the real poller, which would try to reach a collector and a ClickHouse.
These tests render against an injected snapshot instead.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from flow_ui import main
from flow_ui.pipeline import Snapshot

client = TestClient(main.app)


def _snapshot() -> Snapshot:
    return Snapshot(
        mode="batch", collector_up=True, clickhouse_up=True,
        ingest_rate={"logs": 3100.0, "trace": 3100.0, "metrics": 12154.0},
        reject_rate={"logs": 0.4},
        reject_by_reason={"contract": 0.4},
        reject_matrix={"contract": {"logs": 0.4}},
        contract_violations=[{"service": "third-party-agent", "rows": 2760,
                              "violating": 2760,
                              "missing": {"sentinel.run_id": 2760},
                              "total_missing": 2760}],
        flush_rate=5.9, records_per_flush=2500.0, export_latency_ms=45.3,
        persist_rate=14750.0, drop_rate=0.0,
        totals={"ingested": 233100.0, "persisted": 233100.0},
        bronze={"otel_logs": 40200, "otel_traces": 40200,
                "otel_metrics_gauge": 83400, "otel_metrics_sum": 69300},
        bronze_rate={"otel_logs": 2723.0},
        lineage=[{"service": "pubsub-ingestion-topic", "total": 98700,
                  "logs": 16450, "traces": 16450, "gauge": 32900, "sum": 32900}],
        metrics_by_service={"pubsub-ingestion-topic": {
            "gauge": ["operation.latency_ms"],
            "sum": ["operation.request_count", "operation.error_count"]}},
        scenario="baseline",
    )


def test_the_figures_are_printed_before_any_script_runs(monkeypatch):
    """The load-bearing property: with JavaScript disabled the page still answers what the
    pipeline is doing. The graph only illustrates these numbers."""
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    body = client.get("/").text
    assert "18.4k" in body          # 3100 + 3100 + 12154 signals/s
    assert "2.5k" in body           # records per batch
    assert ">45<" in body           # export latency, ms, rounded for the tile
    assert "14.8k" in body          # stored/s


def test_the_detected_mode_is_no_longer_in_the_header(monkeypatch):
    """The header used to print `baseline stream` — two bare words with no label, which
    read as noise. They were removed deliberately. The mode is still detected and still
    reaches the client; it is drawn on the Health timeline, where a coloured region and a
    duration say what a bare word could not."""
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    body = client.get("/").text
    assert "baseline" not in body
    assert client.get("/api/snapshot").json()["mode"] == "batch"


def test_a_nonzero_rejection_rate_marks_its_tile(monkeypatch):
    """Rejections must be legible as a state, not only as a number — the tile takes a
    class so it reads at a glance, and colour is never the only carrier."""
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    body = client.get("/").text
    assert 'class="tile bad"' in body and "rejected/s" in body


def test_an_empty_snapshot_renders_a_real_state_not_a_crash(monkeypatch):
    """Cold start: no scrape yet, every labelled counter family absent from /metrics.
    The tiles must still render — as zeros, which is the truth — rather than blank."""
    monkeypatch.setattr(main.poller, "latest", Snapshot())
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="t-in"' in resp.text and 'id="t-fl"' in resp.text
    assert "signals/s" in resp.text


def test_the_page_defaults_to_the_command_palette(monkeypatch):
    """Both palettes are complete, but the page must paint one before any script runs —
    a document with no world attribute would render on the host's ground."""
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    assert 'data-world="command"' in client.get("/").text


def test_the_page_never_points_the_browser_at_the_collector_or_clickhouse(monkeypatch):
    """CORS: the collector's /metrics server sets only Content-Type and ClickHouse has no
    CORS header configured, so a fetch from the page would be blocked with no visible
    error. If an edit ever puts those origins in the markup, this fails."""
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    body = client.get("/").text
    assert ":9090" not in body
    assert ":8123" not in body


def test_graph_endpoint_carries_the_declared_topology_and_table_docs():
    data = client.get("/api/graph").json()
    assert len(data["topology"]["nodes"]) == 7
    assert len(data["topology"]["edges"]) == 8
    assert set(data["tables"]) == {
        "otel_logs", "otel_traces", "otel_metrics_gauge", "otel_metrics_sum"}
    # The three permanently-empty tables are named, so zero rows reads as a decision.
    assert "otel_metrics_histogram" in data["empty_by_contract"]
    assert data["contract"]["consumer_version"] == "1.0.0.1"


def test_snapshot_endpoint_returns_the_current_tick(monkeypatch):
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    data = client.get("/api/snapshot").json()
    assert data["mode"] == "batch"
    assert data["bronze"]["otel_logs"] == 40200


def test_healthz_reports_both_sources(monkeypatch):
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    assert client.get("/healthz").json() == {
        "ok": True, "collector": True, "clickhouse": True, "subscribers": 0}


def test_fmt_keeps_a_rate_readable_in_a_tile():
    assert main.fmt(18354) == "18.4k"
    assert main.fmt(5.9) == "5.9"
    assert main.fmt(0) == "0"
    assert main.fmt(1_200_000) == "1.2M"


def test_the_snapshot_carries_what_each_zoom_level_needs(monkeypatch):
    """The page fetches /api/graph once for the static half and reads the SSE snapshot for
    everything that moves. These are the fields the detail levels read; dropping one would
    blank a view with no error."""
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    d = client.get("/api/snapshot").json()
    # overview
    assert set(d["ingest_rate"]) >= {"logs", "trace", "metrics"}
    assert "flush_rate" in d and "records_per_flush" in d
    # origin — observed row counts drawn beside the declared topology
    assert d["lineage"] and "service" in d["lineage"][0]
    # split per destination table — every service reaches all four, so the SPLIT is the
    # only per-service information there is downstream
    assert set(d["lineage"][0]) >= {"logs", "traces", "gauge", "sum"}
    # the metric mix is what makes one service's split differ from another's
    assert d["metrics_by_service"]["pubsub-ingestion-topic"]["gauge"]
    # collector / health — the three outcomes
    assert "persist_rate" in d and "drop_rate" in d and "reject_rate" in d
    # …and which signal type each rejection was, which is what colours the falling dot.
    # Losing this field would silently repaint every rejection as one arbitrary type.
    assert d["reject_matrix"]["contract"]["logs"] == 0.4
    # contract board — who violated, which the collector's counters cannot say (no service
    # label). `violating` is rows, not the sum of per-key counts, so it can be a share.
    v = d["contract_violations"][0]
    assert v["service"] == "third-party-agent" and v["violating"] <= v["rows"]
    assert "sentinel.run_id" in v["missing"]
    # health — batches lost, which is a different granularity from signals dropped
    assert "export_errors" in d
    assert "persisted" in d["totals"]


def test_bronze_growth_is_reported_per_table(monkeypatch):
    """Deltas of count(), not a time-window query — bronze stores event time and the
    backfill writes history, so 'rows that arrived' cannot come from a WHERE on Timestamp."""
    monkeypatch.setattr(main.poller, "latest", _snapshot())
    d = client.get("/api/snapshot").json()
    assert set(d["bronze"]) == {
        "otel_logs", "otel_traces", "otel_metrics_gauge", "otel_metrics_sum"}
