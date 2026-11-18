import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from services.ingestion.providers.base import (
    HistoricalPriceData,
    InstrumentInfo,
    MarketDataProvider,
    MarketStatusData,
    MarketStatus,
    QuoteData,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderDataError,
    ProviderAuthenticationError,
)


class AlphaVantageProvider(MarketDataProvider):
    """Alpha Vantage market data provider."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit: int = 5,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        self._rate_limit_value = rate_limit
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_times: list[float] = []
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "alphavantage"

    @property
    def supported_markets(self) -> list[str]:
        return ["US", "India", "Europe", "Global"]

    @property
    def rate_limit(self) -> int:
        return self._rate_limit_value

    @rate_limit.setter
    def rate_limit(self, value: int) -> None:
        self._rate_limit_value = value

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"User-Agent": "StockAI/1.0"},
            )
        return self._client

    async def _enforce_rate_limit(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            self._request_times = [t for t in self._request_times if now - t < 60]
            if len(self._request_times) >= self._rate_limit_value:
                wait_time = 60 - (now - self._request_times[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            self._request_times.append(now)

    async def _request(self, params: dict) -> dict:
        await self._enforce_rate_limit()
        client = await self._get_client()

        params["apikey"] = self.api_key
        try:
            response = await self._client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Check for Alpha Vantage specific errors
            if "Error Message" in data:
                raise ProviderDataError(self.name, data["Error Message"])
            if "Note" in data and "API call frequency" in data["Note"]:
                raise ProviderRateLimitError(self.name, 60)
            if "Information" in data and "API call frequency" in data["Information"]:
                raise ProviderRateLimitError(self.name, 60)

            return data
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(self.name, e)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise ProviderRateLimitError(self.name)
            elif e.response.status_code == 401:
                raise ProviderAuthenticationError(self.name, e)
            raise ProviderError(f"HTTP {e.response.status_code}", self.name, e)
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}", self.name, e)

    async def search_instruments(
        self,
        query: str,
        limit: int = 20,
        market: Optional[str] = None,
    ) -> list[InstrumentInfo]:
        if not self.api_key:
            return []

        try:
            data = await self._request({
                "function": "SYMBOL_SEARCH",
                "keywords": query,
            })

            results = data.get("bestMatches", [])
            instruments = []

            for item in results[:limit]:
                instruments.append(InstrumentInfo(
                    symbol=item.get("1. symbol", ""),
                    name=item.get("2. name", ""),
                    exchange=item.get("4. region", ""),
                    currency=item.get("8. currency", "USD"),
                    type=item.get("3. type", "equity"),
                    metadata={"alphavantage_symbol": item.get("1. symbol")},
                ))

            return instruments[:limit]
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderDataError(self.name, f"Search failed: {e}", e)

    async def get_instrument(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[InstrumentInfo]:
        if not self.api_key:
            return None

        try:
            data = await self._request({
                "function": "OVERVIEW",
                "symbol": symbol,
            })

            if not data or "Symbol" not in data:
                return None

            return InstrumentInfo(
                symbol=data.get("Symbol", symbol),
                name=data.get("Name", ""),
                exchange=data.get("Exchange", exchange),
                currency=data.get("Currency", "USD"),
                type=data.get("AssetType", "equity"),
                sector=data.get("Sector"),
                industry=data.get("Industry"),
                market_cap=int(data.get("MarketCapitalization", 0)) if data.get("MarketCapitalization") else None,
                metadata={"alphavantage_symbol": symbol},
            )
        except Exception as e:
            raise ProviderDataError(self.name, f"Get instrument failed: {e}", e)

    async def get_quote(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[QuoteData]:
        if not self.api_key:
            return None

        try:
            data = await self._request({
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
            })

            quote = data.get("Global Quote", {})
            if not quote:
                return None

            current = Decimal(str(quote.get("05. price", 0)))
            previous_close = Decimal(str(quote.get("08. previous close", 0)))
            change = current - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else Decimal("0")

            # GLOBAL_QUOTE carries no quote timestamp — only the latest
            # trading day (a bare date). Reporting fetch time would
            # relabel a prior session's close as a live quote, so the
            # trading day is used as the conservative source instant and
            # flagged `source_date_only` for route-level refinement.
            trading_day_str = quote.get("07. latest trading day")
            source_ts = None
            if trading_day_str:
                try:
                    source_ts = datetime.strptime(
                        str(trading_day_str)[:10], "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    source_ts = None
            fetch_ts = datetime.now(timezone.utc)
            quote_ts = source_ts or fetch_ts
            same_day = source_ts is not None and source_ts.date() == fetch_ts.date()

            return QuoteData(
                symbol=symbol,
                price=current,
                change=change,
                change_percent=change_percent.quantize(Decimal("0.01")),
                volume=int(quote.get("06. volume", 0)),
                high=Decimal(str(quote.get("03. high", 0))),
                low=Decimal(str(quote.get("04. low", 0))),
                open=Decimal(str(quote.get("02. open", 0))),
                previous_close=previous_close,
                timestamp=quote_ts,
                # Prior-session data is definitely not an open session;
                # same-day session state is derived by the route from the
                # market calendar.
                market_status="closed" if source_ts is not None and not same_day else "unknown",
                data_status=MarketStatus.END_OF_DAY if (source_ts is not None and not same_day) else MarketStatus.LIVE,
                provider=self.name,
                metadata={
                    "latest_trading_day": str(trading_day_str) if trading_day_str else None,
                    "source_date_only": source_ts is not None,
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
        if not self.api_key:
            return []

        try:
            function_map = {
                "1d": "TIME_SERIES_DAILY_ADJUSTED",
                "1w": "TIME_SERIES_WEEKLY_ADJUSTED",
                "1M": "TIME_SERIES_MONTHLY_ADJUSTED",
            }
            function = function_map.get(timeframe, "TIME_SERIES_DAILY_ADJUSTED")

            data = await self._request({
                "function": function,
                "symbol": symbol,
                "outputsize": "full",
            })

            time_series_key = [k for k in data.keys() if "Time Series" in k]
            if not time_series_key:
                return []

            ts_data = data[time_series_key[0]]
            prices = []

            for date_str, values in ts_data.items():
                timestamp = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

                if timestamp < start.replace(tzinfo=timezone.utc) or timestamp > end.replace(tzinfo=timezone.utc):
                    continue

                prices.append(HistoricalPriceData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    open=Decimal(str(values.get("1. open", 0))),
                    high=Decimal(str(values.get("2. high", 0))),
                    low=Decimal(str(values.get("3. low", 0))),
                    close=Decimal(str(values.get("4. close", 0))),
                    volume=int(values.get("5. volume", 0)),
                    adjusted_close=Decimal(str(values.get("5. adjusted close", 0))) if "5. adjusted close" in values else None,
                ))

            return sorted(prices, key=lambda x: x.timestamp)
        except Exception as e:
            raise ProviderDataError(self.name, f"Historical prices failed: {e}", e)

    async def get_market_status(
        self,
        market: str,
        exchange: Optional[str] = None,
    ) -> Optional[MarketStatusData]:
        return None  # Alpha Vantage doesn't provide market status
    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            await self._request({"function": "GLOBAL_QUOTE", "symbol": "AAPL"})
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()