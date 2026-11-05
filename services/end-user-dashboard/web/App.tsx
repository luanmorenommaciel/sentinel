import React, { useEffect, useState } from 'react';
import { Dashboard } from './Dashboard';
import type { Overview, Span } from './types';

export { Dashboard } from './Dashboard';

/** Online polling interval for live dashboard refresh. */
export const LIVE_REFRESH_MS = 30_000;

export default function App() {
  const [range, setRange] = useState(24);
  const [service, setService] = useState('');
  const [span, setSpan] = useState('');
  const [page, setPage] = useState(1);
  const [tick, setTick] = useState(0);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [items, setItems] = useState<Span[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), LIVE_REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const soft = overview !== null;
    if (soft) setRefreshing(true);
    else setLoading(true);
    setError(false);

    const to = new Date();
    const from = new Date(to.getTime() - range * 3600000);
    const params = new URLSearchParams({
      from: from.toISOString(),
      to: to.toISOString(),
      service,
      span,
    });

    Promise.all([
      fetch(`/api/overview?${params}`, { signal: controller.signal }),
      fetch(`/api/spans?${params}&page=${page}`, { signal: controller.signal }),
    ])
      .then(async ([overviewRes, spansRes]) => {
        if (!overviewRes.ok || !spansRes.ok) throw new Error('request failed');
        return Promise.all([overviewRes.json(), spansRes.json()]);
      })
      .then(([overviewBody, spansBody]) => {
        setOverview(overviewBody);
        setItems(spansBody.items);
        setTotal(spansBody.total);
        setLastUpdated(new Date().toISOString());
        setLoading(false);
        setRefreshing(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError(true);
          setLoading(false);
          setRefreshing(false);
        }
      });

    return () => controller.abort();
    // overview intentionally omitted: soft vs hard refresh uses current snapshot only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, service, span, page, tick]);

  const resetPage =
    <T,>(fn: (value: T) => void) =>
    (value: T) => {
      setPage(1);
      fn(value);
    };

  return (
    <Dashboard
      overview={overview}
      items={items}
      error={error}
      loading={loading}
      refreshing={refreshing}
      live
      lastUpdated={lastUpdated}
      refreshIntervalMs={LIVE_REFRESH_MS}
      range={range}
      setRange={resetPage(setRange)}
      service={service}
      setService={resetPage(setService)}
      span={span}
      setSpan={resetPage(setSpan)}
      page={page}
      setPage={setPage}
      total={total}
      refresh={() => setTick((n) => n + 1)}
    />
  );
}
