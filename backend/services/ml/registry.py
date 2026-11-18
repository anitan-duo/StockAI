from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import os
import pickle
import pandas as pd
import numpy as np

from services.ml.training import ModelTrainer


class ModelStatus(str, Enum):
    """Model status in registry."""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class ModelRegistry:
    """
    Model registry with versioning, metadata, and deployment management.

    File-backed with an in-memory index. Route call sites pass the DB session
    positionally (ModelRegistry(session)); it is accepted for forward
    compatibility but persistence remains file-based (session unused).
    """

    def __init__(self, storage_path: Any = "./model_registry", session: Any = None):
        # Routes call ModelRegistry(session): tolerate a session in first position.
        if not isinstance(storage_path, str):
            session = storage_path
            storage_path = "./model_registry"
        self.storage_path = storage_path
        self.session = session  # accepted for forward compat; persistence is file-based
        self.models = {}  # name -> {version -> metadata}
        self.active_versions = {}  # name -> active version
        self._load_index()  # activations/registrations survive restarts

    def _index_path(self) -> str:
        import os

        return os.path.join(self.storage_path, "registry_index.json")

    def _load_index(self) -> None:
        """Restore the registry index (registrations + activations)."""
        import json
        import os

        try:
            path = self._index_path()
            if not os.path.exists(path):
                return
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("models"), dict):
                self.models = data["models"]
            if isinstance(data.get("active_versions"), dict):
                self.active_versions = {
                    str(k): str(v) for k, v in data["active_versions"].items()
                }
        except Exception:
            # Corrupt index must never break serving (filesystem fallback).
            self.models = {}
            self.active_versions = {}

    def _save_index(self) -> None:
        """Persist the registry index (best-effort, never breaks callers)."""
        import json
        import os

        try:
            os.makedirs(self.storage_path, exist_ok=True)
            with open(self._index_path(), "w", encoding="utf-8") as f:
                json.dump(
                    {"models": self.models, "active_versions": self.active_versions},
                    f,
                    indent=2,
                    default=str,
                )
        except Exception:
            pass

    def register(
        self,
        name: str,
        version: str,
        model: Any,
        calibrator: Any,
        scaler: Any,
        features: list[str],
        metrics: dict[str, float],
        training_data_hash: str,
        hyperparameters: dict[str, Any],
        description: str = "",
        status: ModelStatus = ModelStatus.CANDIDATE,
    ) -> str:
        """
        Register a new model version.

        Returns:
            Version identifier
        """
        if name not in self.models:
            self.models[name] = {}

        metadata = {
            "name": name,
            "version": version,
            "status": status.value,
            "description": description,
            "metrics": metrics,
            "training_data_hash": training_data_hash,
            "hyperparameters": hyperparameters,
            "feature_names": features,
            "created_at": datetime.now().isoformat(),
            "model_path": f"{name}/{version}/model.pkl",
            "calibrator_path": f"{name}/{version}/calibrator.pkl",
            "scaler_path": f"{name}/{version}/scaler.pkl",
        }

        self.models[name][version] = metadata

        # Save artifacts
        self._save_artifacts(name, version, model, calibrator, scaler)
        self._save_index()

        return version

    def _save_artifacts(
        self,
        name: str,
        version: str,
        model: Any,
        calibrator: Any,
        scaler: Any,
    ) -> None:
        """Save model artifacts to disk."""
        import os
        path = os.path.join(self.storage_path, name, version)
        os.makedirs(path, exist_ok=True)

        with open(os.path.join(path, "model.pkl"), "wb") as f:
            pickle.dump(model, f)

        with open(os.path.join(path, "calibrator.pkl"), "wb") as f:
            pickle.dump(calibrator, f)

        with open(os.path.join(path, "scaler.pkl"), "wb") as f:
            pickle.dump(scaler, f)

    def load(
        self,
        name: str,
        version: str = "latest",
    ) -> dict[str, Any]:
        """
        Load model artifacts.

        Args:
            name: Model name
            version: Version or "latest" for active version

        Returns:
            Dictionary with model, calibrator, scaler, metadata
        """
        if name not in self.models:
            raise ValueError(f"Model {name} not found")

        if version == "latest":
            version = self.active_versions.get(name)
            if not version:
                raise ValueError(f"No active version for {name}")

        if version not in self.models[name]:
            raise ValueError(f"Version {version} not found for {name}")

        metadata = self.models[name][version]
        path = os.path.join(self.storage_path, name, version)

        with open(os.path.join(path, "model.pkl"), "rb") as f:
            model = pickle.load(f)

        with open(os.path.join(path, "calibrator.pkl"), "rb") as f:
            calibrator = pickle.load(f)

        with open(os.path.join(path, "scaler.pkl"), "rb") as f:
            scaler = pickle.load(f)

        return {
            "model": model,
            "calibrator": calibrator,
            "scaler": scaler,
            "metadata": metadata,
        }

    def set_active(
        self,
        name: str,
        version: str,
    ) -> None:
        """Set a version as active."""
        if name not in self.models or version not in self.models[name]:
            raise ValueError(f"Model {name} version {version} not found")

        self.active_versions[name] = version
        self.models[name][version]["status"] = ModelStatus.ACTIVE.value

        # Archive previous active
        for v, meta in self.models[name].items():
            if v != version and meta["status"] == ModelStatus.ACTIVE.value:
                meta["status"] = ModelStatus.ARCHIVED.value
        self._save_index()

    async def get_active_model(self, horizon: str = "1d") -> Optional[dict[str, Any]]:
        """Get active model for horizon, with filesystem fallback."""
        # Try active_versions
        for name, ver in self.active_versions.items():
            if ver and name in self.models and ver in self.models[name]:
                meta = self.models[name][ver].copy()
                import pathlib
                # Add artifact_path if missing
                if "artifact_path" not in meta:
                    meta["artifact_path"] = str(pathlib.Path(self.storage_path) / name / ver / "model.pkl")
                return meta
        # Try any active
        for name, versions in self.models.items():
            for ver, meta in versions.items():
                if meta.get("status") == ModelStatus.ACTIVE.value:
                    m = meta.copy()
                    import pathlib
                    if "artifact_path" not in m:
                        m["artifact_path"] = str(pathlib.Path(self.storage_path) / name / ver / "model.pkl")
                    return m
        # Filesystem fallback for ensemble v1.0
        import pathlib
        candidates = [
            pathlib.Path(__file__).parent.parent.parent / "model_artifacts" / "ensemble" / "v1.0" / "model.pkl",
            pathlib.Path("backend/model_artifacts/ensemble/v1.0/model.pkl"),
            pathlib.Path("model_artifacts/ensemble/v1.0/model.pkl"),
            pathlib.Path(self.storage_path) / "ensemble" / "v1.0" / "model.pkl",
        ]
        for p in candidates:
            if p.exists():
                return {"artifact_path": str(p), "version": "v1.0", "name": "ensemble", "status": "active"}
        return None

    def list_versions(self, name: str) -> list[dict[str, Any]]:
        """List all versions of a model."""
        if name not in self.models:
            return []

        return [
            {
                "version": v,
                "status": meta["status"],
                "metrics": meta["metrics"],
                "created_at": meta["created_at"],
            }
            for v, meta in self.models[name].items()
        ]

    def compare_versions(
        self,
        name: str,
        metric: str = "accuracy",
    ) -> pd.DataFrame:
        """Compare versions by a metric."""
        if name not in self.models:
            return pd.DataFrame()

        rows = []
        for v, meta in self.models[name].items():
            row = {"version": v, "status": meta["status"]}
            row.update(meta["metrics"])
            rows.append(row)

        df = pd.DataFrame(rows)
        if metric in df.columns:
            df = df.sort_values(metric, ascending=False)
        return df


class ModelDriftMonitor:
    """
    Monitor for model and data drift.
    """

    def __init__(
        self,
        reference_features: np.ndarray,
        feature_names: list[str],
        window_size: int = 1000,
        threshold: float = 0.05,
    ):
        self.reference_features = reference_features
        self.feature_names = feature_names
        self.window_size = window_size
        self.threshold = threshold
        self.recent_features = []

    def add_batch(self, features: np.ndarray) -> None:
        """Add new batch of features for drift monitoring."""
        self.recent_features.append(features)
        if len(self.recent_features) > self.window_size:
            self.recent_features = self.recent_features[-self.window_size:]

    def check_drift(self) -> dict[str, Any]:
        """
        Check for feature drift using population stability index (PSI).

        Returns:
            Drift metrics
        """
        if len(self.recent_features) < 100:
            return {"status": "insufficient_data", "drift_detected": False}

        recent = np.vstack(self.recent_features)

        drift_results = {}
        drift_detected = False

        for i, name in enumerate(self.feature_names):
            psi = self._calculate_psi(
                self.reference_features[:, i],
                recent[:, i],
            )
            drift_results[name] = {
                "psi": float(psi),
                "drift": psi > self.threshold,
            }
            if psi > self.threshold:
                drift_detected = True

        return {
            "status": "checked",
            "drift_detected": drift_detected,
            "threshold": self.threshold,
            "features": drift_results,
            "max_psi": float(max(drift_results.values(), key=lambda x: x["psi"])["psi"]),
        }

    def _calculate_psi(
        self,
        expected: np.ndarray,
        actual: np.ndarray,
        buckets: int = 10,
    ) -> float:
        """
        Calculate Population Stability Index.

        PSI = sum((actual_pct - expected_pct) * ln(actual_pct / expected_pct))
        """
        # Create buckets based on expected distribution
        percentiles = np.linspace(0, 100, buckets + 1)
        bin_edges = np.percentile(expected, percentiles)
        bin_edges[0] = -np.inf
        bin_edges[-1] = np.inf

        expected_counts = np.histogram(expected, bins=bin_edges)[0]
        actual_counts = np.histogram(actual, bins=bin_edges)[0]

        # Avoid division by zero
        expected_pct = expected_counts / len(expected)
        actual_pct = actual_counts / len(actual)

        # Replace zeros with small value
        expected_pct = np.where(expected_pct == 0, 0.0001, expected_pct)
        actual_pct = np.where(actual_pct == 0, 0.0001, actual_pct)

        psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
        return psi


class ModelPerformanceTracker:
    """
    Track model performance over time.
    """

    def __init__(self, window_days: int = 30):
        self.window_days = window_days
        self.predictions = []  # (timestamp, symbol, y_true, y_pred, y_prob, metadata)
        self.performance_history = []

    def record_prediction(
        self,
        timestamp: datetime,
        symbol: str,
        y_true: Optional[int],
        y_pred: int,
        y_prob: np.ndarray,
        model_name: str,
        model_version: str,
        horizon: str = "1d",
    ) -> None:
        """Record a prediction for later evaluation."""
        self.predictions.append({
            "timestamp": timestamp,
            "symbol": symbol,
            "y_true": y_true,
            "y_pred": y_pred,
            "y_prob": y_prob,
            "model_name": model_name,
            "model_version": model_version,
            "horizon": horizon,
        })

    def evaluate_pending(self, price_data: dict[str, pd.DataFrame]) -> list[dict]:
        """
        Evaluate predictions that have reached their horizon.

        Args:
            price_data: Dict of symbol -> price DataFrame

        Returns:
            List of evaluation results
        """
        evaluated = []
        remaining = []

        for pred in self.predictions:
            if pred["y_true"] is not None:
                # Already evaluated
                evaluated.append(pred)
                continue

            horizon_days = {"1d": 1, "1w": 5, "1m": 21}.get(pred["horizon"], 1)
            eval_date = pred["timestamp"] + timedelta(days=horizon_days)

            if datetime.now() < eval_date:
                # Not yet due for evaluation
                remaining.append(pred)
                continue

            # Evaluate using price data
            symbol = pred["symbol"]
            if symbol not in price_data:
                remaining.append(pred)
                continue

            prices = price_data[symbol]
            pred_date = pred["timestamp"].date()
            eval_date = eval_date.date()

            # Find closest trading days
            pred_price = prices[prices.index.date == pred_date]
            eval_price = prices[prices.index.date == eval_date]

            if len(pred_price) == 0 or len(eval_price) == 0:
                remaining.append(pred)
                continue

            pred_close = pred_price.iloc[0]["close"]
            eval_close = eval_price.iloc[0]["close"]

            actual_return = (eval_close - pred_close) / pred_close

            # Determine actual direction (shared target thresholds)
            from services.ml.recipe import TARGET_DOWN_THRESHOLD, TARGET_UP_THRESHOLD

            if actual_return > TARGET_UP_THRESHOLD:
                y_true = 2  # UP
            elif actual_return < TARGET_DOWN_THRESHOLD:
                y_true = 0  # DOWN
            else:
                y_true = 1  # NEUTRAL

            pred["y_true"] = y_true
            pred["actual_return"] = float(actual_return)
            pred["evaluated_at"] = datetime.now().isoformat()

            evaluated.append(pred)

        self.predictions = remaining + evaluated
        return evaluated

    def get_performance_summary(
        self,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get performance summary for recent predictions."""
        cutoff = datetime.now() - timedelta(days=days)

        filtered = [
            p for p in self.predictions
            if p["timestamp"] >= cutoff
            and p["y_true"] is not None
            and (model_name is None or p["model_name"] == model_name)
            and (model_version is None or p["model_version"] == model_version)
        ]

        if not filtered:
            return {"status": "no_data", "count": 0}

        y_true = np.array([p["y_true"] for p in filtered])
        y_pred = np.array([p["y_pred"] for p in filtered])
        y_prob = np.array([p["y_prob"] for p in filtered])

        from services.ml.evaluation import ModelEvaluator
        evaluator = ModelEvaluator()
        metrics = evaluator.evaluate_predictions(y_true, y_pred, y_prob)

        metrics["count"] = len(filtered)
        metrics["period_days"] = days

        return metrics


def create_model_training_pipeline(
    instruments_data: dict[str, pd.DataFrame],
    market_data: Optional[pd.DataFrame] = None,
    sector_mapping: Optional[dict[str, pd.DataFrame]] = None,
    reference_date: Optional[datetime] = None,
    target_def: Optional[Any] = None,
    registry: Optional[ModelRegistry] = None,
) -> tuple[ModelTrainer, dict]:
    """
    End-to-end model training pipeline with registry integration.

    Returns:
        (trainer, training_report)
    """
    from services.ml.features import create_feature_matrix
    from services.ml.training import ModelTrainer
    from services.ml.evaluation import WalkForwardEvaluator

    # Create feature matrix
    features = create_feature_matrix(
        instruments_data,
        market_data,
        sector_mapping,
        reference_date,
    )

    # Prepare prices
    prices = pd.concat([
        df.assign(symbol=symbol).set_index("symbol", append=True)
        for symbol, df in instruments_data.items()
    ])[["close"]]

    # Initialize trainer
    trainer = ModelTrainer(target_definition=target_def)

    # Prepare data
    X, y = trainer.prepare_data(features, prices, reference_date)

    # Train with walk-forward
    training_results = trainer.train_walk_forward(X, y)

    # Walk-forward evaluation
    evaluator = WalkForwardEvaluator(n_splits=5)
    eval_results = evaluator.evaluate(trainer, X, y)

    # Training report
    report = {
        "training_date": datetime.now().isoformat(),
        "reference_date": reference_date.isoformat() if reference_date else None,
        "n_samples": len(X),
        "n_features": len(X.columns),
        "feature_names": X.columns.tolist(),
        "class_distribution": y.value_counts().to_dict(),
        "training_results": training_results,
        "evaluation_results": eval_results,
    }

    # Register if registry provided
    if registry:
        for name, model_info in training_results["best_models"].items():
            registry.register(
                name=f"prediction_{name}",
                version=f"v{training_results.get('model_version', 1)}",
                model=model_info["model"],
                calibrator=model_info["calibrator"],
                scaler=model_info["scaler"],
                features=X.columns.tolist(),
                metrics=eval_results["aggregate"],
                training_data_hash="",  # TODO: compute hash
                hyperparameters=model_info["model"].get_params(),
                status=ModelStatus.CANDIDATE,
            )

    return trainer, report