'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, TrendingUp, Bell, Star, LayoutDashboard, FlaskConical, ArrowRight } from 'lucide-react';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';

type Result = {
  symbol: string;
  name: string;
  exchange: string;
  exchange_code: string;
  market: string;
  type?: string;
  currency?: string;
};

const QUICK_LINKS = [
  { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, hint: 'Market command center' },
  { label: 'Alerts', href: '/alerts', icon: Bell, hint: 'Price & signal triggers' },
  { label: 'Watchlist', href: '/watchlist', icon: Star, hint: 'Tracked instruments' },
  { label: 'Backtesting', href: '/backtesting', icon: FlaskConical, hint: 'Causal walk-forward' },
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setActive(0);
      setSearchError(null);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open ]);

  const search = useCallback((q: string) => {
    if (timer.current) clearTimeout(timer.current);
    if (!q.trim()) {
      setResults([]);
      setLoading(false);
      setSearchError(null);
      return;
    }
    setLoading(true);
    timer.current = setTimeout(async () => {
      try {
        const r = await api.searchInstruments(q.trim(), { limit: 8 });
        setResults(Array.isArray(r) ? r : []);
        setActive(0);
        setSearchError(null);
      } catch (err) {
        console.warn('[command-palette] search failed', err);
        setResults([]);
        setSearchError('Search unavailable');
      } finally {
        setLoading(false);
      }
    }, 220);
  }, []);

  useEffect(() => {
    search(query);
  }, [query, search]);

  const total = results.length + QUICK_LINKS.length;

  const go = (href: string) => {
    onClose();
    router.push(href);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => (a + 1) % Math.max(total, 1));
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => (a - 1 + Math.max(total, 1)) % Math.max(total, 1));
    }
    if (e.key === 'Enter') {
      if (active < results.length && results[active]) {
        const r = results[active];
        go(`/stocks/${encodeURIComponent(r.symbol)}?exchange=${encodeURIComponent(r.exchange_code || r.exchange)}`);
      } else {
        const link = QUICK_LINKS[active - results.length];
        if (link) go(link.href);
      }
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="glass-card w-full max-w-xl overflow-hidden rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ticker, company, or type a command…"
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            aria-label="Search instruments"
          />
          <span className="kbd">esc</span>
        </div>
        <div className="max-h-[50vh] overflow-y-auto p-2">
          {loading && (
            <div className="space-y-2 p-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="chart-skeleton h-12 rounded-lg" />
              ))}
            </div>
          )}
          {!loading && query.trim() === '' && (
            <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Jump to
            </p>
          )}
          {!loading &&
            query.trim() === '' &&
            QUICK_LINKS.map((l, i) => (
              <button
                key={l.href}
                onClick={() => go(l.href)}
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors',
                  active === i ? 'bg-muted' : 'hover:bg-muted/60',
                )}
              >
                <l.icon className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{l.label}</span>
                <span className="text-xs text-muted-foreground">{l.hint}</span>
                <ArrowRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
              </button>
            ))}
          {!loading && query.trim() !== '' && results.length === 0 && (
            <div className="empty-state py-8">
              <p className="empty-state-title text-sm">No instruments found</p>
              <p className="empty-state-description text-xs">
                Try a ticker (AAPL), company (Apple), or check the exchange filter.
              </p>
              {searchError && (
                <p className="empty-state-description text-xs text-amber-600 dark:text-amber-400">
                  {searchError}
                </p>
              )}
            </div>
          )}
          {!loading &&
            results.map((r, i) => (
              <button
                key={`${r.symbol}-${r.exchange_code}`}
                onClick={() =>
                  go(`/stocks/${encodeURIComponent(r.symbol)}?exchange=${encodeURIComponent(r.exchange_code || r.exchange)}`)
                }
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors',
                  active === i ? 'bg-muted' : 'hover:bg-muted/60',
                )}
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                  <TrendingUp className="h-4 w-4 text-primary" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="font-semibold">{r.symbol}</span>
                    <span className="rounded border border-border px-1 text-[10px] text-muted-foreground">
                      {r.exchange_code || r.exchange}
                    </span>
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {r.name} · {r.market}
                  </span>
                </span>
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            ))}
          {!loading && query.trim() !== '' && results.length > 0 && (
            <>
              <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Commands
              </p>
              {QUICK_LINKS.map((l, j) => {
                const idx = results.length + j;
                return (
                  <button
                    key={l.href}
                    onClick={() => go(l.href)}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors',
                      active === idx ? 'bg-muted' : 'hover:bg-muted/60',
                    )}
                  >
                    <l.icon className="h-4 w-4 text-muted-foreground" />
                    <span>{l.label}</span>
                  </button>
                );
              })}
            </>
          )}
        </div>
        <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="kbd">↑↓</span> navigate
          </span>
          <span className="flex items-center gap-1">
            <span className="kbd">↵</span> open
          </span>
          <span className="ml-auto">Live search · backend-ranked</span>
        </div>
      </div>
    </div>
  );
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return { open, setOpen };
}
