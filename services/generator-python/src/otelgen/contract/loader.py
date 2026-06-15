from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from otelgen.contract.models import (
    ProviderProfile,
    ScenarioConfig,
    SchemaConfig,
    TopologyConfig,
)


class ContractError(Exception):
    """Raised when a contract YAML file fails to load or validate."""


@dataclass(frozen=True)
class ContractBundle:
    topology: TopologyConfig
    scenario: ScenarioConfig
    provider_profile: ProviderProfile
    schema: SchemaConfig


def _load_yaml(path: Path) -> dict:
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise ContractError(f"Contract file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ContractError(f"YAML parse error in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"Expected a YAML mapping at the top level of {path}, got {type(data).__name__}.")
    return data


def _validate(model_cls, data: dict, path: Path):
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        field_errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ContractError(
            f"Validation failed in {path} — {field_errors}"
        ) from exc


def _resolve_scenario(
    base_scenario: ScenarioConfig,
    baseline_scenario: ScenarioConfig | None,
) -> ScenarioConfig:
    """If the scenario extends another, merge phases (baseline first, then overrides)."""
    if base_scenario.extends is None or baseline_scenario is None:
        return base_scenario
    merged_phases = baseline_scenario.phases + base_scenario.phases
    return ScenarioConfig(
        version=base_scenario.version,
        name=base_scenario.name,
        extends=base_scenario.extends,
        phases=merged_phases,
    )


def load_contract(
    contract_dir: str | Path,
    scenario_name: str = "baseline",
    provider_name: str = "gcp",
) -> ContractBundle:
    """Load and validate all contract YAML files; return a fully-resolved ContractBundle.

    Raises ContractError on any missing file, YAML error, or validation failure.
    """
    root = Path(contract_dir)

    # Topology — load default.yaml (the canonical topology file)
    topology_path = root / "topology" / "default.yaml"
    topology_data = _load_yaml(topology_path)
    topology = _validate(TopologyConfig, topology_data, topology_path)

    # Scenario — load the requested scenario; resolve extends: baseline
    scenario_path = root / "scenarios" / f"{scenario_name}.yaml"
    scenario_data = _load_yaml(scenario_path)
    scenario = _validate(ScenarioConfig, scenario_data, scenario_path)

    baseline_scenario: ScenarioConfig | None = None
    if scenario.extends is not None:
        baseline_path = root / "scenarios" / f"{scenario.extends}.yaml"
        baseline_data = _load_yaml(baseline_path)
        baseline_scenario = _validate(ScenarioConfig, baseline_data, baseline_path)

    resolved_scenario = _resolve_scenario(scenario, baseline_scenario)

    # Cross-validate: every anomaly phase target must be a known topology component
    known_components = {c.name for c in topology.components}
    for phase in resolved_scenario.phases:
        if phase.target not in known_components:
            raise ContractError(
                f"Scenario '{resolved_scenario.name}': phase target '{phase.target}' "
                f"is not a topology component. Known components: {sorted(known_components)}"
            )

    # Provider profile
    provider_path = root / "provider_profiles" / f"{provider_name}.yaml"
    provider_data = _load_yaml(provider_path)
    provider_profile = _validate(ProviderProfile, provider_data, provider_path)

    # ClickHouse schema
    schema_path = root / "clickhouse_schema.yaml"
    schema_data = _load_yaml(schema_path)
    schema = _validate(SchemaConfig, schema_data, schema_path)

    return ContractBundle(
        topology=topology,
        scenario=resolved_scenario,
        provider_profile=provider_profile,
        schema=schema,
    )
