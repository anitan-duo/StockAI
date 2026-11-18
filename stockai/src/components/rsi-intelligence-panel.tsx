'use client';

/**
 * RSI intelligence panel.
 *
 * RSI is displayed as technical context only. E075 found no incremental
 * out-of-time predictive information over the existing feature set, so this
 * panel never presents RSI as a trading instruction or a model change.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import {
  agreementLabel,
  rsiPolyline,
  rsiTone,
  yForRsi,
  type RsiAnalysis,
} from '@/lib/rsiIntelligence';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Info,
  ShieldQuestion,
  TrendingDown,
  TrendingUp,
  Minus,
} from 'lucide-react';

type Props = {
  symbol: string;
  exchange: string;
  className?: string;
};

function number(value: number | null | undefined, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function signed(value: number | null | undefined, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(digits)}` : '—';
}

function trendIcon(trend: string) {
  if (trend === 'rising') return <TrendingUp className="h-3.5 w-3.5" />;
  if (trend === 'falling') return <TrendingDown className="h-3.5 w-3.5" />;
  return <Minus className="h-3.5 w-3.5" />;
}

export function RsiIntelligencePanel({ symbol, exchange, className }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<RsiAnalysis | null>(null);
  const requestRef = useRef(0);

  const load = useCallback(async () => {
    if (!symbol || !exchange) return;
    const request = ++requestRef.current;
    setLoading(true);
    setError(null);
    try {
      const payload = (await api.getStockRsi(symbol, exchange)) as RsiAnalysis;
      if (request !== requestRef.current) return;
      if (payload.symbol !== symbol.toUpperCase() || payload.exchange !== exchange.toUpperCase()) {
        setPayload(null);
        setError('RSI response did not match the displayed instrument.');
        return;
      }
      setPayload(payload);
    } catch (e: unknown) {
      if (request !== requestRef.current) return;
      setPayload(null);
      setError(e instanceof Error ? e.message : 'RSI analysis unavailable');
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }, [symbol, exchange]);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [open, symbol, exchange, load]);

  const data = payload && payload.symbol === symbol.toUpperCase() && payload.exchange === exchange.toUpperCase() ? payload : null;
  const rsi14 = data?.current?.rsi_14 ?? null;
  const spark = data ? rsiPolyline(data.series.slice(-90), 300, 80, 'rsi_14') : '';
  const latest = data?.series?.[data.series.length - 1];

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <Activity className="h-4 w-4 text-sky-600 dark:text-sky-300" />
        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">RSI Intelligence</span>
        {data ? (
          <>
            <Badge className={cn('ml-1 gap-1 border text-[10px]', rsiTone(data.zone))}>
              {number(rsi14)} · {data.zone}
            </Badge>
            <Badge variant="outline" className="text-[10px]">context only</Badge>
          </>
        ) : (
          <Badge variant="outline" className="ml-1 text-[10px]">momentum context</Badge>
        )}
        <span className="ml-auto text-slate-500 dark:text-slate-400">
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-slate-100 px-4 py-4 dark:border-slate-800">
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ) : error ? (
            <Alert className="py-2">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle className="text-xs">RSI analysis unavailable</AlertTitle>
              <AlertDescription className="space-y-2 text-xs">
                <p>{error}</p>
                <Button size="sm" variant="outline" className="h-6" onClick={() => void load()}>
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : data ? (
            <>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-slate-500 dark:text-slate-400">
                  {data.bar_count} daily bars · through {data.data_timestamp.slice(0, 10)}
                </span>
                <Badge variant="outline" className="ml-auto gap-1 text-[10px]">
                  {trendIcon(data.trend)} {data.trend}
                </Badge>
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[10px]',
                    data.agreement.status === 'agrees' && 'border-emerald-300 text-emerald-700 dark:text-emerald-300',
                    data.agreement.status === 'disagrees' && 'border-amber-300 text-amber-700 dark:text-amber-300',
                  )}
                >
                  {agreementLabel(data.agreement.status)}
                </Badge>
              </div>

              <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-2 dark:border-slate-800 dark:bg-slate-950/40">
                <svg viewBox="0 0 300 80" className="h-24 w-full" role="img" aria-label={`RSI 14 history for ${data.symbol}`}>
                  <line x1="0" y1={yForRsi(70)} x2="300" y2={yForRsi(70)} className="stroke-rose-300 dark:stroke-rose-700" strokeDasharray="3 3" strokeWidth="0.7" />
                  <line x1="0" y1={yForRsi(50)} x2="300" y2={yForRsi(50)} className="stroke-slate-300 dark:stroke-slate-700" strokeWidth="0.5" />
                  <line x1="0" y1={yForRsi(30)} x2="300" y2={yForRsi(30)} className="stroke-sky-300 dark:stroke-sky-700" strokeDasharray="3 3" strokeWidth="0.7" />
                  {spark ? (
                    <polyline points={spark} fill="none" className="stroke-sky-600 dark:stroke-sky-300" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
                  ) : null}
                </svg>
                <div className="flex justify-between text-[9px] text-slate-400">
                  <span>70 overbought</span>
                  <span>30 oversold</span>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center">
                {data.periods.map((period) => (
                  <div key={period} className="rounded-lg border border-slate-100 p-2 dark:border-slate-800">
                    <div className="text-[10px] uppercase tracking-wide text-slate-500">RSI {period}</div>
                    <div className="font-mono text-base font-semibold text-slate-900 dark:text-slate-100">
                      {number(data.current[`rsi_${period}`])}
                    </div>
                    <div className="font-mono text-[10px] text-slate-500">
                      5d {signed(data.slopes_5d[`slope_5d_${period}`])}
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">{data.interpretation}</p>

              <div className="grid gap-3 text-xs sm:grid-cols-2">
                <div className="rounded-lg border border-slate-100 p-2 dark:border-slate-800">
                  <div className="mb-1 font-semibold text-slate-700 dark:text-slate-300">Regime & persistence</div>
                  <div className="space-y-0.5 text-slate-600 dark:text-slate-400">
                    <p>Overbought streak: {data.persistence.overbought_days} day(s)</p>
                    <p>Oversold streak: {data.persistence.oversold_days} day(s)</p>
                    <p>High volatility: {data.regime.high_volatility ? 'yes' : 'no'} · 20d vol {number(data.regime.vol_20d)}%</p>
                    <p>50/200 uptrend: {data.regime.uptrend_50_200 ? 'yes' : 'no'}</p>
                  </div>
                </div>
                <div className="rounded-lg border border-slate-100 p-2 dark:border-slate-800">
                  <div className="mb-1 font-semibold text-slate-700 dark:text-slate-300">Divergence & crossings</div>
                  <div className="space-y-0.5 text-slate-600 dark:text-slate-400">
                    <p>Divergence: {data.divergence.kind} — {data.divergence.reason}</p>
                    {data.crossovers.slice(0, 3).map((c) => (
                      <p key={c.level}>
                        RSI {c.level}: {c.direction}
                        {c.bars_ago != null ? ` ${c.bars_ago} bar(s) ago` : ''}
                      </p>
                    ))}
                  </div>
                </div>
              </div>

              <p className="text-xs text-slate-600 dark:text-slate-400">{data.agreement.reason}</p>

              <Alert className="py-2">
                <Info className="h-4 w-4" />
                <AlertTitle className="text-xs">How to read this</AlertTitle>
                <AlertDescription className="space-y-1 text-[11px] leading-relaxed">
                  <p>{data.method}.</p>
                  <p className="font-medium">
                    Independent out-of-time research (E075) found no incremental predictive information from RSI over the
                    existing feature set. RSI is context, not a trading signal or a change to the v1.0 model.
                  </p>
                  <p>Overbought does not mean sell; oversold does not mean buy. {latest ? `Latest close ${latest.close ?? '—'}.` : ''}</p>
                </AlertDescription>
              </Alert>

              {data.caveats.length > 0 && (
                <div>
                  <h4 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                    <ShieldQuestion className="h-3.5 w-3.5" /> Limitations
                  </h4>
                  <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-400">
                    {data.caveats.map((c, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
