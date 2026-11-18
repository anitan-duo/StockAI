from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.base import BaseEstimator, ClassifierMixin


class ProbabilityCalibrator:
    """
    Probability calibration utilities.

    Supports:
    - Platt scaling (logistic regression)
    - Isotonic regression
    - Temperature scaling (for neural networks)
    """

    def __init__(self, method: str = "isotonic"):
        """
        Initialize calibrator.

        Args:
            method: "platt", "isotonic", or "temperature"
        """
        self.method = method
        self.calibrator = None
        self.is_fitted = False

    def fit(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
    ) -> "ProbabilityCalibrator":
        """
        Fit calibrator on validation data.

        Args:
            y_true: True labels (n_samples,)
            y_prob: Uncalibrated probabilities (n_samples, n_classes)

        Returns:
            self
        """
        if self.method == "platt":
            self.calibrator = LogisticRegression(solver="lbfgs", max_iter=1000)
            # Fit one-vs-rest for multi-class
            from sklearn.multiclass import OneVsRestClassifier
            self.calibrator = OneVsRestClassifier(self.calibrator)
            self.calibrator.fit(y_prob, y_true)

        elif self.method == "isotonic":
            # Isotonic regression per class
            self.calibrator = {}
            n_classes = y_prob.shape[1]
            for i in range(n_classes):
                iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
                y_binary = (y_true == i).astype(int)
                iso.fit(y_prob[:, i], y_binary)
                self.calibrator[i] = iso

        elif self.method == "temperature":
            # Temperature scaling - single temperature parameter
            self.calibrator = self._fit_temperature(y_true, y_prob)

        else:
            raise ValueError(f"Unknown calibration method: {self.method}")

        self.is_fitted = True
        return self

    def _fit_temperature(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
    ) -> float:
        """
        Fit temperature scaling parameter.

        Temperature scaling learns a single parameter T that scales logits:
        calibrated = softmax(logits / T)
        """
        from scipy.optimize import minimize

        # Convert probabilities to logits
        logits = np.log(np.clip(y_prob, 1e-15, 1 - 1e-15))

        def nll(T):
            scaled_logits = logits / T
            # Softmax
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits, axis=1, keepdims=True))
            softmax = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
            # Cross-entropy loss
            true_probs = softmax[np.arange(len(y_true)), y_true]
            return -np.mean(np.log(np.clip(true_probs, 1e-15, 1)))

        result = minimize(nll, x0=1.0, bounds=[(0.01, 10.0)], method="L-BFGS-B")
        return result.x[0]

    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        """
        Apply calibration to probabilities.

        Args:
            y_prob: Uncalibrated probabilities (n_samples, n_classes)

        Returns:
            Calibrated probabilities
        """
        if not self.is_fitted:
            raise ValueError("Calibrator not fitted. Call fit() first.")

        n_classes = y_prob.shape[1]
        calibrated = np.zeros_like(y_prob)

        if self.method == "platt":
            calibrated = self.calibrator.predict_proba(y_prob)

        elif self.method == "isotonic":
            for i in range(n_classes):
                if i in self.calibrator:
                    calibrated[:, i] = self.calibrator[i].transform(y_prob[:, i])
                else:
                    calibrated[:, i] = y_prob[:, i]

        elif self.method == "temperature":
            T = self.calibrator
            logits = np.log(np.clip(y_prob, 1e-15, 1 - 1e-15))
            scaled_logits = logits / T
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits, axis=1, keepdims=True))
            calibrated = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

        # Renormalize
        row_sums = calibrated.sum(axis=1, keepdims=True)
        calibrated = calibrated / np.where(row_sums > 0, row_sums, 1)

        return calibrated

    def fit_transform(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
    ) -> np.ndarray:
        """Fit and transform in one step."""
        return self.fit(y_true, y_prob).transform(y_prob)


class EnsembleCalibrator:
    """
    Calibrate ensemble of models.

    Uses stacking or averaging of calibrated probabilities.
    """

    def __init__(
        self,
        base_calibration: str = "isotonic",
        meta_calibration: str = "isotonic",
    ):
        self.base_calibration = base_calibration
        self.meta_calibration = meta_calibration
        self.base_calibrators = {}
        self.meta_calibrator = None
        self.is_fitted = False

    def fit(
        self,
        y_true: np.ndarray,
        model_probs: dict[str, np.ndarray],
    ) -> "EnsembleCalibrator":
        """
        Fit calibrators for each model and meta-calibrator.

        Args:
            y_true: True labels
            model_probs: Dict of model_name -> uncalibrated probabilities
        """
        # Calibrate each model
        calibrated_probs = {}
        for name, probs in model_probs.items():
            calibrator = ProbabilityCalibrator(method=self.base_calibration)
            calibrated_probs[name] = calibrator.fit_transform(y_true, probs)
            self.base_calibrators[name] = calibrator

        # Stack calibrated probabilities
        stacked = np.hstack(list(calibrated_probs.values()))

        # Meta-calibrator
        self.meta_calibrator = ProbabilityCalibrator(method=self.meta_calibration)
        self.meta_calibrator.fit(y_true, stacked)

        self.is_fitted = True
        return self

    def transform(
        self,
        model_probs: dict[str, np.ndarray],
    ) -> np.ndarray:
        """Apply ensemble calibration."""
        if not self.is_fitted:
            raise ValueError("Not fitted")

        calibrated = {}
        for name, probs in model_probs.items():
            if name in self.base_calibrators:
                calibrated[name] = self.base_calibrators[name].transform(probs)
            else:
                calibrated[name] = probs

        stacked = np.hstack(list(calibrated.values()))
        return self.meta_calibrator.transform(stacked)

    def fit_transform(
        self,
        y_true: np.ndarray,
        model_probs: dict[str, np.ndarray],
    ) -> np.ndarray:
        return self.fit(y_true, model_probs).transform(model_probs)


def calibrate_ensemble_predictions(
    y_true: np.ndarray,
    y_probs: list[np.ndarray],
    method: str = "isotonic",
) -> tuple[np.ndarray, list]:
    """
    Calibrate multiple model predictions and average them.

    Args:
        y_true: True labels
        y_probs: List of probability arrays from each model
        method: Calibration method

    Returns:
        (averaged calibrated probabilities, list of calibrators)
    """
    calibrators = []
    calibrated_probs = []

    for probs in y_probs:
        calibrator = ProbabilityCalibrator(method=method)
        calibrated = calibrator.fit_transform(y_true, probs)
        calibrators.append(calibrator)
        calibrated_probs.append(calibrated)

    # Average calibrated probabilities
    avg_probs = np.mean(calibrated_probs, axis=0)

    return avg_probs, calibrators


class OnlineCalibrator:
    """
    Online calibration that updates incrementally.

    Uses exponential moving average of calibration errors.
    """

    def __init__(
        self,
        n_bins: int = 10,
        alpha: float = 0.1,
    ):
        self.n_bins = n_bins
        self.alpha = alpha
        self.bin_centers = np.linspace(0.05, 0.95, n_bins)
        self.bin_counts = np.zeros(n_bins)
        self.bin_errors = np.zeros(n_bins)  # Average calibration error per bin
        self.is_initialized = False

    def update(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
    ) -> None:
        """
        Update calibration with new batch.

        Args:
            y_true: True labels (n_samples,)
            y_prob: Predicted probabilities for positive class (n_samples,)
        """
        # Bin predictions
        bin_indices = np.searchsorted(self.bin_centers, y_prob) - 1
        bin_indices = np.clip(bin_indices, 0, self.n_bins - 1)

        for i in range(self.n_bins):
            mask = bin_indices == i
            if np.sum(mask) > 0:
                bin_true = y_true[mask].mean()
                bin_pred = y_prob[mask].mean()
                error = bin_true - bin_pred

                if self.is_initialized and self.bin_counts[i] > 0:
                    # EMA update
                    self.bin_errors[i] = (1 - self.alpha) * self.bin_errors[i] + self.alpha * error
                    self.bin_counts[i] += np.sum(mask)
                else:
                    self.bin_errors[i] = error
                    self.bin_counts[i] = np.sum(mask)

        self.is_initialized = True

    def calibrate(self, y_prob: np.ndarray) -> np.ndarray:
        """
        Apply online calibration.

        Args:
            y_prob: Probabilities to calibrate

        Returns:
            Calibrated probabilities
        """
        if not self.is_initialized:
            return y_prob

        bin_indices = np.searchsorted(self.bin_centers, y_prob) - 1
        bin_indices = np.clip(bin_indices, 0, self.n_bins - 1)

        calibrated = y_prob + self.bin_errors[bin_indices]
        return np.clip(calibrated, 0.001, 0.999)


def expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    Calculate Expected Calibration Error (ECE).

    Args:
        y_true: True binary labels
        y_prob: Predicted probabilities
        n_bins: Number of bins

    Returns:
        ECE value
    """
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]

    ece = 0.0
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        in_bin = (y_prob > bin_lower) & (y_prob <= bin_upper)
        prop_in_bin = in_bin.mean()

        if prop_in_bin > 0:
            accuracy_in_bin = y_true[in_bin].mean()
            avg_confidence_in_bin = y_prob[in_bin].mean()
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin

    return ece


def maximum_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    Calculate Maximum Calibration Error (MCE).

    Args:
        y_true: True binary labels
        y_prob: Predicted probabilities
        n_bins: Number of bins

    Returns:
        MCE value
    """
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]

    mce = 0.0
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        in_bin = (y_prob > bin_lower) & (y_prob <= bin_upper)
        if in_bin.any():
            accuracy_in_bin = y_true[in_bin].mean()
            avg_confidence_in_bin = y_prob[in_bin].mean()
            mce = max(mce, np.abs(avg_confidence_in_bin - accuracy_in_bin))

    return mce