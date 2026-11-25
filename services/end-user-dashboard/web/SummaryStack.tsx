import React from 'react';

type Props = {
  total: number;
  services: number;
  peak: number;
  topService: string;
  activeService?: string;
  onClearFocus?: () => void;
};

export function SummaryStack({ total, services, peak, topService, activeService, onClearFocus }: Props) {
  return (
    <section className="glass summary-stack" aria-label="Executive summary">
      <h2>At a glance</h2>
      <dl>
        <div>
          <dt>Error spans</dt>
          <dd>{total.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Services hit</dt>
          <dd>{services.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Peak bucket</dt>
          <dd>{peak.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Hottest service</dt>
          <dd className="truncate">{topService}</dd>
        </div>
      </dl>
      {activeService ? (
        <button type="button" className="btn-clear" onClick={onClearFocus}>
          Clear focus · {activeService}
        </button>
      ) : null}
    </section>
  );
}
