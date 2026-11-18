'use client';

import { use, useEffect, useMemo, useState, useCallback } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api/client';
import { cn, formatPrice, formatPercent } from '@/lib/utils';
import { hasClearEdge, NO_EDGE_THRESHOLD } from '@/lib/prediction';
import { FreshnessBadge } from '@/components/ui/freshness-badge';
import { freshnessStyle, normalizeFreshness } from '@/lib/freshness';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ProbabilityBarGroup } from '@/components/ui/probability-bar';
import { PredictionExplanationPanel } from '@/components/prediction-explanation-panel';
import { RsiIntelligencePanel } from '@/components/rsi-intelligence-panel';
import { TimeframeSelector, ChartTypeSelector, IndicatorSelector, type ChartType } from '@/components/charts/ChartContainer';
import { ProChart } from '@/components/charts/ProChart';
import { IndicatorPane, PANE_KINDS, type PaneKind } from '@/components/charts/IndicatorPane';
import type { HistoricalBar } from '@/types';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  RefreshCw,
  Clock,
  Activity,
  BarChart3,
  Info,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  ShieldAlert,
  Brain,
  Calendar,
  Target,
  Layers,
  Maximize2,
  Minimize2,
} from 'lucide-react';

// --- Helpers ---
function getParam(sp: Record<string, any>, key: string): string | undefined {
  const v = sp?.[key];
  if (Array.isArray(v)) return v[0] as string;
  if (typeof v === 'string') return v;
  return undefined;
}

function parseNumber(v: any, fallback = 0): number {
  if (v === null || v === undefined) return fallback;
  if (typeof v === 'number') return v;
  const n = parseFloat(String(v));
  return Number.isFinite(n) ? n : fallback;
}

function toPercentValue(v: any): number {
  const n = parseNumber(v, 0);
  // if decimal 0-1, convert to percent
  if (Math.abs(n) <= 1 && Math.abs(n) > 0) {
    const cand = n * 100;
    // heuristic: if cand < 20 and abs n < 1, it's likely a fraction
    if (Math.abs(cand) < 80) return cand;
  }
  return n;
}

function normalizeProbability(raw: any): { up: number; neutral: number; down: number } {
  let up = raw?.probabilities?.up ?? raw?.up_probability ?? raw?.upProbability ?? 0;
  let neutral = raw?.probabilities?.neutral ?? raw?.neutral_probability ?? raw?.neutralProbability ?? 0;
  let down = raw?.probabilities?.down ?? raw?.down_probability ?? raw?.downProbability ?? 0;
  up = parseNumber(up, 0);
  neutral = parseNumber(neutral, 0);
  down = parseNumber(down, 0);
  const sum = up + neutral + down;
  const isFraction = sum <= 1.05 && sum > 0 && up <= 1 && neutral <= 1 && down <= 1;
  if (isFraction) {
    up = Math.round(up * 100);
    neutral = Math.round(neutral * 100);
    down = Math.round(down * 100);
  } else {
    up = Math.round(up);
    neutral = Math.round(neutral);
    down = Math.round(down);
  }
  // normalize to 100 if rounding drift
  const total = up + neutral + down;
  if (total !== 100 && total > 0) {
    const diff = 100 - total;
    // add diff to largest bucket
    if (up >= neutral && up >= down) up += diff;
    else if (neutral >= up && neutral >= down) neutral += diff;
    else down += diff;
  }
  return { up, neutral, down };
}

function horizonLabel(): string {
  // v1.0 forecasts the next trading day only (§15 horizon honesty).
  return '1 trading day';
}

function timeframeToApi(timeframe: string): { timeframe: string; limit: number } {
  // backend allows 1m/5m/15m/1h/1d/1w/1M but we use 1d for all daily views.
  // 5D = last ~7 daily bars (a trading week); 1D keeps 30 for context.
  const map: Record<string, number> = {
    '1D': 30,
    '5D': 7,
    '1W': 14,
    '1M': 30,
    '3M': 90,
    '6M': 180,
    '1Y': 365,
    '5Y': 1250,
    'MAX': 2500,
  };
  return { timeframe: '1d', limit: map[timeframe] ?? 90 };
}

function getMarketStatusVariant(status: string) {
  const s = (status || '').toLowerCase();
  if (s === 'open') return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-200';
  if (s === 'closed') return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200';
  if (s === 'pre-market') return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200';
  if (s === 'after-hours') return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200';
  return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-200';
}

function formatTimestamp(ts?: string | null): string {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return String(ts);
  }
}

function isStaleTimestamp(ts?: string | null, minutes = 15): boolean {
  if (!ts) return true;
  const d = new Date(ts).getTime();
  if (Number.isNaN(d)) return true;
  return Date.now() - d > minutes * 60 * 1000;
}

// --- Types ---
type NormalizedPrediction = {
  symbol: string;
  direction: 'up' | 'neutral' | 'down';
  probabilities: { up: number; neutral: number; down: number };
  expectedReturn: number;
  expectedRange: { low: number; high: number };
  confidence: number | null;
  modelVersion: string;
  dataTimestamp: string;
  predictionTimestamp: string;
  horizon: string;
  noClearEdge: boolean;
  topProbability: number | null;
  probabilityMargin: number | null;
  confidenceBasis: string | null;
  confidenceNote: string | null;
  raw: any;
};

type NormalizedHistoryItem = {
  date: string;
  prediction: 'up' | 'neutral' | 'down';
  upProbability: number;
  expectedReturn: number;
  actualReturn: number | null;
  actualDirection?: 'up' | 'neutral' | 'down' | null;
  result: 'correct' | 'incorrect' | 'neutral' | 'pending' | null;
  countedInAccuracy?: boolean;
};

type NormalizedHistory = {
  symbol: string;
  items: NormalizedHistoryItem[];
  summary: {
    totalPredictions: number;
    correctPredictions: number;
    incorrectPredictions: number;
    neutralPredictions: number;
    neutralCorrect: number;
    directionalCount: number;
    accuracy: number | null;
    accuracyReliable: boolean;
    minimumSample: number;
    confidenceIntervalLower: number | null;
    confidenceIntervalUpper: number | null;
    coverage: number | null;
    scoringPolicy: string | null;
    averageReturn: number;
    completedCount: number;
    pendingCount: number;
  };
};

// --- Page ---
export default function StockDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // Handle Promise in Next 15 (use) with fallback for direct object
  const resolvedParams: { symbol: string } = (params as any)?.then ? use(params as any) : (params as any);
  const resolvedSearchParams: Record<string, any> =
    (searchParams as any)?.then ? use(searchParams as any) : ((searchParams as any) ?? {});

  const rawSymbol = (resolvedParams?.symbol || '').toUpperCase().trim();
  const symbol = rawSymbol || 'AAPL';
  const exchange = (getParam(resolvedSearchParams, 'exchange') || getParam(resolvedSearchParams, 'exchange_code') || 'NASDAQ').toUpperCase();
  const market = getParam(resolvedSearchParams, 'market');

  // v1.0 natively forecasts the next trading day only (§15 horizon honesty:
  // the API refuses 1w/1m labels). The horizon is therefore fixed, not a choice.

  // UI state
  const [timeframe, setTimeframe] = useState<string>('1M');
  const [chartType, setChartType] = useState<ChartType>('candlestick');
  const [showVolume, setShowVolume] = useState(true);
  const [indicators, setIndicators] = useState<string[]>(['SMA20']);
  const [subpanes, setSubpanes] = useState<PaneKind[]>([]);
  const [percentView, setPercentView] = useState(false);
  const [showSwings, setShowSwings] = useState(false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [horizon] = useState<'1d'>('1d');

  // Data state
  const [quote, setQuote] = useState<any | null>(null);
  const [instrument, setInstrument] = useState<any | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(true);
  const [quoteError, setQuoteError] = useState<string | null>(null);

  const [history, setHistory] = useState<HistoricalBar[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [prediction, setPrediction] = useState<NormalizedPrediction | null>(null);
  const [predictionLoading, setPredictionLoading] = useState(true);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [predictionUnavailable, setPredictionUnavailable] = useState(false);

  const [factors, setFactors] = useState<{ positive: string[]; neutral: string[]; negative: string[] } | null>(null);
  const [factorsLoading, setFactorsLoading] = useState(true);
  const [factorsError, setFactorsError] = useState<string | null>(null);

  const [predHistory, setPredHistory] = useState<NormalizedHistory | null>(null);
  const [predHistoryLoading, setPredHistoryLoading] = useState(true);
  const [predHistoryError, setPredHistoryError] = useState<string | null>(null);

  // Prediction history UI state
  const [resultFilter, setResultFilter] = useState<'all' | 'correct' | 'incorrect' | 'pending'>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // Refresh tick
  const [refreshing, setRefreshing] = useState(false);

  // Fetch quote + instrument
  const fetchQuoteAndInstrument = useCallback(async () => {
    if (!symbol) return;
    setQuoteLoading(true);
    setQuoteError(null);
    try {
      const q = await api.getQuote(symbol, exchange);
      // Normalize quote: backend may return snake_case
      const normalized = {
        symbol: q.symbol ?? symbol,
        price: parseNumber(q.price ?? q.close, 0),
        change: parseNumber(q.change, 0),
        changePercent: parseNumber(q.change_percent ?? q.changePercent, 0),
        volume: parseNumber(q.volume, 0),
        high: parseNumber(q.high, 0),
        low: parseNumber(q.low, 0),
        open: parseNumber(q.open, 0),
        previousClose: parseNumber(q.previous_close ?? q.previousClose, 0),
        timestamp: q.timestamp ?? q.data_timestamp ?? new Date().toISOString(),
        marketStatus: q.market_status ?? q.marketStatus ?? 'unknown',
        currency: q.currency ?? 'USD',
        // Backend-classified data status (fresh/recent/delayed/stale/unavailable)
        freshness: q.freshness ?? 'unavailable',
        provider: q.provider ?? null,
        sourceTimestamp: q.source_timestamp ?? q.sourceTimestamp ?? null,
        ingestedAt: q.ingested_at ?? q.ingestedAt ?? null,
        exchange: q.exchange ?? exchange,
      };
      setQuote(normalized);

      // Try instrument for name
      try {
        const inst = await api.getInstrument(symbol, exchange);
        setInstrument(inst);
      } catch (err) {
        console.warn('[stocks] getInstrument failed', err);
        try {
          const search = await api.searchInstruments(symbol, { exchange, limit: 5 } as any);
          const found = (search as any[])?.find((s: any) => s.symbol?.toUpperCase() === symbol) ?? (search as any[])?.[0];
          if (found) setInstrument(found);
          else setInstrument(null);
        } catch (searchErr) {
          console.warn('[stocks] instrument search fallback failed', searchErr);
          setInstrument(null);
        }
      }
    } catch (e: any) {
      const msg = e?.message || 'Failed to load quote';
      setQuoteError(msg);
      setQuote(null);
    } finally {
      setQuoteLoading(false);
    }
  }, [symbol, exchange]);

  // Fetch history
  const fetchHistory = useCallback(async () => {
    if (!symbol) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const { timeframe: apiTf, limit } = timeframeToApi(timeframe);
      const data = await api.getHistory(symbol, exchange, { timeframe: apiTf, limit });
      // Normalize bars
      const bars: HistoricalBar[] = (data as any[]).map((b: any) => ({
        timestamp: b.timestamp ?? b.date ?? b.time ?? new Date().toISOString(),
        open: parseNumber(b.open, 0),
        high: parseNumber(b.high, 0),
        low: parseNumber(b.low, 0),
        close: parseNumber(b.close ?? b.price, 0),
        volume: parseNumber(b.volume, 0),
      }));
      // Ensure sorted ascending by timestamp
      bars.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
      setHistory(bars);
    } catch (e: any) {
      setHistoryError(e?.message || 'Failed to load historical data');
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [symbol, exchange, timeframe]);

  // Fetch prediction + factors + history
  const fetchPredictions = useCallback(async () => {
    if (!symbol) return;
    setPredictionLoading(true);
    setPredictionError(null);
    setPredictionUnavailable(false);
    setFactorsLoading(true);
    setFactorsError(null);
    setPredHistoryLoading(true);
    setPredHistoryError(null);

    // Prediction
    try {
      const raw = await api.getPrediction(symbol, exchange, horizon);
      if (!raw) {
        setPredictionUnavailable(true);
        setPrediction(null);
      } else {
        // Normalize prediction
        const probs = normalizeProbability(raw);
        const expRetRaw = raw.expected_return ?? raw.expectedReturn ?? 0;
        const lowRaw = raw.range_lower ?? raw.rangeLower ?? raw.expected_range?.low ?? raw.expectedRange?.low ?? 0;
        const highRaw = raw.range_upper ?? raw.rangeUpper ?? raw.expected_range?.high ?? raw.expectedRange?.high ?? 0;
        // heuristic for decimal vs percent
        const normRet = (() => {
          const v = parseNumber(expRetRaw, 0);
          if (Math.abs(v) < 1 && Math.abs(v) > 0) {
            const cand = v * 100;
            if (Math.abs(cand) < 20) return cand;
          }
          return v;
        })();
        const normLow = (() => {
          const v = parseNumber(lowRaw, 0);
          if (Math.abs(v) < 1 && Math.abs(v) > 0) {
            const cand = v * 100;
            if (Math.abs(cand) < 20) return cand;
          }
          return v;
        })();
        const normHigh = (() => {
          const v = parseNumber(highRaw, 0);
          if (Math.abs(v) < 1 && Math.abs(v) > 0) {
            const cand = v * 100;
            if (Math.abs(cand) < 20) return cand;
          }
          return v;
        })();
        const mv = raw.model_version ?? raw.modelVersion ?? raw.model_version_id ?? 'Ensemble v1.0';
        const mvStr = typeof mv === 'string' ? mv : mv?.version ?? mv?.name ?? 'Ensemble v1.0';
        const normalized: NormalizedPrediction = {
          symbol,
          direction: (raw.predicted_direction ?? raw.direction ?? 'neutral') as any,
          probabilities: probs,
          expectedReturn: normRet,
          expectedRange: { low: normLow, high: normHigh },
          confidence: raw.confidence != null ? parseNumber(raw.confidence, 0) : null,
          modelVersion: typeof mvStr === 'string' ? mvStr : String(mvStr),
          dataTimestamp: raw.data_timestamp ?? raw.dataTimestamp ?? raw.prediction_timestamp ?? new Date().toISOString(),
          predictionTimestamp: raw.prediction_timestamp ?? raw.predictionTimestamp ?? raw.data_timestamp ?? new Date().toISOString(),
          horizon: raw.horizon ?? horizon,
          noClearEdge: Boolean(raw.no_clear_edge ?? raw.noClearEdge ?? !hasClearEdge(probs.up, probs.neutral, probs.down)),
          topProbability: raw.top_probability != null ? parseNumber(raw.top_probability, 0) : Math.max(probs.up, probs.neutral, probs.down),
          probabilityMargin: raw.probability_margin != null ? parseNumber(raw.probability_margin, 0) : null,
          confidenceBasis: raw.confidence_basis ?? null,
          confidenceNote: raw.confidence_note ?? null,
          raw,
        };
        setPrediction(normalized);
        setPredictionUnavailable(false);
      }
    } catch (e: any) {
      const msg = String(e?.message || '');
      if (msg.toLowerCase().includes('404') || msg.toLowerCase().includes('not found') || msg.toLowerCase().includes('no prediction')) {
        setPredictionUnavailable(true);
        setPrediction(null);
        setPredictionError(null);
      } else {
        setPredictionError(msg || 'Failed to load prediction');
        setPrediction(null);
      }
    } finally {
      setPredictionLoading(false);
    }

    // Factors
    try {
      const f = await api.getPredictionFactors(symbol, exchange, horizon);
      setFactors({
        positive: (f?.positive as string[]) ?? [],
        neutral: (f?.neutral as string[]) ?? [],
        negative: (f?.negative as string[]) ?? [],
      });
    } catch (e: any) {
      const msg = String(e?.message || '');
      if (msg.toLowerCase().includes('404') || msg.toLowerCase().includes('not found')) {
        setFactors({ positive: [], neutral: [], negative: [] });
        setFactorsError(null);
      } else {
        setFactorsError(msg || 'Failed to load factors');
        setFactors(null);
      }
    } finally {
      setFactorsLoading(false);
    }

    // History
    try {
      const rawHist: any = await api.getPredictionHistory(symbol, exchange, horizon, 100);
      const itemsRaw: any[] = rawHist?.items ?? rawHist ?? [];
      const summaryRaw: any = rawHist?.summary ?? {};
      const items: NormalizedHistoryItem[] = itemsRaw.map((it: any) => {
        // upProbability handling
        let upProb = it.up_probability ?? it.upProbability ?? it.up_prob ?? 0;
        upProb = parseNumber(upProb, 0);
        if (upProb <= 1 && upProb > 0) upProb = Math.round(upProb * 100);
        else upProb = Math.round(upProb);
        let expRet = parseNumber(it.expected_return ?? it.expectedReturn, 0);
        if (Math.abs(expRet) < 1 && Math.abs(expRet) > 0) {
          const cand = expRet * 100;
          if (Math.abs(cand) < 20) expRet = cand;
        }
        let actRet: number | null = it.actual_return ?? it.actualReturn ?? null;
        if (actRet !== null) {
          actRet = parseNumber(actRet, 0);
          if (Math.abs(actRet) < 1 && Math.abs(actRet) !== 0) {
            const cand = actRet * 100;
            if (Math.abs(cand) < 30) actRet = cand;
          }
        }
        let resultVal: any = it.result ?? it.is_correct ?? null;
        let normalizedResult: 'correct' | 'incorrect' | 'neutral' | 'pending' | null = null;
        if (resultVal === true || resultVal === 'correct' || resultVal === 'Correct') normalizedResult = 'correct';
        else if (resultVal === false || resultVal === 'incorrect' || resultVal === 'Incorrect') normalizedResult = 'incorrect';
        else if (resultVal === 'neutral' || resultVal === 'Neutral') normalizedResult = 'neutral';
        else if (resultVal === null || resultVal === undefined || resultVal === 'pending' || resultVal === 'Pending') normalizedResult = actRet === null ? 'pending' : null;
        // If the backend reports an outcome but no direction/return, it is pending.
        if (actRet === null && (normalizedResult === 'correct' || normalizedResult === 'incorrect' || normalizedResult === 'neutral')) {
          normalizedResult = 'pending';
        }
        if (normalizedResult === null && actRet === null) normalizedResult = 'pending';

        const predDir = (it.prediction ?? it.predicted_direction ?? 'neutral').toString().toLowerCase() as any;
        const actualDirRaw = it.actual_direction ?? it.actualDirection ?? null;
        const actualDir = actualDirRaw ? (String(actualDirRaw).toLowerCase() as any) : null;
        return {
          date: it.date ?? it.timestamp ?? '',
          prediction: predDir,
          upProbability: upProb,
          expectedReturn: expRet,
          actualReturn: actRet,
          actualDirection: actualDir,
          result: normalizedResult,
          countedInAccuracy: Boolean(it.counted_in_accuracy ?? (predDir === 'up' || predDir === 'down')),
        };
      });

      // The backend is the sole authority for accuracy. Never recompute a
      // hit rate in the browser: a client-side denominator silently diverges
      // from the canonical evaluation engine.
      const rawAccuracy = summaryRaw.accuracy ?? summaryRaw.accuracy_percent ?? null;
      const accuracy = rawAccuracy === null || rawAccuracy === undefined || rawAccuracy === ''
        ? null
        : parseNumber(rawAccuracy, 0);
      const summary = {
        totalPredictions: parseNumber(summaryRaw.total_predictions ?? summaryRaw.totalPredictions, items.length),
        correctPredictions: parseNumber(summaryRaw.correct_predictions ?? summaryRaw.correctPredictions, 0),
        incorrectPredictions: parseNumber(summaryRaw.incorrect_predictions ?? summaryRaw.incorrectPredictions, 0),
        neutralPredictions: parseNumber(summaryRaw.neutral_predictions ?? summaryRaw.neutralPredictions, 0),
        neutralCorrect: parseNumber(summaryRaw.neutral_correct ?? summaryRaw.neutralCorrect, 0),
        directionalCount: parseNumber(summaryRaw.directional_count ?? summaryRaw.directionalCount, 0),
        accuracy,
        accuracyReliable: Boolean(summaryRaw.accuracy_reliable ?? summaryRaw.accuracyReliable ?? false),
        minimumSample: parseNumber(summaryRaw.minimum_sample ?? summaryRaw.minimumSample, 30),
        confidenceIntervalLower: summaryRaw.confidence_interval_lower == null ? null : parseNumber(summaryRaw.confidence_interval_lower, 0),
        confidenceIntervalUpper: summaryRaw.confidence_interval_upper == null ? null : parseNumber(summaryRaw.confidence_interval_upper, 0),
        coverage: summaryRaw.coverage == null ? null : parseNumber(summaryRaw.coverage, 0),
        scoringPolicy: summaryRaw.scoring_policy ?? summaryRaw.scoringPolicy ?? null,
        averageReturn: parseNumber(summaryRaw.average_return ?? summaryRaw.averageReturn, 0),
        completedCount: parseNumber(summaryRaw.completed_count ?? summaryRaw.completedCount, 0),
        pendingCount: parseNumber(summaryRaw.pending_count ?? summaryRaw.pendingCount, 0),
      };
      // Fix average_return if fraction
      if (Math.abs(summary.averageReturn) < 1 && Math.abs(summary.averageReturn) > 0) {
        const cand = summary.averageReturn * 100;
        if (Math.abs(cand) < 30) summary.averageReturn = cand;
      }

      setPredHistory({ symbol, items, summary });
    } catch (e: any) {
      const msg = String(e?.message || '');
      if (msg.toLowerCase().includes('404')) {
        setPredHistory({ symbol, items: [], summary: { totalPredictions: 0, correctPredictions: 0, incorrectPredictions: 0, neutralPredictions: 0, neutralCorrect: 0, directionalCount: 0, accuracy: null, accuracyReliable: false, minimumSample: 30, confidenceIntervalLower: null, confidenceIntervalUpper: null, coverage: null, scoringPolicy: null, averageReturn: 0, completedCount: 0, pendingCount: 0 } });
        setPredHistoryError(null);
      } else {
        setPredHistoryError(msg || 'Failed to load prediction history');
        setPredHistory(null);
      }
    } finally {
      setPredHistoryLoading(false);
    }
  }, [symbol, exchange, horizon]);

  useEffect(() => {
    fetchQuoteAndInstrument();
  }, [fetchQuoteAndInstrument]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    fetchPredictions();
  }, [fetchPredictions]);

  const handleRefreshAll = useCallback(async () => {
    setRefreshing(true);
    await Promise.allSettled([fetchQuoteAndInstrument(), fetchHistory(), fetchPredictions()]);
    setRefreshing(false);
  }, [fetchQuoteAndInstrument, fetchHistory, fetchPredictions]);

  // Derived values
  const companyName = useMemo(() => {
    if (instrument?.name) return instrument.name;
    if (instrument?.exchange?.name) return instrument.name;
    return null;
  }, [instrument]);

  const isQuoteStale = useMemo(() => {
    // Trust the backend's freshness classification; do not derive staleness
    // client-side. (Backend: services/freshness.py)
    if (!quote) return false;
    const f = normalizeFreshness((quote as any).freshness);
    return !freshnessStyle(f).presentable;
  }, [quote]);

  const priceChangePositive = (quote?.changePercent ?? 0) >= 0;
  const filteredHistoryItems = useMemo(() => {
    if (!predHistory?.items) return [];
    if (resultFilter === 'all') return predHistory.items;
    return predHistory.items.filter((i) => i.result === resultFilter);
  }, [predHistory, resultFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredHistoryItems.length / pageSize));
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredHistoryItems.slice(start, start + pageSize);
  }, [filteredHistoryItems, currentPage]);

  // Reset page when filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [resultFilter, predHistory]);

  const toggleSubpane = (id: PaneKind, checked: boolean) => {
    setSubpanes((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  // Escape closes chart fullscreen.
  useEffect(() => {
    if (!chartFullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setChartFullscreen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [chartFullscreen]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="mx-auto max-w-[1400px] px-4 py-4 md:px-6 md:py-6 lg:px-8 space-y-6">
        {/* Breadcrumb & actions */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
            <Link href="/dashboard" className="hover:text-slate-700 dark:hover:text-slate-200 transition-colors">
              Dashboard
            </Link>
            <span className="text-slate-300 dark:text-slate-600">/</span>
            <Link href="/markets" className="hover:text-slate-700 dark:hover:text-slate-200 transition-colors">
              Markets
            </Link>
            <span className="text-slate-300 dark:text-slate-600">/</span>
            <span className="font-medium text-slate-900 dark:text-slate-100">{symbol}</span>
            <Badge variant="outline" className="ml-2 font-mono text-xs">
              {exchange}
            </Badge>
            {market && (
              <Badge variant="outline" className="font-mono text-xs">
                {market}
              </Badge>
            )}
          </nav>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleRefreshAll} disabled={refreshing}>
              <RefreshCw className={cn('h-4 w-4 mr-1.5', refreshing && 'animate-spin')} />
              {refreshing ? 'Refreshing' : 'Refresh'}
            </Button>
            <Link href={`/screener?symbol=${symbol}`}>
              <Button variant="ghost" size="sm">
                <Layers className="h-4 w-4 mr-1.5" />
                Screener
              </Button>
            </Link>
          </div>
        </div>

        {/* Header: Company name, Ticker, Exchange, Price, change, market status, last updated */}
        <Card className="overflow-hidden border-slate-200 dark:border-slate-800 shadow-sm">
          <CardContent className="p-4 md:p-6">
            {quoteLoading ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-3">
                    <Skeleton className="h-7 w-64" />
                    <Skeleton className="h-4 w-40" />
                    <div className="flex gap-2">
                      <Skeleton className="h-5 w-16 rounded-full" />
                      <Skeleton className="h-5 w-20 rounded-full" />
                    </div>
                  </div>
                  <div className="space-y-2 text-right">
                    <Skeleton className="h-8 w-32 ml-auto" />
                    <Skeleton className="h-4 w-24 ml-auto" />
                  </div>
                </div>
                <Skeleton className="h-4 w-full" />
              </div>
            ) : quoteError ? (
              <Alert variant="destructive" className="border-red-200 bg-red-50 dark:bg-red-950/30">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Unable to load quote for {symbol}</AlertTitle>
                <AlertDescription className="mt-1 flex flex-wrap items-center gap-3">
                  <span>{quoteError}</span>
                  <Button variant="outline" size="sm" onClick={fetchQuoteAndInstrument} className="h-7">
                    <RefreshCw className="h-3 w-3 mr-1" />
                    Retry
                  </Button>
                  <span className="text-xs text-muted-foreground">Exchange: {exchange} — try ?exchange=NASDAQ</span>
                </AlertDescription>
              </Alert>
            ) : quote ? (
              <div className="flex flex-col gap-4">
                <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                  {/* Left: identity */}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 truncate">
                        {companyName ? (
                          <>
                            {companyName}{' '}
                            <span className="font-mono font-semibold text-slate-500 dark:text-slate-400">({symbol})</span>
                          </>
                        ) : (
                          <span className="font-mono">{symbol}</span>
                        )}
                      </h1>
                      {!companyName && <span className="text-sm text-slate-500 dark:text-slate-400">— {exchange}</span>}
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-mono font-semibold border-slate-300 dark:border-slate-700">
                        {symbol}
                      </Badge>
                      <Badge variant="outline" className="font-medium">
                        {instrument?.exchange_code || instrument?.exchange?.code || exchange}
                      </Badge>
                      <Badge className={cn('border font-medium', getMarketStatusVariant(quote.marketStatus))}>{quote.marketStatus || 'unknown'}</Badge>
                      <FreshnessBadge
                        freshness={(quote as any).freshness}
                        sourceTimestamp={(quote as any).sourceTimestamp ?? quote.timestamp}
                        showAge
                      />
                      {instrument?.sector && (
                        <Badge variant="secondary" className="hidden sm:inline-flex">
                          {instrument.sector}
                        </Badge>
                      )}
                      {quote.currency && <span className="text-xs text-slate-500 dark:text-slate-400">{quote.currency}</span>}
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
                      <span className="inline-flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" />
                        Last updated: {formatTimestamp(quote.timestamp)}
                      </span>
                      {isQuoteStale && (
                        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
                          <ShieldAlert className="h-3.5 w-3.5" />
                          Data may be stale
                        </span>
                      )}
                      <span className="hidden md:inline text-slate-300 dark:text-slate-700">•</span>
                      <span>Prev close: {formatPrice(quote.previousClose, quote.currency || 'USD')}</span>
                      <span className="text-slate-300 dark:text-slate-700">•</span>
                      <span>
                        O {formatPrice(quote.open)} H {formatPrice(quote.high)} L {formatPrice(quote.low)} V {quote.volume?.toLocaleString()}
                      </span>
                    </div>
                  </div>

                  {/* Right: price */}
                  <div className="flex lg:flex-col items-baseline lg:items-end gap-3 lg:gap-1 shrink-0">
                    <div className="flex items-baseline gap-3">
                      <span className="text-3xl md:text-4xl font-bold tracking-tight tabular-nums text-slate-900 dark:text-slate-100">
                        {formatPrice(quote.price, quote.currency || 'USD')}
                      </span>
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-sm font-semibold tabular-nums border',
                          priceChangePositive
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900'
                            : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-900'
                        )}
                      >
                        {priceChangePositive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                        {formatPercent(quote.changePercent)} <span className="hidden sm:inline">({formatPrice(quote.change)})</span>
                      </span>
                    </div>
                    <div className="text-sm text-slate-500 dark:text-slate-400 lg:text-right">
                      <span className={cn(priceChangePositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                        {priceChangePositive ? '+' : ''}
                        {quote.change?.toFixed(2)} today
                      </span>
                      <span className="mx-2 hidden lg:inline text-slate-300">•</span>
                      <span className="hidden lg:inline">{quote.marketStatus === 'open' ? 'Market open' : `Market ${quote.marketStatus}`}</span>
                    </div>
                  </div>
                </div>

                {/* Stale / error inline */}
                {isQuoteStale && (
                  <Alert className="bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900">
                    <Info className="h-4 w-4 text-amber-600" />
                    <AlertTitle className="text-amber-800 dark:text-amber-200">
                      {normalizeFreshness((quote as any)?.freshness) === 'unavailable'
                        ? 'Data status unavailable'
                        : 'Stale price data'}
                    </AlertTitle>
                    <AlertDescription className="text-amber-700 dark:text-amber-300 text-xs">
                      This price is not current market data{quote && (quote as any).provider ? ` (source: ${(quote as any).provider})` : ''}. The last available point is from {formatTimestamp(quote.timestamp)}. Consider refreshing or checking exchange {exchange} trading hours.
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            ) : (
              <div className="py-8 text-center text-slate-500 dark:text-slate-400">
                <CircleDot className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No quote available for {symbol} on {exchange}</p>
                <p className="text-xs mt-1">Try a different exchange via ?exchange=NASDAQ</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Main grid: chart + prediction sidebar */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Chart */}
          <Card className="lg:col-span-8 border-slate-200 dark:border-slate-800 shadow-sm flex flex-col min-h-[540px]">
            <CardHeader className="pb-3 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-slate-700 dark:text-slate-300" />
                  <CardTitle className="text-base">Price Chart</CardTitle>
                  <Badge variant="outline" className="font-mono text-xs hidden sm:inline-flex">
                    {symbol} • {exchange}
                  </Badge>
                  {percentView && (
                    <Badge variant="secondary" className="text-[11px]">
                      %-change (rebased)
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" className="h-8 px-2" onClick={() => setShowVolume((v) => !v)} aria-pressed={showVolume}>
                    <Activity className="h-3.5 w-3.5 mr-1.5" />
                    {showVolume ? 'Hide vol' : 'Show vol'}
                  </Button>
                  <Button variant="ghost" size="sm" className="h-8 px-2" onClick={() => setChartFullscreen(true)}>
                    <Maximize2 className="h-3.5 w-3.5 mr-1.5" />
                    Expand
                  </Button>
                </div>
              </div>

              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <TimeframeSelector value={timeframe} onChange={setTimeframe} className="w-full sm:w-auto" />
                  <ChartTypeSelector value={chartType} onChange={setChartType} />
                </div>

                <div className="flex flex-wrap items-center gap-4 rounded-lg bg-slate-50 dark:bg-slate-900/50 p-3 border border-slate-200 dark:border-slate-800">
                  <div className="flex-1 min-w-[180px]">
                    <div className="text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1">
                      <Layers className="h-3 w-3" />
                      Overlays (same data)
                    </div>
                    <IndicatorSelector selected={indicators} onChange={setIndicators} />
                  </div>
                  <div className="hidden sm:block h-10 w-px bg-slate-200 dark:bg-slate-700" />
                  <div className="min-w-[200px]">
                    <div className="text-xs font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                      Oscillators (sub-charts)
                    </div>
                    <div className="flex flex-wrap gap-3">
                      {PANE_KINDS.map((id) => (
                        <label key={id} className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={subpanes.includes(id)}
                            onChange={(e) => toggleSubpane(id, e.target.checked)}
                            className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                          />
                          <span className="text-sm text-slate-700 dark:text-slate-300">{id}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
                  <label className="flex items-center gap-1.5 cursor-pointer text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={percentView}
                      onChange={(e) => setPercentView(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    %-change view
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-slate-700 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={showSwings}
                      onChange={(e) => setShowSwings(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    Swing H/L markers
                  </label>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    Bands use SMA 20 ± 2σ · RSI 14 · MACD 12/26/9 · Stoch 14/3 · ATR 14 · RelVol 20
                  </span>
                </div>
              </div>
            </CardHeader>

            <CardContent className="flex-1 flex flex-col pt-0">
              {historyLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-[340px] w-full rounded-lg" />
                  {showVolume && <Skeleton className="h-[80px] w-full rounded-lg" />}
                  <div className="flex gap-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-4 w-24" />
                  </div>
                </div>
              ) : historyError ? (
                <div className="flex-1 flex flex-col items-center justify-center py-12 text-center">
                  <AlertTriangle className="h-8 w-8 text-amber-500 mb-3" />
                  <h3 className="font-medium text-slate-900 dark:text-slate-100">Unable to load chart data</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-sm">{historyError}</p>
                  <p className="text-xs text-slate-400 mt-1">Historical data unavailable for this timeframe from the configured provider.</p>
                  <Button variant="outline" size="sm" className="mt-4" onClick={fetchHistory}>
                    <RefreshCw className="h-4 w-4 mr-1.5" />
                    Retry
                  </Button>
                </div>
              ) : history.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center py-12 text-center bg-slate-50 dark:bg-slate-900/30 rounded-lg border border-dashed border-slate-200 dark:border-slate-800">
                  <BarChart3 className="h-8 w-8 text-slate-400 mb-3" />
                  <h3 className="font-medium text-slate-900 dark:text-slate-100">No historical data</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">No price bars returned for {symbol} on {exchange} for {timeframe}.</p>
                  <Button variant="outline" size="sm" className="mt-4" onClick={fetchHistory}>
                    Try different timeframe
                  </Button>
                </div>
              ) : (
                <>
                  <ProChart
                    data={history}
                    chartType={chartType}
                    height={400}
                    showVolume={showVolume}
                    overlays={indicators}
                    percentView={percentView}
                    showSwings={showSwings}
                    currency={quote?.currency || 'USD'}
                    className="flex-1"
                  />
                  {subpanes.map((pane) => (
                    <div key={pane} className="mt-4 border-t border-slate-100 dark:border-slate-800 pt-3">
                      <IndicatorPane data={history} kind={pane} height={140} />
                    </div>
                  ))}
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400 border-t border-slate-100 dark:border-slate-800 pt-3">
                    <span>
                      {history.length} bars • {timeframe} • {percentView ? '%-change' : chartType}
                      {indicators.length > 0 && !percentView ? ` • ${indicators.join(', ')}` : ''}
                      {subpanes.length > 0 ? ` • ${subpanes.join(', ')}` : ''} • Volume {showVolume ? 'on' : 'off'}
                    </span>
                    <span className="hidden sm:inline">Drag to pan • Wheel to zoom • Hover for OHLCV</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Prediction + Factors sidebar */}
          <div className="lg:col-span-4 space-y-6 flex flex-col">
            {/* Prediction Card */}
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Brain className="h-4 w-4 text-violet-600 dark:text-violet-400" />
                      Prediction
                    </CardTitle>
                    <CardDescription className="mt-1 text-xs leading-relaxed">
                      Probabilistic estimate for the next {horizonLabel()} — not financial advice.
                    </CardDescription>
                  </div>
                  <Badge variant="outline" className="font-mono text-[11px] shrink-0">
                    {horizon.toUpperCase()}
                  </Badge>
                </div>

                <div className="flex items-center gap-2" title="v1.0 is a 1-day model; weekly/monthly labels are not offered">
                  <Badge variant="outline" className="font-mono text-[11px]">
                    1D · next trading day
                  </Badge>
                </div>
              </CardHeader>

              <CardContent className="space-y-4">
                {predictionLoading ? (
                  <div className="space-y-4">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-20 w-full" />
                    <div className="grid grid-cols-2 gap-3">
                      <Skeleton className="h-16 rounded-lg" />
                      <Skeleton className="h-16 rounded-lg" />
                    </div>
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : predictionUnavailable ? (
                  <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/30 p-6 text-center">
                    <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
                      <ShieldAlert className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                    </div>
                    <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">Prediction unavailable</h3>
                    <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">No model output available for {symbol} on {exchange} for horizon {horizon.toUpperCase()}. The instrument may be newly listed, illiquid, or pending the next inference cycle.</p>
                    <div className="mt-4 flex flex-col gap-2">
                      <Button variant="outline" size="sm" onClick={fetchPredictions} className="w-full">
                        <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                        Retry
                      </Button>
                      <p className="text-[11px] text-slate-400">Ensemble v1.0 • Updates at market close</p>
                    </div>
                  </div>
                ) : predictionError ? (
                  <Alert variant="destructive" className="py-3">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle className="text-sm">Prediction error</AlertTitle>
                    <AlertDescription className="flex items-center gap-2 text-xs">
                      <span className="truncate">{predictionError}</span>
                      <Button variant="outline" size="sm" className="h-7 shrink-0" onClick={fetchPredictions}>
                        Retry
                      </Button>
                    </AlertDescription>
                  </Alert>
                ) : prediction ? (
                  <>
                    {/* Direction badge */}
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-semibold tracking-widest text-slate-500 dark:text-slate-400 uppercase">Next {horizonLabel()}</div>
                      <Badge
                        className={cn(
                          'gap-1 font-semibold border text-xs',
                          prediction.direction === 'up' && 'bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300',
                          prediction.direction === 'down' && 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300',
                          prediction.direction === 'neutral' && 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300'
                        )}
                      >
                        {prediction.direction === 'up' && <TrendingUp className="h-3 w-3" />}
                        {prediction.direction === 'down' && <TrendingDown className="h-3 w-3" />}
                        {prediction.direction === 'neutral' && <Minus className="h-3 w-3" />}
                        {prediction.direction.toUpperCase()}
                      </Badge>
                    </div>

                    <ProbabilityBarGroup probabilities={prediction.probabilities} />

                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded-lg bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 p-3 text-center">
                        <div className={cn('text-lg font-bold tabular-nums', prediction.expectedReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                          {prediction.expectedReturn >= 0 ? '+' : ''}
                          {prediction.expectedReturn.toFixed(2)}%
                        </div>
                        <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">Expected return</div>
                      </div>
                      <div className="rounded-lg bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 p-3 text-center">
                        <div className="text-lg font-bold tabular-nums text-slate-900 dark:text-white">{prediction.confidence == null ? '—' : `${prediction.confidence}/100`}</div>
                        <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">Signal separation</div>
                      </div>
                    </div>

                    <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 bg-white dark:bg-slate-900">
                      <div className="text-xs font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                        <Target className="h-3.5 w-3.5" />
                        Expected range
                      </div>
                      <div className="mt-1 flex items-baseline justify-between">
                        <span className="font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                          {formatPercent(prediction.expectedRange.low)} → {formatPercent(prediction.expectedRange.high)}
                        </span>
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">1σ</span>
                      </div>
                      <div className="mt-2 h-1.5 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden flex">
                        <div className="bg-slate-300 dark:bg-slate-700" style={{ width: '30%' }} />
                        <div className="bg-violet-500" style={{ width: '40%' }} />
                        <div className="bg-slate-300 dark:bg-slate-700" style={{ width: '30%' }} />
                      </div>
                    </div>

                    <div className="space-y-1.5 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400">
                          <Brain className="h-3 w-3" /> Model
                        </span>
                        <span className="font-medium text-slate-900 dark:text-slate-100">{prediction.modelVersion}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400">
                          <Calendar className="h-3 w-3" /> Horizon
                        </span>
                        <span className="font-medium text-slate-900 dark:text-slate-100 capitalize">{horizonLabel()}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400">
                          <Clock className="h-3 w-3" /> Data
                        </span>
                        <span className="font-medium text-slate-900 dark:text-slate-100 text-[11px]">{formatTimestamp(prediction.dataTimestamp)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1 text-slate-500 dark:text-slate-400">Signal separation</span>
                        <span className="font-mono font-medium text-slate-900 dark:text-slate-100">
                          {prediction.confidence == null ? 'unavailable' : `${prediction.confidence}/100 • ${prediction.noClearEdge ? 'No clear edge' : prediction.confidence >= 70 ? 'High' : prediction.confidence >= 50 ? 'Moderate' : 'Low'}`}
                          {prediction.topProbability != null ? ` · top p=${prediction.topProbability.toFixed(3)}` : ''}
                        </span>
                      </div>
                      {prediction.noClearEdge && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                          NO CLEAR EDGE — top probability below {NO_EDGE_THRESHOLD.toFixed(2)}. Treat direction as uncertain; size positions accordingly or stand aside.
                        </div>
                      )}
                      {isStaleTimestamp(prediction.dataTimestamp, 60 * 24) && (
                        <div className="flex items-center gap-1 text-amber-600 dark:text-amber-400 pt-1">
                          <ShieldAlert className="h-3 w-3" />
                          <span>Data timestamp may be stale — model may be pending refresh.</span>
                        </div>
                      )}
                    </div>

                    <Alert className="bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-800 py-2.5">
                      <Info className="h-3.5 w-3.5 text-slate-500" />
                      <AlertDescription className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                        Probabilistic forecast based on historical patterns. Does not imply certainty or constitute investment advice. Past performance does not guarantee future results. Consider risk, diversification, and your investment objectives.
                      </AlertDescription>
                    </Alert>
                  </>
                ) : null}
              </CardContent>
            </Card>

            <PredictionExplanationPanel
              predictionId={
                prediction?.raw?.id ??
                prediction?.raw?.prediction_id ??
                prediction?.raw?.predictionId ??
                null
              }
            />

            <RsiIntelligencePanel symbol={symbol} exchange={exchange} />

            {/* Factors */}
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Layers className="h-4 w-4 text-slate-700 dark:text-slate-300" />
                  Why this prediction
                </CardTitle>
                <CardDescription className="text-xs">Factor analysis supplied by API • {horizon.toUpperCase()} horizon</CardDescription>
              </CardHeader>
              <CardContent>
                {factorsLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                ) : factorsError ? (
                  <Alert className="py-2">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle className="text-xs">Unable to load factors</AlertTitle>
                    <AlertDescription className="text-xs flex items-center gap-2">
                      <span className="truncate">{factorsError}</span>
                      <Button size="sm" variant="outline" className="h-6" onClick={fetchPredictions}>
                        Retry
                      </Button>
                    </AlertDescription>
                  </Alert>
                ) : !factors || (factors.positive.length === 0 && factors.neutral.length === 0 && factors.negative.length === 0) ? (
                  <div className="py-6 text-center text-sm text-slate-500 dark:text-slate-400">
                    <Info className="h-6 w-6 mx-auto mb-2 opacity-40" />
                    No factor breakdown available for this prediction.
                    <p className="text-xs mt-1">Factors are generated from the model&apos;s feature snapshot (RSI, MACD, moving averages, volume, volatility).</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-xs font-semibold tracking-wide uppercase text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300">+</span>
                        Positive factors
                      </h4>
                      {factors.positive.length ? (
                        <ul className="mt-2 space-y-1.5">
                          {factors.positive.map((f, i) => (
                            <li key={`pos-${i}`} className="flex gap-2 text-sm leading-snug text-slate-700 dark:text-slate-300">
                              <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
                              <span>{f}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">No positive factors flagged for this horizon.</p>
                      )}
                    </div>

                    <div>
                      <h4 className="text-xs font-semibold tracking-wide uppercase text-amber-700 dark:text-amber-300 flex items-center gap-1.5">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">~</span>
                        Neutral factors
                      </h4>
                      {factors.neutral.length ? (
                        <ul className="mt-2 space-y-1.5">
                          {factors.neutral.map((f, i) => (
                            <li key={`neu-${i}`} className="flex gap-2 text-sm leading-snug text-slate-700 dark:text-slate-300">
                              <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-amber-500 shrink-0" />
                              <span>{f}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">No neutral factors.</p>
                      )}
                    </div>

                    <div>
                      <h4 className="text-xs font-semibold tracking-wide uppercase text-red-700 dark:text-red-300 flex items-center gap-1.5">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300">−</span>
                        Negative factors
                      </h4>
                      {factors.negative.length ? (
                        <ul className="mt-2 space-y-1.5">
                          {factors.negative.map((f, i) => (
                            <li key={`neg-${i}`} className="flex gap-2 text-sm leading-snug text-slate-700 dark:text-slate-300">
                              <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                              <span>{f}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">No negative factors flagged.</p>
                      )}
                    </div>

                    <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400 pt-2 border-t border-slate-100 dark:border-slate-800">
                      Factors are descriptive explanations derived from technical features. They do not imply causality and should be weighed alongside fundamentals and risk management.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Prediction History */}
        <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-slate-700 dark:text-slate-300" />
                  Prediction History
                </CardTitle>
                <CardDescription>
                  {symbol} • {exchange} • Horizon {horizon.toUpperCase()} • {predHistory?.items.length ?? 0} records
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={fetchPredictions} disabled={predHistoryLoading}>
                  <RefreshCw className={cn('h-4 w-4 mr-1.5', predHistoryLoading && 'animate-spin')} />
                  Refresh
                </Button>
              </div>
            </div>

            {/* Summary */}
            {predHistoryLoading ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 rounded-lg" />
                ))}
              </div>
            ) : predHistory ? (
              <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Total predictions</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{predHistory.summary.totalPredictions}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    {predHistory.summary.completedCount} evaluated · {predHistory.summary.pendingCount} pending
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-emerald-50 dark:bg-emerald-950/20 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Correct</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums text-emerald-700 dark:text-emerald-300">{predHistory.summary.correctPredictions}</div>
                  <div className="text-xs text-emerald-600 dark:text-emerald-400">
                    of {predHistory.summary.directionalCount} directional
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-violet-50 dark:bg-violet-950/20 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-violet-700 dark:text-violet-300">Accuracy</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums text-violet-700 dark:text-violet-300">
                    {predHistory.summary.accuracy === null ? '—' : `${Number(predHistory.summary.accuracy).toFixed(1)}%`}
                  </div>
                  <div className="text-xs text-violet-600 dark:text-violet-400">
                    {predHistory.summary.accuracy === null
                      ? `insufficient sample (need ${predHistory.summary.minimumSample})`
                      : predHistory.summary.accuracyReliable
                        ? `directional · 95% CI ${predHistory.summary.confidenceIntervalLower ?? '—'}–${predHistory.summary.confidenceIntervalUpper ?? '—'}%`
                        : 'directional · low sample, unreliable'}
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 p-3">
                  <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Avg return</div>
                  <div className={cn('mt-1 text-2xl font-bold tabular-nums', predHistory.summary.averageReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                    {predHistory.summary.averageReturn >= 0 ? '+' : ''}
                    {Number(predHistory.summary.averageReturn).toFixed(2)}%
                  </div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">per prediction</div>
                </div>
              </div>
              <p className="pt-1 text-xs text-slate-500 dark:text-slate-400">
                {predHistory.summary.pendingCount} pending prediction{predHistory.summary.pendingCount === 1 ? '' : 's'} excluded from accuracy.
                {' '}{predHistory.summary.neutralPredictions} neutral prediction{predHistory.summary.neutralPredictions === 1 ? '' : 's'} reported separately
                ({predHistory.summary.neutralCorrect} realised neutral) and never counted as directional wins.
              </p>
              </>
            ) : null}
          </CardHeader>

          <CardContent className="space-y-4">
            {/* Filters */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Tabs value={resultFilter} onValueChange={(v) => setResultFilter(v as any)}>
                <TabsList>
                  <TabsTrigger value="all" className="text-xs">
                    All
                  </TabsTrigger>
                  <TabsTrigger value="correct" className="text-xs">
                    Correct {predHistory ? `(${predHistory.items.filter((i) => i.result === 'correct').length})` : ''}
                  </TabsTrigger>
                  <TabsTrigger value="incorrect" className="text-xs">
                    Incorrect {predHistory ? `(${predHistory.items.filter((i) => i.result === 'incorrect').length})` : ''}
                  </TabsTrigger>
                  <TabsTrigger value="pending" className="text-xs">
                    Pending {predHistory ? `(${predHistory.items.filter((i) => i.result === 'pending').length})` : ''}
                  </TabsTrigger>
                </TabsList>
              </Tabs>

              <div className="text-xs text-slate-500 dark:text-slate-400">
                {filteredHistoryItems.length} {filteredHistoryItems.length === 1 ? 'record' : 'records'} • Page {currentPage} of {totalPages}
              </div>
            </div>

            {/* Table */}
            {predHistoryLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : predHistoryError ? (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Failed to load history</AlertTitle>
                <AlertDescription className="flex items-center gap-2">
                  <span>{predHistoryError}</span>
                  <Button variant="outline" size="sm" onClick={fetchPredictions}>
                    Retry
                  </Button>
                </AlertDescription>
              </Alert>
            ) : filteredHistoryItems.length === 0 ? (
              <div className="py-12 text-center border border-dashed border-slate-200 dark:border-slate-800 rounded-lg bg-slate-50 dark:bg-slate-900/30">
                <Calendar className="h-8 w-8 mx-auto text-slate-400 mb-3" />
                <h3 className="font-medium text-slate-900 dark:text-slate-100">No predictions match filter</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                  {predHistory?.items.length === 0 ? `No historical predictions for ${symbol} yet.` : `No ${resultFilter} predictions.`}
                </p>
                {resultFilter !== 'all' && (
                  <Button variant="outline" size="sm" className="mt-3" onClick={() => setResultFilter('all')}>
                    Show all
                  </Button>
                )}
              </div>
            ) : (
              <>
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden">
                  <Table>
                    <TableHeader className="bg-slate-50 dark:bg-slate-900/50">
                      <TableRow>
                        <TableHead className="font-semibold">Date</TableHead>
                        <TableHead className="font-semibold">Prediction</TableHead>
                        <TableHead className="font-semibold text-right">UP prob</TableHead>
                        <TableHead className="font-semibold text-right">Expected</TableHead>
                        <TableHead className="font-semibold text-right">Actual</TableHead>
                        <TableHead className="font-semibold text-center">Result</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedItems.map((item, idx) => (
                        <TableRow key={`${item.date}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-slate-900/30">
                          <TableCell className="font-mono text-xs tabular-nums whitespace-nowrap">{item.date ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={cn(
                                'font-semibold text-xs border gap-1',
                                item.prediction === 'up' && 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300',
                                item.prediction === 'down' && 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300',
                                item.prediction === 'neutral' && 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300'
                              )}
                            >
                              {item.prediction === 'up' && <TrendingUp className="h-3 w-3" />}
                              {item.prediction === 'down' && <TrendingDown className="h-3 w-3" />}
                              {item.prediction === 'neutral' && <Minus className="h-3 w-3" />}
                              {item.prediction.toUpperCase()}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right tabular-nums font-medium">{item.upProbability}%</TableCell>
                          <TableCell className={cn('text-right tabular-nums font-medium', item.expectedReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                            {item.expectedReturn >= 0 ? '+' : ''}
                            {item.expectedReturn.toFixed(2)}%
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {item.actualReturn === null || item.actualReturn === undefined ? (
                              <span className="text-slate-400">—</span>
                            ) : (
                              <span className={cn('font-medium', (item.actualReturn as number) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                                {(item.actualReturn as number) >= 0 ? '+' : ''}
                                {(item.actualReturn as number).toFixed(2)}%
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="text-center">
                            {item.result === 'correct' && <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 border border-emerald-200">Correct</Badge>}
                            {item.result === 'incorrect' && <Badge className="bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 border border-red-200">Incorrect</Badge>}
                            {item.result === 'neutral' && <Badge variant="outline" className="bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800/40 dark:text-slate-300">Neutral (excluded)</Badge>}
                            {item.result === 'pending' && <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300">Pending</Badge>}
                            {!item.result && <span className="text-slate-400 text-xs">—</span>}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {/* Pagination */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    Showing {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, filteredHistoryItems.length)} of {filteredHistoryItems.length}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="outline" size="sm" disabled={currentPage === 1} onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}>
                      <ChevronLeft className="h-4 w-4" />
                      Prev
                    </Button>
                    {Array.from({ length: Math.min(totalPages, 5) }).map((_, i) => {
                      let pageNum: number;
                      if (totalPages <= 5) pageNum = i + 1;
                      else if (currentPage <= 3) pageNum = i + 1;
                      else if (currentPage >= totalPages - 2) pageNum = totalPages - 4 + i;
                      else pageNum = currentPage - 2 + i;
                      return (
                        <Button
                          key={pageNum}
                          variant={currentPage === pageNum ? 'default' : 'outline'}
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={() => setCurrentPage(pageNum)}
                        >
                          {pageNum}
                        </Button>
                      );
                    })}
                    <Button variant="outline" size="sm" disabled={currentPage === totalPages} onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}>
                      Next
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Footer disclaimer */}
        <div className="rounded-lg bg-slate-900 text-slate-300 px-4 py-3 text-xs leading-relaxed dark:bg-slate-900">
          <p className="font-medium text-white flex items-center gap-1.5">
            <Info className="h-3.5 w-3.5" />
            Important disclosure
          </p>
          <p className="mt-1 text-slate-400">
            This page presents probabilistic model outputs for informational and educational purposes only. It does not constitute investment advice, recommendation, or guarantee of future performance. Predictions are based on historical data and statistical modeling, which may not reflect future market conditions. Trade at your own risk; consider professional advice.
          </p>
        </div>
      </div>

      {/* Fullscreen chart overlay */}
      {chartFullscreen && (
        <div
          className="fixed inset-0 z-[90] flex flex-col bg-white dark:bg-slate-950"
          role="dialog"
          aria-modal="true"
          aria-label={`${symbol} chart fullscreen`}
        >
          <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 px-4 py-2">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-mono font-bold">{symbol}</span>
              <span className="text-slate-500">{exchange} · {timeframe} · {percentView ? '%-change' : chartType}</span>
            </div>
            <div className="flex items-center gap-2">
              <ChartTypeSelector value={chartType} onChange={setChartType} />
              <Button variant="ghost" size="sm" onClick={() => setChartFullscreen(false)} aria-label="Exit fullscreen">
                <Minimize2 className="h-4 w-4 mr-1" /> Exit (esc)
              </Button>
            </div>
          </div>
          <div className="flex-1 overflow-auto p-4">
            <ProChart
              data={history}
              chartType={chartType}
              height={Math.max(420, typeof window !== 'undefined' ? window.innerHeight - 260 : 560)}
              showVolume={showVolume}
              overlays={indicators}
              percentView={percentView}
              showSwings={showSwings}
              currency={quote?.currency || 'USD'}
            />
            {subpanes.map((pane) => (
              <div key={pane} className="mt-4 border-t border-slate-200 dark:border-slate-800 pt-3">
                <IndicatorPane data={history} kind={pane} height={140} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
