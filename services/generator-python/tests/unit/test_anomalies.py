from __future__ import annotations

import pytest

from otelgen.contract.models import PhaseSpec
from otelgen.scenarios.anomalies import (
    FailureSpikeInjector,
    LatencyDegradationInjector,
    PodAutoscaleInjector,
    StalledJobInjector,
    TrafficSurgeInjector,
    injectors_for_phases,
)
from otelgen.scenarios.base import EmissionState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WINDOW_START = 1_700_000_000_000_000_000  # arbitrary fixed ns
ONE_HOUR_NS = 3_600_000_000_000


def _make_phase(
    type_: str,
    target: str = "orchestration.daily_etl",
    start_offset: str = "6h",
    duration: str = "30m",
    magnitude: float = 0.6,
) -> PhaseSpec:
    return PhaseSpec(
        type=type_,
        target=target,
        start_offset=start_offset,
        duration=duration,
        magnitude=magnitude,
    )


def _default_state(error_ratio: float = 0.01) -> EmissionState:
    return EmissionState(error_ratio=error_ratio, latency_mult=1.0, silenced=False)


# ---------------------------------------------------------------------------
# applies_at — before bind_window
# ---------------------------------------------------------------------------


class TestAppliesAtBeforeBind:
    def test_failure_spike_false_before_bind(self):
        phase = _make_phase("failure_spike")
        injector = FailureSpikeInjector(phase)
        assert injector.applies_at(WINDOW_START + ONE_HOUR_NS * 7) is False

    def test_latency_false_before_bind(self):
        phase = _make_phase("latency_degradation")
        injector = LatencyDegradationInjector(phase)
        assert injector.applies_at(WINDOW_START) is False

    def test_stalled_false_before_bind(self):
        phase = _make_phase("stalled_job")
        injector = StalledJobInjector(phase)
        assert injector.applies_at(WINDOW_START) is False


# ---------------------------------------------------------------------------
# FailureSpikeInjector
# ---------------------------------------------------------------------------


class TestFailureSpikeInjector:
    @pytest.fixture()
    def injector(self) -> FailureSpikeInjector:
        phase = _make_phase("failure_spike", start_offset="6h", duration="30m", magnitude=0.6)
        inj = FailureSpikeInjector(phase)
        inj.bind_window(WINDOW_START)
        return inj

    def test_applies_at_start_of_window(self, injector: FailureSpikeInjector):
        t_start = WINDOW_START + 6 * ONE_HOUR_NS
        assert injector.applies_at(t_start) is True

    def test_applies_at_inside_window(self, injector: FailureSpikeInjector):
        t_mid = WINDOW_START + 6 * ONE_HOUR_NS + 15 * 60 * 1_000_000_000
        assert injector.applies_at(t_mid) is True

    def test_does_not_apply_before_window(self, injector: FailureSpikeInjector):
        t_before = WINDOW_START + 5 * ONE_HOUR_NS
        assert injector.applies_at(t_before) is False

    def test_does_not_apply_after_window(self, injector: FailureSpikeInjector):
        # start_offset=6h + duration=30m → end at 6.5h
        t_after = WINDOW_START + 7 * ONE_HOUR_NS
        assert injector.applies_at(t_after) is False

    def test_apply_raises_error_ratio_to_magnitude(self, injector: FailureSpikeInjector):
        state = _default_state(error_ratio=0.01)
        injector.apply(state)
        assert state.error_ratio == pytest.approx(0.6)

    def test_apply_does_not_lower_existing_higher_ratio(self, injector: FailureSpikeInjector):
        # If error_ratio is already higher, apply should use max() — keep the higher value
        state = _default_state(error_ratio=0.9)
        injector.apply(state)
        assert state.error_ratio == pytest.approx(0.9)

    def test_apply_does_not_change_latency(self, injector: FailureSpikeInjector):
        state = _default_state()
        injector.apply(state)
        assert state.latency_mult == pytest.approx(1.0)

    def test_apply_does_not_silence(self, injector: FailureSpikeInjector):
        state = _default_state()
        injector.apply(state)
        assert state.silenced is False


# ---------------------------------------------------------------------------
# LatencyDegradationInjector
# ---------------------------------------------------------------------------


class TestLatencyDegradationInjector:
    @pytest.fixture()
    def injector(self) -> LatencyDegradationInjector:
        phase = _make_phase("latency_degradation", start_offset="8h", duration="1h", magnitude=4.0)
        inj = LatencyDegradationInjector(phase)
        inj.bind_window(WINDOW_START)
        return inj

    def test_applies_at_inside_window(self, injector: LatencyDegradationInjector):
        t = WINDOW_START + 8 * ONE_HOUR_NS + 30 * 60 * 1_000_000_000
        assert injector.applies_at(t) is True

    def test_does_not_apply_before_window(self, injector: LatencyDegradationInjector):
        t = WINDOW_START + 7 * ONE_HOUR_NS
        assert injector.applies_at(t) is False

    def test_does_not_apply_after_window(self, injector: LatencyDegradationInjector):
        # start_offset=8h + duration=1h → end at 9h
        t = WINDOW_START + 10 * ONE_HOUR_NS
        assert injector.applies_at(t) is False

    def test_apply_multiplies_latency(self, injector: LatencyDegradationInjector):
        state = _default_state()
        injector.apply(state)
        assert state.latency_mult == pytest.approx(4.0)

    def test_apply_stacks_latency_multipliers(self, injector: LatencyDegradationInjector):
        state = EmissionState(error_ratio=0.01, latency_mult=2.0, silenced=False)
        injector.apply(state)
        assert state.latency_mult == pytest.approx(8.0)

    def test_apply_does_not_change_error_ratio(self, injector: LatencyDegradationInjector):
        state = _default_state(error_ratio=0.05)
        injector.apply(state)
        assert state.error_ratio == pytest.approx(0.05)

    def test_apply_does_not_silence(self, injector: LatencyDegradationInjector):
        state = _default_state()
        injector.apply(state)
        assert state.silenced is False


# ---------------------------------------------------------------------------
# StalledJobInjector
# ---------------------------------------------------------------------------


class TestStalledJobInjector:
    @pytest.fixture()
    def injector(self) -> StalledJobInjector:
        phase = _make_phase("stalled_job", start_offset="12h", duration="45m", magnitude=1.0)
        inj = StalledJobInjector(phase)
        inj.bind_window(WINDOW_START)
        return inj

    def test_applies_at_inside_window(self, injector: StalledJobInjector):
        t = WINDOW_START + 12 * ONE_HOUR_NS + 20 * 60 * 1_000_000_000
        assert injector.applies_at(t) is True

    def test_does_not_apply_before_window(self, injector: StalledJobInjector):
        t = WINDOW_START + 11 * ONE_HOUR_NS
        assert injector.applies_at(t) is False

    def test_does_not_apply_after_window(self, injector: StalledJobInjector):
        # start_offset=12h + duration=45m → end at 12.75h
        t = WINDOW_START + 13 * ONE_HOUR_NS
        assert injector.applies_at(t) is False

    def test_apply_silences_emission(self, injector: StalledJobInjector):
        state = _default_state()
        injector.apply(state)
        assert state.silenced is True

    def test_apply_does_not_change_error_ratio(self, injector: StalledJobInjector):
        state = _default_state(error_ratio=0.05)
        injector.apply(state)
        assert state.error_ratio == pytest.approx(0.05)

    def test_apply_does_not_change_latency(self, injector: StalledJobInjector):
        state = _default_state()
        injector.apply(state)
        assert state.latency_mult == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# TrafficSurgeInjector
# ---------------------------------------------------------------------------


class TestTrafficSurgeInjector:
    @pytest.fixture()
    def injector(self) -> TrafficSurgeInjector:
        phase = _make_phase("traffic_surge", start_offset="6h", duration="1h", magnitude=5.0)
        inj = TrafficSurgeInjector(phase)
        inj.bind_window(WINDOW_START)
        return inj

    def test_applies_inside_window(self, injector: TrafficSurgeInjector):
        t = WINDOW_START + 6 * ONE_HOUR_NS + 10 * 60 * 1_000_000_000
        assert injector.applies_at(t) is True

    def test_apply_multiplies_volume(self, injector: TrafficSurgeInjector):
        state = _default_state()
        injector.apply(state)
        assert state.volume_mult == pytest.approx(5.0)

    def test_apply_stacks_volume(self, injector: TrafficSurgeInjector):
        state = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False, volume_mult=2.0)
        injector.apply(state)
        assert state.volume_mult == pytest.approx(10.0)

    def test_does_not_apply_after_window(self, injector: TrafficSurgeInjector):
        t = WINDOW_START + 8 * ONE_HOUR_NS
        assert injector.applies_at(t) is False


# ---------------------------------------------------------------------------
# PodAutoscaleInjector
# ---------------------------------------------------------------------------


class TestPodAutoscaleInjector:
    def _make_injector(self) -> PodAutoscaleInjector:
        phase = PhaseSpec(
            type="pod_autoscale",
            target="kubernetes.api_gateway",
            start_offset="6h",
            duration="1h",
            magnitude=1.0,
            params={"baseline_replicas": 30, "peak_replicas": 200},
        )
        inj = PodAutoscaleInjector(phase)
        inj.bind_window(WINDOW_START)
        return inj

    def test_replicas_at_start_equal_baseline(self):
        inj = self._make_injector()
        state = _default_state()
        t_start = WINDOW_START + 6 * ONE_HOUR_NS
        assert inj.applies_at(t_start)
        inj.apply(state)
        assert state.autoscale_replicas == pytest.approx(30.0, abs=0.5)

    def test_replicas_ramp_toward_peak(self):
        inj = self._make_injector()
        state = _default_state()
        # ~halfway through the 1h window
        t_mid = WINDOW_START + 6 * ONE_HOUR_NS + 30 * 60 * 1_000_000_000
        assert inj.applies_at(t_mid)
        inj.apply(state)
        # halfway between 30 and 200 ≈ 115
        assert 100.0 < state.autoscale_replicas < 130.0

    def test_does_not_apply_outside_window(self):
        inj = self._make_injector()
        t_before = WINDOW_START + 5 * ONE_HOUR_NS
        assert inj.applies_at(t_before) is False


# ---------------------------------------------------------------------------
# injectors_for_phases — grouping by target
# ---------------------------------------------------------------------------


class TestInjectorsForPhases:
    def test_groups_by_target(self):
        phases = [
            _make_phase("failure_spike", target="orchestration.daily_etl", start_offset="6h", duration="30m"),
            _make_phase(
                "latency_degradation", target="compute.spark_batch", start_offset="8h", duration="1h", magnitude=4.0
            ),
            _make_phase("stalled_job", target="orchestration.daily_etl", start_offset="12h", duration="45m"),
        ]
        result = injectors_for_phases(phases, WINDOW_START)
        assert set(result.keys()) == {"orchestration.daily_etl", "compute.spark_batch"}
        assert len(result["orchestration.daily_etl"]) == 2
        assert len(result["compute.spark_batch"]) == 1

    def test_injectors_are_bound(self):
        phases = [
            _make_phase("failure_spike", start_offset="6h", duration="30m"),
        ]
        result = injectors_for_phases(phases, WINDOW_START)
        inj = result["orchestration.daily_etl"][0]
        # After bind, applies_at inside the window should be True
        t = WINDOW_START + 6 * ONE_HOUR_NS + 60_000_000_000
        assert inj.applies_at(t) is True

    def test_empty_phases_returns_empty_dict(self):
        result = injectors_for_phases([], WINDOW_START)
        assert result == {}

    def test_returns_correct_injector_types(self):
        phases = [
            _make_phase("failure_spike", target="a", start_offset="1h", duration="30m"),
            _make_phase("latency_degradation", target="b", start_offset="2h", duration="30m", magnitude=2.0),
            _make_phase("stalled_job", target="c", start_offset="3h", duration="30m"),
        ]
        result = injectors_for_phases(phases, WINDOW_START)
        assert isinstance(result["a"][0], FailureSpikeInjector)
        assert isinstance(result["b"][0], LatencyDegradationInjector)
        assert isinstance(result["c"][0], StalledJobInjector)
