'use client';

import { cn, formatPrice, formatPercent, formatVolume, getChangeColor } from '@/lib/utils';
import type { ScreenerResult, WatchlistItem } from '@/types';
import { Button } from './button';
import { PlusCircle, MinusCircle, ExternalLink } from 'lucide-react';

interface StockRowProps {
  stock: ScreenerResult | WatchlistItem;
  showPrediction?: boolean;
  showActions?: boolean;
  onAdd?: () => void;
  onRemove?: () => void;
  onClick?: () => void;
  className?: string;
}

export function StockRow({ 
  stock, 
  showPrediction = true, 
  showActions = false,
  onAdd,
  onRemove,
  onClick,
  className 
}: StockRowProps) {
  const isWatchlist = 'prediction' in stock && !('sector' in stock);
  const changePercent = stock.changePercent;
  const isPositive = changePercent >= 0;
  
  return (
    <div 
      className={cn(
        'flex items-center gap-3 p-3 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors cursor-pointer',
        onClick && 'hover:bg-gray-50 dark:hover:bg-gray-800',
        className
      )}
      onClick={onClick}
    >
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-xs font-medium text-gray-600 dark:text-gray-400">
          {stock.symbol.charAt(0)}
        </div>
        <div className="min-w-0">
          <div className="font-medium text-gray-900 dark:text-white truncate">{stock.name}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
            <span>{stock.symbol}</span>
            {stock.exchange && <span>•</span>}
            {stock.exchange && <span>{stock.exchange}</span>}
            {stock.sector && <><span>•</span><span>{stock.sector}</span></>}
          </div>
        </div>
      </div>
      
      <div className="text-right w-28 shrink-0 hidden sm:block">
        <div className="font-medium text-gray-900 dark:text-white tabular-nums">{formatPrice(stock.price)}</div>
        <div className={cn('text-xs font-medium', getChangeColor(changePercent))}>
          {formatPercent(changePercent)}
        </div>
      </div>
      
      {(stock as WatchlistItem).volume !== undefined && (stock as WatchlistItem).volume !== null && (
        <div className="text-right w-20 shrink-0 hidden md:block text-xs text-gray-500 dark:text-gray-400">
          {formatVolume((stock as WatchlistItem).volume as number)}
        </div>
      )}
      
      {stock.rsi !== undefined && (
        <div className="w-16 shrink-0 hidden lg:block text-center text-xs text-gray-500 dark:text-gray-400">
          RSI: {stock.rsi.toFixed(0)}
        </div>
      )}
      
      {showPrediction && stock.prediction && (
        <div className="w-36 shrink-0 hidden xl:block">
          <div className="flex items-center justify-center gap-2">
            <span className={cn('px-1.5 py-0.5 text-xs font-medium rounded', 
              stock.prediction.direction === 'up' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' :
              stock.prediction.direction === 'down' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' :
              'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
            )}>
              {stock.prediction.direction.toUpperCase()}
            </span>
            <span className="text-xs font-medium tabular-nums text-gray-600 dark:text-gray-400">
              {stock.prediction.probabilities.up}%
            </span>
          </div>
        </div>
      )}
      
      {stock.prediction && (
        <div className="w-24 shrink-0 hidden xl:block text-right">
          <div className="text-xs font-medium tabular-nums text-gray-600 dark:text-gray-400">
            ER: {stock.prediction.expectedReturn >= 0 ? '+' : ''}{stock.prediction.expectedReturn.toFixed(1)}%
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Conf: {stock.prediction.confidence}</div>
        </div>
      )}
      
      {showActions && !isWatchlist && onAdd && (
        <Button 
          size="icon" 
          variant="ghost" 
          className="h-8 w-8 text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30"
          onClick={(e) => { e.stopPropagation(); onAdd(); }}
          aria-label="Add to watchlist"
        >
          <PlusCircle className="h-4 w-4" />
        </Button>
      )}
      
      {showActions && isWatchlist && onRemove && (
        <Button 
          size="icon" 
          variant="ghost" 
          className="h-8 w-8 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          aria-label="Remove from watchlist"
        >
          <MinusCircle className="h-4 w-4" />
        </Button>
      )}
      
      {onClick && (
        <Button 
          size="icon" 
          variant="ghost" 
          className="h-8 w-8 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
          onClick={(e) => { e.stopPropagation(); }}
          aria-label="View details"
        >
          <ExternalLink className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

interface StockTableProps {
  stocks: (ScreenerResult | WatchlistItem)[];
  showPrediction?: boolean;
  showActions?: boolean;
  onAdd?: (symbol: string) => void;
  onRemove?: (symbol: string) => void;
  onRowClick?: (symbol: string) => void;
  loading?: boolean;
  emptyMessage?: string;
  className?: string;
}

export function StockTable({ 
  stocks, 
  showPrediction = true, 
  showActions = false,
  onAdd,
  onRemove,
  onRowClick,
  loading = false,
  emptyMessage = 'No stocks found',
  className 
}: StockTableProps) {
  if (loading) {
    return (
      <div className={cn('space-y-3', className as string)}>
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-14 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }
  
  if (stocks.length === 0) {
    return (
      <div className={cn('py-12 text-center text-gray-500 dark:text-gray-400', className as string)}>
        {emptyMessage}
      </div>
    );
  }
  
  return (
    <div className={cn('space-y-2', className as string)}>
      {stocks.map((stock) => (
        <StockRow
          key={stock.symbol}
          stock={stock}
          showPrediction={showPrediction}
          showActions={showActions}
          onAdd={() => onAdd?.(stock.symbol)}
          onRemove={() => onRemove?.(stock.symbol)}
          onClick={() => onRowClick?.(stock.symbol)}
        />
      ))}
    </div>
  );
}