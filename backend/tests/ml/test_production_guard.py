"""ML production regression guard: v1.0 recipe constants must not drift silently.

If any of these change intentionally, update this test AND the v1 baseline doc.
"""

import pytest

EXPECTED_MODEL_HASH_PREFIX = "sha256:cafe9216074afd5b"


def test_recipe_thresholds_frozen():
    from services.ml import recipe

    assert recipe.TARGET_UP_THRESHOLD == 0.005
    assert recipe.TARGET_DOWN_THRESHOLD == -0.005
    assert recipe.NO_EDGE_THRESHOLD == 0.40
    assert recipe.NO_EDGE_CONFIDENCE_CAP == 55
    assert recipe.ENTRY_CONFIDENCE_MIN == 60
    assert recipe.ENTRY_PROB_MIN == 0.5
    assert recipe.FEATURE_LOOKBACK_BARS == 252
    assert recipe.CALIBRATION_METHOD == "isotonic"
    assert recipe.RANDOM_STATE == 42
    # §15 horizon honesty: the artifact natively forecasts 1 trading day.
    # Any multi-horizon model is a NEW recipe version, never a silent change.
    assert recipe.TARGET_HORIZON_DAYS == 1
    assert recipe.MODEL_NATIVE_HORIZON == "1d"


def test_production_artifact_unchanged():
    import hashlib
    import pathlib

    candidates = [
        pathlib.Path("model_artifacts/real/ensemble/v1.0/model.pkl"),
        pathlib.Path("backend/model_artifacts/real/ensemble/v1.0/model.pkl"),
    ]
    found = [p for p in candidates if p.exists()]
    if not found:
        pytest.skip("Private production model is intentionally excluded from the public repository")
    for p in found:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        assert ("sha256:" + h.hexdigest()).startswith(EXPECTED_MODEL_HASH_PREFIX), p


def test_feature_schema_unchanged():
    import json
    import pathlib

    for p in [
        pathlib.Path("model_artifacts/real/ensemble/v1.0/feature_schema.json"),
        pathlib.Path("backend/model_artifacts/real/ensemble/v1.0/feature_schema.json"),
    ]:
        if not p.exists():
            continue
        schema = json.loads(p.read_text())
        assert schema["n_features"] == 87
        assert schema["lookback_bars"] == 252
        return
    pytest.skip("Private production feature schema is intentionally excluded from the public repository")
