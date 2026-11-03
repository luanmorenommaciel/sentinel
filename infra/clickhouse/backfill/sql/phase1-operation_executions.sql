SELECT Timestamp AS event_time,
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
       TraceId AS trace_id, SpanId AS span_id, ParentSpanId AS parent_span_id,
       Duration / 1000000.0 AS duration_ms,
       StatusCode AS status_code, StatusCode = 'Error' AS is_error,
       ResourceAttributes AS resource_attributes, SpanAttributes AS operation_attributes
FROM bronze.otel_traces
WHERE toDate(Timestamp) = toDate('__DAY__')
