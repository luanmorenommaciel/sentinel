"""Prometheus text-exposition parsing, and rates derived from it.

**The whole reason this module is careful: a metric family that has never been touched is
absent from `/metrics` entirely, not present with a zero.** The collector's five labelled
counters (`signals_ingested_total`, `signals_accepted_total`, `signals_rejected_total`,
`storage_signals_total`, `batch_flush_total`) are `IntCounterVec`s, and a `*Vec` exposes
nothing until some code path instantiates a label combination. Measured on a freshly
started collector: `/metrics` served only `batch_flush_size`, `export_errors_total` and
`export_latency_seconds` — the other five appeared only once traffic arrived.

So every read here goes through :func:`Sample.value`, which returns ``0.0`` for a family
that is not there. An absent family is a normal state, not an error.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: `name{label="v",other="w"} 12.5` or `name 12.5`. The value may be an integer, a float,
#: `+Inf`/`-Inf`/`NaN` (histogram buckets use `+Inf`).
_LINE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?"
    r"\s+(?P<value>[^\s]+)"
)
_LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def _to_float(raw: str) -> float | None:
    """Prometheus spells infinity and NaN in words; Python's float() agrees on all three."""
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class Sample:
    """One scrape, flattened to ``{name: {labelkey: value}}``."""

    #: `{"sentinel_batch_flush_total": {'signal="all",status="success"': 92.0}}`
    series: dict[str, dict[str, float]] = field(default_factory=dict)

    def value(self, name: str, **labels: str) -> float:
        """The value of one series, or ``0.0`` if the family or the label set is absent.

        Absent is the normal cold-start state — see the module docstring.
        """
        family = self.series.get(name)
        if not family:
            return 0.0
        if not labels:
            # No labels asked for: sum the family. For an unlabelled metric this is the
            # single value; for a labelled one it is the family total, which is what a
            # caller that did not name a label wants.
            return sum(family.values())
        key = _label_key(labels)
        return family.get(key, 0.0)

    def sum_over(self, name: str, label: str) -> dict[str, float]:
        """Every value of `name`, keyed by one label's value (e.g. by ``signal``)."""
        out: dict[str, float] = {}
        for key, val in self.series.get(name, {}).items():
            parsed = dict(_LABEL.findall(key))
            if label in parsed:
                out[parsed[label]] = out.get(parsed[label], 0.0) + val
        return out

    def sum_over_pair(self, name: str, first: str, second: str) -> dict[str, dict[str, float]]:
        """Every value of `name`, keyed by TWO labels — ``{first: {second: value}}``.

        :meth:`sum_over` collapses one label at a time, and reading the same family twice
        (once by `signal`, once by `reason`) cannot recover the cross-product: it says
        *three metrics were rejected* and *four rejections were contract failures*, never
        which of the two. `sentinel_signals_rejected_total` carries both labels at the
        increment site (`collector-rust/src/grpc.rs`), so the cross-product is real data,
        not an inference — this reads it.
        """
        out: dict[str, dict[str, float]] = {}
        for key, val in self.series.get(name, {}).items():
            parsed = dict(_LABEL.findall(key))
            if first in parsed and second in parsed:
                bucket = out.setdefault(parsed[first], {})
                bucket[parsed[second]] = bucket.get(parsed[second], 0.0) + val
        return out

    def has(self, name: str) -> bool:
        """Whether the family was present in the scrape at all."""
        return name in self.series


def _label_key(labels: dict[str, str]) -> str:
    """Canonical label key: sorted by name, so lookups do not depend on scrape order."""
    return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))


def parse(text: str) -> Sample:
    """Parse the Prometheus text exposition format into a :class:`Sample`."""
    series: dict[str, dict[str, float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        value = _to_float(m.group("value"))
        if value is None:
            continue
        raw_labels = m.group("labels") or ""
        key = _label_key(dict(_LABEL.findall(raw_labels))) if raw_labels else ""
        series.setdefault(m.group("name"), {})[key] = value
    return Sample(series=series)


def quantile(sample: "Sample", name: str, q: float) -> float:
    """Approximate a quantile from a Prometheus histogram's cumulative buckets.

    The collector already publishes `export_latency_seconds` as a histogram, and reducing
    it to `sum/count` throws away the only thing that matters for health: a mean of 16 ms
    reads identically whether every flush took 16 ms or nine took 4 ms and one took 130.

    Buckets are cumulative and `le` is an upper bound, so the true value sits somewhere
    inside the bucket that first crosses the target rank. We interpolate linearly across
    that bucket, which is what Prometheus' own `histogram_quantile` does — and inherits the
    same caveat: the answer can only be as precise as the bucket edges, and a value in the
    `+Inf` bucket can only be reported as "at least the last finite edge".
    """
    family = sample.series.get(f"{name}_bucket")
    if not family:
        return 0.0
    buckets: list[tuple[float, float]] = []
    for key, count in family.items():
        parsed = dict(_LABEL.findall(key))
        le = _to_float(parsed.get("le", ""))
        if le is not None:
            buckets.append((le, count))
    if not buckets:
        return 0.0
    buckets.sort(key=lambda b: b[0])
    total = buckets[-1][1]
    if total <= 0:
        return 0.0
    target = q * total
    prev_le, prev_count = 0.0, 0.0
    for le, count in buckets:
        if count >= target:
            if le == float("inf"):
                return prev_le
            span = count - prev_count
            if span <= 0:
                return le
            return prev_le + (le - prev_le) * ((target - prev_count) / span)
        prev_le, prev_count = le, count
    return buckets[-1][0]


def rate(current: float, previous: float, dt: float) -> float:
    """Per-second rate between two counter reads.

    A counter that went *backwards* means the collector restarted and its registry is
    fresh — the process builds an independent `Registry` per run, so there is no
    continuity across restarts. Treat the current value as the delta rather than
    reporting a large negative rate.
    """
    if dt <= 0:
        return 0.0
    delta = current - previous
    if delta < 0:
        delta = current
    return delta / dt
