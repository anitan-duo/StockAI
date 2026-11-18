from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class TargetDirection(str, Enum):
    """Target direction for classification."""

    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"


class TargetDefinition:
    """
    Defines the target for next trading day direction prediction.

    The target is computed as the direction of price movement from
    close of day t to close of day t+1 (next trading day).

    Thresholds:
    - UP: return > +0.5%
    - NEUTRAL: -0.5% <= return <= +0.5%
    - DOWN: return < -0.5%

    These thresholds can be configured based on market characteristics.
    """

    def __init__(
        self,
        up_threshold: float = 0.005,
        down_threshold: float = -0.005,
        horizon_days: int = 1,
    ):
        self.up_threshold = up_threshold
        self.down_threshold = down_threshold
        self.horizon_days = horizon_days

    def compute_target(self, close_t: float, close_t_plus_h: float) -> TargetDirection:
        """
        Compute target direction from close prices.

        Args:
            close_t: Close price at prediction time (day t)
            close_t_plus_h: Close price at horizon (day t+h)

        Returns:
            TargetDirection enum value
        """
        if close_t <= 0:
            return TargetDirection.NEUTRAL

        return_pct = (close_t_plus_h - close_t) / close_t

        if return_pct > self.up_threshold:
            return TargetDirection.UP
        elif return_pct < self.down_threshold:
            return TargetDirection.DOWN
        else:
            return TargetDirection.NEUTRAL

def compute_target_series(
        close_series: pd.Series,
        target_def: "TargetDefinition",
    ) -> pd.Series:
        """
        Compute target for a series of close prices.

        Args:
            close_series: Series of close prices indexed by date
            target_def: TargetDefinition instance with thresholds and horizon

        Returns:
            Series of TargetDirection values (with NaN for insufficient data)
        """
        future_close = close_series.shift(-target_def.horizon_days)
        returns = (future_close - close_series) / close_series

        def classify(ret: float):
            if pd.isna(ret):
                return np.nan
            if ret > target_def.up_threshold:
                return TargetDirection.UP
            elif ret < target_def.down_threshold:
                return TargetDirection.DOWN
            return TargetDirection.NEUTRAL

        return returns.apply(classify)


def get_next_trading_day(date: datetime, market_calendar: Optional[set] = None) -> datetime:
    """
    Get the next trading day.

    DEPRECATED/UNUSED: no production path calls this. Real label alignment uses
    shift(-1) over persisted trading bars, so exchange holidays are handled
    naturally (only actual trading days exist in the series). Weekend skipping
    below is retained for backward compatibility only.
    """
    next_day = date + timedelta(days=1)
    while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
        next_day += timedelta(days=1)

    # TODO: Check market_calendar for holidays
    return next_day


def align_to_trading_days(
    dates: pd.DatetimeIndex,
    market_calendar: Optional[set] = None,
) -> pd.DatetimeIndex:
    """
    Align dates to trading days only.

    Removes weekends and optionally holidays.
    """
    # Filter out weekends (Monday=0, Friday=4)
    trading_mask = dates.dayofweek < 5

    if market_calendar:
        # Remove holidays
        holiday_set = {pd.Timestamp(d).date() for d in market_calendar}
        trading_mask = trading_mask & ~dates.date.astype("datetime64[D]").isin(holiday_set)

    return dates[trading_mask]