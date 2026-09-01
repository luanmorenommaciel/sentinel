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

    #: Poll cadence. 1s matches the collector's own flush cadence in stream mode
    #: (measured: 1.03 flushes/s), so one tick carries roughly one flush event.
    poll_interval_s: float = float(os.getenv("FLOW_UI_POLL_INTERVAL", "1.0"))

    #: The service/table breakdown is a GROUP BY over the whole table, so it runs on a
    #: slower cadence than the counters.
    lineage_interval_s: float = float(os.getenv("FLOW_UI_LINEAGE_INTERVAL", "5.0"))

    #: Samples kept for mode detection and the sparklines.
    history: int = int(os.getenv("FLOW_UI_HISTORY", "60"))


settings = Settings()
