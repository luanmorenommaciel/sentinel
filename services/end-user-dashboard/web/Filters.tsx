import React from 'react';

type Props = {
  range: number;
  service: string;
  span?: string;
  setRange?: (n: number) => void;
  setService?: (s: string) => void;
  setSpan?: (s: string) => void;
  refresh?: () => void;
};

export function Filters({ range, service, setRange, setService, refresh }: Props) {
  return (
    <section className="panel" aria-label="Filters">
      <h2>Filters</h2>
      <p className="lede">Narrow the list when you need a closer look</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'end' }}>
        <label style={{ display: 'grid', gap: 4, color: 'var(--dim)', fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Time range
          <select
            value={range}
            onChange={(e) => setRange?.(Number(e.target.value))}
            style={{ background: 'var(--sunk)', color: 'var(--txt)', border: '1px solid var(--rule)', padding: 8, minWidth: 140 }}
          >
            <option value={1}>Last hour</option>
            <option value={24}>Last 24 hours</option>
            <option value={168}>Last 7 days</option>
            <option value={720}>Last 30 days</option>
          </select>
        </label>
        <label style={{ display: 'grid', gap: 4, color: 'var(--dim)', fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Service name
          <input
            value={service}
            onChange={(e) => setService?.(e.target.value)}
            placeholder="Exact service"
            style={{ background: 'var(--sunk)', color: 'var(--txt)', border: '1px solid var(--rule)', padding: 8, minWidth: 140 }}
          />
        </label>
        <button type="button" className="btn pri" onClick={refresh}>
          Refresh
        </button>
      </div>
    </section>
  );
}
