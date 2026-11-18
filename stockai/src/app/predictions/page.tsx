'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { api } from '@/lib/api/client';
import { cn, formatPrice, formatPercent } from '@/lib/utils';
import { relativeAge } from '@/lib/freshness';
import {
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  BarChart3,
  Brain,
  ChevronDown,
  ChevronUp,
  Clock,
  Filter,
  LayoutGrid,
  Minus,
  RefreshCw,
  Search,
  SearchX,
  SlidersHorizontal,
  Sparkles,
  TableIcon,
  Target,
  TrendingDown,
  TrendingUp,
  X,
  Info,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types & helpers
// ---------------------------------------------------------------------------

type MarketFilter = 'all' | 'us' | 'india' | 'europe';
type DirectionFilter = 'all' | 'up' | 'neutral' | 'down';
type VolatilityFilter = 'all' | 'low' | 'medium' | 'high';
type HorizonFilter = '1d';
type SortField = 'confidence' | 'expectedReturn' | 'probability' | 'symbol' | 'price' | 'changePercent';
type SortDir = 'asc' | 'desc';

interface DisplayPrediction {
  symbol: string;
  name: string;
  exchange: string;
  price: number;
  changePercent: number;
  direction: 'up' | 'neutral' | 'down';
  probabilities: { up: number; neutral: number; down: number };
  expectedReturn: number;
  confidence: number;
  horizon: HorizonFilter;
  volatility?: number; // percent vol proxy 0-50
  predictionTimestamp?: string | null;
  modelVersion?: string | null;
  raw?: unknown;
}

const MARKET_META: Record<Exclude<MarketFilter, 'all'>, { label: string; code: string; exchanges: string[] }> = {
  us: { label: 'United States', code: 'US', exchanges: ['NASDAQ', 'NYSE', 'NYSEARCA', 'NYSEAMERICAN', 'AMEX'] },
  india: { label: 'India', code: 'IN', exchanges: ['NSE', 'BSE'] },
  europe: { label: 'Europe', code: 'EU', exchanges: ['XETRA', 'LSE', 'EPA', 'EURONEXT', 'FRA', 'XFRA', 'LON', 'AMS', 'PAR', 'XPAR'] },
};

function getMarketForExchange(exchange: string): MarketFilter {
  const ex = (exchange || '').toUpperCase().trim();
  if (!ex) return 'all';
  if (MARKET_META.india.exchanges.includes(ex)) return 'india';
  if (MARKET_META.europe.exchanges.some((e) => ex === e || ex.includes(e))) return 'europe';
  // US is default for NASDAQ/NYSE etc
  if (['NASDAQ', 'NYSE', 'NYSEARCA', 'AMEX', 'NYSEAMERICAN', 'OTC'].some((k) => ex.includes(k))) return 'us';
  if (ex.includes('XETRA') || ex.includes('LSE') || ex.includes('EPA')) return 'europe';
  if (ex === 'NSE' || ex === 'BSE') return 'india';
  return 'us';
}

function parseNumber(v: unknown, fallback = 0): number {
  if (v === null || v === undefined) return fallback;
  if (typeof v === 'number') return Number.isFinite(v) ? v : fallback;
  const n = Number(String(v));
  return Number.isFinite(n) ? n : fallback;
}

function normalizeProbabilities(rawProbs: unknown): { up: number; neutral: number; down: number } {
  let up = 0, neutral = 0, down = 0;
  if (rawProbs && typeof rawProbs === 'object') {
    const p = rawProbs as Record<string, unknown>;
    up = parseNumber(p.up ?? (p as Record<string, unknown>).up_probability ?? 0);
    neutral = parseNumber(p.neutral ?? (p as Record<string, unknown>).neutral_probability ?? 0);
    down = parseNumber(p.down ?? (p as Record<string, unknown>).down_probability ?? 0);
    // handle case where probabilities are inside probabilities object vs flat
    if (up === 0 && neutral === 0 && down === 0) {
      // try alternative keys
      up = parseNumber((rawProbs as Record<string, unknown>).up);
      neutral = parseNumber((rawProbs as Record<string, unknown>).neutral);
      down = parseNumber((rawProbs as Record<string, unknown>).down);
    }
  }
  const sum = up + neutral + down;
  const isFraction = sum > 0 && sum <= 1.2 && up <= 1 && neutral <= 1 && down <= 1;
  if (isFraction) {
    up = Math.round(up * 1000) / 10;
    neutral = Math.round(neutral * 1000) / 10;
    down = Math.round(down * 1000) / 10;
  } else {
    up = Math.round(up * 10) / 10;
    neutral = Math.round(neutral * 10) / 10;
    down = Math.round(down * 10) / 10;
  }
  // normalize to 100
  let total = up + neutral + down;
  if (total !== 100 && total > 0) {
    const diff = 100 - total;
    if (up >= neutral && up >= down) up = Math.round((up + diff) * 10) / 10;
    else if (neutral >= up && neutral >= down) neutral = Math.round((neutral + diff) * 10) / 10;
    else down = Math.round((down + diff) * 10) / 10;
  }
  // clamp
  up = Math.max(0, Math.min(100, up));
  neutral = Math.max(0, Math.min(100, neutral));
  down = Math.max(0, Math.min(100, down));
  return { up, neutral, down };
}

function normalizeExpectedReturn(v: unknown): number {
  let n = parseNumber(v, 0);
  // backend may return Decimal as fraction (0.011 = 1.1%) or percent (1.1)
  // Heuristic: if abs(n) < 1 && abs(n) > 0, and n*100 < 30 → treat as fraction => *100
  if (Math.abs(n) < 1 && Math.abs(n) > 0) {
    const cand = n * 100;
    // only convert if candidate is in reasonable range (<15) and original is small fractional
    if (Math.abs(cand) < 25 && Math.abs(n) < 0.5) return Math.round(cand * 100) / 100;
    if (Math.abs(cand) < 30) return Math.round(cand * 100) / 100;
  }
  return Math.round(n * 100) / 100;
}

function normalizeHorizon(): HorizonFilter {
  // v1.0 is a 1-day model; the horizon is fixed, never honored from input (§15).
  return '1d';
}

function normalizePrediction(raw: Record<string, unknown>): DisplayPrediction {
  const symbol = String(raw.symbol ?? raw.ticker ?? 'UNKNOWN').toUpperCase();
  const name = String(raw.name ?? raw.display_name ?? raw.company_name ?? symbol);
  const exchange = String(raw.exchange ?? raw.exchange_code ?? 'NASDAQ').toUpperCase();
  const price = parseNumber(raw.price ?? raw.last_price ?? raw.close ?? 0);
  const changePercent = parseNumber(raw.change_percent ?? raw.changePercent ?? raw.change ?? 0);
  // direction
  const dirRaw = String(raw.direction ?? raw.predicted_direction ?? 'neutral').toLowerCase();
  const direction: DisplayPrediction['direction'] = dirRaw === 'up' ? 'up' : dirRaw === 'down' ? 'down' : 'neutral';
  // probabilities
  const probsInput = (raw.probabilities as unknown) ?? {
    up: raw.up_probability ?? raw.upProbability,
    neutral: raw.neutral_probability ?? raw.neutralProbability,
    down: raw.down_probability ?? raw.downProbability,
  };
  const probabilities = normalizeProbabilities(probsInput);
  const expectedReturn = normalizeExpectedReturn(raw.expected_return ?? raw.expectedReturn ?? 0);
  const confidence = Math.round(parseNumber(raw.confidence ?? 50));
  const horizon = normalizeHorizon();
  // volatility proxy from features_snapshot or direct
  let volatility: number | undefined;
  const snap = raw.features_snapshot as Record<string, unknown> | undefined;
  if (raw.volatility !== undefined) volatility = parseNumber(raw.volatility, 0);
  else if (snap) {
    const v = parseNumber(snap.volatility_20 ?? snap.volatility ?? snap.vol ?? 0);
    if (v) volatility = Math.abs(v) < 2 ? v * 100 : v; // convert fraction to percent if needed
  }
  if (volatility === undefined || Number.isNaN(volatility)) {
    // estimate from expected range width
    const low = parseNumber(raw.range_lower ?? (snap as Record<string, unknown> | undefined)?.range_lower ?? 0);
    const high = parseNumber(raw.range_upper ?? (snap as Record<string, unknown> | undefined)?.range_upper ?? 0);
    if (low !== 0 || high !== 0) {
      const width = Math.abs(high - low);
      // width is in fraction? convert similarly
      const widthPct = width < 1 ? width * 100 : width;
      volatility = Math.round(widthPct * 50) / 10; // arbitrary scaling
    }
  }
  if (volatility !== undefined) volatility = Math.round(volatility * 10) / 10;
  return {
    symbol,
    name,
    exchange,
    price,
    changePercent,
    direction,
    probabilities,
    expectedReturn,
    confidence: Math.max(0, Math.min(100, confidence)),
    horizon,
    volatility,
    predictionTimestamp: (raw.prediction_timestamp as string | null) ?? null,
    modelVersion: (raw.model_version as string | null) ?? null,
    raw,
  };
}

function directionBadgeClass(dir: DisplayPrediction['direction']) {
  if (dir === 'up') return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900';
  if (dir === 'down') return 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-900';
  return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900';
}

function changeBadgeClass(v: number) {
  if (v > 0) return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900';
  if (v < 0) return 'bg-red-50 text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-300 dark:ring-red-900';
  return 'bg-slate-50 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300';
}

function volatilityLabel(v?: number): string {
  if (v === undefined) return '—';
  if (v < 15) return 'Low';
  if (v < 30) return 'Medium';
  return 'High';
}

function horizonLabel() {
  // Single supported horizon (§15).
  return '1D';
}

// ---------------------------------------------------------------------------
// Mock data - fallback when API unavailable
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PredictionCardSkeleton() {
  return (
    <Card className="border-slate-200 dark:border-slate-800">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-2 min-w-0 flex-1">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="flex items-baseline justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40">
          <div className="space-y-2">
            <Skeleton className="h-6 w-20" />
            <Skeleton className="h-4 w-16 rounded-full" />
          </div>
          <Skeleton className="h-9 w-9 rounded-lg" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-2 w-full rounded-full" />
          <Skeleton className="h-2 w-full rounded-full" />
          <Skeleton className="h-2 w-full rounded-full" />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
        </div>
        <Skeleton className="h-8 w-full rounded-lg" />
      </CardContent>
    </Card>
  );
}

function PredictionCardItem({ p, onClick }: { p: DisplayPrediction; onClick?: () => void }) {
  const isUp = p.direction === 'up';
  const isDown = p.direction === 'down';
  const DirIcon = isUp ? TrendingUp : isDown ? TrendingDown : Minus;
  const market = getMarketForExchange(p.exchange);
  const meta = market !== 'all' && MARKET_META[market as Exclude<MarketFilter, 'all'>] ? MARKET_META[market as Exclude<MarketFilter, 'all'>] : null;

  return (
    <Link
      href={`/stocks/${encodeURIComponent(p.symbol)}?exchange=${encodeURIComponent(p.exchange)}`}
      className="block group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
      aria-label={`View ${p.symbol} prediction details`}
    >
      <Card className="h-full overflow-hidden border-slate-200 bg-white shadow-sm transition-all hover:shadow-md hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700 flex flex-col">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 min-w-0">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white text-xs font-bold dark:bg-white dark:text-slate-900">
                  {p.symbol.charAt(0)}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-mono text-sm font-semibold tracking-tight truncate">{p.symbol}</span>
                    <Badge variant="outline" className="hidden sm:inline-flex font-mono text-[10px] leading-none px-1.5 py-0.5 shrink-0 border-slate-200 dark:border-slate-700">
                      {p.exchange}
                    </Badge>
                    {meta && <span className="hidden rounded bg-slate-200 px-1 font-mono text-[10px] font-bold dark:bg-slate-700 sm:inline" aria-hidden>{meta.code}</span>}
                  </div>
                  <div className="text-xs text-muted-foreground truncate max-w-[160px] sm:max-w-[200px]">{p.name}</div>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className="rounded-full border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  <Clock className="mr-1 h-3 w-3" />
                  {horizonLabel()}
                </Badge>
                {(() => {
                  const age = relativeAge(p.predictionTimestamp ?? undefined);
                  const stale = (() => {
                    if (!p.predictionTimestamp) return false;
                    const t = new Date(p.predictionTimestamp).getTime();
                    return Number.isFinite(t) && Date.now() - t > 24 * 3600 * 1000;
                  })();
                  return (
                    <span
                      className={cn(
                        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] tabular-nums ring-1',
                        stale
                          ? 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:ring-amber-900'
                          : 'bg-slate-50 text-slate-500 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700',
                      )}
                      title={p.modelVersion ? `Model ${p.modelVersion}` : 'Model version unknown'}
                    >
                      {stale ? 'stale · ' : ''}as of {age ?? '—'}
                      {p.modelVersion ? ` · ${p.modelVersion}` : ''}
                    </span>
                  );
                })()}
                <Badge variant="outline" className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', volatilityLabel(p.volatility) === 'Low' ? 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300' : volatilityLabel(p.volatility) === 'High' ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900' : 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:border-blue-900')}>
                  Vol {volatilityLabel(p.volatility)}
                </Badge>
                {p.volatility !== undefined && (
                  <span className="text-[11px] font-mono tabular-nums text-muted-foreground">{p.volatility.toFixed(1)}%</span>
                )}
              </div>
            </div>
            <Badge className={cn('shrink-0 gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold tabular-nums', directionBadgeClass(p.direction))}>
              <DirIcon className="h-3.5 w-3.5" />
              {p.direction.toUpperCase()} {p.probabilities.up}%
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-4 pt-0 flex-1 flex flex-col">
          {/* Price row */}
          <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2.5 dark:border-slate-800 dark:bg-slate-800/40">
            <div className="min-w-0">
              <div className="font-mono text-[17px] font-semibold leading-none tracking-tight tabular-nums">
                {p.exchange === 'NSE' || p.exchange === 'BSE' ? `₹${p.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : formatPrice(p.price, 'USD')}
              </div>
              <div className={cn('mt-1 inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-semibold tabular-nums', changeBadgeClass(p.changePercent))}>
                {p.changePercent > 0 ? <TrendingUp className="h-3 w-3" /> : p.changePercent < 0 ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                {formatPercent(p.changePercent)}
              </div>
            </div>
            <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-sm', p.changePercent >= 0 ? 'border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400' : 'border-red-200 bg-red-50 text-red-600 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400')}>
              <BarChart3 className="h-4 w-4" />
            </div>
          </div>

          {/* Probabilities */}
          <div className="space-y-2.5 rounded-lg border border-slate-100 bg-slate-50/50 p-3 dark:border-slate-800 dark:bg-slate-800/30">
            {([
              { label: 'UP', value: p.probabilities.up, color: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
              { label: 'NEUTRAL', value: p.probabilities.neutral, color: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400' },
              { label: 'DOWN', value: p.probabilities.down, color: 'bg-red-500', text: 'text-red-600 dark:text-red-400' },
            ] as const).map((row) => (
              <div key={row.label} className="space-y-1">
                <div className="flex items-center justify-between text-[11px] font-medium leading-none">
                  <span className="text-slate-700 dark:text-slate-300 tracking-wide">{row.label}</span>
                  <span className={cn('font-mono font-semibold tabular-nums', row.text)}>{row.value}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700/80">
                  <div className={cn('h-full rounded-full transition-all', row.color)} style={{ width: `${row.value}%` }} />
                </div>
              </div>
            ))}
            <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground">
              <span>Calibrated • sum 100%</span>
              <span className="font-mono tabular-nums">P(up) {p.probabilities.up}%</span>
            </div>
          </div>

          {/* Expected return + confidence */}
          <div className="grid grid-cols-3 gap-2 text-center mt-auto">
            <div className="rounded-lg border border-slate-200 bg-white px-2 py-2.5 dark:border-slate-800 dark:bg-slate-900">
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Exp. return</div>
              <div className={cn('mt-1 text-sm font-semibold tabular-nums', p.expectedReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                {p.expectedReturn >= 0 ? '+' : ''}{p.expectedReturn.toFixed(2)}%
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-2 py-2.5 dark:border-slate-800 dark:bg-slate-900">
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Confidence</div>
              <div className="mt-1 text-sm font-semibold tabular-nums text-slate-900 dark:text-white">{p.confidence}%</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-2 py-2.5 dark:border-slate-800 dark:bg-slate-900">
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Horizon</div>
              <div className="mt-1 text-sm font-semibold tabular-nums text-slate-900 dark:text-white">{horizonLabel()}</div>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1 text-xs">
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Target className="h-3 w-3" />
              View stock
              <ArrowUpRight className="h-3 w-3 opacity-60 group-hover:opacity-100 transition-opacity" />
            </span>
            <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{p.symbol} • {p.exchange}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function PredictionsPage() {
  // Filters
  const [market, setMarket] = useState<MarketFilter>('all');
  const [direction, setDirection] = useState<DirectionFilter>('all');
  const [horizon, setHorizon] = useState<HorizonFilter>('1d');
  const [volatility, setVolatility] = useState<VolatilityFilter>('all');
  const [confidenceMin, setConfidenceMin] = useState<number>(0);
  const [expectedReturnMin, setExpectedReturnMin] = useState<number>(-5); // allow negative to show all, default -5 means all
  const [searchQuery, setSearchQuery] = useState<string>('');

  // UI
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [sortField, setSortField] = useState<SortField>('confidence');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Data
  const [predictions, setPredictions] = useState<DisplayPrediction[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch
  const fetchPredictions = useCallback(async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setIsRefreshing(true);
    else setIsLoading(true);
    setError(null);

    try {
      const filters: Record<string, unknown> = {
        horizon,
        limit: 100,
      };
      if (direction !== 'all') (filters as Record<string, unknown>).direction = direction;
      if (confidenceMin > 0) (filters as Record<string, unknown>).confidenceMin = confidenceMin;
      if (expectedReturnMin > -5) (filters as Record<string, unknown>).expectedReturnMin = expectedReturnMin;

      // Use backend api.getTopPredictions
      let raw: unknown[] | null = null;
      try {
        // Prefer lib/api client method
        raw = (await api.getTopPredictions({
          horizon,
          direction: direction !== 'all' ? direction : undefined,
          confidenceMin: confidenceMin > 0 ? confidenceMin : undefined,
          expectedReturnMin: expectedReturnMin > -5 ? expectedReturnMin : undefined,
          limit: 100,
        } as never)) as unknown[];
      } catch (e) {
        // Try alternative import path via predictions lib
        try {
          const { getTopPredictions } = await import('@/lib/api/predictions');
          raw = await getTopPredictions({
            direction: direction !== 'all' ? direction : undefined,
            confidenceMin: confidenceMin > 0 ? confidenceMin : undefined,
            expectedReturnMin: expectedReturnMin > -5 ? expectedReturnMin : undefined,
            limit: 100,
          } as never) as unknown[];
        } catch {
          throw e;
        }
      }

      if (!Array.isArray(raw)) {
        // backend may return { items: [] } or { data: [] } shaped
        const maybe = raw as Record<string, unknown>;
        if (Array.isArray(maybe.items)) raw = maybe.items as unknown[];
        else if (Array.isArray(maybe.data)) raw = maybe.data as unknown[];
        else if (Array.isArray((maybe as unknown as { results: unknown[] }).results)) raw = (maybe as unknown as { results: unknown[] }).results;
        else raw = [];
      }

      let normalized: DisplayPrediction[] = [];
      if (Array.isArray(raw) && raw.length > 0) {
        normalized = (raw as Record<string, unknown>[]).map((r) => normalizePrediction(r));
        // Filter out invalid
        normalized = normalized.filter((p) => p.symbol && p.exchange);
      }

      // If backend returned empty but not error, show empty (don't fallback) - but for dev we fallback only on error or initial
      if (normalized.length === 0) {
        // If we had successful fetch but empty, respect empty state (don't use mock)
        setPredictions([]);
      } else {
        // Ensure unique symbols
        const seen = new Set<string>();
        const deduped: DisplayPrediction[] = [];
        for (const p of normalized) {
          const key = `${p.symbol}-${p.exchange}`;
          if (!seen.has(key)) {
            seen.add(key);
            deduped.push(p);
          }
        }
        setPredictions(deduped);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : typeof err === 'string' ? err : 'Failed to load predictions. Live model feed unavailable.';
      setError(msg || 'Failed to load predictions. Live model feed unavailable.');
      // Do NOT fallback to mock financial data — show UNAVAILABLE
      setPredictions([]);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [horizon, direction, confidenceMin, expectedReturnMin]);

  useEffect(() => {
    fetchPredictions();
  }, [fetchPredictions]);

  // Client-side filtering + sorting
  const filteredAndSorted = useMemo(() => {
    let out = [...predictions];

    // Market filter (client-side - backend doesn't support market directly efficiently)
    if (market !== 'all') {
      out = out.filter((p) => getMarketForExchange(p.exchange) === market);
    }

    // Volatility filter (client-side)
    if (volatility !== 'all') {
      out = out.filter((p) => {
        const v = p.volatility ?? 0;
        if (volatility === 'low') return v < 15;
        if (volatility === 'medium') return v >= 15 && v < 30;
        if (volatility === 'high') return v >= 30;
        return true;
      });
    }

    // Search query (client-side)
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      out = out.filter(
        (p) =>
          p.symbol.toLowerCase().includes(q) ||
          p.name.toLowerCase().includes(q) ||
          p.exchange.toLowerCase().includes(q)
      );
    }

    // Additional client-side for confidence / expected return / direction if backend didn't filter sharply
    if (confidenceMin > 0) out = out.filter((p) => p.confidence >= confidenceMin);
    if (expectedReturnMin > -5) out = out.filter((p) => p.expectedReturn >= expectedReturnMin);
    if (direction !== 'all') out = out.filter((p) => p.direction === direction);
    if (horizon) out = out.filter((p) => p.horizon === horizon);

    // Sorting
    out.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'confidence':
          cmp = a.confidence - b.confidence;
          break;
        case 'expectedReturn':
          cmp = a.expectedReturn - b.expectedReturn;
          break;
        case 'probability':
          cmp = a.probabilities.up - b.probabilities.up;
          break;
        case 'symbol':
          cmp = a.symbol.localeCompare(b.symbol);
          break;
        case 'price':
          cmp = a.price - b.price;
          break;
        case 'changePercent':
          cmp = a.changePercent - b.changePercent;
          break;
        default:
          cmp = 0;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return out;
  }, [predictions, market, volatility, searchQuery, confidenceMin, expectedReturnMin, direction, horizon, sortField, sortDir]);

  const hasActiveFilters =
    market !== 'all' ||
    direction !== 'all' ||
    volatility !== 'all' ||
    confidenceMin > 0 ||
    expectedReturnMin > -5 ||
    searchQuery.trim().length > 0;

  const activeChips: Array<{ key: string; label: string; onClear: () => void }> = [];
  if (market !== 'all') activeChips.push({ key: 'market', label: `Market: ${market.toUpperCase()}`, onClear: () => setMarket('all') });
  if (direction !== 'all') activeChips.push({ key: 'direction', label: `Direction: ${direction.toUpperCase()}`, onClear: () => setDirection('all') });
  if (volatility !== 'all') activeChips.push({ key: 'volatility', label: `Volatility: ${volatility}`, onClear: () => setVolatility('all') });
  if (confidenceMin > 0) activeChips.push({ key: 'confidence', label: `Confidence ≥ ${confidenceMin}%`, onClear: () => setConfidenceMin(0) });
  if (expectedReturnMin > -5) activeChips.push({ key: 'exp', label: `Exp. return ≥ ${expectedReturnMin >= 0 ? '+' : ''}${expectedReturnMin.toFixed(1)}%`, onClear: () => setExpectedReturnMin(-5) });
  if (searchQuery.trim()) activeChips.push({ key: 'search', label: `Search: "${searchQuery.trim()}"`, onClear: () => setSearchQuery('') });

  const clearAllFilters = useCallback(() => {
    setMarket('all');
    setDirection('all');
    setHorizon('1d');
    setVolatility('all');
    setConfidenceMin(0);
    setExpectedReturnMin(-5);
    setSearchQuery('');
  }, []);

  const handleSort = useCallback((field: SortField) => {
    setSortField((prev) => {
      if (prev === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        return prev;
      }
      setSortDir(field === 'symbol' ? 'asc' : 'desc');
      return field;
    });
  }, []);

  // Stats
  const stats = useMemo(() => {
    if (filteredAndSorted.length === 0) return null;
    const avgConfidence = Math.round(filteredAndSorted.reduce((s, p) => s + p.confidence, 0) / filteredAndSorted.length);
    const avgExp = filteredAndSorted.reduce((s, p) => s + p.expectedReturn, 0) / filteredAndSorted.length;
    const upCount = filteredAndSorted.filter((p) => p.direction === 'up').length;
    const downCount = filteredAndSorted.filter((p) => p.direction === 'down').length;
    return { avgConfidence, avgExp, upCount, downCount };
  }, [filteredAndSorted]);

  return (
    <div className="min-h-screen bg-slate-50/60 dark:bg-slate-950">
      <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1.5 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                <Sparkles className="h-4 w-4" />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Predictions</h1>
              <Badge variant="outline" className="hidden sm:inline-flex rounded-full border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                <Brain className="mr-1 h-3 w-3" />
                Model signals
              </Badge>
              <Badge className="rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                {isLoading ? '—' : `${filteredAndSorted.length} shown`}
                <span className="hidden sm:inline">&nbsp;•&nbsp;{predictions.length} fetched</span>
              </Badge>
              {stats && (
                <Badge variant="outline" className="hidden lg:inline-flex rounded-full border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                  <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{stats.upCount} UP</span>
                  <span className="mx-1 text-slate-300">•</span>
                  <span className="text-red-600 dark:text-red-400 font-semibold">{stats.downCount} DOWN</span>
                  <span className="mx-1 text-slate-300">•</span>
                  Avg conf {stats.avgConfidence}% • Avg ER {stats.avgExp >= 0 ? '+' : ''}{stats.avgExp.toFixed(2)}%
                </Badge>
              )}
            </div>
            <p className="max-w-[760px] text-sm leading-6 text-slate-600 dark:text-slate-400">
              Strongest model signals across global markets. Filter by market, direction, confidence, expected return, volatility, or search. Click any card/row to view the full stock analysis.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                <Clock className="h-3 w-3" />
                Horizon {horizonLabel()} • Sorted by {sortField} {sortDir === 'desc' ? '↓' : '↑'}
              </span>
              <span className="hidden sm:inline-flex items-center gap-1 text-xs">
                <Info className="h-3 w-3" />
                Probabilistic — not investment advice. Past performance does not guarantee future results.
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 self-start">
            <div className="hidden sm:flex items-center rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-800 dark:bg-slate-900">
              <Button variant={viewMode === 'grid' ? 'secondary' : 'ghost'} size="sm" className="h-7 px-2.5" onClick={() => setViewMode('grid')} aria-label="Grid view">
                <LayoutGrid className="h-4 w-4" />
                <span className="hidden lg:inline ml-1">Grid</span>
              </Button>
              <Button variant={viewMode === 'table' ? 'secondary' : 'ghost'} size="sm" className="h-7 px-2.5" onClick={() => setViewMode('table')} aria-label="Table view">
                <TableIcon className="h-4 w-4" />
                <span className="hidden lg:inline ml-1">Table</span>
              </Button>
            </div>
            <Button variant="outline" size="sm" onClick={() => fetchPredictions(true)} disabled={isLoading || isRefreshing} className="bg-white dark:bg-slate-900">
              <RefreshCw className={cn('h-4 w-4', (isLoading || isRefreshing) && 'animate-spin')} />
              {isRefreshing ? 'Refreshing' : 'Refresh'}
            </Button>
          </div>
        </div>

        {/* Filter Bar */}
        <Card className="overflow-hidden border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <CardHeader className="pb-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300">
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                </div>
                <CardTitle className="text-sm font-semibold tracking-tight">Filters</CardTitle>
                <Badge variant="secondary" className="rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs">
                  {filteredAndSorted.length} / {predictions.length}
                </Badge>
                {hasActiveFilters && (
                  <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={clearAllFilters}>
                    <X className="h-3 w-3" />
                    Clear filters
                  </Button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="hidden text-xs text-muted-foreground sm:inline">7 filters • chips below • sortable</span>
                <Badge variant="outline" className="rounded-full border-slate-200 bg-white hidden sm:inline-flex dark:border-slate-800 dark:bg-slate-900">
                  <Filter className="mr-1 h-3 w-3" />
                  {activeChips.length} active
                </Badge>
              </div>
            </div>
            <CardDescription className="text-xs leading-5">
              Backend filters: Horizon, Direction, Confidence, Expected return via <span className="font-mono font-medium">api.getTopPredictions</span> — Market, Volatility, and Search are applied client-side for instant feedback. Use sliders for threshold controls.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {/* Main filter grid */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {/* Search */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                  <Search className="h-3 w-3" />
                  Search query
                </label>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Symbol or name — e.g. AAPL, Reliance, SAP"
                    className="pl-8 h-8 text-sm"
                    aria-label="Search predictions"
                  />
                  {searchQuery && (
                    <Button variant="ghost" size="icon-xs" className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6" onClick={() => setSearchQuery('')}>
                      <X className="h-3 w-3" />
                    </Button>
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground">Matches symbol, name, or exchange.</p>
              </div>

              {/* Market */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Market</label>
                <Select value={market} onValueChange={(v) => setMarket(v as MarketFilter)}>
                  <SelectTrigger className="h-8 text-sm w-full">
                    <SelectValue placeholder="All markets" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All markets</SelectItem>
                    <SelectItem value="us">[US] United States — NASDAQ/NYSE</SelectItem>
                    <SelectItem value="india">[IN] India — NSE/BSE</SelectItem>
                    <SelectItem value="europe">[EU] Europe — XETRA/LSE/EPA</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Inferred from exchange code.</p>
              </div>

              {/* Direction */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Direction</label>
                <Select value={direction} onValueChange={(v) => setDirection(v as DirectionFilter)}>
                  <SelectTrigger className="h-8 text-sm w-full">
                    <SelectValue placeholder="All directions" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All — UP/NEUTRAL/DOWN</SelectItem>
                    <SelectItem value="up">UP — Bullish</SelectItem>
                    <SelectItem value="neutral">NEUTRAL — Range</SelectItem>
                    <SelectItem value="down">DOWN — Bearish</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Model predicted direction.</p>
              </div>

              {/* Horizon — v1.0 natively forecasts the next trading day only;
                  weekly/monthly labels are refused by the API (§15), so no
                  choice is offered here. */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Horizon</label>
                <div className="flex h-8 items-center rounded-md border border-input bg-muted/40 px-3 text-sm font-medium">
                  1D — Next trading day
                </div>
                <p className="text-[11px] text-muted-foreground">v1.0 native forecast window.</p>
              </div>
            </div>

            {/* Second row: Volatility, Sliders */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {/* Volatility */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Volatility</label>
                <Select value={volatility} onValueChange={(v) => setVolatility(v as VolatilityFilter)}>
                  <SelectTrigger className="h-8 text-sm w-full">
                    <SelectValue placeholder="All volatility" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All volatility</SelectItem>
                    <SelectItem value="low">Low — &lt;15%</SelectItem>
                    <SelectItem value="medium">Medium — 15-30%</SelectItem>
                    <SelectItem value="high">High — ≥30%</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">20-day vol proxy.</p>
              </div>

              {/* Confidence min */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Confidence min</label>
                  <span className="rounded-md bg-slate-900 px-1.5 py-0.5 font-mono text-xs font-semibold text-white dark:bg-white dark:text-slate-900 tabular-nums">
                    {confidenceMin}%
                  </span>
                </div>
                <Slider
                  value={[confidenceMin]}
                  onValueChange={(value) => {
                    const v = Array.isArray(value) ? (value[0] as number) : (value as number);
                    setConfidenceMin(typeof v === 'number' && Number.isFinite(v) ? v : 0);
                  }}
                  min={0}
                  max={100}
                  step={5}
                  className="py-2"
                  aria-label="Confidence minimum"
                />
                <div className="flex justify-between text-[11px] text-muted-foreground tabular-nums">
                  <span>0%</span>
                  <span>50%</span>
                  <span>100%</span>
                </div>
              </div>

              {/* Expected return min */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Expected return min</label>
                  <span className={cn('rounded-md px-1.5 py-0.5 font-mono text-xs font-semibold tabular-nums', expectedReturnMin >= 0 ? 'bg-emerald-600 text-white' : 'bg-slate-900 text-white dark:bg-white dark:text-slate-900')}>
                    {expectedReturnMin <= -5 ? 'Any' : `${expectedReturnMin >= 0 ? '+' : ''}${expectedReturnMin.toFixed(1)}%`}
                  </span>
                </div>
                <Slider
                  value={[expectedReturnMin]}
                  onValueChange={(value) => {
                    const v = Array.isArray(value) ? (value[0] as number) : (value as number);
                    setExpectedReturnMin(typeof v === 'number' && Number.isFinite(v) ? v : -5);
                  }}
                  min={-5}
                  max={5}
                  step={0.5}
                  className="py-2"
                  aria-label="Expected return minimum"
                />
                <div className="flex justify-between text-[11px] text-muted-foreground tabular-nums">
                  <span>-5%</span>
                  <span>0%</span>
                  <span>+5%</span>
                </div>
              </div>

              {/* Sort */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Sort by</label>
                <div className="flex gap-2">
                  <Select value={sortField} onValueChange={(v) => setSortField(v as SortField)}>
                    <SelectTrigger className="h-8 text-sm flex-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="confidence">Confidence</SelectItem>
                      <SelectItem value="expectedReturn">Expected return</SelectItem>
                      <SelectItem value="probability">UP Probability</SelectItem>
                      <SelectItem value="price">Price</SelectItem>
                      <SelectItem value="changePercent">Change %</SelectItem>
                      <SelectItem value="symbol">Symbol A→Z</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button variant="outline" size="sm" className="h-8 px-2.5 shrink-0" onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))} aria-label={`Sort ${sortDir === 'asc' ? 'ascending' : 'descending'}`}>
                    {sortDir === 'desc' ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
                    <span className="hidden sm:inline ml-1">{sortDir === 'desc' ? 'Desc' : 'Asc'}</span>
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">Applies to grid and table.</p>
              </div>
            </div>

            {/* Chips & clear */}
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {activeChips.length === 0 ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-800/30 dark:text-slate-400">
                    <Filter className="h-3 w-3" />
                    No active filters — showing all 1D-horizon markets. Use controls above to narrow.
                  </span>
                ) : (
                  activeChips.map((chip) => (
                    <Badge key={chip.key} variant="secondary" className="group gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                      <span>{chip.label}</span>
                      <button
                        type="button"
                        onClick={chip.onClear}
                        className="ml-1 rounded-full p-0.5 hover:bg-slate-100 dark:hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label={`Clear ${chip.key}`}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))
                )}
                {activeChips.length > 0 && (
                  <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={clearAllFilters}>
                    Clear all
                  </Button>
                )}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/50 text-xs">
                <span className="text-muted-foreground">
                  <span className="font-semibold text-slate-900 dark:text-white">{filteredAndSorted.length}</span> of <span className="font-mono tabular-nums">{predictions.length}</span> predictions match • Click column headers in table view to sort • Cards link to stock page
                </span>
                <span className="hidden items-center gap-1.5 sm:inline-flex text-muted-foreground">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Live signals
                  <span className="mx-1">•</span>
                  {horizonLabel()} horizon
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Mobile view toggle */}
        <div className="flex sm:hidden items-center justify-between">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">View</span>
          <div className="flex items-center rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-800 dark:bg-slate-900">
            <Button variant={viewMode === 'grid' ? 'secondary' : 'ghost'} size="sm" className="h-7 flex-1" onClick={() => setViewMode('grid')}>
              <LayoutGrid className="h-4 w-4 mr-1.5" />
              Grid
            </Button>
            <Button variant={viewMode === 'table' ? 'secondary' : 'ghost'} size="sm" className="h-7 flex-1" onClick={() => setViewMode('table')}>
              <TableIcon className="h-4 w-4 mr-1.5" />
              Table
            </Button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <Card className="border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20">
            <CardContent className="flex gap-3 p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
                <AlertTriangle className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">We couldn’t reach live predictions</p>
                <p className="mt-1 text-sm leading-5 text-amber-800/80 dark:text-amber-100/70 break-words">{error}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => fetchPredictions(true)} className="border-amber-200 bg-white text-amber-900 hover:bg-amber-50 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
                    <RefreshCw className="h-3.5 w-3.5" />
                    Retry — api.getTopPredictions
                  </Button>
                  <span className="inline-flex items-center text-xs text-amber-700/70 dark:text-amber-200/60">UNAVAILABLE — live feed returned no predictions</span>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setError(null)} className="shrink-0 text-amber-700 hover:bg-amber-100 dark:text-amber-300">
                Dismiss
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Content */}
        {isLoading ? (
          <>
            {viewMode === 'grid' ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <PredictionCardSkeleton key={i} />
                ))}
              </div>
            ) : (
              <Card className="border-slate-200 dark:border-slate-800">
                <CardContent className="p-0">
                  <div className="space-y-3 p-4">
                    <Skeleton className="h-6 w-40" />
                    {Array.from({ length: 6 }).map((_, i) => (
                      <Skeleton key={i} className="h-12 w-full" />
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        ) : filteredAndSorted.length === 0 ? (
          <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="flex flex-col items-center justify-center py-16 text-center px-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                <SearchX className="h-6 w-6 text-slate-400" />
              </div>
              <h3 className="mt-4 text-base font-semibold text-slate-900 dark:text-white">No predictions match your filters</h3>
              <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
                We found {predictions.length} predictions for horizon {horizonLabel()}, but none matched Market={market}, Direction={direction}, Volatility={volatility}, Confidence ≥ {confidenceMin}%, Expected return ≥ {expectedReturnMin <= -5 ? 'any' : `${expectedReturnMin}%`} and search “{searchQuery || '—'}”. Try widening thresholds or clearing filters.
              </p>
              <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row">
                <Button variant="outline" size="sm" onClick={clearAllFilters} className="bg-white dark:bg-slate-900">
                  <X className="h-4 w-4" />
                  Clear filters
                </Button>
                <Button variant="ghost" size="sm" onClick={() => fetchPredictions(true)}>
                  <RefreshCw className="h-4 w-4" />
                  Refresh predictions
                </Button>
                <Link href="/markets" className="text-sm font-medium text-primary hover:underline underline-offset-4">
                  Browse markets →
                </Link>
              </div>
              <div className="mt-6 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-800/30 dark:text-slate-400 max-w-lg">
                <span className="font-medium text-slate-900 dark:text-white">Example matches:</span> Try “AAPL UP 72% Expected return +1.1%” style signals — e.g., search <span className="font-mono font-semibold">AAPL</span> with <span className="font-mono font-semibold">Confidence ≥ 60%</span> and <span className="font-mono font-semibold">Horizon 1D</span> to see the strongest signals like AAPL 72% UP, NVDA 69% UP, RELIANCE 71% UP.
              </div>
            </CardContent>
          </Card>
        ) : viewMode === 'grid' ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3">
            {filteredAndSorted.map((p) => (
              <PredictionCardItem key={`${p.symbol}-${p.exchange}-${p.horizon}`} p={p} />
            ))}
          </div>
        ) : (
          <Card className="overflow-hidden border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-slate-50/70 dark:bg-slate-800/50">
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="h-9 font-semibold text-xs uppercase tracking-wide">
                        <button type="button" onClick={() => handleSort('symbol')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Symbol
                          {sortField === 'symbol' ? (sortDir === 'desc' ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />) : <span className="h-3 w-3 opacity-30">↕</span>}
                        </button>
                      </TableHead>
                      <TableHead className="h-9 hidden md:table-cell">Name</TableHead>
                      <TableHead className="h-9 font-semibold text-xs uppercase tracking-wide">
                        <button type="button" onClick={() => handleSort('price')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Price / Change
                          {sortField === 'price' ? (sortDir === 'desc' ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />) : null}
                        </button>
                      </TableHead>
                      <TableHead className="h-9 font-semibold text-xs uppercase tracking-wide">
                        <button type="button" onClick={() => handleSort('probability')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Direction
                          {sortField === 'probability' ? (sortDir === 'desc' ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />) : null}
                        </button>
                      </TableHead>
                      <TableHead className="h-9 hidden lg:table-cell text-right">Probabilities</TableHead>
                      <TableHead className="h-9 text-right">
                        <button type="button" onClick={() => handleSort('expectedReturn')} className="inline-flex items-center justify-end gap-1 hover:text-slate-900 dark:hover:text-white w-full">
                          Exp. return
                          {sortField === 'expectedReturn' ? (sortDir === 'desc' ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />) : null}
                        </button>
                      </TableHead>
                      <TableHead className="h-9 text-right">
                        <button type="button" onClick={() => handleSort('confidence')} className="inline-flex items-center justify-end gap-1 hover:text-slate-900 dark:hover:text-white w-full">
                          Confidence
                          {sortField === 'confidence' ? (sortDir === 'desc' ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />) : null}
                        </button>
                      </TableHead>
                      <TableHead className="h-9 text-right">Horizon</TableHead>
                      <TableHead className="h-9 text-right">
                        <span className="sr-only">Link</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredAndSorted.map((p) => {
                      const isUp = p.direction === 'up';
                      const isDown = p.direction === 'down';
                      return (
                        <TableRow key={`${p.symbol}-${p.exchange}-${p.horizon}-row`} className="group hover:bg-slate-50/70 dark:hover:bg-slate-800/40">
                          <TableCell className="py-2.5">
                            <div className="flex items-center gap-2">
                              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-900 text-[11px] font-bold text-white dark:bg-white dark:text-slate-900">
                                {p.symbol.charAt(0)}
                              </div>
                              <div className="min-w-0">
                                <div className="font-mono text-xs font-semibold tracking-wide flex items-center gap-1.5">
                                  {p.symbol}
                                  <Badge variant="outline" className="hidden sm:inline-flex font-mono text-[10px] px-1 py-0 h-4 border-slate-200 dark:border-slate-700">
                                    {p.exchange}
                                  </Badge>
                                </div>
                                <div className="text-[11px] text-muted-foreground hidden sm:block md:hidden lg:hidden truncate max-w-[100px]">{p.name}</div>
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="hidden md:table-cell py-2.5">
                            <div className="max-w-[160px] truncate text-xs font-medium text-slate-700 dark:text-slate-300" title={p.name}>
                              {p.name}
                            </div>
                            <div className="text-[11px] text-muted-foreground">{getMarketForExchange(p.exchange) !== 'all' ? MARKET_META[getMarketForExchange(p.exchange) as Exclude<MarketFilter, 'all'>]?.label : p.exchange} • Vol {volatilityLabel(p.volatility)}</div>
                          </TableCell>
                          <TableCell className="py-2.5">
                            <div className="font-mono text-xs font-semibold tabular-nums">
                              {p.exchange === 'NSE' || p.exchange === 'BSE' ? `₹${p.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : formatPrice(p.price, 'USD')}
                            </div>
                            <div className={cn('inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums mt-1', changeBadgeClass(p.changePercent))}>
                              {p.changePercent > 0 ? <TrendingUp className="h-3 w-3" /> : p.changePercent < 0 ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                              {formatPercent(p.changePercent)}
                            </div>
                          </TableCell>
                          <TableCell className="py-2.5">
                            <Badge className={cn('gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold', directionBadgeClass(p.direction))}>
                              {isUp ? <TrendingUp className="h-3 w-3" /> : isDown ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                              {p.direction.toUpperCase()} {p.probabilities.up}%
                            </Badge>
                            <div className="mt-1 text-[11px] font-mono tabular-nums text-muted-foreground">
                              P(neutral) {p.probabilities.neutral}% • P(down) {p.probabilities.down}%
                            </div>
                          </TableCell>
                          <TableCell className="hidden lg:table-cell py-2.5">
                            <div className="w-[132px] space-y-1">
                              <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700 flex">
                                <div className="h-full bg-emerald-500" style={{ width: `${p.probabilities.up}%` }} />
                                <div className="h-full bg-amber-500" style={{ width: `${p.probabilities.neutral}%` }} />
                                <div className="h-full bg-red-500" style={{ width: `${p.probabilities.down}%` }} />
                              </div>
                              <div className="flex justify-between text-[10px] font-mono tabular-nums text-muted-foreground">
                                <span className="text-emerald-600">{p.probabilities.up}%</span>
                                <span className="text-amber-600">{p.probabilities.neutral}%</span>
                                <span className="text-red-600">{p.probabilities.down}%</span>
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="py-2.5 text-right font-mono text-xs font-semibold tabular-nums">
                            <span className={cn(p.expectedReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                              {p.expectedReturn >= 0 ? '+' : ''}{p.expectedReturn.toFixed(2)}%
                            </span>
                          </TableCell>
                          <TableCell className="py-2.5 text-right">
                            <span className={cn('inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums border', p.confidence >= 70 ? 'bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900 dark:border-white' : p.confidence >= 55 ? 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700' : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900')}>
                              {p.confidence}%
                            </span>
                          </TableCell>
                          <TableCell className="py-2.5 text-right">
                            <Badge variant="outline" className="font-mono text-[11px] border-slate-200 dark:border-slate-700">
                              {horizonLabel()}
                            </Badge>
                          </TableCell>
                          <TableCell className="py-2.5 text-right">
                            <Link
                              href={`/stocks/${encodeURIComponent(p.symbol)}?exchange=${encodeURIComponent(p.exchange)}`}
                              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                            >
                              View
                              <ArrowUpRight className="h-3 w-3" />
                            </Link>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
              <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50/50 px-4 py-3 text-xs text-muted-foreground dark:border-slate-800 dark:bg-slate-800/30">
                <span>
                  Showing <span className="font-mono font-semibold text-slate-900 dark:text-white tabular-nums">{filteredAndSorted.length}</span> of <span className="font-mono tabular-nums">{predictions.length}</span> predictions • sorted by {sortField} {sortDir}
                </span>
                <span className="hidden sm:inline">Click headers to sort • Each row links to stock page</span>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Footer note */}
        <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <CardContent className="p-4">
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                <Info className="h-4 w-4" />
              </div>
              <div className="space-y-1 text-xs leading-5 text-slate-600 dark:text-slate-400">
                <p className="font-medium text-slate-900 dark:text-white text-sm">About predictions</p>
                <p>
                  Predictions are generated by an ensemble model retrained with walk-forward validation. Probabilities are calibrated; expected return is the probability-weighted mean. Confidence reflects separation between P(up) and P(down) and model agreement. Always use predictions alongside fundamentals, risk limits, and diversification. See <Link href="/research" className="underline underline-offset-4 hover:text-slate-900 dark:hover:text-white">Research & Disclosures</Link> for methodology and limitations.
                </p>
                <p className="text-[11px] text-slate-500 dark:text-slate-500">
                  Data via <span className="font-mono font-medium">api.getTopPredictions</span> with horizon/direction/confidence/expectedReturn filters. Market/Volatility/Search are refined client-side for instant UX. Prices may be delayed per exchange policy.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
