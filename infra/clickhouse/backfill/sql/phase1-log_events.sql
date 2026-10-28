SELECT Timestamp AS event_time,
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
       Body AS body, TraceId AS trace_id, SpanId AS span_id,
       ResourceAttributes AS resource_attributes, LogAttributes AS log_attributes
FROM bronze.otel_logs
WHERE TimestampDate = toDate('__DAY__')
