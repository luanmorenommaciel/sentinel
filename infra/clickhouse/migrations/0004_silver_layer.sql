-- Sentinel SILVER v1 — typed operational models consumed by the first Watchers.
--
-- Bronze remains the immutable OTel landing contract. These models materialize
-- Sentinel's hot dimensions and normalize durations/metric kinds so Watchers do
-- not probe attribute Maps or repeat unit conversions in every query.
--
-- Materialized views process new inserts only. In production, deploy this DDL
-- before enabling ingestion. For existing Bronze data, use an explicit backfill
-- rather than POPULATE so deployment can control the time range and deduplication.

CREATE DATABASE IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.operation_executions
(
    `event_time` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
    `end_time` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
    `scenario` LowCardinality(String) CODEC(ZSTD(1)),
    `run_id` String CODEC(ZSTD(1)),
    `cloud_provider` LowCardinality(String) CODEC(ZSTD(1)),
    `is_synthetic` Bool CODEC(Delta(1), ZSTD(1)),
    `contract_version` LowCardinality(String) CODEC(ZSTD(1)),
    `service_name` LowCardinality(String) CODEC(ZSTD(1)),
    `component_name` LowCardinality(String) CODEC(ZSTD(1)),
    `component_type` LowCardinality(String) CODEC(ZSTD(1)),
    `operation_name` LowCardinality(String) CODEC(ZSTD(1)),
    `trace_id` String CODEC(ZSTD(1)),
    `span_id` String CODEC(ZSTD(1)),
    `parent_span_id` String CODEC(ZSTD(1)),
    `duration_ms` Float64 CODEC(ZSTD(1)),
    `status_code` LowCardinality(String) CODEC(ZSTD(1)),
    `is_error` Bool CODEC(Delta(1), ZSTD(1)),
    `resource_attributes` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    `operation_attributes` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    INDEX idx_trace_id trace_id TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_run_id run_id TYPE bloom_filter(0.01) GRANULARITY 4
)
ENGINE = MergeTree
PARTITION BY toDate(event_time)
ORDER BY (scenario, service_name, component_name, operation_name, event_time, trace_id)
TTL toDateTime(event_time) + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.operation_executions_mv
TO silver.operation_executions
AS SELECT
    Timestamp AS event_time,
    addNanoseconds(Timestamp, Duration) AS end_time,
    ResourceAttributes['sentinel.scenario'] AS scenario,
    ResourceAttributes['sentinel.run_id'] AS run_id,
    ResourceAttributes['cloud.provider'] AS cloud_provider,
    lower(ResourceAttributes['sentinel.synthetic']) = 'true' AS is_synthetic,
    ResourceAttributes['contract_version'] AS contract_version,
    ServiceName AS service_name,
    SpanAttributes['component.name'] AS component_name,
    SpanAttributes['component.type'] AS component_type,
    SpanName AS operation_name,
    TraceId AS trace_id,
    SpanId AS span_id,
    ParentSpanId AS parent_span_id,
    Duration / 1000000.0 AS duration_ms,
    StatusCode AS status_code,
    StatusCode = 'Error' AS is_error,
    ResourceAttributes AS resource_attributes,
    SpanAttributes AS operation_attributes
FROM bronze.otel_traces;

CREATE TABLE IF NOT EXISTS silver.log_events
(
    `event_time` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
    `scenario` LowCardinality(String) CODEC(ZSTD(1)),
    `run_id` String CODEC(ZSTD(1)),
    `cloud_provider` LowCardinality(String) CODEC(ZSTD(1)),
    `is_synthetic` Bool CODEC(Delta(1), ZSTD(1)),
    `contract_version` LowCardinality(String) CODEC(ZSTD(1)),
    `service_name` LowCardinality(String) CODEC(ZSTD(1)),
    `component_name` LowCardinality(String) CODEC(ZSTD(1)),
    `severity_text` LowCardinality(String) CODEC(ZSTD(1)),
    `severity_number` UInt8,
    `is_error` Bool CODEC(Delta(1), ZSTD(1)),
    `body` String CODEC(ZSTD(1)),
    `trace_id` String CODEC(ZSTD(1)),
    `span_id` String CODEC(ZSTD(1)),
    `resource_attributes` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    `log_attributes` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    INDEX idx_trace_id trace_id TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_run_id run_id TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX idx_body body TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1
)
ENGINE = MergeTree
PARTITION BY toDate(event_time)
ORDER BY (scenario, service_name, component_name, severity_number, event_time, trace_id)
TTL toDateTime(event_time) + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.log_events_mv
TO silver.log_events
AS SELECT
    Timestamp AS event_time,
    ResourceAttributes['sentinel.scenario'] AS scenario,
    ResourceAttributes['sentinel.run_id'] AS run_id,
    ResourceAttributes['cloud.provider'] AS cloud_provider,
    lower(ResourceAttributes['sentinel.synthetic']) = 'true' AS is_synthetic,
    ResourceAttributes['contract_version'] AS contract_version,
    ServiceName AS service_name,
    LogAttributes['component.name'] AS component_name,
    SeverityText AS severity_text,
    SeverityNumber AS severity_number,
    SeverityNumber >= 17 OR upperUTF8(SeverityText) IN ('ERROR', 'FATAL') AS is_error,
    Body AS body,
    TraceId AS trace_id,
    SpanId AS span_id,
    ResourceAttributes AS resource_attributes,
    LogAttributes AS log_attributes
FROM bronze.otel_logs;

CREATE TABLE IF NOT EXISTS silver.metric_observations
(
    `event_time` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
    `start_time` DateTime64(9) CODEC(Delta(8), ZSTD(1)),
    `scenario` LowCardinality(String) CODEC(ZSTD(1)),
    `run_id` String CODEC(ZSTD(1)),
    `cloud_provider` LowCardinality(String) CODEC(ZSTD(1)),
    `is_synthetic` Bool CODEC(Delta(1), ZSTD(1)),
    `contract_version` LowCardinality(String) CODEC(ZSTD(1)),
    `service_name` LowCardinality(String) CODEC(ZSTD(1)),
    `component_name` LowCardinality(String) CODEC(ZSTD(1)),
    `component_type` LowCardinality(String) CODEC(ZSTD(1)),
    `metric_name` LowCardinality(String) CODEC(ZSTD(1)),
    `metric_kind` Enum8('gauge' = 1, 'sum' = 2),
    `metric_unit` LowCardinality(String) CODEC(ZSTD(1)),
    `value` Float64 CODEC(ZSTD(1)),
    `status` LowCardinality(String) CODEC(ZSTD(1)),
    `resource_attributes` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    `metric_attributes` Map(LowCardinality(String), String) CODEC(ZSTD(1)),
    INDEX idx_run_id run_id TYPE bloom_filter(0.01) GRANULARITY 4
)
ENGINE = MergeTree
PARTITION BY toDate(event_time)
ORDER BY (scenario, service_name, metric_name, component_name, event_time, metric_kind)
TTL toDateTime(event_time) + toIntervalDay(30)
SETTINGS index_granularity = 8192, ttl_only_drop_parts = 1;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.metric_observations_gauge_mv
TO silver.metric_observations
AS SELECT
    TimeUnix AS event_time,
    StartTimeUnix AS start_time,
    ResourceAttributes['sentinel.scenario'] AS scenario,
    ResourceAttributes['sentinel.run_id'] AS run_id,
    ResourceAttributes['cloud.provider'] AS cloud_provider,
    lower(ResourceAttributes['sentinel.synthetic']) = 'true' AS is_synthetic,
    ResourceAttributes['contract_version'] AS contract_version,
    ServiceName AS service_name,
    Attributes['component.name'] AS component_name,
    Attributes['component.type'] AS component_type,
    MetricName AS metric_name,
    'gauge' AS metric_kind,
    if(MetricUnit != '', MetricUnit, Attributes['unit']) AS metric_unit,
    Value AS value,
    Attributes['status'] AS status,
    ResourceAttributes AS resource_attributes,
    Attributes AS metric_attributes
FROM bronze.otel_metrics_gauge;

CREATE MATERIALIZED VIEW IF NOT EXISTS silver.metric_observations_sum_mv
TO silver.metric_observations
AS SELECT
    TimeUnix AS event_time,
    StartTimeUnix AS start_time,
    ResourceAttributes['sentinel.scenario'] AS scenario,
    ResourceAttributes['sentinel.run_id'] AS run_id,
    ResourceAttributes['cloud.provider'] AS cloud_provider,
    lower(ResourceAttributes['sentinel.synthetic']) = 'true' AS is_synthetic,
    ResourceAttributes['contract_version'] AS contract_version,
    ServiceName AS service_name,
    Attributes['component.name'] AS component_name,
    Attributes['component.type'] AS component_type,
    MetricName AS metric_name,
    'sum' AS metric_kind,
    if(MetricUnit != '', MetricUnit, Attributes['unit']) AS metric_unit,
    Value AS value,
    Attributes['status'] AS status,
    ResourceAttributes AS resource_attributes,
    Attributes AS metric_attributes
FROM bronze.otel_metrics_sum;

CREATE VIEW IF NOT EXISTS silver.metric_rollup_1m AS
SELECT
    toStartOfMinute(event_time) AS window_start,
    scenario,
    service_name,
    component_name,
    metric_name,
    metric_kind,
    count() AS sample_count,
    sum(value) AS sum_value,
    sum(value * value) AS sum_squares,
    min(value) AS min_value,
    max(value) AS max_value,
    avg(value) AS avg_value,
    stddevPop(value) AS stddev_value
FROM silver.metric_observations
GROUP BY
    window_start,
    scenario,
    service_name,
    component_name,
    metric_name,
    metric_kind;

CREATE VIEW IF NOT EXISTS silver.service_health_1m AS
SELECT
    toStartOfMinute(event_time) AS window_start,
    scenario,
    service_name,
    component_name,
    operation_name,
    count() AS operation_count,
    countIf(is_error) AS error_count,
    error_count / operation_count AS error_rate,
    quantileExact(0.50)(duration_ms) AS latency_p50_ms,
    quantileExact(0.95)(duration_ms) AS latency_p95_ms,
    quantileExact(0.99)(duration_ms) AS latency_p99_ms,
    max(duration_ms) AS latency_max_ms
FROM silver.operation_executions
GROUP BY
    window_start,
    scenario,
    service_name,
    component_name,
    operation_name;

CREATE VIEW IF NOT EXISTS silver.log_health_1m AS
SELECT
    toStartOfMinute(event_time) AS window_start,
    scenario,
    service_name,
    component_name,
    count() AS log_count,
    countIf(is_error) AS error_log_count,
    error_log_count / log_count AS error_log_rate,
    max(severity_number) AS max_severity_number,
    uniqExact(trace_id) AS affected_trace_count
FROM silver.log_events
GROUP BY
    window_start,
    scenario,
    service_name,
    component_name;

CREATE VIEW IF NOT EXISTS silver.trace_summary AS
SELECT
    scenario,
    run_id,
    trace_id,
    min(event_time) AS trace_start,
    max(end_time) AS trace_end,
    dateDiff('microsecond', trace_start, trace_end) / 1000.0 AS trace_duration_ms,
    count() AS span_count,
    countIf(is_error) AS error_span_count,
    error_span_count > 0 AS has_error,
    argMin(service_name, event_time) AS entry_service,
    argMax(service_name, end_time) AS exit_service,
    groupUniqArray(service_name) AS services,
    groupUniqArray(component_name) AS components
FROM silver.operation_executions
WHERE trace_id != ''
GROUP BY
    scenario,
    run_id,
    trace_id;

CREATE VIEW IF NOT EXISTS silver.telemetry_coverage_1m AS
SELECT
    toStartOfMinute(event_time) AS window_start,
    scenario,
    run_id,
    service_name,
    component_name,
    sum(span_count) AS span_count,
    sum(log_count) AS log_count,
    sum(metric_count) AS metric_count,
    uniqExactIf(metric_name, metric_name != '') AS metric_name_count
FROM
(
    SELECT
        event_time,
        scenario,
        run_id,
        service_name,
        component_name,
        '' AS metric_name,
        toUInt64(1) AS span_count,
        toUInt64(0) AS log_count,
        toUInt64(0) AS metric_count
    FROM silver.operation_executions

    UNION ALL

    SELECT
        event_time,
        scenario,
        run_id,
        service_name,
        component_name,
        '' AS metric_name,
        toUInt64(0) AS span_count,
        toUInt64(1) AS log_count,
        toUInt64(0) AS metric_count
    FROM silver.log_events

    UNION ALL

    SELECT
        event_time,
        scenario,
        run_id,
        service_name,
        component_name,
        metric_name,
        toUInt64(0) AS span_count,
        toUInt64(0) AS log_count,
        toUInt64(1) AS metric_count
    FROM silver.metric_observations
)
GROUP BY
    window_start,
    scenario,
    run_id,
    service_name,
    component_name;

CREATE VIEW IF NOT EXISTS silver.run_summary AS
SELECT
    scenario,
    run_id,
    min(event_time) AS run_start,
    max(event_time) AS run_end,
    dateDiff('millisecond', run_start, run_end) AS observed_duration_ms,
    uniqExact(service_name) AS service_count,
    uniqExactIf(trace_id, trace_id != '') AS trace_count,
    sum(operation_count) AS operation_count,
    sum(operation_error_count) AS operation_error_count,
    sum(log_count) AS log_count,
    sum(log_error_count) AS log_error_count,
    sum(metric_count) AS metric_count
FROM
(
    SELECT
        scenario,
        run_id,
        event_time,
        service_name,
        trace_id,
        toUInt64(1) AS operation_count,
        toUInt64(is_error) AS operation_error_count,
        toUInt64(0) AS log_count,
        toUInt64(0) AS log_error_count,
        toUInt64(0) AS metric_count
    FROM silver.operation_executions

    UNION ALL

    SELECT
        scenario,
        run_id,
        event_time,
        service_name,
        trace_id,
        toUInt64(0) AS operation_count,
        toUInt64(0) AS operation_error_count,
        toUInt64(1) AS log_count,
        toUInt64(is_error) AS log_error_count,
        toUInt64(0) AS metric_count
    FROM silver.log_events

    UNION ALL

    SELECT
        scenario,
        run_id,
        event_time,
        service_name,
        '' AS trace_id,
        toUInt64(0) AS operation_count,
        toUInt64(0) AS operation_error_count,
        toUInt64(0) AS log_count,
        toUInt64(0) AS log_error_count,
        toUInt64(1) AS metric_count
    FROM silver.metric_observations
)
GROUP BY
    scenario,
    run_id;
