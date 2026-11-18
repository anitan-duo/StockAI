import asyncio
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

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


class GoogleFinanceProvider(MarketDataProvider):
    """Google Finance market data provider (web scraping fallback)."""

    BASE_URL = "https://www.google.com/finance"
    QUOTE_URL = f"{BASE_URL}/quote"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(
        self,
        rate_limit: int = 30,
        timeout: float = 30.0,
    ):
        self._rate_limit_value = rate_limit
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_times: list[float] = []
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "google_finance"

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
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
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

    async def _fetch_page(self, url: str) -> str:
        await self._enforce_rate_limit()
        client = await self._get_client()

        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(self.name, e)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise ProviderRateLimitError(self.name, retry_after, e)
            raise ProviderError(f"HTTP {e.response.status_code}", self.name, e)
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}", self.name, e)

    def _parse_price(self, text: str) -> Optional[Decimal]:
        if not text:
            return None
        cleaned = re.sub(r"[^\d.-]", "", text)
        try:
            return Decimal(cleaned)
        except Exception:
            return None

    def _parse_percent(self, text: str) -> Optional[Decimal]:
        if not text:
            return None
        cleaned = re.sub(r"[()%]", "", text)
        try:
            return Decimal(cleaned)
        except Exception:
            return None

    def _parse_volume(self, text: str) -> Optional[int]:
        if not text:
            return None
        text = text.upper().replace(",", "")
        multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
        for suffix, mult in multipliers.items():
            if text.endswith(suffix):
                try:
                    return int(float(text[:-1]) * mult)
                except Exception:
                    return None
        try:
            return int(text)
        except Exception:
            return None

    async def search_instruments(
        self,
        query: str,
        limit: int = 20,
        market: Optional[str] = None,
    ) -> list[InstrumentInfo]:
        if BeautifulSoup is None:
            return []
        url = f"{self.SEARCH_URL}?q={query}"
        try:
            html = await self._fetch_page(url)
            soup = BeautifulSoup(html, "html.parser")

            results = []
            for item in soup.select(".ZvmM7")[:limit]:
                try:
                    symbol_elem = item.select_one(".COaKTb")
                    name_elem = item.select_one(".ZvmM7 .E651vd")
                    exchange_elem = item.select_one(".ZvmM7 .Jp4zVd")

                    if symbol_elem and name_elem:
                        results.append(InstrumentInfo(
                            symbol=symbol_elem.get_text(strip=True),
                            name=name_elem.get_text(strip=True),
                            exchange=exchange_elem.get_text(strip=True) if exchange_elem else "UNKNOWN",
                            currency="USD",
                            metadata={"source": "google_finance_web"},
                        ))
                except Exception:
                    continue

            return results
        except Exception as e:
            raise ProviderDataError(self.name, f"Search failed: {e}", e)

    async def get_instrument(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[InstrumentInfo]:
        if BeautifulSoup is None:
            return None
        url = f"{self.QUOTE_URL}/{symbol}:{exchange}"
        try:
            html = await self._fetch_page(url)
            soup = BeautifulSoup(html, "html.parser")

            name_elem = soup.select_one(".zzDege")
            if not name_elem:
                return None

            return InstrumentInfo(
                symbol=symbol.upper(),
                name=name_elem.get_text(strip=True),
                exchange=exchange.upper(),
                currency="USD",
                metadata={"source": "google_finance_web"},
            )
        except Exception:
            return None

    async def get_quote(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[QuoteData]:
        if BeautifulSoup is None:
            return None
        url = f"{self.QUOTE_URL}/{symbol}:{exchange}"
        try:
            html = await self._fetch_page(url)
            soup = BeautifulSoup(html, "html.parser")

            price_elem = soup.select_one(".YMlKec.fxKbKc")
            change_elem = soup.select_one(".JwB6zf")
            volume_elem = soup.select_one("div[data-last-price]")

            if not price_elem:
                return None

            price = self._parse_price(price_elem.get_text())
            if price is None:
                return None

            change = Decimal("0")
            change_percent = Decimal("0")
            if change_elem:
                change_text = change_elem.get_text(strip=True)
                parts = change_text.split()
                if len(parts) >= 2:
                    change = self._parse_price(parts[0]) or Decimal("0")
                    change_percent = self._parse_percent(parts[1]) or Decimal("0")

            return QuoteData(
                symbol=symbol.upper(),
                price=price,
                change=change,
                change_percent=change_percent,
                volume=self._parse_volume(volume_elem.get_text()) if volume_elem else 0,
                high=price,
                low=price,
                open=price,
                previous_close=price - change,
                timestamp=datetime.now(timezone.utc),
                market_status="open",
                data_status="live",
                provider=self.name,
                metadata={"source": "google_finance_web"},
            )
        except Exception as e:
            raise ProviderDataError(self.name, f"Quote fetch failed: {e}", e)

    async def get_historical_prices(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        market: Optional[str] = None,
    ) -> list[HistoricalPriceData]:
        # Google Finance web doesn't easily provide historical data
        return []

    async def get_market_status(
        self,
        market: str,
        exchange: Optional[str] = None,
    ) -> Optional[MarketStatusData]:
        return MarketStatusData(
            market=market,
            exchange=exchange or "",
            is_open=True,
            metadata={"provider": self.name},
        )

    async def health_check(self) -> bool:
        try:
            await self._fetch_page(self.BASE_URL)
            return True
        except Exception:
            return False

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()