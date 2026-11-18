'use client';

import { cn } from '@/lib/utils';

export type TapeItem = {
  symbol: string;
  name?: string;
  price: number;
  change_percent: number;
  freshness?: string;
};

export function MarketTickerTape({ items }: { items: TapeItem[] }) {
  if (!items.length) return null;
  const doubled = [...items, ...items];
  return (
    <div className="ticker-tape overflow-hidden border-y border-border bg-muted/30" aria-label="Market ticker tape">
      <div className="flex w-max animate-[tape_40s_linear_infinite] gap-8 px-4 py-2 hover:[animation-play-state:paused] motion-reduce:animate-none">
        {doubled.map((t, i) => {
          const up = (t.change_percent ?? 0) >= 0;
          const stale = t.freshness === 'stale' || t.freshness === 'unavailable';
          return (
            <span key={`${t.symbol}-${i}`} className="flex items-center gap-2 text-xs tabular-nums">
              <span className="font-semibold">{t.symbol}</span>
              <span className="text-muted-foreground">{Number(t.price).toFixed(2)}</span>
              <span className={cn('font-medium', stale ? 'text-muted-foreground' : up ? 'tick-up' : 'tick-down')}>
                {up ? '+' : ''}{Number(t.change_percent).toFixed(2)}%
                {stale ? ' • stale' : ''}
              </span>
            </span>
          );
        })}
      </div>
      <style>{`@keyframes tape { to { transform: translateX(-50%); } }`}</style>
    </div>
  );
}
