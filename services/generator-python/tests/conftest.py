from __future__ import annotations

import random
from pathlib import Path

import pytest

from otelgen.contract.loader import ContractBundle, load_contract
from otelgen.contract.models import (
    ComponentSpec,
    ProviderProfile,
    SchemaConfig,
)
from otelgen.model import LogSignal, MetricSignal, SpanSignal
from otelgen.scenarios.base import EmissionState
from otelgen.seeding import make_rng

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONTRACT_DIR = Path(__file__).parent.parent / "config"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def contract_dir() -> Path:
    return CONTRACT_DIR


@pytest.fixture(scope="session")
def baseline_bundle() -> ContractBundle:
    return load_contract(CONTRACT_DIR, scenario_name="baseline", provider_name="gcp")


@pytest.fixture()
def rng() -> random.Random:
    """A fresh, seeded RNG for each test — deterministic."""
    return make_rng(42)


@pytest.fixture()
def component_spec() -> ComponentSpec:
    return ComponentSpec(
        name="orchestration.daily_etl",
        type="orchestration",
        service_name="cloud-composer-etl",
        depends_on=[],
        base_rate=2.0,
        base_latency_ms=250.0,
        error_ratio=0.01,
    )


@pytest.fixture()
def provider_profile(baseline_bundle: ContractBundle) -> ProviderProfile:
    return baseline_bundle.provider_profile


@pytest.fixture()
def schema_config(baseline_bundle: ContractBundle) -> SchemaConfig:
    return baseline_bundle.schema


@pytest.fixture()
def normal_state() -> EmissionState:
    return EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False)


@pytest.fixture()
def silenced_state() -> EmissionState:
    return EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=True)


@pytest.fixture()
def error_state() -> EmissionState:
    return EmissionState(error_ratio=1.0, latency_mult=1.0, silenced=False)


T_UNIX_NANO = 1_700_000_000_000_000_000  # arbitrary fixed timestamp


@pytest.fixture()
def sample_span() -> SpanSignal:
    return SpanSignal(
        trace_id="a" * 32,
        span_id="b" * 16,
        parent_span_id=None,
        name="orchestration.operation",
        service_name="cloud-composer-etl",
        start_unix_nano=T_UNIX_NANO,
        end_unix_nano=T_UNIX_NANO + 250_000_000,
        status_code="OK",
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


@pytest.fixture()
def sample_log() -> LogSignal:
    return LogSignal(
        time_unix_nano=T_UNIX_NANO,
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


@pytest.fixture()
def sample_metric() -> MetricSignal:
    return MetricSignal(
        time_unix_nano=T_UNIX_NANO,
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
