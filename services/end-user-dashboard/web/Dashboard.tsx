import React, { useState } from 'react';
import { AreaChart } from '@tremor/react';
import { Filters } from './Filters';
import { fmtCount } from './format';
import { executiveInsights, headlineInsight, serviceRank } from './insights';
import { LiveStatus } from './LiveStatus';
import { executiveSummary, formatHourChange } from './metrics';
import { SpanDetail } from './SpanDetail';
import { SpanTable } from './SpanTable';
import { TimeRangePills } from './TimeRangePills';
import type { DashboardProps, HourCompare, Span } from './types';
import { VizActualTarget, VizDonut, VizDotBars, VizStackMix } from './viz';

const RANGE_LABEL: Record<number, string> = {
  1: 'Last hour',
  24: 'Last 24 hours',
  168: 'Last 7 days',
  720: 'Last 30 days',
};

type ExecView = 'summary' | 'services' | 'cloud' | 'investigate';

export function Dashboard(props: DashboardProps) {
  const [selected, setSelected] = useState<Span | null>(null);
  const [view, setView] = useState<ExecView>('summary');
  const range = props.range ?? 24;
  const page = props.page ?? 1;
  const total = props.total ?? 0;
  const service = props.service ?? '';
  const summary = props.overview ? executiveSummary(props.overview) : null;
  const typeCounts = props.overview?.types ?? [];
  const typeEventSum = typeCounts.reduce((sum, item) => sum + item.count, 0);
  const hour = props.overview?.hourCompare;
  const insights = props.overview ? executiveInsights(props.overview) : [];
  const headline = props.overview ? headlineInsight(props.overview) : '';
  const services = props.overview?.services ?? [];
  const cloud = props.overview?.cloud;

  const trendData =
    props.overview?.trend.map((point) => ({
      time: new Date(point.timestamp).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
      }),
      Errors: point.count,
    })) ?? [];

  const hourBadge =
    hour == null
      ? null
      : hour.changePct === null
        ? { text: 'new vs prior', tone: 'warn' as const }
        : {
            text: `${hour.changePct > 0 ? '+' : ''}${hour.changePct}% vs last hour`,
            tone: (hour.direction === 'up' ? 'bad' : hour.direction === 'down' ? 'ok' : 'info') as
              | 'ok'
              | 'bad'
              | 'info',
          };

  const openInvestigate = () => setView('investigate');

  return (
    <div className="shell">
      <header className="top">
        <span className="brand">
          <span className="led" aria-hidden="true" />
          Sentinel
        </span>
        <nav className="dash" aria-label="Executive views">
          <button type="button" aria-pressed={view === 'summary'} aria-selected={view === 'summary'} onClick={() => setView('summary')}>
            Executive Summary
          </button>
          <button type="button" aria-pressed={view === 'services'} aria-selected={view === 'services'} onClick={() => setView('services')}>
            Service Focus
          </button>
          <button type="button" aria-pressed={view === 'cloud'} aria-selected={view === 'cloud'} onClick={() => setView('cloud')}>
            Cloud Footprint
          </button>
          <button type="button" aria-pressed={view === 'investigate'} aria-selected={view === 'investigate'} onClick={openInvestigate}>
            Investigate
          </button>
        </nav>
        <div className="meta">
          <span>
            Period · <b>{RANGE_LABEL[range] ?? `${range}h`}</b>
          </span>
          <LiveStatus
            live={props.live}
            refreshing={props.refreshing}
            lastUpdated={props.lastUpdated}
            refreshIntervalMs={props.refreshIntervalMs}
            refresh={props.refresh}
          />
        </div>
      </header>

      <div className="crumb">
        <span className="now">Business health</span>
        <span className="sep">›</span>
        <span>{view === 'summary' ? 'Executive summary' : view === 'services' ? 'Service focus' : view === 'cloud' ? 'Cloud footprint' : 'Investigate'}</span>
        {hour ? <span className="sep">· {formatHourChange(hour)}</span> : null}
        <span className="esc">
          <TimeRangePills range={range} setRange={props.setRange} />
        </span>
      </div>

      <main className="stage" role="tabpanel">
        {props.error ? (
          <section className="panel alert" role="alert">
            <h2>Unable to load</h2>
            <p className="lede">Check the connection and try again.</p>
            <button type="button" className="btn pri" onClick={props.refresh}>
              Retry
            </button>
          </section>
        ) : props.loading && !props.overview ? (
          <p role="status" style={{ color: 'var(--dim)' }}>
            Loading error spans…
          </p>
        ) : (
          props.overview &&
          summary &&
          (view === 'investigate' ? (
            <section style={{ display: 'grid', gap: 12 }}>
              <Filters
                range={range}
                service={service}
                span=""
                setRange={props.setRange}
                setService={props.setService}
                refresh={props.refresh}
              />
              <SpanTable items={props.items} page={page} total={total} setPage={props.setPage} onSelect={setSelected} />
            </section>
          ) : view === 'cloud' ? (
            <CloudExecView cloud={cloud} />
          ) : view === 'services' ? (
            <ServicesExecView
              services={services}
              total={summary.total}
              service={service}
              setService={props.setService}
              onInvestigate={openInvestigate}
            />
          ) : (
            <SummaryExecView
              summary={summary}
              headline={headline}
              hour={hour}
              hourBadge={hourBadge}
              typeCounts={typeCounts}
              typeEventSum={typeEventSum}
              services={services}
              trendData={trendData}
              insights={insights}
              service={service}
              setService={props.setService}
              onInvestigate={openInvestigate}
              cloudChannels={[
                ...(cloud?.providers ?? []).slice(0, 1).map((p) => ({ name: `Provider · ${p.name}`, count: p.count })),
                ...(cloud?.regions ?? []).slice(0, 2).map((r) => ({ name: `Region · ${r.name}`, count: r.count })),
              ]}
            />
          ))
        )}
      </main>

      <footer className="legend">
        <span>
          <span className="dot" />
          <b>Green</b> = improving / healthy
        </span>
        <span>
          <b style={{ color: 'var(--alarm)' }}>Red</b> = rising / act now
        </span>
        <span>
          <b style={{ color: 'var(--sec)' }}>Amber</b> = watch
        </span>
        <span className="sp">Executive format · command palette</span>
      </footer>

      {selected && <SpanDetail span={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function SummaryExecView(props: {
  summary: ReturnType<typeof executiveSummary>;
  headline: string;
  hour?: HourCompare;
  hourBadge: { text: string; tone: 'ok' | 'bad' | 'info' | 'warn' } | null;
  typeCounts: { name: string; count: number }[];
  typeEventSum: number;
  services: { name: string; count: number }[];
  trendData: { time: string; Errors: number }[];
  insights: ReturnType<typeof executiveInsights>;
  service: string;
  setService?: (s: string) => void;
  onInvestigate: () => void;
  cloudChannels: { name: string; count: number }[];
}) {
  const { summary, hour, hourBadge } = props;
  const rows = props.services.slice(0, 6);

  return (
    <div className="exec">
      <section className="exec-hero">
        <div className="exec-hero-copy">
          <p className="exec-kicker">Error health · action board</p>
          <h1>Business path reliability</h1>
          <p className="exec-insight">{props.headline}</p>
        </div>
        <div className="exec-kpis" aria-label="Primary KPIs">
          <div className={`exec-kpi ${summary.total > 0 ? 'bad' : 'ok'}`}>
            <i>Error events</i>
            <b>{fmtCount(summary.total)}</b>
            {hourBadge ? <span className={`badge ${hourBadge.tone}`}>{hourBadge.text}</span> : <span className="badge info">in window</span>}
          </div>
          <div className="exec-kpi">
            <i>Concentration</i>
            <b>
              {summary.concentration}
              <u>%</u>
            </b>
            <span className="badge info">
              {summary.topService === '—' ? 'no leader' : `#1 ${summary.topService}`}
            </span>
          </div>
          <div className="exec-kpi">
            <i>Peak rate</i>
            <b>{fmtCount(summary.peak)}</b>
            <span className="badge warn">bucket high</span>
          </div>
        </div>
      </section>

      <section className="pulse-row" aria-label="Pulse metrics">
        <Pulse label="Alerts last hour" value={fmtCount(hour?.lastHour ?? 0)} badge={hourBadge?.text ?? '—'} tone={hourBadge?.tone ?? 'info'} />
        <Pulse label="Alerts prior hour" value={fmtCount(hour?.previousHour ?? 0)} badge="baseline" tone="info" />
        <Pulse label="Services hit" value={fmtCount(summary.services)} badge={summary.services > 3 ? 'broad' : 'narrow'} tone={summary.services > 5 ? 'warn' : 'info'} />
        <Pulse label="Typed events" value={fmtCount(props.typeEventSum)} badge={`${props.typeCounts.length} types`} tone="ok" />
      </section>

      <section className="exec-mid">
        <VizDonut title="Error mix by type" items={props.typeCounts} centerLabel={fmtCount(props.typeEventSum)} />
        <VizActualTarget title="Service load vs equal share" items={props.services.slice(0, 5)} total={summary.total} />
        <div className="viz-card">
          <h3>Volume trend</h3>
          {props.trendData.length === 0 ? (
            <p className="viz-empty">No error spans in this range.</p>
          ) : (
            <AreaChart
              className="h-44"
              data={props.trendData}
              index="time"
              categories={['Errors']}
              colors={['emerald']}
              showLegend={false}
              showAnimation
              valueFormatter={(value) => fmtCount(Number(value))}
            />
          )}
        </div>
      </section>

      <section className="exec-mid" style={{ gridTemplateColumns: '1.4fr 0.9fr' }}>
        <div className="panel">
          <h2>Service performance</h2>
          <p className="lede">Where to put the next owner — tap a row to focus</p>
          {props.service ? (
            <button type="button" className="btn" style={{ marginBottom: 10 }} onClick={() => props.setService?.('')}>
              Clear focus · {props.service}
            </button>
          ) : null}
          {rows.length === 0 ? (
            <p style={{ color: 'var(--dim)' }}>No affected services.</p>
          ) : (
            <table className="biz exec-table">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Events</th>
                  <th>Share</th>
                  <th>Vs equal</th>
                  <th>Rank</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item, index) => {
                  const share = summary.total > 0 ? Math.round((item.count / summary.total) * 100) : 0;
                  const equal = Math.max(1, Math.round(summary.total / Math.max(rows.length, 1)));
                  const delta = item.count - equal;
                  const rank = serviceRank(index, share);
                  return (
                    <tr key={item.name} className={props.service === item.name ? 'active' : undefined}>
                      <td>
                        <button type="button" className="linkish" onClick={() => props.setService?.(item.name)}>
                          {item.name}
                        </button>
                      </td>
                      <td>{fmtCount(item.count)}</td>
                      <td>{share}%</td>
                      <td>
                        <span className={`badge ${delta > 0 ? 'bad' : delta < 0 ? 'ok' : 'info'}`}>
                          {delta > 0 ? '+' : ''}
                          {fmtCount(delta)}
                        </span>
                      </td>
                      <td>
                        <span className={`rank ${rank.tone}`}>{rank.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total in view</td>
                  <td>{fmtCount(rows.reduce((s, r) => s + r.count, 0))}</td>
                  <td colSpan={3}>{fmtCount(summary.total)} window total</td>
                </tr>
              </tfoot>
            </table>
          )}
          {summary.total > 0 ? (
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn pri" onClick={props.onInvestigate}>
                Open investigation
              </button>
            </div>
          ) : (
            <p style={{ color: 'var(--dim)', marginTop: 12 }}>No error spans in this range.</p>
          )}
        </div>

        <div className="exec-side">
          <VizDotBars title="Cloud / region pulse" items={props.cloudChannels} />
          <div className="panel insights">
            <h2>Key actions</h2>
            <p className="lede">What leadership should do next</p>
            <ul className="insight-list">
              {props.insights.map((item) => (
                <li key={item.title} data-tone={item.tone}>
                  <strong>{item.title}</strong>
                  <span>{item.body}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}

function Pulse({
  label,
  value,
  badge,
  tone,
}: {
  label: string;
  value: string;
  badge: string;
  tone: 'ok' | 'bad' | 'info' | 'warn';
}) {
  return (
    <div className="pulse">
      <i>{label}</i>
      <b>{value}</b>
      <span className={`badge ${tone}`}>{badge}</span>
    </div>
  );
}

function ServicesExecView(props: {
  services: { name: string; count: number }[];
  total: number;
  service: string;
  setService?: (s: string) => void;
  onInvestigate: () => void;
}) {
  return (
    <div className="exec">
      <section className="exec-hero compact">
        <div className="exec-hero-copy">
          <p className="exec-kicker">Service focus</p>
          <h1>Where errors concentrate</h1>
          <p className="exec-insight">Compare actual load against an equal-share target, then drill into Investigate.</p>
        </div>
      </section>
      <section className="exec-mid">
        <VizActualTarget title="Actual vs equal share" items={props.services.slice(0, 8)} total={props.total} />
        <VizStackMix title="Share of error volume" items={props.services.slice(0, 5)} />
        <div className="panel">
          <h2>Focus control</h2>
          <p className="lede">Select a service to filter the investigation list</p>
          {props.service ? (
            <button type="button" className="btn" style={{ marginBottom: 10 }} onClick={() => props.setService?.('')}>
              Clear · {props.service}
            </button>
          ) : null}
          <ul className="svc-list">
            {props.services.slice(0, 8).map((item) => (
              <li key={item.name}>
                <button
                  type="button"
                  className={`svc-row${props.service === item.name ? ' active' : ''}`}
                  aria-pressed={props.service === item.name}
                  onClick={() => props.setService?.(item.name)}
                >
                  <span>{item.name}</span>
                  <span className="count">{fmtCount(item.count)}</span>
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="btn pri" style={{ marginTop: 12 }} onClick={props.onInvestigate}>
            Investigate selection
          </button>
        </div>
      </section>
    </div>
  );
}

function CloudExecView(props: {
  cloud?: {
    providers: { name: string; count: number }[];
    regions: { name: string; count: number }[];
    platforms: { name: string; count: number }[];
    accounts: { name: string; count: number }[];
  };
}) {
  const cloud = props.cloud;
  return (
    <div className="exec">
      <section className="exec-hero compact">
        <div className="exec-hero-copy">
          <p className="exec-kicker">Cloud footprint</p>
          <h1>Provider · region · platform · account</h1>
          <p className="exec-insight">Use this view when the question is “is this us, or the cloud path?”</p>
        </div>
      </section>
      <section className="exec-mid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
        <VizDonut title="Providers" items={cloud?.providers ?? []} />
        <VizActualTarget
          title="Regions vs equal share"
          items={cloud?.regions ?? []}
          total={(cloud?.regions ?? []).reduce((s, r) => s + r.count, 0)}
        />
        <VizDotBars title="Platforms" items={cloud?.platforms ?? []} />
        <VizStackMix title="Accounts" items={cloud?.accounts ?? []} />
      </section>
    </div>
  );
}
