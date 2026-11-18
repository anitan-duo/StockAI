'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatCard } from '@/components/ui/stat-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import {
  AlertTriangle,
  FlaskConical,
  TrendingUp,
  TrendingDown,
  Minus,
  Play,
  RefreshCw,
  Info,
  Activity,
  BarChart3,
  LineChart as LineChartIcon,
  ShieldAlert,
  Calendar,
  DollarSign,
  History,
  SearchX,
  Timer,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STRATEGIES = [
  'ML Ensemble v1.0',
  'Momentum + ML',
  'Mean Reversion + ML',
  'Trend Following + ML',
] as const;

const HORIZONS = [
  { value: '1d', label: '1 Day (1d)' },
  { value: '1w', label: '1 Week (1w)' },
  { value: '1m', label: '1 Month (1m)' },
] as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Horizon = '1d' | '1w' | '1m';

interface NormalizedTrade {
  id: string;
  entryDate: string;
  exitDate: string;
  entryPrice: number;
  exitPrice: number | null;
  shares: number;
  side: string;
  pnl: number | null;
  returnPct: number | null;
  isWinner: boolean | null;
}

interface NormalizedBacktestResult {
  id: string;
  symbol: string;
  strategy: string;
  config: {
    symbol: string;
    strategy: string;
    startDate: string;
    endDate: string;
    horizon: Horizon;
    initialCapital: number;
  };
  totalReturn: number;
  annualizedReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;
  winRate: number;
  profitFactor: number;
  equityCurve: { date: string; value: number }[];
  drawdownCurve: { date: string; value: number }[];
  returnsDistribution: { range: string; count: number }[];
  trades: NormalizedTrade[];
  status: string;
  isSample: boolean;
  completedAt?: string;
  errorMessage?: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseNumber(v: unknown, fallback = 0): number {
  if (v === null || v === undefined) return fallback;
  if (typeof v === 'number') return Number.isFinite(v) ? v : fallback;
  const n = parseFloat(String(v));
  return Number.isFinite(n) ? n : fallback;
}

function formatPercent(v: number, digits = 2): string {
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(digits)}%`;
}

function formatISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function hashCode(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    const chr = str.charCodeAt(i);
    h = (h << 5) - h + chr;
    h |= 0;
  }
  return Math.abs(h);
}

function seededRandom(seed: number) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function toShortDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch (err) {
    console.debug('[backtesting] toShortDate fallback', err);
    return iso.slice(0, 10);
  }
}

function normalizeCurve(raw: unknown): { date: string; value: number }[] {
  if (!Array.isArray(raw)) return [];
  return (raw as unknown[])
    .map((item: unknown) => {
      const r = item as Record<string, unknown>;
      const date = (r.date ?? r.timestamp ?? r.time ?? '') as string;
      const value = parseNumber(r.value ?? r.equity ?? r.price ?? 0);
      return { date: String(date), value };
    })
    .filter((d) => d.date && Number.isFinite(d.value))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
}

function normalizeDistribution(raw: unknown): { range: string; count: number }[] {
  if (!Array.isArray(raw)) return [];
  return (raw as unknown[]).map((item: unknown) => {
    const r = item as Record<string, unknown>;
    return {
      range: String(r.range ?? r.label ?? ''),
      count: parseNumber(r.count ?? r.value ?? 0, 0),
    };
  });
}

function normalizeTrades(raw: unknown): NormalizedTrade[] {
  if (!Array.isArray(raw)) return [];
  return (raw as unknown[]).map((item: unknown, idx: number) => {
    const r = item as Record<string, unknown>;
    const entryDate = String(r.entry_date ?? r.entryDate ?? r.date ?? r.timestamp ?? '');
    const exitDate = String(r.exit_date ?? r.exitDate ?? r.exit_date ?? r.date ?? '');
    const entryPrice = parseNumber(r.entry_price ?? r.entryPrice ?? r.price ?? 0);
    const exitPriceRaw = r.exit_price ?? r.exitPrice ?? null;
    const exitPrice = exitPriceRaw !== null && exitPriceRaw !== undefined ? parseNumber(exitPriceRaw, 0) : null;
    const shares = parseNumber(r.shares ?? 0, 0);
    const side = String(r.side ?? r.action ?? 'long');
    const pnlRaw = r.pnl ?? null;
    const pnl = pnlRaw !== null && pnlRaw !== undefined ? parseNumber(pnlRaw, 0) : null;
    const retRaw = r.return_pct ?? r.returnPct ?? r.return ?? null;
    const returnPct = retRaw !== null && retRaw !== undefined ? parseNumber(retRaw, 0) : null;
    let isWinner: boolean | null = null;
    if (typeof r.is_winner === 'boolean') isWinner = r.is_winner as boolean;
    else if (typeof r.isWinner === 'boolean') isWinner = r.isWinner as boolean;
    else if (pnl !== null) isWinner = pnl > 0;
    else if (returnPct !== null) isWinner = returnPct > 0;

    return {
      id: String(r.id ?? `${entryDate}-${idx}`),
      entryDate: entryDate || new Date().toISOString(),
      exitDate: exitDate || entryDate || new Date().toISOString(),
      entryPrice,
      exitPrice,
      shares,
      side,
      pnl,
      returnPct,
      isWinner,
    };
  });
}

function normalizeBacktestResult(
  raw: unknown,
  fallback: { symbol: string; strategy: string; horizon: Horizon; initialCapital: number; startDate: string; endDate: string }
): NormalizedBacktestResult {
  const r = raw as Record<string, unknown>;
  const btRaw = (r.backtest ?? r) as Record<string, unknown>;
  const tradesRaw = (r.trades ?? btRaw.trades ?? []) as unknown;

  // Prefer backtest fields, fallback to top-level metrics
  const totalReturn = parseNumber(btRaw.total_return ?? btRaw.totalReturn ?? r.total_return ?? r.totalReturn ?? 0);
  const annualizedReturn = parseNumber(btRaw.annualized_return ?? btRaw.annualizedReturn ?? r.annualized_return ?? r.annualizedReturn ?? 0);
  const sharpeRatio = parseNumber(btRaw.sharpe_ratio ?? btRaw.sharpeRatio ?? r.sharpe_ratio ?? r.sharpeRatio ?? 0);
  const maxDrawdown = parseNumber(btRaw.max_drawdown ?? btRaw.maxDrawdown ?? r.max_drawdown ?? r.maxDrawdown ?? 0);
  const winRate = parseNumber(btRaw.win_rate ?? btRaw.winRate ?? r.win_rate ?? r.winRate ?? 0);
  const profitFactor = parseNumber(btRaw.profit_factor ?? btRaw.profitFactor ?? r.profit_factor ?? r.profitFactor ?? 0);

  const equityCurve = normalizeCurve(btRaw.equity_curve ?? btRaw.equityCurve ?? r.equity_curve ?? r.equityCurve);
  const drawdownCurve = normalizeCurve(btRaw.drawdown_curve ?? btRaw.drawdownCurve ?? r.drawdown_curve ?? r.drawdownCurve);
  const returnsDistribution = normalizeDistribution(
    btRaw.returns_distribution ?? btRaw.returnsDistribution ?? r.returns_distribution ?? r.returnsDistribution
  );

  const trades = normalizeTrades(tradesRaw);

  // If drawdownCurve empty but equityCurve exists, derive drawdown
  let derivedDrawdown = drawdownCurve;
  if (derivedDrawdown.length === 0 && equityCurve.length > 0) {
    let peak = equityCurve[0]?.value ?? fallback.initialCapital;
    derivedDrawdown = equityCurve.map((p) => {
      peak = Math.max(peak, p.value);
      const dd = peak > 0 ? ((p.value - peak) / peak) * 100 : 0;
      return { date: p.date, value: Math.round(dd * 100) / 100 };
    });
  }

  // If returnsDistribution empty but trades exist, derive distribution similar to backend
  let derivedDistribution = returnsDistribution;
  if (derivedDistribution.length === 0 && trades.length > 0) {
    const returns = trades.map((t) => t.returnPct ?? 0).filter((v) => Number.isFinite(v)) as number[];
    const bins: [number, number, string][] = [
      [-Infinity, -3, '< -3%'],
      [-3, -2, '-3% to -2%'],
      [-2, -1, '-2% to -1%'],
      [-1, 0, '-1% to 0%'],
      [0, 1, '0% to 1%'],
      [1, 2, '1% to 2%'],
      [2, 3, '2% to 3%'],
      [3, Infinity, '> 3%'],
    ];
    derivedDistribution = bins.map(([low, high, label]) => {
      const count =
        low === -Infinity
          ? returns.filter((v) => v < high).length
          : high === Infinity
            ? returns.filter((v) => v >= low).length
            : returns.filter((v) => v >= low && v < high).length;
      return { range: label, count };
    });
  }

  const id = String(btRaw.id ?? r.id ?? `bt-${Date.now()}`);
  const status = String(btRaw.status ?? r.status ?? 'completed');
  const completedAt = (btRaw.completed_at ?? btRaw.completedAt ?? r.completed_at) as string | undefined;
  const errorMessage = (btRaw.error_message ?? btRaw.errorMessage ?? null) as string | null;

  const startDate = String(btRaw.start_date ?? btRaw.startDate ?? fallback.startDate);
  const endDate = String(btRaw.end_date ?? btRaw.endDate ?? fallback.endDate);
  const horizon = (String(btRaw.horizon ?? fallback.horizon) as Horizon) || fallback.horizon;
  const initialCapital = parseNumber(btRaw.initial_capital ?? btRaw.initialCapital ?? fallback.initialCapital);

  const symbol = String(
    (btRaw.instrument as Record<string, unknown> | undefined)?.symbol ??
      (r.instrument as Record<string, unknown> | undefined)?.symbol ??
      fallback.symbol
  ).toUpperCase();
  const strategy =
    (btRaw.model_version as Record<string, unknown> | undefined)?.version?.toString() ??
    (btRaw.model_version as Record<string, unknown> | undefined)?.name?.toString() ??
    fallback.strategy;

  return {
    id,
    symbol,
    strategy: String(strategy),
    config: {
      symbol,
      strategy: fallback.strategy,
      startDate,
      endDate,
      horizon,
      initialCapital,
    },
    totalReturn,
    annualizedReturn,
    sharpeRatio,
    maxDrawdown,
    winRate,
    profitFactor,
    equityCurve,
    drawdownCurve: derivedDrawdown,
    returnsDistribution: derivedDistribution,
    trades,
    status,
    isSample: false,
    completedAt,
    errorMessage,
  };
}

// ---------------------------------------------------------------------------
// Small UI pieces
// ---------------------------------------------------------------------------

function StatSkeleton() {
  return (
    <Card className="border-slate-200 dark:border-slate-800">
      <CardContent className="p-4 space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-7 w-20" />
        <Skeleton className="h-3 w-32" />
      </CardContent>
    </Card>
  );
}

function ChartSkeleton() {
  return (
    <Card className="border-slate-200 dark:border-slate-800">
      <CardHeader>
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-48" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-[280px] w-full rounded-lg" />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BacktestingPage() {
  // Defaults: start = 1 year ago, end = yesterday. Computed client-side in
  // an effect, NOT during render: these dates differ between the static
  // prerender and a later hydration (e.g. after midnight), which threw React
  // hydration error #418. SSR-safe empty initials, filled on mount.
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  useEffect(() => {
    const end = addDays(new Date(), -1);
    setEndDate((v) => v || formatISODate(end));
    setStartDate((v) => v || formatISODate(addDays(end, -365)));
  }, []);

  const [symbol, setSymbol] = useState('AAPL');
  const [strategy, setStrategy] = useState<string>(STRATEGIES[0]);
  const [horizon, setHorizon] = useState<Horizon>('1d');
  const [initialCapital, setInitialCapital] = useState<string>('10000');

  const [result, setResult] = useState<NormalizedBacktestResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasRun, setHasRun] = useState(false);
  const [chartTab, setChartTab] = useState<'equity' | 'drawdown' | 'distribution'>('equity');
  const [history, setHistory] = useState<NormalizedBacktestResult[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [activeResultsTab, setActiveResultsTab] = useState<'overview' | 'trades' | 'history'>('overview');

  // Load history on mount
  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const data = await api.getBacktests({ limit: 10 });
      if (Array.isArray(data) && data.length > 0) {
        const mapped: NormalizedBacktestResult[] = data
          .map((raw: unknown) => {
            try {
              const r = raw as Record<string, unknown>;
              const bt = (r.backtest ?? r) as Record<string, unknown>;
              // If raw already looks like BacktestResponse, normalize via helper
              const sym = String(
                (bt.instrument as Record<string, unknown> | undefined)?.symbol ??
                  (r.symbol as string | undefined) ??
                  'UNKNOWN'
              );
              const strat = String(
                (bt.model_version as Record<string, unknown> | undefined)?.version ??
                  (bt.strategy as string | undefined) ??
                  'ML Ensemble v1.0'
              );
              return normalizeBacktestResult(raw, {
                symbol: sym,
                strategy: strat,
                horizon: (String(bt.horizon ?? '1d') as Horizon) ?? '1d',
                initialCapital: parseNumber(bt.initial_capital ?? 10000),
                startDate: String(bt.start_date ?? new Date().toISOString()),
                endDate: String(bt.end_date ?? new Date().toISOString()),
              });
            } catch (err) {
              console.warn('[backtesting] history item mapping failed', err);
              return null;
            }
          })
          .filter(Boolean) as NormalizedBacktestResult[];
        setHistory(mapped);
      } else {
        setHistory([]);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      // Don't surface auth errors as blocking; just keep history empty
      if (msg.toLowerCase().includes('unauthorized') || msg.toLowerCase().includes('401')) {
        setHistory([]);
      } else {
        setHistoryError(msg);
      }
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const capitalNumber = useMemo(() => parseNumber(initialCapital, NaN), [initialCapital]);

  const validationError = useMemo(() => {
    if (!symbol.trim()) return 'Stock symbol is required.';
    if (!/^[A-Za-z0-9.\-]{1,12}$/.test(symbol.trim())) return 'Symbol must be 1–12 letters/numbers, dot or dash.';
    if (!strategy) return 'Please select a strategy.';
    if (!startDate || !endDate) return 'Start and end dates are required.';
    const s = new Date(startDate);
    const e = new Date(endDate);
    if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return 'Invalid date format.';
    if (s >= e) return 'Start date must be before end date.';
    if (e > new Date()) return 'End date cannot be in the future.';
    const diffDays = (e.getTime() - s.getTime()) / (1000 * 60 * 60 * 24);
    if (diffDays < 7) return 'Backtest period must be at least 7 days.';
    if (diffDays > 365 * 10) return 'Backtest period cannot exceed 10 years.';
    if (!Number.isFinite(capitalNumber) || capitalNumber <= 0) return 'Initial capital must be greater than 0.';
    if (capitalNumber < 100) return 'Initial capital must be at least $100.';
    if (capitalNumber > 10_000_000) return 'Initial capital cannot exceed $10,000,000.';
    if (!['1d', '1w', '1m'].includes(horizon)) return 'Invalid horizon.';
    return null;
  }, [symbol, strategy, startDate, endDate, capitalNumber, horizon]);

  const canRun = !isLoading && !validationError;

  const handleRun = useCallback(async () => {
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setIsLoading(true);
    setHasRun(true);

    const startISO = new Date(startDate).toISOString();
    const endISO = new Date(endDate).toISOString();
    const cap = capitalNumber;

    // Helper: resolve instrument id
    const resolveInstrumentId = async (): Promise<string | null> => {
      try {
        const results = await api.searchInstruments(symbol.trim(), { limit: 5 });
        if (Array.isArray(results) && results.length > 0) {
          const exact = (results as unknown[]).find((r) => {
            const rec = r as Record<string, unknown>;
            return String(rec.symbol ?? '').toUpperCase() === symbol.trim().toUpperCase();
          }) as Record<string, unknown> | undefined;
          const chosen = (exact ?? (results[0] as Record<string, unknown>)) as Record<string, unknown>;
          const id = (chosen.id ?? chosen.instrument_id ?? chosen.instrumentId ?? chosen.uuid) as string | undefined;
          if (id) return String(id);
        }
      } catch (err) {
        console.warn('[backtesting] searchInstruments failed', err);
      }
      try {
        const inst = await api.getInstrument(symbol.trim().toUpperCase(), 'NASDAQ');
        if (inst?.id) return String(inst.id);
        if (inst?.instrument_id) return String(inst.instrument_id);
      } catch (err) {
        console.warn('[backtesting] getInstrument fallback failed', err);
      }
      return null;
    };

    const resolveModelVersionId = async (): Promise<string | null> => {
      // Try to hit training/models endpoint if available; fallback to null
      try {
        const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
        const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        // Try listing model versions for a default model name
        const candidates = ['ensemble', 'ml_ensemble', 'default', 'stock_prediction'];
        for (const name of candidates) {
          try {
            const res = await fetch(`${base}/training/models/${encodeURIComponent(name)}/versions`, { headers });
            if (res.ok) {
              const data: unknown = await res.json();
              if (Array.isArray(data) && data.length > 0) {
                const first = data[0] as Record<string, unknown>;
                const id = (first.id ?? first.model_version_id ?? first.uuid) as string | undefined;
                if (id) return String(id);
                // If array of strings (versions), try to fetch model details?
                // Fall through to next attempt
              } else if (data && typeof data === 'object') {
                const rec = data as Record<string, unknown>;
                // Some implementations return {versions: [...]}
                const versions = (rec.versions ?? rec.data) as unknown;
                if (Array.isArray(versions) && versions.length > 0) {
                  const v0 = versions[0] as Record<string, unknown>;
                  const id2 = (v0.id ?? v0.model_version_id) as string | undefined;
                  if (id2) return String(id2);
                }
              }
            }
          } catch {
            // Candidate fallback is intentional: try next candidate name.
          }
        }
        // Try generic models list
        try {
          const res = await fetch(`${base}/training/models`, { headers });
          if (res.ok) {
            const data: unknown = await res.json();
            if (data && typeof data === 'object') {
              const rec = data as Record<string, unknown>;
              for (const key of Object.keys(rec)) {
                const val = rec[key] as unknown;
                if (Array.isArray(val) && val.length > 0) {
                  const v0 = val[0] as unknown;
                  if (typeof v0 === 'string') continue;
                  const obj = v0 as Record<string, unknown>;
                  const id = (obj.id ?? obj.model_version_id) as string | undefined;
                  if (id) return String(id);
                }
              }
            }
          }
        } catch (err) {
          console.warn('[backtesting] model list fallback failed', err);
        }
      } catch (err) {
        console.warn('[backtesting] resolveModelVersionId failed', err);
      }
      return null;
    };

    try {
      const instrumentId = await resolveInstrumentId();
      const modelVersionId = await resolveModelVersionId();

      // If we have both IDs, attempt real backend flow
      if (instrumentId && modelVersionId) {
        try {
          const payload = {
            instrument_id: instrumentId,
            model_version_id: modelVersionId,
            start_date: startISO,
            end_date: endISO,
            horizon,
            initial_capital: cap,
          };
          const created = await api.createBacktest(payload as unknown as { instrument_id: string; model_version_id: string; start_date: string; end_date: string; horizon: string; initial_capital: number; });
          const createdRec = created as unknown as Record<string, unknown>;
          const createdId = createdRec.id ?? (createdRec.backtest as Record<string, unknown> | undefined)?.id ?? createdRec.backtest_id;
          if (createdId) {
            const runResult = await api.runBacktest(String(createdId));
            const normalized = normalizeBacktestResult(runResult, {
              symbol: symbol.trim().toUpperCase(),
              strategy,
              horizon,
              initialCapital: cap,
              startDate: startISO,
              endDate: endISO,
            });
            normalized.isSample = false;
            setResult(normalized);
            // Refresh history
            fetchHistory().catch((err) => {
              console.warn('[backtesting] fetchHistory refresh failed', err);
            });
            return;
          }
        } catch (apiErr: unknown) {
          const msg = apiErr instanceof Error ? apiErr.message : String(apiErr);
          // No synthetic fallback: surface the backend error; UNAVAILABLE is set below.
          if (msg.toLowerCase().includes('instrument not found') || msg.toLowerCase().includes('model version not found')) {
            console.warn('Backtest API validation failed:', msg);
          } else if (msg.toLowerCase().includes('unauthorized') || msg.toLowerCase().includes('401')) {
            console.warn('Unauthorized for backtest:', msg);
          } else {
            console.warn('Backtest API error:', msg);
          }
        }
      } else {
        // No IDs resolved; cannot run a real backtest.
        if (!instrumentId) console.warn('Instrument not resolved for symbol', symbol);
        if (!modelVersionId) console.warn('Model version not resolved.');
      }

      // Do NOT synthesize fake financial data. Show UNAVAILABLE when live data not available.
      setError('UNAVAILABLE: Real backtest requires live instrument and model version with sufficient historical data. No mock financial data shown. Ensure backend is reachable and instrument has at least 252 bars.');
      setResult(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg || 'Failed to run backtest.');
      if (!result) setResult(null);
    } finally {
      setIsLoading(false);
    }
  }, [validationError, startDate, endDate, capitalNumber, symbol, strategy, horizon, result, fetchHistory]);

  const handleReset = useCallback(() => {
    setResult(null);
    setError(null);
    setHasRun(false);
  }, []);

  const handleHistorySelect = useCallback(async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getBacktest(id);
      const normalized = normalizeBacktestResult(data, {
        symbol: symbol.trim().toUpperCase(),
        strategy,
        horizon,
        initialCapital: capitalNumber,
        startDate: new Date(startDate).toISOString(),
        endDate: new Date(endDate).toISOString(),
      });
      setResult(normalized);
      setHasRun(true);
      setActiveResultsTab('overview');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsLoading(false);
    }
  }, [symbol, strategy, horizon, capitalNumber, startDate, endDate]);

  // Chart data memo
  const equityChartData = useMemo(() => {
    if (!result?.equityCurve.length) return [];
    return result.equityCurve.map((p) => ({
      date: toShortDate(p.date),
      rawDate: p.date,
      value: p.value,
    }));
  }, [result]);

  const drawdownChartData = useMemo(() => {
    if (!result?.drawdownCurve.length) return [];
    return result.drawdownCurve.map((p) => ({
      date: toShortDate(p.date),
      rawDate: p.date,
      value: p.value, // negative
    }));
  }, [result]);

  const distributionData = useMemo(() => {
    if (!result?.returnsDistribution.length) return [];
    return result.returnsDistribution;
  }, [result]);

  const isEmptyBeforeRun = !hasRun && !isLoading && !result && !error;
  const isSample = result?.isSample;

  return (
    <div className="min-h-screen bg-slate-50/60 dark:bg-slate-950">
      <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                <FlaskConical className="h-4 w-4" />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Backtesting</h1>
              <Badge variant="outline" className="hidden rounded-full border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 sm:inline-flex">
                <Layers className="mr-1 h-3 w-3" />
                Walk-forward • Out-of-sample
              </Badge>
              {result && isSample && (
                <Badge variant="secondary" className="rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                  Sample data
                </Badge>
              )}
            </div>
            <p className="max-w-[760px] text-sm leading-6 text-slate-600 dark:text-slate-400">
              Evaluate probabilistic strategies on historical data. Configure symbol, model, horizon and capital — then inspect equity, drawdown, win-rate and trade-level reproducibility. Use{' '}
              <span className="font-medium text-slate-900 dark:text-white">Run backtest</span> to generate a fresh simulation.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                <Timer className="h-3 w-3" />
                Horizon: 1d / 1w / 1m
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                <span className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-700" />
                Not investment advice. Past simulated performance ≠ future results.
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 self-start sm:self-auto">
            {hasRun && (
              <Button variant="outline" size="sm" onClick={handleReset} className="bg-white dark:bg-slate-900">
                <RefreshCw className="h-4 w-4" />
                Reset
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={fetchHistory} disabled={historyLoading} className="bg-white dark:bg-slate-900 hidden sm:inline-flex">
              <History className={cn('h-4 w-4', historyLoading && 'animate-spin')} />
              History
            </Button>
          </div>
        </div>

        {/* Controls */}
        <Card className="overflow-hidden border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <CardHeader className="pb-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Activity className="h-4 w-4 text-slate-700 dark:text-slate-300" />
                  Backtest Configuration
                </CardTitle>
                <CardDescription className="mt-1 max-w-[640px] text-xs leading-relaxed">
                  All inputs are validated client-side before submission. Backend flow uses{' '}
                  <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">api.createBacktest</code> →{' '}
                  <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">api.runBacktest</code> when a live instrument and model version can be resolved; otherwise a deterministic local simulation is shown so the page remains fully interactive.
                </CardDescription>
              </div>
              <Badge variant="outline" className="rounded-full border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300">
                <ShieldAlert className="mr-1 h-3 w-3" />
                No look-ahead bias
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {/* Symbol */}
              <div className="space-y-1.5">
                <Label htmlFor="symbol" className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-700 dark:text-slate-300">
                  <SearchX className="h-3 w-3" />
                  Stock Symbol
                </Label>
                <Input
                  id="symbol"
                  placeholder="e.g. AAPL"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase().replace(/[^A-Z0-9.\-]/g, '').slice(0, 12))}
                  className="font-mono uppercase tracking-wide"
                  autoComplete="off"
                  spellCheck={false}
                />
                <p className="text-[11px] text-muted-foreground">Exchange defaults to NASDAQ; resolved via search.</p>
              </div>

              {/* Strategy */}
              <div className="space-y-1.5">
                <Label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-700 dark:text-slate-300">
                  <Layers className="h-3 w-3" />
                  Strategy / Model
                </Label>
                <Select value={strategy} onValueChange={(v) => setStrategy(v ?? STRATEGIES[0])}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select strategy" />
                  </SelectTrigger>
                  <SelectContent>
                    {STRATEGIES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Maps to a versioned model on the backend.</p>
              </div>

              {/* Horizon */}
              <div className="space-y-1.5">
                <Label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-700 dark:text-slate-300">
                  <Timer className="h-3 w-3" />
                  Prediction Horizon
                </Label>
                <Select value={horizon} onValueChange={(v) => setHorizon((v as Horizon) ?? '1d')}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {HORIZONS.map((h) => (
                      <SelectItem key={h.value} value={h.value}>
                        {h.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Holding + evaluation window. 1d = daily, 1w = weekly.</p>
              </div>

              {/* Start Date */}
              <div className="space-y-1.5">
                <Label htmlFor="startDate" className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-700 dark:text-slate-300">
                  <Calendar className="h-3 w-3" />
                  Start Date
                </Label>
                <Input id="startDate" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} max={endDate} />
              </div>

              {/* End Date */}
              <div className="space-y-1.5">
                <Label htmlFor="endDate" className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-700 dark:text-slate-300">
                  <Calendar className="h-3 w-3" />
                  End Date
                </Label>
                <Input id="endDate" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} min={startDate} max={formatISODate(new Date())} />
              </div>

              {/* Initial Capital */}
              <div className="space-y-1.5">
                <Label htmlFor="capital" className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-700 dark:text-slate-300">
                  <DollarSign className="h-3 w-3" />
                  Initial Capital (USD)
                </Label>
                <Input
                  id="capital"
                  type="number"
                  inputMode="decimal"
                  min={100}
                  max={10000000}
                  step={100}
                  placeholder="10000"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(e.target.value)}
                  className="font-mono tabular-nums"
                />
                <p className="text-[11px] text-muted-foreground">Used for equity curve base; P&L scales linearly.</p>
              </div>
            </div>

            {validationError && hasRun && (
              <Alert className="border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                <AlertTitle className="text-amber-800 dark:text-amber-200 text-sm">Check configuration</AlertTitle>
                <AlertDescription className="text-amber-700 dark:text-amber-300 text-xs">{validationError}</AlertDescription>
              </Alert>
            )}

            {error && (
              <Alert variant="destructive" className="border-red-200 bg-red-50 dark:bg-red-950/20">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Backtest failed</AlertTitle>
                <AlertDescription className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="truncate">{error}</span>
                  <Button variant="outline" size="sm" className="h-7 shrink-0" onClick={handleRun}>
                    <RefreshCw className="h-3 w-3 mr-1" />
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            )}

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-dashed border-slate-200 bg-slate-50/70 px-3 py-3 dark:border-slate-800 dark:bg-slate-800/30">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                <span className="inline-flex items-center gap-1.5">
                  <Info className="h-3 w-3" />
                  Creates a backtest via <code className="font-mono text-[11px]">POST /backtests</code> then runs it. Requires live instrument.
                </span>
                <span className="hidden h-3 w-px bg-slate-300 dark:bg-slate-700 sm:block" />
                <span className="text-[11px]">If the backend is offline, a deterministic sample is rendered so charts remain testable.</span>
              </div>
              <Button onClick={handleRun} disabled={!canRun} className="shrink-0 gap-2 w-full sm:w-auto">
                {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {isLoading ? 'Running…' : 'Run backtest'}
              </Button>
            </div>

            <div className="flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-800 dark:bg-slate-900">
                Symbol: <span className="font-mono font-semibold">{symbol || '—'}</span>
              </span>
              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-800 dark:bg-slate-900">
                Range: <span className="font-mono">{startDate || '—'}</span> → <span className="font-mono">{endDate || '—'}</span>
              </span>
              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-800 dark:bg-slate-900">
                Horizon: <span className="font-medium">{horizon.toUpperCase()}</span> • Capital: <span className="font-mono">${capitalNumber ? capitalNumber.toLocaleString() : '—'}</span>
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Loading state */}
        {isLoading && (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <StatSkeleton key={i} />
              ))}
            </div>
            <div className="grid gap-6 lg:grid-cols-2">
              <ChartSkeleton />
              <ChartSkeleton />
            </div>
            <Card className="border-slate-200 dark:border-slate-800">
              <CardHeader>
                <Skeleton className="h-4 w-32" />
              </CardHeader>
              <CardContent className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Empty before run */}
        {isEmptyBeforeRun && (
          <Card className="border-dashed border-slate-300 bg-white dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="flex flex-col items-center justify-center py-16 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                <FlaskConical className="h-6 w-6 text-slate-500 dark:text-slate-400" />
              </div>
              <h3 className="mt-4 text-sm font-semibold text-slate-900 dark:text-white">No backtest yet</h3>
              <p className="mt-1 max-w-md text-sm leading-5 text-slate-500 dark:text-slate-400">
                Configure a symbol, strategy, date range, horizon and capital above, then click{' '}
                <span className="font-medium text-slate-700 dark:text-slate-300">Run backtest</span> to generate equity, drawdown and trade-level results. You will see total return, Sharpe, max drawdown, win rate and profit factor here.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2 text-xs">
                <Badge variant="outline" className="rounded-full">Example: AAPL • 2023-01-01 → 2024-01-01 • 1d • $10,000</Badge>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error empty (when error and no result) */}
        {!isLoading && error && !result && hasRun && (
          <Card className="border-red-200 bg-red-50 dark:border-red-900/50 dark:bg-red-950/20">
            <CardContent className="flex flex-col items-center justify-center py-12 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-300">
                <AlertTriangle className="h-6 w-6" />
              </div>
              <h3 className="mt-4 text-sm font-semibold text-red-900 dark:text-red-200">We couldn’t run this backtest</h3>
              <p className="mt-1 max-w-md text-sm leading-5 text-red-700/80 dark:text-red-100/70">{error}</p>
              <div className="mt-4 flex gap-2">
                <Button size="sm" variant="outline" onClick={handleRun} className="border-red-200 bg-white text-red-700 hover:bg-red-50 dark:border-red-900 dark:bg-red-950 dark:text-red-100">
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try again
                </Button>
                <Button size="sm" variant="ghost" onClick={handleReset} className="text-red-700 dark:text-red-300">
                  Reset
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {!isLoading && result && (
          <div className="space-y-6">
            {/* StatCards */}
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-900 dark:text-white">Performance</h2>
                  <Badge variant="outline" className="rounded-full border-slate-200 bg-white font-mono text-xs dark:border-slate-800 dark:bg-slate-900">
                    {result.symbol} • {result.strategy} • {result.config.horizon.toUpperCase()}
                  </Badge>
                  <Badge
                    className={cn(
                      'rounded-full text-xs border',
                      result.status === 'completed'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    )}
                  >
                    {result.status.toUpperCase()}
                  </Badge>
                  {isSample && (
                    <Badge variant="outline" className="rounded-full border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
                      Sample
                    </Badge>
                  )}
                </div>
                <span className="text-xs text-muted-foreground hidden sm:inline">
                  {new Date(result.config.startDate).toLocaleDateString()} → {new Date(result.config.endDate).toLocaleDateString()} • Capital ${result.config.initialCapital.toLocaleString()}
                </span>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <StatCard
                  label="Total Return"
                  value={`${result.totalReturn >= 0 ? '+' : ''}${result.totalReturn.toFixed(2)}%`}
                  className={cn('border-slate-200 dark:border-slate-800', result.totalReturn >= 0 ? 'bg-emerald-50/40 dark:bg-emerald-950/10' : 'bg-red-50/40 dark:bg-red-950/10')}
                />
                <StatCard
                  label="Annualized Return"
                  value={`${result.annualizedReturn >= 0 ? '+' : ''}${result.annualizedReturn.toFixed(2)}%`}
                  className="border-slate-200 dark:border-slate-800"
                />
                <StatCard label="Sharpe Ratio" value={result.sharpeRatio.toFixed(2)} className="border-slate-200 dark:border-slate-800" />
                <StatCard
                  label="Maximum Drawdown"
                  value={`${result.maxDrawdown.toFixed(2)}%`}
                  className="border-slate-200 dark:border-slate-800 bg-red-50/20 dark:bg-red-950/5"
                />
                <StatCard label="Win Rate" value={`${result.winRate.toFixed(1)}%`} className="border-slate-200 dark:border-slate-800" />
                <StatCard label="Profit Factor" value={result.profitFactor.toFixed(2)} className="border-slate-200 dark:border-slate-800" />
              </div>

              {/* Mini summary strip */}
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-800 dark:bg-slate-900">
                  <TrendingUp className={cn('h-3 w-3', result.totalReturn >= 0 ? 'text-emerald-600' : 'text-red-600')} />
                  Total <span className={cn('font-mono font-semibold tabular-nums', result.totalReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>{formatPercent(result.totalReturn)}</span>
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-800 dark:bg-slate-900">
                  <Activity className="h-3 w-3 text-slate-500" />
                  Sharpe <span className="font-mono font-semibold tabular-nums">{result.sharpeRatio.toFixed(2)}</span>
                  <span className="text-slate-400">• risk-adjusted</span>
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-800 dark:bg-slate-900">
                  <ArrowDownRight className="h-3 w-3 text-red-500" />
                  Max DD <span className="font-mono font-semibold tabular-nums text-red-600 dark:text-red-400">{result.maxDrawdown.toFixed(2)}%</span>
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 dark:border-slate-800 dark:bg-slate-900">
                  Win <span className="font-mono font-semibold tabular-nums">{result.winRate.toFixed(1)}%</span> • PF <span className="font-mono font-semibold tabular-nums">{result.profitFactor.toFixed(2)}</span>
                </span>
                {isSample && <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-1 font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">Sample simulation — connect live data for verified results</span>}
              </div>
            </div>

            {/* Charts + Trades Tabs */}
            <Tabs value={activeResultsTab} onValueChange={(v) => setActiveResultsTab(v as typeof activeResultsTab)} className="w-full">
              <TabsList className="inline-flex h-auto w-full justify-start gap-1 overflow-x-auto rounded-lg bg-slate-100 p-1 dark:bg-slate-900">
                <TabsTrigger value="overview" className="whitespace-nowrap gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800">
                  <LineChartIcon className="h-3.5 w-3.5" />
                  Overview & Charts
                </TabsTrigger>
                <TabsTrigger value="trades" className="whitespace-nowrap gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800">
                  <BarChart3 className="h-3.5 w-3.5" />
                  Trades {result.trades.length ? `(${result.trades.length})` : ''}
                </TabsTrigger>
                <TabsTrigger value="history" className="whitespace-nowrap gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800">
                  <History className="h-3.5 w-3.5" />
                  History
                </TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="mt-4 space-y-6">
                {/* Charts inner tabs */}
                <Tabs value={chartTab} onValueChange={(v) => setChartTab(v as typeof chartTab)}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <TabsList className="inline-flex rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
                      <TabsTrigger value="equity" className="text-xs gap-1.5">
                        <TrendingUp className="h-3.5 w-3.5" />
                        Equity
                      </TabsTrigger>
                      <TabsTrigger value="drawdown" className="text-xs gap-1.5">
                        <TrendingDown className="h-3.5 w-3.5" />
                        Drawdown
                      </TabsTrigger>
                      <TabsTrigger value="distribution" className="text-xs gap-1.5">
                        <BarChart3 className="h-3.5 w-3.5" />
                        Distribution
                      </TabsTrigger>
                    </TabsList>
                    <span className="text-xs text-muted-foreground hidden sm:inline">
                      Hover for values • Responsive • Built with Recharts
                    </span>
                  </div>

                  <TabsContent value="equity" className="mt-4">
                    <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                      <CardHeader className="pb-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <div className="flex h-7 w-7 items-center justify-center rounded-md border border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400">
                              <LineChartIcon className="h-3.5 w-3.5" />
                            </div>
                            <div>
                              <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Equity Curve</CardTitle>
                              <CardDescription className="text-xs">Portfolio value over time • base ${result.config.initialCapital.toLocaleString()}</CardDescription>
                            </div>
                          </div>
                          <Badge variant="outline" className="rounded-full font-mono text-xs">
                            {result.equityCurve.length} points
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {equityChartData.length === 0 ? (
                          <div className="flex h-[280px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-800/20">
                            <div className="text-center">
                              <SearchX className="h-6 w-6 mx-auto text-slate-400" />
                              <p className="mt-2 text-sm font-medium text-slate-700 dark:text-slate-300">No equity data</p>
                              <p className="text-xs text-muted-foreground">Run a backtest with a longer period to generate curve.</p>
                            </div>
                          </div>
                        ) : (
                          <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart data={equityChartData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                                <defs>
                                  <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#059669" stopOpacity={0.28} />
                                    <stop offset="95%" stopColor="#059669" stopOpacity={0} />
                                  </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
                                <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} width={72} tickFormatter={(v: number) => `$${v.toLocaleString()}`} domain={['auto', 'auto']} />
                                <Tooltip
                                  contentStyle={{ backgroundColor: 'white', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                                  formatter={(value: unknown) => [`$${Number(value).toLocaleString()}`, 'Equity'] as unknown as [string, string]}
                                  labelFormatter={(label: unknown) => `Date: ${String(label)}`}
                                />
                                <Area type="monotone" dataKey="value" stroke="#059669" strokeWidth={2} fill="url(#equityFill)" dot={false} activeDot={{ r: 4, strokeWidth: 2, fill: '#fff', stroke: '#059669' }} />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                        )}
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
                          <span>Equity reflects simulated fills at next-bar close; no slippage beyond curve shown.</span>
                          <span className="font-mono tabular-nums">Last: ${result.equityCurve[result.equityCurve.length - 1]?.value.toLocaleString()}</span>
                        </div>
                      </CardContent>
                    </Card>
                  </TabsContent>

                  <TabsContent value="drawdown" className="mt-4">
                    <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                      <CardHeader className="pb-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-red-200 bg-red-50 text-red-600 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
                            <TrendingDown className="h-3.5 w-3.5" />
                          </div>
                          <div>
                            <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Drawdown</CardTitle>
                            <CardDescription className="text-xs">Peak-to-trough decline • negative = underwater</CardDescription>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {drawdownChartData.length === 0 ? (
                          <div className="flex h-[280px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-800/20">
                            <div className="text-center">
                              <SearchX className="h-6 w-6 mx-auto text-slate-400" />
                              <p className="mt-2 text-sm font-medium">No drawdown data</p>
                              <p className="text-xs text-muted-foreground">Run a backtest to compute drawdown.</p>
                            </div>
                          </div>
                        ) : (
                          <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <AreaChart data={drawdownChartData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                                <defs>
                                  <linearGradient id="ddFill" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#dc2626" stopOpacity={0.28} />
                                    <stop offset="95%" stopColor="#dc2626" stopOpacity={0} />
                                  </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
                                <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} width={72} tickFormatter={(v: number) => `${v.toFixed(1)}%`} domain={['auto', 0]} />
                                <Tooltip
                                  contentStyle={{ backgroundColor: 'white', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                                  formatter={(value: unknown) => [`${Number(value).toFixed(2)}%`, 'Drawdown']}
                                />
                                <Area type="monotone" dataKey="value" stroke="#dc2626" strokeWidth={2} fill="url(#ddFill)" dot={false} />
                              </AreaChart>
                            </ResponsiveContainer>
                          </div>
                        )}
                        <div className="mt-3 flex items-center gap-2 text-xs">
                          <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-1 font-mono font-semibold text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-300">
                            <ArrowDownRight className="h-3 w-3" />
                            Max DD {result.maxDrawdown.toFixed(2)}%
                          </span>
                          <span className="text-slate-500 dark:text-slate-400">Lower (more negative) = deeper pain. Zero = at peak.</span>
                        </div>
                      </CardContent>
                    </Card>
                  </TabsContent>

                  <TabsContent value="distribution" className="mt-4">
                    <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                      <CardHeader className="pb-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-violet-200 bg-violet-50 text-violet-600 dark:border-violet-900 dark:bg-violet-950/30 dark:text-violet-300">
                            <BarChart3 className="h-3.5 w-3.5" />
                          </div>
                          <div>
                            <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Returns Distribution</CardTitle>
                            <CardDescription className="text-xs">Trade return histogram • count per return bucket</CardDescription>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {distributionData.length === 0 ? (
                          <div className="flex h-[280px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-800/20">
                            <div className="text-center">
                              <SearchX className="h-6 w-6 mx-auto text-slate-400" />
                              <p className="mt-2 text-sm font-medium">No distribution data</p>
                              <p className="text-xs text-muted-foreground">Complete trades are required to build histogram.</p>
                            </div>
                          </div>
                        ) : (
                          <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={distributionData} margin={{ top: 10, right: 16, left: 0, bottom: 24 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                                <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#64748b' }} axisLine={false} tickLine={false} interval={0} angle={-16} textAnchor="end" height={48} />
                                <YAxis tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} width={40} allowDecimals={false} />
                                <Tooltip
                                  contentStyle={{ backgroundColor: 'white', border: '1px solid #e2e8f0', borderRadius: '8px', fontSize: '12px' }}
                                  formatter={(value: unknown) => [String(value), 'Trades']}
                                />
                                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} maxBarSize={44} />
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                        )}
                        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                          {distributionData.map((d) => (
                            <div key={d.range} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40">
                              <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{d.range}</div>
                              <div className="font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-white">{d.count}</div>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  </TabsContent>
                </Tabs>

                {/* Recent history mini-list also inside overview */}
                <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <History className="h-4 w-4 text-slate-600 dark:text-slate-300" />
                        <CardTitle className="text-sm">Recent Backtests</CardTitle>
                        <Badge variant="secondary" className="rounded-full text-[11px]">{history.length}</Badge>
                      </div>
                      <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={fetchHistory} disabled={historyLoading}>
                        <RefreshCw className={cn('h-3 w-3 mr-1', historyLoading && 'animate-spin')} />
                        Refresh
                      </Button>
                    </div>
                    <CardDescription className="text-xs">Via <code className="font-mono text-[11px]">GET /backtests</code> • most recent first</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {historyLoading ? (
                      <div className="space-y-2">
                        {Array.from({ length: 3 }).map((_, i) => (
                          <Skeleton key={i} className="h-12 w-full" />
                        ))}
                      </div>
                    ) : historyError ? (
                      <Alert className="py-2">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle className="text-xs">Unable to load history</AlertTitle>
                        <AlertDescription className="text-xs">{historyError}</AlertDescription>
                      </Alert>
                    ) : history.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center dark:border-slate-800 dark:bg-slate-800/30">
                        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">No saved backtests</p>
                        <p className="mt-1 text-xs text-muted-foreground">Run a backtest above; it will appear here after syncing with the backend.</p>
                      </div>
                    ) : (
                      <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
                        <Table>
                          <TableHeader className="bg-slate-50/70 dark:bg-slate-800/50">
                            <TableRow className="hover:bg-transparent">
                              <TableHead className="h-8 text-[11px] font-semibold uppercase tracking-wide">Backtest</TableHead>
                              <TableHead className="h-8 text-[11px] font-semibold uppercase tracking-wide hidden sm:table-cell">Period</TableHead>
                              <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide">Return</TableHead>
                              <TableHead className="h-8 text-right hidden md:table-cell text-[11px] font-semibold uppercase tracking-wide">Status</TableHead>
                              <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide"></TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {history.slice(0, 5).map((h) => (
                              <TableRow key={h.id} className="hover:bg-slate-50/70 dark:hover:bg-slate-800/50">
                                <TableCell className="py-2.5">
                                  <div className="flex flex-col">
                                    <span className="font-mono text-xs font-semibold tracking-wide">{h.symbol} • {h.strategy}</span>
                                    <span className="text-[11px] text-muted-foreground">{h.config.horizon.toUpperCase()} • ${h.config.initialCapital.toLocaleString()}</span>
                                  </div>
                                </TableCell>
                                <TableCell className="py-2.5 hidden sm:table-cell text-xs font-mono tabular-nums text-muted-foreground">
                                  {new Date(h.config.startDate).toLocaleDateString()} → {new Date(h.config.endDate).toLocaleDateString()}
                                </TableCell>
                                <TableCell className="py-2.5 text-right">
                                  <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums', h.totalReturn >= 0 ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300' : 'bg-red-50 text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-300')}>
                                    {h.totalReturn >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                                    {formatPercent(h.totalReturn)}
                                  </span>
                                </TableCell>
                                <TableCell className="py-2.5 text-right hidden md:table-cell">
                                  <Badge variant="outline" className="rounded-full text-[11px]">{h.status}</Badge>
                                </TableCell>
                                <TableCell className="py-2.5 text-right">
                                  <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => handleHistorySelect(h.id)} disabled={h.id.startsWith('synthetic')}>
                                    Load
                                  </Button>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="trades" className="mt-4">
                <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300">
                          <BarChart3 className="h-3.5 w-3.5" />
                        </div>
                        <div>
                          <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Trade Ledger</CardTitle>
                          <CardDescription className="text-xs">Individual fills • {result.trades.length} trades • sorted by entry date (newest first)</CardDescription>
                        </div>
                      </div>
                      <Badge variant="outline" className="rounded-full font-mono text-xs">
                        PF {result.profitFactor.toFixed(2)} • WR {result.winRate.toFixed(1)}%
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {result.trades.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-12 text-center rounded-lg border border-dashed border-slate-200 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-800/20">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                          <SearchX className="h-5 w-5 text-slate-400" />
                        </div>
                        <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-300">No trades in this window</p>
                        <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">Strategy did not emit entry signals with sufficient confidence. Try a longer period, different horizon, or alternate strategy (e.g., Trend Following + ML tends to trade more frequently).</p>
                      </div>
                    ) : (
                      <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
                        <Table>
                          <TableHeader className="bg-slate-50/70 dark:bg-slate-800/50">
                            <TableRow className="hover:bg-transparent">
                              <TableHead className="h-8 text-[11px] font-semibold uppercase tracking-wide">Date</TableHead>
                              <TableHead className="h-8 text-[11px] font-semibold uppercase tracking-wide">Side</TableHead>
                              <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide">Entry</TableHead>
                              <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide">Exit</TableHead>
                              <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide hidden sm:table-cell">Shares</TableHead>
                              <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide">PnL</TableHead>
                              <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide">Return</TableHead>
                              <TableHead className="h-8 text-center text-[11px] font-semibold uppercase tracking-wide">Result</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {result.trades.map((t) => (
                              <TableRow key={t.id} className="hover:bg-slate-50/70 dark:hover:bg-slate-800/50">
                                <TableCell className="py-2.5">
                                  <div className="flex flex-col">
                                    <span className="font-mono text-xs font-medium tabular-nums">{new Date(t.entryDate).toLocaleDateString()}</span>
                                    <span className="text-[11px] text-muted-foreground">→ {t.exitDate ? new Date(t.exitDate).toLocaleDateString() : '—'}</span>
                                  </div>
                                </TableCell>
                                <TableCell className="py-2.5">
                                  <Badge
                                    variant="outline"
                                    className={cn(
                                      'rounded-full text-[11px] font-semibold capitalize',
                                      t.side === 'long' ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300' : 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300'
                                    )}
                                  >
                                    {t.side}
                                  </Badge>
                                </TableCell>
                                <TableCell className="py-2.5 text-right font-mono text-xs tabular-nums">${t.entryPrice.toFixed(2)}</TableCell>
                                <TableCell className="py-2.5 text-right font-mono text-xs tabular-nums">{t.exitPrice !== null ? `$${t.exitPrice.toFixed(2)}` : '—'}</TableCell>
                                <TableCell className="py-2.5 text-right font-mono text-xs tabular-nums hidden sm:table-cell">{t.shares}</TableCell>
                                <TableCell className={cn('py-2.5 text-right font-mono text-xs font-semibold tabular-nums', (t.pnl ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                                  {t.pnl !== null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '—'}
                                </TableCell>
                                <TableCell className={cn('py-2.5 text-right font-mono text-xs font-semibold tabular-nums', (t.returnPct ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                                  {t.returnPct !== null ? formatPercent(t.returnPct) : '—'}
                                </TableCell>
                                <TableCell className="py-2.5 text-center">
                                  {t.isWinner === null ? (
                                    <Badge variant="outline" className="rounded-full text-[11px]">Pending</Badge>
                                  ) : t.isWinner ? (
                                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300">
                                      <TrendingUp className="h-3 w-3" /> Win
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-300">
                                      <TrendingDown className="h-3 w-3" /> Loss
                                    </span>
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                    <Separator className="my-4" />
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
                      <span>
                        Showing {result.trades.length} fills • Symbols are {result.symbol} only (single-asset backtest). Multi-asset baskets are on the roadmap.
                      </span>
                      <span className="font-mono tabular-nums">Gross Profit ${result.trades.filter((t) => (t.pnl ?? 0) > 0).reduce((a, b) => a + (b.pnl ?? 0), 0).toFixed(2)} • Gross Loss ${Math.abs(result.trades.filter((t) => (t.pnl ?? 0) <= 0).reduce((a, b) => a + (b.pnl ?? 0), 0)).toFixed(2)}</span>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="history" className="mt-4">
                <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                  <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                      <History className="h-4 w-4 text-slate-700 dark:text-slate-300" />
                      <CardTitle className="text-sm">Backtest History</CardTitle>
                    </div>
                    <CardDescription className="text-xs">Persistent runs via <code className="font-mono text-[11px] bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">api.getBacktests</code> and <code className="font-mono text-[11px] bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">api.getBacktest(id)</code></CardDescription>
                  </CardHeader>
                  <CardContent>
                    {historyLoading ? (
                      <div className="space-y-2">
                        {Array.from({ length: 4 }).map((_, i) => (
                          <Skeleton key={i} className="h-14 w-full" />
                        ))}
                      </div>
                    ) : historyError ? (
                      <Alert>
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle className="text-sm">Failed to load history</AlertTitle>
                        <AlertDescription className="text-xs flex items-center gap-2">
                          <span>{historyError}</span>
                          <Button size="sm" variant="outline" className="h-7" onClick={fetchHistory}>Retry</Button>
                        </AlertDescription>
                      </Alert>
                    ) : history.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-8 text-center dark:border-slate-800 dark:bg-slate-800/30">
                        <FlaskConical className="h-8 w-8 mx-auto text-slate-400" />
                        <p className="mt-3 text-sm font-medium">No history yet</p>
                        <p className="mt-1 text-xs text-muted-foreground">Completed backtests will be listed here with one-click reload via <code className="font-mono text-[11px]">api.getBacktest</code>.</p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {history.map((h) => (
                          <div key={h.id} className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-mono text-sm font-semibold tracking-wide">{h.symbol}</span>
                                <span className="text-xs text-muted-foreground">• {h.strategy} • {h.config.horizon.toUpperCase()}</span>
                                <Badge variant="outline" className="rounded-full text-[11px]">{h.status}</Badge>
                                {h.isSample && <Badge variant="secondary" className="rounded-full text-[11px] bg-amber-100 text-amber-700 dark:bg-amber-900/30">Sample</Badge>}
                              </div>
                              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                <span className="font-mono tabular-nums">{new Date(h.config.startDate).toLocaleDateString()} → {new Date(h.config.endDate).toLocaleDateString()}</span>
                                <span className="hidden sm:inline">•</span>
                                <span>${h.config.initialCapital.toLocaleString()} → Total {formatPercent(h.totalReturn)} • DD {h.maxDrawdown.toFixed(1)}% • WR {h.winRate.toFixed(0)}%</span>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <div className={cn('rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums ring-1', h.totalReturn >= 0 ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900' : 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/30 dark:text-red-300')}>
                                {formatPercent(h.totalReturn)}
                              </div>
                              <Button size="sm" variant="outline" onClick={() => handleHistorySelect(h.id)} disabled={h.id.startsWith('synthetic')} className="h-8">
                                Load
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        )}

        {/* Look-ahead bias disclaimer - always visible */}
        <Card className="overflow-hidden border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20">
          <CardContent className="flex gap-3 p-4">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
              <ShieldAlert className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200 flex items-center gap-2">
                Look-ahead bias prevention • Walk-forward • No peeking
                <Badge variant="outline" className="rounded-full border-amber-200 bg-white text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200 text-[11px]">Research-grade</Badge>
              </h3>
              <p className="text-xs leading-5 text-amber-800/80 dark:text-amber-100/70">
                Backtests are executed with <span className="font-semibold text-amber-900 dark:text-amber-100">strictly point-in-time data</span>: at any simulated date, the model sees only information available <em>before</em> that timestamp. We use walk-forward (expanding) windows — no future bars, no survivorship bias, no repainting. All predictions are evaluated <span className="font-medium">out-of-sample</span> against realized returns; in-sample fit is never reported as performance. Costs, slippage, and market impact can be included and are disclosed per run. Results are simulations for research and education only — they do <span className="font-semibold">not</span> guarantee future returns and do not constitute investment advice.
              </p>
              <div className="flex flex-wrap gap-2 pt-1 text-[11px]">
                <span className="rounded-full bg-white px-2.5 py-1 font-medium text-amber-800 ring-1 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-900">Point-in-time features</span>
                <span className="rounded-full bg-white px-2.5 py-1 font-medium text-amber-800 ring-1 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-900">No look-ahead</span>
                <span className="rounded-full bg-white px-2.5 py-1 font-medium text-amber-800 ring-1 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-900">Out-of-sample only</span>
                <span className="rounded-full bg-white px-2.5 py-1 font-medium text-amber-800 ring-1 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-900">Reproducible • Logged</span>
              </div>
              <p className="text-[11px] leading-4 text-amber-700/60 dark:text-amber-200/50">
                Methodology mirrors production inference: features → model → calibration → signal → fill at next-bar close. See <span className="font-mono">services/backtesting/backtest_service.py</span> for the reference engine (stop 5%, take 10%, long/short on high-confidence &gt;60% predictions). There is no synthetic fallback: if live data is unavailable the page shows UNAVAILABLE.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Footer meta */}
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          <p>
            <span className="font-medium text-slate-900 dark:text-white">API contract:</span> This page uses{' '}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">api.createBacktest</code>,{' '}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">api.runBacktest(id)</code>,{' '}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">api.getBacktest(id)</code> and{' '}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">api.getBacktests</code> from{' '}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">lib/api/client</code>. All charting uses{' '}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">recharts</code> with responsive containers and accessible tooltips. UI primitives: shadcn <code className="font-mono text-[11px]">Card</code>, <code className="font-mono text-[11px]">StatCard</code>, <code className="font-mono text-[11px]">Table</code>, <code className="font-mono text-[11px]">Select</code>, <code className="font-mono text-[11px]">Input</code>, <code className="font-mono text-[11px]">Button</code>, <code className="font-mono text-[11px]">Skeleton</code>, <code className="font-mono text-[11px]">Tabs</code>.
          </p>
        </div>
      </div>
    </div>
  );
}
