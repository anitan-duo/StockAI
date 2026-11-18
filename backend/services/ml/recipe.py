"""Single-source production model recipe.

Everything that defines *how* StockAI turns features into probabilities and
signals lives here, so production inference, training, calibration, and causal
backtesting cannot silently diverge. No timestamps, no I/O, no leakage surface:
pure definitions + deterministic math.
"""

from typing import Literal

RANDOM_STATE = 42

# Target definition v1 (matches services.ml.target.TargetDefinition defaults)
TARGET_HORIZON_DAYS = 1
TARGET_UP_THRESHOLD = 0.005
TARGET_DOWN_THRESHOLD = -0.005
TARGET_VERSION = "v1-h1d-0.5pct"

# Wide-band research task (P10-E010): ±1.0% neutral band, same 1d horizon.
# Production default thresholds above are UNCHANGED; research specs must name
# these explicitly so train-time and eval-time mappings cannot diverge.
TARGET_WIDE_UP_THRESHOLD = 0.01
TARGET_WIDE_DOWN_THRESHOLD = -0.01

# Native forecast horizon served by v1.0 artifacts. The predictions API must
# refuse to label these probabilities with any other horizon (§15 horizon lie).
MODEL_NATIVE_HORIZON = "1d"

# Feature pipeline version (matches services.ml.features.FeaturePipeline defaults)
FEATURE_VERSION = "v1"
FEATURE_LOOKBACK_BARS = 252
FEATURE_MIN_PERIODS = 20

# Calibration (matches ModelTrainer defaults)
CALIBRATION_METHOD = "isotonic"
CALIBRATION_CV_FOLDS = 3
CALIBRATION_MIN_SAMPLES = 60

# Model hyperparameters (must stay in sync with ModelTrainer.get_base_models)
LOGISTIC_PARAMS: dict = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "class_weight": "balanced"}
RANDOM_FOREST_PARAMS: dict = {
    "n_estimators": 300,
    "max_depth": 10,
    "min_samples_split": 10,
    "min_samples_leaf": 5,
    "class_weight": "balanced",
    "n_jobs": -1,
}
GRADIENT_BOOSTING_PARAMS: dict = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
}
MODEL_NAMES = ("logistic", "random_forest", "gradient_boosting")

# Model-family ablation (P9). The production ensemble uses all three families;
# research may restrict to a single family to isolate variance-vs-signal.
# "ensemble" is the v1 behavior and the default everywhere in production paths.
MODEL_FAMILIES = ("ensemble",) + MODEL_NAMES

# Feature subsets for disciplined ablation (P5). Subsets are applied as
# post-computation COLUMN RESTRICTIONS on the frozen 87-feature schema:
# removing columns cannot introduce future information. "full" is the v1
# behavior; anything else must be named explicitly in experiment records.
FEATURE_SUBSET_NAMES = ("full", "normalized")

# Raw level features excluded by the "normalized" subset: price-scale levels
# (SMA/EMA in currency units), cumulative/truncated level accumulators (OBV),
# and nominal dollar volumes. Dimensionless relatives (pct_from_*, returns,
# oscillators, MACD differences are kept: they are the normalized signal the
# level features were proxying for.
_NORMALIZED_DROP_PREFIXES = (
    "sma_",
    "ema_",
    "obv",
    "dollar_volume",
    "avg_dollar_volume_",
)


def apply_feature_subset(feat_cols: list[str], subset: str = "full") -> list[str]:
    """Restrict computed feature columns to a named ablation subset."""
    if subset == "full":
        return list(feat_cols)
    if subset == "normalized":
        kept = [c for c in feat_cols if not c.startswith(_NORMALIZED_DROP_PREFIXES)]
        if not kept:
            raise ValueError("normalized subset removed all features")
        return kept
    raise ValueError(f"Unknown feature subset: {subset}")

# Edge / signal semantics (shared by prediction API and backtest signal gate)
NO_EDGE_THRESHOLD = 0.40
NO_EDGE_CONFIDENCE_CAP = 55
ENTRY_CONFIDENCE_MIN = 60
ENTRY_PROB_MIN = 0.5

Direction = Literal["up", "neutral", "down"]


def get_base_models(random_state: int = RANDOM_STATE) -> dict:
    """Instantiate the production model family (unfitted)."""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    return {
        "logistic": LogisticRegression(**LOGISTIC_PARAMS, random_state=random_state),
        "random_forest": RandomForestClassifier(**RANDOM_FOREST_PARAMS, random_state=random_state),
        "gradient_boosting": GradientBoostingClassifier(**GRADIENT_BOOSTING_PARAMS, random_state=random_state),
    }


def get_family_models(family: str = "ensemble", random_state: int = RANDOM_STATE) -> dict:
    """Instantiate one model family (P9 ablation) or the full ensemble.

    ``ensemble`` returns all three production models (v1 behavior).
    A single family name returns just that model; unknown names raise
    ValueError. Restriction-only: no new hyperparameters, no retuning.
    """
    if family == "ensemble":
        return get_base_models(random_state=random_state)
    models = get_base_models(random_state=random_state)
    if family not in models:
        raise ValueError(f"Unknown model family: {family} (expected one of {MODEL_FAMILIES})")
    return {family: models[family]}


def direction_from_probs(up_prob: float, neutral_prob: float, down_prob: float) -> Direction:
    """Deterministic class ordering: ties resolve to neutral."""
    if up_prob > down_prob and up_prob > neutral_prob:
        return "up"
    if down_prob > up_prob and down_prob > neutral_prob:
        return "down"
    return "neutral"


def confidence_from_probs(up_prob: float, down_prob: float, max_prob: float) -> int:
    """Production confidence: separation-based, graded below no-edge threshold.

    Below NO_EDGE_THRESHOLD the confidence cap grades smoothly from 50
    (when max_prob is uniform at 1/3) up to NO_EDGE_CONFIDENCE_CAP (at the
    threshold), instead of a rigid flat cap.

    Supports a weak-signal tier: predictions just below the threshold retain
    slightly higher confidence than near-uniform ones.
    """
    confidence = int(50 + abs(up_prob - down_prob) * 40)
    if max_prob < NO_EDGE_THRESHOLD:
        floor = 1.0 / 3.0
        span = NO_EDGE_THRESHOLD - floor
        if span > 0:
            frac = max(0.0, min(1.0, (max_prob - floor) / span))
        else:
            frac = 0.0
        cap = 50 + int((NO_EDGE_CONFIDENCE_CAP - 50) * frac)
        confidence = min(confidence, cap)
    return confidence


def has_clear_edge(up_prob: float, neutral_prob: float, down_prob: float) -> bool:
    """True unless the top probability is below the no-edge threshold."""
    return max(up_prob, neutral_prob, down_prob) >= NO_EDGE_THRESHOLD


import math

def normalize_probs(up_prob: float, neutral_prob: float, down_prob: float) -> tuple[float, float, float]:
    """Renormalize to sum 1 (guards calibrator rounding drift)."""
    if not all(math.isfinite(p) for p in (up_prob, neutral_prob, down_prob)):
        raise ValueError("Non-finite probability input")
    total = up_prob + neutral_prob + down_prob
    if total <= 0:
        raise ValueError("Non-positive probability mass")
    probs = (up_prob / total, neutral_prob / total, down_prob / total)
    if abs(sum(probs) - 1.0) > 1e-6:
        raise ValueError("Probs do not sum to 1")
    return probs


def combine_ensemble(prob_vectors: list) -> list[float]:
    """Mean-ensemble over model probability vectors (fixed weights, no learning)."""
    import numpy as np

    if not prob_vectors:
        raise ValueError("No model probabilities to combine")
    return [float(v) for v in np.mean(np.asarray(prob_vectors, dtype=float), axis=0)]


def expected_return_from_probs(up_prob: float, down_prob: float, realized_vol_20d: float) -> float:
    """vol-scaled expected return fraction; flat 2.0x multiplier removed."""
    vol_fraction = float(realized_vol_20d) / 100.0
    vol_fraction = min(max(vol_fraction, 0.01), 0.5)
    return (up_prob - down_prob) * vol_fraction * 0.5


def recency_weights(n_rows: int, halflife: float) -> list[float]:
    """Exponential recency weights for chronological training rows (P16).

    Row 0 is oldest, row n-1 newest: w_k = 0.5**((n-1-k)/halflife).
    Newest is always exactly 1.0. Non-positive halflife raises (fail loud).
    Pure function of positions — no labels, no future data.
    """
    if halflife is None or halflife <= 0:
        raise ValueError(f"recency halflife must be positive, got {halflife}")
    if n_rows <= 0:
        raise ValueError("n_rows must be positive")
    return [float(0.5 ** ((n_rows - 1 - k) / halflife)) for k in range(n_rows)]
