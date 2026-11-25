import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { createApp } from './app';

const from = '2026-11-01T00:00:00.000Z';
const to = '2026-11-02T00:00:00.000Z';
describe('read-only dashboard API', () => {
  it('returns only selected fields and passes filter values as data', async () => {
    let received: unknown;
    const app = createApp({
      overview: async (q) => {
        received = q;
        return {
          total: 3,
          bucketSeconds: 3600,
          trend: [],
          services: [],
          types: [{ name: 'compute', count: 2 }, { name: 'messaging', count: 1 }],
          hourCompare: { lastHour: 12, previousHour: 10, changePct: 20, direction: 'up' },
          cloud: {
            providers: [{ name: 'gcp', count: 3 }],
            regions: [{ name: 'us-central1', count: 3 }],
            platforms: [{ name: 'gcp_cloud_storage', count: 1 }],
            accounts: [{ name: 'sentinel-synthetic', count: 3 }],
          },
          secret: 'hidden',
        };
      },
      spans: async () => ({
        total: 1,
        items: [{
          timestamp: from,
          serviceName: 'svc',
          spanName: 'op',
          statusCode: 'Error',
          durationNs: '10',
          traceId: 't',
          spanId: 's',
          componentType: 'compute',
          cloudProvider: 'gcp',
          cloudRegion: 'us-central1',
          cloudAvailabilityZone: 'us-central1-a',
          cloudPlatform: 'gcp_cloud_storage',
          cloudAccountId: 'sentinel-synthetic',
          secret: 'hidden',
        }],
      }),
    });
    const response = await request(app).get('/api/spans').query({ from, to });
    expect(response.status).toBe(200);
    expect(response.body.items[0].componentType).toBe('compute');
    expect(response.body.items[0].cloudProvider).toBe('gcp');
    expect(response.body.items[0].cloudRegion).toBe('us-central1');
    expect(response.body.items[0].cloudAvailabilityZone).toBe('us-central1-a');
    expect(response.body.items[0].cloudPlatform).toBe('gcp_cloud_storage');
    expect(response.body.items[0].cloudAccountId).toBe('sentinel-synthetic');
    expect(JSON.stringify(response.body)).not.toContain('hidden');
    const overview = await request(app).get('/api/overview').query({ from, to, service: "x' OR 1=1" });
    expect(overview.body.types).toEqual([{ name: 'compute', count: 2 }, { name: 'messaging', count: 1 }]);
    expect(overview.body.hourCompare).toEqual({ lastHour: 12, previousHour: 10, changePct: 20, direction: 'up' });
    expect(overview.body.cloud.providers).toEqual([{ name: 'gcp', count: 3 }]);
    expect(JSON.stringify(overview.body)).not.toContain('hidden');
    expect(received).toMatchObject({ service: "x' OR 1=1" });
  });
  it('rejects invalid ranges and sanitizes database failures', async () => {
    const app = createApp({
      overview: async () => {
        throw Error('secret');
      },
      spans: async () => ({ total: 0, items: [] }),
    });
    expect((await request(app).get('/api/overview').query({from: to, to: from})).status).toBe(400);
    const response = await request(app).get('/api/overview').query({from, to});
    expect(response.status).toBe(503);
    expect(JSON.stringify(response.body)).not.toContain('secret');
  });
});
