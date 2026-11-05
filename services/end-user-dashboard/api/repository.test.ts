import { expect, it } from 'vitest';
import { buildSpanQuery, buildTypesQuery } from './repository';

it('keeps filters parameterized, limits pages, and uses a half-open interval', () => {
  const query = buildSpanQuery({ from: '2026-11-01T00:00:00.000Z', to: '2026-11-02T00:00:00.000Z', service: "x' OR 1=1", page: 2 });
  expect(query.sql).not.toContain("x' OR 1=1");
  expect(query.params.service).toBe("x' OR 1=1");
  expect(query.params.offset).toBe(50);
  expect(query.sql).toContain('Timestamp >=');
  expect(query.sql).toContain('Timestamp <');
  expect(query.sql).toContain("SpanAttributes['component.type']");
  expect(query.sql).toContain("ResourceAttributes['cloud.provider']");
  expect(query.sql).toContain("ResourceAttributes['cloud.region']");
  expect(query.sql).toContain("ResourceAttributes['cloud.availability_zone']");
  expect(query.sql).toContain("ResourceAttributes['cloud.platform']");
  expect(query.sql).toContain("ResourceAttributes['cloud.account.id']");
  expect(query.sql).not.toContain('StatusMessage');
});

it('aggregates error events by allowlisted component.type', () => {
  const query = buildTypesQuery({ from: '2026-11-01T00:00:00.000Z', to: '2026-11-02T00:00:00.000Z', page: 1 });
  expect(query.sql).toContain("SpanAttributes['component.type']");
  expect(query.sql).toContain('GROUP BY');
  expect(query.sql).toContain('count()');
});
