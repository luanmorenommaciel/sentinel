-- Representative rows from the Watcher read models (T25). Read-only; safe to run
-- against a populated local stack after `make e2e && make migrate`.

SELECT '── metric_stats_1m: the z-score INPUT, not a z-score ──' AS section FORMAT TSVRaw;
SELECT window_start, service_name, metric_name, metric_kind,
       sum(sample_count) AS samples,
       round(sum(sum_value) / sum(sample_count), 4) AS avg_value,
       round(sqrt(greatest(0, sum(sum_squares) / sum(sample_count)
                              - pow(sum(sum_value) / sum(sample_count), 2))), 4) AS stddev_value,
       min(min_value) AS min_value, max(max_value) AS max_value
FROM silver.metric_stats_1m
GROUP BY window_start, service_name, metric_name, metric_kind
ORDER BY window_start DESC, service_name, metric_name
LIMIT 10;

SELECT '── volume_1m: rows per minute per producer per signal ──' AS section FORMAT TSVRaw;
SELECT window_start, service_name, signal, sum(rows) AS rows
FROM silver.volume_1m
GROUP BY window_start, service_name, signal
ORDER BY window_start DESC, service_name, signal
LIMIT 10;

SELECT '── resource_key_presence_1m: rows missing each key ──' AS section FORMAT TSVRaw;
-- `rows - key_counts[k]` is rows missing key k. The SUM over k is NOT the number of
-- bad rows: a row missing four keys is one bad row, not four.
SELECT service_name, signal, rows, key,
       rows - key_counts[key] AS rows_missing_key
FROM
(
    SELECT service_name, signal,
           sum(rows) AS rows,
           sumMap(key_counts) AS key_counts
    FROM silver.resource_key_presence_1m
    GROUP BY service_name, signal
)
ARRAY JOIN mapKeys(key_counts) AS key
ORDER BY service_name, signal, key
LIMIT 15;

SELECT '── call_edges_1m: src → dst, trailing 24h ──' AS section FORMAT TSVRaw;
SELECT window_start, src_service, dst_service, spans, errors
FROM silver.call_edges_1m
ORDER BY window_start DESC, spans DESC
LIMIT 10;
