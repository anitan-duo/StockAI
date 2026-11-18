#!/usr/bin/env python3
"""Synthetic fixtures for the integration (Postgres) suite.

Deterministic, self-contained seed that replaces the old prod-dump seeding
(`seed_via_dump` in tests/run_tests.py) which copied rows from the production
`stockai` database. The test DB is populated entirely from code here, so no
prod reads or writes are involved and runs are repeatable.

Design
- Idempotent: call `seed_test_db(session)` on a migrated, empty test DB.
- Synthetic market data: prices walk a fixed deterministic path (seeded RNG
  with fixed seed per symbol) so scenarios/outcomes/labels are stable.
- Instruments: 19 active instruments so the scheduler loop reaches >= 19.
- Model: `Ensemble` / `ensemble-v1.0` with a pinned v1.0 champion row.
- Predictions: recent champion predictions for every instrument (fresh today)
  so screener/top/factors endpoints return real feature vectors, plus a few
  older AAPL/MSFT predictions with matured outcomes for outcome-resolution
  tests.

Safety
- This MUST only run against the isolated `stockai_test` database. Callers
  (tests/run_tests.py) set STOCKAI_TEST_MODE=postgres + DATABASE_URL pointing
  at stockai_test before importing the session factory. The db_guard refuses
  the production DB under test mode unless STOCKAI_ALLOW_PROD_DB is set.
"""
from __future__ import annotations

import hashlib
import math
import os
import random
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

# --------------------------------------------------------------------------
# Constants (fixed seeds for determinism)
# --------------------------------------------------------------------------
SEED = 20261105

MARKETS = [
    {
        "code": "US",
        "name": "United States",
        "country_code": "USA",
        "currency": "USD",
        "timezone": "America/New_York",
        "market_open": time(9, 30),
        "market_close": time(16, 0),
        "pre_market_open": time(4, 0),
        "post_market_close": time(20, 0),
    },
    {
        "code": "IN",
        "name": "India",
        "country_code": "IND",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "market_open": time(9, 15),
        "market_close": time(15, 30),
        "pre_market_open": time(9, 0),
        "post_market_close": time(16, 0),
    },
    {
        "code": "EU",
        "name": "Europe",
        "country_code": "DEU",
        "currency": "EUR",
        "timezone": "Europe/Berlin",
        "market_open": time(9, 0),
        "market_close": time(17, 30),
        "pre_market_open": time(8, 0),
        "post_market_close": time(20, 0),
    },
]

def _exch(e: dict) -> dict:
    """Fill trading-hour defaults for exchanges (mirrors seed_markets.py)."""
    e.setdefault("market_open", time(9, 30))
    e.setdefault("market_close", time(16, 0))
    e.setdefault("pre_market_open", time(4, 0))
    e.setdefault("post_market_close", time(20, 0))
    return e


EXCHANGES = [
    _exch({"code": "NASDAQ", "name": "NASDAQ", "market_code": "US", "timezone": "America/New_York", "currency": "USD"}),
    _exch({"code": "NYSE", "name": "New York Stock Exchange", "market_code": "US", "timezone": "America/New_York", "currency": "USD"}),
    _exch({"code": "NYSEARCA", "name": "NYSE Arca", "market_code": "US", "timezone": "America/New_York", "currency": "USD"}),
    _exch({"code": "NSE", "name": "National Stock Exchange of India", "market_code": "IN", "timezone": "Asia/Kolkata", "currency": "INR", "market_open": time(9, 15), "market_close": time(15, 30), "pre_market_open": time(9, 0), "post_market_close": time(16, 0)}),
    _exch({"code": "BSE", "name": "Bombay Stock Exchange", "market_code": "IN", "timezone": "Asia/Kolkata", "currency": "INR", "market_open": time(9, 15), "market_close": time(15, 30), "pre_market_open": time(9, 0), "post_market_close": time(16, 0)}),
    _exch({"code": "LSE", "name": "London Stock Exchange", "market_code": "EU", "timezone": "Europe/London", "currency": "GBP", "market_open": time(8, 0), "market_close": time(16, 30), "pre_market_open": time(7, 0), "post_market_close": time(17, 0)}),
    _exch({"code": "XETRA", "name": "Xetra", "market_code": "EU", "timezone": "Europe/Berlin", "currency": "EUR"}),
    _exch({"code": "EURONEXT", "name": "Euronext", "market_code": "EU", "timezone": "Europe/Paris", "currency": "EUR"}),
    _exch({"code": "SIX", "name": "SIX Swiss Exchange", "market_code": "EU", "timezone": "Europe/Zurich", "currency": "CHF"}),
]

# (symbol, exchange_code, market_code, name, sector, industry, base_price)
INSTRUMENTS = [
    ("AAPL", "NASDAQ", "US", "Apple Inc.", "Technology", "Consumer Electronics", Decimal("200.00")),
    ("MSFT", "NASDAQ", "US", "Microsoft Corporation", "Technology", "Software", Decimal("400.00")),
    ("GOOGL", "NASDAQ", "US", "Alphabet Inc.", "Technology", "Internet", Decimal("150.00")),
    ("AMZN", "NASDAQ", "US", "Amazon.com Inc.", "Consumer Cyclical", "Internet Retail", Decimal("180.00")),
    ("NVDA", "NASDAQ", "US", "NVIDIA Corporation", "Technology", "Semiconductors", Decimal("120.00")),
    ("META", "NASDAQ", "US", "Meta Platforms", "Technology", "Internet", Decimal("500.00")),
    ("TSLA", "NASDAQ", "US", "Tesla Inc.", "Consumer Cyclical", "Auto Manufacturers", Decimal("250.00")),
    ("RELIANCE", "NSE", "IN", "Reliance Industries", "Energy", "Oil & Gas", Decimal("2500.00")),
    ("TCS", "NSE", "IN", "Tata Consultancy Services", "Technology", "IT Services", Decimal("3800.00")),
    ("INFY", "NSE", "IN", "Infosys Ltd", "Technology", "IT Services", Decimal("1800.00")),
    ("HDFCBANK", "NSE", "IN", "HDFC Bank Ltd", "Financial Services", "Banks", Decimal("1600.00")),
    ("ICICIBANK", "NSE", "IN", "ICICI Bank Ltd", "Financial Services", "Banks", Decimal("1200.00")),
    ("SBIN", "NSE", "IN", "State Bank of India", "Financial Services", "Banks", Decimal("800.00")),
    ("HSBA", "LSE", "EU", "HSBC Holdings", "Financial Services", "Banks", Decimal("700.00")),
    ("SHEL", "LSE", "EU", "Shell plc", "Energy", "Oil & Gas", Decimal("2800.00")),
    ("AZN", "LSE", "EU", "AstraZeneca plc", "Healthcare", "Biotechnology", Decimal("10500.00")),
    ("SAP", "XETRA", "EU", "SAP SE", "Technology", "Software", Decimal("200.00")),
    ("SIE", "XETRA", "EU", "Siemens AG", "Industrials", "Conglomerates", Decimal("180.00")),
    ("ASML", "EURONEXT", "EU", "ASML Holding", "Technology", "Semiconductors", Decimal("700.00")),
]

# Pinned v1.0 artifact SHA prefix (must match services/ml/champion.py).
PINNED_SHA = "sha256:cafe9216074afd5b7ce0237aedef3655af1f2b5fa7d01490175fe807b5af01a7"

FEATURE_KEYS = [
    "return_1d", "log_return_1d", "gap_up", "gap_down", "gap_pct", "body_pct",
    "upper_shadow_pct", "lower_shadow_pct", "close_position", "roc_5d", "roc_10d",
    "roc_20d", "roc_60d", "roc_120d", "momentum_10d", "momentum_20d",
    "momentum_60d", "pct_from_high_20d", "pct_from_low_20d",
    "pct_from_high_60d", "pct_from_low_60d", "pct_from_high_120d",
    "pct_from_low_120d", "realized_vol_5d", "realized_vol_10d",
    "realized_vol_20d", "realized_vol_60d", "realized_vol_120d",
    "parkinson_vol_10d", "parkinson_vol_20d", "parkinson_vol_60d",
    "garman_klass_vol_10d", "garman_klass_vol_20d", "garman_klass_vol_60d",
    "vol_percentile_60d", "vol_percentile_120d", "vol_percentile_252d",
    "vol_regime", "rel_volume_10d", "rel_volume_20d", "rel_volume_60d",
    "volume_trend_20d", "dollar_volume", "avg_dollar_volume_10d",
    "avg_dollar_volume_20d", "vol_price_corr_20d", "obv", "obv_ema_20",
    "sma_5", "pct_from_sma_5", "sma_10", "pct_from_sma_10", "sma_20",
    "pct_from_sma_20", "sma_50", "pct_from_sma_50", "sma_100",
    "pct_from_sma_100", "sma_200", "pct_from_sma_200", "ema_12",
    "pct_from_ema_12", "ema_26", "pct_from_ema_26", "ema_50",
    "pct_from_ema_50", "macd", "macd_signal", "macd_histogram", "adx",
    "plus_di", "minus_di", "rsi_7", "rsi_14", "rsi_21", "stoch_k_14",
    "stoch_d_14", "williams_r_14", "cci_20", "trend_regime",
    "vol_regime_high", "vol_regime_low", "momentum_regime",
    "large_jump_up", "large_jump_down", "volume_spike", "price_discontinuity",
]

# Trading days: skip weekends only (no holiday calendar — determinism first).
def _next_trading_day(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d = d + timedelta(days=1)
    return d


def _trading_days(end: date, n: int) -> list[date]:
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d = d - timedelta(days=1)
    return sorted(days)


def _walk_prices(base: float, n: int, seed: int) -> list[dict]:
    """Deterministic random-walk OHLCV closes (seeded per symbol)."""
    rng = random.Random(seed)
    out = []
    price = base
    for i in range(n):
        daily_ret = rng.gauss(0.0005, 0.015)
        open_ = price
        close = max(1.0, open_ * (1.0 + daily_ret))
        high = max(open_, close) * (1.0 + abs(rng.gauss(0, 0.008)))
        low = min(open_, close) * (1.0 - abs(rng.gauss(0, 0.008)))
        volume = int(rng.uniform(800_000, 5_000_000))
        out.append({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
        price = close
    return out


def _feature_vector(close: float, change_pct: float, seed: int) -> dict:
    """Full 87-key vector + price/change/extra keys used by endpoints."""
    rng = random.Random(seed)
    vec: dict = {}
    for k in FEATURE_KEYS:
        # Plausible ranges per key family; determinism comes from the seed.
        if k.startswith("rsi"):
            vec[k] = round(rng.uniform(30, 70), 4)
        elif k.startswith("realized_vol") or k.startswith("parkinson") or k.startswith("garman"):
            vec[k] = round(rng.uniform(0.10, 0.35), 6)
        elif k in ("sma_5", "sma_10", "sma_20", "sma_50", "sma_100", "sma_200",
                   "ema_12", "ema_26", "ema_50", "dollar_volume",
                   "avg_dollar_volume_10d", "avg_dollar_volume_20d", "obv", "obv_ema_20"):
            vec[k] = round(close * rng.uniform(0.95, 1.05), 4)
        elif k.startswith("macd"):
            vec[k] = round(rng.uniform(-2, 2), 6)
        elif k in ("rel_volume_10d", "rel_volume_20d", "rel_volume_60d"):
            vec[k] = round(rng.uniform(0.6, 1.8), 4)
        elif k in ("adx", "plus_di", "minus_di", "stoch_k_14", "stoch_d_14"):
            vec[k] = round(rng.uniform(10, 60), 4)
        elif k == "williams_r_14":
            vec[k] = round(rng.uniform(-80, -20), 4)
        elif k == "cci_20":
            vec[k] = round(rng.uniform(-100, 100), 4)
        elif k in ("large_jump_up", "large_jump_down", "volume_spike",
                   "price_discontinuity", "trend_regime", "vol_regime_high",
                   "vol_regime_low", "momentum_regime", "vol_regime"):
            vec[k] = 0
        elif k in ("gap_up", "gap_down"):
            vec[k] = 0
        else:
            vec[k] = round(rng.uniform(-0.05, 0.05), 6)
    # Endpoint-expected keys
    vec["price"] = round(close, 4)
    vec["change_percent"] = round(change_pct, 4)
    return vec


async def seed_test_db(session, *, bars_per_symbol: int = 300) -> dict:
    """Populate an empty, migrated test DB with synthetic fixtures.

    Returns a summary dict with ids for callers that need them.
    Idempotent: if the Ensemble model already exists, rows are left alone and
    a `seeded: False` summary is returned (safe to call repeatedly).
    """
    from sqlalchemy import select

    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.mlops import ModelChampion
    from apps.api.models.prediction import Model, ModelVersion, Prediction
    from apps.api.models.price import PriceBar

    summary: dict = {"seeded": False, "markets": 0, "exchanges": 0, "instruments": 0, "bars": 0, "predictions": 0}

    existing = (
        await session.execute(select(Model).where(Model.name == "Ensemble"))
    ).scalar_one_or_none()
    if existing is not None:
        summary["seeded"] = False
        return summary

    # --- Markets -----------------------------------------------------------
    market_by_code: dict[str, Market] = {}
    for m in MARKETS:
        row = Market(**m)
        session.add(row)
        await session.flush()
        market_by_code[m["code"]] = row
    summary["markets"] = len(market_by_code)

    # --- Exchanges -----------------------------------------------------------
    exch_by_code: dict[str, Exchange] = {}
    for e in EXCHANGES:
        market_code = e.pop("market_code")
        row = Exchange(market_id=market_by_code[market_code].id, **e)
        e["market_code"] = market_code
        session.add(row)
        await session.flush()
        exch_by_code[row.code] = row
    summary["exchanges"] = len(exch_by_code)

    # --- Model + version + champion ----------------------------------------
    model = Model(name="Ensemble", description="Synthetic fixture model", model_type="ensemble", is_active=True, metadata_json={})
    session.add(model)
    await session.flush()
    version = ModelVersion(
        model_id=model.id, version="ensemble-v1.0", description="v1.0 baseline",
        is_active=True, training_date=datetime(2025, 1, 2, tzinfo=UTC),
        metrics={"accuracy": 0.54, "brier": 0.22}, hyperparameters={},
    )
    session.add(version)
    await session.flush()
    champion = ModelChampion(
        model_version_id=version.id, artifact_sha=PINNED_SHA,
        status="active", approved_at=datetime(2025, 1, 2, tzinfo=UTC),
        decided_by="test-fixtures", rationale="synthetic pinned v1.0 baseline",
        metrics={"accuracy": 0.54}, superseded_at=None,
    )
    session.add(champion)
    await session.flush()

    # --- Instruments + price bars ------------------------------------------
    today = datetime.now(UTC).date()
    days = _trading_days(today, bars_per_symbol)
    # Guarantee scenario window coverage: bars span up to today, so the
    # 2025-06-15 scenario date is inside the range (300 bars back from Nov
    # 2026 lands around Sep 2025 — WIDEN to cover Jun 2025 for scenarios).
    # Extend the start when needed:
    start_day = min(days[0], date(2025, 1, 2))
    # Rebuild a continuous trading-day span from start_day to today.
    span: list[date] = []
    d = start_day
    while d <= today:
        if d.weekday() < 5:
            span.append(d)
        d = d + timedelta(days=1)
    days = span

    inst_by_symbol: dict[str, Instrument] = {}
    bar_rows: list[PriceBar] = []
    for idx, (symbol, exch_code, _mkt, name, sector, industry, base) in enumerate(INSTRUMENTS):
        inst = Instrument(
            symbol=symbol, name=name, exchange_id=exch_by_code[exch_code].id,
            currency=exch_by_code[exch_code].currency, sector=sector,
            industry=industry, is_active=True, is_tradable=True,
            metadata_json={},
        )
        session.add(inst)
        await session.flush()
        inst_by_symbol[symbol] = inst

        walk = _walk_prices(float(base), len(days), SEED + idx)
        for day, bar in zip(days, walk):
            ts = datetime(day.year, day.month, day.day, tzinfo=UTC)
            bar_rows.append(PriceBar(
                instrument_id=inst.id, timestamp=ts, timeframe="1d",
                open=Decimal(str(bar["open"])), high=Decimal(str(bar["high"])),
                low=Decimal(str(bar["low"])), close=Decimal(str(bar["close"])),
                volume=int(bar["volume"]), vwap=None, trades_count=None,
                source="fixture", ingested_at=ts,
            ))
    session.add_all(bar_rows)
    await session.flush()
    summary["instruments"] = len(inst_by_symbol)
    summary["bars"] = len(bar_rows)

    # --- Predictions -------------------------------------------------------
    # 1) Fresh "today" champion predictions for EVERY instrument so the
    #    scheduler loop + screener/top/factors endpoints have real data.
    # 2) Older AAPL/MSFT predictions (matured) for outcome-resolution tests.
    now = datetime.now(UTC)
    pred_rows: list[Prediction] = []

    for idx, (symbol, exch_code, _m, name, sector, industry, base) in enumerate(INSTRUMENTS):
        inst = inst_by_symbol[symbol]
        # Latest close from the walk for the snapshot price.
        walk = _walk_prices(float(base), len(days), SEED + idx)
        last = walk[-1]
        last_close = last["close"]
        prev_close = walk[-2]["close"] if len(walk) > 1 else last_close
        change_pct = (last_close / prev_close - 1.0) * 100.0 if prev_close else 0.0
        feats = _feature_vector(last_close, change_pct, SEED * 7 + idx)
        up = 0.55
        neutral = 0.30
        down = 0.15
        pred_rows.append(Prediction(
            instrument_id=inst.id, model_version_id=version.id, horizon="1d",
            predicted_direction="up",
            up_probability=Decimal(str(up)), neutral_probability=Decimal(str(neutral)),
            down_probability=Decimal(str(down)),
            expected_return=Decimal("0.0030"), range_lower=Decimal("-0.0200"),
            range_upper=Decimal("0.0200"), confidence=72,
            prediction_timestamp=now, data_timestamp=now,
            features_snapshot=feats,
        ))

    # Older matured predictions (30 days ago) for AAPL + MSFT so outcome
    # resolution has work to do that is idempotent on re-run.
    for idx, symbol in enumerate(("AAPL", "MSFT")):
        inst = inst_by_symbol[symbol]
        # Reuse the last walk's close as the historical price anchor.
        # We only need features_snapshot.price > 0 for outcome resolution.
        old_price = 200.0 if symbol == "AAPL" else 400.0
        feats = _feature_vector(old_price, 0.5, SEED * 13 + idx)
        pred_rows.append(Prediction(
            instrument_id=inst.id, model_version_id=version.id, horizon="1d",
            predicted_direction="up",
            up_probability=Decimal("0.6"), neutral_probability=Decimal("0.25"),
            down_probability=Decimal("0.15"),
            expected_return=Decimal("0.0040"), range_lower=Decimal("-0.0150"),
            range_upper=Decimal("0.0150"), confidence=70,
            prediction_timestamp=now - timedelta(days=30),
            data_timestamp=now - timedelta(days=30),
            features_snapshot=feats,
        ))

    session.add_all(pred_rows)
    await session.flush()
    summary["predictions"] = len(pred_rows)
    summary["seeded"] = True
    summary["aapl_id"] = str(inst_by_symbol["AAPL"].id)
    summary["model_version_id"] = str(version.id)
    return summary


if __name__ == "__main__":
    # Standalone: seed the DB named by DATABASE_URL (test DB only).
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from apps.api.database import async_session_factory

    async def _main() -> None:
        async with async_session_factory() as session:
            result = await seed_test_db(session)
            await session.commit()
            print(result)

    asyncio.run(_main())
