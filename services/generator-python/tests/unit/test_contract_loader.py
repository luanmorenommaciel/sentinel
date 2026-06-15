from __future__ import annotations

import textwrap
from datetime import timedelta
from pathlib import Path

import pytest

from otelgen.contract.loader import ContractError, load_contract
from otelgen.contract.models import (
    parse_duration,
)

# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------


class TestParseDuration:
    def test_hours_only(self):
        assert parse_duration("6h") == timedelta(hours=6)

    def test_minutes_only(self):
        assert parse_duration("30m") == timedelta(minutes=30)

    def test_seconds_only(self):
        assert parse_duration("10s") == timedelta(seconds=10)

    def test_hours_and_minutes(self):
        assert parse_duration("1h30m") == timedelta(hours=1, minutes=30)

    def test_hours_minutes_seconds(self):
        assert parse_duration("2h15m45s") == timedelta(hours=2, minutes=15, seconds=45)

    def test_timedelta_passthrough(self):
        td = timedelta(hours=3)
        assert parse_duration(td) == td

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Cannot parse duration"):
            parse_duration("bad")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Cannot parse duration"):
            parse_duration("")


# ---------------------------------------------------------------------------
# Happy path: all four scenarios
# ---------------------------------------------------------------------------


class TestLoadContractValid:
    def test_baseline_loads(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="baseline")
        assert bundle.scenario.name == "baseline"
        assert bundle.scenario.phases == []

    def test_failure_spike_loads(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="failure_spike")
        assert bundle.scenario.name == "failure_spike"
        # One phase from the scenario itself
        phase_types = [p.type for p in bundle.scenario.phases]
        assert "failure_spike" in phase_types

    def test_latency_degradation_loads(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="latency_degradation")
        assert bundle.scenario.name == "latency_degradation"
        phase_types = [p.type for p in bundle.scenario.phases]
        assert "latency_degradation" in phase_types

    def test_stalled_job_loads(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="stalled_job")
        assert bundle.scenario.name == "stalled_job"
        phase_types = [p.type for p in bundle.scenario.phases]
        assert "stalled_job" in phase_types

    def test_topology_has_7_components(self, contract_dir: Path):
        bundle = load_contract(contract_dir)
        assert len(bundle.topology.components) == 7

    def test_topology_contains_expected_components(self, contract_dir: Path):
        bundle = load_contract(contract_dir)
        names = {c.name for c in bundle.topology.components}
        assert "orchestration.daily_etl" in names
        assert "compute.spark_batch" in names

    def test_provider_profile_is_gcp(self, contract_dir: Path):
        bundle = load_contract(contract_dir)
        assert bundle.provider_profile.cloud_provider == "gcp"

    def test_schema_has_three_tables(self, contract_dir: Path):
        bundle = load_contract(contract_dir)
        assert set(bundle.schema.tables.keys()) == {"logs", "traces", "metrics"}


# ---------------------------------------------------------------------------
# extends: baseline resolution
# ---------------------------------------------------------------------------


class TestExtendsResolution:
    def test_failure_spike_extends_baseline(self, contract_dir: Path):
        """After resolution the scenario has both baseline phases (0) + its own."""
        bundle = load_contract(contract_dir, scenario_name="failure_spike")
        # baseline has 0 phases; failure_spike adds 1 phase
        assert len(bundle.scenario.phases) == 1
        assert bundle.scenario.phases[0].type == "failure_spike"

    def test_failure_spike_phase_magnitude(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="failure_spike")
        phase = bundle.scenario.phases[0]
        assert phase.magnitude == pytest.approx(0.6)

    def test_failure_spike_phase_start_offset(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="failure_spike")
        phase = bundle.scenario.phases[0]
        assert phase.start_offset == timedelta(hours=6)

    def test_failure_spike_phase_duration(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="failure_spike")
        phase = bundle.scenario.phases[0]
        assert phase.duration == timedelta(minutes=30)

    def test_latency_degradation_phase_start_offset(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="latency_degradation")
        phase = bundle.scenario.phases[0]
        assert phase.start_offset == timedelta(hours=8)
        assert phase.duration == timedelta(hours=1)

    def test_stalled_job_phase_start_offset(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="stalled_job")
        phase = bundle.scenario.phases[0]
        assert phase.start_offset == timedelta(hours=12)
        assert phase.duration == timedelta(minutes=45)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestContractErrors:
    def test_missing_file_raises_contract_error(self, tmp_path: Path):
        with pytest.raises(ContractError, match="Contract file not found"):
            load_contract(tmp_path / "nonexistent", scenario_name="baseline")

    def test_malformed_yaml_raises_contract_error(self, tmp_path: Path, contract_dir: Path):
        """Write a bad YAML file over the topology and expect ContractError."""
        import shutil

        # Copy real contract dir
        bad_dir = tmp_path / "contract"
        shutil.copytree(contract_dir, bad_dir)

        bad_topo = bad_dir / "topology" / "default.yaml"
        bad_topo.write_text(": bad: yaml: [unterminated")

        with pytest.raises(ContractError, match="YAML parse error"):
            load_contract(bad_dir, scenario_name="baseline")

    def test_missing_scenario_file_raises_contract_error(self, tmp_path: Path, contract_dir: Path):
        import shutil

        bad_dir = tmp_path / "contract"
        shutil.copytree(contract_dir, bad_dir)

        with pytest.raises(ContractError, match="Contract file not found"):
            load_contract(bad_dir, scenario_name="does_not_exist")

    def test_unknown_depends_on_raises_contract_error(self, tmp_path: Path, contract_dir: Path):
        import shutil

        bad_dir = tmp_path / "contract"
        shutil.copytree(contract_dir, bad_dir)

        # Overwrite topology with a component that depends on a nonexistent peer
        bad_topo = bad_dir / "topology" / "default.yaml"
        bad_topo.write_text(
            textwrap.dedent("""\
            components:
              - name: compute.spark_batch
                type: compute
                service_name: dataproc-spark-batch
                depends_on:
                  - nonexistent.component
                base_rate: 2.0
                base_latency_ms: 100.0
                error_ratio: 0.01
            """)
        )
        with pytest.raises(ContractError):
            load_contract(bad_dir, scenario_name="baseline")

    def test_non_mapping_yaml_raises_contract_error(self, tmp_path: Path, contract_dir: Path):
        import shutil

        bad_dir = tmp_path / "contract"
        shutil.copytree(contract_dir, bad_dir)

        # Write a valid YAML list (not a dict) to the topology file
        bad_topo = bad_dir / "topology" / "default.yaml"
        bad_topo.write_text("- item1\n- item2\n")

        with pytest.raises(ContractError, match="Expected a YAML mapping"):
            load_contract(bad_dir, scenario_name="baseline")

    def test_missing_version_raises_contract_error(self, tmp_path: Path, contract_dir: Path):
        """AT-006: a contract file with no `version` field fails validation."""
        import shutil

        bad_dir = tmp_path / "contract"
        shutil.copytree(contract_dir, bad_dir)

        # Strip the version line from the topology file.
        topo = bad_dir / "topology" / "default.yaml"
        lines = [ln for ln in topo.read_text().splitlines() if not ln.startswith("version:")]
        topo.write_text("\n".join(lines) + "\n")

        with pytest.raises(ContractError, match="version"):
            load_contract(bad_dir, scenario_name="baseline")

    def test_invalid_semver_version_raises_contract_error(self, tmp_path: Path, contract_dir: Path):
        import shutil

        bad_dir = tmp_path / "contract"
        shutil.copytree(contract_dir, bad_dir)

        topo = bad_dir / "topology" / "default.yaml"
        text = topo.read_text().replace('version: "1.0.0"', 'version: "v1"')
        topo.write_text(text)

        with pytest.raises(ContractError, match="semver"):
            load_contract(bad_dir, scenario_name="baseline")


class TestVersionField:
    def test_loaded_contracts_carry_version(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="baseline")
        assert bundle.topology.version == "1.0.0"
        assert bundle.scenario.version == "1.0.0"
        assert bundle.provider_profile.version == "1.0.0"
        assert bundle.schema.version == "1.0.0"

    def test_black_friday_scenario_loads(self, contract_dir: Path):
        bundle = load_contract(contract_dir, scenario_name="black_friday")
        phase_types = {p.type for p in bundle.scenario.phases}
        assert "traffic_surge" in phase_types
        assert "pod_autoscale" in phase_types
