# ruff: noqa: PLC0415, PLR2004, N806
"""ACC-001 ranking artifact, inference and outcome-resolution regressions."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from apps.api.models.market import Exchange, Instrument, InstrumentType, Market
from apps.api.models.price import PriceBar
from apps.api.models.ranking import RankingEntry, RankingSnapshot
from services.ml.crosssec_ranking import (
    DESCRIPTOR_NAMES,
    RANKING_OBJECTIVE,
    score_cross_section,
)
from services.ranking.service import RankingService, load_ranking_artifact

ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / "model_artifacts/ranking/v1"


def _synthetic_bars(start: date, count: int, *, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    day = start
    close = 100.0
    while len(rows) < count:
        if day.weekday() < 5:
            ret = 0.0005 + rng.normal(0, 0.012)
            prev = close
            close = max(1.0, close * (1 + ret))
            rows.append(
                {
                    "date": day,
                    "timestamp": datetime(day.year, day.month, day.day, tzinfo=UTC),
                    "open": prev,
                    "high": max(prev, close) * 1.004,
                    "low": min(prev, close) * 0.996,
                    "close": close,
                    "volume": 1_000_000 + int(rng.integers(0, 100_000)),
                }
            )
        day += timedelta(days=1)
    return rows


@pytest.mark.skipif(not ARTIFACT_ROOT.exists(), reason="ranking artifacts not built")
@pytest.mark.parametrize("horizon", [1, 5, 10])
def test_artifacts_match_manifest_and_schema(horizon):
    artifact, digest, path = load_ranking_artifact(horizon)
    assert artifact["objective"] == RANKING_OBJECTIVE
    assert artifact["horizon"] == horizon
    assert len(artifact["feature_names"]) == 90
    assert tuple(artifact["feature_names"][-3:]) == DESCRIPTOR_NAMES
    assert len(digest) == 64
    assert path.exists()


def test_relative_label_fits_model_column():
    from apps.api.models.ranking import RankingEntry

    assert RankingEntry.__table__.c.relative_label.type.length >= len("expected_above_median")


@pytest.mark.skipif(not ARTIFACT_ROOT.exists(), reason="ranking artifacts not built")
def test_score_cross_section_returns_finite_probabilities():
    artifact, _, _ = load_ranking_artifact(1)
    start = date(2025, 1, 1)
    bars = {
        f"SYM{i}@TEST": _synthetic_bars(start, 280, seed=i) for i in range(6)
    }
    markets = dict.fromkeys(bars, "US")
    as_of = bars["SYM0@TEST"][-1]["date"]
    eligible, X, excluded = score_cross_section(
        bars, markets, as_of, artifact["feature_names"], 1
    )
    assert excluded == {}
    assert eligible == sorted(bars)
    assert X.shape == (6, 90)
    assert np.isfinite(X).all()

    from services.ml.crosssec_ranking import predict_outperformance

    probs = predict_outperformance(artifact, X)
    assert probs.shape == (6,)
    assert ((probs >= 0) & (probs <= 1)).all()


@pytest.mark.asyncio
async def test_resolve_outcomes_handles_decimal_prices():
    from apps.api.database import async_session_factory

    async with async_session_factory() as session:
        market = Market(
            code="TS", name="Test", country_code="USA", currency="USD",
            timezone="America/New_York", is_active=True,
            market_open=datetime(2020, 1, 1, 9, 30).time(),
            market_close=datetime(2020, 1, 1, 16, 0).time(),
        )
        session.add(market)
        await session.flush()
        exchange = Exchange(
            code="TST", name="Test Exchange", market_id=market.id,
            timezone="America/New_York", currency="USD", is_active=True,
            market_open=datetime(2020, 1, 1, 9, 30).time(),
            market_close=datetime(2020, 1, 1, 16, 0).time(),
        )
        session.add(exchange)
        await session.flush()
        instruments = []
        for i in range(6):
            inst = Instrument(
                symbol=f"T{i}", name=f"Test {i}", exchange_id=exchange.id,
                type=InstrumentType.EQUITY, currency="USD", is_active=True,
                metadata_json={},
            )
            session.add(inst)
            instruments.append(inst)
        await session.flush()

        as_of = date(2026, 11, 2)
        end = date(2026, 11, 3)
        snapshot = RankingSnapshot(
            market="ALL", horizon="1d", as_of_date=as_of,
            generated_at=datetime.now(UTC), objective=RANKING_OBJECTIVE,
            model_version="ranking-v1-h1", artifact_sha="a" * 64, feature_version="v1",
            universe_size=6, market_universe_size=6, metadata_json={},
        )
        session.add(snapshot)
        await session.flush()
        for i, inst in enumerate(instruments):
            session.add(
                RankingEntry(
                    snapshot_id=snapshot.id, instrument_id=inst.id, symbol=inst.symbol,
                    exchange=exchange.code, rank=i + 1, score=Decimal("0.5"),
                    percentile=Decimal("50.0"), quintile=1,
                    relative_label="expected_above_median",
                )
            )
            for day, close in ((as_of, Decimal("100")), (end, Decimal(100 + i))):
                session.add(
                    PriceBar(
                        instrument_id=inst.id,
                        timestamp=datetime(day.year, day.month, day.day, tzinfo=UTC),
                        timeframe="1d", session_day=day, open=close, high=close,
                        low=close, close=close, volume=1000, source="test",
                    )
                )
        await session.commit()

        result = await RankingService(session).resolve_outcomes()
        assert result["resolved"] == 6
        assert result["errors"] == 0

        perf = await RankingService(session).performance(None, "1d")
        assert perf["n_outcomes"] == 6
        assert perf["hit_rate"] is not None
