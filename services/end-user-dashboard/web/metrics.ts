import type { Overview, ServiceCount, TrendPoint } from './types';

export function trendPeak(trend: TrendPoint[]): number {
  return Math.max(0, ...trend.map((point) => point.count));
}

export function concentrationPct(services: ServiceCount[], total: number): number {
  if (total <= 0 || services.length === 0) return 0;
  return Math.round((services[0]!.count / total) * 100);
}

export function topServiceName(services: ServiceCount[]): string {
  return services[0]?.name ?? '—';
}

export function executiveSummary(overview: Overview) {
  return {
    total: overview.total,
    services: overview.services.length,
    peak: trendPeak(overview.trend),
    concentration: concentrationPct(overview.services, overview.total),
    topService: topServiceName(overview.services),
  };
}

export type HourChange = {
  lastHour: number;
  previousHour: number;
  changePct: number | null;
  direction: 'up' | 'down' | 'flat';
};

/** Compare alert counts in the last hour vs the hour before. */
export function computeHourChange(lastHour: number, previousHour: number): HourChange {
  if (previousHour === 0 && lastHour === 0) {
    return { lastHour, previousHour, changePct: 0, direction: 'flat' };
  }
  if (previousHour === 0) {
    return { lastHour, previousHour, changePct: null, direction: 'up' };
  }
  const changePct = Math.round(((lastHour - previousHour) / previousHour) * 1000) / 10;
  const direction = changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat';
  return { lastHour, previousHour, changePct, direction };
}

export function formatHourChange(change: HourChange): string {
  if (change.changePct === null) return 'new vs prior hour';
  if (change.direction === 'flat') return '0% vs prior hour';
  const sign = change.changePct > 0 ? '+' : '';
  return `${sign}${change.changePct}% vs prior hour`;
}
