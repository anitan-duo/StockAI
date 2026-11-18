# Data Pipeline Documentation

## Overview

The StockAI data pipeline handles market data ingestion, validation, normalization, and persistence.

## Pipeline Stages

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Provider   │───▶│   Fetch     │───▶│  Validate   │───▶│ Normalize   │───▶│  Persist    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                                                                │
       ▼                                                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Ingestion Status & Monitoring                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Provider Abstraction

### MarketDataProvider Interface

All providers implement the `MarketDataProvider` abstract base class:

```python
class MarketDataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def search_instruments(self, query: str, limit: int = 20) -> list[InstrumentInfo]: ...

    @abstractmethod
    async def get_instrument(self, symbol: str, exchange: str) -> Optional[InstrumentInfo]: ...

    @abstractmethod
    async def get_quote(self, symbol: str, exchange: str) -> Optional[QuoteData]: ...

    @abstractmethod
    async def get_historical_prices(
        self, symbol: str, exchange: str, timeframe: str,
        start: datetime, end: datetime
    ) -> list[HistoricalPriceData]: ...

    @abstractmethod
    async def get_market_status(self, market: str) -> Optional[MarketStatusData]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

### Built-in Providers

#### Google Finance Provider

- **File**: `services/ingestion/providers/google_finance.py`
- **Access**: Web scraping (fallback) + Official API (when available)
- **Rate Limit**: Configurable (default 100 req/min)
- **Features**: Quotes, basic instrument info

#### Adding a New Provider

1. Create `services/ingestion/providers/your_provider.py`
2. Implement `MarketDataProvider` interface
3. Register in `ProviderFactory`:

```python
from services.ingestion.providers.factory import ProviderFactory

ProviderFactory.register_provider("your_provider", YourProvider())
```

## Ingestion Service

### IngestionService

Main service orchestrating the pipeline:

```python
class IngestionService:
    async def ingest_quotes(
        self, symbols: list[tuple[str, str]], timeframe: str = "1d"
    ) -> dict[str, Any]: ...

    async def ingest_historical(
        self, symbol: str, exchange_code: str, timeframe: str,
        start: datetime, end: datetime
    ) -> dict[str, Any]: ...

    async def ingest_all_active(
        self, timeframe: str = "1d", limit: Optional[int] = None
    ) -> dict[str, Any]: ...
```

### Features

- **Batch Processing**: Process multiple symbols efficiently
- **Deduplication**: Upsert prevents duplicate price bars
- **Validation**: Comprehensive data quality checks
- **Error Tracking**: Detailed error logging per symbol
- **Statistics**: Real-time ingestion metrics

## Data Validation

### Quote Validation

```python
def _validate_quote(self, quote: QuoteData) -> None:
    # Price must be positive
    if quote.price <= 0:
        raise ValidationError("Price must be positive")

    # Volume cannot be negative
    if quote.volume < 0:
        raise ValidationError("Volume cannot be negative")

    # OHLC consistency
    if quote.high < max(quote.open, quote.close, quote.low):
        raise ValidationError("High must be >= max(open, close, low)")

    if quote.low > min(quote.open, quote.close, quote.high):
        raise ValidationError("Low must be <= min(open, close, high)")

    # Data freshness
    age = datetime.now(timezone.utc) - quote.timestamp
    if age > timedelta(hours=24):
        raise ValidationError(f"Quote data is stale (age: {age})")
```

### Price Bar Validation

```python
def _validate_price_bar(self, bar: HistoricalPriceData) -> None:
    # All prices positive
    if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
        raise ValidationError("All prices must be positive")

    # Volume non-negative
    if bar.volume < 0:
        raise ValidationError("Volume cannot be negative")

    # OHLC consistency
    if bar.high < max(bar.open, bar.close, bar.low):
        raise ValidationError("High must be >= max(open, close, low)")

    if bar.low > min(bar.open, bar.close, bar.high):
        raise ValidationError("Low must be <= min(open, close, high)")
```

## Data Normalization

### Timestamp Handling

- All timestamps stored in UTC
- Provider timestamps converted to UTC
- Timeframe boundaries aligned (daily at 00:00 UTC)

### Price Precision

- Prices stored as `DECIMAL(18, 6)` in PostgreSQL
- Python `Decimal` used throughout
- No floating-point arithmetic for financial data

### Symbol Standardization

- Symbols converted to uppercase
- Exchange codes standardized
- Market codes: `us`, `india`, `europe`

## Persistence

### PriceBar Repository

```python
class PriceBarRepository:
    async def bulk_upsert(self, bars: list[dict]) -> int:
        """Bulk upsert with ON CONFLICT DO UPDATE."""
        stmt = insert(PriceBar).values(bars)
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "timestamp", "timeframe"],
            set_={...}
        )
        return await self.session.execute(stmt)
```

### MarketSnapshot Repository

```python
class MarketSnapshotRepository:
    async def get_latest_batch(self, instrument_ids: list[UUID]) -> list[MarketSnapshot]:
        """Efficiently get latest snapshots for multiple instruments."""
```

## Error Handling

### Provider Errors

```python
class ProviderError(Exception):
    def __init__(self, message: str, provider: str, original_error: Exception = None)

class ProviderRateLimitError(ProviderError):
    def __init__(self, provider: str, retry_after: int = None, ...)

class ProviderTimeoutError(ProviderError):
    ...

class ProviderDataError(ProviderError):
    ...
```

### Ingestion Errors

- Individual symbol failures don't stop batch
- Errors tracked in `IngestionService.stats`
- Failed symbols returned in response

## Monitoring

### Ingestion Statistics

```python
stats = {
    "total_fetched": 0,
    "total_validated": 0,
    "total_persisted": 0,
    "total_errors": 0,
    "errors": [
        {"symbol": "AAPL", "error": "...", "time": "2024-01-01T00:00:00Z"}
    ]
}
```

### Health Checks

- Provider health: `provider.health_check()`
- Database health: `SELECT 1`
- Endpoint: `GET /health/ready`

## Scheduling

### Background Jobs (Planned)

- Quote ingestion: Every 1-5 minutes during market hours
- Historical backfill: Daily after market close
- Prediction generation: Daily before market open
- Outcome evaluation: Daily after market close

### Cron Expressions

| Job | Schedule | Timezone |
|-----|----------|----------|
| Live Quotes | `*/5 * * * *` | Exchange local |
| Historical EOD | `0 1 * * 1-5` | UTC |
| Predictions | `0 8 * * 1-5` | UTC |
| Outcomes | `0 18 * * 1-5` | UTC |

## Configuration

### Environment Variables

```bash
# Ingestion
INGESTION_INTERVAL_MINUTES=5
INGESTION_BATCH_SIZE=100
INGESTION_RETRY_ATTEMPTS=3
INGESTION_TIMEOUT_SECONDS=30

# Provider
GOOGLE_FINANCE_ENABLED=false
GOOGLE_FINANCE_API_KEY=
GOOGLE_FINANCE_RATE_LIMIT=100
```

## Data Quality Metrics

Tracked per provider/symbol:
- **Completeness**: % of expected bars received
- **Timeliness**: Average ingestion latency
- **Accuracy**: Validation pass rate
- **Consistency**: OHLC violation count

## Troubleshooting

### Common Issues

1. **Stale Data**: Check provider health and market hours
2. **Duplicate Bars**: Verify upsert logic and unique constraints
3. **Missing Data**: Check provider rate limits and API status
4. **Validation Failures**: Review provider data format changes

### Debug Commands

```bash
# Check ingestion stats
curl http://localhost:8000/api/v1/admin/ingestion/stats

# Manual ingestion trigger
curl -X POST http://localhost:8000/api/v1/markets/instruments/AAPL/ingest?exchange=NASDAQ

# Provider health
curl http://localhost:8000/api/v1/health/ready
```