from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from otelgen.config import RunConfig

from otelgen.model import LogSignal, MetricSignal, SpanSignal

Signal = LogSignal | MetricSignal | SpanSignal


class Exporter(ABC):
    """Abstract base for all signal exporters."""

    @abstractmethod
    def export(self, signals: Iterable[Signal]) -> None:
        """Write a batch of canonical signals to the delivery target."""

    @abstractmethod
    def flush(self) -> None:
        """Flush any in-memory buffers to the delivery target."""

    def close(self) -> None:
        """Flush and release resources. Override if teardown is needed."""
        self.flush()


def build_exporter(cfg: RunConfig, schema=None) -> Exporter:
    """Factory: return the correct Exporter for the delivery mode in cfg.

    Imports of OTLPExporter and ClickHouseExporter are deferred so this module
    loads cleanly even when opentelemetry or clickhouse-connect are absent.

    Args:
        cfg:    RunConfig with delivery mode, endpoints, and connection settings.
        schema: SchemaConfig (parsed clickhouse_schema.yaml) — required when
                cfg.delivery == "direct".  Loaded by the caller from the
                ContractBundle so that RunConfig does not need to carry it.
    """
    if cfg.delivery == "otlp":
        from otelgen.exporters.otlp import OTLPExporter  # noqa: PLC0415

        return OTLPExporter(
            endpoint=cfg.otlp_endpoint,
            protocol=cfg.otlp_protocol,
            headers=cfg.otlp_headers or None,
            insecure=cfg.otlp_insecure,
        )
    if cfg.delivery == "direct":
        from otelgen.exporters.clickhouse import ClickHouseExporter  # noqa: PLC0415

        if schema is None:
            raise ValueError(
                "schema (SchemaConfig) must be provided when delivery='direct'. "
                "Pass bundle.schema from the loaded ContractBundle."
            )
        return ClickHouseExporter(conn=cfg.clickhouse, schema=schema)
    raise ValueError(f"Unknown delivery mode: {cfg.delivery!r}")
