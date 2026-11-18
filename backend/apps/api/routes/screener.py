from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.database import get_session
from apps.api.models.market import Exchange, Instrument, Market
from apps.api.models.prediction import Prediction
from packages.schemas.base import PaginationParams
from packages.schemas.screener import ScreenerFilters, ScreenerResponse, ScreenerResult

router = APIRouter(prefix="/screener", tags=["screener"])


@router.post("", response_model=ScreenerResponse)
async def screen_stocks(
    filters: ScreenerFilters,
    pagination: Annotated[PaginationParams, Depends()],
    session: AsyncSession = Depends(get_session),
) -> ScreenerResponse:
    """Screen stocks based on filters."""
    query = (
        select(Instrument)
        .options(
            selectinload(Instrument.exchange).selectinload(Exchange.market),
        )
        .where(Instrument.is_active.is_(True))
    )

    # Market filter
    if filters.market:
        query = query.join(Exchange).join(Market).where(
            Market.code.in_([m.upper() for m in filters.market])
        )

    # Exchange filter
    if filters.exchange:
        query = query.join(Exchange).where(
            Exchange.code.in_([e.upper() for e in filters.exchange])
        )

    # Sector filter
    if filters.sector:
        query = query.where(Instrument.sector.in_(filters.sector))

    # NOTE: Instrument has no price column (only market_cap). Price filters are
    # applied post-hoc on the prediction features_snapshot price below.

    # Get base instruments
    base_query = query.offset(pagination.offset).limit(pagination.limit)
    result = await session.execute(base_query)
    instruments = list(result.scalars().all())

    # Get predictions for these instruments (champion versions only: shadow
    # and retired-challenger rows must never surface as production results).
    # Portable latest-per-instrument: DISTINCT ON is Postgres-only, so order
    # + dedupe in Python instead.
    instrument_ids = [i.id for i in instruments]
    predictions = []
    if instrument_ids:
        from apps.api.models.mlops import ModelChampion

        champ_id = (
            await session.execute(
                select(ModelChampion.model_version_id).where(
                    ModelChampion.superseded_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        pred_query = (
            select(Prediction)
            .where(
                Prediction.instrument_id.in_(instrument_ids),
                Prediction.horizon == "1d",
                Prediction.prediction_timestamp >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
            )
            .order_by(Prediction.instrument_id, Prediction.prediction_timestamp.desc())
        )
        if champ_id is not None:
            pred_query = pred_query.where(Prediction.model_version_id == champ_id)
        pred_result = await session.execute(pred_query)
        seen: set = set()
        for p in pred_result.scalars().all():
            if p.instrument_id not in seen:
                seen.add(p.instrument_id)
                predictions.append(p)

    pred_map = {p.instrument_id: p for p in predictions}

    # Apply prediction-based filters
    filtered_instruments = []
    for inst in instruments:
        pred = pred_map.get(inst.id)

        # Price filters on latest snapshot price (Instrument has no price column).
        # Missing price + active price filter => exclude (fail closed: a 0
        # default would wrongly pass price_max or fail price_min).
        if (filters.price_min is not None or filters.price_max is not None) and pred:
            try:
                raw_price = (pred.features_snapshot or {}).get("price")
                snap_price = Decimal(str(raw_price)) if raw_price is not None else None
            except Exception:
                snap_price = None
            if snap_price is None:
                continue
            if filters.price_min is not None and snap_price < filters.price_min:
                continue
            if filters.price_max is not None and snap_price > filters.price_max:
                continue

        # Prediction probability filter
        if filters.prediction_probability_min is not None and pred:
            if pred.up_probability < Decimal(str(filters.prediction_probability_min)):
                continue

        # Expected return filter
        if filters.expected_return_min is not None and pred:
            if pred.expected_return < Decimal(str(filters.expected_return_min)):
                continue

        # Confidence filter
        if filters.confidence_min is not None and pred:
            if pred.confidence < filters.confidence_min:
                continue

        # Direction filter
        if filters.prediction_direction and pred:
            dir_val = pred.predicted_direction.value if hasattr(pred.predicted_direction, 'value') else str(pred.predicted_direction)
            if dir_val != filters.prediction_direction:
                continue

        # RSI filter (would need indicator data)
        # For now, skip RSI/volatility filters as they require indicator computation

        filtered_instruments.append(inst)

    # Build results
    results = []
    for inst in filtered_instruments:
        pred = pred_map.get(inst.id)
        pred_dict = None
        if pred:
            dir_val = pred.predicted_direction.value if hasattr(pred.predicted_direction, 'value') else str(pred.predicted_direction)
            pred_dict = {
                "direction": dir_val,
                "up_probability": float(pred.up_probability),
                "neutral_probability": float(pred.neutral_probability),
                "down_probability": float(pred.down_probability),
                "expected_return": float(pred.expected_return),
                "confidence": pred.confidence,
                "horizon": pred.horizon,
            }
        results.append(ScreenerResult(
            symbol=inst.symbol,
            name=inst.name,
            exchange=inst.exchange.code if inst.exchange else "",
            price=Decimal(str(pred.features_snapshot.get("price"))) if pred and pred.features_snapshot and pred.features_snapshot.get("price") is not None else None,
            change_percent=Decimal(str(pred.features_snapshot.get("change_percent"))) if pred and pred.features_snapshot and pred.features_snapshot.get("change_percent") is not None else None,
            sector=inst.sector,
            rsi=Decimal(str(pred.features_snapshot.get("rsi_14"))) if pred and pred.features_snapshot and pred.features_snapshot.get("rsi_14") is not None else None,
            volatility=Decimal(str(pred.features_snapshot.get("realized_vol_20d"))) if pred and pred.features_snapshot and pred.features_snapshot.get("realized_vol_20d") is not None else None,
            prediction=pred_dict,
        ))

    return ScreenerResponse.create(results, len(results), pagination)


@router.get("/filters/sectors")
async def get_available_sectors(
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """Get list of available sectors."""
    query = select(distinct(Instrument.sector)).where(
        Instrument.sector.is_not(None),
        Instrument.is_active.is_(True),
    )
    result = await session.execute(query)
    return [s for s in result.scalars().all() if s]


@router.get("/filters/exchanges")
async def get_available_exchanges(
    market: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Get list of available exchanges."""
    from apps.api.repositories.market import ExchangeRepository, MarketRepository

    market_id = None
    if market:
        market_repo = MarketRepository(session)
        m = await market_repo.get_by_code(market)
        if m:
            market_id = m.id

    exchange_repo = ExchangeRepository(session)
    exchanges = await exchange_repo.get_by_market(market_id) if market_id else []

    return [
        {"code": e.code, "name": e.name, "market": e.market.code if e.market else ""}
        for e in exchanges
    ]
