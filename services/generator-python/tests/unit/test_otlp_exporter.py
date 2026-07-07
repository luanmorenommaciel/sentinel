from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from otelgen.model import LogSignal, MetricSignal, SpanSignal

T_NS = 1_700_000_000_000_000_000


def _make_span() -> SpanSignal:
    return SpanSignal(
        trace_id="a" * 32,
        span_id="b" * 16,
        parent_span_id=None,
        name="orchestration.operation",
        service_name="cloud-composer-etl",
        start_unix_nano=T_NS,
        end_unix_nano=T_NS + 250_000_000,
        status_code="OK",
        attributes={"component.name": "orchestration.daily_etl"},
        resource_attributes={
            "sentinel.synthetic": "true",
            "sentinel.scenario": "baseline",
            "sentinel.run_id": "test-run-001",
            "cloud.provider": "gcp",
        },
    )


def _make_log() -> LogSignal:
    return LogSignal(
        time_unix_nano=T_NS,
        severity_text="INFO",
        severity_number=9,
        service_name="cloud-composer-etl",
        body="Request completed.",
        trace_id="a" * 32,
        span_id="b" * 16,
        attributes={"component.name": "orchestration.daily_etl"},
        resource_attributes={
            "sentinel.synthetic": "true",
            "sentinel.scenario": "baseline",
            "sentinel.run_id": "test-run-001",
            "cloud.provider": "gcp",
        },
    )


def _make_metric() -> MetricSignal:
    return MetricSignal(
        time_unix_nano=T_NS,
        name="operation.latency_ms",
        type="gauge",
        value=250.0,
        service_name="cloud-composer-etl",
        attributes={"component.name": "orchestration.daily_etl", "component.type": "orchestration"},
        resource_attributes={
            "sentinel.synthetic": "true",
            "sentinel.scenario": "baseline",
            "sentinel.run_id": "test-run-001",
            "cloud.provider": "gcp",
        },
    )


# ---------------------------------------------------------------------------
# OTLPExporter construction
# ---------------------------------------------------------------------------


class TestOTLPExporterConstruction:
    def test_can_construct_http_protobuf(self):
        """OTLPExporter can be instantiated without hitting a network."""
        from otelgen.exporters.otlp import OTLPExporter

        exporter = OTLPExporter(endpoint="http://localhost:4318", protocol="http/protobuf")
        assert exporter is not None

    def test_can_construct_grpc(self):
        from otelgen.exporters.otlp import OTLPExporter

        exporter = OTLPExporter(endpoint="http://localhost:4317", protocol="grpc")
        assert exporter is not None

    def test_headers_forwarded_to_underlying_exporters(self):
        """The auth/headers dict is passed to all three OTLP exporter constructors."""
        headers = {"authorization": "secret-key"}
        with (
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ) as span_cls,
            patch(
                "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"
            ) as log_cls,
            patch(
                "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"
            ) as metric_cls,
        ):
            from otelgen.exporters.otlp import OTLPExporter

            OTLPExporter(endpoint="http://localhost:4318", protocol="http/protobuf", headers=headers)
            for cls in (span_cls, log_cls, metric_cls):
                assert cls.call_args.kwargs["headers"] == headers

    def test_no_headers_passes_none(self):
        with (
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ) as span_cls,
            patch("opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"),
            patch("opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"),
        ):
            from otelgen.exporters.otlp import OTLPExporter

            OTLPExporter(endpoint="http://localhost:4318", protocol="http/protobuf")
            assert span_cls.call_args.kwargs["headers"] is None


class TestGrpcDefaultAndInsecure:
    """AT-001/AT-002: gRPC :4317 is the default transport; insecure auto-resolves."""

    def test_config_defaults_to_grpc_4317(self):
        from otelgen.config import RunConfig

        cfg = RunConfig.build(delivery="otlp")
        assert cfg.otlp_protocol == "grpc"
        assert cfg.otlp_endpoint == "http://localhost:4317"

    def test_grpc_exporters_built_with_insecure_true_for_http(self):
        with (
            patch(
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"
            ) as span_cls,
            patch(
                "opentelemetry.exporter.otlp.proto.grpc._log_exporter.OTLPLogExporter"
            ) as log_cls,
            patch(
                "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter"
            ) as metric_cls,
        ):
            from otelgen.exporters.otlp import OTLPExporter

            OTLPExporter(endpoint="http://localhost:4317", protocol="grpc")
            for cls in (span_cls, log_cls, metric_cls):
                assert cls.call_args.kwargs["insecure"] is True

    def test_grpc_insecure_false_for_https(self):
        with (
            patch(
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"
            ) as span_cls,
            patch("opentelemetry.exporter.otlp.proto.grpc._log_exporter.OTLPLogExporter"),
            patch("opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter"),
        ):
            from otelgen.exporters.otlp import OTLPExporter

            OTLPExporter(endpoint="https://collector.example:4317", protocol="grpc")
            assert span_cls.call_args.kwargs["insecure"] is False

    def test_explicit_insecure_overrides_scheme(self):
        with (
            patch(
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"
            ) as span_cls,
            patch("opentelemetry.exporter.otlp.proto.grpc._log_exporter.OTLPLogExporter"),
            patch("opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter"),
        ):
            from otelgen.exporters.otlp import OTLPExporter

            OTLPExporter(endpoint="https://collector.example:4317", protocol="grpc", insecure=True)
            assert span_cls.call_args.kwargs["insecure"] is True


class TestBuildExporterHeaders:
    def test_build_exporter_forwards_otlp_headers(self):
        from otelgen.config import RunConfig
        from otelgen.exporters import base

        cfg = RunConfig.build(delivery="otlp", otlp_headers={"authorization": "k"})
        with patch.object(base, "build_exporter", wraps=base.build_exporter):
            with patch("otelgen.exporters.otlp.OTLPExporter") as exp_cls:
                base.build_exporter(cfg)
                assert exp_cls.call_args.kwargs["headers"] == {"authorization": "k"}


# ---------------------------------------------------------------------------
# OTLPExporter.export — no network calls (underlying exporters mocked)
# ---------------------------------------------------------------------------


class TestOTLPExporterExport:
    """Patch the three underlying OTLP exporter classes so export() builds
    SDK objects and routes them without sending anything over the wire."""

    @pytest.fixture()
    def patched_exporter(self):
        mock_span_exp = MagicMock()
        mock_log_exp = MagicMock()
        mock_metric_exp = MagicMock()

        with (
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter",
                return_value=mock_span_exp,
            ),
            patch(
                "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter",
                return_value=mock_log_exp,
            ),
            patch(
                "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter",
                return_value=mock_metric_exp,
            ),
        ):
            from otelgen.exporters.otlp import OTLPExporter

            exporter = OTLPExporter(endpoint="http://localhost:4318", protocol="http/protobuf")
            exporter._span_exporter = mock_span_exp
            exporter._log_exporter = mock_log_exp
            exporter._metric_exporter = mock_metric_exp

            yield exporter, mock_span_exp, mock_log_exp, mock_metric_exp

    def test_export_routes_spans(self, patched_exporter):
        exporter, mock_span_exp, _, _ = patched_exporter
        exporter.export([_make_span()])
        mock_span_exp.export.assert_called_once()

    def test_export_routes_logs(self, patched_exporter):
        exporter, _, mock_log_exp, _ = patched_exporter
        exporter.export([_make_log()])
        mock_log_exp.export.assert_called_once()

    def test_export_routes_metrics(self, patched_exporter):
        exporter, _, _, mock_metric_exp = patched_exporter
        exporter.export([_make_metric()])
        mock_metric_exp.export.assert_called_once()

    def test_export_mixed_signals_routes_all(self, patched_exporter):
        exporter, mock_span_exp, mock_log_exp, mock_metric_exp = patched_exporter
        exporter.export([_make_span(), _make_log(), _make_metric()])
        mock_span_exp.export.assert_called_once()
        mock_log_exp.export.assert_called_once()
        mock_metric_exp.export.assert_called_once()

    def test_export_empty_signals_calls_nothing(self, patched_exporter):
        exporter, mock_span_exp, mock_log_exp, mock_metric_exp = patched_exporter
        exporter.export([])
        mock_span_exp.export.assert_not_called()
        mock_log_exp.export.assert_not_called()
        mock_metric_exp.export.assert_not_called()

    def test_error_span_exported_without_error(self, patched_exporter):
        exporter, mock_span_exp, _, _ = patched_exporter
        error_span = SpanSignal(
            trace_id="c" * 32,
            span_id="d" * 16,
            parent_span_id=None,
            name="orchestration.operation",
            service_name="cloud-composer-etl",
            start_unix_nano=T_NS,
            end_unix_nano=T_NS + 100_000_000,
            status_code="ERROR",
            attributes={"error": "true"},
            resource_attributes={"sentinel.synthetic": "true", "cloud.provider": "gcp"},
        )
        exporter.export([error_span])
        mock_span_exp.export.assert_called_once()
