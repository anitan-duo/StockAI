from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.price import PriceBar
from apps.api.repositories.market import PriceBarRepository


class IndicatorService:
    """Technical indicator calculation service."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.price_bar_repo = PriceBarRepository(session)

    async def calculate_sma(
        self,
        instrument_id: UUID,
        period: int,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> Decimal | None:
        """Calculate Simple Moving Average."""
        bars = await self._get_price_data(instrument_id, timeframe, period, end_date)
        if len(bars) < period:
            return None

        closes = [float(b.close) for b in bars[-period:]]
        sma = np.mean(closes)
        return Decimal(str(round(sma, 6)))

    async def calculate_ema(
        self,
        instrument_id: UUID,
        period: int,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> Decimal | None:
        """Calculate Exponential Moving Average."""
        bars = await self._get_price_data(instrument_id, timeframe, period * 2, end_date)
        if len(bars) < period:
            return None

        closes = np.array([float(b.close) for b in bars])
        ema = self._calculate_ema_array(closes, period)
        return Decimal(str(round(ema[-1], 6)))

    def _calculate_ema_array(self, values: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA for array of values."""
        multiplier = 2 / (period + 1)
        ema = np.zeros_like(values)
        ema[0] = values[0]

        for i in range(1, len(values)):
            ema[i] = (values[i] - ema[i - 1]) * multiplier + ema[i - 1]

        return ema

    async def calculate_rsi(
        self,
        instrument_id: UUID,
        period: int = 14,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> Decimal | None:
        """Calculate Relative Strength Index."""
        bars = await self._get_price_data(instrument_id, timeframe, period + 1, end_date)
        if len(bars) < period + 1:
            return None

        closes = np.array([float(b.close) for b in bars])
        deltas = np.diff(closes)

        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return Decimal("100")

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return Decimal(str(round(rsi, 2)))

    async def calculate_macd(
        self,
        instrument_id: UUID,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> dict[str, Decimal] | None:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        bars = await self._get_price_data(
            instrument_id, timeframe, slow_period + signal_period, end_date
        )
        if len(bars) < slow_period + signal_period:
            return None

        closes = np.array([float(b.close) for b in bars])

        ema_fast = self._calculate_ema_array(closes, fast_period)
        ema_slow = self._calculate_ema_array(closes, slow_period)

        macd_line = ema_fast - ema_slow
        signal_line = self._calculate_ema_array(macd_line, signal_period)
        histogram = macd_line - signal_line

        return {
            "macd": Decimal(str(round(macd_line[-1], 6))),
            "signal": Decimal(str(round(signal_line[-1], 6))),
            "histogram": Decimal(str(round(histogram[-1], 6))),
        }

    async def calculate_bollinger_bands(
        self,
        instrument_id: UUID,
        period: int = 20,
        num_std: float = 2.0,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> dict[str, Decimal] | None:
        """Calculate Bollinger Bands."""
        bars = await self._get_price_data(instrument_id, timeframe, period, end_date)
        if len(bars) < period:
            return None

        closes = np.array([float(b.close) for b in bars[-period:]])
        sma = np.mean(closes)
        std = np.std(closes)

        upper = sma + (num_std * std)
        lower = sma - (num_std * std)

        return {
            "upper": Decimal(str(round(upper, 6))),
            "middle": Decimal(str(round(sma, 6))),
            "lower": Decimal(str(round(lower, 6))),
        }

    async def calculate_atr(
        self,
        instrument_id: UUID,
        period: int = 14,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> Decimal | None:
        """Calculate Average True Range."""
        bars = await self._get_price_data(instrument_id, timeframe, period + 1, end_date)
        if len(bars) < period + 1:
            return None

        highs = np.array([float(b.high) for b in bars])
        lows = np.array([float(b.low) for b in bars])
        closes = np.array([float(b.close) for b in bars])

        # True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr = np.zeros(len(bars))
        for i in range(1, len(bars)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr[i] = max(hl, hc, lc)

        atr = np.mean(tr[-period:])
        return Decimal(str(round(atr, 6)))

    async def calculate_volatility(
        self,
        instrument_id: UUID,
        period: int = 20,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> Decimal | None:
        """Calculate rolling volatility (standard deviation of returns)."""
        bars = await self._get_price_data(instrument_id, timeframe, period + 1, end_date)
        if len(bars) < period + 1:
            return None

        closes = np.array([float(b.close) for b in bars])
        returns = np.diff(np.log(closes))
        vol = np.std(returns[-period:]) * np.sqrt(252)  # Annualized
        return Decimal(str(round(vol * 100, 4)))  # As percentage

    async def calculate_roc(
        self,
        instrument_id: UUID,
        period: int = 12,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> Decimal | None:
        """Calculate Rate of Change."""
        bars = await self._get_price_data(instrument_id, timeframe, period + 1, end_date)
        if len(bars) < period + 1:
            return None

        current_close = float(bars[-1].close)
        past_close = float(bars[-period - 1].close)

        if past_close == 0:
            return None

        roc = ((current_close - past_close) / past_close) * 100
        return Decimal(str(round(roc, 4)))

    async def calculate_relative_volume(
        self,
        instrument_id: UUID,
        period: int = 20,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> Decimal | None:
        """Calculate relative volume (current vs average)."""
        bars = await self._get_price_data(instrument_id, timeframe, period + 1, end_date)
        if len(bars) < period + 1:
            return None

        current_volume = float(bars[-1].volume)
        avg_volume = np.mean([float(b.volume) for b in bars[-period - 1:-1]])

        if avg_volume == 0:
            return None

        rel_vol = current_volume / avg_volume
        return Decimal(str(round(rel_vol, 4)))

    async def get_all_indicators(
        self,
        instrument_id: UUID,
        timeframe: str = "1d",
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Calculate all standard indicators."""
        results = {}

        # Trend indicators
        results["sma_20"] = await self.calculate_sma(instrument_id, 20, timeframe, end_date)
        results["sma_50"] = await self.calculate_sma(instrument_id, 50, timeframe, end_date)
        results["ema_20"] = await self.calculate_ema(instrument_id, 20, timeframe, end_date)
        results["ema_50"] = await self.calculate_ema(instrument_id, 50, timeframe, end_date)

        # Momentum indicators
        results["rsi_14"] = await self.calculate_rsi(instrument_id, 14, timeframe, end_date)
        results["macd"] = await self.calculate_macd(instrument_id, 12, 26, 9, timeframe, end_date)
        results["roc_12"] = await self.calculate_roc(instrument_id, 12, timeframe, end_date)

        # Volatility indicators
        results["bollinger_20"] = await self.calculate_bollinger_bands(
            instrument_id, 20, 2.0, timeframe, end_date
        )
        results["atr_14"] = await self.calculate_atr(instrument_id, 14, timeframe, end_date)
        results["volatility_20"] = await self.calculate_volatility(
            instrument_id, 20, timeframe, end_date
        )

        # Volume indicators
        results["relative_volume_20"] = await self.calculate_relative_volume(
            instrument_id, 20, timeframe, end_date
        )

        return results

    async def _get_price_data(
        self,
        instrument_id: UUID,
        timeframe: str,
        limit: int,
        end_date: datetime | None = None,
    ) -> list[PriceBar]:
        """Get price data for indicator calculations."""
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        start_date = end_date - timedelta(days=limit * 2)  # Buffer for weekends/holidays
        bars = await self.price_bar_repo.get_range(
            instrument_id, timeframe, start_date, end_date, limit
        )
        return bars
