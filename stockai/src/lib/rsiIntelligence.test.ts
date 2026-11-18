import { describe, expect, it } from 'vitest';
import { agreementLabel, clampRsi, rsiPolyline, rsiTone, yForRsi, type RsiPoint } from './rsiIntelligence';

const point = (rsi: number | null): RsiPoint => ({
  timestamp: '2026-01-01',
  close: 100,
  rsi_7: rsi,
  rsi_14: rsi,
  rsi_21: rsi,
});

describe('RSI display helpers', () => {
  it('clamps RSI to the bounded oscillator range', () => {
    expect(clampRsi(120)).toBe(100);
    expect(clampRsi(-3)).toBe(0);
    expect(clampRsi(Number.NaN)).toBeNull();
    expect(clampRsi(undefined)).toBeNull();
  });

  it('maps RSI to an inverted y coordinate', () => {
    expect(yForRsi(100, 80)).toBe(0);
    expect(yForRsi(0, 80)).toBe(80);
    expect(yForRsi(50, 80)).toBe(40);
  });

  it('builds a polyline only from finite points', () => {
    const points = [point(20), point(null), point(80)];
    expect(rsiPolyline(points, 300, 80)).toBe('0.00,64.00 300.00,16.00');
    expect(rsiPolyline([point(null), point(50)], 300, 80)).toBe('');
  });

  it('labels agreement and zone tones without implying a recommendation', () => {
    expect(agreementLabel('agrees')).toContain('agrees');
    expect(agreementLabel('unknown')).toContain('no comparison');
    expect(rsiTone('overbought')).toContain('rose');
    expect(rsiTone('neutral')).toContain('slate');
  });
});
