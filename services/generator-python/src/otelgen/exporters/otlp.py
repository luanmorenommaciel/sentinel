from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from otelgen.exporters.base import Exporter
from otelgen.model import LogSignal, MetricSignal, Signal, SpanSignal

if TYPE_CHECKING:
    pass


class OTLPExporter(Exporter):
    """Export canonical signals over OTLP using SDK data-model objects with explicit timestamps.

    Uses:
        - opentelemetry-sdk 1.x (ReadableSpan, LogRecord, MetricsData)
        - opentelemetry-exporter-otlp-proto-http or -grpc depending on protocol
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:4317",
        protocol: str = "grpc",
        headers: dict[str, str] | None = None,
        insecure: bool | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._protocol = protocol
        # Headers (e.g. {"authorization": "<ingestion-key>"}) sent with every OTLP
        # request. None when empty so the SDK falls back to its own env defaults.
        self._headers = dict(headers) if headers else None
        # insecure=None → auto: plaintext for http:// (and scheme-less) endpoints,
        # TLS for https://. gRPC-only; the HTTP exporter derives TLS from the URL.
        self._insecure = insecure

        # Build per-type exporters lazily grouped by resource
        self._span_exporter = self._make_span_exporter()
        self._log_exporter = self._make_log_exporter()
        self._metric_exporter = self._make_metric_exporter()

    def _resolve_insecure(self) -> bool:
        if self._insecure is not None:
            return self._insecure
        return not self._endpoint.startswith("https://")

    # ------------------------------------------------------------------
    # Exporter factories
    # ------------------------------------------------------------------

    def _make_span_exporter(self):
        if self._protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            return OTLPSpanExporter(
                endpoint=self._endpoint, headers=self._headers, insecure=self._resolve_insecure()
            )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        return OTLPSpanExporter(endpoint=f"{self._endpoint}/v1/traces", headers=self._headers)

    def _make_log_exporter(self):
        if self._protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
                OTLPLogExporter,
            )
            return OTLPLogExporter(
                endpoint=self._endpoint, headers=self._headers, insecure=self._resolve_insecure()
            )
        from opentelemetry.exporter.otlp.proto.http._log_exporter import (
            OTLPLogExporter,
        )
        return OTLPLogExporter(endpoint=f"{self._endpoint}/v1/logs", headers=self._headers)

    def _make_metric_exporter(self):
        if self._protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            return OTLPMetricExporter(
                endpoint=self._endpoint, headers=self._headers, insecure=self._resolve_insecure()
            )
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        return OTLPMetricExporter(endpoint=f"{self._endpoint}/v1/metrics", headers=self._headers)

    # ------------------------------------------------------------------
    # SDK object construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_resource(resource_attrs: dict[str, str]):
        from opentelemetry.sdk.resources import Resource
        return Resource(attributes=resource_attrs)

    def _build_readable_span(self, signal: SpanSignal):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import ReadableSpan
        from opentelemetry.sdk.util.instrumentation import InstrumentationScope
        from opentelemetry.trace import SpanKind, TraceFlags
        from opentelemetry.trace.span import SpanContext
        from opentelemetry.trace.status import Status, StatusCode

        trace_id_int = int(signal.trace_id, 16)
        span_id_int = int(signal.span_id, 16)

        ctx = SpanContext(
            trace_id=trace_id_int,
            span_id=span_id_int,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )

        # The parent link. `ScenarioEngine` already assembles correlated traces by walking
        # `depends_on`, and every other path carries the result: the model has the field, the
        # ClickHouse exporter writes it, `otlp_output.schema.json` declares it as 16 hex
        # characters, and the Pod 2 -> Pod 3 read contract documents `ParentSpanId` as `''`
        # *for root spans* — which only means anything if non-root spans have one.
        #
        # This path dropped it. `ReadableSpan` was built with a context and no `parent`, so
        # `trace_id` survived onto the wire and the parent did not: measured over a live run,
        # traces were correlated (8.5 spans each, 30k of them spanning more than one service)
        # while 1,491,881 of 1,491,881 spans arrived in bronze as roots. A call graph that
        # exists in the generator and nowhere downstream.
        parent_ctx = None
        if signal.parent_span_id:
            parent_ctx = SpanContext(
                trace_id=trace_id_int,
                span_id=int(signal.parent_span_id, 16),
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )

        status = Status(
            StatusCode.ERROR if signal.status_code == "ERROR" else StatusCode.OK
        )

        resource = Resource(attributes=signal.resource_attributes)
        scope = InstrumentationScope(name="otelgen", version="0.1.0")

        return ReadableSpan(
            name=signal.name,
            context=ctx,
            parent=parent_ctx,
            resource=resource,
            instrumentation_scope=scope,
            attributes=signal.attributes,
            start_time=signal.start_unix_nano,
            end_time=signal.end_unix_nano,
            status=status,
            kind=SpanKind.INTERNAL,
        )

    def _build_readable_log(self, signal: LogSignal):
        from opentelemetry._logs.severity import SeverityNumber
        from opentelemetry.sdk._logs._internal import LogRecord, ReadableLogRecord
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.util.instrumentation import InstrumentationScope
        from opentelemetry.trace import TraceFlags

        resource = Resource(attributes=signal.resource_attributes)
        scope = InstrumentationScope(name="otelgen", version="0.1.0")

        trace_id_int = int(signal.trace_id, 16) if signal.trace_id else None
        span_id_int = int(signal.span_id, 16) if signal.span_id else None

        log_record = LogRecord(
            timestamp=signal.time_unix_nano,
            observed_timestamp=signal.time_unix_nano,
            trace_id=trace_id_int,
            span_id=span_id_int,
            trace_flags=TraceFlags(TraceFlags.SAMPLED) if trace_id_int else None,
            severity_text=signal.severity_text,
            severity_number=SeverityNumber(signal.severity_number),
            body=signal.body,
            attributes=dict(signal.attributes),
        )

        return ReadableLogRecord(
            log_record=log_record,
            resource=resource,
            instrumentation_scope=scope,
        )

    def _build_metrics_data(self, signals: list[MetricSignal]):
        from opentelemetry.sdk.metrics._internal.point import (
            Gauge,
            Metric,
            NumberDataPoint,
            ResourceMetrics,
            ScopeMetrics,
            Sum,
        )
        from opentelemetry.sdk.metrics.export import AggregationTemporality, MetricsData
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.util.instrumentation import InstrumentationScope

        # Group by resource_attributes
        by_resource: dict[str, tuple[dict[str, str], list[MetricSignal]]] = {}
        for sig in signals:
            key = str(sorted(sig.resource_attributes.items()))
            if key not in by_resource:
                by_resource[key] = (sig.resource_attributes, [])
            by_resource[key][1].append(sig)

        resource_metrics_list = []
        scope = InstrumentationScope(name="otelgen", version="0.1.0")

        for _key, (res_attrs, sigs) in by_resource.items():
            resource = Resource(attributes=res_attrs)
            metric_objs = []
            for sig in sigs:
                dp = NumberDataPoint(
                    attributes=sig.attributes,
                    start_time_unix_nano=sig.time_unix_nano,
                    time_unix_nano=sig.time_unix_nano,
                    value=sig.value,
                )
                data: Sum | Gauge
                if sig.type == "sum":
                    data = Sum(
                        data_points=[dp],
                        aggregation_temporality=AggregationTemporality.CUMULATIVE,
                        is_monotonic=True,
                    )
                elif sig.type == "gauge":
                    data = Gauge(data_points=[dp])
                else:
                    raise ValueError(
                        f"Unsupported MetricSignal type {sig.type!r}; expected 'gauge' or 'sum'."
                    )

                metric_objs.append(
                    Metric(
                        name=sig.name,
                        description="",
                        unit="",
                        data=data,
                    )
                )

            scope_metrics = ScopeMetrics(
                scope=scope,
                metrics=metric_objs,
                schema_url="",
            )
            resource_metrics_list.append(
                ResourceMetrics(
                    resource=resource,
                    scope_metrics=[scope_metrics],
                    schema_url="",
                )
            )

        return MetricsData(resource_metrics=resource_metrics_list)

    # ------------------------------------------------------------------
    # Exporter interface
    # ------------------------------------------------------------------

    def export(self, signals: Iterable[Signal]) -> None:
        spans: list[SpanSignal] = []
        logs: list[LogSignal] = []
        metrics: list[MetricSignal] = []

        for sig in signals:
            if isinstance(sig, SpanSignal):
                spans.append(sig)
            elif isinstance(sig, LogSignal):
                logs.append(sig)
            elif isinstance(sig, MetricSignal):
                metrics.append(sig)

        if spans:
            readable_spans = [self._build_readable_span(s) for s in spans]
            self._span_exporter.export(readable_spans)

        if logs:
            readable_logs = [self._build_readable_log(lg) for lg in logs]
            self._log_exporter.export(readable_logs)

        if metrics:
            metrics_data = self._build_metrics_data(metrics)
            self._metric_exporter.export(metrics_data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.flush()
        try:
            self._span_exporter.shutdown()
        except Exception:
            pass
        try:
            self._log_exporter.shutdown()
        except Exception:
            pass
        try:
            self._metric_exporter.shutdown()
        except Exception:
            pass
