"""Faithful per-prediction feature attribution.

The served artifact is a three-class classifier (v1.0: random forest) wrapped
in isotonic calibration. This module explains the *underlying model output*
with the feature vector that produced the saved prediction:

- tree models: SHAP TreeExplainer (exact TreeSHAP, no sampling),
- linear models: coefficient x standardized-feature contributions,
- anything else: deterministic occlusion against the training feature means.

Calibration is reported separately and explicitly: calibrated probabilities
are not additive in these contributions. Attribution is associative, not
causal — a SHAP value never proves a feature caused a future price move.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

EXPLAINER_VERSION = "v1"
METHOD_TREE_SHAP = "tree_shap"
METHOD_LINEAR = "linear_coefficients"
METHOD_OCCLUSION = "mean_occlusion"
CLASS_NAMES = ("down", "neutral", "up")
NARRATIVE_VERSION = "v1"

FEATURE_LABELS: dict[str, str] = {
    "return_1d": "1-day return",
    "log_return_1d": "1-day log return",
    "gap_pct": "Opening gap",
    "body_pct": "Candle body",
    "close_position": "Close position in daily range",
    "roc_5d": "5-day rate of change",
    "roc_10d": "10-day rate of change",
    "roc_20d": "20-day rate of change",
    "roc_60d": "60-day rate of change",
    "momentum_10d": "10-day momentum",
    "momentum_20d": "20-day momentum",
    "momentum_60d": "60-day momentum",
    "pct_from_high_20d": "Distance from 20-day high",
    "pct_from_low_20d": "Distance from 20-day low",
    "realized_vol_5d": "5-day realized volatility",
    "realized_vol_10d": "10-day realized volatility",
    "realized_vol_20d": "20-day realized volatility",
    "realized_vol_60d": "60-day realized volatility",
    "vol_percentile_60d": "60-day volatility percentile",
    "vol_percentile_120d": "120-day volatility percentile",
    "vol_percentile_252d": "252-day volatility percentile",
    "vol_regime": "Short vs long volatility regime",
    "rel_volume_10d": "Relative volume (10-day)",
    "rel_volume_20d": "Relative volume (20-day)",
    "rel_volume_60d": "Relative volume (60-day)",
    "volume_trend_20d": "20-day volume trend",
    "vol_price_corr_20d": "Price-volume correlation (20-day)",
    "sma_20": "20-day moving average",
    "sma_50": "50-day moving average",
    "sma_200": "200-day moving average",
    "pct_from_sma_20": "Price vs 20-day SMA",
    "pct_from_sma_50": "Price vs 50-day SMA",
    "pct_from_sma_200": "Price vs 200-day SMA",
    "macd": "MACD line",
    "macd_signal": "MACD signal line",
    "macd_histogram": "MACD histogram",
    "adx": "ADX trend strength",
    "plus_di": "Positive directional indicator",
    "minus_di": "Negative directional indicator",
    "rsi_7": "RSI(7)",
    "rsi_14": "RSI(14)",
    "rsi_21": "RSI(21)",
    "stoch_k_14": "Stochastic %K(14)",
    "stoch_d_14": "Stochastic %D(14)",
    "williams_r_14": "Williams %R(14)",
    "cci_20": "Commodity Channel Index(20)",
    "trend_regime": "Trend regime (50d vs 200d SMA)",
    "vol_regime_high": "High-volatility regime flag",
    "vol_regime_low": "Low-volatility regime flag",
    "momentum_regime": "Momentum regime",
    "large_jump_up": "Large upward price jump flag",
    "large_jump_down": "Large downward price jump flag",
    "volume_spike": "Volume spike flag",
    "price_discontinuity": "Price discontinuity flag",
}

_PERCENT_PREFIXES = (
    "roc_",
    "momentum_",
    "pct_from_",
    "rel_return_",
    "return_",
    "log_return_",
    "gap_pct",
    "body_pct",
    "upper_shadow_pct",
    "lower_shadow_pct",
    "rel_strength_",
)
_VOLATILITY_PREFIXES = ("realized_vol_", "parkinson_vol_", "garman_klass_vol_")
_REGIME_FLAGS = {
    "trend_regime",
    "vol_regime",
    "vol_regime_high",
    "vol_regime_low",
    "momentum_regime",
    "large_jump_up",
    "large_jump_down",
    "volume_spike",
    "price_discontinuity",
    "gap_up",
    "gap_down",
}


class ExplanationError(Exception):
    """Explanation cannot be produced faithfully (disclosed to callers)."""

    def __init__(self, message: str, missing: list[str] | None = None):
        super().__init__(message)
        self.missing = missing or []


@dataclass(frozen=True)
class Contribution:
    feature: str
    label: str
    value: float
    standardized_value: float
    contribution: float
    contribution_up: float
    contribution_down: float
    contribution_neutral: float
    net_bullish: float
    formatted_value: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "label": self.label,
            "value": round(self.value, 8),
            "standardized_value": round(self.standardized_value, 6),
            "contribution": round(self.contribution, 8),
            "contribution_up": round(self.contribution_up, 8),
            "contribution_down": round(self.contribution_down, 8),
            "contribution_neutral": round(self.contribution_neutral, 8),
            "net_bullish": round(self.net_bullish, 8),
            "formatted_value": self.formatted_value,
        }


def feature_vector_hash(feature_names: list[str], values: list[float]) -> str:
    """Stable hash binding an explanation to one ordered feature vector."""
    payload = "|".join(f"{n}={float(v):.12g}" for n, v in zip(feature_names, values, strict=True))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def feature_label(name: str) -> str:
    if name in FEATURE_LABELS:
        return FEATURE_LABELS[name]
    if name.startswith("pct_from_sma_"):
        return f"Price vs {name.rsplit('_', 1)[-1]}-day SMA"
    if name.startswith("sma_"):
        return f"{name.split('_', 1)[1]}-day moving average"
    if name.startswith("ema_"):
        return f"{name.split('_', 1)[1]}-day EMA"
    if name.startswith("rsi_"):
        return f"RSI({name.split('_', 1)[1]})"
    if name.startswith("rel_volume_"):
        return f"Relative volume ({name.rsplit('_', 1)[-1]})"
    if name.startswith("realized_vol_"):
        return f"{name.rsplit('_', 2)[-2]}-day realized volatility"
    return name.replace("_", " ")


def format_feature_value(name: str, value: float) -> str:
    if not math.isfinite(value):
        return "unavailable"
    if name in _REGIME_FLAGS or name.startswith("gap_up") or name.startswith("gap_down"):
        return "yes" if value >= 0.5 else "no"
    if name.startswith("rsi_") or name.startswith("stoch_") or name.startswith("williams_r_"):
        return f"{value:.1f}"
    if name == "close_position" or name.startswith("vol_percentile_"):
        return f"{value * 100:.1f}th pct"
    if name.startswith("rel_volume_"):
        return f"{value:.2f}x"
    if name.startswith(_VOLATILITY_PREFIXES):
        return f"{value:.1f}% annualized"
    if name.startswith(_PERCENT_PREFIXES):
        return f"{value * 100:+.2f}%"
    if name.startswith("dollar_volume") or name.startswith("avg_dollar_volume_"):
        return f"${value:,.0f}"
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:.4g}"


def _class_contribution(shap_row: np.ndarray, class_index: int) -> np.ndarray:
    return np.asarray(shap_row[:, class_index], dtype=float)


def _tree_shap(estimator: Any, x_scaled: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    import shap

    explainer = shap.TreeExplainer(estimator)
    values = explainer.shap_values(x_scaled, check_additivity=False)
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 3 and arr.shape[0] == 1:
        # (n_samples, n_features, n_classes)
        row = arr[0]
    elif arr.ndim == 3 and arr.shape[0] == len(estimator.classes_):
        # legacy layout: (n_classes, n_samples, n_features)
        row = arr[:, 0, :].T
    elif arr.ndim == 2:
        # (n_classes, n_features) or (n_features, n_classes)
        if arr.shape[0] == len(estimator.classes_):
            row = arr.T
        else:
            row = arr
    else:
        raise ExplanationError(f"Unsupported SHAP output shape: {arr.shape}")
    expected = np.asarray(explainer.expected_value, dtype=float).reshape(-1)
    if expected.size == 1 and row.shape[1] > 1:
        expected = np.repeat(expected, row.shape[1])
    return row, expected


def _linear_contributions(estimator: Any, x_scaled: np.ndarray, n_classes: int) -> tuple[np.ndarray, np.ndarray]:
    coef = np.asarray(estimator.coef_, dtype=float)
    if coef.ndim == 1:
        coef = np.vstack([-coef, np.zeros_like(coef), coef])
    if coef.shape[0] != n_classes:
        raise ExplanationError("Linear model class dimension does not match served classes")
    row = (coef * x_scaled[0]).T
    intercept = np.asarray(getattr(estimator, "intercept_", np.zeros(n_classes)), dtype=float).reshape(-1)
    return row, intercept


def _occlusion_contributions(
    estimator: Any,
    x_scaled: np.ndarray,
    baseline_scaled: np.ndarray,
    class_index: int,
) -> np.ndarray:
    base_prob = float(estimator.predict_proba(x_scaled)[0, class_index])
    out = np.zeros(x_scaled.shape[1], dtype=float)
    for i in range(x_scaled.shape[1]):
        probe = x_scaled.copy()
        probe[0, i] = baseline_scaled[0, i]
        out[i] = base_prob - float(estimator.predict_proba(probe)[0, class_index])
    return out


def _direction_index(direction: str, classes: list[Any]) -> int:
    label = direction.lower()
    if label not in CLASS_NAMES:
        raise ExplanationError(f"Unknown predicted direction: {direction}")
    target = CLASS_NAMES.index(label)
    try:
        return list(classes).index(target)
    except ValueError as exc:
        raise ExplanationError(f"Model classes {classes} do not contain {label}") from exc


def _driver_phrase(contribution: Contribution, direction: str) -> str:
    points = abs(contribution.contribution) * 100
    verb = "supported" if contribution.contribution >= 0 else "worked against"
    return (
        f"{contribution.label} ({contribution.formatted_value}) {verb} the "
        f"{direction.upper()} score by {points:.1f} probability points."
    )


def _limiting_factors(
    contributions: list[Contribution],
    direction: str,
    served_probs: dict[str, float],
    no_clear_edge: bool,
) -> list[str]:
    factors: list[str] = []
    opponents = [c for c in contributions if c.contribution < 0]
    opponents.sort(key=lambda c: c.contribution)
    for c in opponents[:3]:
        factors.append(
            f"{c.label} ({c.formatted_value}) pushed against the {direction.upper()} forecast "
            f"(-{abs(c.contribution) * 100:.1f} probability points)."
        )
    top_prob = max(served_probs.values()) if served_probs else 0.0
    if no_clear_edge:
        factors.append(
            f"Top-class probability is {top_prob:.1%}, below the 40% no-clear-edge threshold; "
            "the model is not expressing a confident directional view."
        )
    elif top_prob < 0.55:
        factors.append(
            f"Top-class probability is only {top_prob:.1%}; probability mass remains split across classes."
        )
    return factors


def _build_narrative(
    direction: str,
    contributions: list[Contribution],
    served_probs: dict[str, float],
    limiting: list[str],
    no_clear_edge: bool,
) -> dict[str, Any]:
    positives = [c for c in contributions if c.contribution > 0][:3]
    negatives = [c for c in contributions if c.contribution < 0][:2]

    if positives:
        lead = ", ".join(f"{c.label} ({c.formatted_value})" for c in positives)
        summary = (
            f"The {direction.upper()} forecast is driven mainly by {lead}. "
            f"Served probabilities are up {served_probs['up']:.1%}, "
            f"neutral {served_probs['neutral']:.1%}, down {served_probs['down']:.1%}."
        )
    else:
        summary = (
            f"No feature contributed positively to the {direction.upper()} class; "
            "the forecast reflects a weak or conflicted signal."
        )

    bullets = [_driver_phrase(c, direction) for c in positives]
    if negatives:
        bullets.append(
            "Contrary evidence: "
            + "; ".join(f"{c.label} ({c.formatted_value})" for c in negatives)
            + "."
        )

    caveats = [
        "SHAP contributions explain the model's pre-calibration output, not the calibrated probabilities. "
        "Isotonic calibration changes absolute probability levels but not the feature ranking shown here.",
        "Attribution is associative, not causal. A feature contributing to a forecast does not establish that "
        "the feature caused the subsequent price move.",
        "Correlated technical features (momentum, moving averages, volatility) can share credit; "
        "magnitudes should be read as directional evidence, not precise independent effects.",
    ]
    if no_clear_edge:
        caveats.append("NO CLEAR EDGE: the top class probability is below the production threshold.")
    return {
        "summary": summary,
        "bullets": bullets,
        "limiting_factors": limiting,
        "caveats": caveats,
        "narrative_version": NARRATIVE_VERSION,
    }


def explain_feature_vector(
    estimator: Any,
    scaler: Any,
    calibrator: Any,
    feature_names: list[str],
    feature_values: list[float],
    predicted_direction: str,
    served_probabilities: dict[str, float] | None = None,
    no_clear_edge: bool = False,
) -> dict[str, Any]:
    """Explain one feature vector with the model that produced it.

    ``feature_values`` must come from the saved prediction snapshot so the
    explanation cannot drift from the inference vector or use future data.
    """
    names = list(feature_names)
    if len(feature_values) != len(names):
        raise ExplanationError(
            f"Feature vector length {len(feature_values)} != schema length {len(names)}"
        )
    missing: list[str] = []
    clean: list[float] = []
    for name, value in zip(names, feature_values, strict=True):
        try:
            fval = float(value)
        except (TypeError, ValueError):
            missing.append(name)
            continue
        if not math.isfinite(fval):
            missing.append(name)
            continue
        clean.append(fval)
    if missing:
        raise ExplanationError(
            f"Explanation unavailable: {len(missing)} feature(s) missing or non-finite",
            missing=missing,
        )

    x_raw = np.asarray([clean], dtype=float)
    import pandas as pd

    x_scaled = np.asarray(scaler.transform(pd.DataFrame(x_raw, columns=names)), dtype=float)
    raw_probs = np.asarray(estimator.predict_proba(x_scaled)[0], dtype=float)
    classes = list(getattr(estimator, "classes_", range(len(raw_probs))))
    target_index = _direction_index(predicted_direction, classes)

    estimator_name = type(estimator).__name__
    is_tree = hasattr(estimator, "estimators_") or "Forest" in estimator_name or "Boost" in estimator_name
    is_linear = hasattr(estimator, "coef_")

    if is_tree:
        method = METHOD_TREE_SHAP
        import shap

        row, expected = _tree_shap(estimator, x_scaled)
        shap_version = getattr(shap, "__version__", "unknown")
    elif is_linear:
        method = METHOD_LINEAR
        row, expected = _linear_contributions(estimator, x_scaled, len(classes))
        shap_version = None
    else:
        method = METHOD_OCCLUSION
        baseline_raw = np.asarray(getattr(scaler, "mean_", np.zeros(len(names))), dtype=float).reshape(1, -1)
        baseline_scaled = np.asarray(scaler.transform(pd.DataFrame(baseline_raw, columns=names)), dtype=float)
        row = np.zeros((len(names), len(classes)), dtype=float)
        row[:, target_index] = _occlusion_contributions(estimator, x_scaled, baseline_scaled, target_index)
        expected = raw_probs - row.sum(axis=0)
        shap_version = None

    if row.shape[0] != len(names) or row.shape[1] != len(classes):
        raise ExplanationError(
            f"Contribution shape {row.shape} does not match {len(names)} features x {len(classes)} classes"
        )
    if expected.size != len(classes):
        raise ExplanationError("Explainer baseline does not match model class count")

    standardized = x_scaled[0]
    scale = np.asarray(getattr(scaler, "scale_", np.ones(len(names))), dtype=float)
    unreliable = [
        names[i]
        for i in range(len(names))
        if abs(float(standardized[i])) > 8.0 or (np.isfinite(scale[i]) and abs(float(scale[i])) <= 1e-12)
    ]

    contributions: list[Contribution] = []
    for i, name in enumerate(names):
        up = float(row[i, classes.index(2)]) if 2 in classes else 0.0
        down = float(row[i, classes.index(0)]) if 0 in classes else 0.0
        neutral = float(row[i, classes.index(1)]) if 1 in classes else 0.0
        contributions.append(
            Contribution(
                feature=name,
                label=feature_label(name),
                value=float(clean[i]),
                standardized_value=float(standardized[i]),
                contribution=float(row[i, target_index]),
                contribution_up=up,
                contribution_down=down,
                contribution_neutral=neutral,
                net_bullish=up - down,
                formatted_value=format_feature_value(name, float(clean[i])),
            )
        )

    contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
    supporting = [c for c in contributions if c.contribution > 0]
    opposing = [c for c in contributions if c.contribution < 0]

    default_served = {
        CLASS_NAMES[int(cls)] if int(cls) in range(3) else str(cls): float(raw_probs[i])
        for i, cls in enumerate(classes)
    }
    served = served_probabilities or default_served
    served_total = sum(served.values())
    if served_total > 0:
        served = {k: float(v) / served_total for k, v in served.items()}

    reconstructed = expected + row.sum(axis=0)
    max_error = float(np.max(np.abs(reconstructed - raw_probs)))
    tolerance = 2e-5
    dominant_index = int(np.argmax(raw_probs))
    dominant_class = classes[dominant_index]
    recomputed_direction = (
        CLASS_NAMES[int(dominant_class)]
        if int(dominant_class) in range(3)
        else str(dominant_class)
    )

    return {
        "explainer": {
            "method": method,
            "library": "shap" if method == METHOD_TREE_SHAP else "sklearn",
            "library_version": shap_version,
            "explainer_version": EXPLAINER_VERSION,
            "explained_output": "pre_calibration_model_probability",
            "target_class": predicted_direction,
            "estimator": estimator_name,
            "calibrator": type(calibrator).__name__ if calibrator is not None else None,
            "calibration_note": (
                "Contributions explain the pre-calibration model output. Served probabilities pass through "
                "isotonic calibration; contribution magnitudes are not additive to served probabilities."
            ),
        },
        "feature_vector_hash": feature_vector_hash(names, clean),
        "classes": [str(c) for c in classes],
        "expected_value": {CLASS_NAMES[i]: round(float(expected[i]), 8) for i in range(len(classes))},
        "raw_model_probabilities": {
            CLASS_NAMES[i]: round(float(raw_probs[i]), 8) for i in range(len(classes))
        },
        "served_probabilities": {k: round(float(v), 8) for k, v in served.items()},
        "reconciliation": {
            "method": "sum(contributions) + expected_value",
            "max_abs_error": max_error,
            "tolerance": tolerance,
            "matches_model_output": max_error <= tolerance,
            "recomputed_direction": recomputed_direction,
            "direction_matches_saved": recomputed_direction == predicted_direction,
            "served_vs_raw_max_delta": round(
                max(abs(float(served.get(k, 0.0)) - float(raw_probs[i])) for i, k in enumerate(CLASS_NAMES)),
                8,
            ),
        },
        "contributions": [c.as_dict() for c in contributions],
        "top_positive": [c.as_dict() for c in supporting[:6]],
        "top_negative": [c.as_dict() for c in opposing[:6]],
        "missing_features": [],
        "unreliable_features": unreliable,
        "warnings": [
            "SHAP values are associations, not causal effects.",
            "Correlated features can share attribution; do not over-read individual magnitudes.",
            "Only model-input features are attributed. Fundamental and macro data are absent from v1.0.",
        ],
        "no_clear_edge": bool(no_clear_edge),
        "narrative": _build_narrative(
            predicted_direction,
            contributions,
            served,
            _limiting_factors(contributions, predicted_direction, served, no_clear_edge),
            no_clear_edge,
        ),
    }
