from __future__ import annotations

"""Integration test: spin up ClickHouse via testcontainers, run the engine,
write signals with ClickHouseExporter, and query the row back.

Skipped automatically when:
  - testcontainers[clickhouse] is not installed, OR
  - Docker is not reachable on the current host.

Run in the normal pytest suite; the docker integration test skips cleanly
when infrastructure is unavailable.
"""

import pytest

# ---------------------------------------------------------------------------
# Skip guard: require both testcontainers and Docker
# ---------------------------------------------------------------------------

testcontainers = pytest.importorskip(
    "testcontainers",
    reason="testcontainers package not installed; skipping CH integration test",
)

try:
    from testcontainers.clickhouse import ClickHouseContainer  # type: ignore[import]
except ImportError:
    pytest.skip(
        "testcontainers[clickhouse] not installed; skipping CH integration test",
        allow_module_level=True,
    )

try:
    import docker  # type: ignore[import]

    _docker_client = docker.from_env()
    _docker_client.ping()
except Exception:
    pytest.skip(
        "Docker daemon not reachable; skipping CH integration test",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Actual integration test — only runs when Docker + testcontainers are present
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone
from pathlib import Path

from otelgen.config import ClickHouseConnConfig
from otelgen.contract.loader import load_contract
from otelgen.exporters.clickhouse import ClickHouseExporter, render_create_table_ddl
from otelgen.scenarios.engine import ScenarioEngine
from otelgen.seeding import make_rng
from otelgen.signals.factory import SignalFactory
from otelgen.topology import Topology

CONTRACT_DIR = Path(__file__).parent.parent.parent / "contract"


@pytest.fixture(scope="module")
def ch_container():
    with ClickHouseContainer("clickhouse/clickhouse-server:latest") as container:
        yield container


@pytest.fixture(scope="module")
def ch_client(ch_container):
    import clickhouse_connect

    host = ch_container.get_container_host_ip()
    port = int(ch_container.get_exposed_port(8123))
    client = clickhouse_connect.get_client(
        host=host,
        port=port,
        username=ch_container.username,
        password=ch_container.password,
        database=ch_container.dbname,
    )
    yield client
    client.close()


@pytest.fixture(scope="module")
def bundle():
    return load_contract(CONTRACT_DIR, scenario_name="baseline")


@pytest.fixture(scope="module")
def created_tables(ch_client, bundle):
    """Create schema tables from DDL and return."""
    ddl = render_create_table_ddl(bundle.schema)
    for stmt in ddl.split(";"):
        stmt = stmt.strip()
        if stmt:
            ch_client.command(stmt)
    return True


@pytest.fixture(scope="module")
def exported_run(ch_container, bundle, created_tables):
    """Run a small backfill and export to ClickHouse; return run_id."""
    host = ch_container.get_container_host_ip()
    port = int(ch_container.get_exposed_port(8123))

    conn = ClickHouseConnConfig(
        host=host,
        port=port,
        user=ch_container.username,
        password=ch_container.password,
        database=ch_container.dbname,
    )

    rng = make_rng(42)
    run_id = "integration-test-001"

    factory = SignalFactory(
        provider_profile=bundle.provider_profile,
        run_id=run_id,
        scenario_name=bundle.scenario.name,
        rng=rng,
    )
    topology = Topology(bundle.topology)
    engine = ScenarioEngine(topology=topology, scenario=bundle.scenario, factory=factory, rng=rng)

    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    window_start = int((now - timedelta(minutes=5)).timestamp() * 1e9)
    # 3 ticks, 10s apart — small but produces real signals from all 7 components
    ticks = [window_start + i * 10_000_000_000 for i in range(3)]

    exporter = ClickHouseExporter(conn, bundle.schema)
    signals = list(engine.run(ticks, window_start))
    exporter.export(signals)
    exporter.flush()
    exporter.close()

    return run_id


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def test_logs_row_count_greater_than_zero(ch_client, exported_run):
    result = ch_client.query("SELECT count() FROM otel_logs")
    assert result.result_rows[0][0] > 0


def test_traces_row_count_greater_than_zero(ch_client, exported_run):
    result = ch_client.query("SELECT count() FROM otel_traces")
    assert result.result_rows[0][0] > 0


def test_metrics_row_count_greater_than_zero(ch_client, exported_run):
    result = ch_client.query("SELECT count() FROM otel_metrics")
    assert result.result_rows[0][0] > 0


def test_sentinel_synthetic_present_in_logs(ch_client, exported_run):
    result = ch_client.query(
        "SELECT ResourceAttributes['sentinel.synthetic'] FROM otel_logs LIMIT 1"
    )
    assert result.result_rows[0][0] == "true"


def test_sentinel_synthetic_present_in_traces(ch_client, exported_run):
    result = ch_client.query(
        "SELECT ResourceAttributes['sentinel.synthetic'] FROM otel_traces LIMIT 1"
    )
    assert result.result_rows[0][0] == "true"


def test_sentinel_run_id_matches(ch_client, exported_run):
    result = ch_client.query(
        "SELECT ResourceAttributes['sentinel.run_id'] FROM otel_logs LIMIT 1"
    )
    assert result.result_rows[0][0] == exported_run
