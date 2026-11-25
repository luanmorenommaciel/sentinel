import React from 'react';
import type { ServiceCount } from './types';

type Props = {
  services: ServiceCount[];
  activeService?: string;
  setService?: (name: string) => void;
};

export function ServiceRanking({ services, activeService, setService }: Props) {
  const top = services.slice(0, 5);
  const max = Math.max(1, ...top.map((s) => s.count));
  return (
    <section className="glass service-card">
      <div className="section-head">
        <h2>Top services</h2>
        <span className="meta">Tap to focus</span>
      </div>
      {top.length === 0 ? (
        <p className="muted">No affected services.</p>
      ) : (
        <ul className="service-list">
          {top.map((service, index) => {
            const active = activeService === service.name;
            return (
              <li key={service.name}>
                <button
                  type="button"
                  className={`service-row${active ? ' active' : ''}`}
                  aria-pressed={active}
                  onClick={() => setService?.(service.name)}
                >
                  <span className="rank">{index + 1}</span>
                  <span className="service-name">{service.name}</span>
                  <span className="service-count">{service.count.toLocaleString()}</span>
                  <span className="service-meter" aria-hidden="true">
                    <span style={{ width: `${(service.count / max) * 100}%` }} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
