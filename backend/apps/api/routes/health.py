from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from services.ingestion.providers.factory import ProviderFactory

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> dict[str, Any]:
    """Basic health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "version": "0.1.0",
    }


@router.get("/ready")
async def readiness_check(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Verify database readiness and report provider configuration without probing vendors.

    Provider health checks can consume rate-limited API calls, so this endpoint
    deliberately distinguishes configured providers from verified connectivity.
    """
    checks = {}
    overall_healthy = True

    # Database check
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy", "latency_ms": 0}
    except Exception:
        import logging

        logging.getLogger("stockai.api").exception("health database check failed")
        checks["database"] = {"status": "unhealthy", "error": "database unavailable"}
        overall_healthy = False

    # Provider check - use fallback router health
    try:
        router = ProviderFactory.get_router()
        # Check if any provider is configured
        total_providers = sum(len(v) for v in router.providers.values())
        if total_providers > 0:
            checks["provider"] = {
                "status": "configured",
                "connectivity_verified": False,
                "providers": total_providers,
                "markets": list(router.providers.keys()),
            }
        else:
            checks["provider"] = {
                "status": "not_configured",
                "connectivity_verified": False,
                "provider": "none",
            }
    except Exception:
        import logging

        logging.getLogger("stockai.api").exception("health provider check failed")
        checks["provider"] = {"status": "unhealthy", "error": "provider unavailable"}
        overall_healthy = False

    return JSONResponse(
        status_code=200 if overall_healthy else 503,
        content={
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": checks,
        },
    )


@router.get("/live")
async def liveness_check() -> dict[str, Any]:
    """Liveness check - simple endpoint for Kubernetes probes."""
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/freshness")
async def freshness_check(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Data freshness: latest market snapshot/bar/prediction timestamps.

    `stale: true` when any source is older than 48h or entirely absent.
    Never fabricates: absent sources are reported as null.
    """
    from datetime import timedelta

    from sqlalchemy import func, select

    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import Prediction
    from apps.api.models.price import MarketSnapshot, PriceBar

    now = datetime.now(UTC)
    stale_after = now - timedelta(hours=48)

    async def _max(model, column, label: str) -> dict[str, Any]:
        try:
            ts = (await session.execute(select(func.max(column)))).scalar_one_or_none()
            n24 = None
            if ts is not None:
                n24 = (await session.execute(
                    select(func.count()).select_from(model).where(column >= now - timedelta(hours=24))
                )).scalar_one()
            return {
                "latest": ts.isoformat() if ts else None,
                "count_24h": n24,
                "stale": True if ts is None or ts < stale_after else False,
            }
        except Exception:
            import logging

            logging.getLogger("stockai.api").exception("freshness %s check failed", label)
            return {"latest": None, "count_24h": None, "stale": True, "error": "query failed"}

    snapshots = await _max(MarketSnapshot, MarketSnapshot.timestamp, "snapshots")
    bars = await _max(PriceBar, PriceBar.timestamp, "bars")
    predictions = await _max(Prediction, Prediction.prediction_timestamp, "predictions")
    instruments = (await session.execute(select(func.count()).select_from(Instrument))).scalar_one()

    # Per-market freshness: a global max hides stalls in individual markets
    # (EU/IN once stalled 10 days while US bars kept the global max fresh).
    # 96h tolerates weekends; a market with no bar newer than 4 days is stale.
    stale_after_market = now - timedelta(hours=96)
    market_rows = (
        await session.execute(
            select(Market.code, func.max(PriceBar.timestamp))
            .join(Exchange, Exchange.market_id == Market.id)
            .join(Instrument, Instrument.exchange_id == Exchange.id)
            .join(PriceBar, PriceBar.instrument_id == Instrument.id)
            .where(PriceBar.timeframe == "1d")
            .group_by(Market.code)
        )
    ).all()
    from services.prediction.bar_identity import _as_aware_utc

    market_freshness: dict[str, dict[str, Any]] = {
        code: {
            "latest": ts.isoformat() if ts else None,
            # SQLite returns naive UTC datetimes; normalize before compare.
            "stale": ts is None or _as_aware_utc(ts) < stale_after_market,
        }
        for code, ts in market_rows
    }

    scheduler_state: dict[str, Any] = {"last_ingestion": None, "source": "unknown"}
    try:
        from services.cache import get_valkey

        client = await get_valkey()
        if client is not None:
            last_ing = await client.get("scheduler:last_ingestion")
            scheduler_state = {"last_ingestion": last_ing, "source": "valkey"}
    except Exception:
        pass

    any_market_stale = any(v["stale"] for v in market_freshness.values())
    stale = bool(snapshots.get("stale") and bars.get("stale")) or any_market_stale
    return {
        "timestamp": now.isoformat(),
        "stale": stale,
        "markets": market_freshness,
        "instruments": instruments,
        "snapshots": snapshots,
        "price_bars": bars,
        "predictions": predictions,
        "scheduler": scheduler_state,
    }
