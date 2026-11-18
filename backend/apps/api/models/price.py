import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin


class PriceBar(Base, UUIDMixin, TimestampMixin):
    """OHLCV price bar for an instrument."""

    __tablename__ = "price_bars"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # Canonical exchange session day for daily bars (BAR-002). NULL on intraday
    # bars and on explicitly quarantined legacy conflicts.
    session_day: Mapped[date | None] = mapped_column(Date, nullable=True)

    # OHLCV prices using Decimal for precision
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    trades_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Source tracking
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    instrument: Mapped["Instrument"] = relationship(back_populates="price_bars")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "timestamp", "timeframe", name="uq_price_bar_unique"
        ),
        Index("ix_price_bars_instrument_timeframe_ts", "instrument_id", "timeframe", "timestamp"),
        Index("ix_price_bars_timestamp_desc", desc("timestamp")),
        Index("ix_price_bars_session_day", "instrument_id", "timeframe", "session_day"),
        Index(
            "uq_price_bar_instrument_timeframe_session_day",
            "instrument_id",
            "timeframe",
            "session_day",
            unique=True,
            postgresql_where=text("session_day IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<PriceBar(instrument_id={self.instrument_id}, ts={self.timestamp}, tf={self.timeframe})>"


class MarketSnapshot(Base, UUIDMixin, TimestampMixin):
    """Real-time market snapshot for an instrument."""

    __tablename__ = "market_snapshots"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Current price data
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    change: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    change_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    previous_close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Market status
    market_status: Mapped[str] = mapped_column(String(20), nullable=False)
    # 'open', 'closed', 'pre-market', 'after-hours', 'halted'

    # Source tracking
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    instrument: Mapped["Instrument"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "timestamp", name="uq_market_snapshot_unique"
        ),
        Index("ix_market_snapshots_instrument_ts", "instrument_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<MarketSnapshot(instrument_id={self.instrument_id}, price={self.price})>"
