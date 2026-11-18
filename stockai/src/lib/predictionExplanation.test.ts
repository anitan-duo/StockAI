import { describe, expect, it } from 'vitest';
import {
  contributionBarWidth,
  contributionPoints,
  explanationMatchesPrediction,
  type PredictionExplanation,
} from './predictionExplanation';

function explanation(id: string): PredictionExplanation {
  return {
    prediction_id: id,
    horizon: '1d',
    model_horizon: '1d',
    model_version: 'real-v1.0',
    artifact_sha: 'sha256:abc',
    feature_vector_hash: 'sha256:def',
    predicted_direction: 'up',
    prediction_timestamp: '2026-01-01T00:00:00Z',
    data_timestamp: '2026-01-01T00:00:00Z',
    generated_at: '2026-01-01T00:00:01Z',
    explainer_version: 'v1',
    explainer: { method: 'tree_shap', library: 'shap', explained_output: 'pre_calibration_model_probability' },
    served_probabilities: { up: 0.5, neutral: 0.3, down: 0.2 },
    raw_model_probabilities: { up: 0.4, neutral: 0.3, down: 0.3 },
    reconciliation: {
      max_abs_error: 1e-12,
      tolerance: 2e-5,
      matches_model_output: true,
      direction_matches_saved: true,
      served_vs_raw_max_delta: 0.1,
    },
    contributions: [],
    top_positive: [],
    top_negative: [],
    missing_features: [],
    unreliable_features: [],
    warnings: [],
    no_clear_edge: false,
    narrative: { summary: '', bullets: [], limiting_factors: [], caveats: [] },
  };
}

describe('prediction explanation guards', () => {
  it('rejects an explanation for another prediction', () => {
    expect(explanationMatchesPrediction(explanation('a'), 'b')).toBe(false);
    expect(explanationMatchesPrediction(explanation('b'), 'b')).toBe(true);
    expect(explanationMatchesPrediction(null, 'b')).toBe(false);
    expect(explanationMatchesPrediction(explanation('b'), null)).toBe(false);
  });

  it('converts contributions to probability points', () => {
    expect(contributionPoints(0.025)).toBeCloseTo(2.5);
    expect(contributionPoints(-0.01)).toBeCloseTo(-1);
    expect(contributionPoints(Number.NaN)).toBe(0);
  });

  it('scales contribution bars safely', () => {
    expect(contributionBarWidth(0.05, 0.1)).toBe(50);
    expect(contributionBarWidth(-0.1, 0.1)).toBe(100);
    expect(contributionBarWidth(0, 0)).toBe(0);
  });
});
