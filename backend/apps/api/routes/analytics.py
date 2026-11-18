"""Read-only analytics workspace: confirmed prediction performance."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.routes.auth import get_current_user
from services.mlops.analytics import compute_performance_analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/performance")
async def get_performance(
    days: int = Query(default=90, ge=1, le=365),
    symbol: str | None = Query(default=None, max_length=50),
    exchange: str | None = Query(default=None, max_length=20),
    recent_limit: int = Query(default=25, ge=1, le=100),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Confirmed performance from matured outcomes, with explicit sample limits."""
    return await compute_performance_analytics(
        session,
        days=days,
        symbol=symbol,
        exchange=exchange,
        recent_limit=recent_limit,
    )
