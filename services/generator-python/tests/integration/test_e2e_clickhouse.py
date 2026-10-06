"""Integration test: run the engine and write signals to a ClickHouse that is
already running, then query the rows back.

**Targets the instance named by `CLICKHOUSE_URL`** and brings no ClickHouse of
its own. The previous version span one up in a container of its own and skipped
itself away when that machinery or the Docker daemon was missing, which meant it
crossed no seam at all: in the live job it would have started a *second*,
different ClickHouse beside the one the job booted — its own image tag (evading
REQ-I-01's single-version assert), no `init.d` mounts, no silver, and a
passwordless `default` (SPEC §9).

What that costs, named: there is no skip guard any more, so a missing ClickHouse
is a **failure**, not a skip — a test that skips in CI is issue #34 in
miniature — and the file is no longer runnable on a laptop without `make up`
first. That is also why `make test-generator-integration` is deliberately not
part of the `make test` aggregate (REQ-B-15): `make test` must keep working with
no stack running.

The tables are the generator's own dev-only direct→ClickHouse schema
(`config/clickhouse_schema.yaml`), not Pod 3's bronze. They are created in a
scratch database (`CLICKHOUSE_TEST_DATABASE`, default `otelgen_it`) and dropped
afterwards, so this test can neither see nor disturb `bronze.*` / `silver.*`.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import clickhouse_connect
import pytest

from otelgen.config import ClickHouseConnConfig
from otelgen.contract.loader import load_contract
from otelgen.exporters.clickhouse import ClickHouseExporter, render_create_table_ddl
from otelgen.scenarios.engine import ScenarioEngine
from otelgen.seeding import make_rng
from otelgen.signals.factory import SignalFactory
from otelgen.topology import Topology

CONTRACT_DIR = Path(__file__).parent.parent.parent / "config"

#: Scratch database. Separate from `default` so a run cannot collide with the
#: bronze/silver layers living in the same instance.
TEST_DATABASE = os.environ.get("CLICKHOUSE_TEST_DATABASE", "otelgen_it")

RUN_ID = "integration-test-001"


def _target() -> ClickHouseConnConfig:
    """Resolve `CLICKHOUSE_URL` into a connection config, or fail loudly.

    Failing on an unset or unparseable variable is the point: the caller is
    `make test-generator-integration`, which is only ever run against a live
    stack. A default would turn "the stack is not up" into a confusing
    connection error at the first query instead of a statement of the
    precondition here.
    """
    url = os.environ.get("CLICKHOUSE_URL", "").strip()
    if not url:
        pytest.fail(
            "CLICKHOUSE_URL is unset. This suite targets a running ClickHouse and "
            "starts none of its own — run `make up` first, then "
            "`make test-generator-integration`."
        )
    parsed = urlparse(url)
    if not parsed.hostname:
        pytest.fail(f"CLICKHOUSE_URL is not a usable URL: {url!r}")
    return ClickHouseConnConfig(
        host=parsed.hostname,
        port=parsed.port or (8443 if parsed.scheme == "https" else 8123),
        user=parsed.username or os.environ.get("CLICKHOUSE_USER", "default"),
        password=parsed.password or os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database=TEST_DATABASE,
    )


@pytest.fixture(scope="module")
def conn() -> ClickHouseConnConfig:
    return _target()


@pytest.fixture(scope="module")
def ch_client(conn: ClickHouseConnConfig):
    """A client bound to the scratch database, which this fixture owns."""
    admin = clickhouse_connect.get_client(
        host=conn.host, port=conn.port, username=conn.user, password=conn.password
    )
    admin.command(f"CREATE DATABASE IF NOT EXISTS {TEST_DATABASE}")
    admin.close()

    client = clickhouse_connect.get_client(
        host=conn.host,
        port=conn.port,
        username=conn.user,
        password=conn.password,
        database=TEST_DATABASE,
    )
    yield client
    client.command(f"DROP DATABASE IF EXISTS {TEST_DATABASE}")
    client.close()


@pytest.fixture(scope="module")
def bundle():
    return load_contract(CONTRACT_DIR, scenario_name="baseline")


@pytest.fixture(scope="module")
def created_tables(ch_client, bundle):
    for stmt in render_create_table_ddl(bundle.schema).split(";"):
        stmt = stmt.strip()
        if stmt:
            ch_client.command(stmt)
    return True


@pytest.fixture(scope="module")
def exported_run(conn, bundle, created_tables):
    """Run a small backfill and export to ClickHouse; return the run id."""
    rng = make_rng(42)

    factory = SignalFactory(
        provider_profile=bundle.provider_profile,
        run_id=RUN_ID,
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
    exporter.export(list(engine.run(ticks, window_start)))
    exporter.flush()
    exporter.close()

    return RUN_ID


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", ["otel_logs", "otel_traces", "otel_metrics"])
def test_row_count_greater_than_zero(ch_client, exported_run, table):
    result = ch_client.query(f"SELECT count() FROM {table}")
    assert result.result_rows[0][0] > 0


@pytest.mark.parametrize("table", ["otel_logs", "otel_traces"])
def test_sentinel_synthetic_present(ch_client, exported_run, table):
    result = ch_client.query(f"SELECT ResourceAttributes['sentinel.synthetic'] FROM {table} LIMIT 1")
    assert result.result_rows[0][0] == "true"


def test_sentinel_run_id_matches(ch_client, exported_run):
    result = ch_client.query("SELECT ResourceAttributes['sentinel.run_id'] FROM otel_logs LIMIT 1")
    assert result.result_rows[0][0] == exported_run
