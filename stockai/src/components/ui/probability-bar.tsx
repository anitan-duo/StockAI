'use client';

import { cn } from '@/lib/utils';

interface ProbabilityBarProps {
  label: string;
  value: number;
  color: 'up' | 'neutral' | 'down';
  showValue?: boolean;
  className?: string;
}

const COLORS = {
  up: 'bg-green-500',
  neutral: 'bg-amber-500',
  down: 'bg-red-500',
};

const TEXT_COLORS = {
  up: 'text-green-600 dark:text-green-400',
  neutral: 'text-amber-600 dark:text-amber-400',
  down: 'text-red-600 dark:text-red-400',
};

export function ProbabilityBar({ 
  label, 
  value, 
  color, 
  showValue = true,
  className 
}: ProbabilityBarProps) {
  return (
    <div className={cn('w-full', className as string)}>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-medium text-gray-700 dark:text-gray-300">{label}</span>
        {showValue && (
          <span className={cn('font-semibold tabular-nums', TEXT_COLORS[color])}>
            {value}%
          </span>
        )}
      </div>
      <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-500 ease-out', COLORS[color])}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

interface ProbabilityBarGroupProps {
  probabilities: {
    up: number;
    neutral: number;
    down: number;
  };
  className?: string;
}

export function ProbabilityBarGroup({ probabilities, className }: ProbabilityBarGroupProps) {
  return (
    <div className={cn('space-y-3', className as string)}>
      <ProbabilityBar label="UP" value={probabilities.up} color="up" />
      <ProbabilityBar label="NEUTRAL" value={probabilities.neutral} color="neutral" />
      <ProbabilityBar label="DOWN" value={probabilities.down} color="down" />
    </div>
  );
}