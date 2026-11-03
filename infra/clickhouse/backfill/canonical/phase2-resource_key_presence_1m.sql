SELECT toStartOfMinute(event_time) AS window_start, service_name,
       CAST('log', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)') AS signal,
       toUInt64(count()) AS rows,
       sumMap(CAST((mapKeys(resource_attributes), arrayResize(CAST([1], 'Array(UInt64)'), length(mapKeys(resource_attributes)), toUInt64(1))), 'Map(String, UInt64)')) AS key_counts
FROM silver.log_events WHERE toDate(event_time) = toDate('__DAY__') GROUP BY window_start, service_name
UNION ALL
SELECT toStartOfMinute(event_time), service_name,
       CAST('trace', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)'), toUInt64(count()),
       sumMap(CAST((mapKeys(resource_attributes), arrayResize(CAST([1], 'Array(UInt64)'), length(mapKeys(resource_attributes)), toUInt64(1))), 'Map(String, UInt64)'))
FROM silver.operation_executions WHERE toDate(event_time) = toDate('__DAY__') GROUP BY toStartOfMinute(event_time), service_name
UNION ALL
SELECT toStartOfMinute(event_time), service_name,
       CAST('metric', 'Enum8(\'log\' = 1, \'trace\' = 2, \'metric\' = 3)'), toUInt64(count()),
       sumMap(CAST((mapKeys(resource_attributes), arrayResize(CAST([1], 'Array(UInt64)'), length(mapKeys(resource_attributes)), toUInt64(1))), 'Map(String, UInt64)'))
FROM silver.metric_observations WHERE toDate(event_time) = toDate('__DAY__') GROUP BY toStartOfMinute(event_time), service_name
