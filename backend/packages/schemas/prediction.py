from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from packages.schemas.base import BaseSchema


class PredictionDirection(str):
    """Prediction direction enumeration."""

    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"


class PredictionHorizon(str):
    """Prediction horizon enumeration."""

    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1m"


class PredictionBase(BaseSchema):
    """Base prediction schema."""

    instrument_id: UUID
    model_version_id: UUID
    horizon: str = Field(..., pattern="^(1d|1w|1m)$")
    predicted_direction: str = Field(..., pattern="^(up|neutral|down)$")
    up_probability: Decimal = Field(..., ge=0, le=1)
    neutral_probability: Decimal = Field(..., ge=0, le=1)
    down_probability: Decimal = Field(..., ge=0, le=1)
    expected_return: Decimal
    range_lower: Decimal
    range_upper: Decimal
    confidence: int = Field(..., ge=0, le=100)
    prediction_timestamp: datetime
    data_timestamp: datetime
    features_snapshot: dict = Field(default_factory=dict)


class PredictionResponse(PredictionBase):
    """Prediction response schema.

    ``horizon`` echoes the requested horizon; ``model_horizon`` is the native
    forecast horizon of the artifact that produced the probabilities
    (v1.0 is a 1-day model — see services.ml.recipe.TARGET_VERSION).
    Clients must present the model horizon, never imply a 1w/1m forecast.
    """

    id: UUID
    created_at: datetime
    updated_at: datetime
    instrument: Any | None = None
    model_version: Any | None = None
    outcome: Optional["PredictionOutcomeResponse"] = None
    no_clear_edge: bool = False
    model_horizon: str = "1d"
    # Confidence transparency: separate the raw model probability from the
    # heuristic 0-100 "confidence" score so clients do not present a
    # separation heuristic as a calibrated probability of correctness.
    top_probability: float | None = None
    probability_margin: float | None = None
    confidence_basis: str = "heuristic_probability_separation"
    confidence_note: str = (
        "Confidence is a signal-separation heuristic, not a calibrated "
        "probability that the prediction is correct."
    )

    model_config = ConfigDict(from_attributes=True)


class PredictionOutcomeResponse(BaseSchema):
    """Prediction outcome response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    prediction_id: UUID
    actual_return: Decimal
    actual_direction: str
    is_correct: bool
    evaluated_at: datetime
    evaluation_price: Decimal
    evaluation_timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class PredictionHistoryItem(BaseSchema):
    """Prediction history item schema (model version included so mixed
    lineages across champion changes stay attributable)."""

    date: str
    prediction: str
    up_probability: Decimal
    expected_return: Decimal
    actual_return: Decimal | None = None
    actual_direction: str | None = None
    result: str | None = None
    counted_in_accuracy: bool = False
    model_version: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PredictionPerformanceSummary(BaseSchema):
    """Canonical evaluation summary for the returned window.

    ``accuracy`` is the *directional* hit rate (UP/DOWN calls only) as a
    percentage, or ``null`` when there are fewer than ``minimum_sample``
    qualifying predictions. Neutral predictions are reported separately and
    are never included in ``accuracy``.
    """

    total_predictions: int = Field(..., ge=0)  # rows in window (all states)
    completed_count: int = Field(default=0, ge=0)  # with an outcome
    pending_count: int = Field(default=0, ge=0)  # without an outcome
    invalid_count: int = Field(default=0, ge=0)
    expired_count: int = Field(default=0, ge=0)
    correct_predictions: int = Field(..., ge=0)  # directional correct
    incorrect_predictions: int = Field(default=0, ge=0)
    neutral_predictions: int = Field(default=0, ge=0)
    neutral_correct: int = Field(default=0, ge=0)
    directional_count: int = Field(default=0, ge=0)
    accuracy: Decimal | None = None
    accuracy_reliable: bool = False
    minimum_sample: int = 30
    confidence_interval_lower: Decimal | None = None
    confidence_interval_upper: Decimal | None = None
    coverage: Decimal | None = None
    scoring_policy: str | None = None
    average_return: Decimal


class PredictionHistoryResponse(BaseSchema):
    """Prediction history response schema."""

    symbol: str
    items: list[PredictionHistoryItem]
    summary: PredictionPerformanceSummary

    model_config = ConfigDict(from_attributes=True)


class FactorAnalysisResponse(BaseSchema):
    """Factor analysis response schema."""

    positive: list[str]
    neutral: list[str]
    negative: list[str]

    model_config = ConfigDict(from_attributes=True)


class TopPredictionResponse(BaseSchema):
    """Top prediction response for listings (native model horizon: 1d)."""

    symbol: str
    name: str
    exchange: str
    price: Decimal
    change_percent: Decimal
    direction: str
    probabilities: dict
    expected_return: Decimal
    confidence: int
    horizon: str
    no_clear_edge: bool = False
    model_horizon: str = "1d"
    # Confidence transparency: separate the raw model probability from the
    # heuristic 0-100 "confidence" score so clients do not present a
    # separation heuristic as a calibrated probability of correctness.
    top_probability: float | None = None
    probability_margin: float | None = None
    confidence_basis: str = "heuristic_probability_separation"
    confidence_note: str = (
        "Confidence is a signal-separation heuristic, not a calibrated "
        "probability that the prediction is correct."
    )
    prediction_timestamp: datetime | None = None
    model_version: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PredictionExplanationResponse(BaseSchema):
    """Explainable-AI payload for one saved prediction.

    ``prediction_id`` and ``feature_vector_hash`` bind the explanation to the
    exact prediction and feature vector. Clients must refuse to render an
    explanation whose prediction_id differs from the displayed prediction.
    """

    prediction_id: UUID
    symbol: str | None = None
    exchange: str | None = None
    horizon: str
    model_horizon: str
    model_version: str
    artifact_sha: str
    feature_vector_hash: str
    predicted_direction: str
    prediction_timestamp: datetime
    data_timestamp: datetime
    generated_at: datetime
    explainer_version: str
    explainer: dict
    classes: list[str]
    expected_value: dict[str, float]
    raw_model_probabilities: dict[str, float]
    served_probabilities: dict[str, float]
    reconciliation: dict
    contributions: list[dict]
    top_positive: list[dict]
    top_negative: list[dict]
    missing_features: list[str] = Field(default_factory=list)
    unreliable_features: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    no_clear_edge: bool = False
    narrative: dict

    model_config = ConfigDict(from_attributes=True)


class RsiAnalysisResponse(BaseSchema):
    """Point-in-time RSI intelligence for one instrument."""

    symbol: str
    exchange: str
    method: str
    periods: list[int]
    thresholds: dict
    current: dict
    slopes_5d: dict
    roc_5d: dict
    relative_to_mean: dict
    zone: str
    trend: str
    persistence: dict
    regime: dict
    crossovers: list[dict]
    divergence: dict
    agreement: dict
    interpretation: str
    series: list[dict]
    bar_count: int
    data_timestamp: str
    prediction_direction: str | None = None
    prediction_timestamp: datetime | None = None
    caveats: list[str] = Field(default_factory=list)
