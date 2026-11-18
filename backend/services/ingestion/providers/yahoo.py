import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    yf = None  # type: ignore
    pd = None  # type: ignore

from services.ingestion.providers.base import (
    HistoricalPriceData,
    InstrumentInfo,
    MarketDataProvider,
    MarketStatusData,
    MarketStatus,
    QuoteData,
    ProviderDataError,
)


def _to_utc_datetime(ts):
    """Convert a pandas timestamp to an aware UTC datetime correctly.

    yfinance returns a tz-aware index in the exchange's local timezone for
    intraday bars and (depending on version) either tz-aware exchange-local
    or naive timestamps for daily bars. `replace(tzinfo=utc)` would relabel
    exchange-local wall time as UTC without shifting it (a correctness bug);
    converting with astimezone preserves the true instant.
    """
    dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    if dt.tzinfo is None:
        # Naive timestamps from yfinance are exchange-local; treat the
        # session convention conservatively by localizing to UTC only when
        # we cannot know the exchange tz — but yfinance daily bars are
        # midnight exchange-local, so localize to the exchange tz is not
        # recoverable here. yfinance >= 0.2 returns tz-aware for history();
        # naive is treated as UTC to keep a well-defined instant.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class YahooFinanceProvider(MarketDataProvider):
    """Yahoo Finance market data provider using yfinance."""

    def __init__(
        self,
        rate_limit: int = 100,
        timeout: float = 30.0,
    ):
        self._rate_limit_value = rate_limit
        self.timeout = timeout
        self._request_times: list[float] = []
        self._lock = asyncio.Lock()
        self._ticker_cache = {}

    @property
    def name(self) -> str:
        return "yahoo_finance"

    @property
    def supported_markets(self) -> list[str]:
        return ["US", "India", "Europe", "Global"]

    @property
    def rate_limit(self) -> int:
        return self._rate_limit_value

    @rate_limit.setter
    def rate_limit(self, value: int) -> None:
        self._rate_limit_value = value

    async def _enforce_rate_limit(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            self._request_times = [t for t in self._request_times if now - t < 60]
            if len(self._request_times) >= self._rate_limit_value:
                wait_time = 60 - (now - self._request_times[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            self._request_times.append(now)

    def _get_yf_symbol(self, symbol: str, exchange: str, market: Optional[str] = None) -> str:
        """Convert symbol/exchange to yfinance format."""
        # Yahoo Finance uses different formats for different markets
        if exchange.upper() == "NSE":
            return f"{symbol}.NS"
        elif exchange.upper() == "BSE":
            return f"{symbol}.BO"
        elif exchange.upper() in ["LSE", "LONDON"]:
            return f"{symbol}.L"
        elif exchange.upper() == "XETRA":
            return f"{symbol}.DE"
        elif exchange.upper() in ["EURONEXT", "XAMS", "EPA"]:
            return f"{symbol}.AS"
        elif exchange.upper() == "SIX":
            return f"{symbol}.SW"
        elif exchange.upper() == "TSX":
            return f"{symbol}.TO"
        elif exchange.upper() == "ASX":
            return f"{symbol}.AX"
        else:
            # Default to US format
            return symbol

    def _get_ticker(self, symbol: str, exchange: str, market: Optional[str] = None):
        """Get or create yfinance Ticker object."""
        if yf is None:
            raise ProviderDataError(self.name, "yfinance not installed")
        """Get or create yfinance Ticker object."""
        yf_symbol = self._get_yf_symbol(symbol, exchange)
        cache_key = f"{symbol}:{exchange}"

        if cache_key not in self._ticker_cache:
            self._ticker_cache[cache_key] = yf.Ticker(yf_symbol)
        return self._ticker_cache[cache_key]

    async def search_instruments(
        self,
        query: str,
        limit: int = 20,
        market: Optional[str] = None,
    ) -> list[InstrumentInfo]:
        # Yahoo Finance doesn't have a search API via yfinance
        # We would need to use a different endpoint or scrape
        # For now, return empty - this would need a separate search implementation
        return []

    async def get_instrument(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[InstrumentInfo]:
        if yf is None:
            return None
        await self._enforce_rate_limit()

        try:
            ticker = self._get_ticker(symbol, exchange)
            info = await asyncio.get_event_loop().run_in_executor(None, lambda: ticker.info)

            if not info or "symbol" not in info:
                return None

            return InstrumentInfo(
                symbol=info.get("symbol", symbol),
                name=info.get("longName", info.get("shortName", "")),
                exchange=info.get("exchange", exchange),
                currency=info.get("currency", "USD"),
                type=info.get("quoteType", "equity"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                market_cap=info.get("marketCap"),
                metadata={"yfinance_symbol": info.get("symbol")},
            )
        except Exception as e:
            raise ProviderDataError(self.name, f"Get instrument failed: {e}", e)

    async def get_quote(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[QuoteData]:
        if yf is None:
            return None
        await self._enforce_rate_limit()

        try:
            ticker = self._get_ticker(symbol, exchange)
            info = await asyncio.get_event_loop().run_in_executor(None, lambda: ticker.info)

            if not info:
                return None

            current = Decimal(str(info.get("currentPrice", info.get("regularMarketPrice", 0))))
            previous_close = Decimal(str(info.get("previousClose", info.get("regularMarketPreviousClose", 0))))
            change = current - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else Decimal("0")

            # Source instant from regularMarketTime (epoch seconds). The
            # quote is only as fresh as the provider's own timestamp —
            # stamping fetch time would relabel Friday's close as live on
            # a Sunday. Fall back to fetch time only when absent.
            source_ts = None
            rmt = info.get("regularMarketTime")
            if isinstance(rmt, (int, float)) and rmt > 0:
                source_ts = datetime.fromtimestamp(rmt, tz=timezone.utc)
            fetch_ts = datetime.now(timezone.utc)
            quote_ts = source_ts or fetch_ts

            state_map = {
                "REGULAR": "open",
                "PRE": "pre-market",
                "PREPRE": "pre-market",
                "POST": "after-hours",
                "POSTPOST": "after-hours",
                "CLOSED": "closed",
            }
            market_status = state_map.get(str(info.get("marketState", "")).upper(), "unknown")
            # If we could not establish a source instant, claiming any
            # session state would be a guess; classify conservatively.
            if source_ts is None:
                market_status = "unknown"

            same_day = quote_ts.date() == fetch_ts.date()
            return QuoteData(
                symbol=symbol,
                price=current,
                change=change,
                change_percent=change_percent.quantize(Decimal("0.01")),
                volume=int(info.get("volume", info.get("regularMarketVolume", 0))),
                high=Decimal(str(info.get("dayHigh", info.get("regularMarketDayHigh", 0)))),
                low=Decimal(str(info.get("dayLow", info.get("regularMarketDayLow", 0)))),
                open=Decimal(str(info.get("open", info.get("regularMarketOpen", 0)))),
                previous_close=previous_close,
                timestamp=quote_ts,
                market_status=market_status,
                data_status=MarketStatus.LIVE if same_day else MarketStatus.END_OF_DAY,
                provider=self.name,
                metadata={
                    "currency": info.get("currency", "USD"),
                    "exchange": info.get("exchange"),
                    "source_timestamp": info.get("regularMarketTime"),
                    "fetch_time": fetch_ts.isoformat(),
                },
            )
        except Exception as e:
            raise ProviderDataError(self.name, f"Quote failed: {e}", e)

    async def get_historical_prices(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        market: Optional[str] = None,
    ) -> list[HistoricalPriceData]:
        if yf is None or pd is None:
            return []
        await self._enforce_rate_limit()

        try:
            ticker = self._get_ticker(symbol, exchange)

            interval_map = {
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "1h": "1h",
                "1d": "1d",
                "1w": "1wk",
                "1M": "1mo",
            }
            interval = interval_map.get(timeframe, "1d")

            # yfinance history method
            hist = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ticker.history(
                    start=start.strftime("%Y-%m-%d"),
                    end=end.strftime("%Y-%m-%d"),
                    interval=interval,
                    auto_adjust=False,
                )
            )

            if hist.empty:
                return []

            prices = []
            for timestamp, row in hist.iterrows():
                ts = _to_utc_datetime(timestamp)
                prices.append(HistoricalPriceData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close=Decimal(str(row["Close"])),
                    volume=int(row["Volume"]),
                    adjusted_close=Decimal(str(row["Close"])) if "Adj Close" not in row else Decimal(str(row["Adj Close"])),
                ))

            return prices
        except Exception as e:
            raise ProviderDataError(self.name, f"Historical prices failed: {e}", e)

    async def get_market_status(
        self,
        market: str,
        exchange: Optional[str] = None,
    ) -> Optional[MarketStatusData]:
        return None

    async def health_check(self) -> bool:
        if yf is None:
            return False
        try:
            ticker = yf.Ticker("AAPL")
            info = await asyncio.get_event_loop().run_in_executor(None, lambda: ticker.info)
            return info is not None and "symbol" in info
        except Exception:
            return False

    async def close(self) -> None:
        pass