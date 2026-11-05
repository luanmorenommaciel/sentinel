import React from 'react';

type Props = { label: string; valueLabel: string; percent: number; caption: string };

export function KpiRing({ label, valueLabel, percent, caption }: Props) {
  const clamped = Math.max(0, Math.min(100, percent));
  const circumference = 2 * Math.PI * 54;
  const offset = circumference - (clamped / 100) * circumference;
  return (
    <section className="glass kpi-ring" aria-label={label}>
      <h2>{label}</h2>
      <div className="ring-wrap">
        <svg viewBox="0 0 140 140" role="img" aria-label={`${valueLabel}, ${clamped}%`}>
          <circle className="ring-track" cx="70" cy="70" r="54" />
          <circle
            className="ring-value"
            cx="70"
            cy="70"
            r="54"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="ring-center">
          <strong>{valueLabel}</strong>
        </div>
      </div>
      <p>{caption}</p>
    </section>
  );
}
