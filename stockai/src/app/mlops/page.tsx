'use client';

/**
 * Model operations: champion, experiments, jobs, promotions, drift.
 * Reads require sign-in; approve/reject/rollback/trigger are admin-only
 * (server-enforced — the UI additionally hides those controls).
 * Every number comes from /api/v1/mlops; empty states are explicit.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { LearningLoopCard } from '@/components/mlops/learning-loop-card';
import { ModelHealthPanel } from '@/components/mlops/model-health-panel';
import { pct, num } from '@/lib/learningLoop';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Cpu, FlaskConical, History, ShieldCheck, ShieldAlert, Bell, RefreshCw,
  CheckCheck, XCircle, Undo2, Play, Lock,
} from 'lucide-react';

function shortSha(s?: string | null) {
  if (!s) return '—';
  return s.length > 19 ? `${s.slice(0, 19)}…` : s;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: 'bg-emerald-500/10 text-emerald-600',
    approved: 'bg-emerald-500/10 text-emerald-600',
    candidate: 'bg-blue-500/10 text-blue-600',
    shadow: 'bg-violet-500/10 text-violet-600',
    training: 'bg-amber-500/10 text-amber-600',
    evaluating: 'bg-amber-500/10 text-amber-600',
    research: 'bg-muted text-muted-foreground',
    rejected: 'bg-red-500/10 text-red-600',
    failed: 'bg-red-500/10 text-red-600',
    retired: 'bg-muted text-muted-foreground',
    succeeded: 'bg-emerald-500/10 text-emerald-600',
    running: 'bg-blue-500/10 text-blue-600',
    queued: 'bg-muted text-muted-foreground',
  };
  return (
    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-bold uppercase', styles[status] ?? 'bg-muted text-muted-foreground')}>
      {status}
    </span>
  );
}

export default function MLOpsPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [champion, setChampion] = useState<any>(null);
  const [experiments, setExperiments] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [promotions, setPromotions] = useState<any[]>([]);
  const [monitoring, setMonitoring] = useState<any>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const [rationale, setRationale] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    if (!api.isAuthenticated()) {
      setAuthed(false);
      setLoading(false);
      return;
    }
    try {
      const me = await api.getMe().catch(() => null);
      if (!me) {
        setAuthed(false);
        return;
      }
      setAuthed(true);
      setIsAdmin(!!(me as any).is_superuser);
      const [ch, ex, jb, pr, mo] = await Promise.all([
        api.getChampion().catch((e: any) => ({ _error: e.message })),
        api.getExperiments(undefined, 30).catch((e: any) => ({ _error: e.message })),
        api.getTrainingJobs(undefined, 20).catch((e: any) => ({ _error: e.message })),
        api.getPromotions(20).catch((e: any) => ({ _error: e.message })),
        api.getMlMonitoring().catch((e: any) => ({ _error: e.message })),
      ]);
      setChampion(ch);
      setExperiments(Array.isArray((ex as any)?.experiments) ? (ex as any).experiments : []);
      setJobs(Array.isArray((jb as any)?.jobs) ? (jb as any).jobs : []);
      setPromotions(Array.isArray((pr as any)?.promotions) ? (pr as any).promotions : []);
      setMonitoring(mo);
    } catch (e: any) {
      setError(e.message || 'Failed to load MLOps state');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (fn: () => Promise<any>, label: string) => {
    setActing(true);
    setActionMsg(null);
    try {
      const r = await fn();
      setActionMsg(`${label}: ${r?.status ?? 'done'}`);
      await load();
    } catch (e: any) {
      setActionMsg(`${label} failed: ${e.message}`);
    } finally {
      setActing(false);
    }
  };

  if (loading || authed === null) {
    return (
      <div className="mx-auto max-w-[1100px] space-y-4 p-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="mx-auto max-w-[720px] p-6">
        <Card>
          <CardContent className="empty-state">
            <Lock className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="empty-state-title">Sign in to view model operations</p>
            <p className="empty-state-description">Champion status, experiments, and drift monitoring require an account.</p>
            <div className="mt-4 flex gap-2">
              <Link href="/login"><Button>Sign in</Button></Link>
              <Link href="/signup"><Button variant="outline">Create account</Button></Link>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const confirmed = (monitoring as any)?.confirmed ?? {};
  const provisional = (monitoring as any)?.provisional ?? {};
  const openAlerts: any[] = (monitoring as any)?.open_alerts ?? [];

  return (
    <div className="terminal-surface min-h-screen">
      <div className="mx-auto max-w-[1100px] space-y-6 p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
              <Cpu className="h-6 w-6" /> Model operations
            </h1>
            <p className="text-sm text-muted-foreground">
              Champion, challengers, jobs, promotions, drift — every number from the backend, nothing invented.
            </p>
          </div>
          <div className="flex gap-2">
            {isAdmin && (
              <Button variant="outline" size="sm" disabled={acting} onClick={() => act(() => api.triggerEvolution(), 'Evolution cycle')}>
                <Play className="mr-1 h-3.5 w-3.5" /> Run evolution cycle
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => load()}>
              <RefreshCw className="mr-1 h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <ShieldAlert className="h-4 w-4" />
            <AlertTitle>Failed to load</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {actionMsg && (
          <Alert>
            <AlertDescription>{actionMsg}</AlertDescription>
          </Alert>
        )}
        {!isAdmin && (
          <Alert>
            <Lock className="h-4 w-4" />
            <AlertDescription>
              Signed in with a non-admin account: approve, reject, rollback, and manual evolution runs are hidden. Reads remain available.
            </AlertDescription>
          </Alert>
        )}

        {/* Champion */}
        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="h-4 w-4 text-emerald-500" /> Production champion
            </CardTitle>
            <CardDescription>Exactly one current champion; artifact hash verified against the file.</CardDescription>
          </CardHeader>
          <CardContent>
            {champion?._error ? (
              <p className="text-sm text-muted-foreground">Champion unavailable: {champion._error}</p>
            ) : champion ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <p className="text-xs text-muted-foreground">Model / version</p>
                  <p className="font-mono text-sm font-bold">{champion.model ?? '—'} / {champion.version ?? '—'}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Artifact SHA</p>
                  <p className="font-mono text-sm" title={champion.artifact_sha}>{shortSha(champion.artifact_sha)}</p>
                  <p className={cn('text-xs font-semibold', champion.artifact_verified ? 'tick-up' : 'tick-down')}>
                    {champion.artifact_verified ? '✓ hash verified' : '✗ NOT verified'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Status</p>
                  <StatusBadge status={champion.status ?? 'unknown'} />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Approved</p>
                  <p className="text-sm">{champion.approved_at ? new Date(champion.approved_at).toLocaleDateString() : '—'}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No champion recorded.</p>
            )}
            {isAdmin && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Input
                  placeholder="Rationale for rollback (required for audit)"
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  className="max-w-sm"
                />
                <Button
                  variant="outline"
                  size="sm"
                  disabled={acting || !rationale.trim()}
                  onClick={() => act(() => api.rollbackChampion(rationale.trim()), 'Rollback')}
                >
                  <Undo2 className="mr-1 h-3.5 w-3.5" /> Roll back to previous champion
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Model health & trust center (Phase 12) */}
        <ModelHealthPanel monitoring={monitoring} champion={champion} />

        {/* Monitoring */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Confirmed performance (matured outcomes, 30d)</CardTitle>
              <CardDescription>Resolved labels only — provisional signals never count as evidence.</CardDescription>
            </CardHeader>
            <CardContent>
              {(monitoring as any)?._error ? (
                <p className="text-sm text-muted-foreground">Monitoring unavailable: {(monitoring as any)._error}</p>
              ) : (
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between"><span>Matured outcomes</span><b className="tabular-nums">{confirmed.n_matured_30d ?? '—'}</b></div>
                  <div className="flex justify-between"><span>Directional accuracy</span><b className="tabular-nums">{pct(confirmed.accuracy_30d)}</b></div>
                  <div className="flex justify-between"><span>Brier (3-class)</span><b className="tabular-nums">{num(confirmed.brier_30d, 3)}</b></div>
                  <div className="flex justify-between"><span>Directional calls</span><b className="tabular-nums">{confirmed.directional_n_30d ?? '—'}</b></div>
                  <div className="flex justify-between"><span>Neutral predictions</span><b className="tabular-nums">{confirmed.neutral_predictions_30d ?? '—'}</b></div>
                  <div className="flex justify-between"><span>Covered instruments (24h)</span><b className="tabular-nums">{provisional.instruments_covered_24h ?? '—'}/{provisional.instruments_active ?? '—'}</b></div>
                  <div className="flex justify-between"><span>Pending outcomes</span><b className="tabular-nums">{provisional.predictions_pending_outcome ?? '—'}</b></div>
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><Bell className="h-4 w-4" /> Drift alerts ({openAlerts.length})</CardTitle>
              <CardDescription>Alarms fire on confirmed metrics with minimum samples; acknowledging is audit-visible.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {openAlerts.length === 0 && <p className="py-3 text-center text-sm text-muted-foreground">No open alerts.</p>}
              {openAlerts.map((a: any) => (
                <div key={a.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-border p-2 text-sm">
                  <span className="font-mono font-bold">{a.scope}/{a.metric}</span>
                  <span className="tabular-nums">{a.value} vs {a.threshold}</span>
                  <Button size="sm" variant="outline" className="ml-auto" onClick={() => act(() => api.acknowledgeDrift(a.id), 'Acknowledge')}>
                    <CheckCheck className="mr-1 h-3.5 w-3.5" /> Acknowledge
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        <LearningLoopCard monitoring={monitoring} />

        {/* Experiments */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><FlaskConical className="h-4 w-4" /> Experiments ({experiments.length})</CardTitle>
            <CardDescription>Immutable registry: hypotheses, metrics, artifacts, decisions. Failures preserved.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {experiments.length === 0 && <p className="py-3 text-center text-sm text-muted-foreground">No experiments recorded yet.</p>}
            {experiments.map((e: any) => (
              <div key={e.id} className="rounded-xl border border-border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-bold">{e.experiment_id}</span>
                  <StatusBadge status={e.status} />
                  <span className="ml-auto flex gap-2">
                    {isAdmin && (e.status === 'candidate' || e.status === 'shadow') && (
                      <>
                        <Button size="sm" onClick={() => act(() => api.approveExperiment(e.experiment_id, rationale.trim() || `approved ${e.experiment_id}`), 'Approve')} disabled={acting}>
                          Approve & promote
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => act(() => api.rejectExperiment(e.experiment_id, rationale.trim() || 'rejected by operator'), 'Reject')} disabled={acting}>
                          <XCircle className="mr-1 h-3.5 w-3.5" /> Reject
                        </Button>
                      </>
                    )}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{e.hypothesis}</p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
                  <span>acc {(e.metrics as any)?.accuracy ?? (e.metrics as any)?.baseline_full_iso?.accuracy ?? '—'}</span>
                  <span>sha {shortSha(e.artifact_sha_full)}</span>
                  <span>{e.feature_set} · {e.target} · {e.horizon}</span>
                </div>
                {e.decision && <p className="mt-1 text-xs"><b>{e.decision}:</b> {e.decision_reason}</p>}
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Jobs + promotions */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Training jobs ({jobs.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {jobs.length === 0 && <p className="py-3 text-center text-sm text-muted-foreground">No jobs recorded.</p>}
              {jobs.slice(0, 10).map((j: any) => (
                <div key={j.id} className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 font-mono text-xs">
                  <span className="truncate font-bold">{j.job_key}</span>
                  <StatusBadge status={j.status} />
                  <span className="ml-auto text-muted-foreground">{j.attempts}/{j.max_attempts} tries</span>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><History className="h-4 w-4" /> Promotions ({promotions.length})</CardTitle>
              <CardDescription>Every champion switch and rollback, newest first.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {promotions.length === 0 && <p className="py-3 text-center text-sm text-muted-foreground">No promotions yet — v1.0 remains champion.</p>}
              {promotions.slice(0, 10).map((p: any) => (
                <div key={p.id} className="rounded-lg bg-muted/40 px-3 py-2 font-mono text-xs">
                  <span className="font-bold">{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</span>
                  {' → '}
                  <span>{String(p.to_version_id).slice(0, 8)}</span>
                  <span className="ml-2 text-muted-foreground">{p.rationale ?? ''}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
