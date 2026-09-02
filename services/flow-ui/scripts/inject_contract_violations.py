"""Send foreign OTLP — well-formed, but missing `sentinel.run_id`.

The collector's default `warn` policy exists for exactly this: telemetry that did not come
from Pod 1's generator legitimately lacks the five `sentinel.*` keys, so a `strict` default
would reject valid traffic. Under `warn` these signals are counted as contract violations and
**exported anyway**, which is why the evidence shows up in bronze and on the Contract board.

Metrics and logs only, no spans, on purpose: the falling dot in the collector's OUTCOMES
panel is coloured by the signal type that actually failed, so a run of this must leave the
traces lane at zero. If a white dot falls, something is colouring by guess.

Run it from the repo root, against the compose network:

    docker compose run --rm --entrypoint python \
      -v "$PWD/services/flow-ui/scripts/inject_contract_violations.py:/tmp/inject.py:ro" \
      generator /tmp/inject.py <seconds> <logs-per-tick> <metrics-per-tick>

    # 2 minutes of ~40 logs/s and ~300 metrics/s that fail the contract
    ... generator /tmp/inject.py 120 40 300
"""
import sys
import time

import grpc
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2 as LS
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2_grpc as LSG
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2 as MS
from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2_grpc as MSG
from opentelemetry.proto.common.v1 import common_pb2 as C
from opentelemetry.proto.logs.v1 import logs_pb2 as L
from opentelemetry.proto.metrics.v1 import metrics_pb2 as M
from opentelemetry.proto.resource.v1 import resource_pb2 as R

kv = lambda k, v: C.KeyValue(key=k, value=C.AnyValue(string_value=v))
# Four of the five required keys. `sentinel.run_id` is absent — one missing key is enough.
RES = R.Resource(attributes=[
    kv("service.name", "third-party-agent"),
    kv("cloud.provider", "gcp"),
    kv("sentinel.synthetic", "false"),
    kv("sentinel.scenario", "foreign"),
])

ch = grpc.insecure_channel("collector:4317")
logs, mets = LSG.LogsServiceStub(ch), MSG.MetricsServiceStub(ch)
LOGS_PER_TICK, METRICS_PER_TICK = int(sys.argv[2]), int(sys.argv[3])
deadline = time.time() + float(sys.argv[1])
sent = 0
while time.time() < deadline:
    now = time.time_ns()
    logs.Export(LS.ExportLogsServiceRequest(resource_logs=[L.ResourceLogs(
        resource=RES, scope_logs=[L.ScopeLogs(log_records=[
            L.LogRecord(time_unix_nano=now, severity_number=9, severity_text="INFO",
                        body=C.AnyValue(string_value=f"foreign log {i}"))
            for i in range(LOGS_PER_TICK)])])]))
    mets.Export(MS.ExportMetricsServiceRequest(resource_metrics=[M.ResourceMetrics(
        resource=RES, scope_metrics=[M.ScopeMetrics(metrics=[
            M.Metric(name="agent.cpu_pct", gauge=M.Gauge(data_points=[
                M.NumberDataPoint(time_unix_nano=now, as_double=float(i))
                for i in range(METRICS_PER_TICK)]))])])]))
    sent += LOGS_PER_TICK + METRICS_PER_TICK
    time.sleep(1)
print(f"sent {sent} foreign signals", flush=True)
