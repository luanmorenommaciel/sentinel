from __future__ import annotations

from otelgen.contract.models import PhaseSpec
from otelgen.scenarios.base import EmissionState, register_injector


@register_injector("failure_spike")
class FailureSpikeInjector:
    """Raises the component error ratio to at least phase.magnitude during the active window."""

    def __init__(self, phase: PhaseSpec) -> None:
        self._phase = phase
        self._start_ns: int | None = None
        self._end_ns: int | None = None

    def bind_window(self, window_start_unix_nano: int) -> None:
        offset_ns = int(self._phase.start_offset.total_seconds() * 1_000_000_000)
        duration_ns = int(self._phase.duration.total_seconds() * 1_000_000_000)
        self._start_ns = window_start_unix_nano + offset_ns
        self._end_ns = self._start_ns + duration_ns

    def applies_at(self, t_unix_nano: int) -> bool:
        if self._start_ns is None or self._end_ns is None:
            return False
        return self._start_ns <= t_unix_nano < self._end_ns

    def apply(self, state: EmissionState) -> None:
        state.error_ratio = max(state.error_ratio, self._phase.magnitude)


@register_injector("latency_degradation")
class LatencyDegradationInjector:
    """Multiplies the component latency by phase.magnitude during the active window."""

    def __init__(self, phase: PhaseSpec) -> None:
        self._phase = phase
        self._start_ns: int | None = None
        self._end_ns: int | None = None

    def bind_window(self, window_start_unix_nano: int) -> None:
        offset_ns = int(self._phase.start_offset.total_seconds() * 1_000_000_000)
        duration_ns = int(self._phase.duration.total_seconds() * 1_000_000_000)
        self._start_ns = window_start_unix_nano + offset_ns
        self._end_ns = self._start_ns + duration_ns

    def applies_at(self, t_unix_nano: int) -> bool:
        if self._start_ns is None or self._end_ns is None:
            return False
        return self._start_ns <= t_unix_nano < self._end_ns

    def apply(self, state: EmissionState) -> None:
        state.latency_mult *= self._phase.magnitude


@register_injector("stalled_job")
class StalledJobInjector:
    """Silences the component (no signals emitted) during the active window."""

    def __init__(self, phase: PhaseSpec) -> None:
        self._phase = phase
        self._start_ns: int | None = None
        self._end_ns: int | None = None

    def bind_window(self, window_start_unix_nano: int) -> None:
        offset_ns = int(self._phase.start_offset.total_seconds() * 1_000_000_000)
        duration_ns = int(self._phase.duration.total_seconds() * 1_000_000_000)
        self._start_ns = window_start_unix_nano + offset_ns
        self._end_ns = self._start_ns + duration_ns

    def applies_at(self, t_unix_nano: int) -> bool:
        if self._start_ns is None or self._end_ns is None:
            return False
        return self._start_ns <= t_unix_nano < self._end_ns

    def apply(self, state: EmissionState) -> None:
        state.silenced = True


@register_injector("traffic_surge")
class TrafficSurgeInjector:
    """Multiplies the component emission volume by phase.magnitude during the active window."""

    def __init__(self, phase: PhaseSpec) -> None:
        self._phase = phase
        self._start_ns: int | None = None
        self._end_ns: int | None = None

    def bind_window(self, window_start_unix_nano: int) -> None:
        offset_ns = int(self._phase.start_offset.total_seconds() * 1_000_000_000)
        duration_ns = int(self._phase.duration.total_seconds() * 1_000_000_000)
        self._start_ns = window_start_unix_nano + offset_ns
        self._end_ns = self._start_ns + duration_ns

    def applies_at(self, t_unix_nano: int) -> bool:
        if self._start_ns is None or self._end_ns is None:
            return False
        return self._start_ns <= t_unix_nano < self._end_ns

    def apply(self, state: EmissionState) -> None:
        state.volume_mult *= self._phase.magnitude


@register_injector("pod_autoscale")
class PodAutoscaleInjector:
    """Ramps a replica/instance count from baseline to peak across the active window.

    Reads `params.baseline_replicas` and `params.peak_replicas`; sets
    `state.autoscale_replicas` to the linearly-interpolated value at the current tick.
    """

    def __init__(self, phase: PhaseSpec) -> None:
        self._phase = phase
        self._start_ns: int | None = None
        self._end_ns: int | None = None
        self._duration_ns: int = 1
        self._progress: float = 0.0
        params = phase.params or {}
        self._baseline = float(params.get("baseline_replicas", 1))
        self._peak = float(params.get("peak_replicas", 1))

    def bind_window(self, window_start_unix_nano: int) -> None:
        offset_ns = int(self._phase.start_offset.total_seconds() * 1_000_000_000)
        duration_ns = int(self._phase.duration.total_seconds() * 1_000_000_000)
        self._start_ns = window_start_unix_nano + offset_ns
        self._end_ns = self._start_ns + duration_ns
        self._duration_ns = max(1, duration_ns)

    def applies_at(self, t_unix_nano: int) -> bool:
        if self._start_ns is None or self._end_ns is None:
            return False
        active = self._start_ns <= t_unix_nano < self._end_ns
        if active:
            self._progress = (t_unix_nano - self._start_ns) / self._duration_ns
        return active

    def apply(self, state: EmissionState) -> None:
        state.autoscale_replicas = self._baseline + (self._peak - self._baseline) * self._progress


def injectors_for_phases(
    phases: list[PhaseSpec],
    window_start_unix_nano: int,
) -> dict[str, list]:
    """Build, bind, and group injectors by their target component name.

    Importing this module registers all three injector types as a side effect.
    The engine can iterate over each component's injectors and call applies_at/apply per tick.
    """
    from otelgen.scenarios.base import build_injector

    result: dict[str, list] = {}
    for phase in phases:
        injector = build_injector(phase)
        injector.bind_window(window_start_unix_nano)  # type: ignore[attr-defined]
        result.setdefault(phase.target, []).append(injector)
    return result
