from __future__ import annotations

import json
from datetime import timedelta

import pytest

from otelgen.contract.loader import load_contract
from otelgen.contract.output_schema import (
    CONTRACT_VERSION,
    schema_path,
    signal_to_contract_dict,
)
from otelgen.runmode import backfill_ticks
from otelgen.scenarios.engine import ScenarioEngine
from otelgen.seeding import make_rng
from otelgen.signals.factory import SignalFactory
from otelgen.topology import Topology

jsonschema = pytest.importorskip("jsonschema")

WINDOW_START = 1_700_000_000_000_000_000


@pytest.fixture(scope="module")
def schema() -> dict:
    with schema_path().open() as fh:
        return json.load(fh)


def _generate_signals(contract_dir, *, scenario="black_friday", seed=42):
    bundle = load_contract(contract_dir, scenario_name=scenario, provider_name="gcp")
    rng = make_rng(seed)
    factory = SignalFactory(
        provider_profile=bundle.provider_profile,
        run_id="contract-test",
        scenario_name=bundle.scenario.name,
        rng=rng,
    )
    engine = ScenarioEngine(
        topology=Topology(bundle.topology),
        scenario=bundle.scenario,
        factory=factory,
        rng=rng,
        step_seconds=1.0,
        rate=20,
    )
    ticks = backfill_ticks(window=timedelta(seconds=8), step=timedelta(seconds=1))
    return list(engine.run(ticks, WINDOW_START))


class TestOutputContract:
    def test_schema_file_exists_and_is_versioned(self, schema: dict):
        assert schema_path().exists()
        assert schema["version"] == CONTRACT_VERSION

    def test_generated_signals_validate_against_schema(self, contract_dir, schema: dict):
        """AT-007: every emitted signal conforms to the published JSON Schema (0 violations)."""
        validator = jsonschema.Draft202012Validator(schema)
        signals = _generate_signals(contract_dir)
        assert signals, "expected the engine to produce signals"
        violations = 0
        for sig in signals:
            doc = signal_to_contract_dict(sig)
            errors = list(validator.iter_errors(doc))
            violations += len(errors)
        assert violations == 0

    def test_all_three_signal_types_present_and_valid(self, contract_dir, schema: dict):
        validator = jsonschema.Draft202012Validator(schema)
        docs = [signal_to_contract_dict(s) for s in _generate_signals(contract_dir)]
        types = {d["signal_type"] for d in docs}
        assert {"log", "span", "metric"} <= types
        for d in docs:
            validator.validate(d)

    def test_contract_version_stamped(self, contract_dir):
        docs = [signal_to_contract_dict(s) for s in _generate_signals(contract_dir)]
        assert all(d["contract_version"] == CONTRACT_VERSION for d in docs)
