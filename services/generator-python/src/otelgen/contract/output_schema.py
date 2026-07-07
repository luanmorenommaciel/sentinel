from __future__ import annotations

import os
from pathlib import Path

from otelgen.model import LogSignal, MetricSignal, Signal, SpanSignal

# Version of the published OTLP output contract (contract/schema/otlp_output.schema.json).
# Bump when the emitted signal/resource shape changes; keep in sync with the schema file's
# top-level "version" and with Pod 2's validation.
CONTRACT_VERSION = "1.0.0"


def schema_path() -> Path:
    """Absolute path to the published JSON Schema for the OTLP output contract.

    The canonical contract is the monorepo SSOT at contracts/generator/v1. It is resolved via
    the CONTRACTS_DIR env var (set to /contracts/generator/v1 in containers). For local dev we
    fall back to the repo root, walking up from
    services/generator-python/src/otelgen/contract/output_schema.py.
    """
    contracts_dir = os.environ.get("CONTRACTS_DIR")
    if contracts_dir:
        return Path(contracts_dir) / "schema" / "otlp_output.schema.json"
    return Path(__file__).resolve().parents[5] / "contracts" / "generator" / "v1" / "schema" / "otlp_output.schema.json"


def signal_to_contract_dict(signal: Signal) -> dict:
    """Serialize a canonical signal to the contract dict described by otlp_output.schema.json.

    This is the Pod 1 -> Pod 2 handoff shape. The validation test asserts the output
    of this function conforms to the published JSON Schema.
    """
    if isinstance(signal, LogSignal):
        return {
            "signal_type": "log",
            "contract_version": CONTRACT_VERSION,
            "time_unix_nano": signal.time_unix_nano,
            "severity_text": signal.severity_text,
            "severity_number": signal.severity_number,
            "service_name": signal.service_name,
            "body": signal.body,
            "trace_id": signal.trace_id,
            "span_id": signal.span_id,
            "attributes": dict(signal.attributes),
            "resource_attributes": dict(signal.resource_attributes),
        }
    if isinstance(signal, SpanSignal):
        return {
            "signal_type": "span",
            "contract_version": CONTRACT_VERSION,
            "trace_id": signal.trace_id,
            "span_id": signal.span_id,
            "parent_span_id": signal.parent_span_id,
            "name": signal.name,
            "service_name": signal.service_name,
            "start_unix_nano": signal.start_unix_nano,
            "end_unix_nano": signal.end_unix_nano,
            "status_code": signal.status_code,
            "attributes": dict(signal.attributes),
            "resource_attributes": dict(signal.resource_attributes),
        }
    if isinstance(signal, MetricSignal):
        return {
            "signal_type": "metric",
            "contract_version": CONTRACT_VERSION,
            "time_unix_nano": signal.time_unix_nano,
            "name": signal.name,
            "type": signal.type,
            "value": signal.value,
            "service_name": signal.service_name,
            "attributes": dict(signal.attributes),
            "resource_attributes": dict(signal.resource_attributes),
        }
    raise TypeError(f"Unsupported signal type: {type(signal)!r}")
