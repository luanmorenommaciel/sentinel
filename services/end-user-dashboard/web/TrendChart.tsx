import React from 'react';
import { localTime } from './format';
import { trendPeak } from './metrics';
import type { TrendPoint } from './types';

type Props = { trend: TrendPoint[]; total: number };

export function TrendChart({ trend, total }: Props) {
  const peak = trendPeak(trend);
  return (
    <section className="glass trend-card">
      <div className="section-head">
        <div>
          <h2>Error volume</h2>
          <p className="hero-metric">{total.toLocaleString()}</p>
          <span className="meta">Peak {peak.toLocaleString()}</span>
        </div>
      </div>
      {trend.length === 0 ? (
        <p className="muted">No error spans in this range.</p>
      ) : (
        <div className="trend" aria-label="Error span trend">
          {trend.map((point) => (
            <div
              key={point.timestamp}
              className="bar"
              title={`${localTime(point.timestamp)}: ${point.count}`}
              style={{ height: `${Math.max(8, (point.count / Math.max(1, peak)) * 100)}%` }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
