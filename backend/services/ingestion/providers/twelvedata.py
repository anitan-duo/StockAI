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


class TwelveDataProvider(MarketDataProvider):
    """Twelve Data market data provider."""

    BASE_URL = "https://api.twelvedata.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit: int = 800,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")
        self._rate_limit_value = rate_limit
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_times: list[float] = []
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "twelvedata"

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

    def _build_url(self, endpoint: str, params: dict) -> str:
        params["apikey"] = self.api_key
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}/{endpoint}?{query}"

    async def _request(self, endpoint: str, params: dict) -> dict:
        await self._enforce_rate_limit()
        client = await self._get_client()
        url = self._build_url(endpoint, params)

        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == 429:
                raise ProviderRateLimitError(self.name)
            if data.get("status") == "error":
                raise ProviderDataError(self.name, data.get("message", "Unknown error"))
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
            data = await self._request("symbol_search", {
                "symbol": query,
                "outputsize": limit,
            })

            results = data.get("data", [])
            instruments = []

            for item in results[:limit]:
                instruments.append(InstrumentInfo(
                    symbol=item.get("symbol", ""),
                    name=item.get("instrument_name", ""),
                    exchange=item.get("exchange", ""),
                    currency=item.get("currency", "USD"),
                    type=item.get("instrument_type", "equity"),
                    sector=item.get("sector"),
                    industry=item.get("industry"),
                    metadata={"twelvedata_symbol": item.get("symbol")},
                ))

            return instruments
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
            # Use profile endpoint
            data = await self._request("profile", {"symbol": f"{symbol}:{exchange}"})
            if data.get("status") == "error":
                return None

            return InstrumentInfo(
                symbol=data.get("symbol", symbol),
                name=data.get("name", ""),
                exchange=data.get("exchange", exchange),
                currency=data.get("currency", "USD"),
                type=data.get("type", "equity"),
                sector=data.get("sector"),
                industry=data.get("industry"),
                market_cap=data.get("market_capitalization"),
                metadata={"twelvedata_symbol": symbol},
            )
        except ProviderError:
            raise
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
            # timezone=UTC makes the "datetime" field an unambiguous UTC
            # instant (it defaults to exchange-local wall time).
            data = await self._request("quote", {"symbol": f"{symbol}:{exchange}", "timezone": "UTC"})

            if not data or "close" not in data:
                return None

            current = Decimal(str(data.get("close", 0)))
            previous_close = Decimal(str(data.get("previous_close", 0)))
            change = current - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else Decimal("0")

            # The quote's own datetime is the source instant; stamping
            # fetch time would overstate freshness off-session.
            source_ts = None
            dt_str = data.get("datetime")
            if dt_str:
                try:
                    source_ts = datetime.fromisoformat(str(dt_str).replace(" ", "T", 1)).replace(tzinfo=timezone.utc)
                except ValueError:
                    source_ts = None
            fetch_ts = datetime.now(timezone.utc)
            quote_ts = source_ts or fetch_ts
            same_day = quote_ts.date() == fetch_ts.date()

            return QuoteData(
                symbol=symbol,
                price=current,
                change=change,
                change_percent=change_percent.quantize(Decimal("0.01")),
                volume=int(data.get("volume", 0)),
                high=Decimal(str(data.get("high", 0))),
                low=Decimal(str(data.get("low", 0))),
                open=Decimal(str(data.get("open", 0))),
                previous_close=previous_close,
                timestamp=quote_ts,
                market_status="open" if data.get("is_market_open") else "closed",
                data_status=MarketStatus.LIVE if same_day else MarketStatus.END_OF_DAY,
                provider=self.name,
                metadata={
                    "source_timestamp": dt_str,
                    "fetch_time": fetch_ts.isoformat(),
                },
            )
        except ProviderError:
            raise
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
            interval_map = {
                "1m": "1min",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "1h": "1h",
                "1d": "1day",
                "1w": "1week",
                "1M": "1month",
            }
            interval = interval_map.get(timeframe, "1day")

            start_str = start.strftime("%Y-%m-%d")
            end_str = end.strftime("%Y-%m-%d")

            data = await self._request("time_series", {
                "symbol": f"{symbol}:{exchange}",
                "interval": interval,
                "start_date": start_str,
                "end_date": end_str,
                "outputsize": 5000,
            })

            if data.get("status") == "error":
                return []

            prices = []
            for item in data.get("values", []):
                timestamp = datetime.fromisoformat(item["datetime"].replace("Z", "+00:00"))
                prices.append(HistoricalPriceData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    open=Decimal(str(item["open"])),
                    high=Decimal(str(item["high"])),
                    low=Decimal(str(item["low"])),
                    close=Decimal(str(item["close"])),
                    volume=int(item["volume"]),
                ))

            return prices
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderDataError(self.name, f"Historical prices failed: {e}", e)

    async def get_market_status(
        self,
        market: str,
        exchange: Optional[str] = None,
    ) -> Optional[MarketStatusData]:
        # Twelve Data doesn't have market status endpoint
        now = datetime.now(timezone.utc)
        return MarketStatusData(
            market=market,
            exchange=exchange or "",
            is_open=True,
            metadata={"provider": self.name},
        )

    async def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            await self._request("quote", {"symbol": "AAPL:NASDAQ"})
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()