'use client';

/**
 * Expandable "Why StockAI Made This Prediction" panel.
 *
 * Fetches the immutable explanation for the exact prediction id shown on the
 * page. A response is only rendered when its prediction_id matches the current
 * prediction (prevents stale explanations after a refresh/navigation).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import {
  explanationMatchesPrediction,
  contributionPoints,
  contributionBarWidth,
  type PredictionExplanation,
} from '@/lib/predictionExplanation';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Brain,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Info,
  CheckCircle2,
  TrendingUp,
  TrendingDown,
  Minus,
  ShieldQuestion,
} from 'lucide-react';

type Props = {
  predictionId?: string | null;
  className?: string;
};

function pct(v: number | undefined): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '—';
}

function directionIcon(direction: string) {
  if (direction === 'up') return <TrendingUp className="h-3.5 w-3.5" />;
  if (direction === 'down') return <TrendingDown className="h-3.5 w-3.5" />;
  return <Minus className="h-3.5 w-3.5" />;
}

export function PredictionExplanationPanel({ predictionId, className }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<PredictionExplanation | null>(null);
  const requestRef = useRef(0);

  const load = useCallback(async () => {
    if (!predictionId) return;
    const request = ++requestRef.current;
    setLoading(true);
    setError(null);
    try {
      const payload = (await api.getPredictionExplanation(predictionId)) as PredictionExplanation;
      if (request !== requestRef.current) return;
      if (!explanationMatchesPrediction(payload, predictionId)) {
        setPayload(null);
        setError('Explanation did not match the displayed prediction. Refresh to retry.');
        return;
      }
      setPayload(payload);
    } catch (e: unknown) {
      if (request !== requestRef.current) return;
      setPayload(null);
      setError(e instanceof Error ? e.message : 'Explanation unavailable');
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }, [predictionId]);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [open, predictionId, load]);

  const current = explanationMatchesPrediction(payload, predictionId) ? payload : null;
  const maxAbs = current
    ? Math.max(
        1e-9,
        ...current.top_positive.map((c) => Math.abs(c.contribution)),
        ...current.top_negative.map((c) => Math.abs(c.contribution)),
      )
    : 1;

  return (
    <div className={cn('rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <Brain className="h-4 w-4 text-violet-600 dark:text-violet-300" />
        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Why StockAI Made This Prediction
        </span>
        {!predictionId && (
          <Badge variant="outline" className="ml-2 text-[10px]">
            no prediction id
          </Badge>
        )}
        <span className="ml-auto text-slate-500 dark:text-slate-400">
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-slate-100 px-4 py-4 dark:border-slate-800">
          {!predictionId ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              No saved prediction id is available, so a faithful explanation cannot be produced.
            </p>
          ) : loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : error ? (
            <Alert className="py-2">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle className="text-xs">Explanation unavailable</AlertTitle>
              <AlertDescription className="text-xs space-y-2">
                <p>{error}</p>
                <Button size="sm" variant="outline" className="h-6" onClick={() => void load()}>
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : current ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  className={cn(
                    'gap-1',
                    current.predicted_direction === 'up' && 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
                    current.predicted_direction === 'down' && 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
                    current.predicted_direction === 'neutral' && 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
                  )}
                >
                  {directionIcon(current.predicted_direction)}
                  {current.predicted_direction.toUpperCase()}
                </Badge>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  up {pct(current.served_probabilities.up)} · neutral {pct(current.served_probabilities.neutral)} · down {pct(current.served_probabilities.down)}
                </span>
                {current.no_clear_edge && (
                  <Badge variant="outline" className="border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-300">
                    NO CLEAR EDGE
                  </Badge>
                )}
                {current.reconciliation.matches_model_output && (
                  <span className="ml-auto inline-flex items-center gap-1 text-[11px] text-emerald-700 dark:text-emerald-300">
                    <CheckCircle2 className="h-3.5 w-3.5" /> contributions reconcile
                  </span>
                )}
              </div>

              <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                {current.narrative.summary}
              </p>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                    Main supporting factors
                  </h4>
                  {current.top_positive.length === 0 ? (
                    <p className="text-xs text-slate-500">No positive contributors.</p>
                  ) : (
                    <ul className="space-y-2">
                      {current.top_positive.map((c) => (
                        <li key={c.feature}>
                          <div className="flex items-baseline justify-between gap-2 text-xs">
                            <span className="truncate text-slate-700 dark:text-slate-300">{c.label}</span>
                            <span className="font-mono tabular-nums text-emerald-700 dark:text-emerald-300">
                              +{contributionPoints(c.contribution).toFixed(1)} pts
                            </span>
                          </div>
                          <div className="mt-1 flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-slate-100 dark:bg-slate-800">
                              <div
                                className="h-1.5 rounded-full bg-emerald-500"
                                style={{ width: `${contributionBarWidth(c.contribution, maxAbs)}%` }}
                              />
                            </div>
                            <span className="w-24 truncate font-mono text-[10px] text-slate-500">{c.formatted_value}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-red-700 dark:text-red-300">
                    Main opposing factors
                  </h4>
                  {current.top_negative.length === 0 ? (
                    <p className="text-xs text-slate-500">No opposing contributors.</p>
                  ) : (
                    <ul className="space-y-2">
                      {current.top_negative.map((c) => (
                        <li key={c.feature}>
                          <div className="flex items-baseline justify-between gap-2 text-xs">
                            <span className="truncate text-slate-700 dark:text-slate-300">{c.label}</span>
                            <span className="font-mono tabular-nums text-red-700 dark:text-red-300">
                              {contributionPoints(c.contribution).toFixed(1)} pts
                            </span>
                          </div>
                          <div className="mt-1 flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-slate-100 dark:bg-slate-800">
                              <div
                                className="h-1.5 rounded-full bg-red-500"
                                style={{ width: `${contributionBarWidth(c.contribution, maxAbs)}%` }}
                              />
                            </div>
                            <span className="w-24 truncate font-mono text-[10px] text-slate-500">{c.formatted_value}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              {current.narrative.limiting_factors.length > 0 && (
                <div>
                  <h4 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
                    <ShieldQuestion className="h-3.5 w-3.5" /> What limited this forecast
                  </h4>
                  <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-400">
                    {current.narrative.limiting_factors.map((f, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {(current.missing_features.length > 0 || current.unreliable_features.length > 0) && (
                <Alert className="py-2">
                  <Info className="h-4 w-4" />
                  <AlertTitle className="text-xs">Input quality</AlertTitle>
                  <AlertDescription className="text-xs">
                    {current.missing_features.length > 0 && (
                      <p>Missing features: {current.missing_features.join(', ')}</p>
                    )}
                    {current.unreliable_features.length > 0 && (
                      <p>Out-of-distribution inputs: {current.unreliable_features.slice(0, 8).join(', ')}</p>
                    )}
                  </AlertDescription>
                </Alert>
              )}

              <div className="grid gap-x-4 gap-y-1 border-t border-slate-100 pt-3 text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400 sm:grid-cols-2">
                <span>Explainer: <span className="font-mono">{current.explainer.method}</span> ({current.explainer.library})</span>
                <span>Model: <span className="font-mono">{current.model_version}</span></span>
                <span>Artifact: <span className="font-mono">{current.artifact_sha.slice(0, 19)}…</span></span>
                <span>Feature hash: <span className="font-mono">{current.feature_vector_hash.slice(0, 19)}…</span></span>
                <span>Prediction: {new Date(current.prediction_timestamp).toLocaleString()}</span>
                <span>Generated: {new Date(current.generated_at).toLocaleString()}</span>
              </div>

              <div className="space-y-1 rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500 dark:bg-slate-950/50 dark:text-slate-400">
                {current.narrative.caveats.map((c, i) => (
                  <p key={i}>{c}</p>
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
