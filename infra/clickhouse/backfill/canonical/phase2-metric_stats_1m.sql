SELECT toStartOfMinute(event_time) AS window_start, scenario, service_name,
       component_name, metric_name, metric_kind,
       toUInt64(count()) AS sample_count, sum(value) AS sum_value,
       sum(value * value) AS sum_squares, min(value) AS min_value, max(value) AS max_value
FROM silver.metric_observations
WHERE toDate(event_time) = toDate('__DAY__')
GROUP BY window_start, scenario, service_name, component_name, metric_name, metric_kind
