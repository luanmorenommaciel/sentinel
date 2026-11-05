import React from 'react';

const PRESETS = [
  { value: 1, label: 'Last hour' },
  { value: 24, label: 'Last 24 hours' },
  { value: 168, label: 'Last 7 days' },
  { value: 720, label: 'Last 30 days' },
] as const;

type Props = { range: number; setRange?: (n: number) => void; refresh?: () => void };

export function TimeRangePills({ range, setRange }: Props) {
  return (
    <div className="range-pills" role="group" aria-label="Time range">
      {PRESETS.map((preset) => (
        <button
          key={preset.value}
          type="button"
          aria-pressed={range === preset.value}
          onClick={() => setRange?.(preset.value)}
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}
