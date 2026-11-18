"""Screener honesty: no fabricated zeros; real indicator keys.

- price/change_percent are None (never Decimal 0) without snapshot data.
- volatility reads the unified schema key (realized_vol_20d), so it is
  populated whenever a snapshot exists (previously always null via a
  nonexistent 'volatility_20' key).
"""

from decimal import Decimal


def test_null_price_validates_no_zero_fabrication():
    from packages.schemas.screener import ScreenerResult

    r = ScreenerResult(symbol="X", name="X", exchange="N", price=None, change_percent=None)
    assert r.price is None
    assert r.change_percent is None


def test_live_screener_reports_real_values():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    c = TestClient(app)
    r = c.post("/api/v1/screener", json={"limit": 50})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    aapl = next((i for i in items if i["symbol"] == "AAPL"), None)
    assert aapl is not None
    # AAPL has a fresh prediction snapshot: price and volatility are real.
    assert aapl["price"] is not None and Decimal(str(aapl["price"])) > 0
    assert aapl["volatility"] is not None and Decimal(str(aapl["volatility"])) > 0
    assert aapl["prediction"] is not None
