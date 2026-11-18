import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  // Base-ui render-prop classNames can arrive as functions; drop those.
  const sanitized = inputs.map((input) =>
    typeof input === 'function' ? undefined : input,
  ) as ClassValue[];
  return twMerge(clsx(...sanitized));
}

export function formatPrice(price: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

export function formatChange(value: number, showSign: boolean = true): string {
  const sign = value >= 0 && showSign ? '+' : '';
  return `${sign}${value.toFixed(2)}`;
}

export function formatPercent(value: number, showSign: boolean = true): string {
  const sign = value >= 0 && showSign ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatVolume(volume: number): string {
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
  return volume.toString();
}

export function formatMarketCap(marketCap: number): string {
  if (marketCap >= 1e12) return `${(marketCap / 1e12).toFixed(1)}T`;
  if (marketCap >= 1e9) return `${(marketCap / 1e9).toFixed(1)}B`;
  if (marketCap >= 1e6) return `${(marketCap / 1e6).toFixed(1)}M`;
  return marketCap.toString();
}

export function getChangeColor(value: number): string {
  if (value > 0) return 'text-green-600 dark:text-green-400';
  if (value < 0) return 'text-red-600 dark:text-red-400';
  return 'text-gray-600 dark:text-gray-400';
}

export function getChangeBgColor(value: number): string {
  if (value > 0) return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300';
  if (value < 0) return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
  return 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300';
}

export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  });
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatShortDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

export function calculatePercentageChange(current: number, previous: number): number {
  if (previous === 0) return 0;
  return ((current - previous) / previous) * 100;
}

export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;
  
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + '...';
}

export function generateId(): string {
  return Math.random().toString(36).substring(2, 15);
}

export const TIMEFRAMES = [
  { value: '1D', label: '1D', days: 1 },
  { value: '1W', label: '1W', days: 7 },
  { value: '1M', label: '1M', days: 30 },
  { value: '3M', label: '3M', days: 90 },
  { value: '6M', label: '6M', days: 180 },
  { value: '1Y', label: '1Y', days: 365 },
  { value: '5Y', label: '5Y', days: 1825 },
  { value: 'MAX', label: 'MAX', days: 3650 },
] as const;

export type TimeframeValue = typeof TIMEFRAMES[number]['value'];

export const MARKETS = [
  { value: 'us', label: 'United States', code: 'US' },
  { value: 'india', label: 'India', code: 'IN' },
  { value: 'europe', label: 'Europe', code: 'EU' },
] as const;