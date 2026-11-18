'use client';

/**
 * Scenario Lab: blind historical training challenges.
 *
 * Blindness is server-enforced: the bars endpoint returns ONLY bars at or
 * before the decision cutoff, predictions commit before any outcome exists,
 * and outcomes reveal from strictly-later sessions. The UI never sees,
 * caches, or displays future data — what you see is what a trader knew.
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api/client';
import { cn } from '@/lib/utils';
import { relativeAge } from '@/lib/freshness';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ProChart } from '@/components/charts/ProChart';
import type { HistoricalBar } from '@/types';
import {
  FlaskConical, Eye, EyeOff, Target, Trophy, History as HistoryIcon,
  AlertTriangle, RefreshCw, Brain, ChevronRight,
} from 'lucide-react';

const HORIZONS = [
  { id: 'h1d', label: '1 session', hint: '±0.5%' },
  { id: 'h5d', label: '5 sessions', hint: '±1.5%' },
  { id: 'h20d', label: '20 sessions', hint: '±3.0%' },
];

const ACTIONS = ['BUY', 'HOLD', 'SELL'] as const;

export default function ScenariosPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  // Setup
  const [symbol, setSymbol] = useState('AAPL');
  const [exchange, setExchange] = useState('NASDAQ');
  const [decisionDate, setDecisionDate] = useState('2025-06-13');
  const [taskId, setTaskId] = useState('h1d');
  const [experimentId, setExperimentId] = useState('LAB-001');
  const [scenario, setScenario] = useState<any>(null);
  const [bars, setBars] = useState<HistoricalBar[]>([]);
  const [loadingBars, setLoadingBars] = useState(false);
  // Forecast
  const [up, setUp] = useState('40');
  const [neutral, setNeutral] = useState('30');
  const [down, setDown] = useState('30');
  const [action, setAction] = useState<(typeof ACTIONS)[number]>('HOLD');
  const [attempt, setAttempt] = useState<any>(null);
  const [revealed, setRevealed] = useState<any>(null);
  const [diagnosis, setDiagnosis] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Sidebar
  const [streaks, setStreaks] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    setAuthed(api.isAuthenticated());
  }, []);

  const loadScenario = useCallback(async () => {
    setBusy(true);
    setError(null);
    setAttempt(null);
    setRevealed(null);
    setDiagnosis(null);
    try {
      const s = await api.createScenario({
        symbol: symbol.trim().toUpperCase(),
        exchange: exchange.trim().toUpperCase(),
        decision_date: decisionDate,
        task_id: taskId,
        split: 'train',
      });
      setScenario(s);
      const b = await api.getScenarioBars(s.id, 400);
      setBars(
        (b.bars ?? []).map((x: any) => ({
          timestamp: x.timestamp, open: x.open, high: x.high,
          low: x.low, close: x.close, volume: x.volume,
        })),
      );
    } catch (e: any) {
      setError(e.message || 'Failed to load scenario');
      setScenario(null);
      setBars([]);
    } finally {
      setBusy(false);
    }
  }, [symbol, exchange, decisionDate, taskId]);

  const refreshSide = useCallback(async () => {
    try {
      const [st, hi] = await Promise.all([
        api.getStreaks(experimentId || 'LAB-001'),
        api.getChallengeAttempts(experimentId || 'LAB-001', 20),
      ]);
      setStreaks(st.streaks ?? []);
      setHistory(hi.attempts ?? []);
    } catch {
      /* sidebar is best-effort */
    }
  }, [experimentId]);

  useEffect(() => {
    if (authed) refreshSide();
  }, [authed, refreshSide]);

  const probSum = [up, neutral, down].reduce((a, v) => a + (parseFloat(v) || 0), 0);
  const probsValid = Math.abs(probSum - 100) < 0.6;

  const submit = async () => {
    if (!scenario) return;
    setBusy(true);
    setError(null);
    try {
      const a = await api.submitChallenge(scenario.id, {
        experiment_id: experimentId || 'LAB-001',
        up: parseFloat(up) / 100,
        neutral: parseFloat(neutral) / 100,
        down: parseFloat(down) / 100,
        action,
      });
      setAttempt(a);
      setRevealed(null);
      setDiagnosis(null);
    } catch (e: any) {
      setError(e.message || 'Submit failed');
    } finally {
      setBusy(false);
    }
  };

  const reveal = async () => {
    if (!attempt) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.revealChallenge(attempt.id);
      setRevealed(r);
      setAttempt(r);
      if (r.correct === false) {
        const d = await api.getAttemptDiagnosis(r.id).catch(() => null);
        setDiagnosis(d);
      }
      await refreshSide();
    } catch (e: any) {
      setError(e.message || 'Reveal failed (outcome may not have matured yet)');
    } finally {
      setBusy(false);
    }
  };

  if (authed === null) {
    return (
      <div className="mx-auto max-w-[1100px] space-y-4 p-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="mx-auto max-w-[720px] p-6">
        <Card>
          <CardContent className="empty-state">
            <EyeOff className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="empty-state-title">Sign in to enter the Scenario Lab</p>
            <p className="empty-state-description">Blind historical challenges require an account so attempts and streaks persist.</p>
            <div className="mt-4 flex gap-2">
              <Link href="/login"><Button>Sign in</Button></Link>
              <Link href="/signup"><Button variant="outline">Create account</Button></Link>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const cutoff = scenario?.data_cutoff ? new Date(scenario.data_cutoff) : null;

  return (
    <div className="terminal-surface min-h-screen">
      <div className="mx-auto max-w-[1200px] space-y-6 p-6">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <FlaskConical className="h-6 w-6" /> Scenario Lab
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Blind historical challenges: the chart ends at the decision cutoff — no future candles,
            ever. Commit a forecast, then reveal the genuine outcome. Streaks count unique scenarios
            only; misses reset. Long-only policy: SELL exits, never shorts.
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Challenge error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            {/* Setup */}
            <Card className="glass-card">
              <CardHeader>
                <CardTitle className="text-base">1 · Pick a decision point</CardTitle>
                <CardDescription>Weekends and holidays map to the last eligible session — never invented.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <label className="text-xs">Symbol<Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="AAPL" /></label>
                <label className="text-xs">Exchange<Input value={exchange} onChange={(e) => setExchange(e.target.value)} placeholder="NASDAQ" /></label>
                <label className="text-xs">Decision date<Input type="date" value={decisionDate} onChange={(e) => setDecisionDate(e.target.value)} /></label>
                <label className="text-xs">Horizon
                  <select value={taskId} onChange={(e) => setTaskId(e.target.value)} className="mt-1 h-10 w-full rounded-md border border-input bg-background px-2 text-sm">
                    {HORIZONS.map((h) => (
                      <option key={h.id} value={h.id}>{h.label} ({h.hint})</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs">Experiment<Input value={experimentId} onChange={(e) => setExperimentId(e.target.value)} placeholder="LAB-001" /></label>
                <div className="sm:col-span-2 lg:col-span-5">
                  <Button onClick={loadScenario} disabled={busy || !symbol.trim() || !decisionDate}>
                    {busy ? 'Loading…' : 'Load blind scenario'}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Blind chart */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <EyeOff className="h-4 w-4" /> Blind chart
                  </CardTitle>
                  <CardDescription>
                    {scenario
                      ? `Ends ${cutoff?.toLocaleDateString() ?? '—'} (UTC ${cutoff?.toISOString().slice(11, 16) ?? ''}) · ${bars.length} bars · target ${scenario.target_version}`
                      : 'No scenario loaded.'}
                  </CardDescription>
                </div>
                {scenario && (
                  <Badge variant="outline" className="font-mono text-[11px]">
                    {scenario.horizon} · {scenario.split}
                  </Badge>
                )}
              </CardHeader>
              <CardContent>
                {loadingBars || (!scenario && !bars.length) ? (
                  <div className="flex h-[300px] items-center justify-center rounded-lg bg-muted/30 text-sm text-muted-foreground">
                    {busy ? 'Loading decision window…' : 'Load a scenario to reveal its (truncated) history.'}
                  </div>
                ) : bars.length === 0 ? (
                  <div className="empty-state">
                    <p className="empty-state-title text-sm">No bars at or before this date</p>
                    <p className="empty-state-description text-xs">Predates coverage — pick a later date. Nothing is synthesized.</p>
                  </div>
                ) : (
                  <ProChart data={bars} chartType="candlestick" height={340} showVolume currency="USD" />
                )}
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Times in UTC. Gaps are non-sessions (never filled).
                </p>
              </CardContent>
            </Card>

            {/* Forecast */}
            <Card className="glass-card">
              <CardHeader>
                <CardTitle className="text-base">2 · Commit a blind forecast</CardTitle>
                <CardDescription>Frozen at commit — the outcome does not exist yet for this attempt.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-3">
                  {(['up', 'neutral', 'down'] as const).map((k) => (
                    <label key={k} className="text-xs capitalize">{k} %<Input
                      value={k === 'up' ? up : k === 'neutral' ? neutral : down}
                      onChange={(e) => (k === 'up' ? setUp : k === 'neutral' ? setNeutral : setDown)(e.target.value)}
                      inputMode="decimal" placeholder="0-100"
                    /></label>
                  ))}
                </div>
                {!probsValid && (
                  <p className="text-xs text-amber-600">Probabilities sum to {probSum.toFixed(1)}% — must total 100%.</p>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  {ACTIONS.map((a) => (
                    <Button key={a} size="sm" variant={action === a ? 'default' : 'outline'} onClick={() => setAction(a)}>
                      {a}
                    </Button>
                  ))}
                  <span className="text-[11px] text-muted-foreground">BUY needs return above costs · SELL exits · HOLD must sit inside the cost band.</span>
                </div>
                <div className="flex gap-2">
                  <Button onClick={submit} disabled={busy || !scenario || !probsValid}>
                    Commit forecast
                  </Button>
                  <Button variant="outline" onClick={reveal} disabled={busy || !attempt || !!revealed}>
                    <Eye className="mr-1 h-3.5 w-3.5" /> Reveal outcome
                  </Button>
                </div>
                {attempt?.is_repeat && (
                  <p className="text-xs text-amber-600">Repeat attempt on this scenario — recorded, but it will not extend streaks.</p>
                )}
                {revealed && (
                  <Alert className={revealed.correct ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/20' : ''}>
                    <Target className="h-4 w-4" />
                    <AlertTitle>
                      {revealed.correct ? 'Correct decision' : 'Incorrect decision'}
                      {' · '}
                      {revealed.actual_direction?.toUpperCase()} {revealed.actual_return_pct >= 0 ? '+' : ''}{revealed.actual_return_pct}%
                    </AlertTitle>
                    <AlertDescription className="text-xs">
                      {revealed.correct
                        ? 'Logged to the streak (unique scenarios only).'
                        : 'Miss logged — streak reset. Diagnosis below.'}
                    </AlertDescription>
                  </Alert>
                )}
                {diagnosis && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <Brain className="h-4 w-4" /> Error diagnosis: {diagnosis.category}
                      </CardTitle>
                      <CardDescription className="text-xs">Hypothesis with confidence {diagnosis.confidence} — not a verdict.</CardDescription>
                    </CardHeader>
                    <CardContent className="text-xs">
                      <pre className="overflow-x-auto rounded bg-muted/50 p-2 font-mono text-[11px]">{JSON.stringify(diagnosis.evidence, null, 1)}</pre>
                      {diagnosis.alternatives?.length > 0 && (
                        <p className="mt-1 text-muted-foreground">Alternatives: {diagnosis.alternatives.join(', ')}</p>
                      )}
                    </CardContent>
                  </Card>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><Trophy className="h-4 w-4" /> 10/10 streak</CardTitle>
                <CardDescription>Unique scenarios only. A miss resets the run.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {streaks.length === 0 && <p className="text-sm text-muted-foreground">No attempts yet for this experiment.</p>}
                {streaks.map((s: any) => (
                  <div key={s.streak_key} className="rounded-xl border border-border p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold">{s.horizon}</span>
                      {s.completed_10_of_10
                        ? <Badge className="bg-emerald-500/10 text-emerald-600">10/10 COMPLETE</Badge>
                        : <span className="text-sm font-bold tabular-nums">{s.current}/10</span>}
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                      <div className="h-full bg-primary transition-all" style={{ width: `${Math.min(100, (s.current / 10) * 100)}%` }} />
                    </div>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {s.attempts} attempts · {s.unique_scenarios} unique · {s.correct_count}✓ {s.incorrect_count}✗ · longest {s.longest}
                    </p>
                  </div>
                ))}
                <Button variant="outline" size="sm" onClick={refreshSide} className="w-full">
                  <RefreshCw className="mr-1 h-3.5 w-3.5" /> Refresh
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><HistoryIcon className="h-4 w-4" /> Challenge history</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {history.length === 0 && <p className="text-sm text-muted-foreground">Nothing committed yet.</p>}
                {history.slice(0, 12).map((h: any) => (
                  <div key={h.id} className="flex items-center gap-2 rounded-lg bg-muted/40 px-2 py-1.5 text-xs">
                    <span className={cn(
                      'rounded-full px-1.5 py-0.5 text-[10px] font-bold',
                      h.correct === true ? 'bg-emerald-500/10 text-emerald-600'
                        : h.correct === false ? 'bg-red-500/10 text-red-600'
                          : 'bg-muted text-muted-foreground',
                    )}>
                      {h.correct === true ? '✓' : h.correct === false ? '✗' : '…'}
                    </span>
                    <span className="font-mono font-bold">{h.action}</span>
                    <span className="text-muted-foreground">{h.horizon}{h.is_repeat ? ' · repeat' : ''}</span>
                    <Link href="#" onClick={(e) => e.preventDefault()} className="ml-auto flex items-center gap-0.5 text-muted-foreground">
                      {h.actual_return_pct != null ? `${h.actual_return_pct >= 0 ? '+' : ''}${h.actual_return_pct}%` : 'unrevealed'}
                      <ChevronRight className="h-3 w-3" />
                    </Link>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
