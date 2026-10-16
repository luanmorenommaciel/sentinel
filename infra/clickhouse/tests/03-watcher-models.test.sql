-- Silver Watcher read-model assertions (T25-T29).
--
-- Every check is a `throwIf`, so the file is its own test runner: it exits non-zero
-- on the first violation and names it. Run by `make test-silver` alongside
-- 02-silver-layer.sql's 18 assertions, which must stay unchanged and silent
-- (REQ-D-09) — this file adds to that set and alters nothing in it.

-- ════════════════════════════════════════════════════════════════════════════
-- T25 — metric_stats_1m
-- ════════════════════════════════════════════════════════════════════════════

-- The rollup must account for every observation, with nothing double-counted.
-- This is the one assertion that would catch a broken chained-MV firing ([V-1]).
SELECT throwIf(
    (SELECT sum(sample_count) FROM silver.metric_stats_1m)
      != (SELECT count() FROM silver.metric_observations),
    'T25: sum(sample_count) != count(metric_observations) — the rollup lost or duplicated rows'
);

-- The stddev computed from sum_squares must agree with stddevPop over the raw
-- observations. 1e-9 is not slack for sloppiness: it pins `0006`'s greatest(0, …)
-- guard, because on a near-constant series catastrophic cancellation in
-- E[x²] − E[x]² can go marginally negative where stddevPop cannot.
SELECT throwIf(
    (
        SELECT max(abs(from_rollup - from_raw))
        FROM
        (
            SELECT
                s.window_start, s.service_name, s.metric_name,
                r.from_raw,
                sqrt(greatest(0, s.sum_squares / s.sample_count
                                 - pow(s.sum_value / s.sample_count, 2))) AS from_rollup
            FROM
            (
                SELECT window_start, service_name, metric_name,
                       sum(sample_count) AS sample_count,
                       sum(sum_value)    AS sum_value,
                       sum(sum_squares)  AS sum_squares
                FROM silver.metric_stats_1m
                GROUP BY window_start, service_name, metric_name
            ) AS s
            INNER JOIN
            (
                SELECT toStartOfMinute(event_time) AS window_start,
                       service_name, metric_name,
                       stddevPop(value) AS from_raw
                FROM silver.metric_observations
                GROUP BY window_start, service_name, metric_name
            ) AS r
            USING (window_start, service_name, metric_name)
        )
    ) > 1e-9,
    'T25: stddev from sum_squares disagrees with stddevPop by more than 1e-9'
);

-- ════════════════════════════════════════════════════════════════════════════
-- T26 — the real-telemetry tripwire (REQ-H-11)
-- ════════════════════════════════════════════════════════════════════════════
-- The baseline's strongest compliance fact is that all data is synthetic, and
-- nothing else in the system would flag the transition. `is_synthetic` already
-- exists on all three base tables, so this is one predicate each — nearly free
-- now, unaffordable to retrofit after the first real-telemetry swap.
--
-- When this fires it is not necessarily a bug. It means real telemetry has entered
-- a system whose compliance posture assumes it has not.
SELECT throwIf(
    (SELECT countIf(NOT is_synthetic) FROM silver.operation_executions) != 0,
    'T26 TRIPWIRE: non-synthetic rows in silver.operation_executions'
);
SELECT throwIf(
    (SELECT countIf(NOT is_synthetic) FROM silver.log_events) != 0,
    'T26 TRIPWIRE: non-synthetic rows in silver.log_events'
);
SELECT throwIf(
    (SELECT countIf(NOT is_synthetic) FROM silver.metric_observations) != 0,
    'T26 TRIPWIRE: non-synthetic rows in silver.metric_observations'
);

-- ════════════════════════════════════════════════════════════════════════════
-- T27 — volume_1m
-- ════════════════════════════════════════════════════════════════════════════
-- Per producer, per signal, the rollup must equal the base table's row count.
-- Checked per producer rather than in total: a total would hide two services'
-- errors cancelling out.
SELECT throwIf(
    (
        SELECT count()
        FROM
        (
            SELECT service_name, sum(rows) AS n
            FROM silver.volume_1m WHERE signal = 'log' GROUP BY service_name
        ) AS v
        FULL OUTER JOIN
        (
            SELECT service_name, count() AS n FROM silver.log_events GROUP BY service_name
        ) AS b
        USING (service_name)
        WHERE v.n != b.n
    ) != 0,
    'T27: volume_1m log rows disagree with silver.log_events for at least one producer'
);
SELECT throwIf(
    (
        SELECT count()
        FROM
        (
            SELECT service_name, sum(rows) AS n
            FROM silver.volume_1m WHERE signal = 'trace' GROUP BY service_name
        ) AS v
        FULL OUTER JOIN
        (
            SELECT service_name, count() AS n FROM silver.operation_executions GROUP BY service_name
        ) AS b
        USING (service_name)
        WHERE v.n != b.n
    ) != 0,
    'T27: volume_1m trace rows disagree with silver.operation_executions for at least one producer'
);
SELECT throwIf(
    (
        SELECT count()
        FROM
        (
            SELECT service_name, sum(rows) AS n
            FROM silver.volume_1m WHERE signal = 'metric' GROUP BY service_name
        ) AS v
        FULL OUTER JOIN
        (
            SELECT service_name, count() AS n FROM silver.metric_observations GROUP BY service_name
        ) AS b
        USING (service_name)
        WHERE v.n != b.n
    ) != 0,
    'T27: volume_1m metric rows disagree with silver.metric_observations for at least one producer'
);

-- ════════════════════════════════════════════════════════════════════════════
-- T28 — resource_key_presence_1m
-- ════════════════════════════════════════════════════════════════════════════
-- No key can be present on more rows than exist. Checked for EVERY key via an
-- ARRAY JOIN over the map, not for a fixed list — the table is key-list agnostic
-- and a list here would be the third copy of one (REQ-D-06).
SELECT throwIf(
    (
        SELECT countIf(cnt > rows)
        FROM
        (
            SELECT rows, arrayJoin(mapValues(key_counts)) AS cnt
            FROM
            (
                SELECT window_start, service_name, signal,
                       sum(rows) AS rows, sumMap(key_counts) AS key_counts
                FROM silver.resource_key_presence_1m
                GROUP BY window_start, service_name, signal
            )
        )
    ) != 0,
    'T28: a key_counts entry exceeds the row count for its window'
);

-- The rollup's view of a missing key must equal bronze's. `service.name` is the
-- probe key because Pod 1 guarantees it on every signal, so the expected answer is
-- zero and any drift is real.
--
-- NOTE on what this does NOT assert: `rows - key_counts[k]` is rows missing key k,
-- and the sum over k is NOT the number of bad rows — a row missing four keys is one
-- bad row, not four. Reporting the sum once made a producer missing 4 of 5 keys
-- read "80%". `countIf(NOT has_all)` cannot be reconstructed from key_counts, which
-- is why the contract board keeps its bronze source for that column.
SELECT throwIf(
    (
        SELECT sum(rows) - sum(key_counts['service.name'])
        FROM silver.resource_key_presence_1m
    ) != (
        SELECT countIf(NOT mapContains(ResourceAttributes, 'service.name'))
        FROM bronze.otel_logs
    ) + (
        SELECT countIf(NOT mapContains(ResourceAttributes, 'service.name'))
        FROM bronze.otel_traces
    ) + (
        SELECT countIf(NOT mapContains(ResourceAttributes, 'service.name'))
        FROM bronze.otel_metrics_gauge
    ) + (
        SELECT countIf(NOT mapContains(ResourceAttributes, 'service.name'))
        FROM bronze.otel_metrics_sum
    ),
    'T28: rollup rows-missing-service.name disagrees with the bronze probe'
);

-- ════════════════════════════════════════════════════════════════════════════
-- T29 — call_edges_1m
-- ════════════════════════════════════════════════════════════════════════════
-- Non-emptiness first, so none of the checks below can pass vacuously. An empty
-- call_edges_1m satisfies every assertion that follows, which would make a broken
-- refresh look like a clean run. `make test-silver` refreshes the view before
-- running this file precisely so this assertion is meaningful.
SELECT throwIf(
    (SELECT count() FROM silver.call_edges_1m) = 0,
    'T29: call_edges_1m is empty — the refresh did not run, so the checks below prove nothing'
);

-- A service cannot call itself in this model: `parent_span_id != ''` with a join on
-- (trace_id, parent_span_id) means src and dst are different spans, and the
-- topology DAG has no self-loops. A self-edge means the join collapsed.
SELECT throwIf(
    (SELECT count() FROM silver.call_edges_1m WHERE src_service = dst_service) != 0,
    'T29: self-edges in call_edges_1m — the join collapsed src into dst'
);

-- Every generated dependency edge must belong to the topology's declared DAG.
-- In particular, span IDs repeat across runs, so joining without trace_id can
-- invent plausible-looking cross-run service pairs that a self-edge check misses.
SELECT throwIf(
    (
        SELECT count()
        FROM silver.call_edges_1m
        WHERE tuple(src_service, dst_service) NOT IN
        [
            ('cloud-composer-etl', 'dataproc-spark-batch'),
            ('pubsub-ingestion-topic', 'dataproc-spark-batch'),
            ('pubsub-ingestion-topic', 'dataproc-spark-streaming'),
            ('dataproc-spark-batch', 'gcs-raw-bucket'),
            ('dataproc-spark-batch', 'gcs-processed-bucket'),
            ('dataproc-spark-streaming', 'gcs-processed-bucket'),
            ('dataproc-spark-batch', 'k8s-api-gateway'),
            ('dataproc-spark-streaming', 'k8s-api-gateway')
        ]
    ) != 0,
    'T29: call_edges_1m contains an edge absent from topology/default.yaml'
);

-- The 27.6x fan-out guard, as a number. Without the GROUP BY (trace_id, span_id)
-- collapse, a 15-minute window produced 445,229 joined rows from 16,154 children.
-- Total spans across edges cannot exceed the child spans that could have produced
-- them: every edge row counts children with a non-empty parent_span_id.
SELECT throwIf(
    (SELECT sum(spans) FROM silver.call_edges_1m)
      > (SELECT countIf(parent_span_id != '') FROM silver.operation_executions),
    'T29: sum(spans) exceeds the number of child spans — fan-out regression'
);

-- Errors are a subset of spans, per edge.
SELECT throwIf(
    (SELECT countIf(errors > spans) FROM silver.call_edges_1m) != 0,
    'T29: an edge reports more errors than spans'
);
