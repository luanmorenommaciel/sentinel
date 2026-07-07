from __future__ import annotations

from datetime import timedelta

from otelgen.contract.loader import load_contract
from otelgen.model import SpanSignal
from otelgen.runmode import backfill_ticks
from otelgen.scenarios.engine import ScenarioEngine
from otelgen.seeding import make_rng
from otelgen.signals.factory import SignalFactory
from otelgen.topology import Topology

WINDOW_START = 1_700_000_000_000_000_000


def _engine(contract_dir, *, step_seconds: float, rate: int, seed: int = 7, scenario="baseline"):
    bundle = load_contract(contract_dir, scenario_name=scenario, provider_name="gcp")
    rng = make_rng(seed)
    factory = SignalFactory(
        provider_profile=bundle.provider_profile,
        run_id="vol-test",
        scenario_name=bundle.scenario.name,
        rng=rng,
    )
    topology = Topology(bundle.topology)
    return ScenarioEngine(
        topology=topology,
        scenario=bundle.scenario,
        factory=factory,
        rng=rng,
        step_seconds=step_seconds,
        rate=rate,
    )


def _spans(engine, *, window_s: int, step_s: int) -> list[SpanSignal]:
    ticks = backfill_ticks(window=timedelta(seconds=window_s), step=timedelta(seconds=step_s))
    return [s for s in engine.run(ticks, WINDOW_START) if isinstance(s, SpanSignal)]


class TestVolumeScalesWithRate:
    """AT-009: signal volume is proportional to base_rate * step (and capped by --rate)."""

    def test_doubling_step_roughly_doubles_volume(self, contract_dir):
        eng1 = _engine(contract_dir, step_seconds=1.0, rate=0, seed=11)
        eng2 = _engine(contract_dir, step_seconds=2.0, rate=0, seed=11)
        # Same wall-clock window (60s); step=2 → half the ticks but 2x events/tick → ~equal,
        # so instead hold tick-count equal and compare per-tick volume by using same #ticks.
        n1 = len(_spans(eng1, window_s=60, step_s=1))   # 60 ticks @ step 1s
        n2 = len(_spans(eng2, window_s=120, step_s=2))  # 60 ticks @ step 2s
        # 60 ticks each; eng2 emits ~2x per tick (lam ∝ step)
        assert n2 > n1 * 1.5

    def test_rate_cap_reduces_volume(self, contract_dir):
        uncapped = _engine(contract_dir, step_seconds=1.0, rate=0, seed=5)
        capped = _engine(contract_dir, step_seconds=1.0, rate=10, seed=5)
        n_uncapped = len(_spans(uncapped, window_s=30, step_s=1))
        n_capped = len(_spans(capped, window_s=30, step_s=1))
        assert n_capped < n_uncapped

    def test_rate_cap_bounds_throughput(self, contract_dir):
        # With rate=5/s over a 20s window, span throughput should not greatly exceed the cap.
        capped = _engine(contract_dir, step_seconds=1.0, rate=5, seed=5)
        spans = _spans(capped, window_s=20, step_s=1)
        # spans are one component-event each; total events capped at ~rate*window across all signals,
        # so spans (a subset of events) must be under that ceiling.
        assert len(spans) <= 5 * 20


class TestTraceCorrelation:
    """AT-008: one trace per pipeline run, root-anchored; a trace spans >= 2 components."""

    def _run_spans(self, contract_dir) -> list[SpanSignal]:
        eng = _engine(contract_dir, step_seconds=1.0, rate=0, seed=3)
        return _spans(eng, window_s=10, step_s=1)

    def test_a_trace_spans_multiple_components(self, contract_dir):
        spans = self._run_spans(contract_dir)
        by_trace: dict[str, set[str]] = {}
        for s in spans:
            by_trace.setdefault(s.trace_id, set()).add(s.service_name)
        assert any(len(services) >= 2 for services in by_trace.values()), (
            "expected at least one trace spanning >=2 components"
        )

    def test_child_spans_reference_a_parent_in_same_trace(self, contract_dir):
        spans = self._run_spans(contract_dir)
        span_index = {(s.trace_id, s.span_id): s for s in spans}
        children = [s for s in spans if s.parent_span_id is not None]
        assert children, "expected some child spans"
        for child in children:
            assert (child.trace_id, child.parent_span_id) in span_index

    def test_root_component_spans_have_no_parent(self, contract_dir):
        # messaging.ingestion_topic and orchestration.daily_etl are roots (no depends_on).
        spans = self._run_spans(contract_dir)
        roots = {"pubsub-ingestion-topic", "cloud-composer-etl"}
        root_spans = [s for s in spans if s.service_name in roots]
        assert root_spans
        assert all(s.parent_span_id is None for s in root_spans)


class TestSilencedVolume:
    def test_stalled_job_silences_target_in_window(self, contract_dir):
        # stalled_job silences orchestration.daily_etl from 12h for 45m.
        # Explicit ticks aligned to WINDOW_START so the injector binding matches.
        eng = _engine(contract_dir, step_seconds=1.0, rate=0, seed=1, scenario="stalled_job")
        hour_ns = 3_600_000_000_000
        ticks = [WINDOW_START + h * hour_ns for h in range(14)]  # hourly ticks across 14h
        spans = [s for s in eng.run(ticks, WINDOW_START) if isinstance(s, SpanSignal)]

        etl = [s for s in spans if s.service_name == "cloud-composer-etl"]
        stall_start = WINDOW_START + 12 * hour_ns
        stall_end = stall_start + 45 * 60 * 1_000_000_000

        in_window = [s for s in etl if stall_start <= s.start_unix_nano < stall_end]
        outside = [s for s in etl if s.start_unix_nano < stall_start]
        assert in_window == [], "etl must emit nothing during the stall window"
        assert outside, "etl must still emit outside the stall window"
