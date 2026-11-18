'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { api } from '@/lib/api/client';
import { FreshnessBadge } from '@/components/ui/freshness-badge';
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Clock,
  Flame,
  Globe,
  Layers,
  Minus,
  RefreshCw,
  SearchX,
  Timer,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { cn, formatPrice, formatPercent, formatVolume, formatTimestamp } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Region = 'global' | 'us' | 'india' | 'europe';
type MarketStatus = 'open' | 'closed' | 'pre-market' | 'after-hours';

interface MarketIndex {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  status: MarketStatus;
  timestamp: string;
  region: Exclude<Region, 'global'>;
  currency?: string;
  freshness?: string;
  provider?: string;
}

interface MarketMover {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  region: Exclude<Region, 'global'>;
  exchange?: string;
  freshness?: string;
}

interface SectorPerformance {
  sector: string;
  changePercent: number;
}

interface HeatmapCell {
  symbol: string;
  name: string;
  changePercent: number;
  region: Exclude<Region, 'global'>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getRegionMeta(region: Exclude<Region, 'global'>) {
  switch (region) {
    case 'us':
      return { label: 'United States', code: 'US', currency: 'USD' as const };
    case 'india':
      return { label: 'India', code: 'IN', currency: 'INR' as const };
    case 'europe':
      return { label: 'Europe', code: 'EU', currency: 'EUR' as const };
  }
}

function statusBadgeClass(status: MarketStatus) {
  switch (status) {
    case 'open':
      return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900';
    case 'pre-market':
      return 'bg-blue-50 text-blue-700 ring-1 ring-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-900';
    case 'after-hours':
      return 'bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-900';
    case 'closed':
    default:
      return 'bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700';
  }
}

function changeTextClass(v: number) {
  if (v > 0) return 'text-emerald-600 dark:text-emerald-400';
  if (v < 0) return 'text-red-600 dark:text-red-400';
  return 'text-slate-500 dark:text-slate-400';
}

function changeBgClass(v: number) {
  if (v > 0) return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900';
  if (v < 0) return 'bg-red-50 text-red-700 ring-1 ring-red-200 dark:bg-red-950/30 dark:text-red-300 dark:ring-red-900';
  return 'bg-slate-50 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300';
}

function heatmapColor(v: number) {
  const abs = Math.abs(v);
  const intensity = Math.min(abs / 3, 1); // normalize to 0-1 for 3%
  if (v > 0) {
    // green scale - stronger change = darker
    return `rgba(16, 185, 129, ${0.25 + intensity * 0.75})`;
  }
  if (v < 0) {
    return `rgba(239, 68, 68, ${0.25 + intensity * 0.75})`;
  }
  return 'rgba(148, 163, 184, 0.25)';
}

function inferRegion(symbol: string): Exclude<Region, 'global'> {
  const s = symbol.toUpperCase();
  if (['^NSEI', '^BSESN', 'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'SBIN', 'ICICIBANK', 'BHARTIARTL', 'LT', 'WIPRO', 'ADANIENT'].some((k) => s.includes(k))) return 'india';
  if (['^GDAXI', '^FTSE', '^STOXX', 'ASML', 'SAP', 'HSBA', 'LVMH', 'SIE', 'AIR', 'BP', 'NVO'].some((k) => s.includes(k))) return 'europe';
  return 'us';
}

function safeFormatTimestamp(ts: string) {
  try {
    return formatTimestamp(ts);
  } catch {
    try {
      return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' });
    } catch {
      return ts;
    }
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function IndexCard({ index }: { index: MarketIndex }) {
  const isPos = index.changePercent >= 0;
  const isNeg = index.changePercent < 0;
  const meta = getRegionMeta(index.region);
  return (
    <Card className="overflow-hidden border-slate-200 bg-white shadow-sm transition-all hover:shadow-md dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300" aria-hidden>
                {meta.code}
              </span>
              <CardTitle className="truncate text-[15px] font-semibold tracking-tight">{index.name}</CardTitle>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="font-mono font-medium tracking-widest">{index.symbol}</span>
              <span className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600" />
              <span>{meta.label}</span>
            </div>
          </div>
          <Badge variant="outline" className={cn('shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide', statusBadgeClass(index.status))}>
            <span className={cn('mr-1.5 h-1.5 w-1.5 rounded-full', index.status === 'open' ? 'bg-emerald-500' : index.status === 'pre-market' ? 'bg-blue-500' : index.status === 'after-hours' ? 'bg-amber-500' : 'bg-slate-400')} />
            {index.status === 'pre-market' ? 'PRE' : index.status === 'after-hours' ? 'AFTER' : index.status.toUpperCase()}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <div className="flex items-baseline justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate font-mono text-[22px] font-semibold leading-none tracking-tight tabular-nums">
              {index.price === 0 ? '—' : index.currency === 'INR' ? `₹${index.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : formatPrice(index.price, index.currency ?? 'USD')}
            </div>
            <div className={cn('mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums', changeBgClass(index.changePercent))}>
              {isPos ? <ArrowUpRight className="h-3 w-3" /> : isNeg ? <ArrowDownRight className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
              <span>
                {index.price === 0 ? 'Data unavailable' : `${isPos ? '+' : ''}${formatPrice(index.change, index.currency ?? 'USD')} (${formatPercent(index.changePercent)})`}
              </span>
            </div>
          </div>
          <div className={cn('flex h-9 w-9 items-center justify-center rounded-lg border', isPos ? 'border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400' : isNeg ? 'border-red-200 bg-red-50 text-red-600 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400' : 'border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-400')}>
            {isPos ? <TrendingUp className="h-4 w-4" /> : isNeg ? <TrendingDown className="h-4 w-4" /> : <Minus className="h-4 w-4" />}
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span className="tabular-nums">{safeFormatTimestamp(index.timestamp)}</span>
          <FreshnessBadge freshness={index.freshness} sourceTimestamp={index.timestamp} size="sm" />
        </div>
      </CardContent>
    </Card>
  );
}

function IndexCardSkeleton() {
  return (
    <Card className="border-slate-200 dark:border-slate-800">
      <CardHeader className="pb-3">
        <div className="flex justify-between">
          <div className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-5 w-24 rounded-full" />
        <Skeleton className="h-3 w-28" />
      </CardContent>
    </Card>
  );
}

function MoverTable({ title, icon: Icon, movers, emptyMessage, accent }: { title: string; icon: React.ElementType; movers: MarketMover[]; emptyMessage: string; accent: 'gain' | 'loss' | 'volume' }) {
  const accentColor = accent === 'gain' ? 'text-emerald-600 dark:text-emerald-400' : accent === 'loss' ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400';
  return (
    <Card className="flex h-full flex-col border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={cn('flex h-7 w-7 items-center justify-center rounded-md border', accent === 'gain' ? 'border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-400' : accent === 'loss' ? 'border-red-200 bg-red-50 text-red-600 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400' : 'border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-400')}>
              <Icon className="h-3.5 w-3.5" />
            </div>
            <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">{title}</CardTitle>
          </div>
          <Badge variant="secondary" className="rounded-full bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 text-[11px]">
            {movers.length}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex-1 pt-0">
        {movers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
              <SearchX className="h-5 w-5 text-slate-400" />
            </div>
            <p className="mt-3 text-sm font-medium text-slate-900 dark:text-white">No data</p>
            <p className="mt-1 max-w-[220px] text-xs leading-5 text-muted-foreground">{emptyMessage}</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
            <Table>
              <TableHeader className="bg-slate-50/70 dark:bg-slate-800/50">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-8 text-[11px] font-semibold uppercase tracking-wide">Symbol</TableHead>
                  <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide">Price</TableHead>
                  <TableHead className="h-8 text-right text-[11px] font-semibold uppercase tracking-wide">Change</TableHead>
                  <TableHead className="hidden h-8 text-right text-[11px] font-semibold uppercase tracking-wide sm:table-cell">Volume</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {movers.map((m) => (
                  <TableRow key={`${m.symbol}-${m.exchange ?? ''}`} className="group hover:bg-slate-50/70 dark:hover:bg-slate-800/50">
                    <TableCell className="py-2.5">
                      <div className="flex flex-col">
                        <span className="font-mono text-xs font-semibold tracking-wide">{m.symbol}</span>
                        <span className="max-w-[140px] truncate text-[11px] leading-4 text-muted-foreground">{m.name}</span>
                        <span className="text-[10px] leading-4 text-muted-foreground">{m.exchange ?? getRegionMeta(m.region).label}</span>
                      </div>
                    </TableCell>
                    <TableCell className="py-2.5 text-right font-mono text-xs tabular-nums">
                      <span className="font-medium">{m.region === 'india' ? `₹${m.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : formatPrice(m.price, m.region === 'europe' ? 'EUR' : 'USD')}</span>
                    </TableCell>
                    <TableCell className="py-2.5 text-right">
                      <span className={cn('inline-flex items-center justify-end gap-1 rounded-full px-1.5 py-0.5 text-xs font-semibold tabular-nums', changeBgClass(m.changePercent))}>
                        {m.changePercent > 0 ? <TrendingUp className="h-3 w-3" /> : m.changePercent < 0 ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                        {formatPercent(m.changePercent)}
                      </span>
                    </TableCell>
                    <TableCell className="hidden py-2.5 text-right font-mono text-xs tabular-nums text-muted-foreground sm:table-cell">{formatVolume(m.volume)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SectorPerformanceCard({ sectors }: { sectors: SectorPerformance[] }) {
  const maxAbs = Math.max(...sectors.map((s) => Math.abs(s.changePercent)), 1);
  return (
    <Card className="flex h-full flex-col border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300">
            <Layers className="h-3.5 w-3.5" />
          </div>
          <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Sector Performance</CardTitle>
        </div>
        <p className="text-xs text-muted-foreground">Intraday • % change</p>
      </CardHeader>
      <CardContent className="flex-1 space-y-3 pt-0">
        {sectors.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <SearchX className="h-6 w-6 text-slate-400" />
            <p className="mt-2 text-sm font-medium">No sector data</p>
            <p className="text-xs text-muted-foreground">No sectors available for this region.</p>
          </div>
        ) : (
          sectors
            .slice()
            .sort((a, b) => b.changePercent - a.changePercent)
            .map((s) => {
              const isPos = s.changePercent >= 0;
              const width = Math.max((Math.abs(s.changePercent) / maxAbs) * 100, 8);
              return (
                <div key={s.sector} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="truncate pr-2 font-medium text-slate-700 dark:text-slate-300">{s.sector}</span>
                    <span className={cn('shrink-0 font-mono text-xs font-semibold tabular-nums', changeTextClass(s.changePercent))}>{formatPercent(s.changePercent)}</span>
                  </div>
                  <div className="relative h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                    <div
                      className={cn('absolute top-0 h-full rounded-full transition-all', isPos ? 'left-1/2 bg-emerald-500' : 'right-1/2 bg-red-500')}
                      style={{ width: `${width / 2}%` }}
                    />
                    <div className="absolute left-1/2 top-0 h-full w-px bg-white dark:bg-slate-900" />
                  </div>
                </div>
              );
            })
        )}
        <Separator className="my-2" />
        <p className="text-[11px] leading-4 text-muted-foreground">
          <span className="font-medium text-slate-700 dark:text-slate-300">Note:</span> Sector indices are aggregated proxies. Values are illustrative when live feed is unavailable.
        </p>
      </CardContent>
    </Card>
  );
}

function HeatmapPlaceholder({ data }: { data: HeatmapCell[] }) {
  return (
    <Card className="overflow-hidden border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300">
              <Activity className="h-3.5 w-3.5" />
            </div>
            <div>
              <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Market Heatmap</CardTitle>
              <p className="text-xs text-muted-foreground">Breadth • intraday movement intensity</p>
            </div>
          </div>
          <Badge variant="outline" className="hidden rounded-full border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300 sm:inline-flex">
            <Timer className="mr-1 h-3 w-3" />
            Placeholder
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6 lg:grid-cols-8">
          {data.map((cell) => (
            <div
              key={cell.symbol}
              className="group relative flex min-h-[64px] flex-col justify-between rounded-md p-2 text-white transition-all hover:scale-[1.02] hover:shadow-md"
              style={{ backgroundColor: heatmapColor(cell.changePercent) }}
              title={`${cell.name} (${cell.symbol}): ${formatPercent(cell.changePercent)}`}
            >
              <div className="text-[10px] font-semibold uppercase tracking-wide text-white/90 drop-shadow-sm">{cell.symbol}</div>
              <div className="text-[11px] font-mono font-bold tabular-nums drop-shadow-sm">{formatPercent(cell.changePercent)}</div>
              <div className="absolute inset-0 rounded-md ring-1 ring-black/5 group-hover:ring-black/10" />
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/50">
          <div className="flex items-center gap-1.5 text-xs">
            <span className="h-2 w-2 rounded-full bg-red-500" /> Losers
            <span className="mx-1 h-3 w-px bg-slate-300 dark:bg-slate-600" />
            <span className="h-2 w-2 rounded-full bg-slate-300" /> Flat
            <span className="mx-1 h-3 w-px bg-slate-300 dark:bg-slate-600" />
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Gainers
          </div>
          <span className="text-[11px] text-muted-foreground">Intensity → magnitude of move (cap ±3%)</span>
        </div>
        <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/30">
          <p className="text-xs font-medium text-slate-700 dark:text-slate-300">Heatmap coming soon</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Full interactive heatmap (sector × market-cap tiling with live sizing by volume and drag-to-filter) is on the roadmap. This placeholder preserves layout, color semantics, and region filtering until the live feed is connected.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function TopMoversCard({ movers }: { movers: MarketMover[] }) {
  // sort by absolute changePercent desc to show most volatile
  const sorted = [...movers].sort((a, b) => Math.abs(b.changePercent) - Math.abs(a.changePercent)).slice(0, 6);
  return (
    <Card className="flex h-full flex-col border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md border border-violet-200 bg-violet-50 text-violet-600 dark:border-violet-900 dark:bg-violet-950/30 dark:text-violet-300">
            <Flame className="h-3.5 w-3.5" />
          </div>
          <CardTitle className="text-[13px] font-semibold uppercase tracking-widest">Top Movers</CardTitle>
        </div>
        <p className="text-xs text-muted-foreground">Largest absolute intraday moves</p>
      </CardHeader>
      <CardContent className="flex-1 space-y-2 pt-0">
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <SearchX className="h-6 w-6 text-slate-400" />
            <p className="mt-2 text-sm font-medium">No movers</p>
            <p className="text-xs text-muted-foreground">No top movers for this filter.</p>
          </div>
        ) : (
          sorted.map((m, idx) => (
            <div key={`${m.symbol}-${idx}`} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 transition-colors hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white dark:bg-white dark:text-slate-900">{idx + 1}</div>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-1.5">
                  <span className="font-mono text-xs font-semibold tracking-wide">{m.symbol}</span>
                  <span className="truncate text-xs text-muted-foreground">{m.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">{formatVolume(m.volume)} vol</span>
                  <span className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600" />
                  <span className="text-[11px] text-muted-foreground">{m.exchange ?? getRegionMeta(m.region).label}</span>
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-xs font-semibold tabular-nums">{m.region === 'india' ? `₹${m.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : formatPrice(m.price)}</div>
                <div className={cn('inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums', changeBgClass(m.changePercent))}>
                  {m.changePercent > 0 ? <TrendingUp className="h-3 w-3" /> : m.changePercent < 0 ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                  {formatPercent(m.changePercent)}
                </div>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function MarketsPage() {
  const [activeRegion, setActiveRegion] = useState<Region>('global');
  const [indices, setIndices] = useState<MarketIndex[]>([]);
  const [gainers, setGainers] = useState<MarketMover[]>([]);
  const [losers, setLosers] = useState<MarketMover[]>([]);
  const [highVolume, setHighVolume] = useState<MarketMover[]>([]);
  const [sectors, setSectors] = useState<(SectorPerformance & { region: Exclude<Region, 'global'> })[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapCell[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    setError(null);
    const isInitial = indices.length === 0 && isLoading;
    if (!isInitial) setIsRefreshing(true);
    else setIsLoading(true);

    try {
      // Real market overview from the backend: indices are live provider
      // quotes; movers come from persisted snapshots. All elements carry a
      // backend-classified freshness. Nothing is synthesized client-side.
      const overview = await api.getMarketOverview();
      const mappedIndices: MarketIndex[] = (Array.isArray(overview?.indices) ? overview.indices : [])
        .map((m: any) => {
          const symbol: string = m.symbol || '';
          const name: string = m.name || symbol || 'Unknown';
          const price: number = Number(m.price) || 0;
          const change: number = Number(m.change) || 0;
          const changePercent: number = Number(m.change_percent ?? m.changePercent ?? 0);
          const status: MarketStatus = (m.market_status as MarketStatus) || 'closed';
          const timestamp: string = m.timestamp || '';
          const region: Exclude<Region, 'global'> = inferRegion(symbol || name);
          return { symbol, name, price, change, changePercent, status, timestamp, region, currency: m.currency, freshness: m.freshness ?? 'unavailable', provider: m.provider };
        })
        .filter((i: any) => i.symbol && i.price > 0);

      const mapMover = (m: any): MarketMover => ({
        symbol: m.symbol,
        name: m.name,
        price: Number(m.price) || 0,
        change: 0,
        changePercent: Number(m.change_percent ?? m.changePercent ?? 0),
        volume: Number(m.volume) || 0,
        region: inferRegion(m.symbol),
        exchange: m.exchange,
        freshness: m.freshness ?? 'unavailable',
      });

      const mappedGainers = (Array.isArray(overview?.gainers) ? overview.gainers : []).map(mapMover);
      const mappedLosers = (Array.isArray(overview?.losers) ? overview.losers : []).map(mapMover);

      // Backend does not yet expose high-volume/sector/heatmap aggregations.
      // Show UNAVAILABLE instead of mock financial data.
      setIndices(mappedIndices);
      setGainers(mappedGainers);
      setLosers(mappedLosers);
      setHighVolume([]);
      setSectors([]);
      setHeatmap([]);
      setLastUpdated(overview?.as_of || new Date().toISOString());
      if (mappedIndices.length === 0) {
        setError((prev: string | null) => prev || 'Live markets data unavailable — no indices returned from provider. Display will remain empty until live feed is configured.');
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load markets data. Live feed unavailable.');
      if (indices.length === 0) {
        setIndices([]);
        setGainers([]);
        setLosers([]);
        setHighVolume([]);
        setSectors([]);
        setHeatmap([]);
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [indices.length, isLoading]);

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredIndices = useMemo(() => {
    if (activeRegion === 'global') return indices;
    return indices.filter((i) => i.region === activeRegion);
  }, [indices, activeRegion]);

  const filteredGainers = useMemo(() => (activeRegion === 'global' ? gainers : gainers.filter((m) => m.region === activeRegion)), [gainers, activeRegion]);
  const filteredLosers = useMemo(() => (activeRegion === 'global' ? losers : losers.filter((m) => m.region === activeRegion)), [losers, activeRegion]);
  const filteredHighVolume = useMemo(() => (activeRegion === 'global' ? highVolume : highVolume.filter((m) => m.region === activeRegion)), [highVolume, activeRegion]);
  const filteredSectors = useMemo(() => (activeRegion === 'global' ? sectors : sectors.filter((s) => s.region === activeRegion)), [sectors, activeRegion]);
  const filteredHeatmap = useMemo(() => (activeRegion === 'global' ? heatmap : heatmap.filter((h) => h.region === activeRegion)), [heatmap, activeRegion]);
  const allMoversForTop = useMemo(() => [...filteredGainers, ...filteredLosers, ...filteredHighVolume], [filteredGainers, filteredLosers, filteredHighVolume]);

  // counts for header
  const openCount = useMemo(() => indices.filter((i) => i.status === 'open').length, [indices]);

  return (
    <div className="min-h-screen bg-slate-50/60 dark:bg-slate-950">
      <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                <BarChart3 className="h-4 w-4" />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Markets</h1>
              <Badge variant="outline" className="hidden rounded-full border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 sm:inline-flex">
                <Globe className="mr-1 h-3 w-3" />
                {indices.length} indices
              </Badge>
              <span className={cn('hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex', openCount > 0 ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900' : 'bg-slate-100 text-slate-600 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-300')}>
                <span className={cn('h-1.5 w-1.5 rounded-full', openCount > 0 ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400')} />
                {openCount} open
              </span>
            </div>
            <p className="max-w-[720px] text-sm leading-6 text-slate-600 dark:text-slate-400">
              Global overview across United States, India, and Europe. Track major indices, leaders & laggards — live where available. Unavailable sections stay empty and labeled; nothing is ever sampled or synthesized.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                <Clock className="h-3 w-3" />
                {lastUpdated ? `Updated ${safeFormatTimestamp(lastUpdated)}` : 'Awaiting data'}
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                <span className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-700" />
                Data may be delayed by exchange policy
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 self-start sm:self-auto">
            <Button variant="outline" size="sm" onClick={fetchData} disabled={isLoading || isRefreshing} className="bg-white dark:bg-slate-900">
              <RefreshCw className={cn('h-4 w-4', (isLoading || isRefreshing) && 'animate-spin')} />
              {isRefreshing ? 'Refreshing' : 'Refresh'}
            </Button>
          </div>
        </div>

        {/* Region Tabs */}
        <div className="mt-6">
          <Tabs value={activeRegion} onValueChange={(v) => setActiveRegion(v as Region)} className="w-full">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <TabsList className="inline-flex h-auto w-full justify-start gap-1 overflow-x-auto rounded-lg bg-slate-100 p-1 dark:bg-slate-900 sm:w-auto">
                <TabsTrigger value="global" className="whitespace-nowrap data-[state=active]:bg-white data-[state=active]:shadow-sm dark:data-[state=active]:bg-slate-800">
                  <Globe className="h-3.5 w-3.5" />
                  Global
                </TabsTrigger>
                <TabsTrigger value="us" className="whitespace-nowrap data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800">
                  <span className="mr-1 rounded bg-slate-200 px-1 font-mono text-[10px] font-bold dark:bg-slate-700">US</span> United States
                </TabsTrigger>
                <TabsTrigger value="india" className="whitespace-nowrap data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800">
                  <span className="mr-1 rounded bg-slate-200 px-1 font-mono text-[10px] font-bold dark:bg-slate-700">IN</span> India
                </TabsTrigger>
                <TabsTrigger value="europe" className="whitespace-nowrap data-[state=active]:bg-white dark:data-[state=active]:bg-slate-800">
                  <span className="mr-1 rounded bg-slate-200 px-1 font-mono text-[10px] font-bold dark:bg-slate-700">EU</span> Europe
                </TabsTrigger>
              </TabsList>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="hidden sm:inline">Filtered view:</span>
                <Badge variant="secondary" className="rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                  {activeRegion === 'global' ? 'All regions' : getRegionMeta(activeRegion as Exclude<Region, 'global'>).label}
                </Badge>
                <span className="text-slate-400">• {filteredIndices.length} indices • {filteredGainers.length + filteredLosers.length} movers</span>
              </div>
            </div>
          </Tabs>
        </div>

        {/* Error state */}
        {error && (
          <Card className="mt-6 border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20">
            <CardContent className="flex gap-3 p-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300">
                <AlertTriangle className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">We couldn&apos;t reach the live markets feed</p>
                <p className="mt-1 text-sm leading-5 text-amber-800/80 dark:text-amber-100/70">{error}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={fetchData} className="border-amber-200 bg-white text-amber-900 hover:bg-amber-50 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
                    <RefreshCw className="h-3.5 w-3.5" />
                    Retry
                  </Button>
                  <span className="inline-flex items-center text-xs text-amber-700/70 dark:text-amber-200/60">Sections with no data stay empty — never sampled</span>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setError(null)} className="shrink-0 text-amber-700 hover:bg-amber-100 dark:text-amber-300">
                Dismiss
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Indices Section */}
        <section className="mt-6 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-900 dark:text-white">Market Indices</h2>
              <Badge variant="outline" className="rounded-full border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                S&P 500 • NASDAQ • DAX • FTSE • NIFTY 50 • SENSEX
              </Badge>
            </div>
            <span className="hidden text-xs text-muted-foreground sm:inline">
              Price • change • change % • status • timestamp
            </span>
          </div>

          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <IndexCardSkeleton key={i} />
              ))}
            </div>
          ) : filteredIndices.length === 0 ? (
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                  <SearchX className="h-6 w-6 text-slate-400" />
                </div>
                <p className="mt-4 text-sm font-semibold text-slate-900 dark:text-white">No indices for this region</p>
                <p className="mt-1 max-w-sm text-sm leading-5 text-muted-foreground">
                  No market indices matched the selected filter. Try Global view or refresh to load live data.
                </p>
                <Button variant="outline" size="sm" onClick={() => setActiveRegion('global')} className="mt-4">
                  Show Global
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredIndices.map((idx) => (
                <IndexCard key={`${idx.symbol}-${idx.region}`} index={idx} />
              ))}
            </div>
          )}
        </section>

        {/* Gainers / Losers */}
        <section className="mt-6 grid gap-6 lg:grid-cols-2">
          {isLoading ? (
            <>
              <Card className="border-slate-200 dark:border-slate-800">
                <CardHeader>
                  <Skeleton className="h-5 w-32" />
                </CardHeader>
                <CardContent className="space-y-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </CardContent>
              </Card>
              <Card className="border-slate-200 dark:border-slate-800">
                <CardHeader>
                  <Skeleton className="h-5 w-32" />
                </CardHeader>
                <CardContent className="space-y-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </CardContent>
              </Card>
            </>
          ) : (
            <>
              <MoverTable title="Top Gainers" icon={TrendingUp} movers={filteredGainers.slice(0, 5)} emptyMessage="No gainers for this region in the current session." accent="gain" />
              <MoverTable title="Top Losers" icon={TrendingDown} movers={filteredLosers.slice(0, 5)} emptyMessage="No losers for this region in the current session." accent="loss" />
            </>
          )}
        </section>

        {/* High Volume + Sector Performance */}
        <section className="mt-6 grid gap-6 lg:grid-cols-3">
          {isLoading ? (
            <>
              <Card className="border-slate-200 dark:border-slate-800 lg:col-span-2">
                <CardHeader>
                  <Skeleton className="h-5 w-40" />
                </CardHeader>
                <CardContent className="space-y-2">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </CardContent>
              </Card>
              <Card className="border-slate-200 dark:border-slate-800">
                <CardHeader>
                  <Skeleton className="h-5 w-32" />
                </CardHeader>
                <CardContent className="space-y-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-6 w-full" />
                  ))}
                </CardContent>
              </Card>
            </>
          ) : (
            <>
              <div className="lg:col-span-2">
                <MoverTable title="High Volume" icon={BarChart3} movers={filteredHighVolume.slice(0, 6)} emptyMessage="No high-volume leaders for this region." accent="volume" />
              </div>
              <div>
                <SectorPerformanceCard sectors={filteredSectors} />
              </div>
            </>
          )}
        </section>

        {/* Heatmap + Top Movers */}
        <section className="mt-6 grid gap-6 lg:grid-cols-3">
          {isLoading ? (
            <>
              <Card className="border-slate-200 dark:border-slate-800 lg:col-span-2">
                <CardHeader>
                  <Skeleton className="h-5 w-40" />
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6 lg:grid-cols-8">
                    {Array.from({ length: 24 }).map((_, i) => (
                      <Skeleton key={i} className="h-[64px] w-full rounded-md" />
                    ))}
                  </div>
                </CardContent>
              </Card>
              <Card className="border-slate-200 dark:border-slate-800">
                <CardHeader>
                  <Skeleton className="h-5 w-32" />
                </CardHeader>
                <CardContent className="space-y-2">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-14 w-full" />
                  ))}
                </CardContent>
              </Card>
            </>
          ) : (
            <>
              <div className="lg:col-span-2">
                <HeatmapPlaceholder data={filteredHeatmap.length ? filteredHeatmap : heatmap.slice(0, 12)} />
              </div>
              <div>
                <TopMoversCard movers={allMoversForTop} />
              </div>
            </>
          )}
        </section>

        {/* Footer meta */}
        <div className="mt-8 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Gainers
            </span>
            <span className="h-3 w-px bg-slate-200 dark:bg-slate-700" />
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-500" />
              Losers
            </span>
            <span className="h-3 w-px bg-slate-200 dark:bg-slate-700" />
            <span className="inline-flex items-center gap-1.5">
              <Activity className="h-3 w-3" />
              Volume leaders
            </span>
            <span className="h-3 w-px bg-slate-200 dark:bg-slate-700" />
            <span className="inline-flex items-center gap-1.5">
              <Layers className="h-3 w-3" />
              Sectors
            </span>
          </div>
          <span className="text-muted-foreground">
            Source: Exchange feeds via <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-800">/api/v1/markets</code> with client-side fallback. Not investment advice.
          </span>
        </div>
      </div>
    </div>
  );
}
