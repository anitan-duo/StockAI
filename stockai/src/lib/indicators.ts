/**
 * Canonical technical-indicator calculations for StockAI charts.
 *
 * SINGLE SOURCE OF TRUTH: every chart type and every indicator consumes the
 * same `HistoricalBar[]` passed down from the stock page (which itself comes
 * from `GET /markets/instruments/{symbol}/history`). These functions NEVER
 * fetch, NEVER synthesize, NEVER fill gaps, and NEVER use randomness. Warmup
 * periods yield `undefined` (rendered as gaps), never fabricated values.
 *
 * Conventions:
 * - Input arrays are OHLCV closes in chronological (ascending) order.
 * - Outputs are aligned arrays of the same length; `undefined` = insufficient
 *   history (honest gap).
 * - All math is standard TA definition (Wilder's smoothing for RSI/ATR,
 *   classic EMA seeding with SMA, population standard deviation for Bollinger).
 */

export type OHLCVBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

const isFiniteNumber = (v: unknown): v is number =>
  typeof v === 'number' && Number.isFinite(v);

/** Extract closes; non-finite closes become NaN and poison only their window. */
function closesOf(bars: OHLCVBar[]): number[] {
  return bars.map((b) => (isFiniteNumber(b.close) ? b.close : NaN));
}

/**
 * Simple moving average of closes over `period`.
 * values[i] = mean(closes[i-period+1..i]); undefined for i < period-1.
 */
export function sma(values: number[], period: number): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(values.length).fill(undefined);
  if (period <= 0 || values.length === 0) return out;
  // Straightforward windowed mean. O(n·period) is fine for chart sizes
  // (≤2500 bars) and keeps the NaN-window logic obviously correct: any
  // non-finite value in the window → undefined (honest gap, never filled).
  for (let i = period - 1; i < values.length; i++) {
    let sum = 0;
    let ok = true;
    for (let k = i - period + 1; k <= i; k++) {
      const v = values[k];
      if (!isFiniteNumber(v)) {
        ok = false;
        break;
      }
      sum += v;
    }
    if (ok) out[i] = sum / period;
  }
  return out;
}

/** SMA of bar closes (convenience wrapper). */
export function smaCloses(bars: OHLCVBar[], period: number): (number | undefined)[] {
  return sma(closesOf(bars), period);
}

/**
 * Exponential moving average (classic: seed with SMA of first `period`
 * closes, then EMA[i] = (close[i] - EMA[i-1]) * k + EMA[i-1], k = 2/(period+1)).
 * undefined for i < period-1 or when the seed window isn't fully finite.
 */
export function ema(values: number[], period: number): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(values.length).fill(undefined);
  if (period <= 0 || values.length < period) return out;
  // Seed must be fully finite.
  for (let i = 0; i < period; i++) {
    if (!isFiniteNumber(values[i])) return out; // honest: no seed, no EMA at all until finite
  }
  const k = 2 / (period + 1);
  let prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) {
    const v = values[i];
    if (!isFiniteNumber(v)) {
      out[i] = undefined;
      continue; // keep `prev` (do not poison the recursive state with NaN)
    }
    prev = (v - prev) * k + prev;
    out[i] = prev;
  }
  return out;
}

/** EMA of bar closes (convenience wrapper). */
export function emaCloses(bars: OHLCVBar[], period: number): (number | undefined)[] {
  return ema(closesOf(bars), period);
}

/**
 * Anchored VWAP from the first bar: cumulative sum(typical * volume) /
 * cumulative sum(volume), typical = (H+L+C)/3. Bars with non-positive volume
 * or non-finite OHLC are skipped (previous VWAP carried would be fabrication;
 * instead emit undefined for that index).
 */
export function vwapAnchored(bars: OHLCVBar[]): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(bars.length).fill(undefined);
  let cumPV = 0;
  let cumV = 0;
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    if (
      !isFiniteNumber(b.high) ||
      !isFiniteNumber(b.low) ||
      !isFiniteNumber(b.close) ||
      !isFiniteNumber(b.volume) ||
      b.volume <= 0
    ) {
      out[i] = undefined;
      continue;
    }
    const typical = (b.high + b.low + b.close) / 3;
    cumPV += typical * b.volume;
    cumV += b.volume;
    out[i] = cumV > 0 ? cumPV / cumV : undefined;
  }
  return out;
}

/**
 * Bollinger Bands: middle = SMA(period), std = population standard deviation
 * of the same window, upper = middle + mult*std, lower = middle - mult*std.
 * Defaults: period 20, mult 2.
 */
export function bollinger(
  values: number[],
  period = 20,
  mult = 2,
): { middle: (number | undefined)[]; upper: (number | undefined)[]; lower: (number | undefined)[] } {
  const middle = sma(values, period);
  const upper: (number | undefined)[] = new Array(values.length).fill(undefined);
  const lower: (number | undefined)[] = new Array(values.length).fill(undefined);
  for (let i = 0; i < values.length; i++) {
    if (middle[i] === undefined) continue;
    const window = values.slice(i - period + 1, i + 1);
    if (!window.every(isFiniteNumber)) continue;
    const mean = middle[i] as number;
    const variance = window.reduce((a, v) => a + (v - mean) ** 2, 0) / period;
    const sd = Math.sqrt(variance);
    upper[i] = mean + mult * sd;
    lower[i] = mean - mult * sd;
  }
  return { middle, upper, lower };
}

/** Bollinger of bar closes (convenience wrapper). */
export function bollingerCloses(
  bars: OHLCVBar[],
  period = 20,
  mult = 2,
): { middle: (number | undefined)[]; upper: (number | undefined)[]; lower: (number | undefined)[] } {
  return bollinger(closesOf(bars), period, mult);
}

/**
 * RSI (Wilder): period 14 default. First average gain/loss = mean of first
 * `period` deltas; thereafter smoothed: avg = (prev*(period-1) + current)/period.
 * RS = avgGain/avgLoss; RSI = 100 - 100/(1+RS). Flat market (avgLoss=0, avgGain=0)
 * yields 50 (neutral), pure-gain yields 100. undefined for i < period.
 */
export function rsi(values: number[], period = 14): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(values.length).fill(undefined);
  if (period <= 0 || values.length <= period) return out;
  if (!values.slice(0, period + 1).every(isFiniteNumber)) {
    // Seed window not finite — still attempt from first finite stretch below.
  }
  let gainSum = 0;
  let lossSum = 0;
  let seeded = true;
  for (let i = 1; i <= period; i++) {
    const a = values[i - 1];
    const b = values[i];
    if (!isFiniteNumber(a) || !isFiniteNumber(b)) {
      seeded = false;
      break;
    }
    const d = b - a;
    if (d > 0) gainSum += d;
    else lossSum -= d;
  }
  if (!seeded) return out;
  let avgGain = gainSum / period;
  let avgLoss = lossSum / period;
  out[period] = avgLoss === 0 ? (avgGain === 0 ? 50 : 100) : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < values.length; i++) {
    const a = values[i - 1];
    const b = values[i];
    if (!isFiniteNumber(a) || !isFiniteNumber(b)) {
      out[i] = undefined;
      continue;
    }
    const d = b - a;
    const gain = d > 0 ? d : 0;
    const loss = d < 0 ? -d : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    out[i] = avgLoss === 0 ? (avgGain === 0 ? 50 : 100) : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

/** RSI of bar closes (convenience wrapper). */
export function rsiCloses(bars: OHLCVBar[], period = 14): (number | undefined)[] {
  return rsi(closesOf(bars), period);
}

/**
 * MACD: macdLine = EMA(fast) - EMA(slow) (12/26), signal = EMA(signalPeriod) of
 * the macd line (treating leading undefined as warmup: signal seeds on the
 * first `signalPeriod` finite macd values), histogram = macd - signal.
 */
export function macd(
  values: number[],
  fast = 12,
  slow = 26,
  signalPeriod = 9,
): {
  macdLine: (number | undefined)[];
  signalLine: (number | undefined)[];
  histogram: (number | undefined)[];
} {
  const n = values.length;
  const fastE = ema(values, fast);
  const slowE = ema(values, slow);
  const macdLine: (number | undefined)[] = new Array(n).fill(undefined);
  for (let i = 0; i < n; i++) {
    if (fastE[i] !== undefined && slowE[i] !== undefined) {
      macdLine[i] = (fastE[i] as number) - (slowE[i] as number);
    }
  }
  // Signal: EMA over the finite macd values, mapped back to bar indices.
  const signalLine: (number | undefined)[] = new Array(n).fill(undefined);
  const histogram: (number | undefined)[] = new Array(n).fill(undefined);
  const finiteIdx: number[] = [];
  const finiteVals: number[] = [];
  for (let i = 0; i < n; i++) {
    if (macdLine[i] !== undefined) {
      finiteIdx.push(i);
      finiteVals.push(macdLine[i] as number);
    }
  }
  if (finiteVals.length >= signalPeriod) {
    const sig = ema(finiteVals, signalPeriod);
    for (let k = 0; k < finiteVals.length; k++) {
      if (sig[k] === undefined) continue;
      const barIdx = finiteIdx[k];
      signalLine[barIdx] = sig[k];
      histogram[barIdx] = (macdLine[barIdx] as number) - (sig[k] as number);
    }
  }
  return { macdLine, signalLine, histogram };
}

/** MACD of bar closes (convenience wrapper). */
export function macdCloses(
  bars: OHLCVBar[],
  fast = 12,
  slow = 26,
  signalPeriod = 9,
): { macdLine: (number | undefined)[]; signalLine: (number | undefined)[]; histogram: (number | undefined)[] } {
  return macd(closesOf(bars), fast, slow, signalPeriod);
}

/**
 * Stochastic oscillator: %K = (C - lowestLow(N)) / (highestHigh(N) - lowestLow(N)) * 100,
 * %D = SMA(%K, 3). Flat range (high==low) yields 50 (neutral), not 0.
 * undefined for i < N-1.
 */
export function stochastic(
  bars: OHLCVBar[],
  kPeriod = 14,
  dPeriod = 3,
): { k: (number | undefined)[]; d: (number | undefined)[] } {
  const n = bars.length;
  const k: (number | undefined)[] = new Array(n).fill(undefined);
  for (let i = 0; i < n; i++) {
    if (i < kPeriod - 1) continue;
    const window = bars.slice(i - kPeriod + 1, i + 1);
    if (!window.every((b) => isFiniteNumber(b.high) && isFiniteNumber(b.low) && isFiniteNumber(b.close))) continue;
    const highest = Math.max(...window.map((b) => b.high));
    const lowest = Math.min(...window.map((b) => b.low));
    const close = bars[i].close;
    k[i] = highest === lowest ? 50 : ((close - lowest) / (highest - lowest)) * 100;
  }
  // %D: SMA of %K where the %K window is fully defined.
  const d: (number | undefined)[] = new Array(n).fill(undefined);
  for (let i = 0; i < n; i++) {
    if (i < kPeriod - 1 + dPeriod - 1) continue;
    const window = k.slice(i - dPeriod + 1, i + 1);
    if (!window.every((v) => v !== undefined)) continue;
    d[i] = (window as number[]).reduce((a, b) => a + b, 0) / dPeriod;
  }
  return { k, d };
}

/**
 * ATR (Wilder, period 14): true range = max(H-L, |H-prevC|, |L-prevC|);
 * first ATR = mean of first `period` TRs; then smoothed like RSI.
 * undefined for i < period.
 */
export function atr(bars: OHLCVBar[], period = 14): (number | undefined)[] {
  const n = bars.length;
  const out: (number | undefined)[] = new Array(n).fill(undefined);
  if (period <= 0 || n <= period) return out;
  const trs: (number | undefined)[] = new Array(n).fill(undefined);
  for (let i = 1; i < n; i++) {
    const b = bars[i];
    const prev = bars[i - 1];
    if (
      !isFiniteNumber(b.high) ||
      !isFiniteNumber(b.low) ||
      !isFiniteNumber(prev.close)
    ) {
      trs[i] = undefined;
      continue;
    }
    trs[i] = Math.max(
      b.high - b.low,
      Math.abs(b.high - prev.close),
      Math.abs(b.low - prev.close),
    );
  }
  const seed = trs.slice(1, period + 1);
  if (!seed.every((v) => v !== undefined)) return out;
  let prev = (seed as number[]).reduce((a, b) => a + b, 0) / period;
  out[period] = prev;
  for (let i = period + 1; i < n; i++) {
    if (trs[i] === undefined) {
      out[i] = undefined;
      continue;
    }
    prev = (prev * (period - 1) + (trs[i] as number)) / period;
    out[i] = prev;
  }
  return out;
}

/**
 * Relative volume: volume[i] / SMA(volume, period). undefined during warmup or
 * when the window mean is not positive-finite. Values >1 = above average.
 */
export function relativeVolume(bars: OHLCVBar[], period = 20): (number | undefined)[] {
  const vols = bars.map((b) => (isFiniteNumber(b.volume) && b.volume >= 0 ? b.volume : NaN));
  const mean = sma(vols, period);
  return bars.map((b, i) => {
    const m = mean[i];
    if (m === undefined || !isFiniteNumber(m) || (m as number) <= 0) return undefined;
    if (!isFiniteNumber(b.volume)) return undefined;
    return b.volume / (m as number);
  });
}

/**
 * Percentage performance rebased to the first FINITE close:
 * perf[i] = (close[i]/base - 1) * 100. Used for the %-change view and for
 * honest multi-symbol comparison (each series rebased to its own start).
 * undefined before/unless a finite base exists; never invents a base.
 */
export function performancePercent(bars: OHLCVBar[]): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(bars.length).fill(undefined);
  const baseIdx = bars.findIndex((b) => isFiniteNumber(b.close) && b.close !== 0);
  if (baseIdx === -1) return out;
  const base = bars[baseIdx].close;
  for (let i = 0; i < bars.length; i++) {
    if (!isFiniteNumber(bars[i].close)) {
      out[i] = undefined;
      continue;
    }
    out[i] = (bars[i].close / base - 1) * 100;
  }
  return out;
}

/**
 * Objective swing points: index i is a swing high if high[i] is the strict
 * maximum of highs[i-W..i+W]; swing low analogously with strict minimum.
 * Returns index lists (not prices) so the chart can mark them without
 * altering data. Strict inequality avoids plateaus producing clusters.
 */
export function swingPoints(
  bars: OHLCVBar[],
  window = 10,
): { swingHighs: number[]; swingLows: number[] } {
  const swingHighs: number[] = [];
  const swingLows: number[] = [];
  for (let i = window; i < bars.length - window; i++) {
    const b = bars[i];
    if (!isFiniteNumber(b.high) || !isFiniteNumber(b.low)) continue;
    let isHigh = true;
    let isLow = true;
    for (let k = i - window; k <= i + window; k++) {
      if (k === i) continue;
      const o = bars[k];
      if (!isFiniteNumber(o.high) || !isFiniteNumber(o.low)) {
        isHigh = false;
        isLow = false;
        break;
      }
      if (o.high >= b.high) isHigh = false;
      if (o.low <= b.low) isLow = false;
      if (!isHigh && !isLow) break;
    }
    if (isHigh) swingHighs.push(i);
    if (isLow) swingLows.push(i);
  }
  return { swingHighs, swingLows };
}

/* ------------------------------------------------------------------ */
/* Chart-data mapping: pure passthrough. Switching chart types must not */
/* change the underlying financial data — these helpers only reshape.   */
/* ------------------------------------------------------------------ */

export type UTCTimestamp = number; // seconds since epoch, UTC

/** ISO timestamp → unix seconds (UTC). Returns null for unparseable input. */
export function toUTCTime(iso: string): UTCTimestamp | null {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return null;
  return Math.floor(ms / 1000) as UTCTimestamp;
}

export type CandlePoint = {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type LinePoint = { time: UTCTimestamp; value: number };
export type VolumePoint = { time: UTCTimestamp; value: number; up: boolean };

/**
 * Map bars → candlestick points. Drops bars with unparseable timestamps or
 * non-finite OHLC (honest gap — never interpolated). Preserves order.
 */
export function toCandlePoints(bars: OHLCVBar[]): CandlePoint[] {
  const pts: CandlePoint[] = [];
  for (const b of bars) {
    const t = toUTCTime(b.timestamp);
    if (t === null) continue;
    if (!isFiniteNumber(b.open) || !isFiniteNumber(b.high) || !isFiniteNumber(b.low) || !isFiniteNumber(b.close)) continue;
    pts.push({ time: t, open: b.open, high: b.high, low: b.low, close: b.close });
  }
  return pts;
}

/** Map bars → close-price line points (same filtering rules as candles). */
export function toClosePoints(bars: OHLCVBar[]): LinePoint[] {
  const pts: LinePoint[] = [];
  for (const b of bars) {
    const t = toUTCTime(b.timestamp);
    if (t === null) continue;
    if (!isFiniteNumber(b.close)) continue;
    pts.push({ time: t, value: b.close });
  }
  return pts;
}

/** Map bars → volume points with candle direction for coloring. */
export function toVolumePoints(bars: OHLCVBar[]): VolumePoint[] {
  const pts: VolumePoint[] = [];
  for (const b of bars) {
    const t = toUTCTime(b.timestamp);
    if (t === null) continue;
    if (!isFiniteNumber(b.volume) || !isFiniteNumber(b.open) || !isFiniteNumber(b.close)) continue;
    pts.push({ time: t, value: b.volume, up: b.close >= b.open });
  }
  return pts;
}

/** Map an aligned indicator array → line points at the bars' timestamps. */
export function toIndicatorPoints(
  bars: OHLCVBar[],
  values: (number | undefined)[],
): LinePoint[] {
  const pts: LinePoint[] = [];
  for (let i = 0; i < bars.length; i++) {
    const v = values[i];
    if (v === undefined || !isFiniteNumber(v)) continue;
    const t = toUTCTime(bars[i].timestamp);
    if (t === null) continue;
    pts.push({ time: t, value: v });
  }
  return pts;
}
