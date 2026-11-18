from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    log_loss,
    brier_score_loss,
    confusion_matrix,
    classification_report,
)
from sklearn.calibration import calibration_curve
from sklearn.model_selection import TimeSeriesSplit


class ModelEvaluator:
    """
    Comprehensive model evaluation with financial metrics.
    """

    def __init__(
        self,
        target_definition=None,
    ):
        self.target_def = target_definition

    def evaluate_predictions(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: np.ndarray,
    ) -> dict[str, float]:
        """
        Evaluate predictions with classification metrics.

        Args:
            y_true: True labels (0=DOWN, 1=NEUTRAL, 2=UP)
            y_pred: Predicted labels
            y_prob: Predicted probabilities [n_samples, 3]

        Returns:
            Dictionary of metrics
        """
        metrics = {}

        # Basic classification metrics
        metrics["accuracy"] = accuracy_score(y_true, y_pred)
        metrics["precision_macro"] = precision_score(y_true, y_pred, average="macro", zero_division=0)
        metrics["recall_macro"] = recall_score(y_true, y_pred, average="macro", zero_division=0)
        metrics["f1_macro"] = f1_score(y_true, y_pred, average="macro", zero_division=0)

        # Per-class metrics
        for i, label in enumerate(["DOWN", "NEUTRAL", "UP"]):
            metrics[f"precision_{label.lower()}"] = precision_score(y_true, y_pred, labels=[i], average="macro", zero_division=0)
            metrics[f"recall_{label.lower()}"] = recall_score(y_true, y_pred, labels=[i], average="macro", zero_division=0)
            metrics[f"f1_{label.lower()}"] = f1_score(y_true, y_pred, labels=[i], average="macro", zero_division=0)

        # ROC-AUC (one-vs-rest)
        try:
            metrics["roc_auc_ovr"] = roc_auc_score(y_true, y_prob, multi_class="ovr", average="macro")
            metrics["roc_auc_ovo"] = roc_auc_score(y_true, y_prob, multi_class="ovo", average="macro")
        except ValueError:
            metrics["roc_auc_ovr"] = np.nan
            metrics["roc_auc_ovo"] = np.nan

        # Log loss
        metrics["log_loss"] = log_loss(y_true, y_prob)

        # Brier score (per class)
        for i, label in enumerate(["DOWN", "NEUTRAL", "UP"]):
            y_binary = (y_true == i).astype(int)
            if y_prob.shape[1] > i:
                metrics[f"brier_score_{label.lower()}"] = brier_score_loss(y_binary, y_prob[:, i])

        metrics["brier_score_overall"] = np.mean([
            metrics.get(f"brier_score_{label.lower()}", np.nan)
            for label in ["DOWN", "NEUTRAL", "UP"]
        ])

        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])
        metrics["confusion_matrix"] = cm.tolist()

        return metrics

    def evaluate_calibration(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        n_bins: int = 10,
    ) -> dict[str, Any]:
        """
        Evaluate probability calibration.

        Returns:
            Dictionary with calibration metrics and curves
        """
        calibration_results = {}

        for i, label in enumerate(["DOWN", "NEUTRAL", "UP"]):
            y_binary = (y_true == i).astype(int)

            if y_prob.shape[1] <= i:
                continue

            prob_true, prob_pred = calibration_curve(
                y_binary,
                y_prob[:, i],
                n_bins=n_bins,
                strategy="uniform",
            )

            # Expected Calibration Error (ECE)
            bin_counts = np.histogram(y_prob[:, i], bins=n_bins, range=(0, 1))[0]
            ece = np.sum(np.abs(prob_true - prob_pred) * bin_counts) / len(y_binary)

            calibration_results[label.lower()] = {
                "prob_true": prob_true.tolist(),
                "prob_pred": prob_pred.tolist(),
                "ece": float(ece),
                "bin_counts": bin_counts.tolist(),
            }

        # Overall ECE
        eces = [v["ece"] for v in calibration_results.values()]
        calibration_results["overall_ece"] = float(np.mean(eces))

        return calibration_results

    def evaluate_financial_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: np.ndarray,
        actual_returns: np.ndarray,
        predicted_returns: Optional[np.ndarray] = None,
        predicted_ranges: Optional[np.ndarray] = None,
    ) -> dict[str, float]:
        """
        Evaluate financial performance of predictions.

        Args:
            y_true: True direction labels
            y_pred: Predicted directions
            y_prob: Prediction probabilities
            actual_returns: Actual returns (percentage)
            predicted_returns: Expected returns from model
            predicted_ranges: (lower, upper) prediction intervals

        Returns:
            Financial metrics
        """
        metrics = {}

        # Directional accuracy
        metrics["directional_accuracy"] = accuracy_score(y_true, y_pred)

        # Profitability metrics (assuming equal position sizing)
        # Correct directional prediction = profit, incorrect = loss
        correct_mask = y_true == y_pred
        returns_if_correct = np.abs(actual_returns[correct_mask])
        returns_if_incorrect = -np.abs(actual_returns[~correct_mask])

        all_returns = np.zeros_like(actual_returns)
        all_returns[correct_mask] = returns_if_correct
        all_returns[~correct_mask] = returns_if_incorrect

        metrics["mean_return_per_trade"] = float(np.mean(all_returns))
        metrics["win_rate"] = float(np.mean(correct_mask))
        metrics["profit_factor"] = float(
            np.sum(returns_if_correct) / abs(np.sum(returns_if_incorrect))
            if np.sum(returns_if_incorrect) != 0 else np.inf
        )

        # Expected vs actual returns
        if predicted_returns is not None:
            metrics["return_mae"] = float(np.mean(np.abs(predicted_returns - actual_returns)))
            metrics["return_rmse"] = float(np.sqrt(np.mean((predicted_returns - actual_returns) ** 2)))

        # Range coverage
        if predicted_ranges is not None:
            lower, upper = predicted_ranges[:, 0], predicted_ranges[:, 1]
            in_range = (actual_returns >= lower) & (actual_returns <= upper)
            metrics["range_coverage"] = float(np.mean(in_range))
            metrics["avg_range_width"] = float(np.mean(upper - lower))

        # Probability-weighted returns
        # Weight returns by model confidence
        max_probs = np.max(y_prob, axis=1)
        weighted_returns = actual_returns * (2 * max_probs - 1)  # Weight by confidence
        metrics["confidence_weighted_return"] = float(np.mean(weighted_returns))

        return metrics

    def evaluate_by_regime(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: np.ndarray,
        regimes: np.ndarray,
    ) -> dict[str, dict[str, float]]:
        """
        Evaluate model performance by market regime.

        Args:
            y_true: True labels
            y_pred: Predicted labels
            y_prob: Prediction probabilities
            regimes: Regime labels for each prediction

        Returns:
            Metrics per regime
        """
        results = {}
        unique_regimes = np.unique(regimes)

        for regime in unique_regimes:
            mask = regimes == regime
            if np.sum(mask) < 10:
                continue

            regime_metrics = self.evaluate_predictions(
                y_true[mask],
                y_pred[mask],
                y_prob[mask],
            )
            results[f"regime_{regime}"] = regime_metrics

        return results

    def evaluate_by_probability_bucket(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: np.ndarray,
        n_buckets: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Evaluate accuracy by confidence/probability buckets.

        Returns:
            List of metrics per probability bucket
        """
        max_probs = np.max(y_prob, axis=1)
        results = []

        for i in range(n_buckets):
            lower = i / n_buckets
            upper = (i + 1) / n_buckets
            mask = (max_probs >= lower) & (max_probs < upper)

            if np.sum(mask) < 5:
                continue

            bucket_metrics = self.evaluate_predictions(
                y_true[mask],
                y_pred[mask],
                y_prob[mask],
            )
            bucket_metrics["bucket_lower"] = lower
            bucket_metrics["bucket_upper"] = upper
            bucket_metrics["count"] = int(np.sum(mask))
            bucket_metrics["avg_confidence"] = float(np.mean(max_probs[mask]))

            results.append(bucket_metrics)

        return results


class WalkForwardEvaluator:
    """
    Walk-forward evaluation with detailed metrics per fold.
    """

    def __init__(
        self,
        n_splits: int = 5,
        train_months: int = 24,
        test_months: int = 3,
        gap_months: int = 1,
    ):
        self.n_splits = n_splits
        self.train_months = train_months
        self.test_months = test_months
        self.gap_months = gap_months

    def evaluate(
        self,
        trainer,
        X: pd.DataFrame,
        y: pd.Series,
    ) -> dict[str, Any]:
        """
        Run walk-forward evaluation.

        Returns:
            Detailed results per fold and aggregate
        """
        from services.ml.training import WalkForwardSplitter

        splitter = WalkForwardSplitter(
            n_splits=self.n_splits,
            train_size_months=self.train_months,
            test_size_months=self.test_months,
            gap_months=self.gap_months,
        )

        evaluator = ModelEvaluator()
        fold_results = []

        for fold, (train_idx, test_idx) in enumerate(splitter.split(X, y)):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            if len(np.unique(y_train)) < 2:
                continue

            # Train and calibrate for this fold
            fold_models = {}
            fold_probs = {}

            for name, base_model in trainer.get_base_models().items():
                model = base_model.__class__(**base_model.get_params())
                model.fit(X_train, y_train)

                from sklearn.calibration import CalibratedClassifierCV
                calibrator = CalibratedClassifierCV(
                    model,
                    method="isotonic",
                    cv=3,
                )
                calibrator.fit(X_train, y_train)

                probs = calibrator.predict_proba(X_test)
                fold_probs[name] = probs

            # Ensemble probabilities
            all_probs = list(fold_probs.values())
            ensemble_probs = np.mean(all_probs, axis=0)
            ensemble_preds = np.argmax(ensemble_probs, axis=1)

            # Evaluate
            fold_metrics = evaluator.evaluate_predictions(y_test.values, ensemble_preds, ensemble_probs)
            fold_metrics["fold"] = fold
            fold_metrics["train_size"] = len(train_idx)
            fold_metrics["test_size"] = len(test_idx)

            fold_results.append(fold_metrics)

        # Aggregate
        aggregate = {}
        for key in fold_results[0].keys():
            if key not in ["fold", "confusion_matrix"]:
                values = [f[key] for f in fold_results if key in f and not np.isnan(f[key])]
                if values:
                    aggregate[f"mean_{key}"] = float(np.mean(values))
                    aggregate[f"std_{key}"] = float(np.std(values))

        return {
            "folds": fold_results,
            "aggregate": aggregate,
        }


def compare_models(
    results: dict[str, dict[str, float]],
    metric: str = "accuracy",
) -> pd.DataFrame:
    """
    Compare multiple model results.

    Args:
        results: Dict of model_name -> metrics
        metric: Metric to sort by

    Returns:
        Comparison DataFrame
    """
    df = pd.DataFrame(results).T
    if metric in df.columns:
        df = df.sort_values(metric, ascending=False)
    return df