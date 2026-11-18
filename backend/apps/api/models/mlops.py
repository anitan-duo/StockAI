"""MLOps models: experiment registry, training jobs, champion pointer.

All promotion-relevant state lives here (Postgres), not in memory:
completed experiments survive restarts, champion switches are auditable,
and outcome resolution is idempotent. Filesystem artifacts are referenced
by path + SHA, never duplicated into the database.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Float, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin


class Experiment(Base, UUIDMixin, TimestampMixin):
    """Durable experiment registry (hypothesis -> decision)."""

    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    # research|training|evaluating|candidate|shadow|approved|rejected|failed|retired
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="research")
    dataset_fingerprint: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    feature_set: Mapped[str] = mapped_column(String(50), default="full", nullable=False)
    target: Mapped[str] = mapped_column(String(50), default="v1-h1d-0.5pct", nullable=False)
    horizon: Mapped[str] = mapped_column(String(10), default="1d", nullable=False)
    model_family: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    hyperparameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    splits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    backtest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifact_sha: Mapped[str | None] = mapped_column(String(120), nullable=True)
    code_revision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    compute_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    jobs: Mapped[list["TrainingJob"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Experiment({self.experiment_id}, {self.status})>"


class TrainingJob(Base, UUIDMixin, TimestampMixin):
    """Bounded, idempotent training job (one job_key runs once)."""

    __tablename__ = "training_jobs"

    job_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # queued|running|succeeded|failed|cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    timeout_s: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    compute_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    experiment: Mapped[Experiment | None] = relationship(back_populates="jobs")

    def __repr__(self) -> str:
        return f"<TrainingJob({self.job_key}, {self.status})>"


class ModelChampion(Base, UUIDMixin, TimestampMixin):
    """Explicit champion pointer. The current champion is the single row
    with superseded_at NULL (partial unique index enforces this)."""

    __tablename__ = "model_champions"

    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_sha: Mapped[str] = mapped_column(String(120), nullable=False)
    # active|superseded
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_champion_current",
            "superseded_at",
            unique=True,
            postgresql_where=(superseded_at.is_(None)),
        ),
    )

    def __repr__(self) -> str:
        return f"<ModelChampion({self.model_version_id}, {self.status})>"


class ModelPromotion(Base, UUIDMixin, TimestampMixin):
    """Auditable champion switch (rollback = a reversing promotion row)."""

    __tablename__ = "model_promotions"

    from_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    to_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True
    )
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_delta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<ModelPromotion(->{self.to_version_id})>"


class DriftObservation(Base, UUIDMixin, TimestampMixin):
    """Monitoring signal (drift alarm vs confirmed deterioration decided
    by readers: provisional until matured-outcome metrics confirm)."""

    __tablename__ = "drift_observations"

    scope: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_drift_scope_observed", "scope", "observed_at"),
    )

    def __repr__(self) -> str:
        return f"<DriftObservation({self.scope}/{self.metric}={self.value})>"
