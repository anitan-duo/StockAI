/**
 * Guards for per-prediction explanation rendering.
 *
 * Explanations are immutable and keyed by prediction_id. The UI must never
 * display an explanation that belongs to a different prediction than the one
 * currently on screen (stale-response race).
 */

export type ExplanationContribution = {
  feature: string;
  label: string;
  value: number;
  formatted_value: string;
  contribution: number;
  contribution_up: number;
  contribution_down: number;
  contribution_neutral: number;
  net_bullish: number;
};

export type PredictionExplanation = {
  prediction_id: string;
  symbol?: string | null;
  exchange?: string | null;
  horizon: string;
  model_horizon: string;
  model_version: string;
  artifact_sha: string;
  feature_vector_hash: string;
  predicted_direction: 'up' | 'neutral' | 'down' | string;
  prediction_timestamp: string;
  data_timestamp: string;
  generated_at: string;
  explainer_version: string;
  explainer: {
    method: string;
    library: string;
    library_version?: string | null;
    estimator?: string;
    calibrator?: string | null;
    explained_output: string;
    calibration_note?: string;
  };
  served_probabilities: Record<string, number>;
  raw_model_probabilities: Record<string, number>;
  reconciliation: {
    max_abs_error: number;
    tolerance: number;
    matches_model_output: boolean;
    direction_matches_saved: boolean;
    served_vs_raw_max_delta: number;
  };
  contributions: ExplanationContribution[];
  top_positive: ExplanationContribution[];
  top_negative: ExplanationContribution[];
  missing_features: string[];
  unreliable_features: string[];
  warnings: string[];
  no_clear_edge: boolean;
  narrative: {
    summary: string;
    bullets: string[];
    limiting_factors: string[];
    caveats: string[];
  };
};

export function explanationMatchesPrediction(
  explanation: PredictionExplanation | null | undefined,
  predictionId: string | null | undefined,
): boolean {
  if (!explanation || !predictionId) return false;
  return explanation.prediction_id === predictionId;
}

export function contributionPoints(contribution: number): number {
  return Number.isFinite(contribution) ? contribution * 100 : 0;
}

export function contributionBarWidth(contribution: number, maxAbs: number): number {
  if (!Number.isFinite(contribution) || !Number.isFinite(maxAbs) || maxAbs <= 0) return 0;
  return Math.min(100, Math.max(2, (Math.abs(contribution) / maxAbs) * 100));
}
