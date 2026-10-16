"""HyperDX's bootstrap sources against the bronze DDL they are mapped onto.

HyperDX reads `sources.json` only into an empty Mongo and does not validate a column
name until a query runs, so a typo here surfaces as an empty page in the UI. These
tests make the DDL the oracle instead: every expression must name a column that the
source's table actually has in `migrations/0001_bronze_otel.sql`.
"""

import json
import re
from pathlib import Path

import pytest

HYPERDX = Path(__file__).resolve().parents[1]
MIGRATIONS = HYPERDX.parent / "clickhouse" / "migrations"
CONNECTION_NAME = "Sentinel ClickHouse"

EXPRESSION_KEYS = re.compile(r"Expression$|^defaultTableSelectExpression$")
SOURCE_REFS = ("logSourceId", "traceSourceId", "metricSourceId", "sessionSourceId")


def _bronze_columns() -> dict[str, set[str]]:
    ddl = (MIGRATIONS / "0001_bronze_otel.sql").read_text()
    tables: dict[str, set[str]] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS bronze\.(\w+)\s*\((.*?)\n\)\s*\nENGINE", ddl, re.DOTALL
    ):
        tables[match.group(1)] = set(re.findall(r"^\s*`([^`]+)`", match.group(2), re.MULTILINE))
    return tables


def _identifiers(expression: str) -> set[str]:
    """Column names in a ClickHouse expression: bare words that are not calls or numbers."""
    names = set()
    expression = re.sub(r"\b\d[\w.]*", "", expression)
    for token in re.finditer(r"[A-Za-z_][\w.]*(?!\w)(\s*\()?", expression):
        if token.group(1) is None:
            names.add(token.group(0))
    return names


@pytest.fixture(scope="module")
def sources() -> list[dict]:
    return json.loads((HYPERDX / "sources.json").read_text())


@pytest.fixture(scope="module")
def columns() -> dict[str, set[str]]:
    return _bronze_columns()


def test_ddl_parser_finds_the_tables_the_sources_use(columns):
    assert {"otel_logs", "otel_traces", "otel_metrics_gauge"} <= set(columns)
    assert "TimestampTime" in columns["otel_logs"]
    assert "Events.Timestamp" in columns["otel_traces"]


def test_one_source_per_signal(sources):
    assert sorted(s["kind"] for s in sources) == ["log", "metric", "trace"]


def test_every_source_reads_bronze_through_the_one_connection(sources):
    for source in sources:
        assert source["from"]["databaseName"] == "bronze", source["name"]
        assert source["connection"] == CONNECTION_NAME, source["name"]


def test_entrypoint_creates_the_connection_the_sources_name():
    entrypoint = (HYPERDX / "entrypoint.sh").read_text()
    assert f'name: "{CONNECTION_NAME}"' in entrypoint


def test_signal_tables_exist(sources, columns):
    for source in sources:
        table = source["from"]["tableName"]
        if source["kind"] != "metric":
            assert table in columns, f"{source['name']}: bronze.{table} is not in the DDL"


def test_metric_tables_exist_and_carry_a_value_shape(sources, columns):
    (metric,) = (s for s in sources if s["kind"] == "metric")
    assert metric["from"]["tableName"] == ""
    assert set(metric["metricTables"]) <= {"gauge", "sum", "histogram", "summary"}
    for kind, table in metric["metricTables"].items():
        assert table in columns, f"metricTables.{kind}: bronze.{table} is not in the DDL"
        assert {"MetricName", "TimeUnix", "Attributes", "ResourceAttributes"} <= columns[table]


def test_every_expression_names_a_real_column(sources, columns):
    checked = 0
    for source in sources:
        if source["kind"] == "metric":
            tables = list(source["metricTables"].values())
        else:
            tables = [source["from"]["tableName"]]
        for key, value in source.items():
            if not (isinstance(value, str) and EXPRESSION_KEYS.search(key)):
                continue
            for table in tables:
                missing = _identifiers(value) - columns[table]
                assert not missing, f"{source['name']}.{key}={value!r}: {missing} not in bronze.{table}"
            checked += 1
    assert checked >= 20


def test_source_cross_references_resolve(sources):
    names = {s["name"] for s in sources}
    for source in sources:
        for ref in SOURCE_REFS:
            if ref in source:
                assert source[ref] in names, f"{source['name']}.{ref} -> {source[ref]}"


def test_trace_source_maps_the_span_identity_columns(sources):
    (trace,) = (s for s in sources if s["kind"] == "trace")
    assert trace["traceIdExpression"] == "TraceId"
    assert trace["spanIdExpression"] == "SpanId"
    assert trace["parentSpanIdExpression"] == "ParentSpanId"
    # Duration is Int64 nanoseconds, as OTLP carries it; precision 9 is what
    # makes the UI read it as such.
    assert trace["durationPrecision"] == 9


def test_hyperdx_role_is_select_only():
    sql = (MIGRATIONS / "0007_hyperdx_role.sql").read_text()
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    grants = re.findall(r"GRANT\s+(.*?)\s+ON\s+(\S+)\s+TO\s+sentinel_hyperdx\b", code, re.DOTALL)
    assert {on for _, on in grants} == {"bronze.*", "silver.*", "system.tables", "system.columns"}
    assert all(privilege.strip() == "SELECT" for privilege, _ in grants)
    assert "{pw:String}" in code
    assert re.search(r"SETTINGS\s+readonly\s*=\s*2", code)
