export type CalibrationBin = {
  bin: string;
  n: number;
  mean_confidence?: number;
  observed_accuracy?: number;
  gap?: number;
  reliable?: boolean;
};

export type MonitorSnapshot = {
  observed_at?: string;
  confirmed?: {
    n_matured_30d?: number;
    accuracy_30d?: number;
    directional_accuracy_30d?: number;
    directional_n_30d?: number;
    neutral_predictions_30d?: number;
    accuracy_ci_30d?: { lower: number; upper: number; level: number } | null;
    accuracy_reliable_30d?: boolean;
    brier_30d?: number;
    log_loss_30d?: number;
    ece_30d?: number;
    latency_hours_median?: number;
    calibration_30d?: { bins?: CalibrationBin[]; ece?: number | null };
    by_model_version?: Record<string, { n: number; accuracy?: number; brier?: number }>;
    by_predicted_direction?: Record<string, { n: number; accuracy?: number; brier?: number }>;
    by_regime?: Record<string, { on?: { n: number; accuracy?: number }; off?: { n: number; accuracy?: number } }>;
    recent_7d?: { n: number; accuracy: number | null; provisional?: boolean; prior_23d?: { n: number; accuracy: number | null } };
  };
  provisional?: { predictions_pending_outcome?: number; coverage_24h?: number | null };
  learning?: {
    state?: string;
    min_matured_n?: number;
    confirmed_only?: boolean;
    automatic_retraining?: boolean;
    automatic_promotion?: boolean;
    next_action?: string;
  };
  drift?: Array<{ metric: string; value: number; threshold: number; note?: string }>;
};

export function pct(value: number | null | undefined, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : '—';
}

export function num(value: number | null | undefined, digits = 3): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

export function calibrationGap(bin: CalibrationBin): number | null {
  if (typeof bin.gap === 'number' && Number.isFinite(bin.gap)) return bin.gap;
  if (typeof bin.mean_confidence !== 'number' || typeof bin.observed_accuracy !== 'number') return null;
  return bin.observed_accuracy - bin.mean_confidence;
}

export function calibrationVerdict(ece: number | null | undefined, n: number | undefined): string {
  if (!n || n < 30 || typeof ece !== 'number' || !Number.isFinite(ece)) {
    return 'Collecting: fewer than 30 matured outcomes, so calibration is not yet confirmed.';
  }
  if (ece <= 0.03) return 'Calibration is close to stated confidence (ECE ≤ 3 points).';
  if (ece <= 0.08) return 'Calibration gap is moderate (ECE 3–8 points); review before relying on confidence.';
  return 'Calibration gap is large (ECE > 8 points); confidence is not yet trustworthy.';
}

export function learningStateLabel(state: string | undefined): string {
  if (state === 'monitoring') return 'monitoring';
  if (state === 'calibration_review') return 'calibration review';
  return 'collecting outcomes';
}
