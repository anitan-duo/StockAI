import { describe, expect, it } from 'vitest';
import { deriveHealthState, type HealthState } from '@/components/mlops/model-health-panel';

const CI = { lower: 0.55, upper: 0.75 };

function confirmed(overrides: Record<string, unknown> = {}) {
  return {
    n_matured_30d: 40,
    accuracy_30d: 0.6,
    accuracy_ci_30d: CI,
    accuracy_reliable_30d: true,
    recent_7d: { n: 10, accuracy: 0.6, prior_23d: { n: 30, accuracy: 0.58 } },
    ...overrides,
  };
}

describe('model health state derivation', () => {
  it('reports HEALTHY on a reliable matured sample above the neutral band', () => {
    expect(deriveHealthState(confirmed(), {})).toBe('HEALTHY');
  });

  it('reports INSUFFICIENT EVIDENCE when no outcomes matured', () => {
    expect(deriveHealthState(confirmed({ n_matured_30d: 0, accuracy_30d: null }), {})).toBe(
      'INSUFFICIENT EVIDENCE'
    );
  });

  it('reports INSUFFICIENT EVIDENCE when the sample is below the reliability floor', () => {
    expect(deriveHealthState(confirmed({ accuracy_reliable_30d: false }), {})).toBe(
      'INSUFFICIENT EVIDENCE'
    );
  });

  it('reports STALE DATA when nothing matured in the last 7 days', () => {
    expect(deriveHealthState(confirmed({ recent_7d: { n: 0, accuracy: null } }), {})).toBe(
      'STALE DATA'
    );
  });

  it('reports NO CLEAR EDGE when the CI spans the 1/3 neutral rate', () => {
    const spanning = { lower: 0.25, upper: 0.55 };
    expect(deriveHealthState(confirmed({ accuracy_ci_30d: spanning }), {})).toBe('NO CLEAR EDGE');
  });

  it('reports DEGRADED on a reliable sample below 0.5 accuracy', () => {
    expect(deriveHealthState(confirmed({ accuracy_30d: 0.42, accuracy_ci_30d: { lower: 0.36, upper: 0.48 } }), {})).toBe(
      'DEGRADED'
    );
  });

  it('reports UNAVAILABLE when monitoring data is missing', () => {
    expect(deriveHealthState(null, {})).toBe('UNAVAILABLE');
    expect(deriveHealthState({ _error: 'db down' }, {})).toBe('UNAVAILABLE');
  });

  it('reports RESEARCH ONLY when there is no production champion', () => {
    expect(deriveHealthState(confirmed(), {}, { hasChampion: false })).toBe('RESEARCH ONLY');
  });

  it('reports MODEL DRIFT when confirmed-metric drift alerts are open', () => {
    expect(
      deriveHealthState(confirmed(), {}, { hasChampion: true, openAlerts: [{ id: '1', metric: 'ece_30d' }] })
    ).toBe('MODEL DRIFT');
  });

  it('lets drift outrank staleness but research-only outrank drift', () => {
    // Drift beats stale data.
    expect(
      deriveHealthState(confirmed({ recent_7d: { n: 0 } }), {}, { openAlerts: [{ id: '1' }] })
    ).toBe('MODEL DRIFT');
    // No champion beats everything data-derived.
    expect(
      deriveHealthState(confirmed(), {}, { hasChampion: false, openAlerts: [{ id: '1' }] })
    ).toBe('RESEARCH ONLY');
  });

  it('treats provisional signals as never counting as evidence', () => {
    // High provisional coverage cannot rescue an empty confirmed sample.
    expect(deriveHealthState(confirmed({ n_matured_30d: 0 }), { instruments_covered_24h: 19 })).toBe(
      'INSUFFICIENT EVIDENCE'
    );
  });

  it('only ever emits the mandated state vocabulary', () => {
    const allowed: HealthState[] = [
      'HEALTHY',
      'DEGRADED',
      'STALE DATA',
      'INSUFFICIENT EVIDENCE',
      'MODEL DRIFT',
      'NO CLEAR EDGE',
      'RESEARCH ONLY',
      'UNAVAILABLE',
    ];
    for (const s of [
      deriveHealthState(confirmed(), {}),
      deriveHealthState(confirmed({ n_matured_30d: 0 }), {}),
      deriveHealthState(confirmed({ recent_7d: { n: 0 } }), {}),
      deriveHealthState(confirmed({ accuracy_reliable_30d: false }), {}),
      deriveHealthState(confirmed({ accuracy_ci_30d: { lower: 0.2, upper: 0.6 } }), {}),
      deriveHealthState(confirmed({ accuracy_30d: 0.4 }), {}),
      deriveHealthState(null, {}),
    ]) {
      expect(allowed).toContain(s);
    }
  });
});
