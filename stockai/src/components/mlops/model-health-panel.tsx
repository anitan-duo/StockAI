'use client';

/**
 * Model Health & Trust Center panel (Phase 12).
 *
 * Every number comes from /api/v1/mlops/monitoring or /api/v1/mlops/champion.
 * Operational states are derived from evidence thresholds only:
 *   HEALTHY              — matured sample large enough AND accuracy reliable.
 *   INSUFFICIENT EVIDENCE— too few matured outcomes (never hide this).
 *   DEGRADED             — reliable sample with accuracy below champion baseline.
 *   STALE DATA           — no matured outcomes in the last 7 days.
 *   NO CLEAR EDGE        — confidence interval spans the neutral rate.
 * A failed or unreachable API renders an explicit UNAVAILABLE state.
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export type HealthState =
  | 'HEALTHY'
  | 'DEGRADED'
  | 'STALE DATA'
  | 'INSUFFICIENT EVIDENCE'
  | 'MODEL DRIFT'
  | 'NO CLEAR EDGE'
  | 'RESEARCH ONLY'
  | 'UNAVAILABLE';

const STATE_STYLES: Record<HealthState, string> = {
  HEALTHY: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  DEGRADED: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
  'STALE DATA': 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  'INSUFFICIENT EVIDENCE': 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  'MODEL DRIFT': 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  'NO CLEAR EDGE': 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300',
  'RESEARCH ONLY': 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  UNAVAILABLE: 'bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400',
};

export function healthStateLabel(s: HealthState) {
  return s;
}

export function HealthBadge({ state }: { state: HealthState }) {
  return (
    <Badge className={cn('rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide', STATE_STYLES[state])}>
      {state}
    </Badge>
  );
}

interface MetricCell {
  n?: number;
  accuracy?: number | null;
  reliable?: boolean;
  ci_low?: number;
  ci_high?: number;
}

function pct(v: unknown): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return `${(Number(v) * 100).toFixed(1)}%`;
}

/**
 * Derive the operational health state. Priority order (most severe first):
 *   1. UNAVAILABLE          — monitoring endpoint failed / no data.
 *   2. RESEARCH ONLY        — no active production champion.
 *   3. MODEL DRIFT          — open confirmed-metric drift alerts.
 *   4. STALE DATA           — no matured outcomes in the last 7 days.
 *   5. INSUFFICIENT EVIDENCE— matured sample below the reliability floor.
 *   6. NO CLEAR EDGE        — accuracy CI spans the 1/3 neutral rate.
 *   7. DEGRADED             — reliable sample, accuracy below 0.5.
 *   8. HEALTHY              — reliable, above chance, CI excludes neutral.
 * Provisional signals (coverage, pending outcomes) never influence the state.
 */
export function deriveHealthState(
  confirmed: any,
  _provisional: any,
  opts?: { hasChampion?: boolean; openAlerts?: any[] }
): HealthState {
  const n = confirmed?.n_matured_30d ?? 0;
  const acc = confirmed?.accuracy_30d;
  const ci = confirmed?.accuracy_ci_30d;
  const recent7 = confirmed?.recent_7d;
  const openAlerts = opts?.openAlerts ?? [];

  if (!confirmed || (confirmed as any)?._error) return 'UNAVAILABLE';
  if (opts?.hasChampion === false) return 'RESEARCH ONLY';
  if (openAlerts.length > 0) return 'MODEL DRIFT';
  if (n === 0) return 'INSUFFICIENT EVIDENCE';
  if (recent7 && recent7.n === 0) return 'STALE DATA';
  if (!confirmed?.accuracy_reliable_30d) return 'INSUFFICIENT EVIDENCE';
  if (typeof acc === 'number' && typeof ci?.lower === 'number' && typeof ci?.upper === 'number') {
    // Neutral rate is 1/3 for a 3-class problem; if the CI spans it there is
    // no demonstrated directional edge.
    if (ci.lower <= 1 / 3 && ci.upper >= 1 / 3) return 'NO CLEAR EDGE';
    if (acc < 0.5) return 'DEGRADED';
    return 'HEALTHY';
  }
  if (typeof acc === 'number' && acc < 0.5) return 'DEGRADED';
  return 'HEALTHY';
}

export function ModelHealthPanel({ monitoring, champion }: { monitoring: any; champion: any }) {
  const confirmed = monitoring?.confirmed ?? {};
  const provisional = monitoring?.provisional ?? {};
  const cal = confirmed?.calibration_30d ?? {};
  const byMarket = confirmed?.by_market ?? {};
  const byVersion = confirmed?.by_model_version ?? {};
  const byRegime = confirmed?.by_regime ?? {};
  const recent = confirmed?.recent_7d ?? {};
  const openAlerts = monitoring?.open_alerts ?? [];
  const state = deriveHealthState(confirmed, provisional, {
    hasChampion: !!champion && !champion._error,
    openAlerts,
  });

  return (
    <div className="space-y-6">
      {/* Operational state banner */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">Model health — operational state</CardTitle>
            <HealthBadge state={state} />
          </div>
          <CardDescription>
            Derived only from matured outcomes (confirmed labels). Provisional signals never count as evidence.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Champion version</p>
            <p className="mt-1 font-semibold tabular-nums">{champion?.version ?? champion?.model_version ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Matured outcomes (30d)</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{confirmed?.n_matured_30d ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Directional accuracy (30d)</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{pct(confirmed?.accuracy_30d)}</p>
            <p className="text-xs text-muted-foreground">
              {confirmed?.directional_n_30d != null ? `n=${confirmed.directional_n_30d} directional` : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">95% CI (Wilson)</p>
            <p className="mt-1 text-sm font-medium tabular-nums">
              {typeof confirmed?.accuracy_ci_30d === 'object' && confirmed?.accuracy_ci_30d
                ? `${pct(confirmed.accuracy_ci_30d.lower)} – ${pct(confirmed.accuracy_ci_30d.upper)}`
                : '—'}
            </p>
            <p className="text-xs text-muted-foreground">
              {confirmed?.accuracy_reliable_30d ? 'sample adequate' : 'sample too small'}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Coverage (24h)</p>
            <p className="mt-1 font-semibold tabular-nums">
              {provisional?.instruments_covered_24h ?? '—'}/{provisional?.instruments_active ?? '—'} instruments
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Brier / log-loss (30d)</p>
            <p className="mt-1 font-semibold tabular-nums">
              {confirmed?.brier_30d != null ? confirmed.brier_30d.toFixed(3) : '—'} /{' '}
              {confirmed?.log_loss_30d != null ? confirmed.log_loss_30d.toFixed(3) : '—'}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Calibration (ECE top)</p>
            <p className="mt-1 font-semibold tabular-nums">{cal?.ece != null ? cal.ece.toFixed(3) : '—'}</p>
            <p className="text-xs text-muted-foreground">{cal?.bins ? `${cal.bins} bins` : '—'}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Trend (7d vs prior 23d)</p>
            <p className="mt-1 font-semibold tabular-nums">
              {recent?.n != null && recent?.prior_23d ? (
                <>
                  {pct(recent.accuracy)} <span className="text-muted-foreground">vs</span> {pct(recent.prior_23d.accuracy)}
                </>
              ) : (
                '—'
              )}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {/* Performance by market */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Performance by market</CardTitle>
            <CardDescription>Matured outcomes grouped by exchange market.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {Object.keys(byMarket).length === 0 ? (
              <p className="py-3 text-center text-muted-foreground">No matured outcomes in window.</p>
            ) : (
              Object.entries(byMarket).map(([m, cell]: [string, any]) => (
                <div key={m} className="flex items-center justify-between">
                  <span className="font-medium">{m}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {pct(cell?.accuracy)} <span className="text-xs">(n={cell?.n ?? 0})</span>
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Performance by regime */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Performance by regime</CardTitle>
            <CardDescription>Volatility / trend regimes from point-in-time features (on/off split).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {Object.keys(byRegime).length === 0 ? (
              <p className="py-3 text-center text-muted-foreground">No regime splits available.</p>
            ) : (
              Object.entries(byRegime).map(([r, cell]: [string, any]) => (
                <div key={r} className="space-y-1">
                  <p className="font-medium">{r}</p>
                  {['on', 'off'].map((k) => {
                    const sub = cell?.[k];
                    if (!sub) return null;
                    return (
                      <div key={k} className="flex items-center justify-between pl-2 text-muted-foreground">
                        <span className="text-xs">{k === 'on' ? 'active' : 'inactive'}</span>
                        <span className="tabular-nums">
                          {pct(sub?.accuracy)} <span className="text-xs">(n={sub?.n ?? 0})</span>
                        </span>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Calibration bins */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Calibration (confidence bins)</CardTitle>
            <CardDescription>Observed accuracy vs mean confidence per bin; gaps reveal over/under-confidence.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!cal?.bins?.length ? (
              <p className="py-3 text-center text-muted-foreground">No calibration bins available.</p>
            ) : (
              cal.bins.map((b: any) => (
                <div key={b.bin} className="flex items-center justify-between">
                  <span className="font-medium">{b.bin}</span>
                  <span className="tabular-nums text-muted-foreground">
                    obs {pct(b?.observed_accuracy)} <span className="text-xs">vs conf {pct(b?.mean_confidence)}</span>
                    <span className="text-xs"> · n={b?.n ?? 0}</span>
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Model version comparison */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">By model version</CardTitle>
            <CardDescription>Failed or weak versions stay visible — never hidden.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {Object.keys(byVersion).length === 0 ? (
              <p className="py-3 text-center text-muted-foreground">No version breakdown available.</p>
            ) : (
              Object.entries(byVersion).map(([v, cell]: [string, any]) => (
                <div key={v} className="flex items-center justify-between">
                  <span className="font-medium tabular-nums">{v}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {pct(cell?.accuracy)} <span className="text-xs">(n={cell?.n ?? 0})</span>
                    {cell?.calibration?.ece != null ? ` · ECE ${cell.calibration.ece.toFixed(3)}` : ''}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Drift / failure signals */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Active drift &amp; failure signals</CardTitle>
          <CardDescription>
            Open drift alerts and recent failure modes. Acknowledging is audit-visible.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          {openAlerts.length === 0 ? (
            <p className="py-2 text-center text-muted-foreground">No open drift alerts.</p>
          ) : (
            <ul className="space-y-1.5">
              {openAlerts.slice(0, 8).map((a: any, i: number) => (
                <li key={a?.id ?? i} className="space-y-0.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="tabular-nums">
                      {a?.scope ?? '—'} · {a?.metric ?? '—'} = {a?.value ?? '—'} (threshold {a?.threshold ?? '—'})
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {a?.observed_at ? new Date(a.observed_at).toLocaleDateString() : ''}
                    </span>
                  </div>
                  {a?.note && <p className="text-xs text-muted-foreground">{a.note}</p>}
                </li>
              ))}
            </ul>
          )}
          {monitoring?.learning?.state && (
            <p className="mt-3 border-t border-border pt-2 text-xs text-muted-foreground">
              Learning-loop state: <b>{monitoring.learning.state}</b> · min matured n={monitoring.learning.min_matured_n} ·{' '}
              {monitoring.learning.next_action}
            </p>
          )}
        </CardContent>
      </Card>

      {state === 'UNAVAILABLE' && (
        <Card>
          <CardContent className="py-4 text-sm text-muted-foreground">
            Model health data unavailable. The monitoring endpoint did not respond; operational state cannot be
            asserted and is therefore reported as UNAVAILABLE rather than assumed healthy.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
