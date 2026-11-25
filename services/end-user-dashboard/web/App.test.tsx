/** @vitest-environment happy-dom */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { Dashboard } from './App';

afterEach(() => cleanup());

const emptyOverview = { total: 0, trend: [], services: [] as { name: string; count: number }[] };

it('shows executive empty state with time-window controls', () => {
  const html = renderToStaticMarkup(<Dashboard overview={emptyOverview} items={[]} error={false} />);
  expect(html).toContain('No error spans');
  expect(html).toContain('Last 24 hours');
  expect(html).toContain('Executive Summary');
  expect(html).toContain('Business path reliability');
});

it('distinguishes a failed request from empty results', () => {
  const html = renderToStaticMarkup(<Dashboard overview={null} items={[]} error />);
  expect(html).toContain('Unable to load');
  expect(html).not.toContain('No error spans');
});

it('surfaces high-level KPIs without requiring span filters', () => {
  const html = renderToStaticMarkup(
    <Dashboard
      overview={{
        total: 100,
        trend: [
          { timestamp: '2026-11-04T10:00:00.000Z', count: 20 },
          { timestamp: '2026-11-04T11:00:00.000Z', count: 40 },
        ],
        services: [
          { name: 'checkout', count: 60 },
          { name: 'payments', count: 40 },
        ],
        types: [
          { name: 'compute', count: 55 },
          { name: 'messaging', count: 25 },
          { name: 'database', count: 12 },
          { name: 'storage', count: 8 },
        ],
        hourCompare: { lastHour: 40, previousHour: 20, changePct: 100, direction: 'up' },
        cloud: {
          providers: [{ name: 'gcp', count: 100 }],
          regions: [{ name: 'us-central1', count: 80 }],
          platforms: [{ name: 'gcp_cloud_storage', count: 8 }],
          accounts: [{ name: 'sentinel-synthetic', count: 100 }],
        },
      }}
      items={[]}
      error={false}
      total={100}
      live
      lastUpdated="2026-11-04T12:00:00.000Z"
    />,
  );
  expect(html).toContain('Executive Summary');
  expect(html).toContain('Error mix by type');
  expect(html).toContain('Service performance');
  expect(html).toContain('Key actions');
  expect(html).toContain('vs last hour');
  expect(html).toContain('+100%');
  expect(html).toContain('Alerts last hour');
  expect(html).toContain('Live');
  expect(html).toContain('compute');
  expect(html).toContain('messaging');
  expect(html).toContain('checkout');
  expect(html).toContain('#1 Focus');
  expect(html).toContain('Alert pressure rising');
  expect(html).not.toContain('Span name');
  expect(html).not.toContain('Showing 1–');
});

it('filters by a ranked service when the operator clicks it', () => {
  let service = '';
  render(
    <Dashboard
      overview={{ total: 3, trend: [], services: [{ name: 'checkout', count: 3 }] }}
      items={[]}
      error={false}
      service=""
      setService={(value) => {
        service = value;
      }}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /^checkout$/i }));
  expect(service).toBe('checkout');
});

it('keeps span investigation behind an explicit action', () => {
  render(
    <Dashboard
      overview={{ total: 1, trend: [], services: [] }}
      items={[
        {
          timestamp: '2026-11-04T12:00:00.000Z',
          serviceName: 'api',
          spanName: 'GET /pay',
          statusCode: 'Error',
          durationNs: '2500000',
          traceId: 'trace-abc',
          spanId: 'span-xyz',
          componentType: 'compute',
          cloudProvider: 'gcp',
          cloudRegion: 'us-central1',
          cloudAvailabilityZone: 'us-central1-a',
          cloudPlatform: 'gcp_cloud_storage',
          cloudAccountId: 'sentinel-synthetic',
        },
      ]}
      error={false}
      total={1}
      page={1}
    />,
  );
  expect(screen.queryByRole('button', { name: /view details/i })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Investigate' }));
  expect(screen.getByText(/Showing 1–1 of 1/)).toBeTruthy();
  expect(screen.getByRole('columnheader', { name: /type/i })).toBeTruthy();
  expect(screen.getByRole('columnheader', { name: /provider/i })).toBeTruthy();
  expect(screen.getByRole('columnheader', { name: /region/i })).toBeTruthy();
  expect(screen.getByRole('columnheader', { name: /zone/i })).toBeTruthy();
  expect(screen.getByRole('columnheader', { name: /platform/i })).toBeTruthy();
  expect(screen.getByRole('columnheader', { name: /account/i })).toBeTruthy();
  expect(screen.queryByRole('columnheader', { name: /^span$/i })).toBeNull();
  expect(screen.getByText('compute')).toBeTruthy();
  expect(screen.getByText('gcp_cloud_storage')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /view details/i }));
  const details = screen.getByRole('dialog', { name: /span details/i });
  expect(within(details).getByText(/trace-abc/)).toBeTruthy();
  expect(within(details).getByText('us-central1-a')).toBeTruthy();
});

it('exposes cloud and service executive views', () => {
  render(
    <Dashboard
      overview={{
        total: 10,
        trend: [],
        services: [{ name: 'checkout', count: 10 }],
        cloud: {
          providers: [{ name: 'gcp', count: 10 }],
          regions: [{ name: 'us-central1', count: 10 }],
          platforms: [{ name: 'gcp_cloud_run', count: 10 }],
          accounts: [{ name: 'sentinel-synthetic', count: 10 }],
        },
      }}
      items={[]}
      error={false}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Cloud Footprint' }));
  expect(screen.getByText(/Provider · region · platform · account/i)).toBeTruthy();
  expect(screen.getByText('gcp')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Service Focus' }));
  expect(screen.getByText(/Where errors concentrate/i)).toBeTruthy();
});

it('exposes a refresh control while live polling is on', () => {
  let refreshed = false;
  render(
    <Dashboard
      overview={emptyOverview}
      items={[]}
      error={false}
      live
      refreshIntervalMs={30000}
      refresh={() => {
        refreshed = true;
      }}
    />,
  );
  expect(screen.getByText(/Live · every 30s/i)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /^Refresh$/i }));
  expect(refreshed).toBe(true);
});
