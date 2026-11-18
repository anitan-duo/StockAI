'use client';

import { cn, formatPrice, formatPercent, getChangeColor, formatTimestamp } from '@/lib/utils';
import type { MarketIndex } from '@/types';

interface MarketCardProps {
  index: MarketIndex;
  compact?: boolean;
  className?: string;
}

export function MarketCard({ index, compact = false, className }: MarketCardProps) {
  const isPositive = index.change >= 0;
  
  if (compact) {
    return (
      <div className={cn('p-3 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center justify-between', className as string)}>
        <div>
          <div className="font-medium text-gray-900 dark:text-white text-sm">{index.name}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{index.symbol}</div>
        </div>
        <div className="text-right">
          <div className="font-semibold text-gray-900 dark:text-white text-sm">{formatPrice(index.price)}</div>
          <div className={cn('text-xs font-medium', getChangeColor(index.changePercent))}>
            {formatPercent(index.changePercent)}
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className={cn('p-4 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700', className as string)}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-semibold text-gray-900 dark:text-white">{index.name}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{index.symbol} • {index.status}</div>
        </div>
        <span className={cn('px-2 py-0.5 text-xs font-medium rounded', 
          index.status === 'open' 
            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' 
            : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300'
        )}>
          {index.status}
        </span>
      </div>
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{formatPrice(index.price)}</div>
          <div className={cn('text-sm font-medium mt-1', getChangeColor(index.changePercent))}>
            {index.change >= 0 ? '+' : ''}{formatPrice(index.change)} ({formatPercent(index.changePercent)})
          </div>
        </div>
        <div className="text-right text-xs text-gray-500 dark:text-gray-400">
          Updated {formatTimestamp(index.timestamp)}
        </div>
      </div>
    </div>
  );
}

interface MarketMoverCardProps {
  mover: {
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    volume: number;
  };
  className?: string;
}

export function MarketMoverCard({ mover, className }: MarketMoverCardProps) {
  const isPositive = mover.change >= 0;
  
  return (
    <div className={cn('p-3 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-colors', className as string)}>
      <div className="flex items-center justify-between">
        <div className="min-w-0">
          <div className="font-medium text-gray-900 dark:text-white truncate">{mover.name}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{mover.symbol}</div>
        </div>
        <div className="text-right ml-3">
          <div className="text-sm font-semibold text-gray-900 dark:text-white tabular-nums">{formatPrice(mover.price)}</div>
          <div className={cn('text-xs font-medium', getChangeColor(mover.changePercent))}>
            {formatPercent(mover.changePercent)}
          </div>
        </div>
      </div>
      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        Vol: {formatVolume(mover.volume)}
      </div>
    </div>
  );
}

function formatVolume(volume: number): string {
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
  return volume.toString();
}