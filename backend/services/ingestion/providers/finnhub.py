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


class FinnhubProvider(MarketDataProvider):
    """Finnhub market data provider."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit: int = 60,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY")
        self._rate_limit_value = rate_limit
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_times: list[float] = []
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "finnhub"

    @property
    def supported_markets(self) -> list[str]:
        return ["US", "Europe"]

    @property
    def rate_limit(self) -> int:
        return self._rate_limit_value

    @rate_limit.setter
    def rate_limit(self, value: int) -> None:
        self._rate_limit_value = value

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "User-Agent": "StockAI/1.0",
                },
            )
        return self._client

    async def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            # Remove requests older than 1 minute
            self._request_times = [t for t in self._request_times if now - t < 60]

            if len(self._request_times) >= self._rate_limit_value:
                wait_time = 60 - (now - self._request_times[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            self._request_times.append(now)

    def _build_url(self, endpoint: str, params: dict) -> str:
        """Build API URL with API key."""
        params["token"] = self.api_key
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}/{endpoint}?{query}"

    async def _request(self, endpoint: str, params: dict) -> dict:
        """Make API request with rate limiting and error handling."""
        await self._enforce_rate_limit()
        client = await self._get_client()

        url = self._build_url(endpoint, params)
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(self.name, e)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise ProviderRateLimitError(self.name, retry_after, e)
            elif e.response.status_code == 401:
                raise ProviderAuthenticationError(self.name, e)
            else:
                raise ProviderError(f"HTTP {e.response.status_code}: {e.response.text}", self.name, e)
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}", self.name, e)

    async def search_instruments(
        self,
        query: str,
        limit: int = 20,
        market: Optional[str] = None,
    ) -> list[InstrumentInfo]:
        """Search for instruments."""
        if not self.api_key:
            return []

        try:
            data = await self._request("search", {"q": query})
            results = data.get("result", [])

            instruments = []
            for item in results[:limit]:
                # Filter by market if specified
                if market:
                    exchange = item.get("exchange", "")
                    if market == "US" and exchange not in ["NASDAQ", "NYSE", "NYSE ARCA", "BATS"]:
                        continue
                    if market == "Europe" and exchange not in ["LSE", "XETRA", "EURONEXT", "SIX"]:
                        continue

                instruments.append(InstrumentInfo(
                    symbol=item.get("symbol", ""),
                    name=item.get("description", ""),
                    exchange=item.get("exchange", ""),
                    currency=item.get("currency", "USD"),
                    type=item.get("type", "equity"),
                    metadata={"finnhub_symbol": item.get("symbol")},
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
        """Get instrument details."""
        if not self.api_key:
            return None

        try:
            # Finnhub doesn't have a direct profile endpoint by exchange
            # Use search and filter
            results = await self.search_instruments(symbol, limit=5, market=market)
            for inst in results:
                if inst.symbol.upper() == symbol.upper() and inst.exchange.upper() == exchange.upper():
                    return inst
            return None
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
        """Get real-time quote."""
        if not self.api_key:
            return None

        try:
            # Finnhub uses symbol format like "AAPL" for US
            data = await self._request("quote", {"symbol": symbol})

            if not data or "c" not in data:
                return None

            current = Decimal(str(data.get("c", 0)))
            previous_close = Decimal(str(data.get("pc", 0)))
            change = current - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else Decimal("0")

            # Finnhub's "t" is the quote's epoch — the honest source
            # instant. Stamping fetch time would overstate freshness (a
            # weekend fetch of Friday's close would look live).
            t = data.get("t")
            source_ts = (
                datetime.fromtimestamp(t, tz=timezone.utc)
                if isinstance(t, (int, float)) and t > 0
                else None
            )
            fetch_ts = datetime.now(timezone.utc)
            quote_ts = source_ts or fetch_ts
            same_day = quote_ts.date() == fetch_ts.date()

            return QuoteData(
                symbol=symbol,
                price=current,
                change=change,
                change_percent=change_percent.quantize(Decimal("0.01")),
                volume=int(data.get("v", 0)),
                high=Decimal(str(data.get("h", 0))),
                low=Decimal(str(data.get("l", 0))),
                open=Decimal(str(data.get("o", 0))),
                previous_close=previous_close,
                timestamp=quote_ts,
                # The quote payload carries no session state; the route
                # derives it from the market calendar.
                market_status="unknown",
                data_status=MarketStatus.LIVE if same_day else MarketStatus.END_OF_DAY,
                provider=self.name,
                metadata={
                    "source_timestamp": t,
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
        """Get historical prices."""
        if not self.api_key:
            return []

        try:
            # Convert timeframe to Finnhub resolution
            resolution_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "30m": "30",
                "1h": "60",
                "1d": "D",
                "1w": "W",
                "1M": "M",
            }
            resolution = resolution_map.get(timeframe, "D")

            start_ts = int(start.timestamp())
            end_ts = int(end.timestamp())

            data = await self._request("stock/candle", {
                "symbol": symbol,
                "resolution": resolution,
                "from": start_ts,
                "to": end_ts,
            })

            if data.get("s") != "ok":
                return []

            prices = []
            for i in range(len(data.get("t", []))):
                timestamp = datetime.fromtimestamp(data["t"][i], tz=timezone.utc)
                prices.append(HistoricalPriceData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    open=Decimal(str(data["o"][i])),
                    high=Decimal(str(data["h"][i])),
                    low=Decimal(str(data["l"][i])),
                    close=Decimal(str(data["c"][i])),
                    volume=int(data["v"][i]),
                    vwap=Decimal(str(data["o"][i] + data["h"][i] + data["l"][i] + data["c"][i])) / 4,
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
        """Get market status."""
        # Finnhub doesn't provide market status endpoint
        # Return a basic status
        now = datetime.now(timezone.utc)
        return MarketStatusData(
            market=market,
            exchange=exchange or "",
            is_open=True,  # Simplified
            metadata={"provider": self.name},
        )

    async def health_check(self) -> bool:
        """Check provider health."""
        if not self.api_key:
            return False

        try:
            # Simple quote request for health check
            await self._request("quote", {"symbol": "AAPL"})
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()