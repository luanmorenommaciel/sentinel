from __future__ import annotations

import logging
import random
from collections.abc import Iterable, Iterator

from otelgen.contract.models import ScenarioConfig
from otelgen.model import Signal
from otelgen.scenarios.base import EmissionState
from otelgen.seeding import new_span_id, new_trace_id
from otelgen.signals.factory import SignalFactory
from otelgen.topology import Topology

log = logging.getLogger("otelgen.engine")

_CHILD_OFFSET_MAX_NS = 5_000_000  # up to 5ms between a parent span start and its child


class ScenarioEngine:
    """Orchestrates baseline + anomaly emission over a sequence of ticks.

    Per tick it computes a per-component EmissionState (applying injectors),
    derives an emission count from base_rate, applies the global --rate cap,
    then assembles one trace per pipeline run by linking each downstream event
    to a random upstream event emitted in the same tick.
    """

    def __init__(
        self,
        topology: Topology,
        scenario: ScenarioConfig,
        factory: SignalFactory,
        rng: random.Random,
        step_seconds: float = 10.0,
        rate: int = 0,
    ) -> None:
        self._topology = topology
        self._scenario = scenario
        self._factory = factory
        self._rng = rng
        self._step_s = step_seconds
        self._rate = rate

    def _emit_count(self, lam: float) -> int:
        """Round an expected-events value with fractional probability (deterministic via rng)."""
        base = int(lam)
        return base + (1 if self._rng.random() < (lam - base) else 0)

    def _child_offset_ns(self) -> int:
        return self._rng.randint(0, _CHILD_OFFSET_MAX_NS)

    def run(
        self,
        ticks: Iterable[int],
        window_start_unix_nano: int,
    ) -> Iterator[Signal]:
        import otelgen.scenarios.anomalies as _anomalies_mod  # noqa: F401 — registers injectors

        injectors_map = _anomalies_mod.injectors_for_phases(
            self._scenario.phases,
            window_start_unix_nano,
        )
        order = self._topology.topological_order()

        for t in ticks:
            # 1) Per-component emission state (injectors applied)
            states: dict[str, EmissionState] = {}
            counts: dict[str, int] = {}
            for node in order:
                spec = node.spec
                state = EmissionState(
                    error_ratio=spec.error_ratio,
                    latency_mult=1.0,
                    silenced=False,
                    volume_mult=1.0,
                    autoscale_replicas=None,
                )
                for injector in injectors_map.get(spec.name, []):
                    if injector.applies_at(t):
                        injector.apply(state)
                states[spec.name] = state
                lam = spec.base_rate * self._step_s * state.volume_mult
                counts[spec.name] = 0 if state.silenced else self._emit_count(lam)

            # 2) Global --rate cap (events/sec across all components)
            total = sum(counts.values())
            if self._rate and self._step_s > 0 and total > 0 and total / self._step_s > self._rate:
                scale = (self._rate * self._step_s) / total
                counts = {k: int(v * scale) for k, v in counts.items()}
                log.info("rate cap applied: scaled tick emissions by %.3f (rate=%d/s)", scale, self._rate)

            # 3) Build correlated traces: roots start new traces; downstream
            #    events link to a random upstream event emitted this tick.
            emitted: dict[str, list[tuple[str, str, int]]] = {}
            for node in order:
                spec = node.spec
                parent_pool = emitted.get(spec.depends_on[0]) if spec.depends_on else None
                buf: list[tuple[str, str, int]] = []
                for _ in range(counts[spec.name]):
                    if parent_pool:
                        p_trace_id, p_span_id, p_start = self._rng.choice(parent_pool)
                        trace_id = p_trace_id
                        parent_span_id: str | None = p_span_id
                        start = p_start + self._child_offset_ns()
                    else:
                        trace_id = new_trace_id(self._rng)
                        parent_span_id = None
                        start = t
                    span_id = new_span_id(self._rng)
                    yield from self._factory.build_event(
                        spec,
                        states[spec.name],
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        start_ns=start,
                    )
                    buf.append((trace_id, span_id, start))
                emitted[spec.name] = buf
