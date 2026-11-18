'use client';

import { cn } from '@/lib/utils';
import { formatPrice, formatPercent, getChangeColor } from '@/lib/utils';

interface StatCardProps {
  label: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  prefix?: string;
  suffix?: string;
  className?: string;
  trend?: 'up' | 'down' | 'neutral';
}

export function StatCard({ 
  label, 
  value, 
  change, 
  changeLabel,
  prefix = '',
  suffix = '',
  className,
  trend
}: StatCardProps) {
  return (
    <div className={cn('p-4 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700', className as string)}>
      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
        {label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-semibold text-gray-900 dark:text-white tabular-nums">
          {prefix}{value}{suffix}
        </span>
        {change !== undefined && (
          <span className={cn('text-sm font-medium', getChangeColor(change))}>
            {change >= 0 ? '+' : ''}{change.toFixed(2)}%
          </span>
        )}
      </div>
      {changeLabel && (
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {changeLabel}
        </div>
      )}
    </div>
  );
}

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
}

export function MetricCard({ title, value, subtitle, icon, className, action }: MetricCardProps) {
  return (
    <div className={cn('p-5 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700', className as string)}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</div>
          <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{value}</div>
          {subtitle && <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">{subtitle}</div>}
        </div>
        {icon && <div className="text-gray-400">{icon}</div>}
      </div>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}