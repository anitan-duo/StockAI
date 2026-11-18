# StockAI

AI-powered stock market analysis and probabilistic prediction platform. Statically rigorous, leakage-resistant, calibrated, uncertainty-aware. Predictions are probabilistic, not guarantees. The system is allowed to say **NO CLEAR EDGE** when evidence is insufficient and **UNAVAILABLE** when data is insufficient.

> **IMPORTANT — EXPERIMENTAL SOFTWARE / NOT FINANCIAL ADVICE**
>
> StockAI is an experimental stock-market research and prediction project. It is provided for educational, research, and software-evaluation purposes only.
>
> Its predictions are uncertain and can be wrong, including during rapidly changing or unusual market conditions. Historical backtest performance does not guarantee future results. Out-of-sample evaluation does not establish that a model will perform similarly in live markets.
>
> StockAI has NOT demonstrated that it reliably predicts market direction at its original research target across all tested markets and time horizons. Its reported research results are not proof of profitability, investment suitability, or a durable predictive advantage.
>
> Do not rely on StockAI as the sole basis for buying, selling, holding, or shorting any security. Do not invest money you cannot afford to lose based on its output. Independently verify information and consult a qualified financial professional where appropriate.
>
> The software is provided "AS IS", without warranties of any kind, to the extent permitted by applicable law. The authors are not responsible for financial losses arising from use or misuse of the software.

**Disclaimer:** Past performance does not guarantee future results. Not investment advice.


> **CRITICAL DISCLOSURE — MODEL WEIGHTS NOT INCLUDED**
>
> Trained machine learning model weights and binaries (`model.pkl`) are **not included** in this public repository. Prediction and inference functionality require a separately supplied compatible model artifact placed at:
> `model_artifacts/real/ensemble/v1.0/model.pkl` (SHA-256 verified).
> Without this artifact, the backend service starts in fail-closed mode: market data, quotes, and structural APIs are accessible, but prediction generation will return `503 UNAVAILABLE` (`InsufficientDataError`).

## Architecture

```
├── stockai/          # Next.js 15 frontend (standalone)
│   ├── src/app/      # App Router pages: /, /dashboard, /markets, /stocks/[symbol], /predictions, /screener, /watchlist, /backtesting, /research, /settings, /login, /signup
│   └── src/components/ # shadcn + base-ui, price charts via lightweight-charts v5 (candles/OHLC/line/area/baseline + volume + RSI/MACD/Stoch/ATR/RelVol from src/lib/indicators), backtest curves via Recharts
└── backend/           # FastAPI + SQLAlchemy 2.0 + Alembic + Valkey
    ├── apps/api/      # FastAPI app, routes, repositories, services
    ├── services/      # ingestion/providers (Alpha→Twelve→Finnhub→Yahoo), prediction (FeaturePipeline 87 feats), backtesting, jobs
    ├── packages/schemas # Pydantic contracts
    ├── database/migrations # Alembic 62455fe47540 (19 tables)
    └── tests/ml       # leakage + feature-alignment
```

## Model honesty & Historical Research Benchmarks

> **Historical Performance Disclaimer:** All performance figures, accuracy numbers (e.g. 54–58% in cross-asset research evaluations, 0.443 calibrated best-fold), and metrics documented below represent historical research benchmarks on frozen backtest periods. They represent **historical and unverified current performance**, do NOT predict future live trading results, and do not represent a verified predictive edge in live production environments.


- **87 features** via `FeaturePipeline` (252-bar lookback) shared exactly between training and inference.
- Walk-forward `3mo train /1mo gap /1mo test`, 2 splits on 2,752 real samples (19 symbols, 231 dates 2025-09-25→2026-08-20).
- Out-of-sample calibrated best **0.443 (gb)** vs random **0.333** → modest edge. Raw `logistic 0.304/0.401, rf 0.333/0.382, gb 0.356/0.344`; calibrated `logistic 0.346/0.439, rf 0.343/0.393, gb 0.350/0.443`; `Brier 0.221, ECE 0.029, log_loss 1.089, acc 0.380` (see `model_artifacts/real/ensemble/v1.0/{metrics,calibration_metrics}.json`).
- **NO CLEAR EDGE** if `max_prob <0.40` (confidence capped ≤55), now exposed as `no_clear_edge` on `PredictionResponse`/`TopPredictionResponse` and badged on `/stocks/[symbol]`.
- **Insufficient history (<252 bars)** → `503 UNAVAILABLE` with `required/available` (e.g., ASML now 418 after fix, previously 0).
- Artifacts per version: `model.pkl`, `metrics.json`, `calibration_metrics.json`, `calibration_curve.png`, `feature_schema.json`, `training_config.json`, `manifest.json`.

## Research Evaluation: Historical P53 Cross-Asset Lead-Lag Results (Historical Benchmark)

Proposal P53 evaluated whether time-aligned cross-asset lead-lag features combined with validation-frozen threshold calibration (20th percentile) and date-block bootstrapping could achieve the target $\ge 62.00\%$ directional accuracy at $\ge 80.00\%$ coverage across all nine market/horizon cells.

All nine cells **failed** to reach the 62.00% target. Below is the verified nine-cell performance table:

| Market | Horizon | Samples ($n$) | Accuracy | Coverage | 95% CI (Date-Block Bootstrap) | Baseline | Verdict |
|:---:|:---:|---:|---:|---:|:---:|:---:|:---:|
| **US** | **1d** | 27,980 | 54.49% | 79.78% | [53.83%, 55.14%] | 52.07% | FAIL |
| **US** | **5d** | 27,982 | 56.82% | 79.85% | [56.21%, 57.52%] | 56.33% | FAIL |
| **US** | **10d** | 27,899 | 58.08% | 79.70% | [57.39%, 58.87%] | 58.43% | FAIL |
| **EU** | **1d** | 27,261 | 52.18% | 78.38% | [51.57%, 52.79%] | 50.99% | FAIL |
| **EU** | **5d** | 27,079 | 53.54% | 77.91% | [52.86%, 54.13%] | 53.13% | FAIL |
| **EU** | **10d** | 27,334 | 53.80% | 78.71% | [53.19%, 54.42%] | 54.39% | FAIL |
| **IN** | **1d** | 26,628 | 53.53% | 79.79% | [52.88%, 54.27%] | 51.69% | FAIL |
| **IN** | **5d** | 26,562 | 56.34% | 79.65% | [55.66%, 56.93%] | 55.36% | FAIL |
| **IN** | **10d** | 26,434 | 57.30% | 79.34% | [56.77%, 58.03%] | 57.40% | FAIL |

*Note: P53's best individual cell is US 10d at 58.08%, which does not reach 60% confidence intervals, and all coverage values remain below 80%. Protected champion E021 is preserved.*

## Quick start (Docker, recommended)

```bash
cp .env.example .env   # fill FINNHUB/ALPHAVANTAGE/TWELVEDATA keys, set SECRET_KEY ≥32 chars, VALKEY_URL

# IMPORTANT: Model weights are NOT included in Git.
# Copy the authorized E021 champion artifact to:
#   model_artifacts/real/ensemble/v1.0/model.pkl
# Verify its SHA-256 before use (must equal):
#   cafe9216074afd5b7ce0237aedef3655af1f2b5fa7d01490175fe807b5af01a7
# Without this artifact the backend starts but refuses to generate
# predictions (InsufficientDataError, fail-closed). Metadata files
# (manifest.json, metrics.json, feature_schema.json, calibration_metrics.json)
# ARE included in Git.

# Ensure yfinance is available for India/Europe fallback
docker compose up -d postgres valkey
docker compose exec postgres pg_isready -U stockai
docker compose up -d --build api frontend
docker compose ps # postgres healthy, valkey healthy, api healthy (curl /api/v1/health/live), frontend 3000
```

Frontend uses `context: ./stockai` (not root) and `.dockerignore` excludes `node_modules/.next/.git/.venv/model_artifacts` → context ~10 MB not 1.28 GB.

The API also runs Valkey-locked scheduler tasks (quotes/5min, alerts/5min, predictions/hourly; `SCHEDULER_ENABLED=false` disables). See `docs/operations/STOCKAI_OPERATIONS_GUIDE.md` for operational guidance.

## Local dev

```bash
# backend
cd backend
python -m venv .venv; source .venv/bin/activate
pip install -e ".[dev]"
pip install yfinance bcrypt==4.0.1
cp .env.example .env  # set keys
alembic -c database/migrations/alembic.ini upgrade head # 62455fe47540
alembic current
uvicorn apps.api.main:app --reload --port 8000

# frontend
cd stockai
npm ci
npx tsc --noEmit  # must pass with ignoreBuildErrors:false
npm run build     # 15 routes, standalone
npm run dev
```

## Environment

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://stockai:stockai@postgres:5432/stockai` (Docker) / `localhost:5432` (local) | required |
| `VALKEY_URL` / `REDIS_URL` | `redis://valkey:6379/0` (Docker) | `redis://localhost:6379/0` |
| `SECRET_KEY` | ≥32 chars, not placeholder `your-secret...` | required |
| `ALPHAVANTAGE_ENABLED/API_KEY/RATE_LIMIT` | 5/min | false/empty/5 |
| `TWELVEDATA_ENABLED/API_KEY` | 800/min | false |
| `FINNHUB_ENABLED/API_KEY` | 60/min | false |
| `YAHOO_FINANCE_ENABLED` | fallback for India/Europe, uses `yfinance` | false |
| `NEXT_PUBLIC_API_URL` | frontend → api | `http://localhost:8000/api/v1` |

Provider fallback order `Alpha → Twelve → Finnhub → Yahoo → Google(disabled)`, enabled per provider via `*_ENABLED` (defaults false; Yahoo falls back for India/Europe exchanges when enabled). Yahoo `get_historical_prices` handles `NSE .NS, BSE .BO, LSE .L, XETRA .DE, EURONEXT .AS, SIX .SW`. Never expose keys to frontend (`NEXT_PUBLIC_` only API URL).

## Data coverage

`markets 3 (US/IN/EU), exchanges 9 (NASDAQ/NYSE/NYSEARCA/NSE/BSE/XETRA/LSE/EURONEXT/SIX), instruments 19, price_bars 8,358` (AAPL 410, AMZN 499, GOOGL 499, META 499, MSFT 499, NVDA 499, TSLA 499, RELIANCE/TCS/INFY/HDFCBANK/ICICIBANK/SBIN 410, HSBA 414, SHEL 415, AZN 415, SAP 416, SIE 416, ASML 418 after fix XETRA→EURONEXT). All 19 now ≥410 (was ASML 0).

## API

- `GET /api/v1/health`, `/ready` (DB + live provider registry check, `503` when degraded), `/live`, `/health/freshness` (market-data staleness, never fabricated)
- `GET /markets/overview` — major indices (live fetch, 60s cache) + gainers/losers from persisted snapshots; every element carries a backend-classified `freshness` (`fresh|recent|delayed|stale|unavailable`); missing data is absent, never synthesized
- `GET /markets`, `/markets/{code}/exchanges`, `/markets/instruments/search?q=AAPL`, `/markets/instruments/{symbol}/quote?exchange=NASDAQ`, `/history`
- Quote responses carry provenance: `provider`, `freshness`, `delayed`, `source_timestamp`, `ingested_at`, `exchange`, `currency`. The quote endpoint attempts a live provider fetch first (30s cached), then the freshest persisted snapshot, then the latest daily bar — which is explicitly labeled `stale` and derives `previous_close` from the prior bar (never fabricated). The frontend must render `freshness` and must not derive staleness client-side (`stockai/src/lib/freshness.ts`).
- `GET /predictions/stocks/{symbol}?exchange=NASDAQ&horizon=1d` → `up/neutral/down` sum 1, `expected_return`, `range`, `confidence`, `no_clear_edge`, `503 UNAVAILABLE` if <252
- `GET /predictions?limit=...` top (with `no_clear_edge`), `/stocks/{symbol}/history`, `/stocks/{symbol}/factors`
- `GET /rankings`, `/mlops`, `/scenarios`, `/analytics`, `/alerts` (MLOps mutations admin-only; reads signed-in)
- `POST /screener` (price filtered post-hoc on snapshot price; portable latest-prediction per instrument)
- `POST /auth/register`, `/login` (throttled 30/15min per IP+email → `429`, fail-open), `/refresh` (rotates `jti`), `/logout` (revokes by hash), `GET /auth/me`, `POST /forgot-password` (generic), `POST /reset-password` (`501` not configured), `401` unauth, `404` IDOR blocked
- `POST /training/run`, `/models/{name}/activate/{version}`, `/evaluate` admin-only (`403`); `GET /training/calibration` (real metrics or `503`)
- `GET /watchlist`, `POST /watchlist`, `GET /watchlist/{id}`, `POST /watchlist/{id}/items?instrument_id=UUID` (409 duplicate), `PUT /reorder`, `DELETE`
- `POST /alerts`, `GET /alerts`, `PATCH /alerts/{id}`, `POST /alerts/{id}/acknowledge`
- `POST /backtests`, `POST /backtests/{id}/run?method=causal|final` (default causal walk-forward with per-window retraining; legacy final-model path tagged non-causal; 503 if insufficient)

All use parameterized SQLAlchemy `select(where)` with ownership `user_id == _get_user_id(user)`.

## Research artifacts & reproducibility

Research evaluation artifacts live under `research/evaluations/` (per-experiment
`*.json`, manifests, PIT-locked data refs). Large raw inputs
(`*.csv.gz`, `*.npz`, `research/data/`, `sec_facts/`, multi-MB cross-section
outputs) and the 539 MB feature cache are intentionally **not** in Git; the
release manifest carries the manifests, metrics, and protocol docs that make
each experiment auditable (`research/evaluations/LEARNING.json`,
`P37_LEDGER.md`, per-experiment `manifest.json` with pinned SHA-256 inputs).
Where an artifact is absent locally, the matching test in
`backend/tests/research/` skips by design (existence guard) rather than
failing — the assertions themselves are unchanged when the data is present.

## Frontend

`/` landing, `/dashboard`, `/markets` (indices via `api.getMarkets`, `UNAVAILABLE` if 0 not mock), `/stocks/[symbol]` (quote/history/prediction with provider/freshness, `UNAVAILABLE` if <252), `/predictions` (no `MOCK_PREDICTIONS` fallback), `/screener` (real `POST /screener`, no `MOCK_ROWS`), `/watchlist`, `/backtesting` (no `Math.random` synthetic, `UNAVAILABLE` if no instrument/version), `/research` (mock research demo only, not financial prices), `/settings`, `/login`, `/signup`.

`npx tsc --noEmit` 0 errors (no `@ts-nocheck` in `src/`). `npm run build` 21 routes (18 pages + favicon + global-error + not-found) with `ignoreBuildErrors:false`.

## Testing

```bash
cd backend && .venv/bin/python tests/run_tests.py sqlite   # 501 passed, 1 skipped, 1 deselected (2026-11-16)
cd backend && .venv/bin/python tests/run_tests.py postgres # 25 passed (2026-11-15; requires live Postgres)
npx vitest run          # 27 passed (indicator math + chart-data mapping + 2001 regression)
npx playwright test     # 31 passed (smoke 6, charts 5, routes 11 incl. /mlops + /scenarios, predictions-horizon 3, scenarios-lab 2, visual 4)
```

> Backend suite counts are from the unified orchestrator `backend/tests/run_tests.py`
> (SQLite suite: unit + ML + backtesting + research, 501 passed / 1 skipped /
> 1 deselected on 2026-11-16; the skip requires the seeded-AAPL integration
> fixture). The Postgres integration suite (25 passed on 2026-11-15) runs in a
> separate process against the isolated `stockai_test` database.
> Frontend counts are from the local `vitest`/`playwright` runs; the Playwright
> browser specs are not executed in CI.

## MLOps continuous learning

See `docs/mlops.md`. The champion (`real/ensemble/v1.0`, sha `cafe9216…`)
is pinned in `model_champions` and hash-verified at inference; matured
outcomes resolve hourly; challengers train on gated cycles, evaluate in
shadow, and promote only via audited admin approval against a pre-registered
bar. Operate it at `/mlops` (reads: signed-in; mutations: admin).

Live Docker verification (2026-10-10, 4/4 containers healthy): `register 201`, `login 200` (`401` wrong pw, `429` after 30/15min/IP), `GET /auth/me 200`, `GET /markets/exchanges/NASDAQ 200`, `GET /predictions/stocks/AAPL?horizon=1w 422` UNSUPPORTED_HORIZON, `GET /predictions/stocks/AAPL?horizon=1d 200` with `model_horizon: "1d"`, 32-endpoint fuzz with 0 five-hundreds and 0 leak signatures, history newest-biased on all windows with zero pre-2005 bars.

## Limitations

- Edge is modest (0.380 acc / 0.443 best-fold vs 0.333 random); not profitable guarantee.
- Backtest reuses the final production model per timestamp (honest point-in-time features, but not per-window retraining); zero trades reported honestly, never manufactured.
- Backtest defaults to causal walk-forward (per-window production model family logistic/RF300/GB200 + scaler + isotonic-if-n≥60 from `services/ml/recipe.py`, retrained monthly on data strictly before each eval date); legacy `method=final` reuses the production artifact and is labeled non-causal/optimistic.
- Dataset is small for three-way splits: 2 walk-forward folds / 571 eval samples; fold 0 ≈ random (0.333).
- `research` page is a labeled static demo (no LLM wired); `/backtesting` shows UNAVAILABLE when live data is missing (no synthetic fallback).
- **Model weights not in Git.** The E021 champion `model.pkl` (SHA-256 `cafe9216074afd5b7ce0237aedef3655af1f2b5fa7d01490175fe807b5af01a7`) must be supplied locally at `model_artifacts/real/ensemble/v1.0/model.pkl` and hash-verified before use. Without it the backend runs but cannot generate predictions.
- **BAR-002 (price-bar session-day deduplication) is NOT resolved.** It was rehearsed on an isolated database copy only; live production remediation is owner-gated (requires explicit sign-off, `pg_dump` snapshot, and review of 7 quarantined conflict groups). Internal database audit reports are maintained privately.
- `SECRET_KEY` must be ≥32 chars (enforced); training run/activate/evaluate are admin-only (`403` otherwise).
- `ASML` now `EURONEXT .AS` (418 bars) — was `XETRA 0`.

## License

All Rights Reserved (see `LICENSE`).
