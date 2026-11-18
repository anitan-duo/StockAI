"""Cross-sectional relative ranking endpoints (ACC-001)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from packages.schemas.ranking import RankingPerformanceResponse, RankingSnapshotResponse
from services.ranking.service import RankingError, RankingService

router = APIRouter(prefix="/rankings", tags=["rankings"])

HORIZON_PATTERN = "^(1d|5d|10d)$"


def _http_error(exc: RankingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=RankingSnapshotResponse)
async def get_rankings(
    session: Annotated[AsyncSession, Depends(get_session)],
    market: str | None = Query(default=None, min_length=2, max_length=10),
    horizon: str = Query(default="1d", pattern=HORIZON_PATTERN),
    refresh: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
) -> RankingSnapshotResponse:
    """Latest persisted ranking, or a freshly computed one.

    ``score`` is a relative score (expected performance versus the eligible
    cross-section), not an absolute probability that a stock rises.
    """
    service = RankingService(session)
    try:
        snapshot = None if refresh else await service.latest_snapshot(market, horizon)
        if snapshot is None:
            result = await service.rank(market=market, horizon=horizon)
            snapshot = await service.persist(result)
        payload = await service.snapshot_payload(snapshot)
    except RankingError as exc:
        raise _http_error(exc) from exc
    payload["entries"] = payload["entries"][:limit]
    return RankingSnapshotResponse.model_validate(payload)


@router.post("/refresh", response_model=RankingSnapshotResponse)
async def refresh_rankings(
    session: Annotated[AsyncSession, Depends(get_session)],
    market: str | None = Query(default=None, min_length=2, max_length=10),
    horizon: str = Query(default="1d", pattern=HORIZON_PATTERN),
    limit: int = Query(default=20, ge=1, le=100),
) -> RankingSnapshotResponse:
    """Compute and persist the current ranking for a market/horizon."""
    service = RankingService(session)
    try:
        result = await service.rank(market=market, horizon=horizon)
        snapshot = await service.persist(result)
        payload = await service.snapshot_payload(snapshot)
    except RankingError as exc:
        raise _http_error(exc) from exc
    payload["entries"] = payload["entries"][:limit]
    return RankingSnapshotResponse.model_validate(payload)


@router.get("/performance", response_model=RankingPerformanceResponse)
async def get_ranking_performance(
    session: Annotated[AsyncSession, Depends(get_session)],
    market: str | None = Query(default=None, min_length=2, max_length=10),
    horizon: str = Query(default="1d", pattern=HORIZON_PATTERN),
) -> RankingPerformanceResponse:
    """Resolved live ranking performance; ``reliable`` requires n>=30."""
    service = RankingService(session)
    return RankingPerformanceResponse.model_validate(
        await service.performance(market, horizon)
    )
