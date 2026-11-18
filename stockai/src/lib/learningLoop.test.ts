import { describe, expect, it } from 'vitest';
import { calibrationGap, calibrationVerdict, learningStateLabel, pct } from './learningLoop';

describe('learning loop helpers', () => {
  it('formats percentages without inventing values', () => {
    expect(pct(0.734)).toBe('73.4%');
    expect(pct(null)).toBe('—');
    expect(pct(Number.NaN)).toBe('—');
  });

  it('computes calibration gap from stored or derived values', () => {
    expect(calibrationGap({ bin: '50-60%', n: 10, gap: -0.04 })).toBeCloseTo(-0.04);
    expect(calibrationGap({ bin: '50-60%', n: 10, mean_confidence: 0.55, observed_accuracy: 0.6 })).toBeCloseTo(0.05);
    expect(calibrationGap({ bin: '50-60%', n: 10 })).toBeNull();
  });

  it('refuses to call calibration confirmed below the sample floor', () => {
    expect(calibrationVerdict(0.01, 12)).toContain('Collecting');
    expect(calibrationVerdict(0.02, 100)).toContain('close to stated');
    expect(calibrationVerdict(0.05, 100)).toContain('moderate');
    expect(calibrationVerdict(0.2, 100)).toContain('large');
  });

  it('uses explicit state labels', () => {
    expect(learningStateLabel('collecting')).toBe('collecting outcomes');
    expect(learningStateLabel('calibration_review')).toBe('calibration review');
    expect(learningStateLabel(undefined)).toBe('collecting outcomes');
  });
});
