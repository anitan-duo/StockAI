"""Unit: BAR-002 reconciliation plan (no database writes)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from apps.api.models.market import Exchange, Instrument
from apps.api.models.price import PriceBar
from scripts.bar002_reconcile import Plan


def _bar(ts, *, close="100", volume=1000, source="yahoo_finance"):
    return PriceBar(
        id=uuid4(),
        instrument_id=uuid4(),
        timestamp=ts,
        timeframe="1d",
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=volume,
        source=source,
        ingested_at=ts,
        created_at=ts,
        updated_at=ts,
    )


def _instrument(symbol="AAPL"):
    return Instrument(id=uuid4(), symbol=symbol, exchange_id=1)


def _exchange(code="NASDAQ", tz="America/New_York"):
    ex = Exchange(code=code, timezone=tz, market_id=1)
    ex.id = 1
    return ex


def test_us_utc_label_and_exchange_midnight_are_same_session_redundant():
    inst, exch = _instrument(), _exchange()
    label = _bar(datetime(2026, 10, 23, 0, 0, tzinfo=UTC), source="twelvedata")
    yahoo = _bar(datetime(2026, 10, 23, 4, 0, tzinfo=UTC))
    for b in (label, yahoo):
        b.instrument_id = inst.id
    plan = Plan([(label, inst, exch), (yahoo, inst, exch)])

    assert plan.duplicate_groups == 1
    assert plan.classifications == {"redundant": 1}
    assert plan.drop_ids == [label.id]
    assert str(yahoo.id) in plan.backfill[str(inst.id)]


def test_material_ohlcv_disagreement_is_quarantined_not_dropped():
    inst, exch = _instrument("ASML"), _exchange("EURONEXT", "Europe/Paris")
    label = _bar(datetime(2026, 10, 29, 0, 0, tzinfo=UTC), close="1514.4")
    yahoo = _bar(datetime(2026, 10, 28, 23, 0, tzinfo=UTC), close="1487.6")
    for b in (label, yahoo):
        b.instrument_id = inst.id
    plan = Plan([(label, inst, exch), (yahoo, inst, exch)])

    assert plan.classifications == {"quarantined_ohlcv_conflict": 1}
    assert plan.drop_ids == []
    assert plan.quarantine_ids == [str(label.id), str(yahoo.id)]
    assert plan.backfill == {}


def test_missing_canonical_survivor_is_quarantined():
    inst, exch = _instrument(), _exchange()
    # Neither row is stamped at NY midnight (04:00Z on 2026-10-23).
    a = _bar(datetime(2026, 10, 23, 0, 0, tzinfo=UTC), source="twelvedata")
    b = _bar(datetime(2026, 10, 23, 4, 30, tzinfo=UTC), source="finnhub")
    for x in (a, b):
        x.instrument_id = inst.id
    plan = Plan([(a, inst, exch), (b, inst, exch)])

    assert plan.classifications == {"quarantined_no_canonical_survivor": 1}
    assert plan.drop_ids == []
    assert len(plan.quarantine_ids) == 2


def test_unique_rows_are_backfilled_without_changes():
    inst, exch = _instrument("RELIANCE"), _exchange("NSE", "Asia/Kolkata")
    bar = _bar(datetime(2026, 8, 19, 18, 30, tzinfo=UTC))
    bar.instrument_id = inst.id
    plan = Plan([(bar, inst, exch)])

    assert plan.duplicate_groups == 0
    assert plan.drop_ids == []
    assert plan.quarantine_ids == []
    assert plan.backfill[str(inst.id)][str(bar.id)] == "2026-08-20"


def test_dst_canonical_instants_are_session_local_midnight():
    inst, exch = _instrument(), _exchange()
    winter = _bar(datetime(2026, 1, 15, 5, 0, tzinfo=UTC))
    winter.instrument_id = inst.id
    plan = Plan([(winter, inst, exch)])
    assert plan.duplicate_groups == 0
    assert plan.backfill[str(inst.id)][str(winter.id)] == "2026-01-15"
