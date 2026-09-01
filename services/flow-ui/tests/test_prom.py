"""The parser's contract — above all, that an absent metric family is a normal state."""
from __future__ import annotations

from flow_ui import prom

# A freshly started collector serves exactly this: the three unlabelled/histogram families.
# The five `IntCounterVec` families are absent because no label combination exists yet.
COLD = """\
# HELP sentinel_batch_flush_size Number of records per batch flush.
# TYPE sentinel_batch_flush_size histogram
sentinel_batch_flush_size_bucket{le="1"} 0
sentinel_batch_flush_size_bucket{le="+Inf"} 0
sentinel_batch_flush_size_sum 0
sentinel_batch_flush_size_count 0
# HELP sentinel_export_errors_total Total ClickHouse insert errors after all retry attempts.
# TYPE sentinel_export_errors_total counter
sentinel_export_errors_total 0
"""

WARM = """\
sentinel_signals_ingested_total{signal="logs"} 40200
sentinel_signals_ingested_total{signal="metrics"} 152700
sentinel_signals_ingested_total{signal="trace"} 40200
sentinel_batch_flush_total{signal="all",status="success"} 92
sentinel_batch_flush_size_count 92
sentinel_batch_flush_size_sum 233100
sentinel_storage_signals_total{outcome="persisted",signal="all"} 233100
sentinel_signals_rejected_total{reason="contract",signal="metrics"} 900
sentinel_signals_rejected_total{reason="contract",signal="logs"} 40
sentinel_signals_rejected_total{reason="backpressure",signal="trace"} 12
sentinel_export_errors_total 0
"""


def test_absent_family_reads_as_zero_not_an_error():
    """The cold-start case that would otherwise take the whole page down."""
    s = prom.parse(COLD)
    assert s.value("sentinel_signals_ingested_total", signal="logs") == 0.0
    assert s.sum_over("sentinel_signals_ingested_total", "signal") == {}
    assert not s.has("sentinel_signals_ingested_total")
    assert s.has("sentinel_export_errors_total")


def test_labelled_series_are_addressable_and_label_order_does_not_matter():
    s = prom.parse(WARM)
    assert s.value("sentinel_batch_flush_total", signal="all", status="success") == 92
    # The scrape writes signal first; asking status first must find the same series.
    assert s.value("sentinel_batch_flush_total", status="success", signal="all") == 92


def test_sum_over_groups_by_one_label():
    s = prom.parse(WARM)
    assert s.sum_over("sentinel_signals_ingested_total", "signal") == {
        "logs": 40200.0, "metrics": 152700.0, "trace": 40200.0,
    }
    assert s.sum_over("sentinel_storage_signals_total", "outcome") == {"persisted": 233100.0}


def test_sum_over_pair_recovers_the_cross_product_one_label_at_a_time_destroys():
    """The reason this method exists. Grouping by `signal` says 900 metrics were rejected;
    grouping by `reason` says 940 rejections were contract failures. Neither answers "which
    type failed the contract" — and the page paints the falling dot from that answer."""
    s = prom.parse(WARM)
    assert s.sum_over_pair("sentinel_signals_rejected_total", "reason", "signal") == {
        "contract": {"metrics": 900.0, "logs": 40.0},
        "backpressure": {"trace": 12.0},
    }
    # Both single-label views remain correct — and both remain insufficient on their own.
    assert s.sum_over("sentinel_signals_rejected_total", "reason") == {
        "contract": 940.0, "backpressure": 12.0,
    }


def test_sum_over_pair_on_an_absent_or_half_labelled_family_is_empty():
    """Cold start, and the buffer-side families that only carry one of the two labels."""
    assert prom.parse(COLD).sum_over_pair(
        "sentinel_signals_rejected_total", "reason", "signal") == {}
    # `export_errors_total` has no labels at all; asking for two of them yields nothing
    # rather than inventing a bucket.
    assert prom.parse(WARM).sum_over_pair(
        "sentinel_export_errors_total", "reason", "signal") == {}


def test_value_without_labels_sums_the_family():
    s = prom.parse(WARM)
    assert s.value("sentinel_signals_ingested_total") == 233100.0


def test_histogram_buckets_with_inf_do_not_break_parsing():
    s = prom.parse(COLD)
    assert s.value("sentinel_batch_flush_size_bucket", le="+Inf") == 0.0


def test_comments_and_blank_lines_are_ignored():
    assert prom.parse("# HELP x y\n\n# TYPE x counter\n").series == {}


def test_rate_is_per_second():
    assert prom.rate(100.0, 40.0, 2.0) == 30.0


def test_counter_reset_reports_the_new_value_not_a_negative_rate():
    """The collector builds a fresh Registry per process, so a restart resets every
    counter to zero. A naive delta would report a large negative rate."""
    assert prom.rate(5.0, 233100.0, 1.0) == 5.0


def test_zero_elapsed_time_does_not_divide_by_zero():
    assert prom.rate(10.0, 0.0, 0.0) == 0.0


HIST = """\
sentinel_export_latency_seconds_bucket{le="0.005"} 0
sentinel_export_latency_seconds_bucket{le="0.01"} 10
sentinel_export_latency_seconds_bucket{le="0.02"} 50
sentinel_export_latency_seconds_bucket{le="0.04"} 80
sentinel_export_latency_seconds_bucket{le="0.08"} 99
sentinel_export_latency_seconds_bucket{le="+Inf"} 100
sentinel_export_latency_seconds_sum 2.45
sentinel_export_latency_seconds_count 100
"""


def test_quantiles_recover_the_tail_the_mean_hides():
    """The reason this exists: on the live pipeline the mean was 24.5 ms and the p99 was
    79 ms. One number cannot say whether export is healthy."""
    s = prom.parse(HIST)
    p50 = prom.quantile(s, "sentinel_export_latency_seconds", 0.5)
    p99 = prom.quantile(s, "sentinel_export_latency_seconds", 0.99)
    assert 0.01 < p50 <= 0.02      # the 50th observation sits on the bucket edge
    assert p99 > p50 * 2


def test_a_quantile_over_an_absent_histogram_is_zero_not_a_crash():
    assert prom.quantile(prom.parse(""), "sentinel_export_latency_seconds", 0.99) == 0.0


def test_a_value_in_the_inf_bucket_reports_the_last_finite_edge():
    """`+Inf` has no upper bound to interpolate toward, so the honest answer is the last
    edge we can actually name."""
    s = prom.parse("""\
sentinel_x_bucket{le="0.01"} 1
sentinel_x_bucket{le="+Inf"} 100
sentinel_x_count 100
""")
    assert prom.quantile(s, "sentinel_x", 0.99) == 0.01
