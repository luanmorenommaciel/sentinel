import type { ClickHouseClient } from '@clickhouse/client';
import type { Filter, Repository } from './app';
import { computeHourChange } from './hourCompare';

/** Allowlisted span attribute: service topology type. */
const COMPONENT_TYPE = `if(SpanAttributes['component.type'] = '', 'unknown', SpanAttributes['component.type'])`;

/** Allowlisted ResourceAttributes cloud keys (explicit business fields). */
const CLOUD_PROVIDER = `if(ResourceAttributes['cloud.provider'] = '', 'unknown', ResourceAttributes['cloud.provider'])`;
const CLOUD_REGION = `if(ResourceAttributes['cloud.region'] = '', 'unknown', ResourceAttributes['cloud.region'])`;
const CLOUD_ZONE = `if(ResourceAttributes['cloud.availability_zone'] = '', 'unknown', ResourceAttributes['cloud.availability_zone'])`;
const CLOUD_PLATFORM = `if(ResourceAttributes['cloud.platform'] = '', 'unknown', ResourceAttributes['cloud.platform'])`;
const CLOUD_ACCOUNT = `if(ResourceAttributes['cloud.account.id'] = '', 'unknown', ResourceAttributes['cloud.account.id'])`;

const predicate = `StatusCode = 'Error' AND Timestamp >= parseDateTime64BestEffort({from:String}, 9) AND Timestamp < parseDateTime64BestEffort({to:String}, 9) AND ({service:String} = '' OR ServiceName = {service:String}) AND ({span:String} = '' OR SpanName = {span:String})`;
const parameters = (q: Filter) => ({ from: q.from, to: q.to, service: q.service ?? '', span: q.span ?? '', offset: (q.page - 1) * 50 });

export function buildSpanQuery(q: Filter) {
  return {
    sql: `SELECT formatDateTime(Timestamp, '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC') AS timestamp, ServiceName AS serviceName, SpanName AS spanName, StatusCode AS statusCode, toString(Duration) AS durationNs, TraceId AS traceId, SpanId AS spanId, ${COMPONENT_TYPE} AS componentType, ${CLOUD_PROVIDER} AS cloudProvider, ${CLOUD_REGION} AS cloudRegion, ${CLOUD_ZONE} AS cloudAvailabilityZone, ${CLOUD_PLATFORM} AS cloudPlatform, ${CLOUD_ACCOUNT} AS cloudAccountId FROM bronze.otel_traces WHERE ${predicate} ORDER BY Timestamp DESC, TraceId DESC, SpanId DESC LIMIT 50 OFFSET {offset:UInt32}`,
    params: parameters(q),
  };
}

export function buildTypesQuery(q: Filter) {
  return {
    sql: `SELECT ${COMPONENT_TYPE} AS name, count() AS count FROM bronze.otel_traces WHERE ${predicate} GROUP BY name ORDER BY count DESC, name ASC`,
    params: parameters(q),
  };
}

export function buildCloudGroupQuery(q: Filter, expr: string) {
  return {
    sql: `SELECT ${expr} AS name, count() AS count FROM bronze.otel_traces WHERE ${predicate} GROUP BY name ORDER BY count DESC, name ASC LIMIT 20`,
    params: parameters(q),
  };
}

export function createRepository(client: ClickHouseClient): Repository {
  async function rows<T>(query: string, q: Filter, extra = {}): Promise<T[]> {
    const response = await client.query({ query, query_params: { ...parameters(q), ...extra }, format: 'JSONEachRow' });
    return response.json<T>();
  }
  async function count(q: Filter) {
    const result = await rows<{ count: string }>(`SELECT count() AS count FROM bronze.otel_traces WHERE ${predicate}`, q);
    return Number(result[0]?.count ?? 0);
  }
  async function countWindow(q: Filter, fromIso: string, toIso: string) {
    return count({ ...q, from: fromIso, to: toIso, page: 1 });
  }
  async function namedCounts(q: Filter, expr: string) {
    const query = buildCloudGroupQuery(q, expr);
    const data = await rows<{ name: string; count: string }>(query.sql, q);
    return data.map((row) => ({ name: row.name, count: Number(row.count) }));
  }
  return {
    async spans(q) {
      const query = buildSpanQuery(q);
      const [total, items] = await Promise.all([count(q), rows<any>(query.sql, q)]);
      return { total, items };
    },
    async overview(q) {
      const duration = Date.parse(q.to) - Date.parse(q.from);
      const bucketSeconds = duration <= 3600000 ? 60 : duration <= 86400000 ? 3600 : duration <= 7 * 86400000 ? 21600 : 86400;
      const typesQuery = buildTypesQuery(q);
      const endMs = Date.parse(q.to);
      const lastFrom = new Date(endMs - 3600000).toISOString();
      const prevFrom = new Date(endMs - 7200000).toISOString();
      const prevTo = lastFrom;

      const [total, trend, services, types, lastHour, previousHour, providers, regions, platforms, accounts] = await Promise.all([
        count(q),
        rows<{ timestamp: string; count: string }>(
          `SELECT formatDateTime(toStartOfInterval(Timestamp, INTERVAL {bucket:UInt32} SECOND), '%Y-%m-%dT%H:%i:%S.000Z', 'UTC') AS timestamp, count() AS count FROM bronze.otel_traces WHERE ${predicate} GROUP BY timestamp ORDER BY timestamp`,
          q,
          { bucket: bucketSeconds },
        ),
        rows<{ name: string; count: string }>(
          `SELECT ServiceName AS name, count() AS count FROM bronze.otel_traces WHERE ${predicate} GROUP BY name ORDER BY count DESC, name ASC LIMIT 100`,
          q,
        ),
        rows<{ name: string; count: string }>(typesQuery.sql, q),
        countWindow(q, lastFrom, q.to),
        countWindow(q, prevFrom, prevTo),
        namedCounts(q, CLOUD_PROVIDER),
        namedCounts(q, CLOUD_REGION),
        namedCounts(q, CLOUD_PLATFORM),
        namedCounts(q, CLOUD_ACCOUNT),
      ]);
      const lookup = new Map(trend.map((x) => [x.timestamp, Number(x.count)]));
      const start = Math.floor(Date.parse(q.from) / (bucketSeconds * 1000)) * bucketSeconds * 1000;
      const filled = [];
      for (let time = start; time < Date.parse(q.to); time += bucketSeconds * 1000) {
        const timestamp = new Date(time).toISOString();
        filled.push({ timestamp, count: lookup.get(timestamp) ?? 0 });
      }
      return {
        total,
        bucketSeconds,
        trend: filled,
        services: services.map((s) => ({ name: s.name, count: Number(s.count) })),
        types: types.map((t) => ({ name: t.name, count: Number(t.count) })),
        hourCompare: computeHourChange(lastHour, previousHour),
        cloud: { providers, regions, platforms, accounts },
      };
    },
  };
}
