'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Separator } from '@/components/ui/separator';
import { api } from '@/lib/api/client';
import { cn, formatPrice, formatPercent } from '@/lib/utils';
import {
  Search,
  SlidersHorizontal,
  X,
  ChevronUp,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  Minus,
  Bookmark,
  Trash2,
  Filter,
  Sparkles,
  AlertTriangle,
  SearchX,
  RefreshCw,
  Save,
  Star,
  BarChart3,
  Info,
  ArrowUpDown,
  Clock,
  Shield,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortDir = 'asc' | 'desc';
type SortKey =
  | 'symbol'
  | 'name'
  | 'exchange'
  | 'price'
  | 'changePercent'
  | 'sector'
  | 'rsi'
  | 'volatility'
  | 'direction'
  | 'probability'
  | 'expectedReturn'
  | 'confidence';

type NormalizedRow = {
  id: string;
  symbol: string;
  name: string;
  exchange: string;
  price: number | null;
  changePercent: number | null;
  sector: string | null;
  rsi: number | null;
  volatility: number | null;
  prediction: {
    direction: 'up' | 'down' | 'neutral';
    probability: number; // 0-100
    expectedReturn: number; // percent
    confidence: number; // 0-100
  } | null;
};

type FiltersState = {
  market: string; // "all" or code
  exchange: string;
  sector: string;
  priceMin: string;
  priceMax: string;
  performance: string; // all | gainers | losers | strong_gainers | strong_losers | flat
  momentum: string; // all | up | down | neutral
  rsiMin: number;
  rsiMax: number;
  volatility: string; // all | low | medium | high
  probabilityMin: number; // 0-100
  expectedReturnMin: string; // string number percent
  confidenceMin: number; // 0-100
};

// ---------------------------------------------------------------------------
// Constants & Mocks
// ---------------------------------------------------------------------------

const DEFAULT_FILTERS: FiltersState = {
  market: 'all',
  exchange: 'all',
  sector: 'all',
  priceMin: '',
  priceMax: '',
  performance: 'all',
  momentum: 'all',
  rsiMin: 0,
  rsiMax: 100,
  volatility: 'all',
  probabilityMin: 0,
  expectedReturnMin: '',
  confidenceMin: 0,
};

const MARKET_OPTIONS = [
  { value: 'all', label: 'All Markets' },
  { value: 'IN', label: 'India' },
  { value: 'US', label: 'United States' },
  { value: 'EU', label: 'Europe' },
  { value: 'INDA', label: 'India (NSE/BSE)' },
  { value: 'NASDAQ', label: 'US (NASDAQ/NYSE)' },
];

const EXCHANGE_OPTIONS_FALLBACK = [
  { value: 'all', label: 'All Exchanges' },
  { value: 'NSE', label: 'NSE' },
  { value: 'BSE', label: 'BSE' },
  { value: 'NASDAQ', label: 'NASDAQ' },
  { value: 'NYSE', label: 'NYSE' },
  { value: 'XETRA', label: 'XETRA' },
  { value: 'LSE', label: 'LSE' },
  { value: 'EPA', label: 'Euronext' },
];

const SECTOR_FALLBACK = [
  'Technology',
  'Financial Services',
  'Healthcare',
  'Energy',
  'Consumer Discretionary',
  'Industrials',
  'IT',
  'Pharma',
  'FMCG',
  'Automobiles',
  'Banks',
  'Materials',
  'Utilities',
  'Communication Services',
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseNum(v: any, fallback = 0): number {
  if (v == null) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function toPercent(n: number): number {
  // if 0-1 fraction, convert to percent; otherwise already percent
  if (Math.abs(n) <= 1 && Math.abs(n) > 0) {
    const p = n * 100;
    if (Math.abs(p) < 50) return p;
  }
  return n;
}

function confidenceLabel(v: number) {
  if (v >= 70) return 'High';
  if (v >= 50) return 'Med';
  return 'Low';
}

function rsiTone(v: number | null) {
  if (v == null) return 'text-slate-400';
  if (v > 70) return 'text-red-600 dark:text-red-400';
  if (v < 30) return 'text-emerald-600 dark:text-emerald-400';
  return 'text-slate-700 dark:text-slate-300';
}

function volatilityTone(v: number | null) {
  if (v == null) return 'text-slate-400';
  if (v > 30) return 'text-red-600 dark:text-red-400';
  if (v > 20) return 'text-amber-600 dark:text-amber-400';
  return 'text-emerald-600 dark:text-emerald-400';
}

function directionBadge(dir: 'up' | 'down' | 'neutral' | null | undefined) {
  if (dir === 'up') return 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900';
  if (dir === 'down') return 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/30 dark:text-red-300 dark:ring-red-900';
  if (dir === 'neutral') return 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:ring-amber-900';
  return 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-300';
}

function changeBg(v: number | null) {
  if (v != null && v > 0) return 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300';
  if (v != null && v < 0) return 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/30 dark:text-red-300';
  return 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-300';
}

function normalizeRow(raw: any, idx: number): NormalizedRow | null {
  try {
    const symbol: string = (raw.symbol ?? raw.ticker ?? raw.code ?? '').toString().toUpperCase() || `UNK${idx}`;
    const name: string = (raw.name ?? raw.company_name ?? raw.display_name ?? symbol).toString();
    const exchange: string = (raw.exchange ?? raw.exchange_code ?? raw.exchangeCode ?? '').toString().toUpperCase() || 'N/A';
    const priceRaw = raw.price ?? raw.close ?? raw.last_price ?? raw.lastPrice ?? null;
    const price = priceRaw == null ? null : parseNum(priceRaw, NaN);
    const changePercentRaw = raw.change_percent ?? raw.changePercent ?? raw.change_pct ?? null;
    const changePercent = changePercentRaw == null ? null : toPercent(parseNum(changePercentRaw, NaN));
    const sector: string | null = (raw.sector ?? raw.industry ?? null) ? String(raw.sector ?? raw.industry) : null;
    const rsiRaw = raw.rsi ?? raw.rsi_14 ?? raw.rsi14 ?? raw.features_snapshot?.rsi_14 ?? raw.features_snapshot?.rsi ?? null;
    const rsi = rsiRaw != null ? parseNum(rsiRaw, 0) : null;
    const volRaw = raw.volatility ?? raw.volatility_20 ?? raw.vol_20 ?? raw.features_snapshot?.volatility_20 ?? raw.features_snapshot?.volatility ?? null;
    const volatility = volRaw != null ? parseNum(volRaw, 0) : null;

    // prediction
    const predRaw: any = raw.prediction ?? raw.pred ?? raw.latest_prediction ?? null;
    let pred: NormalizedRow['prediction'] = null;
    if (predRaw) {
      // direction
      const dirRaw = (predRaw.predicted_direction ?? predRaw.direction ?? predRaw.signal ?? 'neutral').toString().toLowerCase();
      const direction: 'up' | 'down' | 'neutral' = dirRaw === 'up' || dirRaw === 'bullish' ? 'up' : dirRaw === 'down' || dirRaw === 'bearish' ? 'down' : 'neutral';
      // probability: up_probability 0-1 or 0-100
      let probRaw = predRaw.up_probability ?? predRaw.upProbability ?? predRaw.probability ?? predRaw.probabilities?.up ?? predRaw.p_up ?? 0;
      let prob = parseNum(probRaw, 0);
      if (prob <= 1 && prob > 0) prob = prob * 100;
      prob = Math.round(prob);
      // expected return
      let erRaw = predRaw.expected_return ?? predRaw.expectedReturn ?? predRaw.expected_return_pct ?? 0;
      let er = parseNum(erRaw, 0);
      er = toPercent(er);
      // confidence
      let conf = parseNum(predRaw.confidence ?? predRaw.confidence_score ?? 0, 0);
      if (conf <= 1 && conf > 0) conf = Math.round(conf * 100);
      else conf = Math.round(conf);
      pred = { direction, probability: Math.max(0, Math.min(100, prob)), expectedReturn: er, confidence: Math.max(0, Math.min(100, conf)) };
    } else {
      // try flat fields on raw itself (some backends flatten)
      const hasPred = raw.up_probability != null || raw.predicted_direction != null || raw.confidence != null;
      if (hasPred) {
        const dirRaw = (raw.predicted_direction ?? raw.direction ?? 'neutral').toString().toLowerCase();
        const direction: 'up' | 'down' | 'neutral' = dirRaw === 'up' ? 'up' : dirRaw === 'down' ? 'down' : 'neutral';
        let prob = parseNum(raw.up_probability ?? raw.probability ?? 0, 0);
        if (prob <= 1 && prob > 0) prob = prob * 100;
        let er = toPercent(parseNum(raw.expected_return ?? 0, 0));
        let conf = parseNum(raw.confidence ?? 0, 0);
        if (conf <= 1 && conf > 0) conf = Math.round(conf * 100);
        pred = { direction, probability: Math.round(prob), expectedReturn: er, confidence: conf };
      }
    }

    return {
      id: `${symbol}-${exchange}-${idx}`,
      symbol,
      name,
      exchange,
      price,
      changePercent,
      sector,
      rsi: rsi != null && !Number.isNaN(rsi) ? Math.round(rsi * 10) / 10 : null,
      volatility: volatility != null && !Number.isNaN(volatility) ? Math.round(volatility * 10) / 10 : null,
      prediction: pred,
    };
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ScreenerPage() {
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [naturalQuery, setNaturalQuery] = useState('');
  const [sectorOptions, setSectorOptions] = useState<string[]>(SECTOR_FALLBACK);
  const [exchangeOptions, setExchangeOptions] = useState<{ value: string; label: string }[]>(EXCHANGE_OPTIONS_FALLBACK);
  const [rows, setRows] = useState<NormalizedRow[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [isLoading, setIsLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('symbol');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [savedScreenName, setSavedScreenName] = useState('');
  const [savedScreens, setSavedScreens] = useState<{ id: string; name: string; filters: FiltersState }[]>(() => [
    { id: '1', name: 'Bullish India High Confidence', filters: { ...DEFAULT_FILTERS, market: 'IN', momentum: 'up', confidenceMin: 70 } },
    { id: '2', name: 'US Tech Momentum', filters: { ...DEFAULT_FILTERS, market: 'US', sector: 'Technology', momentum: 'up', rsiMin: 50, rsiMax: 75 } },
    { id: '3', name: 'Oversold Bounce (RSI <35)', filters: { ...DEFAULT_FILTERS, rsiMin: 0, rsiMax: 35, volatility: 'high', probabilityMin: 60 } },
  ]);
  const [selectedSavedId, setSelectedSavedId] = useState<string>('');

  // derived
  const activeChips = useMemo(() => {
    const chips: { key: string; label: string; onRemove: () => void }[] = [];
    if (filters.market !== 'all') chips.push({ key: 'market', label: `Market: ${filters.market}`, onRemove: () => setFilters((p) => ({ ...p, market: 'all' })) });
    if (filters.exchange !== 'all') chips.push({ key: 'exchange', label: `Exchange: ${filters.exchange}`, onRemove: () => setFilters((p) => ({ ...p, exchange: 'all' })) });
    if (filters.sector !== 'all') chips.push({ key: 'sector', label: `Sector: ${filters.sector}`, onRemove: () => setFilters((p) => ({ ...p, sector: 'all' })) });
    if (filters.priceMin) chips.push({ key: 'priceMin', label: `Price ≥ ${filters.priceMin}`, onRemove: () => setFilters((p) => ({ ...p, priceMin: '' })) });
    if (filters.priceMax) chips.push({ key: 'priceMax', label: `Price ≤ ${filters.priceMax}`, onRemove: () => setFilters((p) => ({ ...p, priceMax: '' })) });
    if (filters.performance !== 'all') chips.push({ key: 'performance', label: `Perf: ${filters.performance}`, onRemove: () => setFilters((p) => ({ ...p, performance: 'all' })) });
    if (filters.momentum !== 'all') chips.push({ key: 'momentum', label: `Momentum: ${filters.momentum}`, onRemove: () => setFilters((p) => ({ ...p, momentum: 'all' })) });
    if (filters.rsiMin > 0 || filters.rsiMax < 100) chips.push({ key: 'rsi', label: `RSI ${filters.rsiMin}-${filters.rsiMax}`, onRemove: () => setFilters((p) => ({ ...p, rsiMin: 0, rsiMax: 100 })) });
    if (filters.volatility !== 'all') chips.push({ key: 'volatility', label: `Volatility: ${filters.volatility}`, onRemove: () => setFilters((p) => ({ ...p, volatility: 'all' })) });
    if (filters.probabilityMin > 0) chips.push({ key: 'prob', label: `Prob ≥ ${filters.probabilityMin}%`, onRemove: () => setFilters((p) => ({ ...p, probabilityMin: 0 })) });
    if (filters.expectedReturnMin) chips.push({ key: 'er', label: `Exp Ret ≥ ${filters.expectedReturnMin}%`, onRemove: () => setFilters((p) => ({ ...p, expectedReturnMin: '' })) });
    if (filters.confidenceMin > 0) chips.push({ key: 'conf', label: `Confidence ≥ ${filters.confidenceMin}`, onRemove: () => setFilters((p) => ({ ...p, confidenceMin: 0 })) });
    return chips;
  }, [filters]);

  const hasActiveFilters = activeChips.length > 0;

  // fetch sectors / exchanges
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sectors = await api.getSectors();
        if (!cancelled && Array.isArray(sectors) && sectors.length > 0) {
          // sectors may be string[] or objects
          const norm = sectors.map((s: any) => (typeof s === 'string' ? s : s.name ?? s.sector ?? String(s))).filter(Boolean);
          if (norm.length) setSectorOptions(norm);
        }
      } catch {
        // keep fallback
      }
      try {
        // api.getExchanges is overloaded; for screener it expects optional market param via query
        // try calling with market if selected, else without
        const marketParam = filters.market !== 'all' ? filters.market : undefined;
        // use any to bypass TS overload conflict
        const exchanges: any = await (api as any).getExchanges(marketParam);
        if (!cancelled && Array.isArray(exchanges) && exchanges.length > 0) {
          const norm = exchanges
            .map((e: any) => {
              if (typeof e === 'string') return { value: e.toUpperCase(), label: e.toUpperCase() };
              const code = (e.code ?? e.exchange ?? e.value ?? '').toString().toUpperCase();
              const name = (e.name ?? e.label ?? code).toString();
              if (!code) return null;
              return { value: code, label: code === name ? code : `${code} — ${name}` };
            })
            .filter(Boolean) as { value: string; label: string }[];
          if (norm.length) {
            setExchangeOptions([{ value: 'all', label: 'All Exchanges' }, ...norm]);
          }
        }
      } catch {
        // keep fallback, but also try direct fetch as backup
        try {
          const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
          const url = filters.market !== 'all' ? `${base}/screener/filters/exchanges?market=${encodeURIComponent(filters.market)}` : `${base}/screener/filters/exchanges`;
          const res = await fetch(url);
          if (res.ok) {
            const data = await res.json();
            if (Array.isArray(data) && data.length) {
              const norm = data
                .map((e: any) => {
                  const code = (e.code ?? e).toString().toUpperCase();
                  return { value: code, label: code };
                })
                .filter(Boolean);
              if (!cancelled && norm.length) setExchangeOptions([{ value: 'all', label: 'All Exchanges' }, ...norm]);
            }
          }
        } catch {
          /* ignore */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // only on mount and when market changes for exchanges
  }, [filters.market]);

  const buildApiFilters = useCallback((f: FiltersState) => {
    const out: any = {};
    if (f.market !== 'all' && f.market) out.market = [f.market.toUpperCase()];
    if (f.exchange !== 'all' && f.exchange) out.exchange = [f.exchange.toUpperCase()];
    if (f.sector !== 'all' && f.sector) out.sector = [f.sector];
    if (f.priceMin) {
      const v = parseNum(f.priceMin, NaN);
      if (Number.isFinite(v)) out.price_min = v;
    }
    if (f.priceMax) {
      const v = parseNum(f.priceMax, NaN);
      if (Number.isFinite(v)) out.price_max = v;
    }
    // performance -> performance_min/max
    if (f.performance !== 'all') {
      switch (f.performance) {
        case 'gainers':
          out.performance_min = 0;
          break;
        case 'losers':
          out.performance_max = 0;
          break;
        case 'strong_gainers':
          out.performance_min = 2;
          break;
        case 'strong_losers':
          out.performance_max = -2;
          break;
        case 'flat':
          out.performance_min = -1;
          out.performance_max = 1;
          break;
      }
    }
    // RSI
    if (f.rsiMin > 0) out.rsi_min = f.rsiMin;
    if (f.rsiMax < 100) out.rsi_max = f.rsiMax;
    // volatility
    if (f.volatility !== 'all') {
      switch (f.volatility) {
        case 'low':
          out.volatility_max = 15;
          break;
        case 'medium':
          out.volatility_min = 15;
          out.volatility_max = 30;
          break;
        case 'high':
          out.volatility_min = 30;
          break;
      }
    }
    if (f.probabilityMin > 0) out.prediction_probability_min = f.probabilityMin / 100;
    if (f.expectedReturnMin) {
      const v = parseNum(f.expectedReturnMin, NaN);
      if (Number.isFinite(v)) out.expected_return_min = v / 100;
    }
    if (f.confidenceMin > 0) out.confidence_min = f.confidenceMin;
    if (f.momentum !== 'all') out.prediction_direction = f.momentum; // up | down | neutral
    // limit handled via pagination; but also include as fallback
    out.limit = pageSize;
    return out;
  }, []);

  const fetchScreener = useCallback(
    async (pageToFetch = 1, filtersOverride?: FiltersState) => {
      const f = filtersOverride ?? filters;
      setError(null);
      if (rows.length === 0 && !hasSearched) setIsLoading(true);
      else setIsFetching(true);
      try {
        const apiFilters = buildApiFilters(f);
        // primary via client
        let data: any = null;
        let rawItems: any[] = [];
        let totalCount = 0;
        try {
          data = await api.screenStocks(apiFilters, pageToFetch, pageSize);
        } catch (e: any) {
          // fallback direct fetch with query pagination
          try {
            const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
            const qs = new URLSearchParams({ page: String(pageToFetch), page_size: String(pageSize) });
            const res = await fetch(`${base}/screener?${qs.toString()}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(apiFilters),
            });
            if (res.ok) data = await res.json();
            else throw new Error(`Screener failed ${res.status}`);
          } catch (inner: any) {
            throw e; // rethrow original
          }
        }

        // normalize response shapes
        if (data) {
          if (Array.isArray(data)) {
            rawItems = data;
            totalCount = data.length;
          } else if (Array.isArray(data.items)) {
            rawItems = data.items;
            totalCount = parseNum(data.total, rawItems.length);
          } else if (Array.isArray(data.results)) {
            rawItems = data.results;
            totalCount = parseNum(data.total, rawItems.length);
          } else if (Array.isArray(data.data)) {
            rawItems = data.data;
            totalCount = parseNum(data.total, rawItems.length);
          } else if (data.items && typeof data.items === 'object') {
            // single page object
            rawItems = [];
            totalCount = 0;
          } else {
            // if paginated response wrapped differently
            rawItems = data.items ?? [];
            totalCount = data.total ?? rawItems.length;
          }
        }

        // Do NOT fallback to mock financial data — real data only.
        let normalized: NormalizedRow[] = rawItems.map((r: any, idx: number) => normalizeRow(r, idx)).filter(Boolean) as NormalizedRow[];

        // If backend reachable and empty, show empty (UNAVAILABLE), not mock.
        // No silent mock synthesis.
        const backendReachable = data != null;
        if (backendReachable && normalized.length === 0 && rawItems.length === 0) {
          // genuine empty
          setRows([]);
          setTotal(0);
        } else if (normalized.length === 0 && rawItems.length > 0) {
          // parsing failed — show error, not mock
          setError('Screener response parsing failed — no valid rows. Check backend schema.');
          setRows([]);
          setTotal(0);
        } else if (normalized.length > 0) {
          // Real backend data — apply light local filtering for consistency but do not synthesize.
          setRows(normalized);
          setTotal(totalCount || normalized.length);
        } else {
          // No data and not reachable — UNAVAILABLE
          setRows([]);
          setTotal(0);
          setError((prev) => prev || 'Screener data unavailable — live feed returned no results.');
        }

        setHasSearched(true);
        setPage(pageToFetch);
      } catch (e: any) {
        const msg = e?.message || 'Failed to load screener data';
        setError(msg + ' — UNAVAILABLE: live screener feed not reachable. No mock data shown.');
        // Do NOT fallback to mock financial data
        setRows([]);
        setTotal(0);
        setHasSearched(true);
      } finally {
        setIsLoading(false);
        setIsFetching(false);
      }
    },
    [filters, buildApiFilters, rows.length, hasSearched, hasActiveFilters]
  );

  // initial load
  useEffect(() => {
    fetchScreener(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = useCallback(() => {
    fetchScreener(1);
  }, [fetchScreener]);

  const handleClear = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
    setNaturalQuery('');
    setPage(1);
    // fetch with defaults after state update via timeout
    setTimeout(() => fetchScreener(1, DEFAULT_FILTERS), 0);
  }, [fetchScreener]);

  const handleSavedSelect = useCallback(
    (id: string | null) => {
      if (!id) return;
      setSelectedSavedId(id);
      const found = savedScreens.find((s) => s.id === id);
      if (found) {
        setFilters(found.filters);
        setPage(1);
        setTimeout(() => fetchScreener(1, found.filters), 0);
      }
    },
    [savedScreens, fetchScreener]
  );

  const handleSaveScreen = useCallback(() => {
    if (!savedScreenName.trim()) return;
    const newScreen = { id: Date.now().toString(), name: savedScreenName.trim(), filters: { ...filters } };
    setSavedScreens((prev) => [...prev, newScreen]);
    setSavedScreenName('');
    setSelectedSavedId(newScreen.id);
  }, [savedScreenName, filters]);

  const toggleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortKey(key);
        setSortDir('asc');
      }
    },
    [sortKey]
  );

  const sortedRows = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      let av: any, bv: any;
      switch (sortKey) {
        case 'symbol':
          av = a.symbol;
          bv = b.symbol;
          break;
        case 'name':
          av = a.name;
          bv = b.name;
          break;
        case 'exchange':
          av = a.exchange;
          bv = b.exchange;
          break;
        case 'price':
          av = a.price ?? Number.NEGATIVE_INFINITY;
          bv = b.price ?? Number.NEGATIVE_INFINITY;
          break;
        case 'changePercent':
          av = a.changePercent ?? Number.NEGATIVE_INFINITY;
          bv = b.changePercent ?? Number.NEGATIVE_INFINITY;
          break;
        case 'sector':
          av = a.sector ?? '';
          bv = b.sector ?? '';
          break;
        case 'rsi':
          av = a.rsi ?? -1;
          bv = b.rsi ?? -1;
          break;
        case 'volatility':
          av = a.volatility ?? -1;
          bv = b.volatility ?? -1;
          break;
        case 'direction':
          av = a.prediction?.direction ?? '';
          bv = b.prediction?.direction ?? '';
          break;
        case 'probability':
          av = a.prediction?.probability ?? -1;
          bv = b.prediction?.probability ?? -1;
          break;
        case 'expectedReturn':
          av = a.prediction?.expectedReturn ?? -999;
          bv = b.prediction?.expectedReturn ?? -999;
          break;
        case 'confidence':
          av = a.prediction?.confidence ?? -1;
          bv = b.prediction?.confidence ?? -1;
          break;
        default:
          av = a.symbol;
          bv = b.symbol;
      }
      if (typeof av === 'string' && typeof bv === 'string') {
        const cmp = av.localeCompare(bv);
        return sortDir === 'asc' ? cmp : -cmp;
      }
      const cmp = (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const SortIcon = ({ active }: { active: boolean }) => {
    if (!active) return <ArrowUpDown className="h-3 w-3 opacity-40" />;
    return sortDir === 'asc' ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />;
  };

  return (
    <div className="min-h-screen bg-slate-50/60 dark:bg-slate-950">
      <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 space-y-5">
        {/* Header */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm">
                <BarChart3 className="h-5 w-5" />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Screener</h1>
              <Badge variant="outline" className="rounded-full border-slate-200 bg-white font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                <Filter className="mr-1 h-3 w-3" />
                Professional
              </Badge>
              <Badge variant="secondary" className="rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs">
                {total} results
              </Badge>
              {isFetching && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 ring-1 ring-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:ring-blue-900">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  Updating
                </span>
              )}
            </div>
            <p className="max-w-[760px] text-sm leading-6 text-slate-600 dark:text-slate-400">
              Filter across markets, sectors, price, technicals and StockAI predictions. Combine fundamental screens with probabilistic forecasts — calibrated probabilities, expected return and confidence — in one workspace.
            </p>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                <Shield className="h-3 w-3" />
                Forecasts are probabilistic, not guarantees
              </span>
              <span className="inline-flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                <Clock className="h-3 w-3" />
                Delay disclosure per exchange
              </span>
              <Link href="/research" className="text-primary hover:underline underline-offset-4">
                Methodology →
              </Link>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 self-start lg:self-auto">
            <Button variant="outline" onClick={handleClear} className="bg-white dark:bg-slate-900">
              <Trash2 className="h-4 w-4" />
              Clear filters
            </Button>
            <Button onClick={handleSearch} disabled={isFetching} className="shadow-sm">
              <Search className="h-4 w-4" />
              {isFetching ? 'Scanning…' : 'Scan now'}
            </Button>
          </div>
        </div>

        {/* Natural language search — visual placeholder, not LLM */}
        <Card className="border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-600 text-white">
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <CardTitle className="text-sm font-semibold tracking-tight">Natural language search</CardTitle>
                <Badge variant="outline" className="rounded-full border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300 text-[11px] font-medium">
                  <Info className="mr-1 h-3 w-3" />
                  Visual preview — not LLM
                </Badge>
              </div>
              <span className="text-xs text-muted-foreground hidden sm:inline">Type an idea, then use filters below for precise control</span>
            </div>
            <CardDescription className="text-xs leading-5">
              Describe what you want in plain English. Parsing is not yet connected — this input is a visual placeholder for the upcoming AI screener. Use the structured filters below to run a live scan.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={naturalQuery}
                  onChange={(e) => setNaturalQuery(e.target.value)}
                  placeholder='Find Indian stocks with bullish predictions and confidence above 70.'
                  className="h-10 pl-9 pr-3 bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-800 focus-visible:ring-violet-500/30"
                />
              </div>
              <Button variant="secondary" disabled className="h-10 shrink-0 bg-slate-900 text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100" title="AI parsing coming soon">
                <Sparkles className="h-4 w-4" />
                Parse with AI — coming soon
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground mr-1">Try:</span>
              {[
                'Find Indian stocks with bullish predictions and confidence above 70.',
                'US tech stocks with RSI below 35 and high volatility',
                'Show NSE large-caps with expected return > 2% and probability > 65%',
              ].map((ex) => (
                <button
                  key={ex}
                  onClick={() => setNaturalQuery(ex)}
                  className="inline-flex max-w-full items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs leading-4 text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 truncate"
                  title={ex}
                >
                  <span className="truncate">&ldquo;{ex}&rdquo;</span>
                </button>
              ))}
              <span className="text-[11px] text-slate-400 dark:text-slate-500 ml-1">Not executed — use Scan now below</span>
            </div>
          </CardContent>
        </Card>

        {/* Saved screens + Filter chips */}
        <div className="grid gap-4 lg:grid-cols-12">
          <Card className="lg:col-span-4 border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300">
                  <Bookmark className="h-3.5 w-3.5" />
                </div>
                <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Saved screens</CardTitle>
                <Badge variant="outline" className="ml-auto rounded-full text-[11px] font-medium">
                  Placeholder
                </Badge>
              </div>
              <CardDescription className="text-xs leading-5">Save and reuse filter combinations. Storage is local-only in this preview; backend sync is on the roadmap.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-2">
                <Label className="text-xs font-medium">Load a saved screen</Label>
                <Select value={selectedSavedId} onValueChange={handleSavedSelect}>
                  <SelectTrigger className="h-9 bg-white dark:bg-slate-900">
                    <SelectValue placeholder="Select a screen…" />
                  </SelectTrigger>
                  <SelectContent>
                    {savedScreens.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        <span className="inline-flex items-center gap-1.5">
                          <Star className="h-3 w-3 text-amber-500" />
                          {s.name}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Choosing a screen replaces current filters and re-scans.</p>
              </div>

              <Separator />

              <div className="space-y-2">
                <Label className="text-xs font-medium">Save current screen</Label>
                <div className="flex gap-2">
                  <Input placeholder="e.g., High-conviction NSE longs" value={savedScreenName} onChange={(e) => setSavedScreenName(e.target.value)} className="h-9 flex-1" maxLength={48} />
                  <Button size="sm" onClick={handleSaveScreen} disabled={!savedScreenName.trim()} className="h-9 shrink-0">
                    <Save className="h-4 w-4" />
                    Save
                  </Button>
                </div>
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/70 px-3 py-2 dark:border-slate-800 dark:bg-slate-900/50">
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-300">How saving will work</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">Saved screens will persist to your account (and be shareable via URL) once backend persistence is enabled. For now they live in this tab&apos;s memory.</p>
                </div>
              </div>

              {savedScreens.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <div className="text-xs font-medium text-slate-700 dark:text-slate-300">Recent</div>
                  <div className="flex flex-wrap gap-1.5">
                    {savedScreens.slice(-4).map((s) => (
                      <button
                        key={s.id}
                        onClick={() => handleSavedSelect(s.id)}
                        className={cn(
                          'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                          selectedSavedId === s.id ? 'border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300'
                        )}
                      >
                        <Bookmark className="h-3 w-3" />
                        {s.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="lg:col-span-8 border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300">
                    <Filter className="h-3.5 w-3.5" />
                  </div>
                  <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Active filters</CardTitle>
                  <Badge variant="secondary" className="rounded-full text-[11px]">
                    {activeChips.length} active
                  </Badge>
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="sm" onClick={() => setShowAdvanced((v) => !v)} className="h-7 text-xs">
                    <SlidersHorizontal className="h-3.5 w-3.5" />
                    {showAdvanced ? 'Hide advanced' : 'Advanced filters'}
                    {showAdvanced ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </Button>
                  {hasActiveFilters && (
                    <Button variant="outline" size="sm" onClick={handleClear} className="h-7 text-xs">
                      <Trash2 className="h-3 w-3" />
                      Clear all
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {activeChips.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-center dark:border-slate-800 dark:bg-slate-900/50">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300">No filters applied</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">Showing broad universe. Add filters below or load a saved screen to narrow down.</p>
                </div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {activeChips.map((chip) => (
                    <Badge key={chip.key} variant="secondary" className="group gap-1 rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 pr-1">
                      <span>{chip.label}</span>
                      <button onClick={chip.onRemove} className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-white/20 text-white hover:bg-white/30 dark:bg-slate-900/10 dark:text-slate-900 dark:hover:bg-slate-900/20" aria-label={`Remove ${chip.label}`}>
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                  <button onClick={handleClear} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                    <X className="h-3 w-3" />
                    Clear
                  </button>
                </div>
              )}

              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-300">
                <span className="font-medium text-slate-900 dark:text-white">Tip:</span> Combine market + prediction confidence to find high-conviction ideas, then inspect each ticker on its detail page before acting. Forecasts are probabilistic.
              </div>

              <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  High confidence ≥70
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                  Medium 50-69
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                  Low &lt;50
                </span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <Card className="border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <CardHeader className="pb-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 text-slate-700 dark:text-slate-300" />
                <CardTitle className="text-sm font-semibold">Filters</CardTitle>
                <Badge variant="outline" className="rounded-full font-medium text-xs">
                  {hasActiveFilters ? `${activeChips.length} active` : 'No filters'}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" onClick={() => setShowAdvanced((v) => !v)} className="h-7 text-xs">
                  {showAdvanced ? 'Basic view' : 'Advanced view'}
                  {showAdvanced ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </Button>
                <Button variant="outline" size="sm" onClick={handleClear} className="h-7 bg-white dark:bg-slate-900">
                  <Trash2 className="h-3.5 w-3.5" />
                  Clear
                </Button>
                <Button size="sm" onClick={handleSearch} disabled={isFetching} className="h-7">
                  <Search className="h-3.5 w-3.5" />
                  Apply
                </Button>
              </div>
            </div>
            <CardDescription className="text-xs">All filters are combined with AND. Use Advanced to access technicals and prediction thresholds.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Row 1: Market, Exchange, Sector, Price */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Market</Label>
                <Select value={filters.market} onValueChange={(v) => setFilters((p) => ({ ...p, market: (v as string) ?? 'all', exchange: 'all' }))}>
                  <SelectTrigger className="h-9 bg-white dark:bg-slate-900">
                    <SelectValue placeholder="All Markets" />
                  </SelectTrigger>
                  <SelectContent>
                    {MARKET_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Exchange</Label>
                <Select value={filters.exchange} onValueChange={(v) => setFilters((p) => ({ ...p, exchange: (v as string) ?? 'all' }))}>
                  <SelectTrigger className="h-9 bg-white dark:bg-slate-900">
                    <SelectValue placeholder="All Exchanges" />
                  </SelectTrigger>
                  <SelectContent>
                    {exchangeOptions.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Sector</Label>
                <Select value={filters.sector} onValueChange={(v) => setFilters((p) => ({ ...p, sector: (v as string) ?? 'all' }))}>
                  <SelectTrigger className="h-9 bg-white dark:bg-slate-900">
                    <SelectValue placeholder="All Sectors" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Sectors</SelectItem>
                    {sectorOptions.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Price (₹ / $)</Label>
                <div className="flex gap-2">
                  <Input type="number" placeholder="Min" value={filters.priceMin} onChange={(e) => setFilters((p) => ({ ...p, priceMin: e.target.value }))} className="h-9" min={0} />
                  <Input type="number" placeholder="Max" value={filters.priceMax} onChange={(e) => setFilters((p) => ({ ...p, priceMax: e.target.value }))} className="h-9" min={0} />
                </div>
                <p className="text-[11px] text-muted-foreground">Maps to backend price_min / price_max</p>
              </div>
            </div>

            {/* Row 2: Performance, Momentum, Volatility, Expected Return */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Performance</Label>
                <Select value={filters.performance} onValueChange={(v) => setFilters((p) => ({ ...p, performance: (v as string) ?? 'all' }))}>
                  <SelectTrigger className="h-9 bg-white dark:bg-slate-900">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="gainers">Gainers (&gt;0%)</SelectItem>
                    <SelectItem value="losers">Losers (&lt;0%)</SelectItem>
                    <SelectItem value="strong_gainers">Strong gainers (&gt;2%)</SelectItem>
                    <SelectItem value="strong_losers">Strong losers (&lt;-2%)</SelectItem>
                    <SelectItem value="flat">Flat (-1% to 1%)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Maps to performance_min/max</p>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Momentum / Prediction</Label>
                <Select value={filters.momentum} onValueChange={(v) => setFilters((p) => ({ ...p, momentum: (v as string) ?? 'all' }))}>
                  <SelectTrigger className="h-9 bg-white dark:bg-slate-900">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All directions</SelectItem>
                    <SelectItem value="up">Bullish (UP)</SelectItem>
                    <SelectItem value="down">Bearish (DOWN)</SelectItem>
                    <SelectItem value="neutral">Neutral</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">Maps to prediction_direction</p>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Volatility</Label>
                <Select value={filters.volatility} onValueChange={(v) => setFilters((p) => ({ ...p, volatility: (v as string) ?? 'all' }))}>
                  <SelectTrigger className="h-9 bg-white dark:bg-slate-900">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="low">Low (&lt;15)</SelectItem>
                    <SelectItem value="medium">Medium (15-30)</SelectItem>
                    <SelectItem value="high">High (&gt;30)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground">20-day vol. proxy</p>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Expected return ≥ (%)</Label>
                <Input type="number" placeholder="e.g., 1.5" value={filters.expectedReturnMin} onChange={(e) => setFilters((p) => ({ ...p, expectedReturnMin: e.target.value }))} className="h-9" step={0.1} />
                <p className="text-[11px] text-muted-foreground">Maps to expected_return_min (fraction)</p>
              </div>
            </div>

            {/* Advanced */}
            {showAdvanced && (
              <div className="space-y-5 rounded-xl border border-slate-200 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-800/20">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="rounded-full bg-white dark:bg-slate-900">
                    Advanced
                  </Badge>
                  <span className="text-xs text-muted-foreground">Technicals + prediction thresholds</span>
                </div>

                <div className="grid gap-6 lg:grid-cols-3">
                  <div className="space-y-3">
                    <Label className="text-xs font-medium">RSI (min / max) — 0 to 100</Label>
                    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                      <div className="flex items-center justify-between text-xs font-medium">
                        <span className="text-slate-600 dark:text-slate-300">
                          {filters.rsiMin} — {filters.rsiMax}
                        </span>
                        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold', filters.rsiMin < 30 ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : filters.rsiMax > 70 ? 'bg-red-50 text-red-700 ring-1 ring-red-200' : 'bg-slate-100 text-slate-600')}>
                          {filters.rsiMax > 70 ? 'Overbought' : filters.rsiMin < 30 ? 'Oversold' : 'Neutral band'}
                        </span>
                      </div>
                      <div className="pt-4">
                        <Slider value={[filters.rsiMin, filters.rsiMax]} min={0} max={100} step={1} onValueChange={(v) => { const arr = v as number[]; setFilters((p) => ({ ...p, rsiMin: arr[0] ?? 0, rsiMax: arr[1] ?? 100 })); }} />
                      </div>
                      <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                        <span>Oversold &lt;30</span>
                        <span>Overbought &gt;70</span>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2">
                        <Input type="number" min={0} max={100} value={filters.rsiMin} onChange={(e) => setFilters((p) => ({ ...p, rsiMin: Math.max(0, Math.min(100, parseNum(e.target.value, 0))) }))} className="h-8" placeholder="Min" />
                        <Input type="number" min={0} max={100} value={filters.rsiMax} onChange={(e) => setFilters((p) => ({ ...p, rsiMax: Math.max(0, Math.min(100, parseNum(e.target.value, 100))) }))} className="h-8" placeholder="Max" />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <Label className="text-xs font-medium">Prediction probability ≥ {filters.probabilityMin}%</Label>
                    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-700 dark:text-slate-300">Minimum UP probability</span>
                        <Badge variant="outline" className="font-mono text-xs">
                          {filters.probabilityMin}%
                        </Badge>
                      </div>
                      <div className="pt-4">
                        <Slider value={[filters.probabilityMin]} min={0} max={100} step={1} onValueChange={(v) => { const arr = v as number[]; setFilters((p) => ({ ...p, probabilityMin: arr[0] ?? 0 })); }} />
                      </div>
                      <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                        <span>0% (any)</span>
                        <span>100% (strict)</span>
                      </div>
                      <p className="mt-2 text-[11px] text-muted-foreground">Maps to prediction_probability_min (0-1). Example: 70 → 0.7</p>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <Label className="text-xs font-medium">Confidence ≥ {filters.confidenceMin}</Label>
                    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-slate-700 dark:text-slate-300">Minimum model confidence</span>
                        <Badge className={cn('rounded-full text-xs font-semibold', filters.confidenceMin >= 70 ? 'bg-emerald-600 text-white' : filters.confidenceMin >= 50 ? 'bg-amber-500 text-white' : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200')}>
                          {confidenceLabel(filters.confidenceMin)} • {filters.confidenceMin}
                        </Badge>
                      </div>
                      <div className="pt-4">
                        <Slider value={[filters.confidenceMin]} min={0} max={100} step={1} onValueChange={(v) => { const arr = v as number[]; setFilters((p) => ({ ...p, confidenceMin: arr[0] ?? 0 })); }} />
                      </div>
                      <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                        <span>0 (any)</span>
                        <span>100 (max)</span>
                      </div>
                      <p className="mt-2 text-[11px] text-muted-foreground">Maps to confidence_min. Use 70+ for high-conviction screens.</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 dark:border-amber-900/50 dark:bg-amber-950/20">
                  <p className="text-xs font-semibold text-amber-800 dark:text-amber-200">Prediction filters are horizon 1D</p>
                  <p className="text-xs leading-5 text-amber-700/80 dark:text-amber-100/70">Probability, expected return and confidence are derived from the 1-day StockAI ensemble. Combine with RSI/volatility for confluence. Past prediction performance does not guarantee future results.</p>
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
              <span className="text-xs text-muted-foreground">Active: {activeChips.length} • Results: {total} • Sorted by {sortKey} ({sortDir})</span>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={handleClear} className="h-8 bg-white dark:bg-slate-900">
                  <Trash2 className="h-3.5 w-3.5" />
                  Clear filters
                </Button>
                <Button size="sm" onClick={handleSearch} disabled={isFetching} className="h-8">
                  <Search className="h-3.5 w-3.5" />
                  Apply & Scan
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Results Table */}
        <Card className="border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
          <CardHeader className="pb-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <CardTitle className="text-sm font-semibold">Results</CardTitle>
                <Badge variant="secondary" className="rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                  {isLoading ? 'Loading…' : `${sortedRows.length} of ${total}`}
                </Badge>
                {hasSearched && !isLoading && (
                  <Badge variant="outline" className="hidden sm:inline-flex rounded-full text-xs">
                    Page {page} of {totalPages}
                  </Badge>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="hidden sm:inline">Horizontal scroll on mobile • Click headers to sort</span>
                <Button variant="outline" size="sm" onClick={handleSearch} disabled={isFetching} className="h-7 bg-white dark:bg-slate-900 sm:ml-2">
                  <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} />
                  Refresh
                </Button>
              </div>
            </div>
            <CardDescription className="text-xs">
              Columns: Symbol, Name, Exchange, Price, Change%, Sector, RSI, Volatility, Prediction direction, Probability, Expected return, Confidence. API: <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">POST /api/v1/screener</code> via <code className="font-mono text-[11px]">api.screenStocks(filters, page, pageSize)</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {/* Error */}
            {error && (
              <div className="mx-4 mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-950/20">
                <div className="flex gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
                    <AlertTriangle className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">We couldn’t reach the live screener</p>
                    <p className="mt-1 text-xs leading-5 text-amber-800/80 dark:text-amber-100/70">{error}. Showing locally filtered sample data so you can continue exploring. Filters and sorting remain fully functional.</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => fetchScreener(page)} className="h-7 border-amber-200 bg-white text-amber-900 hover:bg-amber-50 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
                        <RefreshCw className="h-3.5 w-3.5" />
                        Retry live scan
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setError(null)} className="h-7 text-amber-700 dark:text-amber-300">
                        Dismiss
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Table container with horizontal scroll on mobile */}
            <div className="relative w-full overflow-auto border-t border-slate-200 dark:border-slate-800">
              <div className="min-w-[1180px]">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-slate-50/95 backdrop-blur supports-[backdrop-filter]:bg-slate-50/80 dark:bg-slate-900/95">
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="h-9 whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('symbol')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Symbol <SortIcon active={sortKey === 'symbol'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('name')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Name <SortIcon active={sortKey === 'name'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('exchange')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Exchange <SortIcon active={sortKey === 'exchange'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-right text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('price')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white ml-auto">
                          Price <SortIcon active={sortKey === 'price'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-right text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('changePercent')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white ml-auto">
                          Change% <SortIcon active={sortKey === 'changePercent'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('sector')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Sector <SortIcon active={sortKey === 'sector'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-right text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('rsi')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white ml-auto">
                          RSI <SortIcon active={sortKey === 'rsi'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-right text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('volatility')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white ml-auto">
                          Volatility <SortIcon active={sortKey === 'volatility'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('direction')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white">
                          Prediction <SortIcon active={sortKey === 'direction'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-right text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('probability')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white ml-auto">
                          Probability <SortIcon active={sortKey === 'probability'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-right text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('expectedReturn')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white ml-auto">
                          Exp. return <SortIcon active={sortKey === 'expectedReturn'} />
                        </button>
                      </TableHead>
                      <TableHead className="h-9 whitespace-nowrap text-right text-[11px] font-semibold uppercase tracking-wide">
                        <button onClick={() => toggleSort('confidence')} className="inline-flex items-center gap-1 hover:text-slate-900 dark:hover:text-white ml-auto">
                          Confidence <SortIcon active={sortKey === 'confidence'} />
                        </button>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isLoading ? (
                      Array.from({ length: 8 }).map((_, i) => (
                        <TableRow key={i} className="hover:bg-transparent">
                          {Array.from({ length: 12 }).map((__, j) => (
                            <TableCell key={j} className="py-3">
                              <Skeleton className="h-4 w-full" />
                            </TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : sortedRows.length === 0 ? (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={12} className="h-[320px] p-0">
                          <div className="flex h-full flex-col items-center justify-center px-6 py-10 text-center">
                            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                              <SearchX className="h-6 w-6 text-slate-400" />
                            </div>
                            <h3 className="mt-4 text-sm font-semibold text-slate-900 dark:text-white">No stocks matched</h3>
                            <p className="mt-1 max-w-md text-sm leading-5 text-muted-foreground">No instruments satisfied all active filters. Try broadening RSI, lowering confidence/probability thresholds, or clearing sector/market constraints.</p>
                            <div className="mt-4 flex flex-wrap justify-center gap-2">
                              <Button size="sm" variant="outline" onClick={handleClear}>
                                <Trash2 className="h-4 w-4" />
                                Clear filters
                              </Button>
                              <Button size="sm" onClick={() => setShowAdvanced(true)}>
                                <SlidersHorizontal className="h-4 w-4" />
                                Adjust advanced filters
                              </Button>
                            </div>
                            <p className="mt-3 text-xs text-slate-400">Example that returns results: Market: India, Momentum: Bullish, Confidence ≥ 70</p>
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : (
                      sortedRows.map((row) => (
                        <TableRow key={row.id} className="group hover:bg-slate-50/70 dark:hover:bg-slate-800/40">
                          <TableCell className="py-2.5">
                            <Link href={`/stocks/${row.symbol}?exchange=${row.exchange}`} className="font-mono text-xs font-semibold tracking-wide text-slate-900 hover:text-primary dark:text-white dark:hover:text-primary">
                              {row.symbol}
                            </Link>
                          </TableCell>
                          <TableCell className="max-w-[180px] py-2.5">
                            <div className="truncate text-xs font-medium text-slate-700 dark:text-slate-200" title={row.name}>
                              {row.name}
                            </div>
                            <div className="text-[11px] text-muted-foreground sm:hidden">{row.sector ?? '—'}</div>
                          </TableCell>
                          <TableCell className="py-2.5">
                            <Badge variant="outline" className="rounded-md border-slate-200 bg-white font-mono text-[11px] font-medium dark:border-slate-700 dark:bg-slate-900">
                              {row.exchange}
                            </Badge>
                          </TableCell>
                          <TableCell className="py-2.5 text-right font-mono text-xs tabular-nums">
                            <span className="font-medium text-slate-900 dark:text-white">{row.price == null || Number.isNaN(row.price) ? '—' : formatPrice(row.price, row.exchange === 'NSE' || row.exchange === 'BSE' ? 'INR' : 'USD')}</span>
                          </TableCell>
                          <TableCell className="py-2.5 text-right">
                            <span className={cn('inline-flex items-center justify-end gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ring-1', changeBg(row.changePercent))}>
                              {row.changePercent == null || Number.isNaN(row.changePercent) ? (
                                <span className="text-slate-400">—</span>
                              ) : (
                                <>
                                  {row.changePercent > 0 ? <TrendingUp className="h-3 w-3" /> : row.changePercent < 0 ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                                  {formatPercent(row.changePercent)}
                                </>
                              )}
                            </span>
                          </TableCell>
                          <TableCell className="py-2.5">
                            {row.sector ? (
                              <Badge variant="secondary" className="rounded-full bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 text-[11px] font-medium">
                                {row.sector}
                              </Badge>
                            ) : (
                              <span className="text-xs text-slate-400">—</span>
                            )}
                          </TableCell>
                          <TableCell className={cn('py-2.5 text-right font-mono text-xs tabular-nums', rsiTone(row.rsi))}>{row.rsi != null ? row.rsi.toFixed(1) : '—'}</TableCell>
                          <TableCell className={cn('py-2.5 text-right font-mono text-xs tabular-nums', volatilityTone(row.volatility))}>{row.volatility != null ? row.volatility.toFixed(1) : '—'}</TableCell>
                          <TableCell className="py-2.5">
                            {row.prediction ? (
                              <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ring-1', directionBadge(row.prediction.direction))}>
                                {row.prediction.direction === 'up' ? <TrendingUp className="h-3 w-3" /> : row.prediction.direction === 'down' ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                                {row.prediction.direction.toUpperCase()}
                              </span>
                            ) : (
                              <Badge variant="outline" className="rounded-full text-[11px] text-slate-500">
                                No pred
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="py-2.5 text-right">
                            {row.prediction ? (
                              <div className="flex flex-col items-end gap-1">
                                <span className="font-mono text-xs font-semibold tabular-nums">{row.prediction.probability}%</span>
                                <div className="h-1 w-16 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                                  <div className={cn('h-full rounded-full', row.prediction.direction === 'up' ? 'bg-emerald-500' : row.prediction.direction === 'down' ? 'bg-red-500' : 'bg-amber-500')} style={{ width: `${row.prediction.probability}%` }} />
                                </div>
                              </div>
                            ) : (
                              <span className="text-xs text-slate-400">—</span>
                            )}
                          </TableCell>
                          <TableCell className={cn('py-2.5 text-right font-mono text-xs font-semibold tabular-nums', row.prediction ? (row.prediction.expectedReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400') : 'text-slate-400')}>{row.prediction ? formatPercent(row.prediction.expectedReturn) : '—'}</TableCell>
                          <TableCell className="py-2.5 text-right">
                            {row.prediction ? (
                              <div className="flex flex-col items-end gap-1">
                                <span className="font-mono text-xs font-semibold tabular-nums">
                                  {row.prediction.confidence}
                                  <span className="ml-1 text-[11px] font-normal text-muted-foreground">{confidenceLabel(row.prediction.confidence)}</span>
                                </span>
                                <div className="h-1 w-16 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                                  <div className={cn('h-full rounded-full', row.prediction.confidence >= 70 ? 'bg-emerald-500' : row.prediction.confidence >= 50 ? 'bg-amber-500' : 'bg-slate-400')} style={{ width: `${row.prediction.confidence}%` }} />
                                </div>
                              </div>
                            ) : (
                              <span className="text-xs text-slate-400">—</span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>

            {/* Pagination & footer */}
            <div className="flex flex-col gap-3 border-t border-slate-200 bg-slate-50/50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/50 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-xs text-muted-foreground">
                {isLoading ? <Skeleton className="h-4 w-40" /> : <>Showing {sortedRows.length} rows • Page {page} of {totalPages} • Total {total} • Sort: {sortKey} {sortDir}</>}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => fetchScreener(Math.max(1, page - 1))} disabled={page <= 1 || isLoading || isFetching} className="h-8 bg-white dark:bg-slate-900">
                  Previous
                </Button>
                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(totalPages, 5) }).map((_, i) => {
                    // show window around current page
                    let p = i + 1;
                    if (totalPages > 5) {
                      const start = Math.max(1, Math.min(totalPages - 4, page - 2));
                      p = start + i;
                    }
                    return (
                      <button key={p} onClick={() => fetchScreener(p)} className={cn('h-8 w-8 rounded-md border text-xs font-medium', p === page ? 'border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-900' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300')}>
                        {p}
                      </button>
                    );
                  })}
                  {totalPages > 5 && page < totalPages - 2 && <span className="px-1 text-xs text-slate-400">…</span>}
                  {totalPages > 5 && page < totalPages - 1 && (
                    <button onClick={() => fetchScreener(totalPages)} className={cn('h-8 w-8 rounded-md border text-xs font-medium', page === totalPages ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300')}>
                      {totalPages}
                    </button>
                  )}
                </div>
                <Button variant="outline" size="sm" onClick={() => fetchScreener(Math.min(totalPages, page + 1))} disabled={page >= totalPages || isLoading || isFetching} className="h-8 bg-white dark:bg-slate-900">
                  Next
                </Button>
              </div>
            </div>

            {/* Disclaimer */}
            <div className="border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
              <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-700 dark:text-slate-300">Disclaimer:</span> Screener results include probabilistic forecasts that are inherently uncertain. They are not investment advice. Verify prices and do your own research. Data may be delayed. See{' '}
                <Link href="/research" className="underline underline-offset-4 hover:text-slate-700 dark:hover:text-slate-200">
                  methodology & limitations
                </Link>
                .
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
