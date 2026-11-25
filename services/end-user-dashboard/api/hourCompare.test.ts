import { expect, it } from 'vitest';
import { computeHourChange } from './hourCompare';

it('reports rising alerts vs the prior hour', () => {
  expect(computeHourChange(120, 100)).toEqual({
    lastHour: 120,
    previousHour: 100,
    changePct: 20,
    direction: 'up',
  });
});

it('reports falling alerts vs the prior hour', () => {
  expect(computeHourChange(80, 100).direction).toBe('down');
  expect(computeHourChange(80, 100).changePct).toBe(-20);
});
