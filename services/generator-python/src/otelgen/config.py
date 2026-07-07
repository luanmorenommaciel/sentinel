from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Mode(str, Enum):
    backfill = "backfill"
    stream = "stream"


class Delivery(str, Enum):
    otlp = "otlp"
    direct = "direct"


class ClickHouseConnConfig(BaseModel):
    host: str = "localhost"
    port: int = 8123
    user: str = "default"
    password: str = ""
    database: str = "default"


class RunConfig(BaseModel):
    mode: Mode = Mode.backfill
    delivery: Delivery = Delivery.otlp
    provider: str = "gcp"
    scenario: str = "baseline"

    # Durations are stored as plain seconds (float) for simplicity — callers
    # convert using datetime.timedelta(seconds=...) as needed.
    window_seconds: float = Field(default=86400.0, gt=0, description="Backfill window in seconds (default 24h)")
    step_seconds: float = Field(default=10.0, gt=0, description="Tick granularity in seconds (default 10s)")
    rate: int = Field(default=200, gt=0, description="Events per second cap")
    duration_seconds: float = Field(default=300.0, gt=0, description="Streaming run cap in seconds (default 5m)")
    seed: int = 0

    contract_dir: Path = Path("/app/contract")
    otlp_endpoint: str = "http://localhost:4317"
    otlp_protocol: str = "grpc"  # "grpc" | "http/protobuf" — gRPC :4317 is canonical (meeting D4)
    otlp_insecure: bool | None = None  # None = auto (insecure for http:// endpoints)
    otlp_headers: dict[str, str] = Field(default_factory=dict)  # e.g. {"authorization": "<key>"}

    clickhouse: ClickHouseConnConfig = Field(default_factory=ClickHouseConnConfig)

    init_schema: bool = False
    dry_run: bool = False

    @model_validator(mode="after")
    def _validate_delivery_mode(self) -> RunConfig:
        if self.delivery == Delivery.direct and self.init_schema is False:
            # Allowed — no contradiction here; just ensure we have CH config.
            pass
        return self

    @classmethod
    def build(cls, **kwargs: Any) -> RunConfig:
        """Build a RunConfig from explicit keyword arguments (used by the CLI)."""
        ch_fields = {"ch_host", "ch_port", "ch_user", "ch_password", "ch_database"}
        ch_kwargs: dict[str, Any] = {}
        top_kwargs: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key in ch_fields:
                ch_kwargs[key[3:]] = value  # strip "ch_" prefix
            else:
                top_kwargs[key] = value
        if ch_kwargs:
            top_kwargs["clickhouse"] = ClickHouseConnConfig(**ch_kwargs)
        return cls(**top_kwargs)
