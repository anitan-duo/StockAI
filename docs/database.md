# Database Documentation

## Overview

StockAI uses PostgreSQL 16+ with async SQLAlchemy 2.0 for data persistence.

## Connection

```python
DATABASE_URL = "postgresql+asyncpg://user:pass@host:port/dbname"
```

## Schema

### Core Tables

#### users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMPTZ,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_users_email ON users(email);
```

#### sessions
```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    is_revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_sessions_user_expires ON sessions(user_id, expires_at);
```

#### refresh_tokens
```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_token_hash VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_refresh_tokens_user_expires ON refresh_tokens(user_id, expires_at);
```

### Market Tables

#### markets
```sql
CREATE TABLE markets (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    country_code VARCHAR(3) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    timezone VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    market_open TIME NOT NULL,
    market_close TIME NOT NULL,
    pre_market_open TIME,
    post_market_close TIME,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### exchanges
```sql
CREATE TABLE exchanges (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    market_id INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    timezone VARCHAR(50) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    market_open TIME NOT NULL,
    market_close TIME NOT NULL,
    pre_market_open TIME,
    post_market_close TIME,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_exchange_code_market ON exchanges(code, market_id);
```

#### instruments
```sql
CREATE TABLE instruments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id) ON DELETE CASCADE,
    type VARCHAR(20) DEFAULT 'equity',
    currency VARCHAR(3) NOT NULL,
    isin VARCHAR(12) UNIQUE,
    cusip VARCHAR(9) UNIQUE,
    figi VARCHAR(12) UNIQUE,
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    is_active BOOLEAN DEFAULT TRUE,
    is_tradable BOOLEAN DEFAULT TRUE,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_instrument_symbol_exchange ON instruments(symbol, exchange_id);
CREATE INDEX ix_instruments_symbol_active ON instruments(symbol, is_active);
CREATE INDEX ix_instruments_sector ON instruments(sector);
```

### Price Data Tables

#### price_bars
```sql
CREATE TABLE price_bars (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id UUID NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open NUMERIC(18,6) NOT NULL,
    high NUMERIC(18,6) NOT NULL,
    low NUMERIC(18,6) NOT NULL,
    close NUMERIC(18,6) NOT NULL,
    volume BIGINT NOT NULL,
    vwap NUMERIC(18,6),
    trades_count BIGINT,
    source VARCHAR(50) DEFAULT 'unknown',
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_price_bar_unique ON price_bars(instrument_id, timestamp, timeframe);
CREATE INDEX ix_price_bars_instrument_timeframe_ts ON price_bars(instrument_id, timeframe, timestamp);
CREATE INDEX ix_price_bars_timestamp_desc ON price_bars(timestamp DESC);
```

#### market_snapshots
```sql
CREATE TABLE market_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id UUID NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    price NUMERIC(18,6) NOT NULL,
    change NUMERIC(18,6) NOT NULL,
    change_percent NUMERIC(10,4) NOT NULL,
    volume BIGINT NOT NULL,
    high NUMERIC(18,6) NOT NULL,
    low NUMERIC(18,6) NOT NULL,
    open NUMERIC(18,6) NOT NULL,
    previous_close NUMERIC(18,6) NOT NULL,
    market_status VARCHAR(20) NOT NULL,
    source VARCHAR(50) DEFAULT 'unknown',
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_market_snapshot_unique ON market_snapshots(instrument_id, timestamp);
CREATE INDEX ix_market_snapshots_instrument_ts ON market_snapshots(instrument_id, timestamp);
```

### Prediction Tables

#### models
```sql
CREATE TABLE models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(500),
    model_type VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### model_versions
```sql
CREATE TABLE model_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    version VARCHAR(50) NOT NULL,
    description VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE,
    training_date TIMESTAMPTZ,
    metrics JSONB DEFAULT '{}',
    hyperparameters JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_model_version ON model_versions(model_id, version);
CREATE INDEX ix_model_versions_model_active ON model_versions(model_id, is_active);
```

#### predictions
```sql
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id UUID NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    model_version_id UUID NOT NULL REFERENCES model_versions(id) ON DELETE CASCADE,
    horizon VARCHAR(10) NOT NULL,
    predicted_direction VARCHAR(10) NOT NULL,
    up_probability NUMERIC(5,4) NOT NULL,
    neutral_probability NUMERIC(5,4) NOT NULL,
    down_probability NUMERIC(5,4) NOT NULL,
    expected_return NUMERIC(10,4) NOT NULL,
    range_lower NUMERIC(10,4) NOT NULL,
    range_upper NUMERIC(10,4) NOT NULL,
    confidence INTEGER NOT NULL,
    prediction_timestamp TIMESTAMPTZ NOT NULL,
    data_timestamp TIMESTAMPTZ NOT NULL,
    features_snapshot JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_predictions_instrument_horizon_ts ON predictions(instrument_id, horizon, prediction_timestamp);
CREATE INDEX ix_predictions_model_ts ON predictions(model_version_id, prediction_timestamp);
```

#### prediction_outcomes
```sql
CREATE TABLE prediction_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id UUID UNIQUE NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    actual_return NUMERIC(10,4) NOT NULL,
    actual_direction VARCHAR(10) NOT NULL,
    is_correct BOOLEAN NOT NULL,
    evaluated_at TIMESTAMPTZ DEFAULT NOW(),
    evaluation_price NUMERIC(18,6) NOT NULL,
    evaluation_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_prediction_outcomes_prediction ON prediction_outcomes(prediction_id);
```

### Watchlist Tables

#### watchlists
```sql
CREATE TABLE watchlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_watchlist_user_name ON watchlists(user_id, name);
CREATE INDEX ix_watchlists_user_default ON watchlists(user_id, is_default);
```

#### watchlist_items
```sql
CREATE TABLE watchlist_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    instrument_id UUID NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    notes VARCHAR(500),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_watchlist_item_unique ON watchlist_items(watchlist_id, instrument_id);
CREATE INDEX ix_watchlist_items_watchlist_order ON watchlist_items(watchlist_id, sort_order);
```

### Alert Tables

#### alerts
```sql
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instrument_id UUID NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    alert_type VARCHAR(30) NOT NULL,
    condition VARCHAR(20) NOT NULL,
    target_value NUMERIC(18,6) NOT NULL,
    secondary_value NUMERIC(18,6),
    status VARCHAR(20) DEFAULT 'active',
    expires_at TIMESTAMPTZ,
    triggered_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    notify_email BOOLEAN DEFAULT TRUE,
    notify_push BOOLEAN DEFAULT FALSE,
    notify_in_app BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_alerts_user_status ON alerts(user_id, status);
CREATE INDEX ix_alerts_instrument_type ON alerts(instrument_id, alert_type);
CREATE INDEX ix_alerts_expires ON alerts(expires_at);
```

#### alert_triggers
```sql
CREATE TABLE alert_triggers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    triggered_value NUMERIC(18,6) NOT NULL,
    message VARCHAR(500) NOT NULL,
    email_sent BOOLEAN DEFAULT FALSE,
    push_sent BOOLEAN DEFAULT FALSE,
    in_app_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_alert_triggers_alert_ts ON alert_triggers(alert_id, created_at);
```

### Backtest Tables

#### backtests
```sql
CREATE TABLE backtests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instrument_id UUID NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    model_version_id UUID NOT NULL REFERENCES model_versions(id) ON DELETE CASCADE,
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    horizon VARCHAR(10) NOT NULL,
    initial_capital NUMERIC(18,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    total_return NUMERIC(10,4),
    annualized_return NUMERIC(10,4),
    sharpe_ratio NUMERIC(10,4),
    max_drawdown NUMERIC(10,4),
    win_rate NUMERIC(5,2),
    profit_factor NUMERIC(10,4),
    equity_curve JSONB DEFAULT '[]',
    drawdown_curve JSONB DEFAULT '[]',
    returns_distribution JSONB DEFAULT '[]',
    trades JSONB DEFAULT '[]',
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_backtests_user_status ON backtests(user_id, status);
CREATE INDEX ix_backtests_instrument_dates ON backtests(instrument_id, start_date, end_date);
```

#### backtest_trades
```sql
CREATE TABLE backtest_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id UUID NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,
    entry_date TIMESTAMPTZ NOT NULL,
    exit_date TIMESTAMPTZ,
    entry_price NUMERIC(18,6) NOT NULL,
    exit_price NUMERIC(18,6),
    shares BIGINT NOT NULL,
    side VARCHAR(10) NOT NULL,
    pnl NUMERIC(18,2),
    return_pct NUMERIC(10,4),
    is_winner BOOLEAN,
    prediction_id UUID REFERENCES predictions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_backtest_trades_backtest_entry ON backtest_trades(backtest_id, entry_date);
```

### Audit Table

#### audit_logs
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    request_id VARCHAR(100),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_audit_logs_user_action_ts ON audit_logs(user_id, action, created_at);
CREATE INDEX ix_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX ix_audit_logs_ip_ts ON audit_logs(ip_address, created_at);
CREATE INDEX ix_audit_logs_success_ts ON audit_logs(success, created_at);
```

## Migrations

### Creating Migrations

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "Add new column to instruments"

# Manual migration
alembic revision -m "Add custom index"
```

### Running Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade specific revision
alembic upgrade <revision>

# Downgrade
alembic downgrade -1
alembic downgrade <revision>

# Show history
alembic history

# Show current revision
alembic current
```

## Performance Considerations

### Indexing Strategy

- Primary keys on all tables
- Foreign key indexes on all relationships
- Composite indexes for common query patterns
- Partial indexes for boolean flags (is_active, is_deleted)

### Partitioning (Future)

For large tables like `price_bars`:
```sql
-- Partition by timeframe and time
CREATE TABLE price_bars_1d PARTITION OF price_bars
FOR VALUES IN ('1d') PARTITION BY RANGE (timestamp);
```

### Vacuum and Analyze

```sql
-- Regular maintenance
VACUUM ANALYZE price_bars;
VACUUM ANALYZE market_snapshots;
```

## Backup Strategy

- Point-in-time recovery (PITR) with WAL archiving
- Daily logical backups with `pg_dump`
- Cross-region replication for disaster recovery

## Extensions

Required PostgreSQL extensions:
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
```