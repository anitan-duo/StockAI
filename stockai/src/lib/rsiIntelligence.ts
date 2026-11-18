export type RsiPoint = {
  timestamp: string;
  close: number | null;
  rsi_7: number | null;
  rsi_14: number | null;
  rsi_21: number | null;
};

export type RsiAnalysis = {
  symbol: string;
  exchange: string;
  method: string;
  periods: number[];
  thresholds: { overbought: number; oversold: number };
  current: Record<string, number | null>;
  slopes_5d: Record<string, number | null>;
  roc_5d: Record<string, number | null>;
  relative_to_mean: Record<string, number | null>;
  zone: 'overbought' | 'oversold' | 'neutral' | 'unavailable' | string;
  trend: 'rising' | 'falling' | 'flat' | 'unavailable' | string;
  persistence: { overbought_days: number; oversold_days: number };
  regime: { high_volatility: boolean; uptrend_50_200: boolean; vol_20d: number | null; vol_60d: number | null };
  crossovers: Array<{ level: number; direction: string; bars_ago: number | null }>;
  divergence: { kind: string; reason: string; method?: string; bars_ago?: number | null };
  agreement: { status: string; rsi_signal: string; reason: string };
  interpretation: string;
  series: RsiPoint[];
  bar_count: number;
  data_timestamp: string;
  prediction_direction: string | null;
  prediction_timestamp: string | null;
  caveats: string[];
};

export function clampRsi(value: number | null | undefined): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return Math.min(100, Math.max(0, value));
}

export function rsiPolyline(
  points: RsiPoint[],
  width = 300,
  height = 80,
  key: 'rsi_7' | 'rsi_14' | 'rsi_21' = 'rsi_14',
): string {
  const usable = points
    .map((p) => clampRsi(p[key]))
    .map((v, i) => ({ v, i }))
    .filter((p): p is { v: number; i: number } => p.v !== null);
  if (usable.length < 2) return '';
  const denom = Math.max(1, points.length - 1);
  return usable
    .map(({ v, i }) => `${((i / denom) * width).toFixed(2)},${(height - (v / 100) * height).toFixed(2)}`)
    .join(' ');
}

export function yForRsi(value: number, height = 80): number {
  const v = clampRsi(value) ?? 50;
  return height - (v / 100) * height;
}

export function rsiTone(zone: string): string {
  if (zone === 'overbought') return 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300';
  if (zone === 'oversold') return 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300';
  return 'border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300';
}

export function agreementLabel(status: string): string {
  if (status === 'agrees') return 'agrees with model';
  if (status === 'disagrees') return 'diverges from model';
  return 'no comparison';
}
