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


def _band(**kw):
    base = {"service": "s", "median": 100.0, "mad": 0.0, "sd": 0.0,
            "seen": 30, "estate": 30, "latest": 100, "latest_t": 0, "series": []}
    return {**base, **kw}


def test_the_band_returned_is_the_band_that_decided():
    """Metaplane shipped a version where the drawn area and the alerting rule were computed
    separately, then called reconciling them a simplification. One function returns both."""
    from flow_ui.pipeline import MAD_TO_SIGMA, Z_WARN, volume_state

    v = volume_state(_band(mad=10.0, latest=100))
    scale = 10.0 * MAD_TO_SIGMA
    assert v["lo"] == round(100 - Z_WARN * scale, 1)
    assert v["hi"] == round(100 + Z_WARN * scale, 1)
    # a value placed just outside the drawn band must be the one that alerts
    assert volume_state(_band(mad=10.0, latest=int(v["hi"]) + 2))["state"] != "passing"
    assert volume_state(_band(mad=10.0, latest=int(v["hi"]) - 2))["state"] == "passing"


def test_a_perfectly_regular_producer_is_unmonitored_not_healthy():
    """The degenerate case that makes robust statistics bite: MAD = 0 gives a zero-width
    band in which every value is infinitely anomalous. Falls back to stddev; if that is flat
    too the series is declared unmodellable. Grey means *not observed*, never *fine*."""
    from flow_ui.pipeline import volume_state

    flat = volume_state(_band(mad=0.0, sd=0.0, latest=1_000_000))
    assert flat["state"] == "unmonitored" and flat["estimator"] == "none"
    assert flat["why"] == "no dispersion to model"

    fallback = volume_state(_band(mad=0.0, sd=20.0, latest=100))
    assert fallback["estimator"] == "stddev" and fallback["state"] == "passing"

    assert volume_state(_band(mad=5.0, sd=99.0))["estimator"] == "mad"


def test_too_short_a_window_is_unmonitored_rather_than_a_band_drawn_from_three_points():
    from flow_ui.pipeline import MIN_BUCKETS, volume_state

    v = volume_state(_band(mad=10.0, seen=3, estate=3, latest=99999))
    assert v["state"] == "unmonitored" and str(MIN_BUCKETS) not in v["service"]
    assert "buckets in the window" in v["why"]


def test_absence_is_its_own_axis_not_a_band_violation():
    """A producer silent while the estate kept receiving is the write that never happened —
    a signal a tool reading tables at rest cannot produce. It must not be folded into the
    band verdict, or a silent producer sitting at its median would read as passing."""
    from flow_ui.pipeline import volume_state

    v = volume_state(_band(mad=10.0, seen=18, estate=30, latest=100))
    assert v["state"] == "passing"      # the buckets it DID write were normal
    assert v["absent"] == 12            # and it missed twelve the estate received


def test_the_estimator_is_chosen_by_whether_its_band_fits_not_by_mad_being_nonzero():
    """The regression: `mad * 1.4826 or sd` was a cliff, not a fallback. On a series that
    alternates full minutes with partial ones the median sits on the dominant mode, MAD
    measures that mode's spread against itself (50 against a true 699), and the instant MAD
    crossed zero σ moved 74 → 699 between two ticks — flipping every producer from passing
    to alerting on one new bucket. Observed live, not hypothesised."""
    from flow_ui.pipeline import volume_state

    # 20 full minutes at 2850, 11 partial ones: bimodal, exactly the measured shape
    series = [[i, 2850] for i in range(20)] + [[20 + i, v] for i, v in
              enumerate([600, 750, 1000, 1250, 1300, 1600, 1900, 2000, 2200, 2400, 2600])]
    row = _band(median=2800.0, mad=50.0, sd=699.0, seen=31, estate=31,
                latest=1600, series=series)
    v = volume_state(row)
    # the MAD band would reject nearly half its own window, so it is not the one used
    assert v["estimator"] == "stddev"
    assert v["oob"] <= 0.15
    assert v["state"] == "passing"


def test_a_series_no_band_fits_is_unmonitored_rather_than_eight_alerts():
    """When both estimators produce a band that rejects its own training window, the series
    is multi-modal and no single band describes it. Grey, with the reason."""
    from flow_ui.pipeline import volume_state

    # two tight modes far apart: every band either misses one mode or spans nothing
    series = [[i, 100] for i in range(15)] + [[15 + i, 10_000] for i in range(15)]
    v = volume_state(_band(median=100.0, mad=0.5, sd=1.0, seen=30, estate=30,
                           latest=10_000, series=series))
    assert v["state"] == "unmonitored"
    assert "not single-mode" in v["why"]
