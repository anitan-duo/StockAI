from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import ConfigDict, Field

from packages.schemas.base import BaseSchema


class MarketBase(BaseSchema):
    """Base market schema."""

    code: str = Field(..., max_length=10)
    name: str = Field(..., max_length=100)
    country_code: str = Field(..., max_length=3)
    currency: str = Field(..., max_length=3)
    timezone: str = Field(..., max_length=50)
    is_active: bool = True
    market_open: time
    market_close: time
    pre_market_open: time | None = None
    post_market_close: time | None = None


class MarketResponse(MarketBase):
    """Market response schema."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExchangeBase(BaseSchema):
    """Base exchange schema."""

    code: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    market_id: int
    timezone: str = Field(..., max_length=50)
    currency: str = Field(..., max_length=3)
    is_active: bool = True
    market_open: time
    market_close: time
    pre_market_open: time | None = None
    post_market_close: time | None = None


class ExchangeResponse(ExchangeBase):
    """Exchange response schema."""

    id: int
    created_at: datetime
    updated_at: datetime
    market: MarketResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class InstrumentType(str):
    """Instrument type enumeration."""

    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    OPTION = "option"
    FUTURE = "future"
    CURRENCY = "currency"
    CRYPTO = "crypto"


class InstrumentBase(BaseSchema):
    """Base instrument schema."""

    symbol: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    exchange_id: int
    type: str = Field(default=InstrumentType.EQUITY, max_length=20)
    currency: str = Field(..., max_length=3)
    isin: str | None = Field(default=None, max_length=12)
    cusip: str | None = Field(default=None, max_length=9)
    figi: str | None = Field(default=None, max_length=12)
    sector: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    market_cap: int | None = None
    is_active: bool = True
    is_tradable: bool = True
    metadata_json: dict = Field(default_factory=dict)


class InstrumentResponse(InstrumentBase):
    """Instrument response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    exchange: ExchangeResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class InstrumentSearchResult(BaseSchema):
    """Instrument search result schema."""

    symbol: str
    name: str
    exchange: str
    exchange_code: str
    market: str
    type: str
    currency: str

    model_config = ConfigDict(from_attributes=True)


class QuoteResponse(BaseSchema):
    """Quote response schema with explicit data provenance.

    `freshness` is the backend's authoritative data-status classification
    (fresh/recent/delayed/stale/unavailable). The frontend must display it
    and must not derive its own staleness heuristics.
    """

    symbol: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    volume: int
    high: Decimal
    low: Decimal
    open: Decimal
    previous_close: Decimal
    timestamp: str
    market_status: str
    # --- Provenance / freshness metadata ---
    exchange: str | None = None
    currency: str | None = None
    provider: str | None = None
    freshness: str = "unavailable"  # Freshness enum value
    delayed: bool = False
    source_timestamp: str | None = None  # provider-reported data time
    ingested_at: str | None = None  # when our system persisted/fetched it

    model_config = ConfigDict(from_attributes=True)


class HistoricalPriceResponse(BaseSchema):
    """Historical price bar response schema."""

    timestamp: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)


class MarketSnapshotResponse(BaseSchema):
    """Market snapshot response schema."""

    symbol: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    volume: int
    high: Decimal
    low: Decimal
    open: Decimal
    previous_close: Decimal
    market_status: str
    timestamp: str

    model_config = ConfigDict(from_attributes=True)


class IndexQuote(BaseSchema):
    """A market index quote with freshness provenance."""

    symbol: str
    name: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    market_status: str
    timestamp: str
    provider: str | None = None
    freshness: str = "unavailable"
    currency: str = "USD"


class MarketMover(BaseSchema):
    """A top gainer/loser derived from persisted snapshots."""

    symbol: str
    name: str
    exchange: str
    market: str
    price: Decimal
    change_percent: Decimal
    volume: int
    timestamp: str
    freshness: str = "unavailable"


class MarketOverviewResponse(BaseSchema):
    """Market overview: indices + movers with explicit freshness.

    Every element carries a backend-classified freshness value. Missing
    indices are simply absent (the frontend shows UNAVAILABLE) — no
    synthetic values are ever returned.
    """

    indices: list[IndexQuote] = []
    gainers: list[MarketMover] = []
    losers: list[MarketMover] = []
    as_of: str
    stale: bool = False
