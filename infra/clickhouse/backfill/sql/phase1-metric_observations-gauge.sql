SELECT TimeUnix AS event_time, StartTimeUnix AS start_time,
       ResourceAttributes['sentinel.scenario'] AS scenario,
       ResourceAttributes['sentinel.run_id'] AS run_id,
       ResourceAttributes['cloud.provider'] AS cloud_provider,
       lower(ResourceAttributes['sentinel.synthetic']) = 'true' AS is_synthetic,
       ResourceAttributes['contract_version'] AS contract_version,
       ServiceName AS service_name, Attributes['component.name'] AS component_name,
       Attributes['component.type'] AS component_type, MetricName AS metric_name,
       'gauge' AS metric_kind,
       if(MetricUnit != '', MetricUnit, Attributes['unit']) AS metric_unit,
       Value AS value, Attributes['status'] AS status,
       ResourceAttributes AS resource_attributes, Attributes AS metric_attributes
FROM bronze.otel_metrics_gauge
WHERE toDate(TimeUnix) = toDate('__DAY__')
