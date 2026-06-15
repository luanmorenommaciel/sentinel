from __future__ import annotations

import random

from otelgen.contract.models import ComponentSpec, MetricDescriptor, ProviderProfile
from otelgen.model import LogSignal, MetricSignal, Signal, SpanSignal
from otelgen.scenarios.base import EmissionState
from otelgen.seeding import new_span_id, new_trace_id

_MS_TO_NS = 1_000_000

_AUTOSCALE_METRIC = "k8s.deployment.available_replicas"

_LOG_BODIES_OK = [
    "Request completed successfully.",
    "Processed batch without errors.",
    "Operation finished within SLA.",
    "Response dispatched to downstream.",
    "Job step completed.",
]

_LOG_BODIES_ERR = [
    "Request failed: upstream returned error.",
    "Operation timed out after retries exhausted.",
    "Unhandled exception during processing.",
    "Circuit breaker open: too many failures.",
    "Batch aborted due to downstream rejection.",
]


def base_resource_attrs(
    component: ComponentSpec,
    profile: ProviderProfile,
    run_id: str,
    scenario_name: str,
) -> dict[str, str]:
    return {
        **profile.resource_attrs_for(component),
        "service.name": component.service_name,
        "sentinel.synthetic": "true",
        "sentinel.scenario": scenario_name,
        "sentinel.run_id": run_id,
    }


class SignalFactory:
    def __init__(
        self,
        provider_profile: ProviderProfile,
        run_id: str,
        scenario_name: str,
        rng: random.Random,
    ) -> None:
        self._profile = provider_profile
        self._run_id = run_id
        self._scenario_name = scenario_name
        self._rng = rng

    def build_event(
        self,
        component_spec: ComponentSpec,
        state: EmissionState,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        start_ns: int,
    ) -> list[Signal]:
        """Build one correlated event-set (span + log + metrics) for a component.

        The trace context (trace_id/span_id/parent_span_id) is supplied by the
        caller (ScenarioEngine), which assembles one trace per pipeline run.
        """
        if state.silenced:
            return []

        rng = self._rng
        is_error = rng.random() < state.error_ratio

        resource_attrs = base_resource_attrs(
            component_spec,
            self._profile,
            self._run_id,
            self._scenario_name,
        )

        # Latency with jitter (±10%)
        base_latency_ns = int(component_spec.base_latency_ms * state.latency_mult * _MS_TO_NS)
        jitter = rng.uniform(-0.1, 0.1)
        latency_ns = max(1, int(base_latency_ns * (1.0 + jitter)))

        span_name = f"{component_spec.type}.operation"
        span_attrs: dict[str, str] = {
            "component.name": component_spec.name,
            "component.type": component_spec.type,
        }
        if is_error:
            span_attrs["error"] = "true"

        span = SpanSignal(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=span_name,
            service_name=component_spec.service_name,
            start_unix_nano=start_ns,
            end_unix_nano=start_ns + latency_ns,
            status_code="ERROR" if is_error else "OK",
            attributes=span_attrs,
            resource_attributes=resource_attrs,
        )

        body_pool = _LOG_BODIES_ERR if is_error else _LOG_BODIES_OK
        log_body = body_pool[rng.randrange(len(body_pool))]
        log = LogSignal(
            time_unix_nano=start_ns,
            severity_text="ERROR" if is_error else "INFO",
            severity_number=17 if is_error else 9,
            service_name=component_spec.service_name,
            body=log_body,
            trace_id=trace_id,
            span_id=span_id,
            attributes={"component.name": component_spec.name},
            resource_attributes=resource_attrs,
        )

        latency_ms_value = latency_ns / _MS_TO_NS
        metric_latency = MetricSignal(
            time_unix_nano=start_ns,
            name="operation.latency_ms",
            type="gauge",
            value=round(latency_ms_value, 3),
            service_name=component_spec.service_name,
            attributes={"component.name": component_spec.name, "component.type": component_spec.type},
            resource_attributes=resource_attrs,
        )

        metric_requests = MetricSignal(
            time_unix_nano=start_ns,
            name="operation.error_count" if is_error else "operation.request_count",
            type="sum",
            value=1.0,
            service_name=component_spec.service_name,
            attributes={
                "component.name": component_spec.name,
                "status": "error" if is_error else "ok",
            },
            resource_attributes=resource_attrs,
        )

        signals: list[Signal] = [span, log, metric_latency, metric_requests]

        # Real provider metric descriptors for this component type (GCP fidelity).
        for descriptor in self._profile.metrics_for(component_spec.type):
            signals.append(
                self._catalog_metric(descriptor, component_spec, start_ns, resource_attrs)
            )

        # Pod autoscale: emit the ramped replica-count gauge.
        if state.autoscale_replicas is not None:
            signals.append(
                MetricSignal(
                    time_unix_nano=start_ns,
                    name=_AUTOSCALE_METRIC,
                    type="gauge",
                    value=round(state.autoscale_replicas, 1),
                    service_name=component_spec.service_name,
                    attributes={"component.name": component_spec.name, "component.type": component_spec.type},
                    resource_attributes=resource_attrs,
                )
            )

        return signals

    def _catalog_metric(
        self,
        descriptor: MetricDescriptor,
        component_spec: ComponentSpec,
        start_ns: int,
        resource_attrs: dict[str, str],
    ) -> MetricSignal:
        if descriptor.instrument == "sum":
            value = float(self._rng.randint(1, 50))
        else:
            value = round(self._rng.uniform(0.0, 100.0), 3)
        return MetricSignal(
            time_unix_nano=start_ns,
            name=descriptor.name,
            type=descriptor.instrument,
            value=value,
            service_name=component_spec.service_name,
            attributes={
                "component.name": component_spec.name,
                "component.type": component_spec.type,
                "unit": descriptor.unit,
            },
            resource_attributes=resource_attrs,
        )

    def build_for_component(
        self,
        component_spec: ComponentSpec,
        t_unix_nano: int,
        state: EmissionState,
    ) -> list[Signal]:
        """Backward-compatible single-event builder.

        Mints a fresh root trace context and delegates to build_event. The
        ScenarioEngine uses build_event directly to assemble correlated traces.
        """
        if state.silenced:
            return []
        return self.build_event(
            component_spec,
            state,
            trace_id=new_trace_id(self._rng),
            span_id=new_span_id(self._rng),
            parent_span_id=None,
            start_ns=t_unix_nano,
        )
