from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from otelgen.contract.models import PhaseSpec

# ---------------------------------------------------------------------------
# Emission state — mutable snapshot mutated by injectors each tick
# ---------------------------------------------------------------------------


@dataclass
class EmissionState:
    """Mutable per-tick emission parameters for a component.

    Anomaly injectors mutate these fields in place; the SignalFactory reads them
    to shape the signals it builds.
    """

    error_ratio: float  # current error rate [0.0, 1.0]
    latency_mult: float  # multiplier applied to base_latency_ms (1.0 = no change)
    silenced: bool  # when True the component emits no signals this tick
    volume_mult: float = 1.0  # multiplier on emission volume (traffic_surge)
    autoscale_replicas: float | None = None  # current replica count when pod_autoscale active


# ---------------------------------------------------------------------------
# Injector Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Injector(Protocol):
    """Interface every anomaly injector must satisfy."""

    def applies_at(self, t_unix_nano: int) -> bool:
        """Return True if this injector is active at the given timestamp."""
        ...

    def apply(self, state: EmissionState) -> None:
        """Mutate *state* to reflect this injector's effect."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_INJECTOR_REGISTRY: dict[str, type] = {}


def register_injector(type_name: str):
    """Class decorator that registers a concrete Injector under *type_name*.

    Usage::

        @register_injector("failure_spike")
        class FailureSpikeInjector:
            ...
    """

    def _decorator(cls: type) -> type:
        _INJECTOR_REGISTRY[type_name] = cls
        return cls

    return _decorator


def build_injector(phase_spec: PhaseSpec) -> Injector:
    """Instantiate and return the injector registered for *phase_spec.type*.

    Raises KeyError if the type is unknown.  Concrete injectors live in
    ``otelgen.scenarios.anomalies`` and must be imported before build_injector
    is called.
    """
    type_name = phase_spec.type
    try:
        cls = _INJECTOR_REGISTRY[type_name]
    except KeyError as exc:
        supported = sorted(_INJECTOR_REGISTRY.keys())
        raise KeyError(
            f"Unknown injector type '{type_name}'. "
            f"Supported types: {supported}. "
            "Ensure otelgen.scenarios.anomalies is imported before calling build_injector()."
        ) from exc
    return cls(phase_spec)
