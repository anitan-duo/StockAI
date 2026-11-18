"""Training-pipeline integrity: prepare_data path, fold scaler bookkeeping, predict names.

Regression coverage for defects found in audit:
- ModelTrainer.prepare_data called a non-existent TargetDefinition.compute_target_series
- best_models stored the unfitted production scaler instead of the fold scaler
- ModelTrainer.predict passed numpy (no feature names) to calibrated models
"""

import numpy as np
import pandas as pd
import pytest  # noqa: F401  (kept for asyncio marker consistency)


def _prices_frame(symbols=("AAA", "BBB"), n=120, seed=7):
    rng = np.random.default_rng(seed)
    frames = []
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    for s in symbols:
        close = 100 + np.cumsum(rng.normal(0, 0.8, n))
        close = np.maximum(close, 5)
        df = pd.DataFrame({"close": close}, index=dates)
        df["symbol"] = s
        df = df.set_index("symbol", append=True).swaplevel(0, 1)
        df.index.names = ["symbol", "date"]
        frames.append(df)
    return pd.concat(frames).sort_index()


def _features_frame(prices, n_features=5, seed=11):
    rng = np.random.default_rng(seed)
    idx = prices.index
    cols = [f"f{i}" for i in range(n_features)]
    data = rng.normal(0, 1, (len(idx), n_features))
    return pd.DataFrame(data, index=idx, columns=cols)


def test_prepare_data_uses_module_target_function():
    from services.ml.training import ModelTrainer

    trainer = ModelTrainer()
    prices = _prices_frame()
    features = _features_frame(prices)
    X, y = trainer.prepare_data(features, prices)
    assert len(X) > 0
    assert set(np.unique(y)).issubset({0, 1, 2})
    # last bar per symbol has NaN target and must be dropped
    assert len(X) == len(prices) - len(prices.index.get_level_values("symbol").unique())


def test_best_models_store_fitted_fold_scaler():
    from services.ml.training import ModelTrainer

    trainer = ModelTrainer()
    prices = _prices_frame(n=200)
    features = _features_frame(prices)
    X, y = trainer.prepare_data(features, prices)
    report = trainer.train_walk_forward(X, y, n_splits=2)
    assert report["best_models"], "expected at least one fold to train"
    for name, info in report["best_models"].items():
        scaler = info["scaler"]
        assert hasattr(scaler, "mean_"), f"{name}: stored scaler is unfitted"
        assert scaler.n_features_in_ == len(trainer.feature_names)
    assert "majority_class" in report["baseline_scores"]
    assert len(report["baseline_scores"]["majority_class"]) > 0


def test_predict_accepts_feature_names_without_warning():
    import warnings

    from services.ml.training import ModelTrainer

    trainer = ModelTrainer()
    prices = _prices_frame(n=200)
    features = _features_frame(prices)
    X, y = trainer.prepare_data(features, prices)
    trainer.train_walk_forward(X, y, n_splits=2)
    sample = X.iloc[:4]
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        out = trainer.predict(sample)
    assert out["probabilities"].shape == (4, 3)


def test_artifact_manifest_consistent_with_model():
    """Artifact bundle must be self-consistent: schema/manifest match model.pkl."""
    import json
    import pathlib

    import joblib

    candidates = [
        pathlib.Path("model_artifacts/real/ensemble/v1.0"),
        pathlib.Path("backend/model_artifacts/real/ensemble/v1.0"),
        pathlib.Path("model_artifacts/ensemble/v1.0"),
    ]
    root = next((p for p in candidates if (p / "model.pkl").exists()), None)
    assert root is not None, "no model artifact found"
    data = joblib.load(root / "model.pkl")
    schema = json.loads((root / "feature_schema.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    assert schema["n_features"] == len(data["features"]) == 87
    assert schema["feature_names"] == data["features"]
    assert manifest["n_features"] == 87
    assert manifest["model_version"] == data.get("model_version")
    assert "model.pkl" in manifest["files"]
    assert manifest.get("integrity", {}).get("model.pkl", "").startswith("sha256:")


def test_filesystem_loader_returns_schema_compatible_artifact():
    """Inference must refuse silently-incompatible artifacts (dims + schema checked)."""
    import json
    import pathlib

    from services.prediction.prediction_service import PredictionEngine

    eng = PredictionEngine.__new__(PredictionEngine)
    out = eng._load_filesystem_model()
    assert out is not None, "expected a loadable filesystem artifact"
    _, scaler, feats, _, path = out
    assert len(feats) == 87
    assert getattr(scaler, "n_features_in_", len(feats)) == len(feats)
    schema_path = pathlib.Path(path).parent / "feature_schema.json"
    assert schema_path.exists()
    assert json.loads(schema_path.read_text())["feature_names"] == list(feats)
