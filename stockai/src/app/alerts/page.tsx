'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api/client';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Bell, BellOff, Plus, Trash2, CheckCheck, AlertTriangle } from 'lucide-react';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authed, setAuthed] = useState(false);

  // Create form
  const [symbol, setSymbol] = useState('AAPL');
  const [exchange, setExchange] = useState('NASDAQ');
  const [alertType, setAlertType] = useState('price_above');
  const [condition, setCondition] = useState('gt');
  const [target, setTarget] = useState('200');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    if (!api.isAuthenticated()) {
      setAuthed(false);
      setLoading(false);
      return;
    }
    setAuthed(true);
    try {
      const list = await api.getAlerts();
      setAlerts(Array.isArray(list) ? list : []);
    } catch (e: any) {
      setError(e.message || 'Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async () => {
    setCreating(true);
    try {
      // Resolve instrument first so alert points at the right exchange-specific row.
      const found = await api.searchInstruments(symbol.trim(), { limit: 5 }).catch(() => []);
      const match = (found || []).find(
        (r: any) => (r.exchange_code || r.exchange || '').toUpperCase() === exchange.trim().toUpperCase(),
      ) ?? (found || [])[0];
      if (!match) throw new Error(`Instrument ${symbol} not found — check ticker/exchange`);
      // Need instrument id: fetch detail via getWatchlists? Use search result id if present.
      const instrumentId = (match as any).id ?? (match as any).instrument_id;
      if (!instrumentId) {
        // Fall back: backend alerts API expects instrument_id; fetch instruments list via screener-adjacent search endpoint shape.
        throw new Error('Search did not return an instrument id — open the stock page and create the alert there.');
      }
      await api.createAlert({
        instrument_id: instrumentId,
        name: `${symbol.trim().toUpperCase()} ${alertType} ${condition} ${target}`,
        alert_type: alertType,
        condition,
        target_value: Number(target),
      });
      setTarget('');
      await load();
    } catch (e: any) {
      setError(e.message || 'Failed to create alert');
    } finally {
      setCreating(false);
    }
  };

  const acknowledge = async (id: string) => {
    try {
      await api.acknowledgeAlert(id);
      await load();
    } catch (e: any) {
      setError(e.message || 'Acknowledge failed');
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteAlert(id);
      await load();
    } catch (e: any) {
      setError(e.message || 'Delete failed');
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-[1000px] space-y-4 p-6">
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
            <Bell className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="empty-state-title">Sign in to use alerts</p>
            <p className="empty-state-description">
              Alerts are real backend evaluators (price above/below, change %, volume) — user-scoped and auditable.
            </p>
            <div className="mt-4 flex gap-2">
              <Link href="/login"><Button>Sign in</Button></Link>
              <Link href="/signup"><Button variant="outline">Create account</Button></Link>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="terminal-surface min-h-screen">
      <div className="mx-auto max-w-[1000px] space-y-6 p-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
              <Bell className="h-6 w-6" /> Alerts
            </h1>
            <p className="text-sm text-muted-foreground">
              Backend-evaluated every 5 min. Idempotent triggers, persisted events, explicit acknowledgement.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => load()}>Refresh</Button>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Something went wrong</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><Plus className="h-4 w-4" /> New alert</CardTitle>
            <CardDescription>Evaluated against live snapshots — stale data never silently fires.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <label className="text-xs">Symbol<Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="AAPL" /></label>
            <label className="text-xs">Exchange<Input value={exchange} onChange={(e) => setExchange(e.target.value)} placeholder="NASDAQ" /></label>
            <label className="text-xs">Type
              <select value={alertType} onChange={(e) => setAlertType(e.target.value)} className="mt-1 h-10 w-full rounded-md border border-input bg-background px-2 text-sm">
                <option value="price_above">price above</option>
                <option value="price_below">price below</option>
                <option value="price_change_pct">price change %</option>
                <option value="volume_above">volume above</option>
              </select>
            </label>
            <label className="text-xs">Condition
              <select value={condition} onChange={(e) => setCondition(e.target.value)} className="mt-1 h-10 w-full rounded-md border border-input bg-background px-2 text-sm">
                <option value="gt">above ({'>'})</option>
                <option value="lt">below ({'<'})</option>
                <option value="gte">at or above (≥)</option>
                <option value="lte">at or below (≤)</option>
                <option value="crosses_above">crosses above</option>
                <option value="crosses_below">crosses below</option>
              </select>
            </label>
            <label className="text-xs">Target<Input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="200" inputMode="decimal" /></label>
            <div className="sm:col-span-2 lg:col-span-5">
              <Button onClick={create} disabled={creating || !symbol.trim() || !target.trim()}>
                {creating ? 'Creating…' : 'Create alert'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Active & triggered ({alerts.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {alerts.length === 0 && (
              <div className="empty-state">
                <BellOff className="mb-2 h-6 w-6 text-muted-foreground" />
                <p className="empty-state-title text-sm">No alerts yet</p>
                <p className="empty-state-description text-xs">Create your first trigger above. We fail honest — never fake a fill.</p>
              </div>
            )}
            {alerts.map((a: any) => (
              <div key={a.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-border p-3">
                <span className={`rounded-full px-2 py-1 text-[11px] font-bold ${a.status === 'TRIGGERED' ? 'bg-red-500/10 text-red-600' : 'bg-emerald-500/10 text-emerald-600'}`}>
                  {a.status}
                </span>
                <span className="text-sm font-medium">{a.alert_type} {a.condition} {a.target_value}</span>
                <span className="text-xs text-muted-foreground">{a.created_at ? new Date(a.created_at).toLocaleString() : ''}</span>
                <span className="ml-auto flex gap-2">
                  {a.status === 'TRIGGERED' || a.status === 'ACTIVE' ? (
                    <Button size="sm" variant="outline" onClick={() => acknowledge(a.id)}>
                      <CheckCheck className="mr-1 h-3.5 w-3.5" /> Acknowledge
                    </Button>
                  ) : null}
                  <Button size="sm" variant="ghost" onClick={() => remove(a.id)} aria-label="Delete alert">
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
