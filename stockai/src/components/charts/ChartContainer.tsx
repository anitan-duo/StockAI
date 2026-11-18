'use client';

/**
 * ChartContainer — backward-compatible adapter over the professional chart
 * engine (ProChart + lightweight-charts).
 *
 * Historical note: this component previously emulated candlesticks with four
 * recharts Line series (no real OHLC rendering). It now delegates to ProChart
 * so every visualization consumes the same verified `HistoricalBar[]` source.
 * Kept API-stable for existing callers; new code should use ProChart directly.
 */

import { ProChart, type ProChartType } from '@/components/charts/ProChart';
import { cn } from '@/lib/utils';
import type { HistoricalBar } from '@/types';

export type ChartType = 'line' | 'area' | 'candlestick' | 'ohlc' | 'baseline';

interface ChartContainerProps {
  data: HistoricalBar[];
  type?: ChartType;
  height?: number;
  showVolume?: boolean;
  indicators?: string[];
  className?: string;
  onCrosshairChange?: (data: HistoricalBar | null) => void;
}

export function ChartContainer({
  data,
  type = 'line',
  height = 400,
  showVolume = true,
  indicators = [],
  className,
  onCrosshairChange,
}: ChartContainerProps) {
  return (
    <ProChart
      data={data}
      chartType={type as ProChartType}
      height={height}
      showVolume={showVolume}
      overlays={indicators}
      className={className}
      onHover={(bar) => onCrosshairChange?.(bar)}
    />
  );
}

interface TimeframeSelectorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export function TimeframeSelector({ value, onChange, className }: TimeframeSelectorProps) {
  // 5D added: backend history is daily bars; 5D = last ~7 daily bars.
  const timeframes = ['1D', '5D', '1M', '3M', '6M', '1Y', '5Y', 'MAX'];

  return (
    <div className={cn('flex max-w-full gap-1 overflow-x-auto p-1 bg-gray-100 dark:bg-gray-800 rounded-lg', className)}>
      {timeframes.map((tf) => (
        <button
          key={tf}
          onClick={() => onChange(tf)}
          className={cn(
            'shrink-0 px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
            value === tf
              ? 'bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          )}
        >
          {tf}
        </button>
      ))}
    </div>
  );
}

interface ChartTypeSelectorProps {
  value: ChartType;
  onChange: (value: ChartType) => void;
  className?: string;
}

export function ChartTypeSelector({ value, onChange, className }: ChartTypeSelectorProps) {
  const types: { value: ChartType; label: string }[] = [
    { value: 'candlestick', label: 'Candles' },
    { value: 'ohlc', label: 'OHLC' },
    { value: 'line', label: 'Line' },
    { value: 'area', label: 'Area' },
    { value: 'baseline', label: 'Baseline' },
  ];

  return (
    <div className={cn('flex max-w-full gap-1 overflow-x-auto p-1 bg-gray-100 dark:bg-gray-800 rounded-lg', className)}>
      {types.map(({ value: v, label }) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className={cn(
            'shrink-0 px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
            value === v
              ? 'bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

interface IndicatorSelectorProps {
  selected: string[];
  onChange: (indicators: string[]) => void;
  className?: string;
}

export function IndicatorSelector({ selected, onChange, className }: IndicatorSelectorProps) {
  const indicators = [
    { id: 'SMA20', label: 'SMA 20' },
    { id: 'SMA50', label: 'SMA 50' },
    { id: 'EMA20', label: 'EMA 20' },
    { id: 'EMA50', label: 'EMA 50' },
    { id: 'VWAP', label: 'VWAP' },
    { id: 'BB', label: 'Bollinger (20,2)' },
  ];

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {indicators.map(({ id, label }) => (
        <label key={id} className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={selected.includes(id)}
            onChange={(e) => onChange(e.target.checked ? [...selected, id] : selected.filter((i) => i !== id))}
            className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
        </label>
      ))}
    </div>
  );
}
