from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.market import Instrument, Exchange, Market
from apps.api.models.price import PriceBar, MarketSnapshot
from apps.api.repositories.market import (
    InstrumentRepository,
    PriceBarRepository,
    MarketSnapshotRepository,
    ExchangeRepository,
)
from services.ingestion.canonical_days import canonical_daily_timestamp
from services.ingestion.providers.base import (
    MarketDataProvider,
    QuoteData,
    HistoricalPriceData,
    ProviderError,
    MarketStatus,
)
from services.ingestion.providers.factory import ProviderFactory


class ValidationError(Exception):
    """Data validation error."""

    def __init__(self, message: str, field: str = "", value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value


class IngestionService:
    """Market data ingestion service."""

    def __init__(
        self,
        session: AsyncSession,
        provider: Optional[MarketDataProvider] = None,
    ):
        self.session = session
        self.provider = provider or ProviderFactory.get_fallback_provider()
        self.instrument_repo = InstrumentRepository(session)
        self.price_bar_repo = PriceBarRepository(session)
        self.snapshot_repo = MarketSnapshotRepository(session)
        self.exchange_repo = ExchangeRepository(session)

        # Ingestion stats
        self.stats = {
            "total_fetched": 0,
            "total_validated": 0,
            "total_persisted": 0,
            "total_errors": 0,
            "errors": [],
        }

    async def ingest_quotes(
        self,
        symbols: list[tuple[str, str, Optional[str]]],  # (symbol, exchange_code, market_code)
    ) -> dict[str, Any]:
        """Ingest real-time quotes for multiple instruments."""
        if not self.provider:
            return {"error": "No provider configured", "stats": self.stats}

        results = {"success": [], "failed": []}

        for symbol, exchange_code, market_code in symbols:
            try:
                # Isolate each symbol so one bad row never poisons the batch.
                async with self.session.begin_nested():
                    # Get exchange
                    exchange = await self.exchange_repo.get_by_code(exchange_code)
                    if not exchange:
                        raise ValidationError(f"Exchange {exchange_code} not found", "exchange", exchange_code)

                    # Get instrument
                    instrument = await self.instrument_repo.get_by_symbol_exchange(
                        symbol.upper(), exchange.id
                    )
                    if not instrument:
                        raise ValidationError("Instrument not found", "symbol", symbol)

                    # Fetch quote
                    quote = await self.provider.get_quote(symbol, exchange_code, market_code)
                    if not quote:
                        raise ProviderError("No quote data returned", provider=self.provider.name)

                    # Validate quote
                    self._validate_quote(quote)

                    # Persist snapshot
                    await self._persist_snapshot(instrument.id, quote)

                    # Also create a price bar for the current period
                    # (canonical session-day stamp for daily bars).
                    await self._create_price_bar_from_quote(
                        instrument.id, quote, "1d",
                        exchange_tz=getattr(exchange, "timezone", None),
                    )

                    results["success"].append(symbol)
                    self.stats["total_fetched"] += 1
                    self.stats["total_validated"] += 1
                    self.stats["total_persisted"] += 1

            except ValidationError as e:
                results["failed"].append(
                    {"symbol": symbol, "error": f"Validation failed: {e}"}
                )
                self.stats["total_errors"] += 1
            except ProviderError as e:
                results["failed"].append(
                    {"symbol": symbol, "error": f"Provider error: {e}"}
                )
                self.stats["total_errors"] += 1
            except Exception as e:
                results["failed"].append(
                    {"symbol": symbol, "error": f"Unexpected error: {e}"}
                )
                self.stats["total_errors"] += 1
                self.stats["errors"].append(
                    {"symbol": symbol, "error": str(e), "time": datetime.now(timezone.utc).isoformat()}
                )

        return results

    async def ingest_historical(
        self,
        symbol: str,
        exchange_code: str,
        market_code: Optional[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Ingest historical price data."""
        if not self.provider:
            return {"error": "No provider configured", "stats": self.stats}

        try:
            # Get exchange
            exchange = await self.exchange_repo.get_by_code(exchange_code)
            if not exchange:
                return {"error": f"Exchange {exchange_code} not found", "stats": self.stats}
            exchange_tz = getattr(exchange, "timezone", None)

            # Get instrument
            instrument = await self.instrument_repo.get_by_symbol_exchange(
                symbol.upper(), exchange.id
            )
            if not instrument:
                return {"error": "Instrument not found", "stats": self.stats}

            # Gap-aware duplicate avoidance: the old forward-only logic
            # (start = latest + 1us) could never heal interior gaps — e.g. a
            # series with bars through Aug-21 plus quote-derived bars in Oct
            # would never backfill September. Instead, load the timestamps we
            # already hold in [start, end] (indexed range scan) and skip only
            # those. bulk_upsert remains idempotent as a second guard.
            existing_ts = await self.price_bar_repo.get_timestamps_in_range(
                instrument.id, timeframe, start, end
            )
            existing_set = set(existing_ts)

            # Canonical trading-day stamping (BAR-002): providers stamp the
            # same session differently (UTC midnight vs exchange-local midnight
            # in UTC). Normalize every daily bar to ONE instant per session day
            # before gap-checking/upsert, or the same day is stored twice.
            def _canon(ts: datetime) -> datetime:
                return canonical_daily_timestamp(ts, timeframe, exchange_tz)

            # Fetch historical data for the full requested window.
            bars = await self.provider.get_historical_prices(
                symbol, exchange_code, timeframe, start, end, market_code
            )

            if not bars:
                return {"message": "No new data", "stats": self.stats}

            # Canonicalize, drop bars we already persist, then validate.
            canon_bars = []
            for b in bars:
                canon_ts = _canon(b.timestamp)
                if canon_ts != b.timestamp:
                    b.timestamp = canon_ts
                canon_bars.append(b)
            new_bars = [b for b in canon_bars if b.timestamp not in existing_set]
            if not new_bars:
                return {"message": "No new data", "stats": self.stats}

            # Validate and prepare for bulk insert
            valid_bars = []
            for bar in new_bars:
                try:
                    self._validate_price_bar(bar)
                    # Provenance: the real adapter name stamped by the fallback
                    # router (bar.metadata), never the generic "fallback".
                    source = (
                        bar.metadata.get("provider")
                        if isinstance(bar.metadata, dict) and bar.metadata.get("provider")
                        else self.provider.name
                    )
                    valid_bars.append(
                        {
                            "instrument_id": instrument.id,
                            "timestamp": bar.timestamp,
                            "timeframe": timeframe,
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                            "vwap": bar.vwap,
                            "source": source,
                        }
                    )
                    self.stats["total_validated"] += 1
                except ValidationError as e:
                    self.stats["total_errors"] += 1
                    self.stats["errors"].append(
                        {
                            "symbol": symbol,
                            "timestamp": bar.timestamp.isoformat(),
                            "error": str(e),
                        }
                    )

            # Bulk upsert
            if valid_bars:
                count = await self.price_bar_repo.bulk_upsert(valid_bars)
                self.stats["total_persisted"] += count
                self.stats["total_fetched"] += len(bars)

            return {
                "symbol": symbol,
                "fetched": len(bars),
                "validated": len(valid_bars),
                "persisted": len(valid_bars),
                "stats": self.stats,
            }

        except ProviderError as e:
            self.stats["total_errors"] += 1
            return {"error": f"Provider error: {e}", "stats": self.stats}
        except Exception as e:
            self.stats["total_errors"] += 1
            self.stats["errors"].append(
                {"symbol": symbol, "error": str(e), "time": datetime.now(timezone.utc).isoformat()}
            )
            return {"error": f"Unexpected error: {e}", "stats": self.stats}

    async def ingest_all_active(
        self,
        timeframe: str = "1d",
        limit: Optional[int] = None,
        market_codes: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Ingest quotes for all active instruments."""
        instruments = await self.instrument_repo.get_active_instruments(limit=limit)

        if market_codes:
            # Filter by market
            filtered = []
            for inst in instruments:
                if inst.exchange and inst.exchange.market and inst.exchange.market.code in market_codes:
                    filtered.append(inst)
            instruments = filtered

        symbols = [(inst.symbol, inst.exchange.code, inst.exchange.market.code if inst.exchange.market else None)
                   for inst in instruments]
        return await self.ingest_quotes(symbols)

    def _validate_quote(self, quote: QuoteData) -> None:
        """Validate quote data."""
        if quote.price <= 0:
            raise ValidationError("Price must be positive", "price", quote.price)

        if quote.volume < 0:
            raise ValidationError("Volume cannot be negative", "volume", quote.volume)

        # OHLC consistency (QuoteData carries live price; treat price as close)
        if quote.high < max(quote.open, quote.price, quote.low):
            raise ValidationError(
                "High must be >= max(open, close, low)", "high", quote.high
            )

        if quote.low > min(quote.open, quote.price, quote.high):
            raise ValidationError(
                "Low must be <= min(open, close, high)", "low", quote.low
            )

        # Intraday-range cap: all four quotes describe ONE session, so a
        # >5x spread is a unit/currency error, not volatility (observed:
        # INFY open 10.41 vs high 1009.00 from one provider payload).
        # Splits affect previous-close comparisons, never a single quote.
        lo = min(quote.open, quote.price, quote.low)
        hi = max(quote.open, quote.price, quote.high)
        if lo > 0 and hi / lo > 5:
            raise ValidationError(
                f"Intraday range impossible ({lo}–{hi}): unit error, not volatility",
                "high",
                quote.high,
            )

        # Check for stale data (> 24 hours old for live quote)
        age = datetime.now(timezone.utc) - quote.timestamp
        if age > timedelta(hours=24):
            raise ValidationError(
                f"Quote data is stale (age: {age})", "timestamp", quote.timestamp
            )

    def _validate_price_bar(self, bar: HistoricalPriceData) -> None:
        """Validate price bar data. Historical bars may legitimately be old
        (decades of daily history), so no stale-age rejection here — recency
        is enforced at read time (newest-biased get_range + freshness labels).
        Future timestamps are always rejected as data-integrity violations."""
        if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
            raise ValidationError("All prices must be positive", "prices", bar)

        if bar.volume < 0:
            raise ValidationError("Volume cannot be negative", "volume", bar.volume)

        # No-session bars: zero reported volume means the provider saw no
        # trading session (exchange holidays emit prev-close stubs; weekend
        # quotes carry no volume). Persisting them poisons trailing-window
        # features (vol_price_corr_20d goes NaN via inf pct-change and
        # inference fail-closes for weeks — observed Oct 2026 across 10
        # IN/EU symbols). Reject at the door; holidays remain honest gaps.
        # (A flat OHLC was previously the only rejected shape; Oct 2026
        # showed zero-volume bars WITH a range — equally session-less.)
        if bar.volume == 0:
            raise ValidationError(
                "Zero reported volume means no trading session occurred",
                "volume",
                bar.volume,
            )

        # Intraday-range cap (same unit-error rationale as quotes: INFY).
        if bar.low > 0 and bar.high / bar.low > 5:
            raise ValidationError(
                f"Intraday range impossible ({bar.low}–{bar.high})",
                "high",
                bar.high,
            )

        if bar.high < max(bar.open, bar.close, bar.low):
            raise ValidationError(
                "High must be >= max(open, close, low)", "high", bar.high
            )

        if bar.low > min(bar.open, bar.close, bar.high):
            raise ValidationError(
                "Low must be <= min(open, close, high)", "low", bar.low
            )

        now = datetime.now(timezone.utc)
        ts = bar.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts > now + timedelta(minutes=5):
            raise ValidationError(
                f"Bar timestamp is in the future: {bar.timestamp.isoformat()}",
                "timestamp",
                bar.timestamp,
            )

    async def _persist_snapshot(
        self, instrument_id: UUID, quote: QuoteData
    ) -> MarketSnapshot:
        """Persist market snapshot."""
        snapshot = MarketSnapshot(
            instrument_id=instrument_id,
            timestamp=quote.timestamp,
            price=quote.price,
            change=quote.change,
            change_percent=quote.change_percent,
            volume=quote.volume,
            high=quote.high,
            low=quote.low,
            open=quote.open,
            previous_close=quote.previous_close,
            market_status=quote.market_status,
            source=quote.provider,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def _create_price_bar_from_quote(
        self,
        instrument_id: UUID,
        quote: QuoteData,
        timeframe: str,
        exchange_tz: str | None = None,
    ) -> PriceBar | None:
        """Create or update price bar from quote (idempotent on re-ingestion).

        Returns None without persisting when the quote carries no volume:
        a volume-less quote is not evidence of a trading session (weekend /
        holiday quotes), and persisting it manufactures a session bar that
        poisons volume features. The snapshot path still records the quote
        itself with honest freshness. Provenance is the real adapter name
        carried on the quote, never the generic fallback label.
        """
        if quote.volume == 0:
            return None
        source = quote.provider or self.provider.name
        # Round timestamp to timeframe boundary (canonical session day for 1d).
        if timeframe == "1d":
            bar_timestamp = canonical_daily_timestamp(quote.timestamp, timeframe, exchange_tz)
        else:
            bar_timestamp = self._round_to_timeframe(quote.timestamp, timeframe)

        existing = await self.price_bar_repo.get_bar(
            instrument_id, bar_timestamp, timeframe
        )
        if existing is not None:
            existing.open = quote.open
            existing.high = max(existing.high, quote.high)
            existing.low = min(existing.low, quote.low)
            existing.close = quote.price
            existing.volume = quote.volume
            existing.source = source
            await self.session.flush()
            return existing

        bar = PriceBar(
            instrument_id=instrument_id,
            timestamp=bar_timestamp,
            timeframe=timeframe,
            open=quote.open,
            high=quote.high,
            low=quote.low,
            close=quote.price,
            volume=quote.volume,
            source=source,
        )
        self.session.add(bar)
        await self.session.flush()
        return bar

    def _round_to_timeframe(self, dt: datetime, timeframe: str) -> datetime:
        """Round datetime to timeframe boundary."""
        if timeframe == "1d":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "1h":
            return dt.replace(minute=0, second=0, microsecond=0)
        elif timeframe == "15m":
            minute = (dt.minute // 15) * 15
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "5m":
            minute = (dt.minute // 5) * 5
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "1m":
            return dt.replace(second=0, microsecond=0)
        return dt

    def get_stats(self) -> dict[str, Any]:
        """Get ingestion statistics."""
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset ingestion statistics."""
        self.stats = {
            "total_fetched": 0,
            "total_validated": 0,
            "total_persisted": 0,
            "total_errors": 0,
            "errors": [],
        }