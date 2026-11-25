const PAGE_SIZE = 50;

export function localTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function formatDuration(durationNs: string): string {
  const ns = Number(durationNs);
  if (!Number.isFinite(ns) || ns < 0) return durationNs;
  if (ns < 1_000) return `${ns} ns`;
  if (ns < 1_000_000) return `${(ns / 1_000).toFixed(1)} µs`;
  if (ns < 1_000_000_000) return `${(ns / 1_000_000).toFixed(1)} ms`;
  return `${(ns / 1_000_000_000).toFixed(2)} s`;
}

export function pageRangeLabel(page: number, total: number, pageSize = PAGE_SIZE): string {
  if (total <= 0) return 'Showing 0 of 0';
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return `Showing ${start}–${end} of ${total}`;
}

/** Compact figures like flow-ui (`1.7k`, `18.0M`). */
export function fmtCount(n: number): string {
  const abs = Math.abs(n);
  if (abs < 1000) return String(Math.round(n));
  if (abs < 1_000_000) return `${(n / 1000).toFixed(abs < 10_000 ? 1 : 0).replace(/\.0$/, '')}k`;
  if (abs < 1_000_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  return `${(n / 1_000_000_000).toFixed(1).replace(/\.0$/, '')}B`;
}

export { PAGE_SIZE };
