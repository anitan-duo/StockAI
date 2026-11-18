from typing import Any, Optional

from apps.api.config import settings
from services.ingestion.providers.base import MarketDataProvider
from services.ingestion.providers.finnhub import FinnhubProvider
from services.ingestion.providers.twelvedata import TwelveDataProvider
from services.ingestion.providers.alphavantage import AlphaVantageProvider
from services.ingestion.providers.yahoo import YahooFinanceProvider
from services.ingestion.providers.google import GoogleFinanceProvider
from services.ingestion.providers.base import ProviderRouter, FallbackMarketDataProvider


def _is_yahoo_enabled() -> bool:
    return bool(getattr(settings, "yahoo_finance_enabled", getattr(settings, "yahoo_enabled", False)))


def _yahoo_rate_limit() -> int:
    return int(getattr(settings, "yahoo_finance_rate_limit", getattr(settings, "yahoo_rate_limit", 100)))


# Canonical market codes used by the DB seed are US / IN / EU.
# Providers were historically registered as US / India / Europe, which meant
# any live lookup with market_code IN or EU found zero providers and silently
# fell back to stale DB data. We register both spellings and normalize lookups.
MARKET_CODE_ALIASES: dict[str, str] = {
    "US": "US",
    "USA": "US",
    "IN": "India",
    "INDIA": "India",
    "EU": "Europe",
    "EUROPE": "Europe",
    "GLOBAL": "Global",
}

CANONICAL_GROUPS: dict[str, list[str]] = {
    "US": ["US"],
    "India": ["India", "IN"],
    "Europe": ["Europe", "EU"],
    "Global": ["Global"],
}


def normalize_market_code(code: str | None) -> str | None:
    if not code:
        return code
    return MARKET_CODE_ALIASES.get(code.strip().upper(), code)


class ProviderFactory:
    """Factory for creating market data providers."""

    _router: Optional[ProviderRouter] = None
    _fallback_provider: Optional[FallbackMarketDataProvider] = None

    @classmethod
    def get_router(cls) -> ProviderRouter:
        """Get or create the provider router."""
        if cls._router is None:
            cls._router = ProviderRouter()
            cls._initialize_router(cls._router)
        return cls._router

    @classmethod
    def _initialize_router(cls, router: ProviderRouter) -> None:
        """Initialize router with all available providers."""
        # Preferred order per spec: Alpha Vantage -> Twelve Data -> Finnhub -> Yahoo -> Google fallback
        # Register under both canonical names (India/Europe) and DB codes (IN/EU)
        # so live lookups never silently miss because of a code-spelling mismatch.
        market_keys = ["US", "India", "IN", "Europe", "EU"]
        for mkt in market_keys:
            if settings.alphavantage_enabled:
                router.register_provider(mkt, AlphaVantageProvider(
                    api_key=settings.alphavantage_api_key,
                    rate_limit=settings.alphavantage_rate_limit,
                ), priority=0)

            if settings.twelvedata_enabled:
                router.register_provider(mkt, TwelveDataProvider(
                    api_key=settings.twelvedata_api_key,
                    rate_limit=settings.twelvedata_rate_limit,
                ), priority=1)

            if settings.finnhub_enabled:
                router.register_provider(mkt, FinnhubProvider(
                    api_key=settings.finnhub_api_key,
                    rate_limit=settings.finnhub_rate_limit,
                ), priority=2)

            if _is_yahoo_enabled():
                router.register_provider(mkt, YahooFinanceProvider(
                    rate_limit=_yahoo_rate_limit(),
                ), priority=3)

        # Global fallback - Yahoo Finance
        if _is_yahoo_enabled():
            router.register_provider("Global", YahooFinanceProvider(
                rate_limit=_yahoo_rate_limit(),
            ), priority=0)

        # Google Finance as fallback for all (not required)
        if settings.google_finance_enabled:
            for market in ["US", "India", "IN", "Europe", "EU", "Global"]:
                router.register_provider(market, GoogleFinanceProvider(
                    rate_limit=settings.google_finance_rate_limit,
                ), priority=99)  # Low priority fallback

    @classmethod
    def get_fallback_provider(cls) -> FallbackMarketDataProvider:
        """Get the fallback provider instance."""
        if cls._fallback_provider is None:
            cls._fallback_provider = FallbackMarketDataProvider(cls.get_router())
        return cls._fallback_provider

    @classmethod
    def get_provider(cls, market: str, name: str) -> Optional[Any]:
        """Get specific provider by market and name."""
        router = cls.get_router()
        providers = router.get_all_providers(market)

        name_lower = name.lower()
        provider_map = {
            "finnhub": FinnhubProvider,
            "twelvedata": TwelveDataProvider,
            "alphavantage": AlphaVantageProvider,
            "yahoo": YahooFinanceProvider,
            "google": GoogleFinanceProvider,
        }

        if name_lower not in provider_map:
            return None

        for provider in providers:
            if isinstance(provider, provider_map[name_lower]):
                return provider

        return None

    @classmethod
    async def close_all(cls) -> None:
        """Close all providers."""
        router = cls.get_router()
        for providers in router.providers.values():
            for provider in providers:
                if hasattr(provider, "close"):
                    await provider.close()
