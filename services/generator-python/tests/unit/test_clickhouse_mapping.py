from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from otelgen.config import ClickHouseConnConfig
from otelgen.contract.models import SchemaConfig, TableSpec
from otelgen.exporters.clickhouse import (
    ClickHouseExporter,
    _ns_to_dt,
    render_create_table_ddl,
)
from otelgen.model import LogSignal, MetricSignal, SpanSignal

T_NS = 1_700_000_000_000_000_000  # arbitrary fixed ns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn() -> ClickHouseConnConfig:
    return ClickHouseConnConfig(
        host="localhost", port=8123, user="default", password="", database="default"
    )


def _make_span(start_ns: int = T_NS, end_ns: int = T_NS + 250_000_000) -> SpanSignal:
    return SpanSignal(
        trace_id="a" * 32,
        span_id="b" * 16,
        parent_span_id=None,
        name="orchestration.operation",
        service_name="cloud-composer-etl",
        start_unix_nano=start_ns,
        end_unix_nano=end_ns,
        status_code="OK",
        attributes={"component.name": "orchestration.daily_etl", "component.type": "orchestration"},
        resource_attributes={
            "sentinel.synthetic": "true",
            "sentinel.scenario": "baseline",
            "sentinel.run_id": "test-run-001",
            "cloud.provider": "gcp",
            "gcp.project_id": "sentinel-synthetic",
            "service.name": "cloud-composer-etl",
        },
    )


def _make_log() -> LogSignal:
    return LogSignal(
        time_unix_nano=T_NS,
        severity_text="INFO",
        severity_number=9,
        service_name="cloud-composer-etl",
        body="Request completed successfully.",
        trace_id="a" * 32,
        span_id="b" * 16,
        attributes={"component.name": "orchestration.daily_etl"},
        resource_attributes={
            "sentinel.synthetic": "true",
            "sentinel.scenario": "baseline",
            "sentinel.run_id": "test-run-001",
            "cloud.provider": "gcp",
            "gcp.project_id": "sentinel-synthetic",
            "service.name": "cloud-composer-etl",
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
            "gcp.project_id": "sentinel-synthetic",
            "service.name": "cloud-composer-etl",
        },
    )


# ---------------------------------------------------------------------------
# _ns_to_dt helper
# ---------------------------------------------------------------------------


class TestNsToDt:
    def test_converts_to_utc_datetime(self):
        dt = _ns_to_dt(T_NS)
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc

    def test_value_is_correct(self):
        dt = _ns_to_dt(T_NS)
        expected = datetime.fromtimestamp(T_NS / 1e9, tz=timezone.utc)
        assert abs((dt - expected).total_seconds()) < 0.001


# ---------------------------------------------------------------------------
# ClickHouseExporter with mocked client
# ---------------------------------------------------------------------------


class TestClickHouseExporter:
    @pytest.fixture()
    def mock_client(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(
            "clickhouse_connect.get_client",
            lambda **kwargs: fake_client,
        )
        return fake_client

    def test_exporter_construction_calls_get_client(self, monkeypatch, schema_config):
        captured = {}

        def fake_get_client(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr("clickhouse_connect.get_client", fake_get_client)
        conn = _make_conn()
        ClickHouseExporter(conn, schema_config)
        assert captured["host"] == "localhost"

    def test_export_buffers_signals_below_batch_size(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_span(), _make_log()])
        # batch_size is 5000; only 2 signals → no insert yet
        mock_client.insert.assert_not_called()

    def test_flush_inserts_buffered_rows(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_span(), _make_log(), _make_metric()])
        exporter.flush()
        assert mock_client.insert.call_count == 3  # one insert per table kind

    def test_insert_uses_schema_table_names(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_span()])
        exporter.flush()
        call_args_list = mock_client.insert.call_args_list
        table_names = [c.args[0] for c in call_args_list]
        assert "otel_traces" in table_names

    def test_span_row_column_names_match_schema_ordered_columns(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_span()])
        exporter.flush()
        # Find the insert call for traces
        traces_call = next(
            c for c in mock_client.insert.call_args_list if c.args[0] == "otel_traces"
        )
        kwargs = traces_call.kwargs
        col_names = kwargs.get("column_names", traces_call.args[2] if len(traces_call.args) > 2 else [])
        expected_cols = schema_config.tables["traces"].ordered_columns
        assert col_names == expected_cols

    def test_log_row_column_names_match_schema_ordered_columns(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_log()])
        exporter.flush()
        logs_call = next(
            c for c in mock_client.insert.call_args_list if c.args[0] == "otel_logs"
        )
        col_names = logs_call.kwargs.get("column_names", logs_call.args[2] if len(logs_call.args) > 2 else [])
        expected_cols = schema_config.tables["logs"].ordered_columns
        assert col_names == expected_cols

    def test_metric_row_column_names_match_schema_ordered_columns(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_metric()])
        exporter.flush()
        metrics_call = next(
            c for c in mock_client.insert.call_args_list if c.args[0] == "otel_metrics"
        )
        col_names = metrics_call.kwargs.get("column_names", metrics_call.args[2] if len(metrics_call.args) > 2 else [])
        expected_cols = schema_config.tables["metrics"].ordered_columns
        assert col_names == expected_cols

    def test_timestamp_converted_to_datetime(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_log()])
        exporter.flush()
        logs_call = next(
            c for c in mock_client.insert.call_args_list if c.args[0] == "otel_logs"
        )
        rows = logs_call.args[1]
        assert len(rows) == 1
        row = rows[0]
        # First column in logs is Timestamp (time_unix_nano converted)
        assert isinstance(row[0], datetime)
        assert row[0].tzinfo == timezone.utc

    def test_span_duration_is_end_minus_start(self, mock_client, schema_config):
        start_ns = T_NS
        end_ns = T_NS + 500_000_000
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_span(start_ns=start_ns, end_ns=end_ns)])
        exporter.flush()
        traces_call = next(
            c for c in mock_client.insert.call_args_list if c.args[0] == "otel_traces"
        )
        rows = traces_call.args[1]
        row = rows[0]
        # Find Duration column index
        tbl = schema_config.tables["traces"]
        col_list = list(tbl.columns.keys())
        dur_idx = col_list.index("duration_nano")
        assert row[dur_idx] == end_ns - start_ns

    def test_close_flushes_and_closes_client(self, mock_client, schema_config):
        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_span()])
        exporter.close()
        mock_client.insert.assert_called()
        mock_client.close.assert_called_once()


# ---------------------------------------------------------------------------
# AT-003: Renamed column follows the YAML config with no code change
# ---------------------------------------------------------------------------


class TestSchemaReconfig:
    """Renaming a column in the schema config must retarget the insert."""

    def _make_renamed_schema(self, schema_config: SchemaConfig) -> SchemaConfig:
        """Return a SchemaConfig with traces.TraceId renamed to MyTraceId."""
        tables_data = {}
        for kind, tbl in schema_config.tables.items():
            new_cols = dict(tbl.columns)
            if kind == "traces" and "trace_id" in new_cols:
                new_cols["trace_id"] = "MyTraceId"
            tables_data[kind] = TableSpec(name=tbl.name, columns=new_cols)
        return SchemaConfig(version=schema_config.version, batch_size=schema_config.batch_size, tables=tables_data)

    def test_renamed_column_appears_in_insert(self, monkeypatch, schema_config):
        fake_client = MagicMock()
        monkeypatch.setattr("clickhouse_connect.get_client", lambda **kwargs: fake_client)

        renamed = self._make_renamed_schema(schema_config)
        exporter = ClickHouseExporter(_make_conn(), renamed)
        exporter.export([_make_span()])
        exporter.flush()

        traces_call = next(
            c for c in fake_client.insert.call_args_list if c.args[0] == "otel_traces"
        )
        col_names = traces_call.kwargs.get("column_names", traces_call.args[2] if len(traces_call.args) > 2 else [])
        assert "MyTraceId" in col_names
        assert "TraceId" not in col_names

    def test_original_column_name_unchanged_in_original_schema(self, monkeypatch, schema_config):
        fake_client = MagicMock()
        monkeypatch.setattr("clickhouse_connect.get_client", lambda **kwargs: fake_client)

        exporter = ClickHouseExporter(_make_conn(), schema_config)
        exporter.export([_make_span()])
        exporter.flush()

        traces_call = next(
            c for c in fake_client.insert.call_args_list if c.args[0] == "otel_traces"
        )
        col_names = traces_call.kwargs.get("column_names", traces_call.args[2] if len(traces_call.args) > 2 else [])
        assert "TraceId" in col_names


# ---------------------------------------------------------------------------
# render_create_table_ddl
# ---------------------------------------------------------------------------


class TestRenderCreateTableDdl:
    def test_ddl_contains_all_table_names(self, schema_config):
        ddl = render_create_table_ddl(schema_config)
        assert "otel_logs" in ddl
        assert "otel_traces" in ddl
        assert "otel_metrics" in ddl

    def test_ddl_contains_create_table_if_not_exists(self, schema_config):
        ddl = render_create_table_ddl(schema_config)
        assert "CREATE TABLE IF NOT EXISTS" in ddl

    def test_ddl_contains_mergetree_engine(self, schema_config):
        ddl = render_create_table_ddl(schema_config)
        assert "MergeTree()" in ddl

    def test_ddl_contains_partition_by(self, schema_config):
        ddl = render_create_table_ddl(schema_config)
        assert "PARTITION BY" in ddl

    def test_ddl_contains_all_column_names(self, schema_config):
        ddl = render_create_table_ddl(schema_config)
        # spot-check a few CH column names
        assert "Timestamp" in ddl
        assert "TraceId" in ddl
        assert "ServiceName" in ddl

    def test_ddl_renamed_column_reflects_schema(self, schema_config):
        """A renamed column in the schema config must appear in the DDL."""
        tables_data = {}
        for kind, tbl in schema_config.tables.items():
            new_cols = dict(tbl.columns)
            if kind == "logs" and "body" in new_cols:
                new_cols["body"] = "LogBody"
            tables_data[kind] = TableSpec(name=tbl.name, columns=new_cols)
        modified = SchemaConfig(version=schema_config.version, batch_size=schema_config.batch_size, tables=tables_data)
        ddl = render_create_table_ddl(modified)
        assert "LogBody" in ddl
