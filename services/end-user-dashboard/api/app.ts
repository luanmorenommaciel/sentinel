import express from 'express';

export type Filter = { from: string; to: string; service?: string; span?: string; page: number };

type NamedCount = { name: string; count: number };

type Span = {
  timestamp: string;
  serviceName: string;
  spanName: string;
  statusCode: string;
  durationNs: string;
  traceId: string;
  spanId: string;
  componentType?: string;
  cloudProvider?: string;
  cloudRegion?: string;
  cloudAvailabilityZone?: string;
  cloudPlatform?: string;
  cloudAccountId?: string;
  [key: string]: unknown;
};

export type HourCompare = {
  lastHour: number;
  previousHour: number;
  changePct: number | null;
  direction: 'up' | 'down' | 'flat';
};

function cloudField(value: unknown): string {
  return typeof value === 'string' && value ? value : 'unknown';
}

export interface Repository {
  overview(q: Filter): Promise<{
    total: number;
    bucketSeconds: number;
    trend: { timestamp: string; count: number }[];
    services: { name: string; count: number }[];
    types: { name: string; count: number }[];
    hourCompare: HourCompare;
    cloud: {
      providers: NamedCount[];
      regions: NamedCount[];
      platforms: NamedCount[];
      accounts: NamedCount[];
    };
  }>;
  spans(q: Filter): Promise<{ total: number; items: Span[] }>;
}

export function createApp(repository: Repository) {
  const app = express();
  for (const route of ['overview', 'spans'] as const)
    app.get(`/api/${route}`, async (req, res) => {
      const { from, to, service, span, page = '1' } = req.query;
      if (
        typeof from !== 'string' ||
        typeof to !== 'string' ||
        !/^\d{4}-\d\d-\d\dT.*Z$/.test(from) ||
        !/^\d{4}-\d\d-\d\dT.*Z$/.test(to) ||
        !Number.isFinite(Date.parse(from)) ||
        !Number.isFinite(Date.parse(to)) ||
        Date.parse(to) <= Date.parse(from) ||
        Date.parse(to) - Date.parse(from) > 30 * 86400000 ||
        typeof page !== 'string' ||
        !/^[1-9]\d{0,5}$/.test(page) ||
        (service !== undefined && (typeof service !== 'string' || service.length > 256)) ||
        (span !== undefined && (typeof span !== 'string' || span.length > 256))
      )
        return res.status(400).json({ error: 'Invalid query parameters' });
      const query: Filter = { from, to, service, span, page: Number(page) };
      try {
        if (route === 'overview') {
          const { total, bucketSeconds, trend, services, types, hourCompare, cloud } = await repository.overview(query);
          return res.json({
            total,
            bucketSeconds,
            trend: trend.map(({ timestamp, count }) => ({ timestamp, count })),
            services: services.map(({ name, count }) => ({ name, count })),
            types: types.map(({ name, count }) => ({ name, count })),
            hourCompare,
            cloud: {
              providers: cloud.providers.map(({ name, count }) => ({ name, count })),
              regions: cloud.regions.map(({ name, count }) => ({ name, count })),
              platforms: cloud.platforms.map(({ name, count }) => ({ name, count })),
              accounts: cloud.accounts.map(({ name, count }) => ({ name, count })),
            },
            from,
            to,
          });
        }
        const result = await repository.spans(query);
        const items = result.items.map((item) => ({
          timestamp: item.timestamp,
          serviceName: item.serviceName,
          spanName: item.spanName,
          statusCode: item.statusCode,
          durationNs: item.durationNs,
          traceId: item.traceId,
          spanId: item.spanId,
          componentType: cloudField(item.componentType),
          cloudProvider: cloudField(item.cloudProvider),
          cloudRegion: cloudField(item.cloudRegion),
          cloudAvailabilityZone: cloudField(item.cloudAvailabilityZone),
          cloudPlatform: cloudField(item.cloudPlatform),
          cloudAccountId: cloudField(item.cloudAccountId),
        }));
        return res.json({ items, total: result.total, page: query.page, pageSize: 50, from, to });
      } catch {
        return res.status(503).json({ error: 'Data temporarily unavailable' });
      }
    });
  return app;
}
