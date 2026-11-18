import enum
from datetime import time
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, IDMixin, TimestampMixin, UUIDMixin


class Market(Base, IDMixin, TimestampMixin):
    """Market model (e.g., US, India, Europe)."""

    __tablename__ = "markets"

    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Trading hours (in market local time)
    market_open: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    market_close: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    pre_market_open: Mapped[time | None] = mapped_column(
        Time(timezone=False), nullable=True
    )
    post_market_close: Mapped[time | None] = mapped_column(
        Time(timezone=False), nullable=True
    )

    # Relationships
    exchanges: Mapped[list["Exchange"]] = relationship(
        back_populates="market", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Market(code={self.code}, name={self.name})>"


class Exchange(Base, IDMixin, TimestampMixin):
    """Exchange model (e.g., NASDAQ, NSE, NYSE)."""

    __tablename__ = "exchanges"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Trading hours (in exchange local time, may differ from market)
    market_open: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    market_close: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    pre_market_open: Mapped[time | None] = mapped_column(
        Time(timezone=False), nullable=True
    )
    post_market_close: Mapped[time | None] = mapped_column(
        Time(timezone=False), nullable=True
    )

    # Relationships
    market: Mapped["Market"] = relationship(back_populates="exchanges")
    instruments: Mapped[list["Instrument"]] = relationship(
        back_populates="exchange", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("code", "market_id", name="uq_exchange_code_market"),
    )

    def __repr__(self) -> str:
        return f"<Exchange(code={self.code}, name={self.name})>"


class InstrumentType(str, enum.Enum):
    """Instrument type enumeration."""

    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    OPTION = "option"
    FUTURE = "future"
    CURRENCY = "currency"
    CRYPTO = "crypto"


class Instrument(Base, UUIDMixin, TimestampMixin):
    """Financial instrument model (stocks, ETFs, indices, etc.)."""

    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange_id: Mapped[int] = mapped_column(
        ForeignKey("exchanges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[InstrumentType] = mapped_column(
        String(20), default=InstrumentType.EQUITY, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    cusip: Mapped[str | None] = mapped_column(String(9), unique=True, nullable=True)
    figi: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)

    # Sector/Industry classification
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Market cap (in base currency)
    market_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_tradable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Metadata
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    exchange: Mapped["Exchange"] = relationship(back_populates="instruments")
    price_bars: Mapped[list["PriceBar"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )
    watchlist_items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("symbol", "exchange_id", name="uq_instrument_symbol_exchange"),
        Index("ix_instruments_symbol_active", "symbol", "is_active"),
        Index("ix_instruments_sector", "sector"),
    )

    def __repr__(self) -> str:
        return f"<Instrument(symbol={self.symbol}, name={self.name})>"
