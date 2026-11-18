"""Persisted cross-sectional ranking snapshots and resolved outcomes (ACC-001)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin


class RankingSnapshot(Base, UUIDMixin, TimestampMixin):
    """One immutable ranking of a market/horizon as of a trading session."""

    __tablename__ = "ranking_snapshots"

    market: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    objective: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_sha: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(40), nullable=False)

    universe_size: Mapped[int] = mapped_column(Integer, nullable=False)
    market_universe_size: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    entries: Mapped[list["RankingEntry"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", order_by="RankingEntry.rank"
    )

    __table_args__ = (
        UniqueConstraint(
            "market", "horizon", "as_of_date", "model_version",
            name="uq_ranking_snapshot_scope",
        ),
        Index("ix_ranking_snapshots_market_horizon_date", "market", "horizon", "as_of_date"),
    )


class RankingEntry(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ranking_entries"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ranking_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    percentile: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    quintile: Mapped[int] = mapped_column(Integer, nullable=False)
    relative_label: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    snapshot: Mapped["RankingSnapshot"] = relationship(back_populates="entries")
    outcome: Mapped[Optional["RankingOutcome"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("snapshot_id", "instrument_id", name="uq_ranking_entry_scope"),
        Index("ix_ranking_entries_snapshot_rank", "snapshot_id", "rank"),
    )


class RankingOutcome(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ranking_outcomes"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ranking_entries.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    forward_return: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    cross_sectional_median_return: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    relative_return: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    outperformed: Mapped[bool] = mapped_column(nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    entry: Mapped["RankingEntry"] = relationship(back_populates="outcome")
