import React, { useEffect, useState } from 'react';

type Props = {
  live?: boolean;
  refreshing?: boolean;
  lastUpdated?: string | null;
  refreshIntervalMs?: number;
  refresh?: () => void;
};

function formatAge(iso: string, nowMs: number): string {
  const ageSec = Math.max(0, Math.floor((nowMs - new Date(iso).getTime()) / 1000));
  if (ageSec < 5) return 'just now';
  if (ageSec < 60) return `${ageSec}s ago`;
  return `${Math.floor(ageSec / 60)}m ago`;
}

export function LiveStatus({ live, refreshing, lastUpdated, refreshIntervalMs = 30_000, refresh }: Props) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const intervalLabel = `${Math.round(refreshIntervalMs / 1000)}s`;

  return (
    <>
      <span className="st" data-up={live ? 'y' : 'n'}>
        {live ? `Live · every ${intervalLabel}` : 'Offline'}
      </span>
      <span>
        {refreshing ? 'Refreshing…' : lastUpdated ? (
          <>
            Updated <b>{formatAge(lastUpdated, now)}</b>
          </>
        ) : (
          'Waiting'
        )}
      </span>
      <button type="button" className="btn" onClick={refresh}>
        Refresh
      </button>
    </>
  );
}
