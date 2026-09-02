SELECT *
FROM silver.run_summary
ORDER BY run_start DESC
LIMIT 3;

SELECT
    window_start,
    service_name,
    operation_count,
    error_count,
    round(error_rate, 4) AS error_rate,
    round(latency_p95_ms, 3) AS latency_p95_ms
FROM silver.service_health_1m
ORDER BY window_start DESC, service_name
LIMIT 10;

SELECT
    event_time,
    service_name,
    component_name,
    severity_text,
    body,
    trace_id
FROM silver.log_events
WHERE is_error
ORDER BY event_time DESC
LIMIT 5;

SELECT
    event_time,
    service_name,
    component_name,
    metric_name,
    metric_kind,
    value,
    metric_unit
FROM silver.metric_observations
ORDER BY event_time DESC
LIMIT 5;

SELECT
    trace_id,
    span_count,
    error_span_count,
    entry_service,
    exit_service,
    round(trace_duration_ms, 3) AS trace_duration_ms
FROM silver.trace_summary
ORDER BY trace_start DESC
LIMIT 5;
