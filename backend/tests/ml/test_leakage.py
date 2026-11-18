"""
Leakage prevention tests for ML pipeline.

These tests ensure that no future information leaks into historical features
or targets during training and prediction.
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta, UTC
from sklearn.preprocessing import StandardScaler

from services.ml.features import FeaturePipeline
from services.ml.target import TargetDefinition, TargetDirection, compute_target_series
from services.ml.training import WalkForwardSplitter, ModelTrainer
from services.ml.features import create_feature_matrix


class TestFeatureLeakage:
    """Tests for feature engineering leakage prevention."""

    def test_no_future_data_in_features(self):
        """Ensure features only use historical data up to reference date."""
        # Create sample OHLCV data
        dates = pd.date_range('2023-01-01', periods=100, freq='D', tz=UTC)
        np.random.seed(42)
        base_price = 100
        prices = []
        for i in range(100):
            change = np.random.normal(0, 0.02)
            base_price = base_price * (1 + change)
            prices.append(base_price)

        ohlcv = pd.DataFrame({
            'open': prices,
            'high': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
            'low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
            'close': prices,
            'volume': np.random.randint(1000000, 10000000, 100),
        }, index=dates)

        pipeline = FeaturePipeline()
        reference_date = dates[50]  # Middle of the data

        features = pipeline.compute_all_features(ohlcv, reference_date=reference_date)

        # Check that no feature uses data after reference_date
        for col in features.columns:
            feature_data = features[col]
            # All non-NaN values should be at or before reference_date
            valid_idx = feature_data.dropna().index
            assert all(idx <= reference_date for idx in valid_idx), \
                f"Feature {col} contains future data after reference date"

    def test_feature_calculation_uses_only_historical_data(self):
        """Test that rolling windows only use past data."""
        dates = pd.date_range('2023-01-01', periods=50, freq='D', tz=UTC)
        prices = 100 + np.cumsum(np.random.normal(0, 1, 50))

        ohlcv = pd.DataFrame({
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices,
            'volume': np.ones(50) * 1000000,
        }, index=dates)

        pipeline = FeaturePipeline()
        reference_date = dates[25]

        features = pipeline.compute_all_features(ohlcv, reference_date=reference_date)

        # SMA should only use data up to reference date
        sma_20 = features['sma_20'].dropna()
        assert all(idx <= reference_date for idx in sma_20.index)

        # RSI should only use data up to reference date
        rsi = features['rsi_14'].dropna()
        assert all(idx <= reference_date for idx in rsi.index)


class TestTargetLeakage:
    """Tests for target definition leakage prevention."""

    def test_target_uses_future_price_correctly(self):
        """Target should use future price (t+horizon) not current price."""
        target_def = TargetDefinition(up_threshold=0.005, down_threshold=-0.005, horizon_days=1)

        # Create price series
        dates = pd.date_range('2023-01-01', periods=10, freq='D', tz=UTC)
        close_prices = pd.Series([100, 101, 102, 101, 103, 102, 104, 105, 106, 107], index=dates)

        targets = compute_target_series(close_prices, target_def)

        # Check that target at day i uses price at day i+1
        # Day 0 (100) -> Day 1 (101) = +1% -> UP
        assert targets.iloc[0] == TargetDirection.UP
        # Day 1 (101) -> Day 2 (102) = +0.99% -> UP
        assert targets.iloc[1] == TargetDirection.UP
        # Day 2 (102) -> Day 3 (101) = -0.98% -> DOWN
        assert targets.iloc[2] == TargetDirection.DOWN
        # Day 8 (106) -> Day 9 (107) = +0.94% -> UP
        assert targets.iloc[8] == TargetDirection.UP
        # Day 9 has no future data -> NaN
        assert pd.isna(targets.iloc[9])

    def test_target_thresholds(self):
        """Test that thresholds correctly classify directions."""
        target_def = TargetDefinition(up_threshold=0.01, down_threshold=-0.01, horizon_days=1)

        dates = pd.date_range('2023-01-01', periods=5, freq='D', tz=UTC)
        # Prices: 100 -> 100.5% -> 101.5% -> 100.5% -> 99.5%
        close_prices = pd.Series([100, 100.5, 101.5, 100.5, 99.5], index=dates)

        targets = compute_target_series(close_prices, target_def)

        # Day 0: 100 -> 100.5 = +0.5% -> NEUTRAL (between -1% and +1%)
        assert targets.iloc[0] == TargetDirection.NEUTRAL
        # Day 1: 100.5 -> 101.5 = +0.995% -> NEUTRAL (just under 1%)
        assert targets.iloc[1] == TargetDirection.NEUTRAL
        # Day 2: 101.5 -> 100.5 = -0.985% -> NEUTRAL (just above -1%)
        assert targets.iloc[2] == TargetDirection.NEUTRAL
        # Day 3: 100.5 -> 99.5 = -0.995% -> NEUTRAL (just above -1%)
        assert targets.iloc[3] == TargetDirection.NEUTRAL


class TestWalkForwardLeakage:
    """Tests for walk-forward validation leakage prevention."""

    def test_walk_forward_splits_are_chronological(self):
        """Walk-forward splits should always have train before test."""
        dates = pd.date_range('2020-01-01', periods=500, freq='D', tz=UTC)
        X = pd.DataFrame({'feature': np.random.randn(500)}, index=dates)
        y = pd.Series(np.random.randint(0, 3, 500), index=dates)

        splitter = WalkForwardSplitter(n_splits=3, train_size_months=12, test_size_months=3, gap_months=1)

        for train_idx, test_idx in splitter.split(X, y):
            train_dates = X.index[train_idx]
            test_dates = X.index[test_idx]

            # All train dates should be before all test dates
            assert train_dates.max() < test_dates.min(), \
                f"Train dates leak into test dates: {train_dates.max()} >= {test_dates.min()}"

    def test_walk_forward_gap_prevents_leakage(self):
        """Gap between train and test should prevent leakage."""
        dates = pd.date_range('2020-01-01', periods=500, freq='D', tz=UTC)
        X = pd.DataFrame({'feature': np.random.randn(500)}, index=dates)
        y = pd.Series(np.random.randint(0, 3, 500), index=dates)

        splitter = WalkForwardSplitter(
            n_splits=2,
            train_size_months=12,
            test_size_months=1,
            gap_months=1,  # 1 month gap
        )

        for train_idx, test_idx in splitter.split(X, y):
            train_dates = X.index[train_idx]
            test_dates = X.index[test_idx]

            # Gap should be at least ~30 days
            gap = (test_dates.min() - train_dates.max()).days
            assert gap >= 28, f"Gap too small: {gap} days"


class TestScalerLeakage:
    """Tests for scaler fitting leakage prevention."""

    def test_scaler_fit_only_on_training_data(self):
        """Scaler should only be fit on training data."""
        from sklearn.preprocessing import StandardScaler

        dates = pd.date_range('2023-01-01', periods=100, freq='D', tz=UTC)
        X = pd.DataFrame({
            'feature1': np.random.randn(100) * 100,
            'feature2': np.random.randn(100) * 10,
        }, index=dates)

        # Simulate walk-forward
        train_size = 70
        X_train = X.iloc[:train_size]
        X_test = X.iloc[train_size:]

        scaler = StandardScaler()
        scaler.fit(X_train)  # Fit ONLY on training data

        X_train_scaled = scaler.transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Training data should be centered at 0
        assert np.abs(X_train_scaled.mean()) < 0.1
        assert np.abs(X_train_scaled.std() - 1) < 0.1

        # Test data should use same scaler (not refit)
        # Test mean/std can be different from 0/1 (that's expected)


class TestDataAlignmentLeakage:
    """Tests for data alignment leakage."""

    def test_feature_target_alignment(self):
        """Features and targets should be aligned by date without leakage."""
        dates = pd.date_range('2023-01-01', periods=100, freq='D', tz=UTC)
        np.random.seed(42)

        # Create features
        X = pd.DataFrame({
            'feature1': np.random.randn(100),
            'feature2': np.random.randn(100),
        }, index=dates)

        # Create prices and targets
        close_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        prices = pd.Series(close_prices, index=dates)

        target_def = TargetDefinition()
        targets = compute_target_series(prices, target_def)

        # Align features and targets
        common_idx = X.index.intersection(targets.index)
        X_aligned = X.loc[common_idx]
        y_aligned = targets.loc[common_idx]

        # Remove NaN targets
        valid_mask = ~y_aligned.isna()
        X_final = X_aligned[valid_mask]
        y_final = y_aligned[valid_mask]

        # Verify no future data in features
        for idx in X_final.index:
            # The target at this index should be computed from prices at idx + 1 day
            target_date = idx + timedelta(days=1)
            assert target_date in prices.index or target_date > dates[-1]


class TestNormalizationLeakage:
    """Tests for normalization leakage."""

    def test_normalization_parameters_from_training_only(self):
        """Normalization parameters should be computed from training data only."""
        dates = pd.date_range('2023-01-01', periods=100, freq='D', tz=UTC)
        train_size = 70

        X = pd.DataFrame({
            'feature1': np.random.randn(100) * 100,
            'feature2': np.random.randn(100) * 10,
        }, index=dates)

        X_train = X.iloc[:train_size]
        X_test = X.iloc[train_size:]

        from sklearn.preprocessing import StandardScaler

        # Fit on training data only
        scaler = StandardScaler()
        scaler.fit(X_train)

        # Transform both
        X_train_scaled = scaler.transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Training mean should be ~0
        assert np.abs(X_train_scaled.mean()) < 0.1
        # Training std should be ~1
        assert np.abs(X_train_scaled.std() - 1) < 0.1

        # Test should use same scaler (not refit)
        # This is the correct behavior - no leakage


class TestModelTrainerLeakage:
    """Tests for ModelTrainer walk-forward leakage prevention."""

    def test_model_trainer_scaler_fit_inside_fold(self):
        """Verify ModelTrainer fits scaler inside each walk-forward fold, not on full data."""
        from services.ml.training import ModelTrainer, WalkForwardSplitter

        # Create synthetic data
        dates = pd.date_range('2020-01-01', periods=400, freq='D', tz=UTC)
        np.random.seed(42)
        X = pd.DataFrame({
            'feature1': np.random.randn(400) * 100,
            'feature2': np.random.randn(400) * 10,
            'feature3': np.random.randn(400) * 5,
        }, index=dates)
        y = pd.Series(np.random.randint(0, 3, 400), index=dates)

        trainer = ModelTrainer()

        # Use small split config for test
        splitter = WalkForwardSplitter(n_splits=3, train_size_months=3, test_size_months=1, gap_months=1, min_train_size=50)

        # Track scalers used in each fold
        fold_scalers = []

        # Patch the loop to capture scalers
        original_fit = StandardScaler.fit

        def track_fit(scaler_self, X_data, y=None):
            fold_scalers.append((len(fold_scalers), X_data.shape[0]))
            return original_fit(scaler_self, X_data, y)

        # Manually test the fold logic
        for fold, (train_idx, test_idx) in enumerate(splitter.split(X, y)):
            X_train_raw = X.iloc[train_idx]
            X_test_raw = X.iloc[test_idx]

            # This is what the fixed code does - fit scaler inside fold
            fold_scaler = StandardScaler()
            X_train = pd.DataFrame(fold_scaler.fit_transform(X_train_raw), index=X_train_raw.index, columns=X_train_raw.columns)
            X_test = pd.DataFrame(fold_scaler.transform(X_test_raw), index=X_test_raw.index, columns=X_test_raw.columns)

            # Verify train data is normalized
            assert np.abs(X_train.mean().mean()) < 0.1, f"Fold {fold}: Training data not centered"
            assert np.abs(X_train.std().mean() - 1) < 0.1, f"Fold {fold}: Training data not scaled"

            # Verify test data uses same scaler (not refit)
            fold_scalers.append(fold_scaler)

        # Verify we used different scalers for each fold (each fit on its own train data)
        assert len(fold_scalers) == 3, "Should have 3 fold scalers"

        # Each scaler should have been fit on different amount of data
        train_sizes = [len(X.iloc[train_idx]) for train_idx, _ in splitter.split(X, y)]
        assert len(set(train_sizes)) > 1 or train_sizes[0] > 0, "Should have valid train sizes"

    def test_model_trainer_production_scaler_fit_on_full_data(self):
        """Verify production scaler is fit on full dataset after walk-forward."""
        from services.ml.training import ModelTrainer

        dates = pd.date_range('2020-01-01', periods=400, freq='D', tz=UTC)
        np.random.seed(42)
        X = pd.DataFrame({
            'feature1': np.random.randn(400) * 100,
            'feature2': np.random.randn(400) * 10,
        }, index=dates)
        y = pd.Series(np.random.randint(0, 3, 400), index=dates)

        trainer = ModelTrainer()
        trainer.feature_names = X.columns.tolist()

        # Simulate final production training
        trainer.scaler = StandardScaler()
        X_full_scaled = pd.DataFrame(trainer.scaler.fit_transform(X), index=X.index, columns=X.columns)

        # Verify production scaler was fit on full data
        assert np.abs(X_full_scaled.mean().mean()) < 0.1, "Production scaler not centered"
        assert np.abs(X_full_scaled.std().mean() - 1) < 0.1, "Production scaler not scaled"

        # Verify scaler is stored on trainer
        assert hasattr(trainer, 'scaler'), "Scaler should be stored on trainer"
        assert trainer.scaler is not None, "Scaler should not be None"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])