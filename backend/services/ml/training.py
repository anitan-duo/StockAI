from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler

from services.ml.target import TargetDirection, TargetDefinition, compute_target_series
from services.ml.features import create_feature_matrix


class WalkForwardSplitter:
    """
    Walk-forward cross-validation splitter.

    Ensures no future data leaks into training.
    """

    def __init__(
        self,
        n_splits: int = 5,
        train_size_months: int = 24,
        test_size_months: int = 3,
        gap_months: int = 1,
        min_train_size: int = 100,
    ):
        self.n_splits = n_splits
        self.train_size = train_size_months
        self.test_size = test_size_months
        self.gap = gap_months
        self.min_train_size = min_train_size

    def split(
        self,
        X: pd.DataFrame,
        y: Optional[pd.Series] = None,
        groups: Optional[pd.Series] = None,
    ):
        """
        Generate train/test indices for walk-forward validation.

        If groups (symbols) provided, ensure each symbol has enough data.
        """
        dates = X.index.get_level_values("date") if isinstance(X.index, pd.MultiIndex) else X.index
        unique_dates = np.sort(dates.unique())

        if len(unique_dates) < self.train_size + self.gap + self.test_size:
            raise ValueError("Insufficient data for walk-forward splits")

        # Calculate split boundaries - calendar-aware
        total_months = (pd.Timestamp(unique_dates[-1]) - pd.Timestamp(unique_dates[0])).days / 30.44
        if total_months <= 0:
            total_months = len(unique_dates) / 30.44 * 30  # fallback
        months_per_split = (total_months - self.train_size - self.gap) / self.n_splits if self.n_splits > 0 else 0

        for i in range(self.n_splits):
            test_start_idx = int(self.train_size / total_months * len(unique_dates)) + i * int(months_per_split / total_months * len(unique_dates))
            gap_end_idx = test_start_idx + int(self.gap / total_months * len(unique_dates))
            test_end_idx = min(gap_end_idx + int(self.test_size / total_months * len(unique_dates)), len(unique_dates))

            if test_end_idx > len(unique_dates):
                break

            train_dates = unique_dates[:test_start_idx]
            test_dates = unique_dates[gap_end_idx:test_end_idx]

            if len(train_dates) < self.min_train_size:
                continue

            train_mask = dates.isin(train_dates)
            test_mask = dates.isin(test_dates)

            yield np.where(train_mask)[0], np.where(test_mask)[0]


class ModelTrainer:
    """
    Model training with walk-forward validation and calibration.
    """

    def __init__(
        self,
        target_definition: Optional[TargetDefinition] = None,
        calibration_method: str = "isotonic",
        n_calibration_folds: int = 3,
        random_state: int = 42,
    ):
        from services.ml import recipe

        assert calibration_method == recipe.CALIBRATION_METHOD
        assert n_calibration_folds == recipe.CALIBRATION_CV_FOLDS
        assert random_state == recipe.RANDOM_STATE
        self.target_def = target_definition or TargetDefinition()
        self.calibration_method = calibration_method
        self.n_calibration_folds = n_calibration_folds
        self.random_state = random_state
        self.models = {}
        self.calibrators = {}
        self.scaler = StandardScaler()
        self.feature_names = None

    def get_base_models(self) -> dict[str, BaseEstimator]:
        """Get base model configurations (single-sourced from services.ml.recipe)."""
        from services.ml import recipe

        return recipe.get_base_models(random_state=self.random_state)

    def prepare_data(
        self,
        features: pd.DataFrame,
        prices: pd.DataFrame,
        reference_date: Optional[datetime] = None,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """
        Prepare features and targets for training.

        Args:
            features: Feature matrix (symbol, date) -> features
            prices: Price data with close prices
            reference_date: Optional cutoff date

        Returns:
            X, y
        """
        # Compute targets
        target_def = self.target_def
        targets = []

        for symbol in prices.index.get_level_values("symbol").unique():
            symbol_prices = prices.xs(symbol, level="symbol")["close"]
            symbol_targets = compute_target_series(symbol_prices, target_def)
            symbol_targets.name = "target"
            symbol_targets.index = pd.MultiIndex.from_tuples(
                [(symbol, d) for d in symbol_targets.index],
                names=["symbol", "date"]
            )
            targets.append(symbol_targets)

        if not targets:
            return pd.DataFrame(), pd.Series(dtype=object)

        y = pd.concat(targets)

        # Align features and targets
        common_idx = features.index.intersection(y.index)
        X = features.loc[common_idx]
        y_aligned = y.loc[common_idx]

        # Remove rows with NaN targets
        valid_mask = ~y_aligned.isna()
        X = X[valid_mask]
        y = y_aligned[valid_mask]

        # Convert target to numeric
        target_map = {
            TargetDirection.DOWN: 0,
            TargetDirection.NEUTRAL: 1,
            TargetDirection.UP: 2,
        }
        y_numeric = y.map(target_map)

        return X, y_numeric

    def train_walk_forward(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        n_splits: int = 5,
    ) -> dict[str, Any]:
        """
        Train models using walk-forward validation.

        Returns:
            Dictionary with trained models, calibration, and metrics
        """
        self.feature_names = X.columns.tolist()

        # Walk-forward splitter - adaptive for small datasets
        # If data spans < 28 months (24 train +1 gap +3 test), use smaller windows
        dates_tmp = X.index.get_level_values("date") if isinstance(X.index, pd.MultiIndex) else X.index
        unique_tmp = dates_tmp.unique()
        total_months_tmp = (unique_tmp.max() - unique_tmp.min()).days / 30.44 if len(unique_tmp) > 1 else 12
        if total_months_tmp < 28:
            # Small dataset: 3 months train, 1 month test, 1 month gap (preserve leakage gap)
            splitter = WalkForwardSplitter(n_splits=n_splits, train_size_months=3, test_size_months=1, gap_months=1, min_train_size=50)
        else:
            splitter = WalkForwardSplitter(n_splits=n_splits)

        # Results storage
        model_scores = {name: [] for name in self.get_base_models()}
        calibrated_scores = {name: [] for name in self.get_base_models()}
        brier_scores = {name: [] for name in self.get_base_models()}
        logloss_scores = {name: [] for name in self.get_base_models()}
        baseline_scores: list[float] = []

        # Store best models
        best_models = {}

        for fold, (train_idx, test_idx) in enumerate(splitter.split(X, y)):
            X_train_raw, X_test_raw = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            if len(np.unique(y_train)) < 2:
                continue

            # Majority-class baseline for this fold (fair comparison reference)
            majority = pd.Series(y_train).value_counts().idxmax()
            baseline_scores.append(float((y_test == majority).mean()))

            # Leakage prevention: fit scaler strictly on training dataset for this fold
            fold_scaler = StandardScaler()
            X_train = pd.DataFrame(fold_scaler.fit_transform(X_train_raw), index=X_train_raw.index, columns=X_train_raw.columns)
            X_test = pd.DataFrame(fold_scaler.transform(X_test_raw), index=X_test_raw.index, columns=X_test_raw.columns)

            fold_models = {}

            for name, base_model in self.get_base_models().items():
                # Train base model
                model = base_model.__class__(**base_model.get_params())
                model.fit(X_train, y_train)

                # Calibrate
                calibrator = CalibratedClassifierCV(
                    model,
                    method=self.calibration_method,
                    cv=self.n_calibration_folds,
                )
                calibrator.fit(X_train, y_train)

                # Evaluate
                from sklearn.metrics import accuracy_score, log_loss, brier_score_loss

                # Base model predictions
                y_pred = model.predict(X_test)
                base_acc = accuracy_score(y_test, y_pred)

                # Calibrated predictions
                y_cal_prob = calibrator.predict_proba(X_test)
                y_cal_pred = calibrator.predict(X_test)
                cal_acc = accuracy_score(y_test, y_cal_pred)
                cal_brier = brier_score_loss(
                    (y_test == 2).astype(int),
                    y_cal_prob[:, 2] if y_cal_prob.shape[1] > 2 else y_cal_prob[:, 1]
                )
                cal_logloss = log_loss(y_test, y_cal_prob, labels=[0, 1, 2])

                model_scores[name].append(base_acc)
                calibrated_scores[name].append(cal_acc)
                brier_scores[name].append(float(cal_brier))
                logloss_scores[name].append(float(cal_logloss))
                fold_models[name] = {"model": model, "calibrator": calibrator}

                # Store calibrator for this fold
                if name not in self.calibrators:
                    self.calibrators[name] = []
                self.calibrators[name].append(calibrator)

                # Store best model (by calibrated accuracy)
                if name not in best_models or cal_acc > best_models[name]["score"]:
                    best_models[name] = {
                        "model": model,
                        "calibrator": calibrator,
                        "scaler": fold_scaler,
                        "score": cal_acc,
                        "fold": fold,
                    }

        # Final training on all data for production - fit production scaler on full dataset
        self.scaler = StandardScaler()
        X_full_scaled = pd.DataFrame(self.scaler.fit_transform(X), index=X.index, columns=X.columns)

        for name, base_model in self.get_base_models().items():
            model = base_model.__class__(**base_model.get_params())
            model.fit(X_full_scaled, y)

            calibrator = CalibratedClassifierCV(
                model,
                method=self.calibration_method,
                cv=self.n_calibration_folds,
            )
            calibrator.fit(X_full_scaled, y)

            self.models[name] = model
            self.calibrators[name] = [calibrator]

        return {
            "models": self.models,
            "calibrators": self.calibrators,
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "fold_scores": model_scores,
            "calibrated_scores": calibrated_scores,
            "brier_scores": brier_scores,
            "logloss_scores": logloss_scores,
            "baseline_scores": {"majority_class": baseline_scores},
            "best_models": best_models,
        }

    def predict(
        self,
        X: pd.DataFrame,
        model_name: str = "ensemble",
    ) -> dict[str, np.ndarray]:
        """
        Generate predictions using trained models.

        Returns:
            Dictionary with probabilities and predictions
        """
        X_scaled = self.scaler.transform(X[self.feature_names])
        X_pred = pd.DataFrame(X_scaled, columns=self.feature_names)

        if model_name == "ensemble":
            # Average calibrated probabilities across models
            all_probs = []
            for name, calibrators in self.calibrators.items():
                for cal in calibrators:
                    prob = cal.predict_proba(X_pred)
                    all_probs.append(prob)

            if not all_probs:
                raise ValueError("No trained models available")

            avg_probs = np.mean(all_probs, axis=0)
            preds = np.argmax(avg_probs, axis=1)

            return {
                "probabilities": avg_probs,
                "predictions": preds,
                "individual_probs": all_probs,
            }
        else:
            if model_name not in self.calibrators:
                raise ValueError(f"Model {model_name} not found")

            calibrator = self.calibrators[model_name][0]
            probs = calibrator.predict_proba(X_pred)
            preds = calibrator.predict(X_pred)

            return {
                "probabilities": probs,
                "predictions": preds,
            }

    def predict_proba(
        self,
        X: pd.DataFrame,
        model_name: str = "ensemble",
    ) -> np.ndarray:
        """Get calibrated probabilities."""
        result = self.predict(X, model_name)
        return result["probabilities"]

    def get_feature_importance(self, model_name: str = "random_forest") -> pd.Series:
        """Get feature importance from a model."""
        if model_name not in self.models:
            raise ValueError(f"Model {model_name} not trained")

        model = self.models[model_name]
        if hasattr(model, "feature_importances_"):
            return pd.Series(
                model.feature_importances_,
                index=self.feature_names,
            ).sort_values(ascending=False)

        if hasattr(model, "coef_"):
            return pd.Series(
                np.abs(model.coef_).mean(axis=0),
                index=self.feature_names,
            ).sort_values(ascending=False)

        return pd.Series()


def create_training_pipeline(
    instruments_data: dict[str, pd.DataFrame],
    prices_data: dict[str, pd.DataFrame],
    market_data: Optional[pd.DataFrame] = None,
    sector_mapping: Optional[dict[str, pd.DataFrame]] = None,
    reference_date: Optional[datetime] = None,
    target_def: Optional[TargetDefinition] = None,
) -> ModelTrainer:
    """
    Create complete training pipeline from raw data.

    Args:
        instruments_data: Dict of symbol -> OHLCV DataFrame
        prices_data: Dict of symbol -> close price DataFrame (for target computation)
        market_data: Optional market index data
        sector_mapping: Optional sector data per symbol
        reference_date: Training cutoff date
        target_def: Target definition

    Returns:
        Trained ModelTrainer
    """
    # Create feature matrix
    features = create_feature_matrix(
        instruments_data,
        market_data,
        sector_mapping,
        reference_date,
    )

    # Prepare prices for target
    prices = pd.concat([
        df.assign(symbol=symbol).set_index("symbol", append=True)
        for symbol, df in prices_data.items()
    ])

    # Initialize trainer
    trainer = ModelTrainer(target_definition=target_def)

    # Prepare data
    X, y = trainer.prepare_data(features, prices, reference_date)

    # Train
    trainer.train_walk_forward(X, y)

    return trainer