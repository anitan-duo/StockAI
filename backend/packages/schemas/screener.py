from decimal import Decimal

from pydantic import ConfigDict, Field

from packages.schemas.base import BaseSchema, PaginatedResponse


class ScreenerFilters(BaseSchema):
    """Screener filter parameters."""

    market: list[str] | None = Field(default=None)
    exchange: list[str] | None = Field(default=None)
    sector: list[str] | None = Field(default=None)
    price_min: Decimal | None = Field(default=None, ge=0)
    price_max: Decimal | None = Field(default=None, ge=0)
    performance_min: Decimal | None = Field(default=None)
    performance_max: Decimal | None = Field(default=None)
    rsi_min: Decimal | None = Field(default=None, ge=0, le=100)
    rsi_max: Decimal | None = Field(default=None, ge=0, le=100)
    volatility_min: Decimal | None = Field(default=None, ge=0)
    volatility_max: Decimal | None = Field(default=None, ge=0)
    prediction_probability_min: Decimal | None = Field(default=None, ge=0, le=1)
    expected_return_min: Decimal | None = Field(default=None)
    confidence_min: int | None = Field(default=None, ge=0, le=100)
    prediction_direction: str | None = Field(
        default=None, pattern="^(up|neutral|down)$"
    )
    limit: int = Field(default=50, ge=1, le=500)


class ScreenerResult(BaseSchema):
    """Screener result item schema.

    ``price``/``change_percent`` are None (never 0) when no prediction
    snapshot exists: 0 is a fabricated price, absence is honest.
    """

    symbol: str
    name: str
    exchange: str
    price: Decimal | None = None
    change_percent: Decimal | None = None
    sector: str | None = None
    rsi: Decimal | None = None
    volatility: Decimal | None = None
    prediction: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class ScreenerResponse(PaginatedResponse[ScreenerResult]):
    """Screener response schema."""

    pass
