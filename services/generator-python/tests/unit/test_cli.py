from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from otelgen.cli import app

runner = CliRunner()

CONTRACT_DIR = str(Path(__file__).parent.parent.parent / "config")


# ---------------------------------------------------------------------------
# --init-schema path
# ---------------------------------------------------------------------------


class TestInitSchema:
    def test_init_schema_exits_0(self):
        result = runner.invoke(app, ["--init-schema", "--contract-dir", CONTRACT_DIR])
        assert result.exit_code == 0, result.output

    def test_init_schema_prints_create_table(self):
        result = runner.invoke(app, ["--init-schema", "--contract-dir", CONTRACT_DIR])
        assert "CREATE TABLE IF NOT EXISTS" in result.output

    def test_init_schema_includes_all_table_names(self):
        result = runner.invoke(app, ["--init-schema", "--contract-dir", CONTRACT_DIR])
        assert "otel_logs" in result.output
        assert "otel_traces" in result.output
        assert "otel_metrics" in result.output

    def test_init_schema_with_failure_spike_scenario(self):
        result = runner.invoke(
            app,
            [
                "--init-schema",
                "--contract-dir", CONTRACT_DIR,
                "--scenario", "failure_spike",
            ],
        )
        assert result.exit_code == 0

    def test_init_schema_nonexistent_contract_dir_exits_nonzero(self):
        result = runner.invoke(
            app,
            ["--init-schema", "--contract-dir", "/nonexistent/path/contract"],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_invalid_provider_exits_nonzero(self):
        """AT-010: unsupported provider should fail fast."""
        result = runner.invoke(
            app,
            [
                "--init-schema",
                "--contract-dir", CONTRACT_DIR,
                "--provider", "notreal",
            ],
        )
        assert result.exit_code != 0

    def test_missing_scenario_exits_nonzero(self):
        result = runner.invoke(
            app,
            [
                "--init-schema",
                "--contract-dir", CONTRACT_DIR,
                "--scenario", "does_not_exist",
            ],
        )
        assert result.exit_code != 0

    def test_invalid_window_duration_exits_2(self):
        """Bad duration string should fail with exit code 2."""
        result = runner.invoke(
            app,
            [
                "--window", "notaduration",
                "--contract-dir", CONTRACT_DIR,
            ],
        )
        assert result.exit_code == 2

    def test_invalid_step_duration_exits_2(self):
        result = runner.invoke(
            app,
            [
                "--step", "xyz",
                "--contract-dir", CONTRACT_DIR,
            ],
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# OTLP auth headers (--otlp-api-key / --otlp-header)
# ---------------------------------------------------------------------------


class TestOtlpHeaders:
    def _run_capturing_cfg(self, extra_args: list[str]):
        """Run the CLI with network/exporter mocked; return the RunConfig handed to build_exporter."""
        captured = {}

        def fake_build_exporter(cfg, schema=None):
            captured["cfg"] = cfg
            return MagicMock()

        with (
            patch("otelgen.cli._preflight_otlp"),
            patch("otelgen.exporters.base.build_exporter", side_effect=fake_build_exporter),
        ):
            result = runner.invoke(
                app,
                ["--delivery", "otlp", "--mode", "backfill", "--window", "5m", "--step", "1m",
                 "--contract-dir", CONTRACT_DIR, *extra_args],
            )
        return result, captured.get("cfg")

    def test_api_key_becomes_authorization_header(self):
        result, cfg = self._run_capturing_cfg(["--otlp-api-key", "secret-123"])
        assert result.exit_code == 0, result.output
        assert cfg.otlp_headers == {"authorization": "secret-123"}

    def test_custom_header_parsed(self):
        result, cfg = self._run_capturing_cfg(["--otlp-header", "x-team=alpha"])
        assert result.exit_code == 0, result.output
        assert cfg.otlp_headers["x-team"] == "alpha"

    def test_malformed_header_exits_2(self):
        result, _ = self._run_capturing_cfg(["--otlp-header", "noequals"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# --dry-run (AT-012)
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_exits_0_without_exporter(self):
        called = {"build": False}

        def fake_build_exporter(cfg, schema=None):
            called["build"] = True
            return MagicMock()

        with (
            patch("otelgen.cli._preflight_otlp") as preflight,
            patch("otelgen.exporters.base.build_exporter", side_effect=fake_build_exporter),
        ):
            result = runner.invoke(
                app,
                ["--dry-run", "--contract-dir", CONTRACT_DIR, "--window", "10m", "--step", "5m", "--seed", "1"],
            )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert called["build"] is False
        preflight.assert_not_called()

    def test_dry_run_reports_signal_counts(self):
        result = runner.invoke(
            app,
            ["--dry-run", "--contract-dir", CONTRACT_DIR, "--window", "10m", "--step", "5m", "--seed", "1"],
        )
        assert result.exit_code == 0, result.output
        assert "logs:" in result.output
        assert "traces:" in result.output
        assert "metrics:" in result.output


# ---------------------------------------------------------------------------
# Direct delivery is non-canonical (AT-011)
# ---------------------------------------------------------------------------


class TestDirectDeliveryWarning:
    def test_direct_delivery_logs_warning(self, caplog):
        import logging

        def fake_build_exporter(cfg, schema=None):
            return MagicMock()

        with (
            patch("otelgen.cli._preflight_clickhouse"),
            patch("otelgen.exporters.base.build_exporter", side_effect=fake_build_exporter),
            caplog.at_level(logging.WARNING, logger="otelgen.cli"),
        ):
            result = runner.invoke(
                app,
                ["--delivery", "direct", "--contract-dir", CONTRACT_DIR,
                 "--window", "5m", "--step", "5m", "--seed", "1"],
            )
        assert result.exit_code == 0, result.output
        assert any("NON-CANONICAL" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# gRPC default transport (AT-001)
# ---------------------------------------------------------------------------


class TestGrpcDefault:
    def test_default_protocol_is_grpc_4317(self):
        captured = {}

        def fake_build_exporter(cfg, schema=None):
            captured["cfg"] = cfg
            return MagicMock()

        with (
            patch("otelgen.cli._preflight_otlp"),
            patch("otelgen.exporters.base.build_exporter", side_effect=fake_build_exporter),
        ):
            result = runner.invoke(
                app,
                ["--contract-dir", CONTRACT_DIR, "--window", "5m", "--step", "5m", "--seed", "1"],
            )
        assert result.exit_code == 0, result.output
        assert captured["cfg"].otlp_protocol == "grpc"
        assert captured["cfg"].otlp_endpoint == "http://localhost:4317"
