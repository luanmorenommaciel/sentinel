from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def parse_duration(value: str) -> timedelta:
    """Parse a human duration string such as '6h', '30m', '10s', '1h30m' into a timedelta."""
    if isinstance(value, timedelta):
        return value
    m = _DURATION_RE.match(str(value).strip())
    if not m or not any(m.groups()):
        raise ValueError(
            f"Cannot parse duration {value!r}. Expected format like '6h', '30m', '10s', '1h30m'."
        )
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


# ---------------------------------------------------------------------------
# Versioned contract base — every top-level contract file carries a semver
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class VersionedContract(BaseModel):
    """Base for every top-level contract document. Enforces a semver `version`.

    Loading a contract file without a `version` field is a validation error
    (AT-006): the Pod 1 → Pod 2 handoff is explicitly versioned (meeting D8).
    """

    version: str = Field(description="Contract semantic version, e.g. '1.0.0'")

    @field_validator("version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"version must be semver 'X.Y.Z', got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Topology models
# ---------------------------------------------------------------------------


class ComponentSpec(BaseModel):
    name: str
    type: str
    service_name: str
    depends_on: list[str] = Field(default_factory=list)
    base_rate: float = Field(gt=0, description="Baseline events per second")
    base_latency_ms: float = Field(gt=0, description="Baseline latency in milliseconds")
    error_ratio: float = Field(ge=0.0, le=1.0, description="Baseline error rate [0,1]")


class TopologyConfig(VersionedContract):
    components: list[ComponentSpec]

    @model_validator(mode="after")
    def _unique_names(self) -> TopologyConfig:
        names = [c.name for c in self.components]
        if len(names) != len(set(names)):
            raise ValueError("Component names must be unique within a topology file.")
        return self

    @model_validator(mode="after")
    def _depends_on_exist(self) -> TopologyConfig:
        names = {c.name for c in self.components}
        for comp in self.components:
            for dep in comp.depends_on:
                if dep not in names:
                    raise ValueError(
                        f"Component '{comp.name}' depends_on '{dep}' which is not defined."
                    )
        return self


# ---------------------------------------------------------------------------
# Provider profile models — GCP-faithful resource attributes + metric catalog
# ---------------------------------------------------------------------------


class MetricDescriptor(BaseModel):
    """A real cloud-provider metric descriptor emitted for a component type."""

    name: str = Field(description="Provider metric descriptor, e.g. a Cloud Monitoring metric type")
    instrument: str = Field(description="OTel instrument kind: 'gauge' or 'sum'")
    unit: str = Field(default="", description="UCUM unit string, e.g. 's', 'By', '{request}'")

    @field_validator("instrument")
    @classmethod
    def _known_instrument(cls, v: str) -> str:
        if v not in {"gauge", "sum"}:
            raise ValueError(f"instrument must be 'gauge' or 'sum', got {v!r}")
        return v


class ComponentTypeProfile(BaseModel):
    """Resource attributes and metric descriptors for a single component type."""

    resource_attrs: dict[str, str] = Field(default_factory=dict)
    metrics: list[MetricDescriptor] = Field(default_factory=list)


class ProviderProfile(VersionedContract):
    """Provider emulation profile: global + per-component-type resource attributes
    (OTel/GCP resource-detector conventions) and a per-type metric descriptor catalog.
    """

    name: str
    resource_attrs: dict[str, str] = Field(
        default_factory=dict,
        description="Resource attributes applied to every signal (e.g. cloud.provider)",
    )
    component_types: dict[str, ComponentTypeProfile] = Field(
        default_factory=dict,
        description="Per-component-type resource attribute + metric overrides",
    )

    @property
    def cloud_provider(self) -> str:
        return self.resource_attrs.get("cloud.provider", "")

    def resource_attrs_for(self, component: ComponentSpec) -> dict[str, str]:
        attrs: dict[str, str] = {k: str(v) for k, v in self.resource_attrs.items()}
        ctp = self.component_types.get(component.type)
        if ctp is not None:
            attrs.update({k: str(v) for k, v in ctp.resource_attrs.items()})
        return attrs

    def metrics_for(self, component_type: str) -> list[MetricDescriptor]:
        ctp = self.component_types.get(component_type)
        return list(ctp.metrics) if ctp is not None else []


# ---------------------------------------------------------------------------
# Scenario / phase models
# ---------------------------------------------------------------------------


class PhaseSpec(BaseModel):
    type: str = Field(
        description="Injector type: failure_spike | latency_degradation | stalled_job | traffic_surge | pod_autoscale"
    )
    target: str = Field(description="Component name this phase targets")
    start_offset: timedelta
    duration: timedelta
    magnitude: float = Field(ge=0.0, description="Injector-specific intensity parameter")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Injector-specific extra parameters (e.g. baseline_replicas, peak_replicas)",
    )

    @field_validator("start_offset", "duration", mode="before")
    @classmethod
    def _parse_duration(cls, v: Any) -> timedelta:
        if isinstance(v, timedelta):
            return v
        return parse_duration(str(v))


class ScenarioConfig(VersionedContract):
    name: str
    extends: str | None = None
    phases: list[PhaseSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema / ClickHouse models
# ---------------------------------------------------------------------------


class TableSpec(BaseModel):
    name: str
    columns: dict[str, str] = Field(
        description="Mapping of canonical field name to ClickHouse column name"
    )

    @property
    def ordered_columns(self) -> list[str]:
        """Ordered list of ClickHouse column names (insertion order)."""
        return list(self.columns.values())

    def canonical_to_ch(self, canonical_field: str) -> str:
        """Return the ClickHouse column name for a given canonical field."""
        try:
            return self.columns[canonical_field]
        except KeyError as exc:
            raise KeyError(
                f"Canonical field '{canonical_field}' not found in table '{self.name}' mapping."
            ) from exc

    def ch_to_canonical(self, ch_column: str) -> str:
        """Reverse lookup: ClickHouse column name → canonical field name."""
        for canonical, ch in self.columns.items():
            if ch == ch_column:
                return canonical
        raise KeyError(
            f"ClickHouse column '{ch_column}' not found in table '{self.name}' mapping."
        )


class SchemaConfig(VersionedContract):
    batch_size: int = Field(gt=0, default=5000)
    tables: dict[str, TableSpec]

    @model_validator(mode="after")
    def _required_tables(self) -> SchemaConfig:
        required = {"logs", "traces", "metrics"}
        missing = required - set(self.tables.keys())
        if missing:
            raise ValueError(
                f"clickhouse_schema.yaml must define tables for: {sorted(missing)}"
            )
        return self
