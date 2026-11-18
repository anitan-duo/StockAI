from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from enum import Enum


class MarketStatus(str, Enum):
    """Market status enumeration."""

    LIVE = "live"
    DELAYED = "delayed"
    END_OF_DAY = "end_of_day"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class ProviderError(Exception):
    """Base provider error."""

    def __init__(self, message: str, provider: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.provider = provider
        self.original_error = original_error


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded error."""

    def __init__(self, provider: str, retry_after: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__("Rate limit exceeded", provider, original_error)
        self.retry_after = retry_after


class ProviderTimeoutError(ProviderError):
    """Provider timeout error."""

    def __init__(self, provider: str, original_error: Optional[Exception] = None):
        super().__init__("Provider timeout", provider, original_error)


class ProviderDataError(ProviderError):
    """Provider returned invalid data."""

    def __init__(self, provider: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(message, provider, original_error)


class ProviderAuthenticationError(ProviderError):
    """Provider authentication failed."""

    def __init__(self, provider: str, original_error: Optional[Exception] = None):
        super().__init__("Authentication failed", provider, original_error)


@dataclass
class InstrumentInfo:
    """Instrument information from provider."""

    symbol: str
    name: str
    exchange: str
    currency: str
    type: str = "equity"
    isin: Optional[str] = None
    cusip: Optional[str] = None
    figi: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[int] = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class QuoteData:
    """Real-time quote data from provider."""

    symbol: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    volume: int
    high: Decimal
    low: Decimal
    open: Decimal
    previous_close: Decimal
    timestamp: datetime
    market_status: str
    data_status: MarketStatus = MarketStatus.LIVE
    provider: str = ""
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class HistoricalPriceData:
    """Historical price data from provider."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Optional[Decimal] = None
    adjusted_close: Optional[Decimal] = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class MarketStatusData:
    """Market status data from provider."""

    market: str
    exchange: str
    is_open: bool
    next_open: Optional[datetime] = None
    next_close: Optional[datetime] = None
    current_session: Optional[str] = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def supported_markets(self) -> list[str]:
        """List of supported markets (e.g., 'US', 'India', 'Europe')."""
        pass

    @property
    @abstractmethod
    def rate_limit(self) -> int:
        """Requests per minute."""
        pass

    @abstractmethod
    async def search_instruments(
        self,
        query: str,
        limit: int = 20,
        market: Optional[str] = None,
    ) -> list[InstrumentInfo]:
        """Search for instruments by symbol or name."""
        pass

    @abstractmethod
    async def get_instrument(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[InstrumentInfo]:
        """Get instrument details."""
        pass

    @abstractmethod
    async def get_quote(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[QuoteData]:
        """Get real-time quote for an instrument."""
        pass

    @abstractmethod
    async def get_historical_prices(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        market: Optional[str] = None,
    ) -> list[HistoricalPriceData]:
        """Get historical prices for an instrument."""
        pass

    @abstractmethod
    async def get_market_status(
        self,
        market: str,
        exchange: Optional[str] = None,
    ) -> Optional[MarketStatusData]:
        """Get market status."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is healthy."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close provider connections."""
        pass


class ProviderRouter:
    """
    Routes requests to appropriate provider with fallback.
    """

    def __init__(self):
        self.providers: dict[str, list[MarketDataProvider]] = {}  # market -> [providers in priority order]

    def register_provider(
        self,
        market: str,
        provider: MarketDataProvider,
        priority: int = 0,
    ) -> None:
        """Register a provider for a market."""
        if market not in self.providers:
            self.providers[market] = []

        # Insert at priority position
        self.providers[market].insert(priority, provider)

    def get_provider(self, market: str) -> Optional[MarketDataProvider]:
        """Get the first available provider for a market."""
        providers = self.providers.get(market, [])
        if not providers:
            return None
        return providers[0]

    def get_all_providers(self, market: str) -> list[MarketDataProvider]:
        """Get all providers for a market in priority order."""
        # Normalize common aliases so DB codes (IN/EU) and display names
        # (India/Europe) resolve to the same provider set.
        if market in self.providers and self.providers[market]:
            return self.providers[market]
        alias_map = {
            "IN": "India", "INDIA": "India",
            "EU": "Europe", "EUROPE": "Europe",
            "US": "US", "USA": "US",
        }
        normalized = alias_map.get(str(market).strip().upper(), market)
        if normalized in self.providers:
            return self.providers[normalized]
        # Reverse lookup: e.g. router has IN but caller asked India
        for key, providers in self.providers.items():
            if alias_map.get(key.strip().upper(), key) == normalized and providers:
                return providers
        return self.providers.get(market, [])


class FallbackMarketDataProvider:
    """
    Market data provider with automatic fallback.
    """

    def __init__(self, router: ProviderRouter):
        self.router = router

    @property
    def name(self) -> str:
        return "fallback"

    @property
    def supported_markets(self) -> list[str]:
        return list(self.router.providers.keys())

    @property
    def rate_limit(self) -> int:
        return 100

    async def close(self) -> None:
        for providers in self.router.providers.values():
            for p in providers:
                if hasattr(p, "close"):
                    try:
                        await p.close()
                    except Exception:
                        pass

    async def search_instruments(
        self,
        query: str,
        limit: int = 20,
        market: Optional[str] = None,
    ) -> list[InstrumentInfo]:
        """Search with fallback."""
        markets = [market] if market else self.router.providers.keys()

        for mkt in markets:
            providers = self.router.get_all_providers(mkt)
            for provider in providers:
                try:
                    return await provider.search_instruments(query, limit, mkt)
                except ProviderError:
                    continue

        return []

    async def get_instrument(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[InstrumentInfo]:
        """Get instrument with fallback."""
        markets = [market] if market else self.router.providers.keys()

        for mkt in markets:
            providers = self.router.get_all_providers(mkt)
            for provider in providers:
                try:
                    return await provider.get_instrument(symbol, exchange, mkt)
                except ProviderError:
                    continue

        return None

    async def get_quote(
        self,
        symbol: str,
        exchange: str,
        market: Optional[str] = None,
    ) -> Optional[QuoteData]:
        """Get quote with fallback."""
        markets = [market] if market else self.router.providers.keys()

        for mkt in markets:
            providers = self.router.get_all_providers(mkt)
            for provider in providers:
                try:
                    quote = await provider.get_quote(symbol, exchange, mkt)
                    if quote:
                        quote.provider = provider.name
                        return quote
                except ProviderError:
                    continue

        return None

    async def get_historical_prices(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        market: Optional[str] = None,
    ) -> list[HistoricalPriceData]:
        """Get historical prices with fallback."""
        markets = [market] if market else self.router.providers.keys()

        for mkt in markets:
            providers = self.router.get_all_providers(mkt)
            for provider in providers:
                try:
                    prices = await provider.get_historical_prices(symbol, exchange, timeframe, start, end, mkt)
                    if prices:
                        # Stamp provenance so persistence layers record the real
                        # adapter (e.g. alphavantage), never just "fallback".
                        # Defensive getattr: the ABC guarantees .name, but a
                        # degraded/partial adapter must not break the loop.
                        provider_name = getattr(provider, "name", None) or type(provider).__name__
                        for bar in prices:
                            if isinstance(bar.metadata, dict):
                                bar.metadata.setdefault("provider", provider_name)
                        return prices
                except ProviderError:
                    continue

        return []

    async def get_market_status(
        self,
        market: str,
        exchange: Optional[str] = None,
    ) -> Optional[MarketStatusData]:
        """Get market status with fallback."""
        providers = self.router.get_all_providers(market)
        for provider in providers:
            try:
                return await provider.get_market_status(market, exchange)
            except ProviderError:
                continue

        return None

    async def health_check(self) -> bool:
        """Check if any provider is healthy."""
        for providers in self.router.providers.values():
            for provider in providers:
                if await provider.health_check():
                    return True
        return False