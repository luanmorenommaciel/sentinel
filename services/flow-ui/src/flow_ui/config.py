"""Runtime configuration, read from the environment.

Every default points at the root `docker-compose.yml` topology, so the app runs with no
configuration at all next to a `make up` pipeline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    #: The collector's Prometheus endpoint. The browser never talks to this — it has no
    #: CORS headers (see `collector-rust/src/metrics_server.rs`, which sets only
    #: Content-Type), so a cross-origin fetch from the page would be blocked. This
    #: service is the only thing that reads it.
    collector_metrics_url: str = os.getenv(
        "COLLECTOR_METRICS_URL", "http://localhost:9090/metrics"
    )

    #: ClickHouse HTTP. Queries are POSTed with the SQL as the raw body — passing it as a
    #: url-encoded `query=` parameter makes ClickHouse parse the literal string `query=`
    #: as the statement and fail with a syntax error.
    clickhouse_url: str = os.getenv("CLICKHOUSE_URL", "http://localhost:8123")
    clickhouse_database: str = os.getenv("CLICKHOUSE_DATABASE", "bronze")

    #: Reader credentials (T18). `sentinel_reader` holds SELECT on bronze, silver and
    #: `system.tables`/`system.columns` — the last two are what the Flow board's Silver
    #: box is drawn from, so without them it silently disappears.
    #:
    #: The password is a **path**, never a value, matching the collector's contract
    #: (SPEC §14.2): a path can live in a committed file under review while the secret
    #: never does. Both default to empty so a bare `make ui` against a passwordless
    #: local ClickHouse still works with no configuration — the credentials are only
    #: sent when a user is actually set.
    clickhouse_user: str = os.getenv("CLICKHOUSE_USER", "")
    clickhouse_password_file: str = os.getenv("CLICKHOUSE_PASSWORD_FILE", "")

    #: Poll cadence. 1s matches the collector's own flush cadence in stream mode
    #: (measured: 1.03 flushes/s), so one tick carries roughly one flush event.
    poll_interval_s: float = float(os.getenv("FLOW_UI_POLL_INTERVAL", "1.0"))

    #: The service/table breakdown is a GROUP BY over the whole table, so it runs on a
    #: slower cadence than the counters.
    lineage_interval_s: float = float(os.getenv("FLOW_UI_LINEAGE_INTERVAL", "5.0"))
    #: Contract health gets a slower lane of its own. It probes an unindexed Map across
    #: every live table — measured 1.26s over ~6M rows — so at the 5s lineage cadence it
    #: would hold ClickHouse a quarter of the time, and the cost grows with bronze.
    contract_interval_s: float = float(os.getenv("FLOW_UI_CONTRACT_INTERVAL", "30.0"))
    #: Training window for the volume band, in minutes. Elementary's documented baseline is
    #: a 1-day bucket over 14 days; the bucket here is a minute because that is this
    #: pipeline's cadence, and a day-wide bucket over a stream measured in minutes would
    #: hold exactly one point. Same method, scaled to the data.
    volume_window_min: int = int(os.getenv("FLOW_UI_VOLUME_WINDOW_MIN", "60"))

    #: Samples kept for mode detection and the sparklines.
    history: int = int(os.getenv("FLOW_UI_HISTORY", "60"))


settings = Settings()
