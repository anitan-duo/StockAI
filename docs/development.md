# Development Guide

## Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Node.js 20+ (for frontend)

## Setup

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment
cp .env.example .env
# Edit .env with your settings

# Start PostgreSQL and Redis (or use docker-compose)
docker-compose up -d postgres redis

# Run migrations
alembic upgrade head

# Start API server
uvicorn apps.api.main:app --reload
```

### Frontend

```bash
cd stockai

# Install dependencies
npm install

# Start dev server
npm run dev
```

### Full Stack (Docker)

```bash
docker-compose up -d
```

## Development Workflow

### Code Style

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy apps services packages
```

### Pre-commit Hooks

```bash
# Install
pre-commit install

# Run manually
pre-commit run --all-files
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=apps --cov=services --cov=packages --cov-report=html

# Run specific test
pytest tests/unit/test_indicators.py -v

# Run integration tests
pytest tests/integration -v

# Watch mode
pytest-watch
```

### Database

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Reset database (dev only)
alembic downgrade base
alembic upgrade head

# Seed development data
python -m scripts.seed_dev_data
```

## Project Structure

### Adding a New Model

1. Create model in `apps/api/models/`
2. Add to `apps/api/models/__init__.py`
3. Create repository in `apps/api/repositories/`
4. Add to `apps/api/repositories/__init__.py`
5. Create schema in `packages/schemas/`
6. Add to `packages/schemas/__init__.py`
7. Generate migration: `alembic revision --autogenerate -m "Add new model"`
8. Apply migration: `alembic upgrade head`

### Adding a New API Endpoint

1. Create route in `apps/api/routes/`
2. Add to `apps/api/routes/__init__.py`
3. Include router in `apps/api/main.py`
4. Add tests in `tests/integration/`

### Adding a New Provider

1. Create provider in `services/ingestion/providers/`
2. Implement `MarketDataProvider` interface
3. Register in `ProviderFactory`
4. Add tests in `tests/providers/`

## Environment Variables

### Backend (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://stockai:stockai@localhost:5432/stockai

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=your-secret-key-min-32-chars
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# API
API_V1_PREFIX=/api/v1
PROJECT_NAME=StockAI
DEBUG=true

# CORS
BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Provider
GOOGLE_FINANCE_ENABLED=false
GOOGLE_FINANCE_API_KEY=
GOOGLE_FINANCE_RATE_LIMIT=100

# Ingestion
INGESTION_INTERVAL_MINUTES=5
INGESTION_BATCH_SIZE=100
INGESTION_RETRY_ATTEMPTS=3
INGESTION_TIMEOUT_SECONDS=30

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Frontend (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Debugging

### API Debugging

```bash
# View logs
docker-compose logs -f api

# Shell into container
docker-compose exec api bash

# Database shell
docker-compose exec postgres psql -U stockai -d stockai
```

### Frontend Debugging

```bash
# View logs
docker-compose logs -f frontend

# Open browser dev tools
# Network tab for API calls
# React DevTools for component inspection
```

## Common Tasks

### Reset Development Database

```bash
# Stop services
docker-compose down

# Remove volumes
docker-compose down -v

# Restart
docker-compose up -d

# Run migrations
docker-compose exec api alembic upgrade head
```

### Add Test Data

```bash
# Run seed script
docker-compose exec api python -m scripts.seed_dev_data
```

### View Database Schema

```bash
# Using psql
docker-compose exec postgres psql -U stockai -d stockai -c "\dt"

# Table structure
docker-compose exec postgres psql -U stockai -d stockai -c "\d users"
```

## Troubleshooting

### Port Conflicts

```bash
# Check what's using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Test connection
docker-compose exec api python -c "from apps.api.database import engine; print('OK')"
```

### Migration Issues

```bash
# Check current revision
alembic current

# View migration history
alembic history

# Fix conflicts
alembic merge heads
```

### Import Errors

```bash
# Reinstall package
pip install -e . --force-reinstall --no-deps

# Clear cache
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

## CI/CD

### GitHub Actions (Example)

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: stockai
          POSTGRES_PASSWORD: stockai
          POSTGRES_DB: stockai
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: alembic upgrade head
      - run: ruff check .
      - run: mypy apps services packages
      - run: pytest --cov=apps --cov=services --cov=packages
```

## Useful Commands

```bash
# Generate OpenAPI spec
docker-compose exec api python -c "from apps.api.main import app; import json; print(json.dumps(app.openapi(), indent=2))" > openapi.json

# Run specific test with debug
pytest tests/unit/test_indicators.py::test_rsi -v -s

# Profile API endpoint
docker-compose exec api python -m cProfile -o profile.stats -m uvicorn apps.api.main:app

# Check database size
docker-compose exec postgres psql -U stockai -d stockai -c "
SELECT pg_size_pretty(pg_database_size('stockai'));
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables WHERE schemaname='public' ORDER BY size DESC;"
```