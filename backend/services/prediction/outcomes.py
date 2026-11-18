"""Matured-outcome resolution: learn only from observable reality.

For each prediction WITHOUT an outcome whose 1-day target has matured
(a later trading bar exists), compute the label with the ORIGINAL v1 target
(±0.5% thresholds) from real persisted bars and record an immutable
PredictionOutcome with provenance. Idempotent: re-runs skip resolved rows
(unique prediction_id) and leave immature rows pending — never inventing
labels for unresolved predictions.

PIT-002 Fix: Use exchange-calendar-aware date comparison instead of
UTC .date() to correctly handle timezone boundaries, weekends, and
holidays.
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.prediction import Prediction, PredictionOutcome
from apps.api.models.price import PriceBar
from apps.api.models.market import Instrument, Exchange, Market
from services.ml import recipe


def _exchange_trading_day(prediction_ts: datetime, market_tz: str) -> date:
    """Convert a UTC prediction timestamp to the exchange's trading day.

    This correctly handles:
    - UTC/local date boundaries (e.g., 23:00 UTC = previous day in US)
    - Weekend/holiday shifts (if prediction made on weekend, use Friday)
    - Daylight saving transitions

    Args:
        prediction_ts: UTC timestamp of the prediction
        market_tz: IANA timezone string (e.g., "America/New_York", "Europe/Paris", "Asia/Kolkata")

    Returns:
        The exchange trading day date
    """
    if prediction_ts.tzinfo is None:
        prediction_ts = prediction_ts.replace(tzinfo=timezone.utc)

    tz = ZoneInfo(market_tz)
    local_ts = prediction_ts.astimezone(tz)

    # If it's weekend in market local time, roll back to Friday
    # This matches exchange calendar behavior
    while local_ts.weekday() >= 5:  # Saturday=5, Sunday=6
        local_ts = local_ts - timedelta(days=1)

    return local_ts.date()


async def _get_market_timezone(session: AsyncSession, instrument_id) -> str:
    """Get the IANA timezone for an instrument's market."""
    from sqlalchemy.orm import selectinload

    # Get instrument with exchange and market
    instrument = await session.get(
        Instrument,
        instrument_id,
        options=[
            selectinload(Instrument.exchange).selectinload(Exchange.market)
        ],
    )

    if instrument and instrument.exchange and instrument.exchange.market:
        return instrument.exchange.market.timezone
    elif instrument and instrument.exchange:
        return instrument.exchange.timezone
    else:
        # Fallback to UTC
        return "UTC"


async def resolve_matured_outcomes(session, limit: int = 200) -> dict:
    """Resolve matured 1d predictions. Returns counts + first error sample."""
    from apps.api.models.prediction import Prediction, PredictionOutcome
    from apps.api.models.price import PriceBar, MarketSnapshot

    resolved = skipped_immature = skipped_invalid = 0
    errors: list[dict] = []

    # Predictions lacking an outcome, oldest first (outer join + NULL filter).
    rows = (
        await session.execute(
            select(Prediction)
            .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .where(PredictionOutcome.id.is_(None), Prediction.horizon == "1d")
            .order_by(Prediction.prediction_timestamp)
            .limit(limit)
        )
    ).scalars().all()

    # Snapshot ORM values BEFORE any commit/rollback. A rollback expires
    # loaded instances even with expire_on_commit=False, and refreshing an
    # expired instance inside this async loop triggers sync IO
    # (MissingGreenlet). Plain Python values are rollback-safe.
    candidates = [
        (
            p.id,
            p.instrument_id,
            p.prediction_timestamp,
            p.data_timestamp,
            p.features_snapshot,
            str(
                p.predicted_direction.value
                if hasattr(p.predicted_direction, "value")
                else p.predicted_direction
            ),
        )
        for p in rows
    ]

    # Cache market timezones to avoid repeated queries
    tz_cache = {}

    for pred_id, inst_id, pred_ts, data_ts, snap_src, predicted in candidates:
        # Get market timezone for exchange-calendar-aware date comparison
        if inst_id not in tz_cache:
            tz_cache[inst_id] = await _get_market_timezone(session, inst_id)
        market_tz = tz_cache[inst_id]

        # PIT-002: Use exchange trading day instead of UTC .date()
        pred_day = _exchange_trading_day(pred_ts, market_tz)

        # Also validate data_timestamp is on the same trading day
        if data_ts is not None:
            data_day = _exchange_trading_day(data_ts, market_tz)
            if data_day != pred_day:
                skipped_invalid += 1
                continue

        try:
            # Next trading bar strictly after the prediction day.
            # Holidays / weekends simply yield nothing yet -> stays pending (honest).
            bars = (
                await session.execute(
                    select(PriceBar)
                    .where(
                        PriceBar.instrument_id == inst_id,
                        PriceBar.timeframe == "1d",
                        PriceBar.timestamp > pred_ts,
                    )
                    .order_by(PriceBar.timestamp)
                    .limit(5)
                )
            ).scalars().all()

            # Find the first bar on a strictly later trading day
            nxt = None
            for b in bars:
                bar_ts = b.timestamp
                if bar_ts.tzinfo is None:
                    bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                bar_day = _exchange_trading_day(bar_ts, market_tz)
                if bar_day > pred_day:
                    nxt = b
                    break

            if nxt is None:
                skipped_immature += 1
                continue

            # Defensive bar validation (ingestion gates normally prevent these).
            ohlc = [nxt.open, nxt.high, nxt.low, nxt.close]
            if any(v is None or v <= 0 for v in ohlc) or nxt.volume is None or nxt.volume < 0:
                skipped_invalid += 1
                continue

            snap = snap_src or {}
            base = snap.get("price")
            if base is None:
                skipped_invalid += 1
                continue

            base_dec = Decimal(str(base))
            close_dec = Decimal(str(nxt.close))

            if base_dec <= 0:
                skipped_invalid += 1
                continue

            ret_dec = (close_dec - base_dec) / base_dec
            ret = float(ret_dec)

            if ret > recipe.TARGET_UP_THRESHOLD:
                actual = "up"
            elif ret < recipe.TARGET_DOWN_THRESHOLD:
                actual = "down"
            else:
                actual = "neutral"

            # Double-checked idempotency (unique constraint is the backstop).
            exists = (
                await session.execute(
                    select(PredictionOutcome.id).where(PredictionOutcome.prediction_id == pred_id)
                )
            ).scalar_one_or_none()

            if exists is not None:
                continue

            session.add(
                PredictionOutcome(
                    prediction_id=pred_id,
                    actual_return=(ret_dec * 100).quantize(Decimal("0.0001")),
                    actual_direction=actual,
                    is_correct=(predicted == actual),
                    evaluation_price=nxt.close,
                    evaluation_timestamp=nxt.timestamp,
                    source=getattr(nxt, "source", None),
                    note=None,
                )
            )
            await session.commit()
            resolved += 1

        except Exception as e:  # noqa: BLE001 - per-row isolation; recorded, never raised
            errors.append({"prediction_id": str(pred_id), "error": str(e)[:200]})
            try:
                await session.rollback()
            except Exception:
                pass

    return {
        "resolved": resolved,
        "skipped_immature": skipped_immature,
        "skipped_invalid": skipped_invalid,
        "errors": errors,
    }