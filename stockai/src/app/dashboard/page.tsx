'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { cn, formatPrice } from '@/lib/utils';
import { relativeAge } from '@/lib/freshness';
import { FreshnessBadge } from '@/components/ui/freshness-badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { MarketTickerTape } from '@/components/market-ticker-tape';
import { CommandPalette, useCommandPalette } from '@/components/command-palette';
import {
  Activity, AlertTriangle, ArrowUpRight, ArrowDownRight, Bell, RefreshCw,
  Search, Star, Zap, Globe, ShieldCheck, Radio, Clock,
} from 'lucide-react';

type Overview = {
  indices: any[];
  gainers: any[];
  losers: any[];
  as_of?: string;
  stale?: boolean;
};

function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export default function DashboardPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [predictions, setPredictions] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const { open, setOpen } = useCommandPalette();
  const now = useNow(1000);

  const load = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      else setRefreshing(true);
      setError(null);
      const [ov, preds] = await Promise.all([
        api.getMarketOverview(),
        api.getTopPredictions({ limit: 6 }).catch(() => []),
      ]);
      setOverview(ov);
      const normalized = (Array.isArray(preds) ? preds : []).map((p: any) => ({
        symbol: p.symbol,
        name: p.name,
        exchange: p.exchange,
        horizon: p.horizon,
        direction: p.direction,
        up: Math.round(Number(p.probabilities?.up ?? 0) * 1000) / 10,
        expectedReturn: Number(p.expected_return ?? p.expectedReturn ?? 0),
        confidence: Number(p.confidence ?? 0),
        no_clear_edge: p.no_clear_edge ?? false,
        predictionTimestamp: p.prediction_timestamp ?? p.predictionTimestamp ?? null,
      }));
      setPredictions(normalized);
      try {
        if (api.isAuthenticated()) {
          const a = await api.getAlerts().catch(() => []);
          setAlerts(Array.isArray(a) ? a.slice(0, 5) : []);
        }
      } catch { /* alerts optional */ }
    } catch (err: any) {
      setError(err.message || 'Failed to load dashboard data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh market data every 60s (indices are cached 60s server-side).
  useEffect(() => {
    const t = setInterval(() => load(true), 60000);
    return () => clearInterval(t);
  }, [load]);

  const stats = useMemo(() => {
    const idx = overview?.indices ?? [];
    const fresh = idx.filter((i) => ['fresh', 'recent', 'delayed'].includes(i.freshness)).length;
    const up = (overview?.gainers ?? []).length;
    const down = (overview?.losers ?? []).length;
    return { total: idx.length, fresh, up, down };
  }, [overview]);

  const tapeItems = useMemo(
    () =>
      [...(overview?.indices ?? []), ...(overview?.gainers ?? []).slice(0, 5)].map((i: any) => ({
        symbol: i.symbol,
        name: i.name,
        price: Number(i.price) || 0,
        change_percent: Number(i.change_percent ?? i.changePercent ?? 0) || 0,
        freshness: i.freshness,
      })),
    [overview],
  );

  if (loading) {
    return (
      <div className="terminal-surface min-h-screen">
        <div className="mx-auto max-w-[1400px] space-y-6 p-6">
          <div className="chart-skeleton h-10 w-full rounded-lg" />
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="chart-skeleton h-32 rounded-xl" />
            ))}
          </div>
          <div className="chart-skeleton h-64 rounded-xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="terminal-surface min-h-screen">
      <CommandPalette open={open} onClose={() => setOpen(false)} />
      <MarketTickerTape items={tapeItems} />

      <div className="relative">
        <div className="terminal-grid-bg pointer-events-none absolute inset-x-0 top-0 h-72" />
        <div className="relative mx-auto max-w-[1400px] space-y-6 p-6">
          {/* Hero header */}
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                Market command center · {now.toLocaleTimeString('en-US', { hour12: false })} local
              </p>
              <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">
                What&apos;s moving, what&apos;s fresh, what needs you.
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                Live indices, watchlist attention, movers, alerts and model edge — every price
                carries backend-classified freshness. Stale is labeled stale. Missing is missing.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
                <Search className="mr-2 h-4 w-4" /> Search <span className="kbd ml-2">⌘K</span>
              </Button>
              <Button variant="outline" size="sm" onClick={() => load(true)} disabled={refreshing}>
                <RefreshCw className={cn('mr-2 h-4 w-4', refreshing && 'animate-spin')} />
                {refreshing ? 'Refreshing' : 'Refresh'}
              </Button>
            </div>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Dashboard failed to load</AlertTitle>
              <AlertDescription className="flex items-center gap-3">
                {error}
                <Button variant="outline" size="sm" onClick={() => load()}>Retry</Button>
              </AlertDescription>
            </Alert>
          )}

          {/* Status strip */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="glass-card">
              <CardContent className="flex items-center gap-3 p-4">
                <span className="rounded-lg bg-emerald-500/10 p-2"><Radio className="h-5 w-5 text-emerald-500" /></span>
                <div>
                  <p className="text-xs text-muted-foreground">Live coverage</p>
                  <p className="text-lg font-bold tabular-nums">{stats.fresh}/{stats.total} fresh</p>
                </div>
              </CardContent>
            </Card>
            <Card className="glass-card">
              <CardContent className="flex items-center gap-3 p-4">
                <span className="rounded-lg bg-primary/10 p-2"><Activity className="h-5 w-5 text-primary" /></span>
                <div>
                  <p className="text-xs text-muted-foreground">Breadth (snapshots)</p>
                  <p className="text-lg font-bold tabular-nums">
                    <span className="tick-up">{stats.up} ↑</span> · <span className="tick-down">{stats.down} ↓</span>
                  </p>
                </div>
              </CardContent>
            </Card>
            <Card className="glass-card">
              <CardContent className="flex items-center gap-3 p-4">
                <span className="rounded-lg bg-amber-500/10 p-2"><Bell className="h-5 w-5 text-amber-500" /></span>
                <div>
                  <p className="text-xs text-muted-foreground">Active alerts</p>
                  <p className="text-lg font-bold tabular-nums">{alerts.length} tracked</p>
                </div>
                <Link href="/alerts" className="ml-auto text-xs text-primary hover:underline">Manage</Link>
              </CardContent>
            </Card>
            <Card className="glass-card">
              <CardContent className="flex items-center gap-3 p-4">
                <span className="rounded-lg bg-violet-500/10 p-2"><ShieldCheck className="h-5 w-5 text-violet-500" /></span>
                <div>
                  <p className="text-xs text-muted-foreground">Model edge</p>
                  <p className="text-lg font-bold tabular-nums">
                    {predictions.filter((p) => !p.no_clear_edge).length}/{predictions.length} clear
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Indices */}
          <section aria-label="Market overview">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Globe className="h-4 w-4 text-muted-foreground" /> Market overview
              </h2>
              <Link href="/markets" className="text-sm text-primary hover:underline">All markets →</Link>
            </div>
            {(!overview || overview.indices.length === 0) ? (
              <Card>
                <CardContent className="empty-state">
                  <p className="empty-state-title">Live market data unavailable</p>
                  <p className="empty-state-description">
                    No index quotes returned. Configure FINNHUB / TWELVEDATA / ALPHAVANTAGE keys —
                    we show UNAVAILABLE instead of guessing.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {overview.indices.map((idx: any) => {
                  const cp = Number(idx.change_percent) || 0;
                  const up = cp >= 0;
                  return (
                    <Card key={idx.symbol} className="glass-card card-hover">
                      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <div>
                          <CardTitle className="text-sm font-medium">{idx.name ?? idx.symbol}</CardTitle>
                          <CardDescription className="font-mono text-[11px]">{idx.symbol} · {idx.provider ?? '—'}</CardDescription>
                        </div>
                        <FreshnessBadge freshness={idx.freshness} sourceTimestamp={idx.timestamp} size="sm" />
                      </CardHeader>
                      <CardContent>
                        <div className="text-2xl font-bold tabular-nums">{formatPrice(Number(idx.price) || 0, idx.currency || 'USD')}</div>
                        <p className={cn('flex items-center gap-1 text-sm tabular-nums', up ? 'tick-up' : 'tick-down')}>
                          {up ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
                          {up ? '+' : ''}{cp.toFixed(2)}%
                        </p>
                        <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          {idx.timestamp ? new Date(idx.timestamp).toLocaleString() : 'timestamp unknown'}
                        </p>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
            {overview?.stale && (overview?.indices?.length ?? 0) > 0 && (
              <Alert className="mt-3">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>All indices stale</AlertTitle>
                <AlertDescription>Provider or scheduler data is older than tolerance. Prices remain labeled — not hidden.</AlertDescription>
              </Alert>
            )}
          </section>

          {/* Movers + Predictions */}
          <div className="grid gap-6 lg:grid-cols-2">
            <section aria-label="Market movers">
              <h2 className="mb-3 text-lg font-semibold">Market movers</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm text-emerald-600">Top gainers</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {(overview?.gainers ?? []).length === 0 && <p className="text-sm text-muted-foreground">No snapshot data.</p>}
                    {(overview?.gainers ?? []).map((m: any) => (
                      <Link
                        key={m.symbol}
                        href={`/stocks/${m.symbol}?exchange=${m.exchange}`}
                        className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm hover:bg-muted/60"
                      >
                        <span className="font-semibold">{m.symbol}</span>
                        <span className="flex items-center gap-2">
                          <FreshnessBadge freshness={m.freshness} size="sm" />
                          <span className="tick-up tabular-nums">+{Number(m.change_percent).toFixed(2)}%</span>
                        </span>
                      </Link>
                    ))}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2"><CardTitle className="text-sm text-red-600">Top losers</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {(overview?.losers ?? []).length === 0 && <p className="text-sm text-muted-foreground">No snapshot data.</p>}
                    {(overview?.losers ?? []).map((m: any) => (
                      <Link
                        key={m.symbol}
                        href={`/stocks/${m.symbol}?exchange=${m.exchange}`}
                        className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm hover:bg-muted/60"
                      >
                        <span className="font-semibold">{m.symbol}</span>
                        <span className="flex items-center gap-2">
                          <FreshnessBadge freshness={m.freshness} size="sm" />
                          <span className="tick-down tabular-nums">{Number(m.change_percent).toFixed(2)}%</span>
                        </span>
                      </Link>
                    ))}
                  </CardContent>
                </Card>
              </div>
            </section>

            <section aria-label="Top AI predictions">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-lg font-semibold"><Zap className="h-4 w-4 text-amber-500" /> Model edge</h2>
                <Link href="/predictions" className="text-sm text-primary hover:underline">View all →</Link>
              </div>
              <Card>
                <CardContent className="space-y-2 p-3">
                  {predictions.length === 0 && (
                    <p className="p-4 text-center text-sm text-muted-foreground">
                      No predictions available. Honest empty state — not a mock.
                    </p>
                  )}
                  {predictions.map((p) => (
                    <Link
                      key={`${p.symbol}-${p.exchange}`}
                      href={`/stocks/${p.symbol}?exchange=${p.exchange}`}
                      className="flex items-center justify-between rounded-lg border border-transparent p-3 transition-colors hover:border-border hover:bg-muted/40"
                    >
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-14 items-center justify-center rounded-lg bg-primary/10 font-mono text-xs font-bold">
                          {p.symbol}
                        </span>
                        <div>
                          <p className="text-sm font-medium">{p.name ?? p.symbol}</p>
                          <p className="text-xs text-muted-foreground">
                            {p.exchange} · {p.horizon}
                            {p.predictionTimestamp ? ` · as of ${relativeAge(p.predictionTimestamp) ?? '—'}` : ''}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 text-sm">
                        {p.no_clear_edge
                          ? <span className="rounded-full bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground">NO CLEAR EDGE</span>
                          : <span className={cn('rounded-full px-2 py-1 text-[11px] font-bold', p.direction === 'up' ? 'bg-emerald-500/10 text-emerald-600' : p.direction === 'down' ? 'bg-red-500/10 text-red-600' : 'bg-amber-500/10 text-amber-600')}>{p.direction?.toUpperCase()} {p.up}%</span>}
                        <span className="tabular-nums text-xs text-muted-foreground">ER {p.expectedReturn >= 0 ? '+' : ''}{p.expectedReturn.toFixed(1)}%</span>
                      </div>
                    </Link>
                  ))}
                </CardContent>
              </Card>
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                Probabilistic, calibrated, uncertainty-aware. Past performance ≠ future results. Not investment advice.
              </p>
            </section>
          </div>

          {/* Alerts + quick actions */}
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base"><Bell className="h-4 w-4" /> Alerts needing you</CardTitle>
                  <CardDescription>Real backend triggers — never fired on stale data silently.</CardDescription>
                </div>
                <Link href="/alerts"><Button size="sm" variant="outline">Open alerts</Button></Link>
              </CardHeader>
              <CardContent>
                {alerts.length === 0 ? (
                  <p className="py-4 text-center text-sm text-muted-foreground">
                    {api.isAuthenticated() ? 'No active alerts. Create one from any stock page.' : 'Sign in to create price alerts.'}
                  </p>
                ) : (
                  <div className="space-y-2">
                    {alerts.map((a: any) => (
                      <div key={a.id} className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2 text-sm">
                        <span className="font-medium">{a.symbol ?? a.instrument_id?.slice(0, 8)}</span>
                        <span className="text-xs text-muted-foreground">{a.status} · {a.alert_type} {a.condition} {a.target_value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Quick actions</CardTitle>
                <CardDescription>Jump straight into analysis.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-2 sm:grid-cols-3">
                <Link href="/stocks/AAPL?exchange=NASDAQ" className="rounded-xl border border-border p-4 transition-colors hover:bg-muted/50">
                  <Zap className="mb-2 h-5 w-5 text-blue-500" />
                  <p className="text-sm font-semibold">Analyze AAPL</p>
                  <p className="text-xs text-muted-foreground">Quote · chart · edge</p>
                </Link>
                <Link href="/screener" className="rounded-xl border border-border p-4 transition-colors hover:bg-muted/50">
                  <Search className="mb-2 h-5 w-5 text-emerald-500" />
                  <p className="text-sm font-semibold">Screen stocks</p>
                  <p className="text-xs text-muted-foreground">Real filters, no mocks</p>
                </Link>
                <Link href="/watchlist" className="rounded-xl border border-border p-4 transition-colors hover:bg-muted/50">
                  <Star className="mb-2 h-5 w-5 text-violet-500" />
                  <p className="text-sm font-semibold">Watchlist</p>
                  <p className="text-xs text-muted-foreground">Live refresh + freshness</p>
                </Link>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
