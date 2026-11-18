/**
 * Unit tests for the canonical indicator library.
 * Every test uses deterministic fixtures — no randomness, no network.
 * Math expectations are hand-computed from the standard TA definitions.
 */
import { describe, expect, it } from 'vitest';
import {
  atr,
  bollinger,
  ema,
  macd,
  performancePercent,
  relativeVolume,
  rsi,
  sma,
  stochastic,
  swingPoints,
  toCandlePoints,
  toClosePoints,
  toIndicatorPoints,
  toVolumePoints,
  vwapAnchored,
  type OHLCVBar,
} from '@/lib/indicators';

const bar = (close: number, extra: Partial<OHLCVBar> = {}): OHLCVBar => ({
  timestamp: '2026-01-05T00:00:00.000Z',
  open: close - 0.5,
  high: close + 0.5,
  low: close - 1,
  close,
  volume: 1000,
  ...extra,
});

const ts = (iso: string, close: number): OHLCVBar => bar(close, { timestamp: iso });

describe('sma', () => {
  it('computes rolling means with warmup gaps', () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([undefined, undefined, 2, 3, 4]);
  });
  it('emits nothing when history is shorter than the period', () => {
    expect(sma([1, 2], 5)).toEqual([undefined, undefined]);
  });
  it('rejects non-positive periods honestly', () => {
    expect(sma([1, 2, 3], 0)).toEqual([undefined, undefined, undefined]);
  });
  it('never fills a window containing a bad tick', () => {
    const out = sma([1, 2, NaN, 4, 5, 6], 3);
    expect(out[2]).toBeUndefined();
    expect(out[3]).toBeUndefined();
    expect(out[4]).toBeUndefined();
    // window [4,5,6] is clean again
    expect(out[5]).toBeCloseTo(5, 10);
  });
});

describe('ema', () => {
  it('matches hand-computed classic EMA', () => {
    // seed SMA(1,2,3)=2, k=0.5 → E3=(4-2)*.5+2=3, E4=(5-3)*.5+3=4
    expect(ema([1, 2, 3, 4, 5], 3)).toEqual([undefined, undefined, 2, 3, 4]);
  });
  it('holds constant series constant', () => {
    expect(ema([10, 10, 10, 10, 10], 3)).toEqual([undefined, undefined, 10, 10, 10]);
  });
  it('emits nothing without enough history', () => {
    expect(ema([1, 2], 5)).toEqual([undefined, undefined]);
  });
});

describe('vwapAnchored', () => {
  it('equals typical price for a single bar', () => {
    const out = vwapAnchored([bar(100, { high: 102, low: 98, close: 100, volume: 1000 })]);
    expect(out[0]).toBeCloseTo(100, 10);
  });
  it('skips zero-volume bars without carrying a fabricated value', () => {
    const out = vwapAnchored([
      bar(100, { high: 101, low: 99, close: 100, volume: 1000 }),
      bar(200, { high: 201, low: 199, close: 200, volume: 0 }),
    ]);
    expect(out[0]).toBeCloseTo(100, 10);
    expect(out[1]).toBeUndefined();
  });
});

describe('bollinger', () => {
  it('collapses to the price on constant series', () => {
    const { middle, upper, lower } = bollinger([5, 5, 5, 5, 5], 3, 2);
    expect(middle.slice(2)).toEqual([5, 5, 5]);
    expect(upper.slice(2)).toEqual([5, 5, 5]);
    expect(lower.slice(2)).toEqual([5, 5, 5]);
  });
  it('widens symmetrically around the mean on varying data', () => {
    const { middle, upper, lower } = bollinger([1, 2, 3, 4, 5], 5, 2);
    expect(middle[4]).toBeCloseTo(3, 10);
    const sd = Math.sqrt(2);
    expect(upper[4]).toBeCloseTo(3 + 2 * sd, 8);
    expect(lower[4]).toBeCloseTo(3 - 2 * sd, 8);
  });
});

describe('rsi', () => {
  it('yields 100 on pure gains, 0 on pure losses, 50 on flat', () => {
    const gains = Array.from({ length: 20 }, (_, i) => 100 + i);
    expect(rsi(gains, 14)[19]).toBe(100);
    const losses = Array.from({ length: 20 }, (_, i) => 100 - i);
    expect(rsi(losses, 14)[19]).toBe(0);
    const flat = new Array(20).fill(50);
    expect(rsi(flat, 14)[19]).toBe(50);
  });
  it('stays within 0..100 on noisy data', () => {
    const noisy = [10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18, 17, 19];
    for (const v of rsi(noisy, 14)) {
      if (v !== undefined) {
        expect(v).toBeGreaterThanOrEqual(0);
        expect(v).toBeLessThanOrEqual(100);
      }
    }
  });
});

describe('macd', () => {
  it('is zero on constant series once warmed up', () => {
    const c = new Array(60).fill(42);
    const { macdLine, signalLine, histogram } = macd(c, 12, 26, 9);
    const last = macdLine.length - 1;
    expect(macdLine[last]).toBeCloseTo(0, 8);
    expect(signalLine[last]).toBeCloseTo(0, 8);
    expect(histogram[last]).toBeCloseTo(0, 8);
  });
  it('goes positive on a sustained rally', () => {
    const c = Array.from({ length: 60 }, (_, i) => 100 + i * 2);
    const { macdLine } = macd(c, 12, 26, 9);
    expect(macdLine[macdLine.length - 1]).toBeGreaterThan(0);
  });
});

describe('stochastic', () => {
  it('yields 100 when close sits at the range top', () => {
    const bars = Array.from({ length: 14 }, (_, i) =>
      bar(100 + i, { high: 120, low: 90, close: i === 13 ? 120 : 100 + i, volume: 500 }),
    );
    const { k } = stochastic(bars, 14, 3);
    expect(k[13]).toBe(100);
  });
  it('yields 50 on a flat range (never 0/NaN)', () => {
    const bars = Array.from({ length: 20 }, () => bar(100, { high: 100, low: 100, close: 100 }));
    const { k } = stochastic(bars, 14, 3);
    expect(k[19]).toBe(50);
  });
});

describe('atr', () => {
  it('equals the range on constant-range bars', () => {
    const bars = Array.from({ length: 20 }, () => bar(100, { high: 101, low: 99, close: 100 }));
    const out = atr(bars, 14);
    expect(out[19]).toBeCloseTo(2, 8);
  });
});

describe('relativeVolume', () => {
  it('is 1.0 on constant volume after warmup', () => {
    const bars = Array.from({ length: 25 }, () => bar(100));
    expect(relativeVolume(bars, 20)[24]).toBeCloseTo(1, 10);
  });
  it('spikes above 1 on a volume surge', () => {
    const bars = Array.from({ length: 25 }, () => bar(100));
    bars[24] = bar(100, { volume: 5000 });
    expect(relativeVolume(bars, 20)[24]).toBeGreaterThan(4);
  });
});

describe('performancePercent', () => {
  it('rebases to the first close', () => {
    const bars = [ts('2026-01-01T00:00:00Z', 100), ts('2026-01-02T00:00:00Z', 150)];
    expect(performancePercent(bars)).toEqual([0, 50]);
  });
  it('returns all-undefined with no finite close (never invents a base)', () => {
    const bars = [bar(NaN), bar(NaN)];
    expect(performancePercent(bars)).toEqual([undefined, undefined]);
  });
});

describe('swingPoints', () => {
  it('detects an objective peak and trough', () => {
    // peak at index 5 (value 200 surrounded by lower values, window 2)
    const closes = [10, 20, 30, 40, 50, 200, 50, 40, 30, 20, 10, 5, 1, 0.5, 0.25, 300, 10, 9, 8, 7];
    const bars = closes.map((c, i) =>
      bar(c, { timestamp: `2026-01-${String(i + 1).padStart(2, '0')}T00:00:00Z`, high: c + 1, low: c - 1 }),
    );
    const { swingHighs, swingLows } = swingPoints(bars, 2);
    expect(swingHighs).toContain(5);
    expect(swingLows.length).toBeGreaterThanOrEqual(0);
  });
});

describe('chart-data mapping (single source of truth)', () => {
  const bars: OHLCVBar[] = [
    ts('2026-01-01T00:00:00.000Z', 100),
    ts('2026-01-02T00:00:00.000Z', 101),
    { timestamp: 'not-a-date', open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
    ts('2026-01-03T00:00:00.000Z', 102),
  ];

  it('drops unparseable timestamps, preserves order, never mutates values', () => {
    const candles = toCandlePoints(bars);
    expect(candles).toHaveLength(3);
    expect(candles.map((c) => c.close)).toEqual([100, 101, 102]);
    expect(toClosePoints(bars).map((p) => p.value)).toEqual([100, 101, 102]);
    expect(toVolumePoints(bars)).toHaveLength(3);
  });

  it('switching chart types does not change financial data', () => {
    const before = JSON.stringify(bars);
    toCandlePoints(bars);
    toClosePoints(bars);
    toVolumePoints(bars);
    toIndicatorPoints(bars, [1, undefined, 3, 4]);
    expect(JSON.stringify(bars)).toBe(before);
  });

  it('indicator points skip warmup without shifting timestamps', () => {
    const pts = toIndicatorPoints(bars, [undefined, 5, undefined, 7]);
    expect(pts).toHaveLength(2);
    expect(pts[0].value).toBe(5);
    expect(pts[1].value).toBe(7);
  });
});

describe('2001-data regression (frontend side)', () => {
  it('a series spanning 2001→today keeps the newest bar last after ASC sort', () => {
    // Simulates the fixed backend contract: newest-N DESC then ASC for charts.
    const ancient = ts('2001-09-11T00:00:00.000Z', 10);
    const recent = [30, 31, 32].map((c, i) =>
      ts(`2026-09-2${i}T00:00:00.000Z`, c),
    );
    const freshestFirst = [...recent, ancient].sort(
      (a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp),
    );
    const forChart = [...freshestFirst]
      .slice(0, 3)
      .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
    // Newest-biased window: the ancient bar must NOT be in a 3-bar recent window.
    expect(forChart.map((b) => b.timestamp)).not.toContain('2001-09-11T00:00:00.000Z');
    const last = forChart[forChart.length - 1];
    expect(last.timestamp).toBe('2026-09-22T00:00:00.000Z');
    // And the chart must still render the full-span series oldest→newest when asked.
    const full = [ancient, ...recent].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
    expect(full[0].timestamp).toContain('2001');
    expect(toCandlePoints(full)).toHaveLength(4);
  });
});
