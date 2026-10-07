#!/usr/bin/env bash
# Local MergeTree backfill runner. The managed-provider REPLACE PARTITION probe
# remains deferred (see plan/decisions/DEC-A2.md).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FROM_DATE=""
TO_DATE=""
PHASE=all

for arg in "$@"; do
    case "$arg" in
        FROM=*) FROM_DATE="${arg#FROM=}" ;;
        TO=*) TO_DATE="${arg#TO=}" ;;
        PHASE=*) PHASE="${arg#PHASE=}" ;;
        *) printf 'backfill: unexpected argument: %s\n' "$arg" >&2; exit 1 ;;
    esac
done

[[ -z "$FROM_DATE" || "$FROM_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || {
    echo 'backfill: FROM must be YYYY-MM-DD' >&2; exit 1;
}
[[ -z "$TO_DATE" || "$TO_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || {
    echo 'backfill: TO must be YYYY-MM-DD' >&2; exit 1;
}
[[ "$PHASE" == all || "$PHASE" == 1 || "$PHASE" == 2 ]] || {
    echo 'backfill: PHASE must be 1, 2, or all' >&2; exit 1;
}

# shellcheck disable=SC2206
CLIENT=(${CH_CLIENT:-clickhouse-client})
ch() { "${CLIENT[@]}" --multiquery; }
query() { printf '%s\n' "$1" | ch; }
record_status() {
    local phase="$1" target="$2" partition="$3" before="$4" after="$5" written="$6" hash="$7" expected="$8" status="$9"
    query "INSERT INTO _meta.backfill_runs (run_id, phase, target_table, partition_id, bronze_rows_before, bronze_rows_after, silver_rows_written, content_hash, expected_hash, started_at, finished_at, status) VALUES ('$RUN_ID', '$phase', '$target', '$partition', $before, $after, $written, $hash, $expected, now(), now(), '$status')" >/dev/null
}

if ! TODAY="$(query 'SELECT toString(today()) FORMAT TSV')"; then
    echo 'backfill: cannot reach ClickHouse' >&2; exit 2
fi
YESTERDAY="$(query 'SELECT toString(today() - 1) FORMAT TSV')"
FROM_DATE="${FROM_DATE:-$YESTERDAY}"
TO_DATE="${TO_DATE:-$YESTERDAY}"

[[ "$FROM_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ && "$TO_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || {
    echo 'backfill: FROM and TO must be YYYY-MM-DD' >&2; exit 1;
}
[[ "$FROM_DATE" < "$TO_DATE" || "$FROM_DATE" == "$TO_DATE" ]] || {
    echo 'backfill: FROM must be on or before TO' >&2; exit 1;
}
[[ "$PHASE" == all || "$PHASE" == 1 || "$PHASE" == 2 ]] || {
    echo 'backfill: PHASE must be 1, 2, or all' >&2; exit 1;
}

RUN_ID="$(query 'SELECT toString(generateUUIDv4()) FORMAT TSV')"

# There is deliberately no live-partition override. Record the refusal before
# returning, and do not issue any Silver INSERT on this path.
if [[ "$TO_DATE" > "$TODAY" || "$TO_DATE" == "$TODAY" ]]; then
    printf 'backfill: live partition range refused (TO=%s, today=%s)\n' "$TO_DATE" "$TODAY" >&2
    query "INSERT INTO _meta.backfill_runs (run_id, phase, target_table, partition_id, bronze_rows_before, bronze_rows_after, silver_rows_written, content_hash, expected_hash, started_at, finished_at, status) VALUES ('$RUN_ID', 'phase1', 'silver.log_events', '$TO_DATE', 0, 0, 0, 0, 0, now(), now(), 'refused')" >/dev/null
    exit 1
fi

run_phase1() {
    local table source sql canonical_sql metric_part count_before count_after rows actual expected days day_query
    day_query="SELECT DISTINCT toString(day)
FROM
(
    SELECT toDate(Timestamp) AS day
    FROM bronze.otel_logs
    WHERE day BETWEEN toDate('$FROM_DATE') AND toDate('$TO_DATE')
      AND toYYYYMM(day) IN (SELECT toUInt32(partition) FROM system.parts WHERE active AND database='bronze' AND table='otel_logs')
    UNION DISTINCT
    SELECT toDate(Timestamp) AS day
    FROM bronze.otel_traces
    WHERE day BETWEEN toDate('$FROM_DATE') AND toDate('$TO_DATE')
      AND toString(day) IN (SELECT partition FROM system.parts WHERE active AND database='bronze' AND table='otel_traces')
    UNION DISTINCT
    SELECT toDate(TimeUnix) AS day
    FROM bronze.otel_metrics_gauge
    WHERE day BETWEEN toDate('$FROM_DATE') AND toDate('$TO_DATE')
      AND toString(day) IN (SELECT partition FROM system.parts WHERE active AND database='bronze' AND table='otel_metrics_gauge')
    UNION DISTINCT
    SELECT toDate(TimeUnix) AS day
    FROM bronze.otel_metrics_sum
    WHERE day BETWEEN toDate('$FROM_DATE') AND toDate('$TO_DATE')
      AND toString(day) IN (SELECT partition FROM system.parts WHERE active AND database='bronze' AND table='otel_metrics_sum')
)
ORDER BY day FORMAT TSV"
    days="$(query "$day_query")" || return 2
    for table in log_events operation_executions metric_observations; do
        case "$table" in
            log_events) source=otel_logs ;;
            operation_executions) source=otel_traces ;;
            metric_observations) source=otel_metrics_gauge ;;
        esac
        while IFS= read -r day; do
                [[ -n "$day" ]] || continue
                if ! query "SELECT count() FROM system.tables WHERE database='silver' AND name='$table' FORMAT TSV" | grep -qx 1; then
                    echo "backfill: silver.$table is absent" >&2; return 1
                fi
                local phase_sql="$script_dir/sql/phase1-$table.sql"
                if [[ "$table" == metric_observations ]]; then
                    [[ -r "$script_dir/sql/phase1-metric_observations-gauge.sql" && -r "$script_dir/sql/phase1-metric_observations-sum.sql" ]] || { echo 'backfill: metric phase-1 SQL templates are missing' >&2; return 1; }
                else
                    [[ -r "$phase_sql" ]] || { echo "backfill: missing $phase_sql" >&2; return 1; }
                fi
                case "$table" in
                    log_events) count_before="$(query "SELECT count() FROM bronze.otel_logs WHERE TimestampDate=toDate('$day') FORMAT TSV")" ;;
                    operation_executions) count_before="$(query "SELECT count() FROM bronze.otel_traces WHERE toDate(Timestamp)=toDate('$day') FORMAT TSV")" ;;
                    metric_observations) count_before="$(query "SELECT (SELECT count() FROM bronze.otel_metrics_gauge WHERE toDate(TimeUnix)=toDate('$day')) + (SELECT count() FROM bronze.otel_metrics_sum WHERE toDate(TimeUnix)=toDate('$day')) FORMAT TSV")" ;;
                esac
                record_status phase1 "silver.$table" "$day" "$count_before" "$count_before" 0 0 0 running
                if [[ "$count_before" == 0 ]]; then
                    record_status phase1 "silver.$table" "$day" 0 0 0 0 0 ok
                    continue
                fi
                query "CREATE TABLE IF NOT EXISTS silver.${table}__bf AS silver.$table" >/dev/null
                query "CREATE TABLE IF NOT EXISTS silver.${table}__expected AS silver.$table" >/dev/null
                query "ALTER TABLE silver.${table}__bf DROP PARTITION '$day'" >/dev/null
                query "ALTER TABLE silver.${table}__expected DROP PARTITION '$day'" >/dev/null
                if [[ "$table" == metric_observations ]]; then
                    for metric_part in gauge sum; do
                        sql="$(sed "s|__DAY__|$day|g" "$script_dir/sql/phase1-metric_observations-$metric_part.sql")"
                        canonical_sql="$(sed "s|__DAY__|$day|g" "$script_dir/canonical/phase1-metric_observations-$metric_part.sql")"
                        printf '%s\n' "INSERT INTO silver.metric_observations__bf $sql" | ch >/dev/null
                        printf '%s\n' "INSERT INTO silver.metric_observations__expected $canonical_sql" | ch >/dev/null
                    done
                else
                    sql="$(sed "s|__DAY__|$day|g" "$phase_sql")"
                    canonical_sql="$(sed "s|__DAY__|$day|g" "$script_dir/canonical/phase1-$table.sql")"
                    printf '%s\n' "INSERT INTO silver.${table}__bf $sql" | ch >/dev/null
                    printf '%s\n' "INSERT INTO silver.${table}__expected $canonical_sql" | ch >/dev/null
                fi
                rows="$(query "SELECT count() FROM silver.${table}__bf WHERE toDate(event_time)=toDate('$day') FORMAT TSV")"
                actual="$(query "SELECT ifNull(sum(cityHash64(*)),0) FROM silver.${table}__bf WHERE toDate(event_time)=toDate('$day') FORMAT TSV")"
                expected="$(query "SELECT ifNull(sum(cityHash64(*)),0) FROM silver.${table}__expected WHERE toDate(event_time)=toDate('$day') FORMAT TSV")"
                case "$table" in
                    log_events) count_after="$(query "SELECT count() FROM bronze.otel_logs WHERE TimestampDate=toDate('$day') FORMAT TSV")" ;;
                    operation_executions) count_after="$(query "SELECT count() FROM bronze.otel_traces WHERE toDate(Timestamp)=toDate('$day') FORMAT TSV")" ;;
                    metric_observations) count_after="$(query "SELECT (SELECT count() FROM bronze.otel_metrics_gauge WHERE toDate(TimeUnix)=toDate('$day')) + (SELECT count() FROM bronze.otel_metrics_sum WHERE toDate(TimeUnix)=toDate('$day')) FORMAT TSV")" ;;
                esac
                if [[ "$actual" != "$expected" ]]; then
                    echo "backfill: content checksum mismatch for silver.$table partition $day: $actual != $expected" >&2
                    record_status phase1 "silver.$table" "$day" "$count_before" "$count_after" "$rows" "$actual" "$expected" failed
                    return 1
                fi
                # Validate staging schema against its target before the atomic swap.
                query "SELECT throwIf((SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='${table}__bf') != (SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='$table'), 'backfill: staging structure differs for silver.$table')" >/dev/null
                query "SELECT throwIf((SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='${table}__expected') != (SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='$table'), 'backfill: expected structure differs for silver.$table')" >/dev/null
                if [[ "$count_after" != "$count_before" ]]; then
                    echo "backfill: bronze.$source changed during partition $day" >&2
                    record_status phase1 "silver.$table" "$day" "$count_before" "$count_after" "$rows" "$actual" "$expected" failed
                    return 1
                fi
                query "ALTER TABLE silver.$table REPLACE PARTITION '$day' FROM silver.${table}__bf" >/dev/null
                query "ALTER TABLE silver.${table}__bf DROP PARTITION '$day'" >/dev/null
                query "ALTER TABLE silver.${table}__expected DROP PARTITION '$day'" >/dev/null
                record_status phase1 "silver.$table" "$day" "$count_before" "$count_after" "$rows" "$actual" "$expected" ok
                printf 'backfill: phase1 silver.%s partition %s rows=%s checksum=%s\n' "$table" "$day" "$rows" "$actual"
        done <<< "$days"
    done
}

run_phase2() {
    local table partition sql canonical_sql rows hash expected phase1 days
    for table in metric_stats_1m volume_1m resource_key_presence_1m; do
        days="$(query "SELECT DISTINCT partition FROM system.parts WHERE active AND database='silver' AND table IN ('log_events','operation_executions','metric_observations') AND partition BETWEEN '$FROM_DATE' AND '$TO_DATE' ORDER BY partition FORMAT TSV")" || return 2
        while IFS= read -r partition; do
            [[ -n "$partition" ]] || continue
            phase1="$(query "SELECT uniqExact(target_table) FROM _meta.backfill_runs WHERE phase='phase1' AND partition_id='$partition' AND status='ok' AND target_table IN ('silver.log_events','silver.operation_executions','silver.metric_observations') FORMAT TSV")"
            if [[ "$phase1" != 3 ]]; then
                echo "backfill: phase2 partition $partition has no completed phase1 row" >&2
                record_status phase2 "silver.$table" "$partition" 0 0 0 0 0 refused
                return 1
            fi
            query "CREATE TABLE IF NOT EXISTS silver.${table}__bf AS silver.$table" >/dev/null
            query "CREATE TABLE IF NOT EXISTS silver.${table}__expected AS silver.$table" >/dev/null
            query "ALTER TABLE silver.${table}__bf DROP PARTITION '$partition'" >/dev/null
            query "ALTER TABLE silver.${table}__expected DROP PARTITION '$partition'" >/dev/null
            sql="$(sed "s|__DAY__|$partition|g" "$script_dir/sql/phase2-$table.sql")"
            canonical_sql="$(sed "s|__DAY__|$partition|g" "$script_dir/canonical/phase2-$table.sql")"
            printf '%s\n' "INSERT INTO silver.${table}__bf $sql" | ch >/dev/null
            printf '%s\n' "INSERT INTO silver.${table}__expected $canonical_sql" | ch >/dev/null
            rows="$(query "SELECT count() FROM silver.${table}__bf WHERE toDate(window_start)=toDate('$partition') FORMAT TSV")"
            hash="$(query "SELECT ifNull(sum(cityHash64(*)),0) FROM silver.${table}__bf WHERE toDate(window_start)=toDate('$partition') FORMAT TSV")"
            expected="$(query "SELECT ifNull(sum(cityHash64(*)),0) FROM silver.${table}__expected WHERE toDate(window_start)=toDate('$partition') FORMAT TSV")"
            if [[ "$hash" != "$expected" ]]; then
                echo "backfill: content checksum mismatch for silver.$table partition $partition: $hash != $expected" >&2
                record_status phase2 "silver.$table" "$partition" 0 0 "$rows" "$hash" "$expected" failed
                return 1
            fi
            query "SELECT throwIf((SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='${table}__bf') != (SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='$table'), 'backfill: staging structure differs for silver.$table')" >/dev/null
            query "SELECT throwIf((SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='${table}__expected') != (SELECT arraySort(groupArray((name,type))) FROM system.columns WHERE database='silver' AND table='$table'), 'backfill: expected structure differs for silver.$table')" >/dev/null
            query "ALTER TABLE silver.$table REPLACE PARTITION '$partition' FROM silver.${table}__bf" >/dev/null
            query "ALTER TABLE silver.${table}__bf DROP PARTITION '$partition'" >/dev/null
            query "ALTER TABLE silver.${table}__expected DROP PARTITION '$partition'" >/dev/null
            record_status phase2 "silver.$table" "$partition" 0 0 "$rows" "$hash" "$expected" ok
            printf 'backfill: phase2 silver.%s partition %s rows=%s checksum=%s\n' "$table" "$partition" "$rows" "$hash"
        done <<< "$days"
    done
}

if [[ "$PHASE" == 1 || "$PHASE" == all ]]; then
    run_phase1
fi
if [[ "$PHASE" == 2 || "$PHASE" == all ]]; then
    run_phase2
fi
