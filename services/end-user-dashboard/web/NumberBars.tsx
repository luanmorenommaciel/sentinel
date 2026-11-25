import React from 'react';
import { fmtCount } from './format';

type Item = { name: string; count: number };

type Props = {
  items: Item[];
  ariaLabel: string;
};

export function NumberBars({ items, ariaLabel }: Props) {
  const max = Math.max(1, ...items.map((item) => item.count));
  if (items.length === 0) {
    return <p style={{ color: 'var(--dim)' }}>No data.</p>;
  }
  return (
    <ul className="num-bars" aria-label={ariaLabel}>
      {items.map((item) => (
        <li key={item.name}>
          <div className="num-bars-meta">
            <span className="num-bars-name">{item.name}</span>
            <span className="num-bars-count">{fmtCount(item.count)}</span>
          </div>
          <div className="num-bars-track" aria-hidden="true">
            <span style={{ width: `${(item.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
