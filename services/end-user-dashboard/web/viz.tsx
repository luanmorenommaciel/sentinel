import React from 'react';
import { fmtCount } from './format';

const PALETTE = ['var(--pri)', 'var(--sec)', 'var(--alarm)', 'var(--ter)', 'var(--dim2)'];

type Slice = { name: string; count: number };

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polar(cx, cy, r, end);
  const e = polar(cx, cy, r, start);
  const large = end - start <= 180 ? 0 : 1;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 0 ${e.x} ${e.y}`;
}

/** Donut breakdown — same idea as the reference rings, flow-ui colors only. */
export function VizDonut({
  title,
  items,
  centerLabel,
}: {
  title: string;
  items: Slice[];
  centerLabel?: string;
}) {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  const cx = 70;
  const cy = 70;
  const r = 52;
  let cursor = 0;
  const arcs =
    total === 0
      ? []
      : items.map((item, index) => {
          const sweep = (item.count / total) * 360;
          const start = cursor;
          const end = cursor + Math.max(sweep, item.count > 0 ? 0.8 : 0);
          cursor = end;
          return {
            ...item,
            d: arcPath(cx, cy, r, start, end),
            color: PALETTE[index % PALETTE.length]!,
          };
        });

  return (
    <div className="viz-card">
      <h3>{title}</h3>
      <div className="viz-donut-wrap">
        <svg viewBox="0 0 140 140" role="img" aria-label={title}>
          <circle cx={cx} cy={cy} r={r} className="viz-track" />
          {arcs.map((arc) => (
            <path key={arc.name} d={arc.d} className="viz-arc" stroke={arc.color} fill="none" strokeWidth="14" />
          ))}
        </svg>
        <div className="viz-donut-center">
          <strong>{centerLabel ?? fmtCount(total)}</strong>
          <span>total</span>
        </div>
      </div>
      <ul className="viz-legend">
        {items.slice(0, 6).map((item, index) => (
          <li key={item.name}>
            <i style={{ background: PALETTE[index % PALETTE.length] }} />
            <span>{item.name}</span>
            <b>{fmtCount(item.count)}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Radial meter for a 0–100% KPI (focus / hour pressure). */
export function VizRadial({
  title,
  percent,
  subtitle,
  tone = 'pri',
}: {
  title: string;
  percent: number;
  subtitle: string;
  tone?: 'pri' | 'sec' | 'alarm';
}) {
  const clamped = Math.max(0, Math.min(100, percent));
  const r = 54;
  const c = 2 * Math.PI * r;
  const offset = c - (clamped / 100) * c;
  const stroke = tone === 'alarm' ? 'var(--alarm)' : tone === 'sec' ? 'var(--sec)' : 'var(--pri)';
  return (
    <div className="viz-card">
      <h3>{title}</h3>
      <div className="viz-donut-wrap">
        <svg viewBox="0 0 140 140" role="img" aria-label={`${title} ${clamped}%`}>
          <circle cx="70" cy="70" r={r} className="viz-track" />
          <circle
            cx="70"
            cy="70"
            r={r}
            fill="none"
            stroke={stroke}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            transform="rotate(-90 70 70)"
            style={{ filter: `drop-shadow(0 0 8px ${stroke})` }}
          />
        </svg>
        <div className="viz-donut-center">
          <strong>{Math.round(clamped)}%</strong>
          <span>{subtitle}</span>
        </div>
      </div>
    </div>
  );
}

/** Horizontal bars with end caps — reference “dot bar” format, command palette colors. */
export function VizDotBars({ title, items }: { title: string; items: Slice[] }) {
  const max = Math.max(1, ...items.map((item) => item.count));
  return (
    <div className="viz-card">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="viz-empty">No data.</p>
      ) : (
        <ul className="viz-dotbars">
          {items.map((item, index) => {
            const width = (item.count / max) * 100;
            const color = PALETTE[index % PALETTE.length]!;
            return (
              <li key={item.name}>
                <div className="viz-dotbars-meta">
                  <span>{item.name}</span>
                  <b>{fmtCount(item.count)}</b>
                </div>
                <div className="viz-dotbars-track">
                  <span className="viz-dotbars-fill" style={{ width: `${width}%`, background: color }}>
                    <i style={{ background: color, boxShadow: `0 0 10px ${color}` }} />
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Actual vs equal-share target — executive “regional performance” style. */
export function VizActualTarget({
  title,
  items,
  total,
}: {
  title: string;
  items: Slice[];
  total: number;
}) {
  const target = items.length > 0 ? Math.max(1, Math.round(total / Math.max(items.length, 1))) : 1;
  const max = Math.max(target, ...items.map((item) => item.count), 1);
  return (
    <div className="viz-card">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="viz-empty">No data.</p>
      ) : (
        <>
          <p className="viz-hint">Solid = actual · outline = equal-share target</p>
          <ul className="viz-actual">
            {items.map((item, index) => {
              const color = PALETTE[index % PALETTE.length]!;
              return (
                <li key={item.name}>
                  <div className="viz-dotbars-meta">
                    <span>{item.name}</span>
                    <b>{fmtCount(item.count)}</b>
                  </div>
                  <div className="viz-actual-track">
                    <span className="viz-actual-target" style={{ width: `${(target / max) * 100}%` }} />
                    <span
                      className="viz-actual-fill"
                      style={{ width: `${(item.count / max) * 100}%`, background: color, boxShadow: `0 0 10px ${color}` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}

/** 100% stacked row for component-type mix (price-band style). */
export function VizStackMix({ title, items }: { title: string; items: Slice[] }) {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  return (
    <div className="viz-card">
      <h3>{title}</h3>
      {total === 0 ? (
        <p className="viz-empty">No data.</p>
      ) : (
        <>
          <div className="viz-stack" role="img" aria-label={title}>
            {items.map((item, index) => {
              const pct = Math.max(2, Math.round((item.count / total) * 100));
              return (
                <span
                  key={item.name}
                  style={{ width: `${pct}%`, background: PALETTE[index % PALETTE.length] }}
                  title={`${item.name} ${pct}%`}
                >
                  {pct >= 12 ? `${pct}%` : ''}
                </span>
              );
            })}
          </div>
          <ul className="viz-legend">
            {items.map((item, index) => (
              <li key={item.name}>
                <i style={{ background: PALETTE[index % PALETTE.length] }} />
                <span>{item.name}</span>
                <b>
                  {fmtCount(item.count)} · {Math.round((item.count / total) * 100)}%
                </b>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** Segmented progress strips for ranked shares. */
export function VizSegments({ title, items }: { title: string; items: Slice[] }) {
  const total = Math.max(1, items.reduce((sum, item) => sum + item.count, 0));
  return (
    <div className="viz-card">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="viz-empty">No data.</p>
      ) : (
        <ul className="viz-segments">
          {items.slice(0, 5).map((item, index) => {
            const pct = Math.round((item.count / total) * 100);
            return (
              <li key={item.name}>
                <div className="viz-dotbars-meta">
                  <span>{item.name}</span>
                  <b>
                    {fmtCount(item.count)} · {pct}%
                  </b>
                </div>
                <div className="viz-seg-track">
                  {Array.from({ length: 20 }, (_, i) => (
                    <i
                      key={i}
                      className={i < Math.round(pct / 5) ? 'on' : ''}
                      style={i < Math.round(pct / 5) ? { background: PALETTE[index % PALETTE.length] } : undefined}
                    />
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
