'use client';

/**
 * IndicatorPane — oscillator sub-chart (RSI / MACD / Stochastic / ATR / RelVol).
 * Same single-source contract as ProChart: derives everything from `data`
 * via `@/lib/indicators`. Reference bands (RSI 30/70, Stoch 20/80, MACD zero)
 * are guides, not signals — no buy/sell language anywhere.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils';
import type { HistoricalBar } from '@/types';
import {
  atr,
  macdCloses,
  relativeVolume,
  rsiCloses,
  stochastic,
  toIndicatorPoints,
  toUTCTime,
} from '@/lib/indicators';

export type PaneKind = 'RSI' | 'MACD' | 'STOCH' | 'ATR' | 'RELVOL';

export function IndicatorPane({
  data,
  kind,
  height = 140,
  className,
}: {
  data: HistoricalBar[];
  kind: PaneKind;
  height?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const series = useMemo(() => {
    if (!data.length) return null;
    if (kind === 'RSI') {
      const v = rsiCloses(data, 14);
      return {
        lines: [{ id: 'RSI 14', color: '#7e57c2', points: toIndicatorPoints(data, v), width: 1 as const }],
        bands: [30, 70],
        range: { min: 0, max: 100 } as const,
      };
    }
    if (kind === 'MACD') {
      const m = macdCloses(data, 12, 26, 9);
      return {
        lines: [
          { id: 'MACD', color: '#2962ff', points: toIndicatorPoints(data, m.macdLine), width: 1 as const },
          { id: 'Signal', color: '#ff6d00', points: toIndicatorPoints(data, m.signalLine), width: 1 as const },
        ],
        hist: toIndicatorPoints(data, m.histogram).map((p) => ({
          time: p.time,
          value: p.value,
          up: p.value >= 0,
        })),
        bands: [0],
      };
    }
    if (kind === 'STOCH') {
      const s = stochastic(data, 14, 3);
      return {
        lines: [
          { id: '%K', color: '#2962ff', points: toIndicatorPoints(data, s.k), width: 1 as const },
          { id: '%D', color: '#ff6d00', points: toIndicatorPoints(data, s.d), width: 1 as const },
        ],
        bands: [20, 80],
        range: { min: 0, max: 100 } as const,
      };
    }
    if (kind === 'ATR') {
      const v = atr(data, 14);
      return {
        lines: [{ id: 'ATR 14', color: '#009688', points: toIndicatorPoints(data, v), width: 1 as const }],
      };
    }
    const v = relativeVolume(data, 20);
    return {
      hist: toIndicatorPoints(data, v).map((p) => ({
        time: p.time,
        value: p.value,
        up: p.value >= 1,
      })),
      bands: [1],
    };
  }, [data, kind]);

  const desc = useMemo(() => {
    switch (kind) {
      case 'RSI':
        return 'RSI 14 (Wilder) — momentum 0–100. Bands at 30/70 are guides, not signals.';
      case 'MACD':
        return 'MACD 12/26/9 — trend-following spread. Zero band shown; crossovers are not advice.';
      case 'STOCH':
        return 'Stochastic 14/3 — close position within recent range. Bands at 20/80 are guides.';
      case 'ATR':
        return 'ATR 14 (Wilder) — average true range in price units. Volatility gauge, not direction.';
      case 'RELVOL':
        return 'Relative volume vs 20-bar mean. 1.0 = average; spikes mark attention, not action.';
    }
  }, [kind]);

  useEffect(() => {
    if (!mounted || !ref.current || !series) return;
    let chart: any = null;
    let disposed = false;
    (async () => {
      const lwc: any = await import('lightweight-charts');
      if (disposed || !ref.current) return;
      const { createChart, LineSeries, HistogramSeries, LineStyle } = lwc;
      const dark = resolvedTheme === 'dark';
      const grid = dark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.14)';
      const text = dark ? '#94a3b8' : '#64748b';
      chart = createChart(ref.current, {
        width: ref.current.clientWidth,
        height,
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: text, fontSize: 10 },
        grid: { vertLines: { color: grid }, horzLines: { color: grid } },
        rightPriceScale: { borderColor: grid },
        timeScale: { borderColor: grid, timeVisible: true },
      });
      const useAdd = typeof lwc.LineSeries !== 'undefined';
      for (const line of (series as any).lines ?? []) {
        const s = useAdd
          ? chart.addSeries(LineSeries, { color: line.color, lineWidth: line.width, priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false })
          : chart.addLineSeries({ color: line.color, lineWidth: line.width, priceLineVisible: false, lastValueVisible: true });
        s.setData(line.points);
      }
      if ((series as any).hist) {
        const h = useAdd
          ? chart.addSeries(HistogramSeries, { priceScaleId: '', priceFormat: { type: 'volume' } })
          : chart.addHistogramSeries({ priceScaleId: '' });
        h.setData(
          (series as any).hist.map((p: any) => ({
            time: p.time,
            value: p.value,
            color: p.up ? 'rgba(38,166,154,0.6)' : 'rgba(239,83,80,0.6)',
          })),
        );
      }
      for (const b of (series as any).bands ?? []) {
        const times = data
          .map((d) => toUTCTime(d.timestamp))
          .filter((t): t is number => t !== null);
        if (times.length < 2) continue;
        const s = useAdd
          ? chart.addSeries(LineSeries, { color: text, lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
          : chart.addLineSeries({ color: text, lineWidth: 1, lineStyle: lwc.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
        s.setData([
          { time: times[0], value: b },
          { time: times[times.length - 1], value: b },
        ]);
      }
      chart.timeScale().fitContent();
      const ro = new ResizeObserver((es) => {
        const w = es[0]?.contentRect.width;
        if (w && chart) chart.applyOptions({ width: Math.floor(w) });
      });
      if (ref.current) ro.observe(ref.current);
      return () => ro.disconnect();
    })();
    return () => {
      disposed = true;
      try {
        chart?.remove();
      } catch {
        /* noop */
      }
    };
  }, [mounted, series, height, resolvedTheme, data]);

  const empty = !series || !((series as any).lines?.some((l: any) => l.points.length) || (series as any).hist?.length);

  return (
    <div className={cn('w-full', className)}>
      <div className="mb-1 flex items-baseline justify-between">
        <p className="font-mono text-[11px] font-semibold text-foreground">{kind}</p>
        <p className="text-[11px] text-muted-foreground">{desc}</p>
      </div>
      {empty ? (
        <div className="flex h-[80px] items-center justify-center rounded-lg bg-muted/30 text-xs text-muted-foreground" role="status">
          Not enough history for {kind} — needs warmup bars (honest gap, never estimated).
        </div>
      ) : (
        <div ref={ref} style={{ height }} className="w-full" role="img" aria-label={`${kind} indicator chart`} />
      )}
    </div>
  );
}

export const PANE_KINDS: PaneKind[] = ['RSI', 'MACD', 'STOCH', 'ATR', 'RELVOL'];
