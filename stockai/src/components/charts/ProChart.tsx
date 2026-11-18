'use client';

/**
 * ProChart — professional financial chart built on lightweight-charts.
 *
 * Data contract (SINGLE SOURCE OF TRUTH):
 * - Consumes ONLY the `data: HistoricalBar[]` prop (backend history bars).
 * - All series (candles, line, area, baseline, OHLC, volume) and all overlays
 *   (SMA/EMA/VWAP/Bollinger) derive from that array via `@/lib/indicators`.
 * - Switching `chartType` never changes financial values — only reshapes them.
 * - Gaps stay gaps (warmup → no point emitted). No interpolation, no random.
 * - Empty input renders an honest empty state (parent owns error/stale UI).
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import { cn, formatPrice } from '@/lib/utils';
import type { HistoricalBar } from '@/types';
import {
  bollingerCloses,
  emaCloses,
  performancePercent,
  smaCloses,
  swingPoints,
  toCandlePoints,
  toClosePoints,
  toIndicatorPoints,
  toVolumePoints,
  vwapAnchored,
} from '@/lib/indicators';

export type ProChartType = 'candlestick' | 'ohlc' | 'line' | 'area' | 'baseline';

export interface ProChartProps {
  data: HistoricalBar[];
  chartType?: ProChartType;
  height?: number;
  showVolume?: boolean;
  /** Overlay ids: SMA20, SMA50, EMA20, EMA50, VWAP, BB */
  overlays?: string[];
  /** Percent-change (rebased) view — forces a normalized line rendering. */
  percentView?: boolean;
  /** Objective swing high/low markers derived from the data. */
  showSwings?: boolean;
  currency?: string;
  className?: string;
  onHover?: (bar: HistoricalBar | null, index: number) => void;
}

const UP = '#26a69a';
const DOWN = '#ef5350';

const OVERLAY_DEFS: Record<string, { label: string; color: string; dashed?: boolean }> = {
  SMA20: { label: 'SMA 20', color: '#2962ff' },
  SMA50: { label: 'SMA 50', color: '#ff6d00' },
  EMA20: { label: 'EMA 20', color: '#7e57c2' },
  EMA50: { label: 'EMA 50', color: '#ec407a' },
  VWAP: { label: 'VWAP (anchored)', color: '#009688', dashed: true },
  BB_UPPER: { label: 'BB upper', color: '#78909c', dashed: true },
  BB_LOWER: { label: 'BB lower', color: '#78909c', dashed: true },
};

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function ProChart({
  data,
  chartType = 'candlestick',
  height = 400,
  showVolume = true,
  overlays = [],
  percentView = false,
  showSwings = false,
  currency = 'USD',
  className,
  onHover,
}: ProChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const seriesRef = useRef<any>(null);
  const volumeRef = useRef<any>(null);
  const overlayRefs = useRef<any[]>([]);
  const { resolvedTheme } = useTheme();
  const [hover, setHover] = useState<{ bar: HistoricalBar; index: number } | null>(null);
  const [mounted, setMounted] = useState(false);
  const dataRef = useRef(data);
  dataRef.current = data;
  const hoverRef = useRef(onHover);
  hoverRef.current = onHover;

  const dark = resolvedTheme === 'dark';
  const gridColor = dark ? 'rgba(148, 163, 184, 0.12)' : 'rgba(100, 116, 139, 0.14)';
  const textColor = dark ? '#94a3b8' : '#64748b';
  const crossColor = dark ? '#475569' : '#94a3b8';

  // Effective type: percent view forces normalized line semantics.
  const effectiveType: ProChartType = percentView ? 'line' : chartType;

  const derived = useMemo(() => {
    if (!data.length) return null;
    const candles = toCandlePoints(data);
    const closes = toClosePoints(data);
    const vols = toVolumePoints(data);
    const perf = performancePercent(data);
    const perfPoints = perf
      .map((v, i) => {
        if (v === undefined || !Number.isFinite(v)) return null;
        const t = closes[i]?.time ?? candles[i]?.time;
        if (t === undefined) return null;
        return { time: t, value: v };
      })
      .filter((p): p is { time: number; value: number } => p !== null);
    const sma20 = smaCloses(data, 20);
    const sma50 = smaCloses(data, 50);
    const ema20 = emaCloses(data, 20);
    const ema50 = emaCloses(data, 50);
    const vwap = vwapAnchored(data);
    const bb = bollingerCloses(data, 20, 2);
    const swings = showSwings ? swingPoints(data, 10) : { swingHighs: [], swingLows: [] };
    return { candles, closes, vols, perfPoints, sma20, sma50, ema20, ema50, vwap, bb, swings };
  }, [data, showSwings]);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Build / rebuild chart when theme-relevant options change.
  useEffect(() => {
    if (!mounted || !containerRef.current || !derived) return;
    let chart: any = null;
    let disposed = false;

    (async () => {
      const lwc: any = await import('lightweight-charts');
      if (disposed || !containerRef.current) return;
      const {
        createChart,
        CandlestickSeries,
        LineSeries,
        AreaSeries,
        BarSeries,
        BaselineSeries,
        HistogramSeries,
        LineStyle,
      } = lwc;

      // Defensive: support both v5 (addSeries) and v4 (addXxxSeries) APIs.
      const useAddSeries = typeof lwc.CandlestickSeries !== 'undefined';

      chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height,
        layout: {
          background: { type: 'solid', color: 'transparent' },
          textColor,
          fontSize: 11,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        },
        grid: {
          vertLines: { color: gridColor },
          horzLines: { color: gridColor },
        },
        crosshair: {
          vertLine: { color: crossColor, style: LineStyle.Dashed, labelBackgroundColor: crossColor },
          horzLine: { color: crossColor, style: LineStyle.Dashed, labelBackgroundColor: crossColor },
        },
        rightPriceScale: { borderColor: gridColor },
        timeScale: {
          borderColor: gridColor,
          timeVisible: true,
          secondsVisible: false,
          rightOffset: 4,
        },
        kineticScroll: { enabled: !(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false) },
      });
      chartRef.current = chart;

      const addSeries = (type: any, opts: any) => {
        if (useAddSeries) return chart.addSeries(type, opts);
        // v4 fallback
        if (type === CandlestickSeries) return chart.addCandlestickSeries(opts);
        if (type === BarSeries) return chart.addBarSeries(opts);
        if (type === AreaSeries) return chart.addAreaSeries(opts);
        if (type === BaselineSeries) return chart.addBaselineSeries(opts);
        return chart.addLineSeries(opts);
      };

      // ---- main price series (single source: `derived`) ----
      let main: any = null;
      if (effectiveType === 'candlestick') {
        main = addSeries(CandlestickSeries, {
          upColor: UP,
          downColor: DOWN,
          wickUpColor: UP,
          wickDownColor: DOWN,
          borderVisible: false,
        });
        main.setData(derived.candles);
      } else if (effectiveType === 'ohlc') {
        main = addSeries(BarSeries, { upColor: UP, downColor: DOWN, thinBars: false });
        main.setData(derived.candles);
      } else if (effectiveType === 'area') {
        const lastClose = dataRef.current[dataRef.current.length - 1]?.close ?? 0;
        const firstClose = dataRef.current[0]?.close ?? 0;
        const up = lastClose >= firstClose;
        main = addSeries(AreaSeries, {
          lineColor: up ? UP : DOWN,
          topColor: hexToRgba(up ? UP : DOWN, 0.35),
          bottomColor: hexToRgba(up ? UP : DOWN, 0.0),
          lineWidth: 2,
        });
        main.setData(derived.closes);
      } else if (effectiveType === 'baseline') {
        main = addSeries(BaselineSeries, {
          baseValue: { type: 'price', price: dataRef.current[0]?.close ?? 0 },
          topLineColor: UP,
          bottomLineColor: DOWN,
          topFillColor1: hexToRgba(UP, 0.25),
          topFillColor2: hexToRgba(UP, 0.0),
          bottomFillColor1: hexToRgba(DOWN, 0.0),
          bottomFillColor2: hexToRgba(DOWN, 0.25),
          lineWidth: 2,
        });
        main.setData(derived.closes);
      } else {
        // line (or percentView normalized line)
        const pts = percentView ? derived.perfPoints : derived.closes;
        const up = percentView
          ? (pts.length ? pts[pts.length - 1].value >= 0 : true)
          : (dataRef.current[dataRef.current.length - 1]?.close ?? 0) >= (dataRef.current[0]?.close ?? 0);
        main = addSeries(LineSeries, {
          color: up ? UP : DOWN,
          lineWidth: 2,
          priceFormat: percentView ? { type: 'percent' } : undefined,
        });
        main.setData(pts);
      }
      seriesRef.current = main;

      // ---- volume (real volume, never synthesized) ----
      if (showVolume && !percentView) {
        const vol = chart.addSeries
          ? chart.addSeries(HistogramSeries, {
              priceScaleId: '',
              priceFormat: { type: 'volume' },
            })
          : chart.addHistogramSeries({ priceScaleId: '' });
        vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
        vol.setData(
          derived.vols.map((v) => ({
            time: v.time,
            value: v.value,
            color: hexToRgba(v.up ? UP : DOWN, 0.55),
          })),
        );
        volumeRef.current = vol;
      }

      // ---- overlays (same source, indicator math) ----
      overlayRefs.current = [];
      const want = new Set(percentView ? [] : overlays);
      const mk = (id: string, values: (number | undefined)[]) => {
        if (!want.has(id)) return;
        const pts = toIndicatorPoints(dataRef.current, values);
        if (!pts.length) return;
        const def = OVERLAY_DEFS[id] ?? OVERLAY_DEFS.BB_UPPER;
        const s = useAddSeries
          ? chart.addSeries(LineSeries, {
              color: def.color,
              lineWidth: 1,
              lineStyle: def.dashed ? LineStyle.Dashed : LineStyle.Solid,
              priceLineVisible: false,
              lastValueVisible: false,
              crosshairMarkerVisible: false,
            })
          : chart.addLineSeries({
              color: def.color,
              lineWidth: 1,
              lineStyle: lwc.LineStyle.Dashed,
              priceLineVisible: false,
              lastValueVisible: false,
              crosshairMarkerVisible: false,
            });
        s.setData(pts);
        overlayRefs.current.push(s);
      };
      mk('SMA20', derived.sma20);
      mk('SMA50', derived.sma50);
      mk('EMA20', derived.ema20);
      mk('EMA50', derived.ema50);
      mk('VWAP', derived.vwap);
      if (want.has('BB')) {
        mk('BB_UPPER', derived.bb.upper);
        mk('BB_LOWER', derived.bb.lower);
      }

      // ---- swing markers (objective, derived — labeled as such in legend) ----
      if (showSwings && !percentView && (derived.swings.swingHighs.length || derived.swings.swingLows.length)) {
        const markers = [
          ...derived.swings.swingHighs.map((i) => {
            const t = derived.candles[i]?.time;
            return t === undefined
              ? null
              : { time: t, position: 'aboveBar', color: DOWN, shape: 'arrowDown', text: 'H' };
          }),
          ...derived.swings.swingLows.map((i) => {
            const t = derived.candles[i]?.time;
            return t === undefined
              ? null
              : { time: t, position: 'belowBar', color: UP, shape: 'arrowUp', text: 'L' };
          }),
        ].filter(Boolean);
        try {
          if (typeof lwc.createSeriesMarkers === 'function') {
            lwc.createSeriesMarkers(main, markers);
          } else if (typeof main.setMarkers === 'function') {
            main.setMarkers(markers);
          }
        } catch {
          /* markers are decorative; never break the chart */
        }
      }

      chart.timeScale().fitContent();

      // ---- crosshair → hover state (exact timestamp, OHLCV, indicator values) ----
      chart.subscribeCrosshairMove((param: any) => {
        if (!param || !param.time) {
          setHover(null);
          hoverRef.current?.(null, -1);
          return;
        }
        const t = param.time as number;
        // Binary search the bar (times are ascending unix seconds).
        const bars = dataRef.current;
        let lo = 0;
        let hi = bars.length - 1;
        let found = -1;
        while (lo <= hi) {
          const mid = (lo + hi) >> 1;
          const mt = Date.parse(bars[mid].timestamp) / 1000;
          if (Math.abs(mt - t) < 43200) {
            found = mid;
            break;
          }
          if (mt < t) lo = mid + 1;
          else hi = mid - 1;
        }
        if (found === -1) found = Math.max(0, Math.min(bars.length - 1, lo));
        const bar = bars[found];
        if (!bar) {
          setHover(null);
          hoverRef.current?.(null, -1);
          return;
        }
        setHover({ bar, index: found });
        hoverRef.current?.(bar, found);
      });

      const ro = new ResizeObserver((entries) => {
        const w = entries[0]?.contentRect.width;
        if (w && chart) chart.applyOptions({ width: Math.floor(w) });
      });
      if (containerRef.current) ro.observe(containerRef.current);

      return () => {
        ro.disconnect();
      };
    })();

    return () => {
      disposed = true;
      try {
        chartRef.current?.remove();
      } catch {
        /* noop */
      }
      chartRef.current = null;
      seriesRef.current = null;
      volumeRef.current = null;
      overlayRefs.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, derived, effectiveType, showVolume, percentView, height, dark, showSwings, JSON.stringify(overlays)]);

  if (!data.length) {
    return (
      <div
        className={cn(
          'flex h-[300px] items-center justify-center rounded-lg bg-muted/30 text-sm text-muted-foreground',
          className,
        )}
        role="status"
      >
        No chart data — the provider returned no bars for this range (never synthesized).
      </div>
    );
  }

  const hoverDate = hover ? new Date(hover.bar.timestamp) : null;
  const activeOverlays = overlays.filter((o) => o !== 'BB' || true);

  return (
    <div className={cn('w-full', className)}>
      {/* Legend / hover readout */}
      <div className="mb-2 flex min-h-[28px] flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
        {hover && hoverDate && !Number.isNaN(hoverDate.getTime()) ? (
          <>
            <span className="font-semibold text-foreground">
              {hoverDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              <span className="ml-1 font-normal text-muted-foreground">UTC {hoverDate.toISOString().slice(11, 16)}</span>
            </span>
            {!percentView ? (
              <>
                <span>O <b className="text-foreground">{formatPrice(hover.bar.open, currency)}</b></span>
                <span>H <b className="text-foreground">{formatPrice(hover.bar.high, currency)}</b></span>
                <span>L <b className="text-foreground">{formatPrice(hover.bar.low, currency)}</b></span>
                <span>C <b className="text-foreground">{formatPrice(hover.bar.close, currency)}</b></span>
                <span>Vol <b className="text-foreground">{hover.bar.volume.toLocaleString()}</b></span>
              </>
            ) : (
              <span>Perf <b className="text-foreground">{percentLabel(data, hover.index)}</b></span>
            )}
          </>
        ) : (
          <span>
            {data.length} bars · {effectiveType}
            {percentView ? ' · %-change (rebased)' : ''} · hover for OHLCV
            {showSwings ? ' · swing H/L derived' : ''}
          </span>
        )}
        <span className="ml-auto hidden gap-3 sm:flex">
          {activeOverlays
            .filter((o) => o !== 'BB')
            .map((o) => (
              <span key={o} className="flex items-center gap-1">
                <span
                  className="inline-block h-[3px] w-4 rounded"
                  style={{ background: (OVERLAY_DEFS[o] ?? {}).color ?? '#999' }}
                />
                {o}
              </span>
            ))}
          {overlays.includes('BB') && <span className="flex items-center gap-1">BB(20,2)</span>}
        </span>
      </div>
      <div ref={containerRef} style={{ height }} className="w-full" role="img" aria-label={`${effectiveType} price chart, ${data.length} bars`} />
      <p className="mt-1 text-[11px] text-muted-foreground">
        {percentView
          ? 'Percentage view rebases each series to its first close (=0%). Compare, don’t mistake for prices.'
          : 'All values from backend history bars. Gaps = no data (never filled). Times shown in UTC.'}
      </p>
    </div>
  );
}

function percentLabel(data: HistoricalBar[], index: number): string {
  const base = data.find((b) => Number.isFinite(b.close) && b.close !== 0)?.close;
  const cur = data[index]?.close;
  if (!base || !Number.isFinite(cur)) return '—';
  const p = (cur / base - 1) * 100;
  return `${p >= 0 ? '+' : ''}${p.toFixed(2)}%`;
}

export const PRO_CHART_TYPES: { value: ProChartType; label: string }[] = [
  { value: 'candlestick', label: 'Candles' },
  { value: 'ohlc', label: 'OHLC' },
  { value: 'line', label: 'Line' },
  { value: 'area', label: 'Area' },
  { value: 'baseline', label: 'Baseline' },
];
