# StockAI — Operations Guide

**Last updated:** 2026-11-09

## 1. Prerequisites

- Python >= 3.11, Node.js for the frontend.
- PostgreSQL 16 (production and integration tests), Valkey/Redis (scheduler locks, cache).
- `.env` with a unique `SECRET_KEY` of at least 32 characters. Production must never use the placeholder.
- Test mode does **not** read `.env`; tests supply a deterministic test-only `SECRET_KEY`.

## 2. Local startup

```bash
# Database + cache
docker compose up -d postgres valkey

# Backend
cd backend
.venv/bin/python -m alembic -c database/migrations/alembic.ini upgrade head
.venv/bin/uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd ../stockai
npm install
npm run dev
```

## 3. Test commands

```bash
cd backend
.venv/bin/python tests/run_tests.py sqlite      # unit/ML/research (no Postgres)
.venv/bin/python tests/run_tests.py postgres    # integration (requires Postgres)
.venv/bin/python tests/run_tests.py             # both

cd ../stockai
npx tsc --noEmit
npx vitest run
```

The SQLite suite uses a file-backed DB under `/tmp`. Override with
`STOCKAI_TEST_DB_PATH` / `STOCKAI_SQLITE_DB_PATH` when running nested
orchestrator self-tests.

## 4. Background jobs

The API lifespan starts lock-guarded asyncio jobs:

- quotes (5 min, fail-open)
- history backfill (6 h, fail-open)
- predictions (1 h, requires lock)
- outcomes (1 h, requires lock)
- monitoring (1 h, requires lock)
- evolution / shadow (daily/hourly, requires lock)
- alerts (5 min, requires lock, fails closed)

Disable with `SCHEDULER_ENABLED=false`.

## 5. Prediction operations

- Generation is idempotent per `(instrument, horizon, model version, bar)`.
- Outcome resolution uses the next trading bar and never fabricates labels.
- If ingestion lags, predictions stay pending rather than being scored against the wrong day.
- The champion artifact is SHA-verified before serving.

## 6. Health checks

- `GET /api/v1/health` — liveness/readiness surfaces.
- Scheduler logs: `scheduler.<job>` with lock/skip/result metadata.
- Drift observations are deduplicated until acknowledged.

## 7. Diagnostics

```bash
# Are different stocks actually getting different predictions?
cd backend
.venv/bin/python scripts/diagnose_prediction_diversity.py --json

# Interpret exit code 1 as: identical feature/probability vectors or
# duplicate bar rows were found. Do NOT "fix" by adding random noise;
# trace the data/model path.
```

## 8. Recovery

### After host/scheduler downtime

1. Start services: `docker start stockai-postgres stockai-valkey` (they hold the real state; no resets).
2. Clear stale scheduler locks (safe once nothing else runs):
   `docker exec stockai-valkey redis-cli DEL scheduler:lock:predictions` (and other `scheduler:lock:*` keys).
3. Heal data gaps (idempotent): run the history backfill job (covers ALL markets).
4. Resolve outcomes (idempotent, additive): run the outcome-resolution job.
5. Generate predictions (idempotent per bar): run the prediction job.
6. Check `/api/v1/health/freshness` — every market's `stale` flag must be false.

Never treat an empty database as the real one. The dev DB `stockai` holds production history.

- Re-run a scheduler job manually from the MLOps admin surface or by invoking the job function.
- Outcomes are immutable; corrections require an audit-logged note, not overwriting history.
- Never run `git reset --hard`, `git clean`, database resets, or destructive migrations on production.
- Preserve the sealed holdout; do not open it for interactive research.

## 9. Release checklist

1. `tests/run_tests.py` (both suites) must pass.
2. `npx tsc --noEmit` and `npx vitest run` must pass.
3. Champion hash must match the approved value.
4. No secrets in frontend bundles or logs.
5. Prediction-diversity diagnostic must report `OK`.
6. Canonical evaluation numbers must be reproducible from persisted rows.
