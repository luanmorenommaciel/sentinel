"""The producer's declared topology, and what each bronze table holds.

Two static sources feed the detail levels of the graph. Neither is invented here.

**The service graph** is Pod 1's own `config/topology/default.yaml` — the seven synthetic
services and the `depends_on` edges between them. Reading the producer's config rather than
redrawing it means the picture cannot drift from what actually emits the telemetry.

*A note on where this goes next:* this is the **declared** topology. The **observed** one is
recoverable from `bronze.otel_traces` by following `ParentSpanId` across services, and the
two disagreeing would itself be a finding worth surfacing. That comparison is out of scope
for v1 but is the reason this module keeps the two ideas namable.

**The table documentation** is the Pod 2 → Pod 3 read contract v1.0.0.1, transcribed. It is
the semantic layer the DDL cannot express: which columns Pod 2 populates, what it guarantees,
and which tables stay empty by design.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

log = logging.getLogger("flow_ui.topology")

#: Mounted read-only by compose; falls back to the source checkout for local runs.
_CANDIDATES = (
    Path(os.getenv("GENERATOR_CONFIG_DIR", "/app/generator-config")),
    Path(__file__).resolve().parents[3] / "generator-python" / "config",
)


def _config_dir() -> Path | None:
    for p in _CANDIDATES:
        if (p / "topology" / "default.yaml").is_file():
            return p
    return None


def service_graph() -> dict:
    """The declared service topology as `{nodes, edges, source}`.

    Edges point the way data *flows*: `depends_on: [a]` on component `b` means a produces
    what b consumes, so the edge is `a → b`. Reading it the other way would draw every
    arrow backwards, which is the kind of mistake a diagram never announces.
    """
    cfg = _config_dir()
    if cfg is None:
        log.warning("generator topology not found; detail level will be empty")
        return {"nodes": [], "edges": [], "source": None}

    path = cfg / "topology" / "default.yaml"
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        log.warning("topology unreadable (%s): %s", path, exc)
        return {"nodes": [], "edges": [], "source": None}

    by_component = {c["name"]: c for c in raw.get("components", [])}
    nodes, edges = [], []
    for comp in raw.get("components", []):
        nodes.append({
            "id": comp["name"],
            "service": comp["service_name"],
            "kind": comp.get("type", "unknown"),
            "rate": comp.get("base_rate"),
            "latency_ms": comp.get("base_latency_ms"),
            "error_ratio": comp.get("error_ratio"),
            "roots": not comp.get("depends_on"),
        })
        for upstream in comp.get("depends_on") or []:
            if upstream in by_component:
                edges.append({"from": upstream, "to": comp["name"]})
    return {
        "nodes": nodes,
        "edges": edges,
        "source": str(path),
        "version": raw.get("version"),
    }


#: Per-table semantics from the read contract. `columns` lists only what Pod 2 actually
#: writes — every other bronze column sits at its ClickHouse default by design (§2), which
#: is why showing the full DDL here would misrepresent what a consumer can rely on.
TABLE_DOCS: dict[str, dict] = {
    "otel_logs": {
        "section": "§2.1",
        "summary": "OTLP log records. The six sentinel.* keys travel inside "
                   "ResourceAttributes, not as columns.",
        "order_by": "(ServiceName, TimestampDate, TimestampTime)",
        "partition": "toYYYYMM(TimestampDate)",
        "ttl": "30d",
        "columns": [
            ("Timestamp", "DateTime64(9)", "event time, UTC, ns"),
            ("ServiceName", "LowCardinality(String)", "always present · indexed"),
            ("SeverityText", "LowCardinality(String)", "INFO, ERROR, …"),
            ("SeverityNumber", "UInt8", "0–24"),
            ("Body", "String", "log message"),
            ("TraceId", "String", "'' when absent, never NULL"),
            ("SpanId", "String", "'' when absent, never NULL"),
            ("LogAttributes", "Map", "record-level attributes"),
            ("ResourceAttributes", "Map", "includes the sentinel.* keys"),
        ],
    },
    "otel_traces": {
        "section": "§2.2",
        "summary": "Spans. Duration is nanoseconds, precomputed; end time is not a column "
                   "— it is Timestamp + Duration.",
        "order_by": "(ServiceName, SpanName, toUnixTimestamp(Timestamp), TraceId)",
        "partition": "toDate(Timestamp)",
        "ttl": "30d",
        "columns": [
            ("Timestamp", "DateTime64(9)", "span start"),
            ("TraceId", "String", "32 hex, always present"),
            ("SpanId", "String", "16 hex, always present"),
            ("ParentSpanId", "String", "'' for root spans"),
            ("SpanName", "LowCardinality(String)", "span name"),
            ("ServiceName", "LowCardinality(String)", "always present · indexed"),
            ("Duration", "Int64", "nanoseconds"),
            ("StatusCode", "LowCardinality(String)", "Ok or Error"),
            ("SpanAttributes", "Map", "span-level attributes"),
            ("ResourceAttributes", "Map", "includes the sentinel.* keys"),
        ],
    },
    "otel_metrics_gauge": {
        "section": "§2.3",
        "summary": "Gauge data points. The data-point type selects the table — there is no "
                   "MetricType column.",
        "order_by": "(ServiceName, MetricName, Attributes, toUnixTimestamp64Nano(TimeUnix))",
        "partition": "toDate(TimeUnix)",
        "ttl": "30d",
        "columns": [
            ("ServiceName", "LowCardinality(String)", "always present · indexed"),
            ("MetricName", "LowCardinality(String)", "metric name"),
            ("TimeUnix", "DateTime64(9)", "event time"),
            ("Value", "Float64", "sample value"),
            ("Attributes", "Map", "data-point attributes"),
            ("ResourceAttributes", "Map", "includes the sentinel.* keys"),
        ],
    },
    "otel_metrics_sum": {
        "section": "§2.3",
        "summary": "Sum data points. Same shape as gauge; AggregationTemporality and "
                   "IsMonotonic are left at their defaults.",
        "order_by": "(ServiceName, MetricName, Attributes, toUnixTimestamp64Nano(TimeUnix))",
        "partition": "toDate(TimeUnix)",
        "ttl": "30d",
        "columns": [
            ("ServiceName", "LowCardinality(String)", "always present · indexed"),
            ("MetricName", "LowCardinality(String)", "metric name"),
            ("TimeUnix", "DateTime64(9)", "event time"),
            ("Value", "Float64", "sample value"),
            ("Attributes", "Map", "data-point attributes"),
            ("ResourceAttributes", "Map", "includes the sentinel.* keys"),
        ],
    },
}

#: Present in the DDL, empty in this contract version — Pod 1 v1.0.0 emits gauge and sum
#: only (§2.3, §5.5). Named on screen so three permanently-zero tables read as a decision
#: rather than as a failure.
EMPTY_BY_CONTRACT = {
    "otel_metrics_histogram": "no histogram data points in contract v1.0.0",
    "otel_metrics_exponential_histogram": "no exponential histogram data points in v1.0.0",
    "otel_metrics_summary": "no summary data points in v1.0.0",
}

#: Bronze also carries the contrib trace-id index and the view that fills it. It is not a
#: table Pod 2 writes — the MV does — so it is listed apart from both groups above.
DERIVED = {
    "otel_traces_trace_id_ts": "trace-id index, filled by otel_traces_trace_id_ts_mv",
}

CONTRACT = {
    "producer": "generator/v1",
    "producer_version": "1.0.0",
    "consumer": "collector/v1",
    "consumer_version": "1.0.0.1",
    "validation": "grpc_validation",
}
