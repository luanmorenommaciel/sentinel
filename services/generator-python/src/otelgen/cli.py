from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer

from otelgen.contract.models import parse_duration

app = typer.Typer(
    name="otelgen",
    help="OTel synthetic data generator — produces logs, metrics, and traces.",
    add_completion=False,
)


def _configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    )


def _preflight_otlp(endpoint: str, protocol: str = "http/protobuf") -> None:
    """Best-effort TCP reachability check for the OTLP endpoint; exits 1 if unreachable.

    A plain socket connect is used (not an HTTP probe) because auth-required
    collectors reset unauthenticated requests, which would otherwise look like
    a connectivity failure.
    """
    import socket
    import urllib.parse

    parsed = urllib.parse.urlparse(endpoint if "//" in endpoint else f"//{endpoint}")
    host = parsed.hostname or "localhost"
    port = parsed.port or (4317 if protocol == "grpc" else 4318)
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
    except Exception as exc:
        typer.echo(
            f"ERROR: Cannot reach OTLP endpoint {endpoint!r} ({host}:{port}): {exc}\n"
            "Ensure the collector is running and --otlp-endpoint is correct.",
            err=True,
        )
        raise typer.Exit(1)


def _preflight_clickhouse(conn) -> None:
    """Best-effort connectivity check for ClickHouse; exits 1 if unreachable."""
    import socket
    try:
        with socket.create_connection((conn.host, conn.port), timeout=5):
            pass
    except Exception as exc:
        typer.echo(
            f"ERROR: Cannot reach ClickHouse at {conn.host}:{conn.port}: {exc}\n"
            "Ensure ClickHouse is running and --ch-host/--ch-port are correct.",
            err=True,
        )
        raise typer.Exit(1)


@app.command()
def run(
    mode: str = typer.Option("backfill", "--mode", help="Run mode: backfill or stream"),
    delivery: str = typer.Option("otlp", "--delivery", help="Delivery: otlp or direct"),
    provider: str = typer.Option("gcp", "--provider", help="Provider profile (e.g. gcp)"),
    scenario: str = typer.Option("baseline", "--scenario", help="Scenario name"),
    window: str = typer.Option("24h", "--window", help="Backfill window (e.g. 24h, 1h30m)"),
    step: str = typer.Option("10s", "--step", help="Tick step size (e.g. 10s, 1m)"),
    rate: int = typer.Option(200, "--rate", help="Events per second cap"),
    duration: str = typer.Option("5m", "--duration", help="Streaming run cap (e.g. 5m, 1h)"),
    seed: int = typer.Option(0, "--seed", help="RNG seed for reproducibility"),
    contract_dir: Path = typer.Option(Path("/app/contract"), "--contract-dir", help="Root of YAML contract"),
    otlp_endpoint: str = typer.Option(
        "http://localhost:4317",
        "--otlp-endpoint",
        envvar="OTELGEN_OTLP_ENDPOINT",
        help="OTLP collector endpoint (canonical: gRPC on :4317)",
    ),
    otlp_protocol: str = typer.Option("grpc", "--otlp-protocol", help="OTLP protocol: grpc or http/protobuf"),
    otlp_insecure: bool | None = typer.Option(
        None,
        "--otlp-insecure/--otlp-secure",
        help="Plaintext gRPC (no TLS). Default: auto — insecure for http:// endpoints.",
    ),
    otlp_api_key: str = typer.Option(
        "",
        "--otlp-api-key",
        envvar="OTELGEN_OTLP_API_KEY",
        help="OTLP ingestion API key; sent as the 'authorization' header (e.g. for HyperDX/ClickStack)",
    ),
    otlp_header: list[str] = typer.Option(
        [],
        "--otlp-header",
        help="Additional OTLP header as 'key=value' (repeatable)",
    ),
    ch_host: str = typer.Option("localhost", "--ch-host", envvar="CH_HOST", help="ClickHouse host"),
    ch_port: int = typer.Option(8123, "--ch-port", envvar="CH_PORT", help="ClickHouse port"),
    ch_user: str = typer.Option("default", "--ch-user", envvar="CH_USER", help="ClickHouse user"),
    ch_password: str = typer.Option("", "--ch-password", envvar="CH_PASSWORD", help="ClickHouse password"),
    ch_database: str = typer.Option("default", "--ch-database", envvar="CH_DATABASE", help="ClickHouse database"),
    init_schema: bool = typer.Option(False, "--init-schema", help="Print CREATE TABLE DDL and exit"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate config and estimate signal counts without exporting; then exit 0"
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level: DEBUG, INFO, WARNING, ERROR"),
) -> None:
    """Generate synthetic OTel telemetry and deliver it to the configured target."""
    _configure_logging(log_level)
    log = logging.getLogger("otelgen.cli")

    # Parse durations
    try:
        window_td = parse_duration(window)
        step_td = parse_duration(step)
        duration_td = parse_duration(duration)
    except ValueError as exc:
        typer.echo(f"ERROR: Invalid duration — {exc}", err=True)
        raise typer.Exit(2)

    # Assemble OTLP headers: explicit --otlp-header entries plus the API key.
    otlp_headers: dict[str, str] = {}
    for raw in otlp_header:
        if "=" not in raw:
            typer.echo(f"ERROR: --otlp-header must be 'key=value', got {raw!r}", err=True)
            raise typer.Exit(2)
        key, value = raw.split("=", 1)
        otlp_headers[key.strip()] = value.strip()
    if otlp_api_key:
        otlp_headers["authorization"] = otlp_api_key

    from otelgen.config import RunConfig

    cfg = RunConfig.build(
        mode=mode,
        delivery=delivery,
        provider=provider,
        scenario=scenario,
        window_seconds=window_td.total_seconds(),
        step_seconds=step_td.total_seconds(),
        rate=rate,
        duration_seconds=duration_td.total_seconds(),
        seed=seed,
        contract_dir=contract_dir,
        otlp_endpoint=otlp_endpoint,
        otlp_protocol=otlp_protocol,
        otlp_insecure=otlp_insecure,
        otlp_headers=otlp_headers,
        ch_host=ch_host,
        ch_port=ch_port,
        ch_user=ch_user,
        ch_password=ch_password,
        ch_database=ch_database,
        init_schema=init_schema,
        dry_run=dry_run,
    )

    from otelgen.contract.loader import ContractError, load_contract

    try:
        bundle = load_contract(cfg.contract_dir, cfg.scenario, cfg.provider)
    except ContractError as exc:
        typer.echo(f"ERROR: Contract loading failed — {exc}", err=True)
        raise typer.Exit(2)

    if cfg.init_schema:
        try:
            from otelgen.exporters.clickhouse import render_create_table_ddl
            typer.echo(render_create_table_ddl(bundle.schema))
        except ImportError as exc:
            typer.echo(f"ERROR: clickhouse exporter unavailable — {exc}", err=True)
            raise typer.Exit(1)
        raise typer.Exit(0)

    from otelgen.model import LogSignal, MetricSignal, SpanSignal
    from otelgen.reporting import RunReporter
    from otelgen.runmode import backfill_ticks, stream_ticks
    from otelgen.scenarios.engine import ScenarioEngine
    from otelgen.seeding import make_rng
    from otelgen.signals.factory import SignalFactory
    from otelgen.topology import Topology

    rng = make_rng(cfg.seed)
    run_id = str(uuid.uuid4())

    factory = SignalFactory(
        provider_profile=bundle.provider_profile,
        run_id=run_id,
        scenario_name=bundle.scenario.name,
        rng=rng,
    )

    topology = Topology(bundle.topology)
    engine = ScenarioEngine(
        topology=topology,
        scenario=bundle.scenario,
        factory=factory,
        rng=rng,
        step_seconds=cfg.step_seconds,
        rate=cfg.rate,
    )

    now = datetime.now(timezone.utc)
    if cfg.mode == "backfill":
        window_td_obj = timedelta(seconds=cfg.window_seconds)
        step_td_obj = timedelta(seconds=cfg.step_seconds)
        end_dt = now
        start_dt = end_dt - window_td_obj
        window_start_unix_nano = int(start_dt.timestamp() * 1e9)
        ticks = backfill_ticks(window=window_td_obj, step=step_td_obj, end=end_dt)
    else:
        step_td_obj = timedelta(seconds=cfg.step_seconds)
        until_dt = now + timedelta(seconds=cfg.duration_seconds)
        window_start_unix_nano = int(now.timestamp() * 1e9)
        ticks = stream_ticks(step=step_td_obj, until=until_dt)

    # Dry run: validate + estimate signal counts without building an exporter or exporting.
    if cfg.dry_run:
        import json

        counts = {"logs": 0, "traces": 0, "metrics": 0}
        stream_output = cfg.mode == "stream"

        for signal in engine.run(ticks, window_start_unix_nano):
            if isinstance(signal, SpanSignal):
                counts["traces"] += 1
                if stream_output:
                    ts = datetime.fromtimestamp(signal.start_unix_nano / 1e9, tz=timezone.utc).isoformat()
                    typer.echo(json.dumps({
                        "type": "span", "ts": ts, "service": signal.service_name,
                        "name": signal.name, "status": signal.status_code,
                        "trace_id": signal.trace_id, "span_id": signal.span_id,
                    }))
            elif isinstance(signal, LogSignal):
                counts["logs"] += 1
                if stream_output:
                    ts = datetime.fromtimestamp(signal.time_unix_nano / 1e9, tz=timezone.utc).isoformat()
                    typer.echo(json.dumps({
                        "type": "log", "ts": ts, "service": signal.service_name,
                        "severity": signal.severity_text, "body": signal.body,
                    }))
            elif isinstance(signal, MetricSignal):
                counts["metrics"] += 1
                if stream_output:
                    ts = datetime.fromtimestamp(signal.time_unix_nano / 1e9, tz=timezone.utc).isoformat()
                    typer.echo(json.dumps({
                        "type": "metric", "ts": ts, "service": signal.service_name,
                        "name": signal.name, "metric_type": signal.type, "value": signal.value,
                    }))

        total = sum(counts.values())
        typer.echo(
            "DRY RUN — no data exported.\n"
            f"  scenario: {cfg.scenario}  mode: {cfg.mode}  provider: {cfg.provider}\n"
            f"  logs:    {counts['logs']}\n"
            f"  traces:  {counts['traces']}\n"
            f"  metrics: {counts['metrics']}\n"
            f"  total:   {total}"
        )
        raise typer.Exit(0)

    # Preflight connectivity
    if cfg.delivery == "otlp":
        _preflight_otlp(cfg.otlp_endpoint, cfg.otlp_protocol)
    elif cfg.delivery == "direct":
        log.warning(
            "Delivery 'direct' (generator -> ClickHouse) is NON-CANONICAL, for dev/testing only. "
            "Canonical path is OTLP -> OTel Collector (meeting D6); the ClickHouse table schema is owned by Pod 3."
        )
        _preflight_clickhouse(cfg.clickhouse)

    from otelgen.exporters.base import build_exporter

    try:
        exporter = build_exporter(cfg, schema=bundle.schema)
    except Exception as exc:
        typer.echo(f"ERROR: Failed to build exporter — {exc}", err=True)
        raise typer.Exit(1)

    reporter = RunReporter()
    reporter.start()
    log.info("Run started", extra={"run_id": run_id, "mode": cfg.mode, "scenario": cfg.scenario})

    delivery_label = cfg.delivery

    try:
        batch: list = []
        batch_size = 500
        for signal in engine.run(ticks, window_start_unix_nano):
            batch.append(signal)
            if len(batch) >= batch_size:
                try:
                    exporter.export(batch)
                    for s in batch:
                        reporter.record_emitted(s, delivery=delivery_label)
                except Exception as exc:
                    log.error("Export error: %s", exc)
                    for s in batch:
                        reporter.record_failed(s, str(exc), delivery=delivery_label)
                    reporter.record_error(str(exc))
                batch = []

        if batch:
            try:
                exporter.export(batch)
                for s in batch:
                    reporter.record_emitted(s, delivery=delivery_label)
            except Exception as exc:
                log.error("Export error (final batch): %s", exc)
                for s in batch:
                    reporter.record_failed(s, str(exc), delivery=delivery_label)
                reporter.record_error(str(exc))

    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        reporter.record_error("Run interrupted by KeyboardInterrupt.")

    try:
        exporter.flush()
        exporter.close()
    except Exception as exc:
        log.warning("Exporter close error: %s", exc)

    reporter.end()
    reporter.render()
    raise typer.Exit(reporter.exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
