"""Historical scenario lab: blind predict-then-reveal training challenges.

A scenario is a reproducible decision point: symbol + decision timestamp +
horizon, with inputs restricted to bars at or before the decision timestamp.
Predictions commit BEFORE the outcome is revealed; reuse never counts as
fresh evidence; final-evaluation scenarios are quarantined from training.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin


class Scenario(Base, UUIDMixin, TimestampMixin):
    """A historical decision point (blind until revealed)."""

    __tablename__ = "scenarios"

    scenario_key: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    horizon: Mapped[str] = mapped_column(String(10), nullable=False, default="1d")
    target_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1-h1d-0.5pct")
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
    # train|validation|final — final scenarios may never influence training.
    split: Mapped[str] = mapped_column(String(20), nullable=False, default="train", index=True)
    seen_by_model: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_for_training: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # pending|matured|unavailable (+ reason when unavailable)
    outcome_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)

    attempts: Mapped[list["ChallengeAttempt"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Scenario({self.scenario_key} {self.split}/{self.outcome_status})>"


class ChallengeAttempt(Base, UUIDMixin, TimestampMixin):
    """One committed blind prediction on a scenario (immutable once revealed)."""

    __tablename__ = "challenge_attempts"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    experiment_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False, default="ensemble-v1.0")
    artifact_sha: Mapped[str | None] = mapped_column(String(120), nullable=True)
    horizon: Mapped[str] = mapped_column(String(10), nullable=False, default="1d")
    # Committed forecast (frozen before reveal).
    pred_up: Mapped[float] = mapped_column(Float, nullable=False)
    pred_neutral: Mapped[float] = mapped_column(Float, nullable=False)
    pred_down: Mapped[float] = mapped_column(Float, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False, default="HOLD")
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Reveal (filled once, never rewritten).
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_repeat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    scenario: Mapped[Scenario] = relationship(back_populates="attempts")
    diagnosis: Mapped["ErrorDiagnosis | None"] = relationship(
        back_populates="attempt", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Attempt({self.experiment_id} {self.action} correct={self.correct})>"


class Streak(Base, UUIDMixin, TimestampMixin):
    """10/10 training-challenge streak per (experiment, horizon)."""

    __tablename__ = "streaks"

    streak_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    experiment_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(10), nullable=False, default="1d")
    correctness_rule: Mapped[str] = mapped_column(
        String(200), nullable=False, default="action-vs-cost-band"
    )
    current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_scenarios: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_10_of_10: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<Streak({self.streak_key} current={self.current})>"


class ErrorDiagnosis(Base, UUIDMixin, TimestampMixin):
    """Structured diagnosis of a matured incorrect decision."""

    __tablename__ = "error_diagnoses"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("challenge_attempts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # e.g. stale-data | volatility-regime | miscalibration | threshold |
    #       label-noise | gap-corporate-action | illiquidity | overfitting |
    #       data-sparse | unpredictable-event | cost-erosion | unclassified
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    alternatives: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    intervention: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_metric: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    attempt: Mapped[ChallengeAttempt] = relationship(back_populates="diagnosis")

    def __repr__(self) -> str:
        return f"<Diagnosis({self.category} {self.confidence})>"
