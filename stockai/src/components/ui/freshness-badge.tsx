'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { freshnessStyle, normalizeFreshness, relativeAge } from '@/lib/freshness';

interface FreshnessBadgeProps {
  /** Backend-classified freshness value from QuoteResponse.freshness */
  freshness: string | null | undefined;
  /** Provider-reported source timestamp (ISO) for the relative age label */
  sourceTimestamp?: string | null;
  size?: 'sm' | 'md';
  showAge?: boolean;
  className?: string;
}

/**
 * Displays the backend's authoritative data-status classification.
 * Renders LIVE / RECENT / DELAYED / STALE / DATA UNAVAILABLE with an
 * optional relative age ("Updated 4s ago"). Never derives staleness
 * client-side.
 */
export function FreshnessBadge({
  freshness,
  sourceTimestamp,
  size = 'md',
  showAge = true,
  className,
}: FreshnessBadgeProps) {
  const style = freshnessStyle(freshness);
  const [, setTick] = useState(0);

  // Re-render every 5s so the relative age stays current.
  useEffect(() => {
    if (!showAge || !sourceTimestamp) return;
    const id = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, [showAge, sourceTimestamp]);

  const age = showAge ? relativeAge(sourceTimestamp) : null;

  return (
    <span
      role="status"
      aria-label={`${style.ariaLabel}${age ? `, updated ${age}` : ''}`}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-semibold uppercase tracking-wide',
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]',
        style.className,
        className
      )}
      data-freshness={normalizeFreshness(freshness)}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', style.dotClassName)} aria-hidden="true" />
      {style.label}
      {age && <span className="font-normal normal-case tracking-normal opacity-80">· {age}</span>}
    </span>
  );
}