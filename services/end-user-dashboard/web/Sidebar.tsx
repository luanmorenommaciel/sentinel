import React from 'react';

type Props = { active: 'overview' | 'investigate'; onNavigate: (view: 'overview' | 'investigate') => void };

export function Sidebar({ active, onNavigate }: Props) {
  const item = (id: 'overview' | 'investigate', label: string, ariaLabel: string) => (
    <button
      type="button"
      className={`mb-2 flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition ${
        active === id
          ? 'border border-cyan-400/40 bg-gradient-to-r from-cyan-500/20 to-violet-500/20 text-white'
          : 'border border-transparent text-slate-400 hover:bg-white/5 hover:text-slate-100'
      }`}
      aria-label={ariaLabel}
      aria-current={active === id ? 'page' : undefined}
      onClick={() => onNavigate(id)}
    >
      {label}
    </button>
  );

  return (
    <aside className="border-b border-slate-800 bg-slate-950/70 p-4 backdrop-blur lg:border-b-0 lg:border-r" aria-label="Dashboard navigation">
      <div className="mb-6 flex items-center gap-3 px-1">
        <span className="h-8 w-8 rounded-xl bg-gradient-to-br from-cyan-400 via-blue-500 to-violet-500 shadow-[0_0_24px_rgba(34,211,238,0.35)]" aria-hidden="true" />
        <div>
          <strong className="block text-sm text-white">Sentinel</strong>
          <span className="text-xs text-slate-400">Error health</span>
        </div>
      </div>
      <nav>
        {item('overview', 'Overview', 'Overview')}
        {item('investigate', 'Investigate', 'Open investigation')}
      </nav>
    </aside>
  );
}
