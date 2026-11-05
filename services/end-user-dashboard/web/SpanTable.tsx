import React from 'react';
import { localTime, pageRangeLabel, PAGE_SIZE } from './format';
import type { Span } from './types';

type Props = {
  items: Span[];
  page: number;
  total: number;
  setPage?: (n: number) => void;
  onSelect: (span: Span) => void;
};

export function SpanTable({ items, page, total, setPage, onSelect }: Props) {
  return (
    <section className="panel">
      <h2>Recent error spans</h2>
      <p className="lede">{pageRangeLabel(page, total)}</p>
      {items.length === 0 ? (
        <p style={{ color: 'var(--dim)' }}>No error spans in this range.</p>
      ) : (
        <div style={{ overflow: 'auto' }}>
          <table className="biz">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Service</th>
                <th scope="col">Type</th>
                <th scope="col">Provider</th>
                <th scope="col">Region</th>
                <th scope="col">Zone</th>
                <th scope="col">Platform</th>
                <th scope="col">Account</th>
                <th scope="col">Status</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${item.traceId}-${item.spanId}-${index}`}>
                  <td>{localTime(item.timestamp)}</td>
                  <td>{item.serviceName}</td>
                  <td>
                    <span className="pill">{item.componentType ?? 'unknown'}</span>
                  </td>
                  <td>{item.cloudProvider ?? 'unknown'}</td>
                  <td>{item.cloudRegion ?? 'unknown'}</td>
                  <td>{item.cloudAvailabilityZone ?? 'unknown'}</td>
                  <td style={{ fontSize: 11 }}>{item.cloudPlatform ?? 'unknown'}</td>
                  <td style={{ fontSize: 11 }}>{item.cloudAccountId ?? 'unknown'}</td>
                  <td>
                    <span className="pill bad">{item.statusCode}</span>
                  </td>
                  <td>
                    <button type="button" className="btn" onClick={() => onSelect(item)}>
                      View details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <nav style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, color: 'var(--dim)' }} aria-label="Pages">
        <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage?.(page - 1)}>
          Previous
        </button>
        <span>
          Page {page}
          {total > 0 ? ` · ${Math.ceil(total / PAGE_SIZE)} total` : ''}
        </span>
        <button type="button" className="btn" disabled={page * PAGE_SIZE >= total} onClick={() => setPage?.(page + 1)}>
          Next
        </button>
      </nav>
    </section>
  );
}
