# StockAI Architecture

## Overview

StockAI follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                      │
├─────────────────────────────────────────────────────────────┤
│                  Application Services                       │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────────┐  │
│  │   Auth      │ │  Market     │ │    Prediction        │  │
│  │  Service    │ │  Service    │ │    Service           │  │
│  └─────────────┘ └─────────────┘ └──────────────────────┘  │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────────┐  │
│  │  Watchlist  │ │   Alert     │ │    Backtest          │  │
│  │  Service    │ │  Service    │ │    Service           │  │
│  └─────────────┘ └─────────────┘ └──────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Domain Logic                             │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────────┐  │
│  │  Indicator  │ │  Prediction │ │    Backtest          │  │
│  │  Engine     │ │  Engine     │ │    Engine            │  │
│  └─────────────┘ └─────────────┘ └──────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                  Repository Layer                           │
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────────────┐  │
│  │   User      │ │  Market     │ │    Prediction        │  │
│  │ Repository  │ │ Repository  │ │   Repository         │  │
│  └─────────────┘ └─────────────┘ └──────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                  Data Layer (PostgreSQL)                    │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Principles

1. **Separation of Concerns**: Each layer has a single responsibility
2. **Dependency Inversion**: Services depend on repository interfaces
3. **Provider Abstraction**: Market data providers are pluggable
4. **Type Safety**: Full type hints throughout
5. **Async First**: All I/O operations are async

## Data Flow

### Market Data Ingestion

```
Provider → IngestionService → Validation → Normalization → Persistence
                ↓
         PriceBarRepository
                ↓
         PostgreSQL (price_bars table)
```

### Prediction Generation

```
User Request → PredictionService → IndicatorService → Feature Extraction
                                              ↓
                                    PredictionEngine → ML Model
                                              ↓
                                    PredictionRepository → PostgreSQL
```

### Backtesting

```
Backtest Request → BacktestService → BacktestEngine → Walk-forward Simulation
                                                        ↓
                                              PredictionRepository (historical)
                                                        ↓
                                              PriceBarRepository (prices)
                                                        ↓
                                              Metrics Calculation → Results
```

## Database Schema

Key tables:
- `users` - User accounts
- `sessions` - Active sessions
- `refresh_tokens` - JWT refresh tokens
- `markets` - Markets (US, India, Europe)
- `exchanges` - Exchanges (NASDAQ, NSE, etc.)
- `instruments` - Financial instruments
- `price_bars` - OHLCV data
- `market_snapshots` - Real-time quotes
- `models` - ML models
- `model_versions` - Model versions
- `predictions` - Generated predictions
- `prediction_outcomes` - Evaluated outcomes
- `watchlists` - User watchlists
- `watchlist_items` - Watchlist contents
- `alerts` - User alerts
- `alert_triggers` - Alert trigger history
- `backtests` - Backtest configurations
- `backtest_trades` - Individual trades
- `audit_logs` - Security audit trail

## Security

- Password hashing with bcrypt
- JWT access/refresh tokens
- Session management with revocation
- Rate limiting (planned)
- CORS configuration
- Input validation with Pydantic
- SQL injection prevention via SQLAlchemy ORM

## Scalability Considerations

- Async database operations
- Connection pooling
- Redis caching for frequent queries
- Background job processing (planned)
- Horizontal scaling via stateless API