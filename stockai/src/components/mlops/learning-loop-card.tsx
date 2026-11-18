'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  calibrationGap,
  calibrationVerdict,
  learningStateLabel,
  num,
  pct,
  type MonitorSnapshot,
} from '@/lib/learningLoop';
import { Activity, ShieldCheck, Info } from 'lucide-react';

export function LearningLoopCard({ monitoring }: { monitoring: MonitorSnapshot | null }) {
  const confirmed = monitoring?.confirmed ?? {};
  const learning = monitoring?.learning ?? {};
  const provisional = monitoring?.provisional ?? {};
  const bins = confirmed.calibration_30d?.bins ?? [];
  const versions = Object.entries(confirmed.by_model_version ?? {});
  const regime = Object.entries(confirmed.by_regime ?? {});
  const mature = confirmed.n_matured_30d ?? 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4" /> Learning loop
          </CardTitle>
          <Badge variant="outline" className="text-[10px] uppercase">
            {learningStateLabel(learning.state)}
          </Badge>
          <Badge variant="outline" className="ml-auto gap-1 text-[10px]">
            <ShieldCheck className="h-3 w-3" /> no auto-promotion
          </Badge>
        </div>
        <CardDescription>
          Matured, resolved outcomes only. Provisional freshness signals are shown separately and never count as
          evidence. Diagnostics do not retrain or promote a model.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Matured outcomes (30d)" value={String(mature)} />
          <Metric label="Accuracy" value={pct(confirmed.accuracy_30d)} />
          <Metric label="ECE calibration" value={num(confirmed.ece_30d, 3)} />
          <Metric
            label="Median resolution"
            value={confirmed.latency_hours_median != null ? `${confirmed.latency_hours_median.toFixed(1)} h` : '—'}
          />
          <Metric label="Per-class Brier" value={num(confirmed.brier_30d, 3)} />
          <Metric label="Log loss" value={num(confirmed.log_loss_30d, 3)} />
          <Metric label="Coverage (24h)" value={pct(provisional.coverage_24h)} />
          <Metric label="Pending outcomes" value={String(provisional.predictions_pending_outcome ?? '—')} />
        </div>

        <p className="text-xs text-muted-foreground">{calibrationVerdict(confirmed.ece_30d, mature)}</p>

        {bins.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Stated confidence</th>
                  <th className="px-3 py-2">n</th>
                  <th className="px-3 py-2">Observed hit rate</th>
                  <th className="px-3 py-2">Gap</th>
                </tr>
              </thead>
              <tbody>
                {bins.map((b) => {
                  const gap = calibrationGap(b);
                  return (
                    <tr key={b.bin} className="border-t border-border/60">
                      <td className="px-3 py-2 font-mono">{b.bin}</td>
                      <td className="px-3 py-2 tabular-nums">{b.n}</td>
                      <td className="px-3 py-2 tabular-nums">{pct(b.observed_accuracy)}</td>
                      <td
                        className={`px-3 py-2 tabular-nums ${
                          gap != null && Math.abs(gap) > 0.08 ? 'text-amber-600' : ''
                        }`}
                      >
                        {gap == null ? '—' : `${gap >= 0 ? '+' : ''}${(gap * 100).toFixed(1)} pts`}
                        {!b.reliable && b.n > 0 ? (
                          <span className="ml-1 text-[9px] text-muted-foreground">small n</span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {(versions.length > 0 || regime.length > 0) && (
          <div className="grid gap-3 text-xs sm:grid-cols-2">
            {versions.length > 0 && (
              <div className="rounded-lg border border-border p-2">
                <div className="mb-1 font-semibold">By model version</div>
                {versions.map(([name, cell]) => (
                  <div key={name} className="flex justify-between gap-2 py-0.5">
                    <span className="truncate font-mono">{name}</span>
                    <span className="tabular-nums text-muted-foreground">
                      n {cell.n} · acc {pct(cell.accuracy)} · brier {num(cell.brier)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {regime.length > 0 && (
              <div className="rounded-lg border border-border p-2">
                <div className="mb-1 font-semibold">By regime</div>
                {regime.map(([name, cell]) => (
                  <div key={name} className="flex justify-between gap-2 py-0.5">
                    <span className="truncate">{name.replaceAll('_', ' ')}</span>
                    <span className="tabular-nums text-muted-foreground">
                      on {pct(cell.on?.accuracy)} (n {cell.on?.n ?? 0}) · off {pct(cell.off?.accuracy)} (n {cell.off?.n ?? 0})
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {confirmed.recent_7d && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>
              Last 7d: {pct(confirmed.recent_7d.accuracy)} (n {confirmed.recent_7d.n}) vs prior 23d{' '}
              {pct(confirmed.recent_7d.prior_23d?.accuracy)} (n {confirmed.recent_7d.prior_23d?.n ?? 0}).
            </span>
            {confirmed.recent_7d.provisional && (
              <Badge variant="outline" className="text-[9px]">
                provisional (&lt;30)
              </Badge>
            )}
          </div>
        )}

        <Alert className="py-2">
          <Info className="h-4 w-4" />
          <AlertTitle className="text-xs">What this loop does — and does not do</AlertTitle>
          <AlertDescription className="text-[11px] leading-relaxed">
            <p>{learning.next_action}</p>
            <p className="mt-1">
              Confirmed only: {learning.confirmed_only ? 'yes' : 'unknown'} · Automatic retraining:{' '}
              {learning.automatic_retraining ? 'yes' : 'no'} · Automatic promotion:{' '}
              {learning.automatic_promotion ? 'yes' : 'no'}.
            </p>
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="font-mono text-base font-semibold tabular-nums">{value}</div>
    </div>
  );
}
