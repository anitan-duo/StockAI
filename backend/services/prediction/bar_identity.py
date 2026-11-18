"""Underlying-bar identity for prediction de-duplication.

Legacy predictions store wall-clock timestamps (prediction_timestamp ==
data_timestamp == generation time), so the bar a forecast belongs to must
be derived from price bars: the latest 1d bar at or before the prediction
timestamp. Bars may also be double-stamped by multiple providers for the
same trading day, so the canonical dedupe key is the bar's UTC DATE.

All hit-rate denominators must collapse forecasts to one row per
(instrument, horizon, model version, bar day). Newer rows are bar-aligned
and resolve to their own timestamp, so this mapping is safe for both.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _as_aware_utc(ts: datetime) -> datetime:
    """Normalize (possibly naive) timestamps to aware UTC.

    SQLite drivers return naive datetimes while Postgres returns aware
    ones; naive values are interpreted as UTC (the DB stores UTC).
    """
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


async def load_bar_day_index(
    session: AsyncSession,
    instrument_ids: list | None = None,
) -> dict[object, list[datetime]]:
    """Return {instrument_id: sorted 1d bar timestamps} (UTC datetimes)."""
    from apps.api.models.price import PriceBar

    query = select(PriceBar.instrument_id, PriceBar.timestamp).where(
        PriceBar.timeframe == "1d"
    )
    if instrument_ids:
        query = query.where(PriceBar.instrument_id.in_(instrument_ids))
    rows = (await session.execute(query)).all()

    index: dict[object, list[datetime]] = defaultdict(list)
    for instrument_id, ts in rows:
        index[instrument_id].append(_as_aware_utc(ts))
    for stamps in index.values():
        stamps.sort()
    return index


def bar_day(
    index: dict[object, list[datetime]],
    instrument_id: Any,
    prediction_ts: datetime,
) -> datetime.date:
    """UTC date of the latest 1d bar at or before the prediction timestamp.

    Falls back to the prediction's own date when the instrument has no bar
    at or before it (e.g. brand-new instruments) — never raises.
    """
    stamps = index.get(instrument_id) or []
    pred_ts = _as_aware_utc(prediction_ts)
    if not stamps:
        return pred_ts.date()
    i = bisect.bisect_right(stamps, pred_ts)
    if i == 0:
        return prediction_ts.date()
    return stamps[i - 1].date()
