from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from packages.schemas.base import BaseSchema


class BacktestStatus(str):
    """Backtest status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestConfig(BaseSchema):
    """Backtest configuration schema."""

    instrument_id: UUID
    model_version_id: UUID
    start_date: datetime
    end_date: datetime
    horizon: str = Field(..., pattern="^(1d|1w|1m)$")
    initial_capital: Decimal = Field(..., gt=0)


class BacktestCreate(BacktestConfig):
    """Backtest creation schema."""

    pass


class BacktestResponse(BacktestConfig):
    """Backtest response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    user_id: UUID
    status: str
    error_message: str | None = None
    total_return: Decimal | None = None
    annualized_return: Decimal | None = None
    sharpe_ratio: Decimal | None = None
    max_drawdown: Decimal | None = None
    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None
    equity_curve: list | None = None
    drawdown_curve: list | None = None
    returns_distribution: list | None = None
    trades: list | None = None
    completed_at: datetime | None = None
    instrument: Any | None = None
    model_version: Any | None = None

    model_config = ConfigDict(from_attributes=True)


class BacktestTradeResponse(BaseSchema):
    """Backtest trade response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    backtest_id: UUID
    entry_date: datetime
    exit_date: datetime | None = None
    entry_price: Decimal
    exit_price: Decimal | None = None
    shares: int
    side: str
    pnl: Decimal | None = None
    return_pct: Decimal | None = None
    is_winner: bool | None = None
    prediction_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class BacktestResultResponse(BaseSchema):
    """Backtest result summary schema."""

    backtest: BacktestResponse
    trades: list[BacktestTradeResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
