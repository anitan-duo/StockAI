from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.models.backtest import BacktestStatus
from apps.api.repositories.backtest import BacktestRepository, BacktestTradeRepository
from apps.api.repositories.market import InstrumentRepository
from apps.api.repositories.prediction import ModelVersionRepository
from apps.api.routes.auth import get_current_user

def _get_user_id(user) -> UUID:
    """Handle User ORM, dict, or string identity without recursion."""
    if hasattr(user, "id"):
        uid = user.id  # type: ignore
        return uid if isinstance(uid, UUID) else UUID(str(uid))
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                return UUID(str(user[key]))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    if isinstance(user, str):
        return UUID(user)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
from packages.schemas.backtest import (
    BacktestCreate,
    BacktestResponse,
    BacktestResultResponse,
    BacktestTradeResponse,
)
from services.backtesting.backtest_service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtesting"])


@router.get("", response_model=list[BacktestResponse])
async def list_backtests(
    status_filter: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BacktestResponse]:
    """List user's backtests."""
    repo = BacktestRepository(session)
    backtests = await repo.get_user_backtests(
        _get_user_id(user), status_filter, skip=skip, limit=limit
    )
    return [BacktestResponse.model_validate(b) for b in backtests]


@router.post("", response_model=BacktestResponse, status_code=status.HTTP_201_CREATED)
async def create_backtest(
    data: BacktestCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestResponse:
    """Create a new backtest."""
    # Validate instrument
    instrument_repo = InstrumentRepository(session)
    instrument = await instrument_repo.get(data.instrument_id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    # Validate model version
    model_version_repo = ModelVersionRepository(session)
    model_version = await model_version_repo.get(data.model_version_id)
    if not model_version:
        raise HTTPException(status_code=404, detail="Model version not found")

    # Validate dates
    if data.start_date >= data.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if data.end_date > datetime.now(UTC):
        raise HTTPException(status_code=400, detail="end_date cannot be in the future")

    service = BacktestService(session)
    backtest = await service.create_backtest(
        user_id=_get_user_id(user),
        instrument_id=data.instrument_id,
        model_version_id=data.model_version_id,
        start_date=data.start_date,
        end_date=data.end_date,
        horizon=data.horizon,
        initial_capital=data.initial_capital,
    )
    await session.commit()
    # Avoid serializing ORM relationships
    try:
        session.expunge(backtest)
    except Exception:
        pass
    backtest.instrument = None  # type: ignore
    backtest.model_version = None  # type: ignore
    return BacktestResponse.model_validate(backtest)


@router.get("/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest(
    backtest_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestResultResponse:
    """Get backtest with results."""
    service = BacktestService(session)
    backtest = await service.get_backtest(backtest_id)

    if not backtest or backtest.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Backtest not found")

    # Get trades
    trade_repo = BacktestTradeRepository(session)
    trades = await trade_repo.get_backtest_trades(backtest_id)

    # Avoid ORM serialization issues
    try:
        session.expunge(backtest)
    except Exception:
        pass
    backtest.instrument = None  # type: ignore
    backtest.model_version = None  # type: ignore
    return BacktestResultResponse(
        backtest=BacktestResponse.model_validate(backtest),
        trades=[BacktestTradeResponse.model_validate(t) for t in trades],
    )


@router.post("/{backtest_id}/run", response_model=BacktestResultResponse)
async def run_backtest(
    backtest_id: UUID,
    method: str = Query(default="causal", pattern="^(causal|final)$"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestResultResponse:
    """Run a backtest (causal walk-forward by default; method=final selects the legacy final-model path)."""
    service = BacktestService(session)
    backtest = await service.get_backtest(backtest_id)

    if not backtest or backtest.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Backtest not found")

    if backtest.status == BacktestStatus.RUNNING or backtest.status == "running":
        raise HTTPException(status_code=409, detail="Backtest already running")

    try:
        result = await service.run_backtest(backtest_id, method=method)
        if not result:
            raise HTTPException(status_code=500, detail="Backtest failed")

        # Get trades
        trade_repo = BacktestTradeRepository(session)
        trades = await trade_repo.get_backtest_trades(backtest_id)

        # Avoid ORM serialization
        try:
            session.expunge(result)
        except Exception:
            pass
        result.instrument = None  # type: ignore
        result.model_version = None  # type: ignore
        return BacktestResultResponse(
            backtest=BacktestResponse.model_validate(result),
            trades=[BacktestTradeResponse.model_validate(t) for t in trades],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        import logging

        logging.getLogger("stockai.api").exception("backtest failed")
        raise HTTPException(status_code=500, detail="Backtest failed")


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backtest(
    backtest_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete backtest."""
    repo = BacktestRepository(session)
    backtest = await repo.get(backtest_id)

    if not backtest or backtest.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Backtest not found")

    await repo.delete(backtest_id)
    await session.commit()
