# StockAI — Target Architecture

**Status:** target design, partially implemented
**Last updated:** 2026-11-09

## 1. Design principle

One prediction, one outcome, one score.

Every layer must be able to point to the canonical record and the canonical evaluation formula. No layer is allowed to invent its own hit rate, denominator, or correctness rule.

## 2. Canonical data contracts

### Prediction

```
prediction_id            uuid
instrument_id            uuid  -> instruments
exchange / market / currency
horizon                  "1d" (native; 1w/1m refused until a native model exists)
prediction_timestamp     latest closed bar timestamp (PIT)
data_timestamp           same bar timestamp
model_version_id         uuid
feature_pipeline_version "v1"
data_snapshot_ref        bar timestamp + source
predicted_direction      up | neutral | down
up/neutral/down_prob     sum to 1
expected_return          vol-scaled
confidence               heuristic signal separation (0-100), NOT a probability
features_snapshot        87 validated features + price
status                   pending | evaluated | invalid | expired
```

### Outcome

```
prediction_id       unique
evaluation_price    next trading bar close
actual_return       percent
actual_direction    up | neutral | down
evaluation_timestamp
source              provider
methodology_version "v1-h1d-0.5pct"
status              evaluated | invalid | expired
```

### Evaluation (single engine: `services/prediction/evaluation.py`)

```
directional_n            evaluated predictions with predicted in {up,down}
directional_correct      predicted == actual
directional_accuracy     directional_correct / directional_n
neutral_n                evaluated predictions with predicted == neutral
neutral_correct          actual == neutral
all_class_accuracy       exact matches / evaluated  (diagnostic only)
pending                  no outcome; excluded, never wrong
invalid / expired        reported separately
coverage                 evaluated / total in scope
CI                       Wilson 95%
reliable                 directional_n >= 30
```

## 3. Runtime architecture

```
Providers (yfinance / Finnhub / TwelveData / AlphaVantage / NSE)
        │
        ▼
Ingestion service ── validation ── provenance ── stale checks
        │
        ▼
price_bars (unique instrument+timestamp+timeframe)
        │
        ▼
FeaturePipeline (training == inference, 87 features, no zero-fill)
        │
        ▼
Champion artifact (SHA-verified) ── probabilities + heuristic separation
        │
        ▼
predictions (idempotent per instrument/horizon/model/bar)
        │
        ▼
outcome resolver (next trading bar, PIT, idempotent)
        │
        ▼
CANONICAL EVALUATION ENGINE
        │
        ├── analytics API
        ├── monitor API
        ├── stock history API
        └── research reports
        │
        ▼
Next.js UI (renders server numbers; never recomputes accuracy)
```

## 4. Hard boundaries

- The sealed holdout is read-only and off-limits to interactive research unless explicitly authorized.
- Champion promotion requires pre-registered OOS evaluation, calibration, coverage and stability checks.
- Shadow/challenger predictions are stored under their own model version and never served as production.
- Frontend never derives accuracy, coverage, or correctness.
- Background jobs are lock-guarded and idempotent.

## 5. Planned hardening

1. Database unique constraint on `(instrument_id, horizon, model_version_id, prediction_timestamp)` after auditing legacy duplicates.
2. Exchange-calendar-aware evaluation (`services/market_session.py`) for non-US markets and holidays.
3. Holdout access guard (filesystem permission + application check).
4. Per-market/per-horizon calibration artifacts with versioned methodology.
5. Point-in-time fundamentals and event features (see research roadmap).
