'use client';

/**
 * Read-only analytics workspace.
 *
 * Every number comes from matured PredictionOutcome rows via
 * /api/v1/analytics/performance. Pending predictions are shown separately and
 * never counted as performance. Nothing here retrains or promotes a model.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { pct, num, calibrationGap, calibrationVerdict, type CalibrationBin } from '@/lib/learningLoop';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Info,
  Lock,
  RefreshCw,
  Search,
  ShieldCheck,
  XCircle,
} from 'lucide-react';

type Cell = { n: number; accuracy?: number; brier?: number; directional_n?: number; neutral_n?: number; reliable?: boolean; confidence_interval?: { lower: number; upper: number; level: number } | null };
type Recent = {
  symbol: string;
  exchange: string;
  predicted: string;
  actual: string;
  correct: boolean;
  directional?: boolean;
  counted_in_accuracy?: boolean;
  confidence: number;
  brier: number;
  evaluated_at: string;
  version: string;
};

type Analytics = {
  generated_at: string;
  scope: { days: number; symbol: string | null; exchange: string | null; since: string; confirmed_only: boolean };
  summary: {
    n: number;
    minimum_sample: number;
    sufficient_sample: boolean;
    accuracy?: number | null;
    brier?: number;
    log_loss?: number;
    ece?: number | null;
    latency_hours_median?: number;
    coverage_note?: string;
    directional_n?: number;
    directional_correct?: number;
    neutral_n?: number;
    neutral_correct?: number;
    reliable?: boolean;
    confidence_interval?: { lower: number; upper: number; level: number } | null;
    scoring_policy?: string;
  };
  calibration: { n: number; bins: CalibrationBin[]; ece: number | null };
  by_symbol: Record<string, Cell>;
  by_direction: Record<string, Cell>;
  by_version: Record<string, Cell>;
  by_market: Record<string, Cell>;
  by_regime: Record<string, { on?: Cell; off?: Cell }>;
  pending_outcomes: number;
  recent_outcomes: Recent[];
  caveats: string[];
};

function ScopeTable({ title, rows, limit = 8 }: { title: string; rows: Record<string, Cell>; limit?: number }) {
  const entries = Object.entries(rows).sort((a, b) => b[1].n - a[1].n).slice(0, limit);
  return (
    <div className="rounded-lg border border-border p-2 text-xs">
      <div className="mb-1 font-semibold">{title}</div>
      {entries.length === 0 ? (
        <p className="py-2 text-muted-foreground">No matured outcomes in this scope.</p>
      ) : (
        entries.map(([name, cell]) => (
          <div key={name} className="flex justify-between gap-2 py-0.5">
            <span className="truncate font-mono">{name}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              n {cell.n} · acc {pct(cell.accuracy)} · brier {num(cell.brier)}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Analytics | null>(null);
  const [days, setDays] = useState('90');
  const [symbol, setSymbol] = useState('');
  const [exchange, setExchange] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    if (!api.isAuthenticated()) {
      setAuthed(false);
      setLoading(false);
      return;
    }
    try {
      const me = await api.getMe().catch(() => null);
      if (!me) {
        setAuthed(false);
        return;
      }
      setAuthed(true);
      const payload = (await api.getAnalyticsPerformance({
        days: Number(days),
        symbol: symbol.trim() || undefined,
        exchange: exchange.trim() || undefined,
      })) as Analytics;
      setData(payload);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Analytics unavailable');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, symbol, exchange]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const bins = data?.calibration.bins ?? [];
  const mature = data?.summary.n ?? 0;
  const maxBin = Math.max(1, ...bins.map((b) => b.n));

  if (authed === false) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="h-5 w-5" /> Sign in for analytics
            </CardTitle>
            <CardDescription>
              Performance analytics use confirmed prediction outcomes and require an account.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/login">Sign in</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BarChart3 className="h-6 w-6" /> Signal Analytics
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Confirmed performance from matured outcomes. Read-only; no model is retrained or promoted here.
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Select value={days} onValueChange={(v) => setDays(v ?? '90')}>
            <SelectTrigger className="h-8 w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
              <SelectItem value="180">180 days</SelectItem>
              <SelectItem value="365">365 days</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative">
            <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
            <Input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="Symbol"
              className="h-8 w-28 pl-8 font-mono"
            />
          </div>
          <Input
            value={exchange}
            onChange={(e) => setExchange(e.target.value.toUpperCase())}
            placeholder="Exchange"
            className="h-8 w-28 font-mono"
          />
          <Button size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={cn('mr-1 h-3.5 w-3.5', loading && 'animate-spin')} /> Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : error ? (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Analytics unavailable</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>{error}</p>
            <Button size="sm" variant="outline" onClick={() => void load()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Matured outcomes" value={String(mature)} />
            <Stat label="Directional accuracy" value={pct(data.summary.accuracy)} />
            <Stat label="ECE calibration" value={num(data.summary.ece, 3)} />
            <Stat label="Per-class Brier" value={num(data.summary.brier, 3)} />
            <Stat label="Log loss" value={num(data.summary.log_loss, 3)} />
            <Stat label="Median resolution" value={data.summary.latency_hours_median != null ? `${data.summary.latency_hours_median.toFixed(1)} h` : '—'} />
            <Stat label="Pending outcomes" value={String(data.pending_outcomes)} />
            <Stat label="Directional calls" value={String(data.summary.directional_n ?? '—')} />
            <Stat label="Neutral (excluded)" value={`${data.summary.neutral_n ?? 0} / ${data.summary.neutral_correct ?? 0} neutral`} />
            <Stat label="Sample floor" value={String(data.summary.minimum_sample)} />
          </div>

          {data.summary.confidence_interval && (
            <p className="text-xs text-muted-foreground">
              95% confidence interval for directional accuracy:{' '}
              {pct(data.summary.confidence_interval.lower)}–{pct(data.summary.confidence_interval.upper)}.
              {' '}Neutral predictions are reported separately and never counted as directional wins.
            </p>
          )}

          {!data.summary.sufficient_sample && (
            <Alert className="border-amber-300">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle className="text-xs">Sample too small for conclusions</AlertTitle>
              <AlertDescription className="text-xs">
                {mature} matured outcomes in this scope; the minimum is {data.summary.minimum_sample}. Treat every
                number above as provisional and do not infer edge.
              </AlertDescription>
            </Alert>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Reliability: stated confidence vs observed</CardTitle>
                <CardDescription>{calibrationVerdict(data.summary.ece, mature)}</CardDescription>
              </CardHeader>
              <CardContent>
                {bins.length === 0 ? (
                  <p className="py-4 text-center text-sm text-muted-foreground">No matured outcomes in this scope.</p>
                ) : (
                  <div className="space-y-2">
                    {bins.map((b) => {
                      const gap = calibrationGap(b);
                      return (
                        <div key={b.bin} className="space-y-1">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-mono">{b.bin}</span>
                            <span className="tabular-nums text-muted-foreground">
                              n {b.n} · observed {pct(b.observed_accuracy)} · gap{' '}
                              {gap == null ? '—' : `${gap >= 0 ? '+' : ''}${(gap * 100).toFixed(1)} pts`}
                            </span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-muted">
                            <div
                              className={cn('h-full rounded-full', gap != null && Math.abs(gap) > 0.08 ? 'bg-amber-500' : 'bg-sky-500')}
                              style={{ width: `${Math.max(2, (b.n / maxBin) * 100)}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Recent confirmed outcomes</CardTitle>
                <CardDescription>Newest first; pending predictions are excluded from accuracy.</CardDescription>
              </CardHeader>
              <CardContent className="max-h-80 overflow-auto">
                {data.recent_outcomes.length === 0 ? (
                  <p className="py-4 text-center text-sm text-muted-foreground">No confirmed outcomes yet.</p>
                ) : (
                  <table className="w-full text-left text-xs">
                    <thead className="text-[10px] uppercase text-muted-foreground">
                      <tr>
                        <th className="py-1">Symbol</th>
                        <th className="py-1">Pred → actual</th>
                        <th className="py-1 text-right">Conf.</th>
                        <th className="py-1 text-right">Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_outcomes.map((r, i) => (
                        <tr key={`${r.symbol}-${r.evaluated_at}-${i}`} className="border-t border-border/60">
                          <td className="py-1.5 font-mono">{r.symbol}</td>
                          <td className="py-1.5 text-muted-foreground">
                            {r.predicted} → {r.actual}
                          </td>
                          <td className="py-1.5 text-right tabular-nums">{pct(r.confidence)}</td>
                          <td className="py-1.5 text-right">
                            {r.directional === false ? (
                              <span className="text-[10px] text-muted-foreground">neutral · excluded</span>
                            ) : r.correct ? (
                              <CheckCircle2 className="ml-auto h-3.5 w-3.5 text-emerald-600" />
                            ) : (
                              <XCircle className="ml-auto h-3.5 w-3.5 text-red-600" />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            <ScopeTable title="By symbol" rows={data.by_symbol} limit={10} />
            <ScopeTable title="By predicted direction" rows={data.by_direction} />
            <ScopeTable title="By model version" rows={data.by_version} />
            <ScopeTable title="By market" rows={data.by_market} />
          </div>

          {Object.keys(data.by_regime).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Regime performance (observational)</CardTitle>
                <CardDescription>Not causal: regimes are observed, not randomized.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-2 text-xs sm:grid-cols-2">
                {Object.entries(data.by_regime).map(([name, cell]) => (
                  <div key={name} className="rounded-lg border border-border p-2">
                    <div className="mb-1 font-semibold">{name.replaceAll('_', ' ')}</div>
                    <div className="flex justify-between">
                      <span>On</span>
                      <span className="tabular-nums text-muted-foreground">n {cell.on?.n ?? 0} · acc {pct(cell.on?.accuracy)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Off</span>
                      <span className="tabular-nums text-muted-foreground">n {cell.off?.n ?? 0} · acc {pct(cell.off?.accuracy)}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle className="flex items-center gap-2 text-xs">
              <ShieldCheck className="h-3.5 w-3.5" /> Evidence boundary
            </AlertTitle>
            <AlertDescription className="text-xs">
              <p>
                Scope: {data.scope.symbol ?? 'all symbols'} {data.scope.exchange ? `· ${data.scope.exchange}` : ''} ·{' '}
                {data.scope.days} days. Confirmed only: {data.scope.confirmed_only ? 'yes' : 'unknown'}.
              </p>
              <ul className="mt-2 list-disc space-y-0.5 pl-4">
                {data.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
