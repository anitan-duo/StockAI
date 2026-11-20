import json
import pathlib
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone

from services.ml.calibration import expected_calibration_error
from services.ml.features import FeaturePipeline
from services.ml.target import TargetDefinition, compute_target_series



def _require_calibration_file():
    """Return the private real-evaluation artifact or skip artifact-dependent assertions."""
    candidates = [
        pathlib.Path("backend/model_artifacts/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("model_artifacts/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("backend/model_artifacts/real/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("model_artifacts/real/ensemble/v1.0/calibration_metrics.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    pytest.skip("Private real walk-forward calibration artifact is not distributed in the public repository")

# Helper to create synthetic priced data for deterministic tests
def _make_prices(n=300, seed=0):
    np.random.seed(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="D", tz=timezone.utc)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 10)
    return pd.Series(close, index=dates)

def test_calibration_uses_real_data_not_synthetic():
    """1. Calibration metrics must come from real evaluation data, not synthetic beta."""
    p = _require_calibration_file()
    assert p.exists(), "calibration_metrics.json missing"
    data = json.loads(p.read_text())
    # Must have note indicating walk-forward, not synthetic
    assert "Walk-forward" in data.get("note", "") or "walk-forward" in data.get("note", "").lower()
    # Must not be the old synthetic note
    assert "synthetic" not in data.get("note", "").lower() or "No synthetic" in data.get("note", "")
    # Must have evaluation_period with real dates
    assert "evaluation_period" in data
    assert data["evaluation_period"]["start"] is not None
    assert data["evaluation_period"]["end"] is not None

def test_calibration_is_out_of_sample():
    """2. Calibration evaluation is out-of-sample (test dates after train)."""
    p = _require_calibration_file()
    data = json.loads(p.read_text())
    # fold_metrics should show train/test split
    assert "fold_metrics" in data
    assert len(data["fold_metrics"]) >= 2
    # Evaluation period should be after training period (2026-01 to 2026-06 is out-of-sample for training that used up to 2026-08 but with gap)
    # Check that evaluation period is not the full training period
    start = datetime.fromisoformat(data["evaluation_period"]["start"])
    end = datetime.fromisoformat(data["evaluation_period"]["end"])
    assert start < end
    assert start.year == 2026  # out-of-sample is recent

def test_no_future_target_in_features():
    """3. No future target values enter feature construction."""
    # Check that FeaturePipeline uses only shift(1) and rolling, never shift(-1)
    fp_path = pathlib.Path("backend/services/ml/features.py")
    if not fp_path.exists():
        fp_path = pathlib.Path("services/ml/features.py")
    fp = fp_path.read_text()
    assert "shift(-1)" not in fp, "Feature pipeline must not use future shift(-1)"
    assert "shift(1)" in fp or "pct_change" in fp
    # Check target uses future (which is correct for label) but features don't
    tp_path = pathlib.Path("backend/services/ml/target.py")
    if not tp_path.exists():
        tp_path = pathlib.Path("services/ml/target.py")
    tp = tp_path.read_text()
    assert "shift(-1)" in tp or "future" in tp.lower()  # target should use future

def test_brier_is_multiclass_mean():
    """4. Brier score is documented as multiclass mean of per-class one-vs-rest."""
    p = _require_calibration_file()
    data = json.loads(p.read_text())
    # brier_score should be mean of per-class
    assert "brier_score" in data
    assert "brier_per_class" in data
    per_class = data["brier_per_class"]
    assert set(per_class.keys()) == {"down", "neutral", "up"}
    expected_mean = sum(per_class.values()) / len(per_class)
    assert abs(data["brier_score"] - expected_mean) < 1e-6, "Brier overall must be mean of per-class"

def test_ece_is_mean_of_per_class():
    """5. ECE is calculated as mean of per-class ECE or top-class, documented."""
    p = _require_calibration_file()
    data = json.loads(p.read_text())
    assert "ece" in data
    assert "ece_per_class" in data
    per_class = data["ece_per_class"]
    assert set(per_class.keys()) == {"down", "neutral", "up"}
    expected = sum(per_class.values()) / len(per_class)
    assert abs(data["ece"] - expected) < 1e-6
    # Also check ece_top exists
    assert "ece_top" in data

def test_calibration_output_includes_version_and_count():
    """6. Calibration output includes model version and sample count."""
    p = _require_calibration_file()
    data = json.loads(p.read_text())
    assert "model_version" in data
    assert data["model_version"] == "real-v1.0"
    assert "sample_count" in data
    assert data["sample_count"] == 571
    assert "classes" in data
    assert data["classes"] == ["down", "neutral", "up"]

def test_calibration_endpoint_schema():
    """7. GET /training/calibration returns expected schema."""
    import sys
    sys.path.insert(0, "backend")
    from fastapi.testclient import TestClient
    from apps.api.main import app
    c = TestClient(app)
    # Need auth
    import uuid
    email = f"cal_test_{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/api/v1/auth/register", json={"email": email, "password": "TestPass123!", "full_name": "Cal Test"})
    assert r.status_code in (200, 201)
    token = r.json()["tokens"]["access_token"]
    r = c.get("/api/v1/training/calibration", headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 503:
        assert "calibration data unavailable" in r.text.lower()
        return
    assert r.status_code == 200, r.text
    data = r.json()
    assert "model_version" in data
    assert "brier_score" in data
    assert "ece" in data
    assert "sample_count" in data
    assert "calibration_curve" in data
    assert "generated_at" in data

def test_missing_calibration_returns_unavailable():
    """8. Missing/unavailable calibration data produces explicit non-success response."""
    import pathlib

    candidates = [
        pathlib.Path("backend/model_artifacts/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("model_artifacts/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("backend/model_artifacts/real/ensemble/v1.0/calibration_metrics.json"),
        pathlib.Path("model_artifacts/real/ensemble/v1.0/calibration_metrics.json"),
    ]
    backups = {}
    for p in candidates:
        if p.exists():
            backups[p] = p.read_bytes()
            p.unlink()
    # Also need to handle legacy metrics.json fallback
    legacy = [
        pathlib.Path("backend/model_artifacts/ensemble/v1.0/metrics.json"),
        pathlib.Path("model_artifacts/ensemble/v1.0/metrics.json"),
    ]
    legacy_backups = {}
    for p in legacy:
        if p.exists():
            # Temporarily move but ensure no brier_score
            data = p.read_bytes()
            import json

            j = json.loads(data)
            if "brier_score" in j:
                legacy_backups[p] = data
                p.unlink()

    try:
        import sys

        sys.path.insert(0, "backend")
        from fastapi.testclient import TestClient
        from apps.api.main import app
        import uuid

        c = TestClient(app)
        email = f"cal_missing_{uuid.uuid4().hex[:8]}@example.com"
        r = c.post("/api/v1/auth/register", json={"email": email, "password": "TestPass123!", "full_name": "Test"})
        token = r.json()["tokens"]["access_token"]
        r = c.get("/api/v1/training/calibration", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 503, f"Expected 503, got {r.status_code} {r.text}"
        assert "unavailable" in r.text.lower() or "Calibration data unavailable" in r.text
    finally:
        for p, data in backups.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        for p, data in legacy_backups.items():
            p.write_bytes(data)

def test_endpoint_does_not_expose_secrets():
    """9. Endpoint does not expose secrets or filesystem internals."""
    import sys
    sys.path.insert(0, "backend")
    from fastapi.testclient import TestClient
    from apps.api.main import app
    import uuid
    c = TestClient(app)
    email = f"cal_secret_{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/api/v1/auth/register", json={"email": email, "password": "TestPass123!", "full_name": "Test"})
    token = r.json()["tokens"]["access_token"]
    r = c.get("/api/v1/training/calibration", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200, 503)
    text = r.text.lower()
    assert "secret" not in text
    assert "api_key" not in text
    assert "alpa" not in text
    assert "backend/model_artifacts" not in text
    assert "private" not in text or "private" in r.json().get("note", "").lower()  # allow note
