from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

import clickhouse_connect

from otelgen.config import ClickHouseConnConfig
from otelgen.contract.models import SchemaConfig
from otelgen.exporters.base import Exporter, Signal
from otelgen.model import LogSignal, MetricSignal, SpanSignal


def _ns_to_dt(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)


# Canonical fields whose values are datetime (converted from unix nano).
_TIMESTAMP_FIELDS = frozenset({"time_unix_nano", "start_unix_nano"})

# Canonical field for trace duration (derived: end_unix_nano - start_unix_nano).
_DURATION_FIELD = "duration_nano"

# Canonical fields each signal kind produces (mirrors _extract_fields). Used to keep
# the inserted column list in lockstep with the row values when the schema config
# maps columns that a given signal kind does not provide.
_KNOWN_FIELDS: dict[str, frozenset[str]] = {
    "logs": frozenset(
        {"time_unix_nano", "service_name", "severity_text", "severity_number",
         "body", "trace_id", "span_id", "attributes", "resource_attributes"}
    ),
    "traces": frozenset(
        {"start_unix_nano", "trace_id", "span_id", "parent_span_id", "name",
         "service_name", "duration_nano", "status_code", "attributes", "resource_attributes"}
    ),
    "metrics": frozenset(
        {"time_unix_nano", "name", "type", "value", "service_name",
         "attributes", "resource_attributes"}
    ),
}

# Column type hints used by render_create_table_ddl.
_COLUMN_TYPES: dict[str, str] = {
    "Timestamp": "DateTime64(9, 'UTC')",
    "TraceId": "String",
    "SpanId": "String",
    "ParentSpanId": "Nullable(String)",
    "SpanName": "LowCardinality(String)",
    "ServiceName": "LowCardinality(String)",
    "SeverityText": "LowCardinality(String)",
    "SeverityNumber": "Int32",
    "Body": "String",
    "Duration": "Int64",
    "StatusCode": "LowCardinality(String)",
    "MetricName": "LowCardinality(String)",
    "MetricType": "LowCardinality(String)",
    "Value": "Float64",
    "LogAttributes": "Map(String, String)",
    "SpanAttributes": "Map(String, String)",
    "Attributes": "Map(String, String)",
    "ResourceAttributes": "Map(String, String)",
}

_DEFAULT_COL_TYPE = "String"


def _extract_fields(signal: Signal) -> tuple[str, dict[str, object]]:
    """Return (kind, canonical_fields_dict) for a signal.

    The returned dict includes the derived `duration_nano` key for spans.
    Fields with a None value are kept so the exporter can decide whether to skip them.
    """
    if isinstance(signal, LogSignal):
        return "logs", {
            "time_unix_nano": signal.time_unix_nano,
            "service_name": signal.service_name,
            "severity_text": signal.severity_text,
            "severity_number": signal.severity_number,
            "body": signal.body,
            "trace_id": signal.trace_id,
            "span_id": signal.span_id,
            "attributes": signal.attributes,
            "resource_attributes": signal.resource_attributes,
        }
    if isinstance(signal, SpanSignal):
        return "traces", {
            "start_unix_nano": signal.start_unix_nano,
            "trace_id": signal.trace_id,
            "span_id": signal.span_id,
            "parent_span_id": signal.parent_span_id,
            "name": signal.name,
            "service_name": signal.service_name,
            "duration_nano": signal.end_unix_nano - signal.start_unix_nano,
            "status_code": signal.status_code,
            "attributes": signal.attributes,
            "resource_attributes": signal.resource_attributes,
        }
    if isinstance(signal, MetricSignal):
        return "metrics", {
            "time_unix_nano": signal.time_unix_nano,
            "name": signal.name,
            "type": signal.type,
            "value": signal.value,
            "service_name": signal.service_name,
            "attributes": signal.attributes,
            "resource_attributes": signal.resource_attributes,
        }
    raise TypeError(f"Unsupported signal type: {type(signal)!r}")


class ClickHouseExporter(Exporter):
    """Schema-config-driven batch exporter writing canonical signals to ClickHouse.

    Constructor args:
        conn   -- ClickHouseConnConfig with host/port/user/password/database.
        schema -- SchemaConfig parsed from clickhouse_schema.yaml.
    """

    def __init__(self, conn: ClickHouseConnConfig, schema: SchemaConfig) -> None:
        self._client = clickhouse_connect.get_client(
            host=conn.host,
            port=conn.port,
            username=conn.user,
            password=conn.password,
            database=conn.database,
        )
        self._schema = schema
        self._buf: dict[str, list[list[object]]] = {
            "logs": [],
            "traces": [],
            "metrics": [],
        }

    def _effective_columns(self, kind: str) -> list[tuple[str, str]]:
        """Ordered (canonical_field, ch_column) pairs this kind actually populates.

        Filters the schema's column map to fields the signal kind produces, so added
        columns with no canonical mapping are skipped consistently in both the row
        and the inserted column list.
        """
        known = _KNOWN_FIELDS[kind]
        tbl = self._schema.tables[kind]
        return [(cf, col) for cf, col in tbl.columns.items() if cf in known]

    def _to_row(self, signal: Signal) -> tuple[str, list[object]]:
        """Map a canonical signal to an ordered row list for its ClickHouse table."""
        kind, fields = _extract_fields(signal)
        row: list[object] = []
        for canonical_field, _ch_col in self._effective_columns(kind):
            value = fields[canonical_field]
            if canonical_field in _TIMESTAMP_FIELDS and isinstance(value, int):
                value = _ns_to_dt(value)
            row.append(value)
        return kind, row

    def export(self, signals: Iterable[Signal]) -> None:
        for signal in signals:
            kind, row = self._to_row(signal)
            self._buf[kind].append(row)
        for kind in list(self._buf):
            if len(self._buf[kind]) >= self._schema.batch_size:
                self._flush_kind(kind)

    def _flush_kind(self, kind: str) -> None:
        rows, self._buf[kind] = self._buf[kind], []
        if not rows:
            return
        tbl = self._schema.tables[kind]
        col_names = [ch_col for _cf, ch_col in self._effective_columns(kind)]
        self._client.insert(tbl.name, rows, column_names=col_names)

    def flush(self) -> None:
        for kind in list(self._buf):
            self._flush_kind(kind)

    def close(self) -> None:
        self.flush()
        self._client.close()


def render_create_table_ddl(schema: SchemaConfig) -> str:
    """Return CREATE TABLE DDL statements for all tables in *schema*.

    Used by the --init-schema CLI flag. Does NOT execute against ClickHouse.
    Tables use MergeTree engine, partitioned daily by the timestamp column.
    """
    parts: list[str] = []
    for kind, tbl in schema.tables.items():
        col_defs: list[str] = []
        timestamp_col: str | None = None
        for canonical_field, ch_col in tbl.columns.items():
            col_type = _COLUMN_TYPES.get(ch_col, _DEFAULT_COL_TYPE)
            col_defs.append(f"    {ch_col} {col_type}")
            if canonical_field in _TIMESTAMP_FIELDS and timestamp_col is None:
                timestamp_col = ch_col

        col_block = ",\n".join(col_defs)
        partition_expr = (
            f"toYYYYMMDD({timestamp_col})" if timestamp_col else "tuple()"
        )
        ddl = (
            f"-- {kind}\n"
            f"CREATE TABLE IF NOT EXISTS {tbl.name}\n"
            f"(\n"
            f"{col_block}\n"
            f")\n"
            f"ENGINE = MergeTree()\n"
            f"PARTITION BY {partition_expr}\n"
            f"ORDER BY ({timestamp_col or 'tuple()'});\n"
        )
        parts.append(ddl)
    return "\n".join(parts)
