import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin
from apps.api.models.market import Instrument
from apps.api.models.prediction import ModelVersion
from apps.api.models.user import User


class BacktestStatus(str, enum.Enum):
    """Backtest status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Backtest(Base, UUIDMixin, TimestampMixin):
    """Backtest model."""

    __tablename__ = "backtests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Configuration
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon: Mapped[str] = mapped_column(String(10), nullable=False)  # PredictionHorizon
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Status - stored as String to match Alembic varchar(9) migration
    status: Mapped[str] = mapped_column(
        String(20), default=BacktestStatus.PENDING.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Results
    total_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    annualized_return: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    # Result data (stored as JSON for flexibility)
    equity_curve: Mapped[list[Any] | None] = mapped_column(JSON, default=list, nullable=True)
    drawdown_curve: Mapped[list[Any] | None] = mapped_column(JSON, default=list, nullable=True)
    returns_distribution: Mapped[list[Any] | None] = mapped_column(JSON, default=list, nullable=True)
    trades: Mapped[list[Any] | None] = mapped_column(JSON, default=list, nullable=True)

    # Completed timestamp
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship()
    instrument: Mapped["Instrument"] = relationship()
    model_version: Mapped["ModelVersion"] = relationship()

    __table_args__ = (
        Index("ix_backtests_user_status", "user_id", "status"),
        Index("ix_backtests_instrument_dates", "instrument_id", "start_date", "end_date"),
    )

    def __repr__(self) -> str:
        return f"<Backtest(id={self.id}, status={self.status})>"


class BacktestTrade(Base, UUIDMixin, TimestampMixin):
    """Individual trade within a backtest."""

    __tablename__ = "backtest_trades"

    backtest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Trade details
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # 'long' or 'short'

    # Results
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    is_winner: Mapped[bool | None] = mapped_column(nullable=True)

    # Prediction reference
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    backtest: Mapped["Backtest"] = relationship()

    __table_args__ = (
        Index("ix_backtest_trades_backtest_entry", "backtest_id", "entry_date"),
    )

    def __repr__(self) -> str:
        return f"<BacktestTrade(backtest={self.backtest_id}, entry={self.entry_date}, pnl={self.pnl})>"
