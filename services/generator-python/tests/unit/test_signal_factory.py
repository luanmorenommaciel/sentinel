from __future__ import annotations

import random

import pytest

from otelgen.contract.models import ComponentSpec, ProviderProfile
from otelgen.model import LogSignal, MetricSignal, SpanSignal
from otelgen.scenarios.base import EmissionState
from otelgen.seeding import make_rng
from otelgen.signals.factory import SignalFactory

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

T_UNIX_NANO = 1_700_000_000_000_000_000
RUN_ID = "test-run-123"
SCENARIO_NAME = "baseline"


def _make_factory(rng: random.Random, profile: ProviderProfile) -> SignalFactory:
    return SignalFactory(
        provider_profile=profile,
        run_id=RUN_ID,
        scenario_name=SCENARIO_NAME,
        rng=rng,
    )


def _make_component(
    name: str = "orchestration.daily_etl",
    type_: str = "orchestration",
    service_name: str = "cloud-composer-etl",
    base_latency_ms: float = 250.0,
    error_ratio: float = 0.01,
) -> ComponentSpec:
    return ComponentSpec(
        name=name,
        type=type_,
        service_name=service_name,
        depends_on=[],
        base_rate=2.0,
        base_latency_ms=base_latency_ms,
        error_ratio=error_ratio,
    )


# ---------------------------------------------------------------------------
# Silenced state
# ---------------------------------------------------------------------------


class TestSilencedState:
    def test_silenced_state_yields_empty_list(self, rng: random.Random, provider_profile: ProviderProfile):
        factory = _make_factory(rng, provider_profile)
        component = _make_component()
        state = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=True)
        result = factory.build_for_component(component, T_UNIX_NANO, state)
        assert result == []


# ---------------------------------------------------------------------------
# Normal emission: correlated IDs + signal types
# ---------------------------------------------------------------------------


class TestNormalEmission:
    @pytest.fixture()
    def signals(self, rng: random.Random, provider_profile: ProviderProfile) -> list:
        factory = _make_factory(rng, provider_profile)
        component = _make_component()
        state = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False)
        return factory.build_for_component(component, T_UNIX_NANO, state)

    def test_has_exactly_one_span(self, signals: list):
        spans = [s for s in signals if isinstance(s, SpanSignal)]
        assert len(spans) == 1

    def test_has_exactly_one_log(self, signals: list):
        logs = [s for s in signals if isinstance(s, LogSignal)]
        assert len(logs) == 1

    def test_includes_generic_and_catalog_metrics(self, signals: list):
        # 2 generic operation metrics + the GCP catalog metrics for this component type.
        metrics = [s for s in signals if isinstance(s, MetricSignal)]
        assert len(metrics) >= 2
        names = {m.name for m in metrics}
        assert "operation.latency_ms" in names

    def test_includes_real_gcp_metric_descriptor(self, signals: list):
        """AT-004: at least one metric uses a real Cloud Monitoring descriptor name."""
        metric_names = {s.name for s in signals if isinstance(s, MetricSignal)}
        assert any(n.startswith("composer.googleapis.com/") for n in metric_names)

    def test_span_and_log_share_trace_id(self, signals: list):
        span = next(s for s in signals if isinstance(s, SpanSignal))
        log = next(s for s in signals if isinstance(s, LogSignal))
        assert span.trace_id == log.trace_id

    def test_span_and_log_share_span_id(self, signals: list):
        span = next(s for s in signals if isinstance(s, SpanSignal))
        log = next(s for s in signals if isinstance(s, LogSignal))
        assert span.span_id == log.span_id

    def test_span_end_after_start(self, signals: list):
        span = next(s for s in signals if isinstance(s, SpanSignal))
        assert span.end_unix_nano > span.start_unix_nano

    def test_span_name_matches_component_type(self, signals: list):
        span = next(s for s in signals if isinstance(s, SpanSignal))
        assert span.name == "orchestration.operation"


# ---------------------------------------------------------------------------
# sentinel.* resource attributes on every signal
# ---------------------------------------------------------------------------


class TestSentinelAttributes:
    @pytest.fixture()
    def signals(self, rng: random.Random, provider_profile: ProviderProfile) -> list:
        factory = _make_factory(rng, provider_profile)
        component = _make_component()
        state = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False)
        return factory.build_for_component(component, T_UNIX_NANO, state)

    def _resource_attrs(self, signal) -> dict:
        return signal.resource_attributes

    @pytest.mark.parametrize("idx", [0, 1, 2, 3])
    def test_sentinel_synthetic_true(self, signals: list, idx: int):
        attrs = self._resource_attrs(signals[idx])
        assert attrs.get("sentinel.synthetic") == "true"

    @pytest.mark.parametrize("idx", [0, 1, 2, 3])
    def test_sentinel_scenario_present(self, signals: list, idx: int):
        attrs = self._resource_attrs(signals[idx])
        assert attrs.get("sentinel.scenario") == SCENARIO_NAME

    @pytest.mark.parametrize("idx", [0, 1, 2, 3])
    def test_sentinel_run_id_present(self, signals: list, idx: int):
        attrs = self._resource_attrs(signals[idx])
        assert attrs.get("sentinel.run_id") == RUN_ID


# ---------------------------------------------------------------------------
# Provider profile resource attributes (GCP)
# ---------------------------------------------------------------------------


class TestProviderProfileAttrs:
    def test_cloud_provider_is_gcp(self, rng: random.Random, provider_profile: ProviderProfile):
        factory = _make_factory(rng, provider_profile)
        component = _make_component(type_="orchestration")
        state = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False)
        signals = factory.build_for_component(component, T_UNIX_NANO, state)
        for sig in signals:
            assert sig.resource_attributes.get("cloud.provider") == "gcp"

    def test_cloud_account_id_present(self, rng: random.Random, provider_profile: ProviderProfile):
        factory = _make_factory(rng, provider_profile)
        component = _make_component(type_="orchestration")
        state = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False)
        signals = factory.build_for_component(component, T_UNIX_NANO, state)
        for sig in signals:
            assert "cloud.account.id" in sig.resource_attributes

    def test_cloud_platform_present(self, rng: random.Random, provider_profile: ProviderProfile):
        factory = _make_factory(rng, provider_profile)
        component = _make_component(type_="orchestration")
        state = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False)
        signals = factory.build_for_component(component, T_UNIX_NANO, state)
        for sig in signals:
            assert sig.resource_attributes.get("cloud.platform") == "gcp_cloud_composer"


# ---------------------------------------------------------------------------
# Error state: error_ratio=1.0
# ---------------------------------------------------------------------------


class TestErrorState:
    @pytest.fixture()
    def signals(self, provider_profile: ProviderProfile) -> list:
        # Use a fixed rng that will always produce a value < 1.0 (any rng works since ratio=1.0)
        rng = make_rng(0)
        factory = _make_factory(rng, provider_profile)
        component = _make_component()
        state = EmissionState(error_ratio=1.0, latency_mult=1.0, silenced=False)
        return factory.build_for_component(component, T_UNIX_NANO, state)

    def test_span_status_is_error(self, signals: list):
        span = next(s for s in signals if isinstance(s, SpanSignal))
        assert span.status_code == "ERROR"

    def test_log_severity_is_error(self, signals: list):
        log = next(s for s in signals if isinstance(s, LogSignal))
        assert log.severity_text == "ERROR"
        assert log.severity_number == 17

    def test_span_attributes_contain_error_true(self, signals: list):
        span = next(s for s in signals if isinstance(s, SpanSignal))
        assert span.attributes.get("error") == "true"


# ---------------------------------------------------------------------------
# Latency multiplier effect
# ---------------------------------------------------------------------------


class TestLatencyMultiplier:
    def test_latency_mult_increases_span_duration(self, provider_profile: ProviderProfile):
        component = _make_component(base_latency_ms=100.0, error_ratio=0.0)

        rng1 = make_rng(99)
        factory1 = _make_factory(rng1, provider_profile)
        state1 = EmissionState(error_ratio=0.0, latency_mult=1.0, silenced=False)
        signals1 = factory1.build_for_component(component, T_UNIX_NANO, state1)
        span1 = next(s for s in signals1 if isinstance(s, SpanSignal))

        rng2 = make_rng(99)
        factory2 = _make_factory(rng2, provider_profile)
        state2 = EmissionState(error_ratio=0.0, latency_mult=4.0, silenced=False)
        signals2 = factory2.build_for_component(component, T_UNIX_NANO, state2)
        span2 = next(s for s in signals2 if isinstance(s, SpanSignal))

        duration1 = span1.end_unix_nano - span1.start_unix_nano
        duration2 = span2.end_unix_nano - span2.start_unix_nano
        assert duration2 > duration1
