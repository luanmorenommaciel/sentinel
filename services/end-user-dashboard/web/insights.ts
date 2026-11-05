import { formatHourChange } from './metrics';
import type { Overview } from './types';

export type ExecInsight = { title: string; body: string; tone: 'ok' | 'warn' | 'bad' | 'info' };

/** Action-oriented lines for VP / CEO / CTO — derived only from live overview fields. */
export function executiveInsights(overview: Overview): ExecInsight[] {
  const insights: ExecInsight[] = [];
  const hour = overview.hourCompare;
  const top = overview.services[0];
  const types = overview.types ?? [];
  const topType = types[0];
  const typeSum = types.reduce((s, t) => s + t.count, 0);
  const region = overview.cloud?.regions[0];
  const provider = overview.cloud?.providers[0];
  const concentration =
    overview.total > 0 && top ? Math.round((top.count / overview.total) * 100) : 0;

  if (overview.total === 0) {
    insights.push({
      title: 'Clear window',
      body: 'No error events in range — keep the live feed on and watch the next hour for regressions.',
      tone: 'ok',
    });
    return insights;
  }

  if (hour) {
    if (hour.direction === 'up') {
      insights.push({
        title: 'Alert pressure rising',
        body: `${formatHourChange(hour)}. Escalate the top service and freeze non-critical releases until the rate bends.`,
        tone: 'bad',
      });
    } else if (hour.direction === 'down') {
      insights.push({
        title: 'Alert pressure easing',
        body: `${formatHourChange(hour)}. Confirm the fix holds for one more hour before closing the incident thread.`,
        tone: 'ok',
      });
    } else {
      insights.push({
        title: 'Alert rate steady',
        body: `${formatHourChange(hour)}. Hold the current triage queue; look for concentration risk instead of volume.`,
        tone: 'info',
      });
    }
  }

  if (top && concentration >= 40) {
    insights.push({
      title: `Concentrate on ${top.name}`,
      body: `${concentration}% of errors sit on one service — assign an owner and open Investigate focused on that name.`,
      tone: concentration >= 60 ? 'bad' : 'warn',
    });
  } else if (top) {
    insights.push({
      title: 'Spread across services',
      body: `Lead service ${top.name} holds ${concentration}% — scan the performance table for a second hot spot before calling an all-hands.`,
      tone: 'info',
    });
  }

  if (topType && typeSum > 0) {
    const share = Math.round((topType.count / typeSum) * 100);
    insights.push({
      title: `${topType.name} leads the mix`,
      body: `${share}% of typed events are ${topType.name}. Route the next fix to that platform team (compute / messaging / data / storage).`,
      tone: share >= 50 ? 'warn' : 'info',
    });
  }

  if (provider || region) {
    const where = [provider?.name, region?.name].filter(Boolean).join(' · ');
    insights.push({
      title: 'Cloud footprint',
      body: `Heaviest signal in ${where}. Cross-check provider status and region capacity before blaming application code.`,
      tone: 'info',
    });
  }

  return insights.slice(0, 4);
}

export function serviceRank(index: number, sharePct: number): { label: string; tone: 'leader' | 'strong' | 'watch' | 'tail' } {
  if (index === 0) return { label: '#1 Focus', tone: 'leader' };
  if (sharePct >= 20) return { label: `#${index + 1} Strong`, tone: 'strong' };
  if (sharePct >= 10) return { label: `#${index + 1} Watch`, tone: 'watch' };
  return { label: `#${index + 1} Tail`, tone: 'tail' };
}

export function headlineInsight(overview: Overview): string {
  if (overview.total === 0) return 'No error events in the selected window — business path looks clear.';
  const hour = overview.hourCompare;
  const top = overview.services[0]?.name ?? 'unknown';
  const move =
    hour?.direction === 'up'
      ? 'rising vs last hour'
      : hour?.direction === 'down'
        ? 'falling vs last hour'
        : 'steady vs last hour';
  return `Error load is ${move}; ${top} is the primary service to act on first.`;
}
