from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LogSignal:
    time_unix_nano: int
    severity_text: str
    severity_number: int
    service_name: str
    body: str
    trace_id: str | None
    span_id: str | None
    attributes: dict[str, str]
    resource_attributes: dict[str, str]


@dataclass(frozen=True)
class MetricSignal:
    time_unix_nano: int
    name: str
    type: str  # "gauge" | "sum" | "histogram"
    value: float
    service_name: str
    attributes: dict[str, str]
    resource_attributes: dict[str, str]


@dataclass(frozen=True)
class SpanSignal:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    service_name: str
    start_unix_nano: int
    end_unix_nano: int
    status_code: str  # "OK" | "ERROR"
    attributes: dict[str, str]
    resource_attributes: dict[str, str]


Signal = LogSignal | MetricSignal | SpanSignal
