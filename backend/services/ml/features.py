from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import numpy as np
import pandas as pd

from services.ml.target import TargetDirection, TargetDefinition


class FeaturePipeline:
    """
    Feature engineering pipeline with strict leakage prevention.

    Key principles:
    1. All features computed ONLY from data available at prediction time
    2. No future information in any feature
    3. Scalers/transformers fit only on training data
    4. Rolling windows use only historical data
    5. Corporate actions handled using point-in-time data
    """

    def __init__(
        self,
        lookback_window: int = 252,
        min_periods: int = 20,
    ):
        self.lookback_window = lookback_window
        self.min_periods = min_periods

    def compute_all_features(
        self,
        ohlcv: pd.DataFrame,
        market_data: Optional[pd.DataFrame] = None,
        sector_data: Optional[pd.DataFrame] = None,
        reference_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Compute all features for a single instrument up to reference_date.

        Args:
            ohlcv: DataFrame with columns [open, high, low, close, volume] indexed by date
            market_data: Optional market index data for relative features
            sector_data: Optional sector index data for relative features
            reference_date: Cutoff date - only data up to this date is used

        Returns:
            DataFrame with features indexed by date
        """
        if reference_date:
            ohlcv = ohlcv[ohlcv.index <= pd.Timestamp(reference_date)]
            if market_data is not None:
                market_data = market_data[market_data.index <= pd.Timestamp(reference_date)]
            if sector_data is not None:
                sector_data = sector_data[sector_data.index <= pd.Timestamp(reference_date)]

        if len(ohlcv) < self.min_periods:
            return pd.DataFrame(index=ohlcv.index)

        features = pd.DataFrame(index=ohlcv.index)

        # Price features
        features = self._add_price_features(features, ohlcv)
        # Momentum features
        features = self._add_momentum_features(features, ohlcv)
        # Volatility features
        features = self._add_volatility_features(features, ohlcv)
        # Volume features
        features = self._add_volume_features(features, ohlcv)
        # Trend features
        features = self._add_trend_features(features, ohlcv)
        # Technical indicators
        features = self._add_technical_indicators(features, ohlcv)

        if market_data is not None:
            features = self._add_market_relative_features(features, ohlcv, market_data)

        if sector_data is not None:
            features = self._add_sector_relative_features(features, ohlcv, sector_data)

        # Regime features
        features = self._add_regime_features(features, ohlcv)

        # Corporate action flags
        features = self._add_corporate_action_features(features, ohlcv)

        return features

    def _add_price_features(self, features: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Price-based features."""
        close = ohlcv["close"]
        open_ = ohlcv["open"]
        high = ohlcv["high"]
        low = ohlcv["low"]

        # Returns
        features["return_1d"] = close.pct_change()
        features["log_return_1d"] = np.log(close / close.shift(1))

        # Gap features
        features["gap_up"] = (open_ > high.shift(1)).astype(int)
        features["gap_down"] = (open_ < low.shift(1)).astype(int)
        features["gap_pct"] = (open_ - close.shift(1)) / close.shift(1)

        # Intraday features
        features["body_pct"] = (close - open_) / open_
        features["upper_shadow_pct"] = (high - np.maximum(close, open_)) / close
        features["lower_shadow_pct"] = (np.minimum(close, open_) - low) / close

        # Price position
        features["close_position"] = (close - low) / (high - low).replace(0, np.nan)

        return features

    def _add_momentum_features(self, features: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Momentum features."""
        close = ohlcv["close"]

        # Rate of Change
        for period in [5, 10, 20, 60, 120]:
            features[f"roc_{period}d"] = close.pct_change(period)

        # Momentum
        for period in [10, 20, 60]:
            features[f"momentum_{period}d"] = close / close.shift(period) - 1

        # Rolling highs/lows
        for period in [20, 60, 120]:
            features[f"pct_from_high_{period}d"] = (close / close.rolling(period).max() - 1)
            features[f"pct_from_low_{period}d"] = (close / close.rolling(period).min() - 1)

        return features

    def _add_volatility_features(self, features: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Volatility features."""
        close = ohlcv["close"]
        open_ = ohlcv["open"]
        high = ohlcv["high"]
        low = ohlcv["low"]

        returns = close.pct_change()
        log_returns = np.log(close / close.shift(1))

        # Realized volatility
        for period in [5, 10, 20, 60, 120]:
            features[f"realized_vol_{period}d"] = returns.rolling(period).std() * np.sqrt(252)

        # Parkinson volatility (high-low)
        for period in [10, 20, 60]:
            hl_var = (np.log(high / low) ** 2).rolling(period).mean() / (4 * np.log(2))
            features[f"parkinson_vol_{period}d"] = np.sqrt(hl_var) * np.sqrt(252)

        # Garman-Klass volatility
        for period in [10, 20, 60]:
            gk = (0.5 * (np.log(high / low) ** 2) - (2 * np.log(2) - 1) * (np.log(close / open_) ** 2)).rolling(period).mean()
            features[f"garman_klass_vol_{period}d"] = np.sqrt(gk.clip(lower=0)) * np.sqrt(252)

        # Volatility percentile (rank within lookback)
        for period in [60, 120, 252]:
            vol = features[f"realized_vol_{min(period, 20)}d"]
            features[f"vol_percentile_{period}d"] = vol.rolling(period).rank(pct=True)

        # Volatility regime
        short_vol = features["realized_vol_20d"]
        long_vol = features["realized_vol_60d"]
        features["vol_regime"] = (short_vol > long_vol).astype(int)

        return features

    def _add_volume_features(self, features: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Volume features."""
        volume = ohlcv["volume"]
        close = ohlcv["close"]

        # Relative volume
        for period in [10, 20, 60]:
            avg_vol = volume.rolling(period).mean()
            features[f"rel_volume_{period}d"] = volume / avg_vol.replace(0, np.nan)

        # Volume trend
        features["volume_trend_20d"] = volume.rolling(20).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 20 else np.nan
        )

        # Dollar volume
        features["dollar_volume"] = volume * close
        for period in [10, 20]:
            features[f"avg_dollar_volume_{period}d"] = features["dollar_volume"].rolling(period).mean()

        # Volume-price correlation
        returns = close.pct_change()
        features["vol_price_corr_20d"] = returns.rolling(20).corr(volume.pct_change())

        # On-Balance Volume
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        features["obv"] = obv
        features["obv_ema_20"] = obv.ewm(span=20).mean()

        return features

    def _add_trend_features(self, features: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Trend features."""
        close = ohlcv["close"]

        # Moving averages
        for period in [5, 10, 20, 50, 100, 200]:
            ma = close.rolling(period).mean()
            features[f"sma_{period}"] = ma
            features[f"pct_from_sma_{period}"] = close / ma - 1

        # EMA
        for period in [12, 26, 50]:
            ema = close.ewm(span=period, adjust=False).mean()
            features[f"ema_{period}"] = ema
            features[f"pct_from_ema_{period}"] = close / ema - 1

        # MACD
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9, adjust=False).mean()
        features["macd"] = macd
        features["macd_signal"] = signal
        features["macd_histogram"] = macd - signal

        # Trend strength (ADX-like)
        features = self._add_adx(features, ohlcv)

        return features

    def _add_adx(self, features: pd.DataFrame, ohlcv: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Average Directional Index."""
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]

        plus_dm = high.diff()
        minus_dm = low.diff().abs()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.rolling(period).mean()

        features["adx"] = adx
        features["plus_di"] = plus_di
        features["minus_di"] = minus_di

        return features

    def _add_technical_indicators(self, features: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Additional technical indicators."""
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]

        # RSI
        for period in [7, 14, 21]:
            features[f"rsi_{period}"] = self._calculate_rsi(close, period)

        # Stochastic
        for period in [14]:
            low_min = low.rolling(period).min()
            high_max = high.rolling(period).max()
            stoch_k = 100 * (close - low_min) / (high_max - low_min)
            stoch_d = stoch_k.rolling(3).mean()
            features[f"stoch_k_{period}"] = stoch_k
            features[f"stoch_d_{period}"] = stoch_d

        # Williams %R
        for period in [14]:
            wr = -100 * (high.rolling(period).max() - close) / (high.rolling(period).max() - low.rolling(period).min())
            features[f"williams_r_{period}"] = wr

        # CCI
        for period in [20]:
            tp = (high + low + close) / 3
            ma = tp.rolling(period).mean()
            md = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - x.mean())))
            cci = (tp - ma) / (0.015 * md)
            features[f"cci_{period}"] = cci

        return features

    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _add_market_relative_features(
        self,
        features: pd.DataFrame,
        ohlcv: pd.DataFrame,
        market_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Market-relative features."""
        close = ohlcv["close"]
        market_close = market_data["close"]

        # Align dates
        common_dates = close.index.intersection(market_close.index)
        if len(common_dates) < 20:
            return features

        close_aligned = close.loc[common_dates]
        market_aligned = market_close.loc[common_dates]

        # Relative returns
        for period in [1, 5, 20, 60]:
            stock_ret = close_aligned.pct_change(period)
            market_ret = market_aligned.pct_change(period)
            rel_ret = stock_ret - market_ret
            features.loc[common_dates, f"rel_return_{period}d"] = rel_ret

        # Beta
        stock_ret_1d = close_aligned.pct_change()
        market_ret_1d = market_aligned.pct_change()
        for period in [60, 120, 252]:
            cov = stock_ret_1d.rolling(period).cov(market_ret_1d)
            var = market_ret_1d.rolling(period).var()
            features.loc[common_dates, f"beta_{period}d"] = cov / var.replace(0, np.nan)

        # Correlation
        for period in [20, 60, 120]:
            corr = stock_ret_1d.rolling(period).corr(market_ret_1d)
            features.loc[common_dates, f"corr_market_{period}d"] = corr

        # Relative strength
        for period in [20, 60, 120]:
            rel_strength = (close_aligned / close_aligned.shift(period)) / (market_aligned / market_aligned.shift(period))
            features.loc[common_dates, f"rel_strength_{period}d"] = rel_strength

        return features

    def _add_sector_relative_features(
        self,
        features: pd.DataFrame,
        ohlcv: pd.DataFrame,
        sector_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Sector-relative features (similar to market-relative)."""
        close = ohlcv["close"]
        sector_close = sector_data["close"]

        common_dates = close.index.intersection(sector_close.index)
        if len(common_dates) < 20:
            return features

        close_aligned = close.loc[common_dates]
        sector_aligned = sector_close.loc[common_dates]

        for period in [20, 60]:
            stock_ret = close_aligned.pct_change(period)
            sector_ret = sector_aligned.pct_change(period)
            rel_ret = stock_ret - sector_ret
            features.loc[common_dates, f"rel_return_sector_{period}d"] = rel_ret

        return features

    def _add_regime_features(self, features: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """Market regime features."""
        close = ohlcv["close"]

        # Trend regime
        sma_50 = close.rolling(50).mean()
        sma_200 = close.rolling(200).mean()
        features["trend_regime"] = (sma_50 > sma_200).astype(int)

        # Volatility regime
        vol_20 = features.get("realized_vol_20d", close.pct_change().rolling(20).std() * np.sqrt(252))
        vol_60 = features.get("realized_vol_60d", close.pct_change().rolling(60).std() * np.sqrt(252))
        features["vol_regime_high"] = (vol_20 > vol_60 * 1.2).astype(int)
        features["vol_regime_low"] = (vol_20 < vol_60 * 0.8).astype(int)

        # Momentum regime
        mom_60 = close.pct_change(60)
        features["momentum_regime"] = (mom_60 > 0).astype(int)

        # Breadth (if we had multiple stocks)
        # Placeholder for future

        return features

    def _add_corporate_action_features(
        self,
        features: pd.DataFrame,
        ohlcv: pd.DataFrame,
    ) -> pd.DataFrame:
        """Corporate action flags."""
        close = ohlcv["close"]
        volume = ohlcv["volume"]

        # Large price jumps (potential splits/dividends)
        daily_return = close.pct_change()
        features["large_jump_up"] = (daily_return > 0.15).astype(int)
        features["large_jump_down"] = (daily_return < -0.15).astype(int)

        # Volume spikes
        vol_ma = volume.rolling(20).mean()
        features["volume_spike"] = (volume > vol_ma * 5).astype(int)

        # Price continuity (detect splits)
        features["price_discontinuity"] = (
            (close / close.shift(1) > 1.5) | (close / close.shift(1) < 0.5)
        ).astype(int)

        return features


def create_feature_matrix(
    instruments_data: dict[str, pd.DataFrame],
    market_data: Optional[pd.DataFrame] = None,
    sector_mapping: Optional[dict[str, pd.DataFrame]] = None,
    reference_date: Optional[datetime] = None,
    lookback_window: int = 252,
) -> pd.DataFrame:
    """
    Create feature matrix for multiple instruments.

    Args:
        instruments_data: Dict of symbol -> OHLCV DataFrame
        market_data: Optional market index DataFrame
        sector_mapping: Optional dict of sector -> sector index DataFrame
        reference_date: Cutoff date for features
        lookback_window: Maximum lookback period

    Returns:
        Feature matrix with MultiIndex (symbol, date)
    """
    pipeline = FeaturePipeline(lookback_window=lookback_window)

    all_features = []
    for symbol, ohlcv in instruments_data.items():
        sector_data = sector_mapping.get(symbol) if sector_mapping else None
        feats = pipeline.compute_all_features(
            ohlcv, market_data, sector_data, reference_date
        )
        if not feats.empty:
            feats["symbol"] = symbol
            all_features.append(feats)

    if not all_features:
        return pd.DataFrame()

    result = pd.concat(all_features)
    result = result.set_index("symbol", append=True).reorder_levels(["symbol", "date"])
    return result.sort_index()