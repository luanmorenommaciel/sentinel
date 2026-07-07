from __future__ import annotations

import random
from pathlib import Path

from otelgen.seeding import make_rng, new_span_id, new_trace_id

# ---------------------------------------------------------------------------
# make_rng determinism
# ---------------------------------------------------------------------------


class TestMakeRng:
    def test_returns_random_instance(self):
        rng = make_rng(42)
        assert isinstance(rng, random.Random)

    def test_same_seed_same_sequence(self):
        rng1 = make_rng(42)
        rng2 = make_rng(42)
        seq1 = [rng1.random() for _ in range(20)]
        seq2 = [rng2.random() for _ in range(20)]
        assert seq1 == seq2

    def test_different_seed_different_sequence(self):
        rng1 = make_rng(1)
        rng2 = make_rng(2)
        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]
        assert seq1 != seq2

    def test_instances_are_isolated(self):
        """Consuming from one RNG must not affect another."""
        rng1 = make_rng(7)
        rng2 = make_rng(7)
        # Drain rng1
        for _ in range(50):
            rng1.random()
        # rng2 should produce same first value as the original rng1 before draining
        rng_check = make_rng(7)
        assert rng2.random() == rng_check.random()


# ---------------------------------------------------------------------------
# new_trace_id
# ---------------------------------------------------------------------------


class TestNewTraceId:
    def test_length_is_32(self):
        rng = make_rng(0)
        tid = new_trace_id(rng)
        assert len(tid) == 32

    def test_is_hex(self):
        rng = make_rng(0)
        tid = new_trace_id(rng)
        int(tid, 16)  # should not raise

    def test_lowercase_hex(self):
        rng = make_rng(0)
        tid = new_trace_id(rng)
        assert tid == tid.lower()

    def test_deterministic_with_same_seed(self):
        rng1 = make_rng(123)
        rng2 = make_rng(123)
        assert new_trace_id(rng1) == new_trace_id(rng2)

    def test_different_calls_produce_different_ids(self):
        rng = make_rng(0)
        ids = {new_trace_id(rng) for _ in range(20)}
        assert len(ids) == 20


# ---------------------------------------------------------------------------
# new_span_id
# ---------------------------------------------------------------------------


class TestNewSpanId:
    def test_length_is_16(self):
        rng = make_rng(0)
        sid = new_span_id(rng)
        assert len(sid) == 16

    def test_is_hex(self):
        rng = make_rng(0)
        sid = new_span_id(rng)
        int(sid, 16)  # should not raise

    def test_lowercase_hex(self):
        rng = make_rng(0)
        sid = new_span_id(rng)
        assert sid == sid.lower()

    def test_deterministic_with_same_seed(self):
        rng1 = make_rng(55)
        rng2 = make_rng(55)
        assert new_span_id(rng1) == new_span_id(rng2)

    def test_different_calls_produce_different_ids(self):
        rng = make_rng(0)
        ids = {new_span_id(rng) for _ in range(20)}
        assert len(ids) == 20


# ---------------------------------------------------------------------------
# Engine reproducibility: same seed → same output
# ---------------------------------------------------------------------------


class TestEngineReproducibility:
    """AT-008: Two runs with identical config + fixed seed produce equivalent datasets."""

    def _run_engine(self, contract_dir: Path, seed: int) -> list:
        from datetime import datetime, timedelta, timezone

        from otelgen.contract.loader import load_contract
        from otelgen.scenarios.engine import ScenarioEngine
        from otelgen.seeding import make_rng
        from otelgen.signals.factory import SignalFactory
        from otelgen.topology import Topology

        bundle = load_contract(contract_dir, scenario_name="baseline")
        rng = make_rng(seed)

        factory = SignalFactory(
            provider_profile=bundle.provider_profile,
            run_id="reproducibility-test",
            scenario_name=bundle.scenario.name,
            rng=rng,
        )
        topology = Topology(bundle.topology)
        engine = ScenarioEngine(topology=topology, scenario=bundle.scenario, factory=factory, rng=rng)

        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        window_start = int((now - timedelta(hours=1)).timestamp() * 1e9)
        # Only 5 ticks to keep the test fast
        ticks = [window_start + i * 10_000_000_000 for i in range(5)]

        return list(engine.run(ticks, window_start))

    def test_same_seed_same_signal_count(self, contract_dir: Path):
        signals_a = self._run_engine(contract_dir, seed=42)
        signals_b = self._run_engine(contract_dir, seed=42)
        assert len(signals_a) == len(signals_b)

    def test_same_seed_same_first_span_trace_id(self, contract_dir: Path):
        from otelgen.model import SpanSignal

        signals_a = self._run_engine(contract_dir, seed=42)
        signals_b = self._run_engine(contract_dir, seed=42)

        spans_a = [s for s in signals_a if isinstance(s, SpanSignal)]
        spans_b = [s for s in signals_b if isinstance(s, SpanSignal)]

        assert len(spans_a) > 0, "Expected at least one span"
        assert spans_a[0].trace_id == spans_b[0].trace_id

    def test_different_seed_different_first_span_trace_id(self, contract_dir: Path):
        from otelgen.model import SpanSignal

        signals_a = self._run_engine(contract_dir, seed=1)
        signals_b = self._run_engine(contract_dir, seed=2)

        spans_a = [s for s in signals_a if isinstance(s, SpanSignal)]
        spans_b = [s for s in signals_b if isinstance(s, SpanSignal)]

        if spans_a and spans_b:
            assert spans_a[0].trace_id != spans_b[0].trace_id
