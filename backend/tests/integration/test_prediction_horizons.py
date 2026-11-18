"""Horizon honesty (§15): v1.0 is a 1-day model; 1w/1m labels are refused.

Live-DB integration tests (require Postgres + seeded instruments).
"""

from fastapi.testclient import TestClient


def _client():
    from apps.api.main import app

    return TestClient(app)


def test_unsupported_horizons_rejected_on_all_prediction_endpoints():
    c = _client()
    # Quote-style single prediction
    r = c.get("/api/v1/predictions/stocks/AAPL?exchange=NASDAQ&horizon=1w")
    assert r.status_code == 422
    assert r.json()["detail"]["status"] == "UNSUPPORTED_HORIZON"
    r = c.get("/api/v1/predictions/stocks/AAPL?exchange=NASDAQ&horizon=1m")
    assert r.status_code == 422
    # History / factors / top share the same contract
    assert c.get("/api/v1/predictions/stocks/AAPL/history?exchange=NASDAQ&horizon=1w").status_code == 422
    assert c.get("/api/v1/predictions/stocks/AAPL/factors?exchange=NASDAQ&horizon=1m").status_code == 422
    assert c.get("/api/v1/predictions?horizon=1w").status_code == 422


def test_1d_prediction_carries_native_horizon():
    c = _client()
    r = c.get("/api/v1/predictions/stocks/AAPL?exchange=NASDAQ&horizon=1d")
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        body = r.json()
        assert body["model_horizon"] == "1d"
        assert body["horizon"] == "1d"


def test_top_predictions_carry_native_horizon():
    c = _client()
    r = c.get("/api/v1/predictions?horizon=1d&limit=5")
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    for item in items:
        assert item["model_horizon"] == "1d"
        # Transparency fields for age/version display (never timeless).
        assert item["prediction_timestamp"], "top item missing prediction_timestamp"
        assert item["model_version"], "top item missing model_version"


def test_factors_read_real_feature_keys():
    c = _client()
    r = c.get("/api/v1/predictions/stocks/AAPL/factors?exchange=NASDAQ&horizon=1d")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert isinstance(body["positive"], list)
        assert isinstance(body["neutral"], list)
        assert isinstance(body["negative"], list)
        total = len(body["positive"]) + len(body["neutral"]) + len(body["negative"])
        # AAPL snapshot carries full 87-feature vectors; the fixed key mapping
        # (rsi_14/macd_histogram/rel_volume_20d/realized_vol_20d) must surface
        # real factor statements instead of the old always-empty output.
        assert total > 0
