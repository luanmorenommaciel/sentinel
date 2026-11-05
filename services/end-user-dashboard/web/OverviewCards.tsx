import React from 'react';
import type { Overview } from './types';

type Props = { overview: Overview; serviceCount: number };

export function OverviewCards({ overview, serviceCount }: Props) {
  return (
    <section className="cards" aria-label="Overview">
      <article className="stat panel">
        <h2>Error spans</h2>
        <strong>{overview.total.toLocaleString()}</strong>
        <p>In the selected window</p>
      </article>
      <article className="stat panel">
        <h2>Affected services</h2>
        <strong>{serviceCount.toLocaleString()}</strong>
        <p>Ranked by error count</p>
      </article>
    </section>
  );
}
