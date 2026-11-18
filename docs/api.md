# StockAI API Documentation

## Base URL

```
Development: http://localhost:8000/api/v1
Production:  https://api.stockai.example.com/api/v1
```

## Authentication

All protected endpoints require a Bearer token:

```
Authorization: Bearer <access_token>
```

### Token Endpoints

#### Register
```
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword123",
  "full_name": "John Doe"
}
```

#### Login
```
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword123",
  "remember_me": true
}
```

#### Refresh Token
```
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "<refresh_token>"
}
```

#### Logout
```
POST /auth/logout
Authorization: Bearer <access_token>
X-Refresh-Token: <refresh_token>
```

## Markets

### List Markets
```
GET /markets
```

### Get Market
```
GET /markets/{market_code}
```

### List Exchanges
```
GET /markets/{market_code}/exchanges
```

### Get Exchange
```
GET /markets/exchanges/{exchange_code}?market_code={market_code}
```

### Search Instruments
```
GET /markets/instruments/search?q={query}&market={market}&exchange={exchange}&type={type}&limit={limit}
```

### Get Instrument
```
GET /markets/instruments/{symbol}?exchange={exchange_code}
```

### Get Quote
```
GET /markets/instruments/{symbol}/quote?exchange={exchange_code}
```

### Get Historical Prices
```
GET /markets/instruments/{symbol}/history?exchange={exchange_code}&timeframe=1d&start=2024-01-01&end=2024-12-31&limit=500
```

### Ingest Data
```
POST /markets/instruments/{symbol}/ingest?exchange={exchange_code}&timeframe=1d
```

## Predictions

### Get Stock Prediction
```
GET /predictions/stocks/{symbol}?exchange={exchange_code}&horizon=1d
```

### Get Prediction History
```
GET /predictions/stocks/{symbol}/history?exchange={exchange_code}&horizon=1d&limit=100
```

### Get Factor Analysis
```
GET /predictions/stocks/{symbol}/factors?exchange={exchange_code}&horizon=1d
```

### Get Top Predictions
```
GET /predictions?horizon=1d&direction=up&confidence_min=70&expected_return_min=0.5&limit=50
```

## Screener

### Screen Stocks
```
POST /screener
Content-Type: application/json

{
  "market": ["us", "india"],
  "exchange": ["NASDAQ", "NSE"],
  "sector": ["Technology", "Financial Services"],
  "price_min": 10,
  "price_max": 1000,
  "performance_min": -10,
  "performance_max": 50,
  "rsi_min": 30,
  "rsi_max": 70,
  "volatility_min": 10,
  "volatility_max": 50,
  "prediction_probability_min": 0.6,
  "expected_return_min": 0.5,
  "confidence_min": 60,
  "prediction_direction": "up",
  "limit": 50
}
```

### Get Available Sectors
```
GET /screener/filters/sectors
```

### Get Available Exchanges
```
GET /screener/filters/exchanges?market=us
```

## Watchlist

### List Watchlists
```
GET /watchlist
Authorization: Bearer <token>
```

### Create Watchlist
```
POST /watchlist
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Tech Stocks",
  "description": "My favorite tech companies",
  "is_default": false
}
```

### Get Watchlist
```
GET /watchlist/{watchlist_id}
Authorization: Bearer <token>
```

### Update Watchlist
```
PATCH /watchlist/{watchlist_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description",
  "is_default": true
}
```

### Delete Watchlist
```
DELETE /watchlist/{watchlist_id}
Authorization: Bearer <token>
```

### Add to Watchlist
```
POST /watchlist/{watchlist_id}/items
Authorization: Bearer <token>
Content-Type: application/json

{
  "instrument_id": "uuid",
  "notes": "Long term hold"
}
```

### Remove from Watchlist
```
DELETE /watchlist/{watchlist_id}/items/{instrument_id}
Authorization: Bearer <token>
```

### Reorder Watchlist
```
PUT /watchlist/{watchlist_id}/reorder
Authorization: Bearer <token>
Content-Type: application/json

["item-id-1", "item-id-2", "item-id-3"]
```

## Alerts

### List Alerts
```
GET /alerts?status=active
Authorization: Bearer <token>
```

### Create Alert
```
POST /alerts
Authorization: Bearer <token>
Content-Type: application/json

{
  "instrument_id": "uuid",
  "name": "AAPL above 200",
  "alert_type": "price_above",
  "condition": "gt",
  "target_value": 200,
  "secondary_value": null,
  "expires_at": "2024-12-31T23:59:59Z",
  "notify_email": true,
  "notify_push": false,
  "notify_in_app": true
}
```

### Get Alert
```
GET /alerts/{alert_id}
Authorization: Bearer <token>
```

### Update Alert
```
PATCH /alerts/{alert_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Updated name",
  "target_value": 210,
  "status": "active"
}
```

### Acknowledge Alert
```
POST /alerts/{alert_id}/acknowledge
Authorization: Bearer <token>
```

### Disable Alert
```
POST /alerts/{alert_id}/disable
Authorization: Bearer <token>
```

### Delete Alert
```
DELETE /alerts/{alert_id}
Authorization: Bearer <token>
```

### Get Alert Triggers
```
GET /alerts/{alert_id}/triggers?limit=50
Authorization: Bearer <token>
```

### Get Available Alert Types
```
GET /alerts/types/available
```

## Backtesting

### List Backtests
```
GET /backtests?status=completed&skip=0&limit=20
Authorization: Bearer <token>
```

### Create Backtest
```
POST /backtests
Authorization: Bearer <token>
Content-Type: application/json

{
  "instrument_id": "uuid",
  "model_version_id": "uuid",
  "start_date": "2023-01-01T00:00:00Z",
  "end_date": "2023-12-31T23:59:59Z",
  "horizon": "1d",
  "initial_capital": 100000
}
```

### Get Backtest
```
GET /backtests/{backtest_id}
Authorization: Bearer <token>
```

### Run Backtest
```
POST /backtests/{backtest_id}/run
Authorization: Bearer <token>
```

### Delete Backtest
```
DELETE /backtests/{backtest_id}
Authorization: Bearer <token>
```

## Health Checks

### Basic Health
```
GET /health
```

### Readiness
```
GET /health/ready
```

### Liveness
```
GET /health/live
```

## Error Responses

All endpoints return consistent error format:

```json
{
  "detail": "Error description",
  "type": "error_type"
}
```

### HTTP Status Codes

- `200` - Success
- `201` - Created
- `204` - No Content
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `409` - Conflict
- `422` - Validation Error
- `429` - Rate Limited
- `500` - Internal Server Error
- `503` - Service Unavailable

## Rate Limiting

Rate limiting is planned but not yet implemented. Current limits:
- Auth endpoints: 10 requests/minute per IP
- Market data: 100 requests/minute per user
- Predictions: 50 requests/minute per user

## Pagination

List endpoints support pagination:

```
GET /endpoint?page=1&page_size=20
```

Response includes:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

## Webhooks (Planned)

Future support for webhook notifications on:
- Alert triggers
- Prediction updates
- Backtest completion