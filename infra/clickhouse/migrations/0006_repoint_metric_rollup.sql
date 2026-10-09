-- A fresh silver.metric_stats_1m is empty until base partitions have been
-- recomputed. Keep the existing public view on the raw observations until the
-- backfill ledger proves phase 2 for every currently present base partition.
SELECT concat('0006 missing metric_stats_1m phase-2 partitions: ',
              arrayStringConcat(groupArrayIf(partition, NOT phase2_done), ', '))
FROM
(
    SELECT p.partition,
           countIf(r.status = 'ok') > 0 AS phase2_done
    FROM
    (
        SELECT DISTINCT partition
        FROM system.parts
        WHERE active AND database = 'silver' AND table = 'metric_observations'
    ) AS p
    LEFT JOIN _meta.backfill_runs AS r
        ON r.phase = 'phase2'
       AND r.target_table = 'silver.metric_stats_1m'
       AND r.partition_id = p.partition
    GROUP BY p.partition
)
HAVING countIf(NOT phase2_done) > 0;

SELECT throwIf(countIf(NOT phase2_done) > 0,
               '0006 refused: metric_stats_1m backfill is incomplete')
FROM
(
    SELECT p.partition,
           countIf(r.status = 'ok') > 0 AS phase2_done
    FROM
    (
        SELECT DISTINCT partition
        FROM system.parts
        WHERE active AND database = 'silver' AND table = 'metric_observations'
    ) AS p
    LEFT JOIN _meta.backfill_runs AS r
        ON r.phase = 'phase2'
       AND r.target_table = 'silver.metric_stats_1m'
       AND r.partition_id = p.partition
    GROUP BY p.partition
);

CREATE OR REPLACE VIEW silver.metric_rollup_1m AS
WITH stats AS
(
    SELECT
        window_start,
        scenario,
        service_name,
        component_name,
        metric_name,
        metric_kind,
        sum(sample_count) AS sample_count,
        sum(sum_value) AS sum_value,
        sum(sum_squares) AS sum_squares,
        toFloat64(min(min_value)) AS min_value,
        toFloat64(max(max_value)) AS max_value
    FROM silver.metric_stats_1m
    GROUP BY
        window_start,
        scenario,
        service_name,
        component_name,
        metric_name,
        metric_kind
)
SELECT
    window_start,
    scenario,
    service_name,
    component_name,
    metric_name,
    metric_kind,
    sample_count,
    sum_value,
    sum_squares,
    min_value,
    max_value,
    sum_value / sample_count AS avg_value,
    sqrt(greatest(0., sum_squares / sample_count - (sum_value / sample_count) * (sum_value / sample_count))) AS stddev_value
FROM stats;
