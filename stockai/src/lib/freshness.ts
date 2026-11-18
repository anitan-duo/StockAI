/**
 * Freshness display helpers.
 *
 * The backend classifies every quote's data status (fresh/recent/delayed/
 * stale/unavailable) — see backend/services/freshness.py. The frontend must
 * display that classification, never invent its own staleness heuristic.
 */

export type Freshness = 'fresh' | 'recent' | 'delayed' | 'stale' | 'unavailable';

export interface FreshnessStyle {
  label: string;
  className: string;
  dotClassName: string;
  /** Whether the price may be presented as current market data. */
  presentable: boolean;
  ariaLabel: string;
}

const STYLES: Record<Freshness, FreshnessStyle> = {
  fresh: {
    label: 'LIVE',
    className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    dotClassName: 'bg-emerald-500',
    presentable: true,
    ariaLabel: 'Live market data',
  },
  recent: {
    label: 'RECENT',
    className: 'border-sky-500/40 bg-sky-500/10 text-sky-600 dark:text-sky-400',
    dotClassName: 'bg-sky-500',
    presentable: true,
    ariaLabel: 'Recent market data',
  },
  delayed: {
    label: 'DELAYED',
    className: 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400',
    dotClassName: 'bg-amber-500',
    presentable: true,
    ariaLabel: 'Delayed market data',
  },
  stale: {
    label: 'STALE',
    className: 'border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400',
    dotClassName: 'bg-red-500',
    presentable: false,
    ariaLabel: 'Stale data — not current market data',
  },
  unavailable: {
    label: 'DATA UNAVAILABLE',
    className: 'border-slate-400/40 bg-slate-400/10 text-slate-500 dark:text-slate-400',
    dotClassName: 'bg-slate-400',
    presentable: false,
    ariaLabel: 'Data unavailable',
  },
};

export function normalizeFreshness(value: unknown): Freshness {
  const v = String(value ?? '').toLowerCase();
  if (v in STYLES) return v as Freshness;
  return 'unavailable';
}

export function freshnessStyle(value: unknown): FreshnessStyle {
  return STYLES[normalizeFreshness(value)];
}

/** Relative age label, e.g. "4s ago", "12 min ago", "3 h ago", "2 d ago". */
export function relativeAge(iso: string | null | undefined, nowMs: number = Date.now()): string | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return null;
  let s = Math.round((nowMs - t) / 1000);
  const future = s < 0;
  s = Math.abs(s);
  let out: string;
  if (s < 60) out = `${s}s`;
  else if (s < 3600) out = `${Math.round(s / 60)} min`;
  else if (s < 86400) out = `${Math.round(s / 3600)} h`;
  else out = `${Math.round(s / 86400)} d`;
  return future ? `in ${out}` : `${out} ago`;
}