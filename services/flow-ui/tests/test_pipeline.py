"""Mode detection — the inference the whole animation hangs off.

The thresholds come from measuring this pipeline, not from taste:

    --mode stream    1.03 flushes/s, 500–1000 records per flush
    --mode backfill  6.6  flushes/s (min 4, max 8), ~2534 records per flush

so the two distributions do not overlap on either axis.
"""
from __future__ import annotations

from flow_ui.config import Settings
from flow_ui.pipeline import MODE_BATCH, MODE_IDLE, MODE_STREAM, Poller, Snapshot, Broadcaster


def poller() -> Poller:
    return Poller(Settings())


def test_stream_cadence_is_read_as_stream():
    p = poller()
    for _ in range(3):
        p._flush_rates.append(1.0)
    assert p._detect_mode(0.99, 1000.0, 988.0) == MODE_STREAM


def test_backfill_cadence_is_read_as_batch():
    p = poller()
    for r in (5.9, 5.9, 6.6):
        p._flush_rates.append(r)
    assert p._detect_mode(5.9, 2500.0, 16297.0) == MODE_BATCH


def test_a_fat_batch_is_batch_even_if_the_flush_rate_sample_dips():
    """A poll can land between bursts and see a low rate; batch size is the second tell."""
    p = poller()
    p._flush_rates.append(1.0)
    assert p._detect_mode(1.0, 2500.0, 16000.0) == MODE_BATCH


def test_no_traffic_is_idle():
    assert poller()._detect_mode(0.0, 0.0, 0.0) == MODE_IDLE


def test_stream_is_not_promoted_to_batch_by_its_own_1000_record_flush():
    """Stream's largest observed flush (1000) must stay below the batch threshold."""
    p = poller()
    p._flush_rates.append(0.99)
    assert p._detect_mode(0.99, 1000.0, 988.0) == MODE_STREAM


def test_snapshot_serializes_to_json_safe_primitives():
    import json
    json.dumps(Snapshot().as_dict())


def test_snapshot_names_the_tables_that_are_empty_by_contract():
    """Contract §2.3/§5: histogram, exponential-histogram and summary stay empty in
    v1.0.0. The page says so rather than drawing three dead tables unexplained."""
    assert "otel_metrics_histogram" in Snapshot().bronze_empty
    assert "otel_metrics_summary" in Snapshot().bronze_empty


def test_a_full_subscriber_queue_drops_its_own_frames_not_the_publisher():
    b = Broadcaster()
    q = b.subscribe()
    for _ in range(6):
        b.publish(Snapshot())        # must never raise, whatever the queue depth
    assert q.qsize() <= 2
    b.unsubscribe(q)
    assert b.subscribers == 0


def test_the_verdict_names_a_state_and_the_reason_for_it():
    """Colour is never the only carrier: every state ships the sentence a reader acts on."""
    p = poller()
    healthy = Snapshot(collector_up=True, clickhouse_up=True,
                       ingest_rate={"logs": 500.0}, export_latency_p99=30.0)
    assert p._verdict(healthy) == ("ok", "flowing, nothing rejected or lost")


def test_an_unreachable_source_outranks_everything_else():
    p = poller()
    assert p._verdict(Snapshot(collector_up=False, clickhouse_up=True))[0] == "fail"
    assert p._verdict(Snapshot(collector_up=True, clickhouse_up=False))[0] == "fail"


def test_loss_is_a_failure_and_rejection_is_a_warning():
    """A contract violation under the `warn` policy is recorded and let through — the data
    still arrives. A dropped batch is data that no longer exists anywhere."""
    p = poller()
    assert p._verdict(Snapshot(collector_up=True, clickhouse_up=True,
                               ingest_rate={"logs": 1.0}, drop_rate=0.5))[0] == "fail"
    p2 = poller()
    assert p2._verdict(Snapshot(collector_up=True, clickhouse_up=True,
                                ingest_rate={"logs": 1.0},
                                reject_by_reason={"contract": 0.2}))[0] == "warn"


def test_a_tail_over_the_measured_ceiling_warns_even_when_nothing_is_lost():
    p = poller()
    state, note = p._verdict(Snapshot(collector_up=True, clickhouse_up=True,
                                      ingest_rate={"logs": 900.0}, export_latency_p99=120.0))
    assert state == "warn" and "p99" in note


def test_no_traffic_is_idle_not_a_failure():
    p = poller()
    assert p._verdict(Snapshot(collector_up=True, clickhouse_up=True))[0] == "idle"


def test_the_two_rejection_reasons_are_not_the_same_problem():
    """`contract` is a bad payload — under the `warn` policy it is counted and exported
    anyway, so the data still lands. `backpressure` is the collector refusing a batch it
    has no room for, which the producer is told about and can retry. Reporting them as one
    number hides which of the two is happening."""
    p = poller()
    _, contract = p._verdict(Snapshot(collector_up=True, clickhouse_up=True,
                                      ingest_rate={"logs": 1.0},
                                      reject_by_reason={"contract": 3.0}))
    p2 = poller()
    _, back = p2._verdict(Snapshot(collector_up=True, clickhouse_up=True,
                                   ingest_rate={"logs": 1.0},
                                   reject_by_reason={"backpressure": 3.0}))
    assert "contract" in contract and "exported anyway" in contract
    assert "saturated" in back and "retry" in back
    assert contract != back


def test_saturation_outranks_a_bad_payload():
    """If both are happening, the one that means the collector cannot keep up is the one
    worth naming first."""
    p = poller()
    _, note = p._verdict(Snapshot(collector_up=True, clickhouse_up=True,
                                  ingest_rate={"logs": 1.0},
                                  reject_by_reason={"contract": 9.0, "backpressure": 1.0}))
    assert "saturated" in note
