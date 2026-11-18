from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.prediction import (
    Model,
    ModelVersion,
    Prediction,
    PredictionDirection,
    PredictionOutcome,
)
from apps.api.repositories.market import InstrumentRepository
from apps.api.repositories.prediction import (
    ModelRepository,
    ModelVersionRepository,
    PredictionOutcomeRepository,
    PredictionRepository,
)
from services.ml.registry import ModelRegistry


def deduplicate_trading_days(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse multi-provider double-stamped daily bars to one row per day.

    Providers stamp the same trading day at different UTC times (00:00 and
    04:00/05:00 stamps coexist in price_bars). Rolling feature windows
    assume exactly one row per trading day; duplicates halve every window
    (SMA200 over ~100 distinct days) and inject near-identical rows that
    distort rel-volume/volatility statistics vs training data. Keeps the
    latest row per day (freshest provider stamp) in day order.
    """
    if df.empty:
        return df
    days = list(df.index.date)
    if len(set(days)) == len(days):
        return df
    return df.groupby(days, sort=True).tail(1)


class InsufficientDataError(Exception):
    """Raised when insufficient historical data for feature generation."""

    def __init__(self, message: str, required: int = 0, available: int = 0):
        super().__init__(message)
        self.required = required
        self.available = available


class PredictionEngine:
    """Core prediction engine using trained ML models - unified FeaturePipeline."""

    def __init__(self, session: AsyncSession):
        self.session = session
        # IndicatorService kept for UI display only, NOT for ML inference
        try:
            from services.prediction.indicator_service import IndicatorService

            self.indicator_service = IndicatorService(session)
        except Exception:
            self.indicator_service = None  # type: ignore
        try:
            self.model_registry = ModelRegistry()
        except Exception:
            self.model_registry = None

    async def load_active_model(self, horizon: str = "1d") -> Optional[tuple]:
        """Load the active model for the given horizon."""
        model_info = await self.model_registry.get_active_model(horizon)
        if not model_info:
            return None

        model_path = model_info.get("artifact_path")
        if not model_path:
            return None

        try:
            model_data = joblib.load(model_path)
            return (
                model_data.get("model"),
                model_data.get("scaler"),
                model_data.get("features"),
                model_info.get("version"),
                model_info.get("calibrator"),
            )
        except Exception:
            return None

    def _load_filesystem_model(self):
        """Try to load model artifact from filesystem fallback."""
        import pathlib
        # Canonical artifact first (model_artifacts/real/ensemble/v1.0), legacy mirrors after.
        for p in [
            pathlib.Path("model_artifacts/real/ensemble/v1.0/model.pkl"),
            pathlib.Path("backend/model_artifacts/real/ensemble/v1.0/model.pkl"),
            pathlib.Path(__file__).parent.parent.parent / "model_artifacts" / "real" / "ensemble" / "v1.0" / "model.pkl",
            pathlib.Path("model_artifacts/ensemble/v1.0/model.pkl"),
            pathlib.Path("backend/model_artifacts/ensemble/v1.0/model.pkl"),
            pathlib.Path(__file__).parent.parent.parent / "model_artifacts" / "ensemble" / "v1.0" / "model.pkl",
        ]:
            if p.exists():
                try:
                    import joblib
                    data = joblib.load(p)
                    # Support both old and new artifact formats
                    model = data.get("model")
                    scaler = data.get("scaler")
                    # Try 'features' or 'feature_names'
                    feats = data.get("features") or data.get("feature_names") or data.get("features_snapshot")
                    cal = data.get("calibrator")
                    if model is None or scaler is None or feats is None:
                        continue
                    # Reject incompatible artifacts: scaler dims + schema file must agree
                    if hasattr(scaler, "n_features_in_") and scaler.n_features_in_ != len(feats):
                        continue
                    schema_path = p.parent / "feature_schema.json"
                    if schema_path.exists():
                        import json

                        schema = json.loads(schema_path.read_text())
                        if schema.get("feature_names") != list(feats):
                            continue
                    return model, scaler, feats, cal, str(p)
                except Exception:
                    continue
        return None

    async def _extract_unified_features(
        self, instrument_id: UUID, feature_names: list[str], horizon: str = "1d"
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """
        Unified feature extraction using FeaturePipeline (same as training).
        Raises InsufficientDataError if not enough history or missing features.
        Does NOT silently fill with zeros.
        """
        from apps.api.repositories.market import PriceBarRepository
        from services.ml.features import FeaturePipeline

        # Need at least 252 bars for full feature set (SMA200, vol 252 etc)
        required_bars = 252
        # Load recent daily bars
        price_repo = PriceBarRepository(self.session)
        # Get up to 400 most recent bars to ensure enough lookback
        # Use get_range with wide window
        from datetime import timedelta

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=500)  # ~500 calendar days → ~350 trading days
        bars = await price_repo.get_range(instrument_id, "1d", start_date, end_date, limit=400)
        # Fallback to get_latest if get_range returns empty due to timezone mismatch
        if len(bars) < required_bars:
            bars = await price_repo.get_latest(instrument_id, "1d", limit=400)
            bars = sorted(bars, key=lambda b: b.timestamp)

        if len(bars) < required_bars:
            raise InsufficientDataError(
                f"Insufficient historical data: need {required_bars} bars for 87-feature pipeline, have {len(bars)}",
                required=required_bars,
                available=len(bars),
            )

        # Build OHLCV DataFrame indexed by timestamp (must be sorted)
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume),
                    "timestamp": b.timestamp,
                }
                for b in bars
            ]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        # Ensure numeric dtypes
        df = df[["open", "high", "low", "close", "volume"]]

        pipeline = FeaturePipeline(lookback_window=252, min_periods=20)
        features_df = pipeline.compute_all_features(df)

        if features_df.empty:
            raise InsufficientDataError("Feature pipeline returned empty", required=required_bars, available=len(bars))

        # Take latest feature row
        latest = features_df.iloc[-1]
        # Check for NaN or missing in required feature_names
        missing = []
        nan_features = []
        for fname in feature_names:
            if fname not in latest.index:
                missing.append(fname)
            elif pd.isna(latest[fname]):
                nan_features.append(fname)

        if missing:
            raise InsufficientDataError(f"Missing features in pipeline output: {missing[:5]}", required=len(feature_names), available=len(feature_names)-len(missing))
        if nan_features:
            raise InsufficientDataError(
                f"Features NaN due to insufficient lookback ({len(nan_features)} features): {nan_features[:5]}",
                required=required_bars,
                available=len(bars),
            )

        # Build vector in exact feature_names order - no silent zero replacement
        vec = []
        feature_dict = {}
        for fname in feature_names:
            val = latest[fname]
            # Ensure finite
            if not np.isfinite(val):
                raise InsufficientDataError(f"Feature {fname} is non-finite: {val}", required=required_bars, available=len(bars))
            vec.append(float(val))
            feature_dict[fname] = float(val)

        # Also add price/change for snapshot (required by downstream)
        # Use latest close as price
        latest_close = float(df["close"].iloc[-1])
        latest_open = float(df["open"].iloc[-1])
        feature_dict["price"] = latest_close
        feature_dict["change_percent"] = float((latest_close - latest_open) / latest_open * 100) if latest_open != 0 else 0.0

        X = np.array([vec])
        return X, feature_dict

    async def generate_prediction_async(
        self,
        instrument_id: UUID,
        model_version_id: UUID,
        horizon: str,
        features: dict[str, Any],
        artifact_override: Optional[tuple] = None,
    ) -> dict[str, Any]:
        """
        Generate a prediction using the trained ML model asynchronously.
        Unified pipeline: training and inference share identical FeaturePipeline.
        Raises InsufficientDataError if not enough history (no silent zero fill).
        Probabilities always sum to 1.
        """
        # Try filesystem fallback first for ensemble v1.0 - unified pipeline
        if artifact_override is not None:
            fs_model = artifact_override
        else:
            fs_model = self._load_filesystem_model()
        if fs_model is not None:
            model, scaler, feature_names, calibrator, _ = fs_model
            try:
                # Validate scaler dimensions match feature_names
                if hasattr(scaler, "n_features_in_") and scaler.n_features_in_ != len(feature_names):
                    raise ValueError(
                        f"Scaler feature mismatch: scaler expects {scaler.n_features_in_}, artifact has {len(feature_names)}"
                    )
                # Extract features via unified pipeline (no silent zeros)
                X, feature_dict = await self._extract_unified_features(instrument_id, feature_names, horizon)
                if X.shape[1] != len(feature_names):
                    raise ValueError(f"Feature dim {X.shape[1]} != expected {len(feature_names)}")
                X_df = pd.DataFrame(X, columns=feature_names)
                X_scaled = scaler.transform(X_df)
                X_pred = pd.DataFrame(X_scaled, columns=feature_names)
                # Use calibrator if available, else model
                if calibrator is not None and hasattr(calibrator, "predict_proba"):
                    probs = calibrator.predict_proba(X_pred)[0]
                else:
                    probs = model.predict_proba(X_pred)[0]
                # Map 3-class: assume 0=DOWN,1=NEUTRAL,2=UP
                if len(probs) == 3:
                    down_prob, neutral_prob, up_prob = float(probs[0]), float(probs[1]), float(probs[2])
                elif len(probs) == 2:
                    down_prob, up_prob = float(probs[0]), float(probs[1])
                    neutral_prob = max(0.0, 1.0 - down_prob - up_prob)
                else:
                    raise ValueError("Unexpected prob length")
                from services.ml import recipe as _recipe

                up_prob, neutral_prob, down_prob = _recipe.normalize_probs(up_prob, neutral_prob, down_prob)
                direction = PredictionDirection(_recipe.direction_from_probs(up_prob, neutral_prob, down_prob))
                # NO CLEAR EDGE if separation low (quantify uncertainty)
                max_prob = max(up_prob, neutral_prob, down_prob)
                # Use realized vol from unified features for range
                vol = feature_dict.get("realized_vol_20d", feature_dict.get("realized_vol_10d", 20.0))
                try:
                    vol_factor = float(vol) / 100 if vol is not None else 0.2
                except Exception:
                    vol_factor = 0.2
                vol_factor = min(max(vol_factor, 0.01), 0.5)
                expected_return = float(up_prob - down_prob) * 2.0
                if direction == PredictionDirection.UP:
                    range_lower = Decimal(str(-vol_factor * 0.5))
                    range_upper = Decimal(str(vol_factor * 1.5))
                elif direction == PredictionDirection.DOWN:
                    range_lower = Decimal(str(-vol_factor * 1.5))
                    range_upper = Decimal(str(vol_factor * 0.5))
                else:
                    range_lower = Decimal(str(-vol_factor))
                    range_upper = Decimal(str(vol_factor))
                confidence = _recipe.confidence_from_probs(up_prob, down_prob, max_prob)
                return {
                    "predicted_direction": direction,
                    "up_probability": Decimal(str(up_prob)).quantize(Decimal("0.0001")),
                    "neutral_probability": Decimal(str(neutral_prob)).quantize(Decimal("0.0001")),
                    "down_probability": Decimal(str(down_prob)).quantize(Decimal("0.0001")),
                    "expected_return": Decimal(str(expected_return)).quantize(Decimal("0.0001")),
                    "range_lower": Decimal(str(range_lower)).quantize(Decimal("0.0001")),
                    "range_upper": Decimal(str(range_upper)).quantize(Decimal("0.0001")),
                    "confidence": confidence,
                    "_feature_dict": feature_dict,  # internal for snapshot
                    "_prob_max": max_prob,
                    "_no_edge": not _recipe.has_clear_edge(up_prob, neutral_prob, down_prob),
                }
            except InsufficientDataError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(f"Filesystem model inference failed: {e}")
                raise

        # DB model path - also unified
        if self.model_registry is None:
            raise InsufficientDataError("No model registry available")
        model_info = await self.model_registry.get_active_model(horizon)
        if not model_info:
            raise InsufficientDataError("No active model for horizon")
        model_path = model_info.get("artifact_path")
        if not model_path:
            raise InsufficientDataError("Model artifact path missing")
        try:
            model_data = joblib.load(model_path)
            model = model_data.get("model")
            scaler = model_data.get("scaler")
            feature_names = model_data.get("features") or model_data.get("feature_names")
            calibrator = model_data.get("calibrator")
            if model is None or scaler is None or feature_names is None:
                raise InsufficientDataError("Model artifacts incomplete")
            if hasattr(scaler, "n_features_in_") and scaler.n_features_in_ != len(feature_names):
                raise ValueError("Scaler dim mismatch")
            X, feature_dict = await self._extract_unified_features(instrument_id, feature_names, horizon)
            X_df = pd.DataFrame(X, columns=feature_names)
            X_scaled = scaler.transform(X_df)
            X_pred = pd.DataFrame(X_scaled, columns=feature_names)
            if calibrator is not None and hasattr(calibrator, "predict_proba"):
                probs = calibrator.predict_proba(X_pred)[0]
            else:
                probs = model.predict_proba(X_pred)[0]
            if len(probs) == 3:
                down_prob, neutral_prob, up_prob = float(probs[0]), float(probs[1]), float(probs[2])
            elif len(probs) == 2:
                down_prob, up_prob = float(probs[0]), float(probs[1])
                neutral_prob = max(0.0, 1.0 - down_prob - up_prob)
            else:
                raise ValueError("Unexpected prob length")
            from services.ml import recipe as _recipe

            up_prob, neutral_prob, down_prob = _recipe.normalize_probs(up_prob, neutral_prob, down_prob)
            direction = PredictionDirection(_recipe.direction_from_probs(up_prob, neutral_prob, down_prob))
            vol = feature_dict.get("realized_vol_20d", 20.0)
            vol_factor = float(vol) / 100 if vol is not None else 0.2
            vol_factor = min(max(vol_factor, 0.01), 0.5)
            expected_return = float(up_prob - down_prob) * 2.0
            if direction == PredictionDirection.UP:
                range_lower = Decimal(str(-vol_factor * 0.5))
                range_upper = Decimal(str(vol_factor * 1.5))
            elif direction == PredictionDirection.DOWN:
                range_lower = Decimal(str(-vol_factor * 1.5))
                range_upper = Decimal(str(vol_factor * 0.5))
            else:
                range_lower = Decimal(str(-vol_factor))
                range_upper = Decimal(str(vol_factor))
            max_prob = max(up_prob, neutral_prob, down_prob)
            confidence = _recipe.confidence_from_probs(up_prob, down_prob, max_prob)
            return {
                "predicted_direction": direction,
                "up_probability": Decimal(str(up_prob)).quantize(Decimal("0.0001")),
                "neutral_probability": Decimal(str(neutral_prob)).quantize(Decimal("0.0001")),
                "down_probability": Decimal(str(down_prob)).quantize(Decimal("0.0001")),
                "expected_return": Decimal(str(expected_return)).quantize(Decimal("0.0001")),
                "range_lower": Decimal(str(range_lower)).quantize(Decimal("0.0001")),
                "range_upper": Decimal(str(range_upper)).quantize(Decimal("0.0001")),
                "confidence": confidence,
                "_feature_dict": feature_dict,
                "_prob_max": max_prob,
                "_no_edge": not _recipe.has_clear_edge(up_prob, neutral_prob, down_prob),
            }
        except InsufficientDataError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Model inference failed: {e}")
            raise InsufficientDataError(f"Model inference failed: {e}")

    def _generate_heuristic_prediction(self, features: dict[str, Any]) -> dict[str, Any]:
        """Fallback heuristic prediction when model is unavailable."""
        rsi = features.get("rsi_14", 50)
        macd = features.get("macd", {})
        macd_hist = macd.get("histogram", 0) if isinstance(macd, dict) else 0
        trend = features.get("sma_20", 0) - features.get("sma_50", 0) if features.get("sma_20") and features.get("sma_50") else 0
        rel_volume = features.get("relative_volume_20", 1.0)
        volatility = features.get("volatility_20", 20.0)

        bullish_signals = 0
        bearish_signals = 0

        if rsi < 30:
            bullish_signals += 1
        elif rsi > 70:
            bearish_signals += 1

        if macd_hist > 0:
            bullish_signals += 1
        elif macd_hist < 0:
            bearish_signals += 1

        if trend > 0:
            bullish_signals += 1
        elif trend < 0:
            bearish_signals += 1

        if rel_volume > 1.5:
            if bullish_signals > bearish_signals:
                bullish_signals += 1
            elif bearish_signals > bullish_signals:
                bearish_signals += 1

        total_signals = bullish_signals + bearish_signals
        if total_signals == 0:
            up_prob = neutral_prob = down_prob = Decimal("0.333")
            direction = PredictionDirection.NEUTRAL
        else:
            up_prob = Decimal(str(bullish_signals / total_signals * 0.7 + 0.15))
            down_prob = Decimal(str(bearish_signals / total_signals * 0.7 + 0.15))
            neutral_prob = Decimal("1") - up_prob - down_prob

            if up_prob > down_prob and up_prob > neutral_prob:
                direction = PredictionDirection.UP
            elif down_prob > up_prob and down_prob > neutral_prob:
                direction = PredictionDirection.DOWN
            else:
                direction = PredictionDirection.NEUTRAL

        total = up_prob + neutral_prob + down_prob
        up_prob = up_prob / total
        neutral_prob = neutral_prob / total
        down_prob = down_prob / total

        vol_factor = float(volatility) / 100
        if direction == PredictionDirection.UP:
            expected_return = Decimal(str(vol_factor * 0.5))
            range_lower = Decimal(str(-vol_factor * 0.5))
            range_upper = Decimal(str(vol_factor * 1.5))
        elif direction == PredictionDirection.DOWN:
            expected_return = Decimal(str(-vol_factor * 0.5))
            range_lower = Decimal(str(-vol_factor * 1.5))
            range_upper = Decimal(str(vol_factor * 0.5))
        else:
            expected_return = Decimal("0")
            range_lower = Decimal(str(-vol_factor))
            range_upper = Decimal(str(vol_factor))

        signal_strength = abs(bullish_signals - bearish_signals) / max(total_signals, 1)
        confidence = int(50 + signal_strength * 40)

        return {
            "predicted_direction": direction,
            "up_probability": up_prob.quantize(Decimal("0.0001")),
            "neutral_probability": neutral_prob.quantize(Decimal("0.0001")),
            "down_probability": down_prob.quantize(Decimal("0.0001")),
            "expected_return": expected_return.quantize(Decimal("0.0001")),
            "range_lower": range_lower.quantize(Decimal("0.0001")),
            "range_upper": range_upper.quantize(Decimal("0.0001")),
            "confidence": confidence,
        }


class PredictionService:
    """Prediction service for managing predictions."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.engine = PredictionEngine(session)
        self.model_repo = ModelRepository(session)
        self.model_version_repo = ModelVersionRepository(session)
        self.prediction_repo = PredictionRepository(session)
        self.outcome_repo = PredictionOutcomeRepository(session)
        self.instrument_repo = InstrumentRepository(session)

    async def get_or_create_model(self, name: str = "Ensemble") -> Model:
        """Get or create default model."""
        model = await self.model_repo.get_by_name(name)
        if not model:
            model = await self.model_repo.create(
                name=name,
                description="Ensemble prediction model",
                model_type="ensemble",
            )
        return model

    async def get_active_model_version(self, model_id: UUID) -> ModelVersion:
        """Get active model version."""
        version = await self.model_version_repo.get_latest_active(model_id)
        if not version:
            version = await self.model_version_repo.create(
                model_id=model_id,
                version=settings.prediction_model_version,
                description="Default model version",
            )
        return version

    async def generate_prediction(
        self,
        instrument_id: UUID,
        horizon: str = "1d",
        model_version_id: Optional[UUID] = None,
    ) -> Prediction:
        """Generate and persist a prediction using the trained model."""
        # Get model version
        if model_version_id is None:
            champ_version_id = await self.prediction_repo._champion_version_id()
            if champ_version_id:
                model_version_id = champ_version_id
            else:
                model = await self.get_or_create_model()
                version = await self.get_active_model_version(model.id)
                model_version_id = version.id

        # Get instrument
        instrument = await self.instrument_repo.get(instrument_id)
        if not instrument:
            raise ValueError("Instrument not found")

        # Generate prediction using unified FeaturePipeline (training == inference)
        # Do NOT use IndicatorService for ML inference - unified path ensures identical features
        pred_data = await self.engine.generate_prediction_async(
            instrument_id, model_version_id, horizon, {}
        )

        # Bar identity determines the point-in-time data timestamp. Inference
        # may be re-run on the same closed bar, but the persisted record must
        # be keyed to that bar — never to wall-clock now (PIT) — so that
        # re-running inference cannot double-count the same trading day.
        bar_ts = pred_data.get("_data_timestamp") or datetime.now(UTC)

        # Idempotency: one instrument/horizon/model/bar yields exactly one
        # production prediction (get_for_bar dedupes by bar identity).
        existing = await self.prediction_repo.get_for_bar(
            instrument_id, horizon, model_version_id, bar_ts
        )
        if existing is not None:
            return existing

        # Use unified feature dict from engine for snapshot (contains 87 features + price)
        features = pred_data.pop("_feature_dict", {})
        # Also pop internal flags but keep for snapshot if needed
        pred_data.pop("_prob_max", None)
        pred_data.pop("_no_edge", None)

        # Sanitize features for JSON serialization (Decimal -> float, nested dicts)
        def _sanitize(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_sanitize(v) for v in obj]
            return obj

        features_json = _sanitize(features)

        # Create prediction
        prediction = await self.prediction_repo.create_prediction(
            instrument_id=instrument_id,
            model_version_id=model_version_id,
            horizon=horizon,
            predicted_direction=pred_data["predicted_direction"],
            up_probability=pred_data["up_probability"],
            neutral_probability=pred_data["neutral_probability"],
            down_probability=pred_data["down_probability"],
            expected_return=pred_data["expected_return"],
            range_lower=pred_data["range_lower"],
            range_upper=pred_data["range_upper"],
            confidence=pred_data["confidence"],
            prediction_timestamp=bar_ts,
            data_timestamp=bar_ts,
            features_snapshot=features_json,
        )

        return prediction

    async def generate_predictions_batch(
        self,
        instrument_ids: list[UUID],
        horizon: str = "1d",
        model_version_id: Optional[UUID] = None,
    ) -> list[Prediction]:
        """Generate predictions for multiple instruments."""
        predictions = []
        for instrument_id in instrument_ids:
            try:
                pred = await self.generate_prediction(
                    instrument_id, horizon, model_version_id
                )
                predictions.append(pred)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to generate prediction for {instrument_id}: {e}")
        return predictions

    async def get_latest_prediction(
        self,
        instrument_id: UUID,
        horizon: str = "1d",
    ) -> Optional[Prediction]:
        """Get latest prediction for an instrument."""
        return await self.prediction_repo.get_latest_for_instrument(
            instrument_id, horizon
        )

    async def get_prediction_history(
        self,
        instrument_id: UUID,
        horizon: str = "1d",
        limit: int = 100,
    ) -> list[Prediction]:
        """Get prediction history for an instrument."""
        return await self.prediction_repo.get_history(instrument_id, horizon, limit=limit)

    async def evaluate_pending_predictions(
        self, horizon: str = "1d"
    ) -> dict[str, int]:
        """Evaluate predictions that have reached their horizon."""
        pending = await self.prediction_repo.get_pending_outcomes(horizon)
        evaluated = 0
        errors = 0

        for prediction in pending:
            try:
                # Get actual price at evaluation time
                from apps.api.repositories.market import MarketSnapshotRepository
                snapshot_repo = MarketSnapshotRepository(self.session)
                snapshot = await snapshot_repo.get_latest(prediction.instrument_id)

                if not snapshot:
                    continue

                await self.evaluate_prediction(
                    prediction=prediction,
                    evaluation_price=snapshot.price,
                    evaluation_timestamp=datetime.now(UTC),
                )
                evaluated += 1
            except Exception as e:
                errors += 1
                import logging
                logging.getLogger(__name__).warning(f"Failed to evaluate prediction {prediction.id}: {e}")

        return {"evaluated": evaluated, "errors": errors}

    async def evaluate_prediction(
        self,
        prediction: Prediction,
        evaluation_price: Decimal,
        evaluation_timestamp: datetime,
    ) -> PredictionOutcome:
        """Evaluate a single prediction."""
        # Calculate actual return
        predicted_price = prediction.features_snapshot.get("price", evaluation_price)
        if isinstance(predicted_price, (int, float, str)):
            predicted_price = Decimal(str(predicted_price))

        actual_return = (
            (evaluation_price - predicted_price) / predicted_price * 100
        ).quantize(Decimal("0.0001"))

        # Determine actual direction
        if actual_return > Decimal("0.5"):
            actual_direction = PredictionDirection.UP
        elif actual_return < Decimal("-0.5"):
            actual_direction = PredictionDirection.DOWN
        else:
            actual_direction = PredictionDirection.NEUTRAL

        outcome = await self.outcome_repo.evaluate_prediction(
            prediction=prediction,
            actual_return=actual_return,
            actual_direction=actual_direction,
            evaluation_price=evaluation_price,
            evaluation_timestamp=evaluation_timestamp,
        )

        return outcome