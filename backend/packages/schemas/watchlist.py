from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from packages.schemas.base import BaseSchema
from packages.schemas.market import InstrumentResponse, QuoteResponse
from packages.schemas.prediction import PredictionResponse


class WatchlistBase(BaseSchema):
    """Base watchlist schema."""

    name: str = Field(..., max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_default: bool = False


class WatchlistCreate(WatchlistBase):
    """Watchlist creation schema."""

    pass


class WatchlistUpdate(BaseSchema):
    """Watchlist update schema."""

    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_default: bool | None = None


class WatchlistResponse(WatchlistBase):
    """Watchlist response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    item_count: int = 0
    user_id: UUID

    model_config = ConfigDict(from_attributes=True)


class WatchlistItemBase(BaseSchema):
    """Base watchlist item schema."""

    instrument_id: UUID
    notes: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class WatchlistItemCreate(WatchlistItemBase):
    """Watchlist item creation schema."""

    pass


class WatchlistItemUpdate(BaseSchema):
    """Watchlist item update schema."""

    notes: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class WatchlistItemResponse(WatchlistItemBase):
    """Watchlist item response schema with full instrument and quote data."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    watchlist_id: UUID
    instrument: Any  # InstrumentResponse but relaxed to Any to avoid ORM serialization issues
    quote: Any | None = None
    prediction: Any | None = None

    model_config = ConfigDict(from_attributes=True)


class WatchlistWithItemsResponse(WatchlistResponse):
    """Watchlist with items response schema."""

    items: list[WatchlistItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
