'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Info, RefreshCw, Trophy } from 'lucide-react';
import type { RankingPerformance, RankingSnapshot } from '@/types';

type MarketFilter = 'ALL' | 'US' | 'EU' | 'IN';
type HorizonFilter = '1d' | '5d' | '10d';

const MARKETS: { value: MarketFilter; label: string }[] = [
  { value: 'ALL', label: 'All markets' },
  { value: 'US', label: 'United States' },
  { value: 'EU', label: 'Europe' },
  { value: 'IN', label: 'India' },
];

const HORIZONS: { value: HorizonFilter; label: string }[] = [
  { value: '1d', label: '1 session' },
  { value: '5d', label: '5 sessions' },
  { value: '10d', label: '10 sessions' },
];

function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export default function RankingsPage() {
  const [market, setMarket] = useState<MarketFilter>('ALL');
  const [horizon, setHorizon] = useState<HorizonFilter>('1d');
  const [snapshot, setSnapshot] = useState<RankingSnapshot | null>(null);
  const [performance, setPerformance] = useState<RankingPerformance | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (refresh = false) => {
      setError(null);
      if (refresh) setRefreshing(true);
      else setLoading(true);
      try {
        const options = {
          market: market === 'ALL' ? undefined : market,
          horizon,
          limit: 50,
        };
        const next = refresh
          ? await api.refreshRankings(options)
          : await api.getRankings(options);
        setSnapshot(next);
        const perf = await api.getRankingPerformance({
          market: market === 'ALL' ? undefined : market,
          horizon,
        });
        setPerformance(perf);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Rankings are unavailable');
        setSnapshot(null);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [market, horizon]
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 px-4 py-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Trophy className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Relative Rankings</h1>
          </div>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Cross-sectional ordering of eligible instruments by expected performance versus
            the same-market median. Scores are relative rank signals, not absolute up/down
            forecasts.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void load(true)}
          disabled={refreshing || loading}
          className="gap-2 self-start"
        >
          <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
          {refreshing ? 'Refreshing' : 'Refresh'}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1 rounded-lg border p-1">
          {MARKETS.map((m) => (
            <Button
              key={m.value}
              size="sm"
              variant={market === m.value ? 'default' : 'ghost'}
              onClick={() => setMarket(m.value)}
            >
              {m.label}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1 rounded-lg border p-1">
          {HORIZONS.map((h) => (
            <Button
              key={h.value}
              size="sm"
              variant={horizon === h.value ? 'default' : 'ghost'}
              onClick={() => setHorizon(h.value)}
            >
              {h.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <p className="text-muted-foreground">
          A relative ranking does not mean that a stock will rise. Ranking evidence is
          walk-forward on a 19-symbol development panel. Live profitability and universal
          generalisation are not established. This page is research-grade decision
          support, not investment advice.
        </p>
      </div>

      {error && (
        <Card className="border-destructive/40">
          <CardContent className="flex items-start gap-3 py-6">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium">Rankings unavailable</p>
              <p className="text-sm text-muted-foreground">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && !snapshot && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      )}

      {snapshot && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card size="sm">
              <CardHeader>
                <CardDescription>As of session</CardDescription>
                <CardTitle>{snapshot.as_of_date}</CardTitle>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardDescription>Ranked instruments</CardDescription>
                <CardTitle>
                  {snapshot.ranked_count} / {snapshot.market_universe_size}
                </CardTitle>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardDescription>Model</CardDescription>
                <CardTitle className="text-sm">{snapshot.model_version}</CardTitle>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardDescription>Resolved outcomes</CardDescription>
                <CardTitle>
                  {performance?.n_outcomes ?? 0}
                  {performance?.reliable ? (
                    <Badge variant="secondary" className="ml-2">
                      reliable sample
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="ml-2">
                      small sample
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle>Ranking</CardTitle>
                <CardDescription>
                  Rank 1 is expected to outperform the eligible cross-section. Percentile
                  is relative to the displayed market universe.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {snapshot.entries.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    No instruments met the eligibility requirements for this session.
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-14">Rank</TableHead>
                        <TableHead>Instrument</TableHead>
                        <TableHead className="text-right">Relative score</TableHead>
                        <TableHead className="text-right">Percentile</TableHead>
                        <TableHead>Bucket</TableHead>
                        <TableHead>Signal</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {snapshot.entries.map((entry) => {
                        const above = entry.relative_label === 'expected_above_median';
                        return (
                          <TableRow key={entry.instrument_id}>
                            <TableCell className="font-mono font-semibold">
                              {entry.rank}
                            </TableCell>
                            <TableCell>
                              <Link
                                href={`/stocks/${encodeURIComponent(entry.symbol)}?exchange=${encodeURIComponent(entry.exchange)}`}
                                className="font-medium hover:underline"
                              >
                                {entry.symbol}
                              </Link>
                              <p className="text-xs text-muted-foreground">{entry.exchange}</p>
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {entry.score.toFixed(3)}
                            </TableCell>
                            <TableCell className="text-right">
                              {entry.percentile.toFixed(1)}
                            </TableCell>
                            <TableCell>
                              <Badge variant={entry.quintile === 1 ? 'default' : 'outline'}>
                                Q{entry.quintile}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <span
                                className={cn(
                                  'inline-flex items-center gap-1 text-xs font-medium',
                                  above ? 'text-emerald-600' : 'text-rose-600'
                                )}
                              >
                                {above ? (
                                  <ArrowUpRight className="h-3.5 w-3.5" />
                                ) : (
                                  <ArrowDownRight className="h-3.5 w-3.5" />
                                )}
                                {above ? 'Above median' : 'Below median'}
                              </span>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Live resolved performance</CardTitle>
                  <CardDescription>
                    Directional hit rate of the relative call once the horizon resolves.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-xs text-muted-foreground">Hit rate</p>
                      <p className="text-lg font-semibold">{pct(performance?.hit_rate)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Outcomes</p>
                      <p className="text-lg font-semibold">{performance?.n_outcomes ?? 0}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Rank IC</p>
                      <p className="text-lg font-semibold">
                        {performance?.mean_snapshot_rank_ic?.toFixed(3) ?? '—'}
                      </p>
                    </div>
                  </div>
                  {performance && Object.keys(performance.by_quintile).length > 0 && (
                    <div className="space-y-1 border-t pt-3">
                      {Object.entries(performance.by_quintile).map(([q, stats]) => (
                        <div
                          key={q}
                          className="flex items-center justify-between text-sm"
                        >
                          <span className="text-muted-foreground">Quintile {q}</span>
                          <span className="font-mono">
                            {pct(stats.hit_rate)}{' '}
                            <span className="text-muted-foreground">(n={stats.n})</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {performance?.reliable
                      ? 'Sample meets the minimum reporting threshold (n>=30).'
                      : 'Too few outcomes for a stable estimate; treat as provisional.'}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Artifact & caveats</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-xs text-muted-foreground">
                  <p>
                    <span className="font-medium text-foreground">Score semantics:</span>{' '}
                    {snapshot.score_semantics ||
                      'Relative rank score; not a calibrated probability.'}
                  </p>
                  <p className="break-all">
                    <span className="font-medium text-foreground">Artifact SHA:</span>{' '}
                    {snapshot.artifact_sha.slice(0, 16)}…
                  </p>
                  <p>
                    <span className="font-medium text-foreground">Eligible universe:</span>{' '}
                    {snapshot.universe_size} instruments
                  </p>
                  {Object.keys(snapshot.excluded).length > 0 && (
                    <p>
                      <span className="font-medium text-foreground">Excluded:</span>{' '}
                      {Object.entries(snapshot.excluded)
                        .map(([reason, count]) => `${reason} (${count})`)
                        .join(', ')}
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
