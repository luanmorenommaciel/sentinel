import React, { useEffect, useRef } from 'react';
import { formatDuration, localTime } from './format';
import type { Span } from './types';

type Props = { span: Span; onClose: () => void };

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    /* ignore */
  }
}

export function SpanDetail({ span, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Span details"
        onClick={(event) => event.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--dim)' }}>
            Span details
          </h2>
          <button ref={closeRef} type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </div>
        <p style={{ fontSize: 16, fontWeight: 500 }}>
          {span.serviceName} / {span.spanName}
        </p>
        <p>
          <span className="pill">{span.componentType ?? 'unknown'}</span>{' '}
          <span className="pill bad">{span.statusCode}</span>
        </p>
        <p style={{ color: 'var(--dim2)' }}>
          {localTime(span.timestamp)} · {formatDuration(span.durationNs)}
        </p>
        <div className="panel" style={{ marginTop: 12 }}>
          <h2>Cloud</h2>
          <dl style={{ margin: 0, display: 'grid', gap: 8 }}>
            <div>
              <dt style={{ color: 'var(--dim)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Provider</dt>
              <dd style={{ margin: 0 }}>{span.cloudProvider ?? 'unknown'}</dd>
            </div>
            <div>
              <dt style={{ color: 'var(--dim)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Region</dt>
              <dd style={{ margin: 0 }}>{span.cloudRegion ?? 'unknown'}</dd>
            </div>
            <div>
              <dt style={{ color: 'var(--dim)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Zone</dt>
              <dd style={{ margin: 0 }}>{span.cloudAvailabilityZone ?? 'unknown'}</dd>
            </div>
            <div>
              <dt style={{ color: 'var(--dim)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Platform</dt>
              <dd style={{ margin: 0 }}>{span.cloudPlatform ?? 'unknown'}</dd>
            </div>
            <div>
              <dt style={{ color: 'var(--dim)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Account</dt>
              <dd style={{ margin: 0 }}>{span.cloudAccountId ?? 'unknown'}</dd>
            </div>
          </dl>
        </div>
        <div className="panel" style={{ marginTop: 12 }}>
          <p style={{ margin: '0 0 8px', overflowWrap: 'anywhere' }}>
            Trace ID: <code>{span.traceId}</code>
          </p>
          <button type="button" className="btn" onClick={() => void copyText(span.traceId)}>
            Copy trace ID
          </button>
        </div>
        <div className="panel" style={{ marginTop: 8 }}>
          <p style={{ margin: '0 0 8px' }}>
            Span ID: <code>{span.spanId}</code>
          </p>
          <button type="button" className="btn" onClick={() => void copyText(span.spanId)}>
            Copy span ID
          </button>
        </div>
      </aside>
    </div>
  );
}
