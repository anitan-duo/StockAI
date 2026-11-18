import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin
from apps.api.models.market import Instrument


class PredictionDirection(str, enum.Enum):
    """Prediction direction enumeration."""

    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"


class PredictionHorizon(str, enum.Enum):
    """Prediction horizon enumeration."""

    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1m"


class Model(Base, UUIDMixin, TimestampMixin):
    """ML Model model."""

    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    versions: Mapped[list["ModelVersion"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Model(name={self.name})>"


class ModelVersion(Base, UUIDMixin, TimestampMixin):
    """Model version model."""

    __tablename__ = "model_versions"

    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    training_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    model: Mapped["Model"] = relationship(back_populates="versions")
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="model_version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_model_version"),
        Index("ix_model_versions_model_active", "model_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ModelVersion(model={self.model_id}, version={self.version})>"


class Prediction(Base, UUIDMixin, TimestampMixin):
    """Prediction model."""

    __tablename__ = "predictions"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Prediction details
    horizon: Mapped[PredictionHorizon] = mapped_column(
        String(10), nullable=False
    )
    predicted_direction: Mapped[PredictionDirection] = mapped_column(
        String(10), nullable=False
    )

    # Probabilities (must sum to 1)
    up_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    neutral_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    down_probability: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    # Expected return and range
    expected_return: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    range_lower: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    range_upper: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)

    # Confidence score (0-100)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timestamps
    prediction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    data_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Input features snapshot
    features_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    instrument: Mapped["Instrument"] = relationship(back_populates="predictions")
    model_version: Mapped["ModelVersion"] = relationship(back_populates="predictions")
    outcome: Mapped[Optional["PredictionOutcome"]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        Index(
            "ix_predictions_instrument_horizon_ts",
            "instrument_id",
            "horizon",
            "prediction_timestamp",
        ),
        Index("ix_predictions_model_ts", "model_version_id", "prediction_timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Prediction(instrument={self.instrument_id}, dir={self.predicted_direction}, conf={self.confidence})>"


class PredictionOutcome(Base, UUIDMixin, TimestampMixin):
    """Prediction outcome for evaluation."""

    __tablename__ = "prediction_outcomes"

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Actual outcome
    actual_return: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    actual_direction: Mapped[PredictionDirection] = mapped_column(
        String(10), nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(nullable=False)

    # Evaluation timestamp
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Price data used for evaluation
    evaluation_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    evaluation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Resolution provenance (provider that supplied the evaluation bar) and
    # auditor notes (corrections reference audit_logs; rows stay immutable).
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    prediction: Mapped["Prediction"] = relationship(back_populates="outcome")

    def __repr__(self) -> str:
        return f"<PredictionOutcome(prediction={self.prediction_id}, correct={self.is_correct})>"


class PredictionExplanation(Base, UUIDMixin, TimestampMixin):
    """Immutable per-prediction explanation artifact.

    One row per prediction (unique prediction_id). Explanations are generated
    from the saved feature snapshot and the hash-verified champion artifact.
    Rows are never rewritten; regenerating returns the stored artifact.
    """

    __tablename__ = "prediction_explanations"

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    explainer_version: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    artifact_sha: Mapped[str | None] = mapped_column(String(120), nullable=True)
    feature_vector_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    predicted_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<PredictionExplanation(prediction={self.prediction_id}, method={self.method})>"
