SELECT throwIf(
    (SELECT count() FROM silver.operation_executions) = 0,
    'silver.operation_executions is empty'
);

SELECT throwIf(
    (SELECT count() FROM silver.metric_observations) = 0,
    'silver.metric_observations is empty'
);

SELECT throwIf(
    (SELECT count() FROM silver.log_events) = 0,
    'silver.log_events is empty'
);

SELECT throwIf(
    (SELECT count() FROM silver.operation_executions) !=
        (SELECT count() FROM bronze.otel_traces),
    'trace row count differs between bronze and silver'
);

SELECT throwIf(
    (SELECT count() FROM silver.metric_observations) !=
        (SELECT count() FROM bronze.otel_metrics_gauge) +
        (SELECT count() FROM bronze.otel_metrics_sum),
    'metric row count differs between bronze and silver'
);

SELECT throwIf(
    (SELECT count() FROM silver.log_events) !=
        (SELECT count() FROM bronze.otel_logs),
    'log row count differs between bronze and silver'
);

SELECT throwIf(
    (SELECT countIf(
        scenario = '' OR run_id = '' OR service_name = '' OR contract_version = ''
    ) FROM silver.operation_executions) != 0,
    'required typed dimensions are missing from operation executions'
);

SELECT throwIf(
    (SELECT countIf(duration_ms < 0) FROM silver.operation_executions) != 0,
    'negative duration found in operation executions'
);

SELECT throwIf(
    (SELECT sum(sample_count) FROM silver.metric_rollup_1m) !=
        (SELECT count() FROM silver.metric_observations),
    'metric rollup does not cover every metric observation'
);

SELECT throwIf(
    (SELECT sum(operation_count) FROM silver.service_health_1m) !=
        (SELECT count() FROM silver.operation_executions),
    'service health rollup does not cover every operation execution'
);

SELECT throwIf(
    (SELECT sum(log_count) FROM silver.log_health_1m) !=
        (SELECT count() FROM silver.log_events),
    'log health rollup does not cover every log event'
);

SELECT throwIf(
    (SELECT count() FROM silver.trace_summary) !=
        (SELECT uniqExact(trace_id) FROM silver.operation_executions WHERE trace_id != ''),
    'trace summary does not contain exactly one row per trace'
);

SELECT throwIf(
    (SELECT sum(span_count) FROM silver.telemetry_coverage_1m) !=
        (SELECT count() FROM silver.operation_executions),
    'telemetry coverage span count differs from silver evidence'
);

SELECT throwIf(
    (SELECT sum(log_count) FROM silver.telemetry_coverage_1m) !=
        (SELECT count() FROM silver.log_events),
    'telemetry coverage log count differs from silver evidence'
);

SELECT throwIf(
    (SELECT sum(metric_count) FROM silver.telemetry_coverage_1m) !=
        (SELECT count() FROM silver.metric_observations),
    'telemetry coverage metric count differs from silver evidence'
);

SELECT throwIf(
    (SELECT sum(operation_count) FROM silver.run_summary) !=
        (SELECT count() FROM silver.operation_executions),
    'run summary operation count differs from silver evidence'
);

SELECT throwIf(
    (SELECT sum(log_count) FROM silver.run_summary) !=
        (SELECT count() FROM silver.log_events),
    'run summary log count differs from silver evidence'
);

SELECT throwIf(
    (SELECT sum(metric_count) FROM silver.run_summary) !=
        (SELECT count() FROM silver.metric_observations),
    'run summary metric count differs from silver evidence'
);

SELECT
    (SELECT count() FROM silver.operation_executions) AS operation_executions,
    (SELECT count() FROM silver.log_events) AS log_events,
    (SELECT count() FROM silver.metric_observations) AS metric_observations,
    (SELECT count() FROM silver.metric_rollup_1m) AS metric_rollup_windows,
    (SELECT count() FROM silver.service_health_1m) AS service_health_windows,
    (SELECT count() FROM silver.log_health_1m) AS log_health_windows,
    (SELECT count() FROM silver.trace_summary) AS traces,
    (SELECT count() FROM silver.telemetry_coverage_1m) AS coverage_windows,
    (SELECT count() FROM silver.run_summary) AS runs;
