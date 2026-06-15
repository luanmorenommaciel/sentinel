from __future__ import annotations

import json
import os
from pathlib import Path

from otelgen.contract.loader import load_contract
from otelgen.contract.output_schema import signal_to_contract_dict
from otelgen.scenarios.engine import ScenarioEngine
from otelgen.seeding import make_rng
from otelgen.signals.factory import SignalFactory
from otelgen.topology import Topology

# Fixed, reproducible generation parameters for the golden snapshot (AT-005).
GOLDEN_SEED = 42
GOLDEN_RUN_ID = "golden-fixed-run"
GOLDEN_BASE_NS = 1_700_000_000_000_000_000
GOLDEN_TICKS = [GOLDEN_BASE_NS + i * 1_000_000_000 for i in range(3)]
GOLDEN_STEP_SECONDS = 1.0
GOLDEN_RATE = 20

_contracts_dir = os.environ.get("CONTRACTS_DIR")
_contracts_root = Path(_contracts_dir) if _contracts_dir else Path(__file__).resolve().parents[4] / "contracts" / "v1"
GOLDEN_FILE = _contracts_root / "golden" / "baseline_seed42.jsonl"


def generate_golden(contract_dir) -> list[dict]:
    """Deterministically generate the baseline signal set for the golden fixture.

    Uses fixed ticks (not wall-clock) + fixed seed + run_id so output is byte-stable.
    """
    bundle = load_contract(contract_dir, scenario_name="baseline", provider_name="gcp")
    rng = make_rng(GOLDEN_SEED)
    factory = SignalFactory(
        provider_profile=bundle.provider_profile,
        run_id=GOLDEN_RUN_ID,
        scenario_name=bundle.scenario.name,
        rng=rng,
    )
    engine = ScenarioEngine(
        topology=Topology(bundle.topology),
        scenario=bundle.scenario,
        factory=factory,
        rng=rng,
        step_seconds=GOLDEN_STEP_SECONDS,
        rate=GOLDEN_RATE,
    )
    return [signal_to_contract_dict(s) for s in engine.run(iter(GOLDEN_TICKS), GOLDEN_BASE_NS)]


class TestGoldenFixture:
    def test_golden_file_exists(self):
        assert GOLDEN_FILE.exists(), (
            f"Golden fixture missing at {GOLDEN_FILE}. Regenerate with "
            "scripts/regen_golden (see test_golden.generate_golden)."
        )

    def test_generation_matches_golden(self, contract_dir):
        """AT-005: deterministic generation reproduces the committed golden fixture."""
        generated = generate_golden(contract_dir)
        committed = [json.loads(line) for line in GOLDEN_FILE.read_text().splitlines() if line.strip()]
        assert generated == committed, (
            "Generated output drifted from the golden fixture. If this change is intended, "
            "regenerate the fixture and review the diff."
        )

    def test_golden_is_nonempty_and_correlated(self, contract_dir):
        generated = generate_golden(contract_dir)
        assert generated, "golden generation produced no signals"
        spans = [d for d in generated if d["signal_type"] == "span"]
        by_trace: dict[str, set[str]] = {}
        for s in spans:
            by_trace.setdefault(s["trace_id"], set()).add(s["service_name"])
        assert any(len(v) >= 2 for v in by_trace.values())
