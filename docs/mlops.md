# MLOps: Continuous Learning Architecture

The production champion is `real/ensemble/v1.0`
(`sha256:cafe9216074afd5b…`, frozen since Phase 3). The system below improves
on it only with evidence — it never self-promotes, never touches the champion
without an audited admin approval, and never reuses burned holdouts.

## Components

| Piece | Location | Notes |
|---|---|---|
| Champion pointer | `model_champions` (one current row) + `services/ml/champion.py` | Inference resolves the champion and hash-verifies bytes before trusting them; fresh DBs fall back to the pinned v1.0 hash only. |
| Experiment registry | `experiments` table + `services/mlops/experiments.py` | Lifecycle `research→training→evaluating→candidate→shadow→approved` (+`rejected/failed/retired`), guarded transitions, burned-range refusal. |
| Training jobs | `training_jobs` table (unique `job_key`) | Bounded attempts/timeouts; per-cycle cadence via scheduler locks. |
| Outcome resolution | `services/prediction/outcomes.py` + hourly scheduler job | Resolves only matured 1d labels from real bars (original ±0.5% target); idempotent; holidays stay pending. Legacy snapshot-based evaluator was dead code and removed. |
| Challenger cycle | `services/mlops/evolution.py` (daily, Valkey-locked) | Skips without ≥60 fresh unburned evals; at most one experiment/cycle; frozen configs; never promotes. Stale workers auto-fail after 6h. |
| Shadow evaluation | `services/mlops/shadow.py` + hourly job | Hash-verified challenger artifacts; predictions keyed by challenger version (production listings untouched); skips when no candidates. |
| Monitoring | `services/mlops/monitor.py` + hourly job | Confirmed metrics (matured outcomes only): accuracy, per-class Brier, log loss, ECE calibration, per-version/regime breakdown; provisional coverage stays separate. Drift alarms need ≥30 samples and are recorded once until acknowledged. |
| Promotions | `model_promotions` + `POST /mlops/.../approve`, `/mlops/rollback` (admin) | Bar re-verified server-side (Δacc ≥ +0.05, Δbrier ≤ −0.01, n ≥ 60); atomic switch; rollback = reversing row. |
| Analytics workspace | `services/mlops/analytics.py`, `GET /analytics/performance`, `/analytics` page | Read-only lookback/filter views over resolved outcomes (calibration, symbol/version/regime cells, recent outcomes). Pending rows never count as performance. |
| UI | `/mlops` and `/analytics` pages + header nav | Reads for signed-in users; mutations hidden for non-admins (server enforces). |

## Scheduler additions

`outcomes`/`monitoring`/`shadow` hourly, `evolution` daily — all Valkey-locked
(`require_lock=True`: hourly+ jobs skip a cycle rather than run duplicated
across workers; freshness-critical quotes/history stay fail-open).

## Read-path isolation

Production reads (latest quote-analysis prediction, top lists, screener,
alert evaluation, scheduler same-day checks) are scoped to the champion
version id. Shadow and retired-challenger rows can never surface as
production predictions; explicit version reads remain available for audit
and shadow comparison. Verified by `test_champion_scoping.py`.

## Transparency

Top-list responses carry `prediction_timestamp` + `model_version`; history
items carry `model_version`. The predictions page shows "as of X · version"
with >24h stale styling; the dashboard shows relative age. The API refuses
non-`1d` horizon labels (422) and stamps `model_horizon: "1d"`.
and boot-staggered. Configure via `SCHEDULER_{OUTCOMES,MONITORING,EVOLUTION,SHADOW}_SECONDS`.

## Learning loop boundary

The loop is diagnostic, not autonomous. Matured outcomes feed calibration and
drift diagnostics; nothing in `monitor.py` or `analytics.py` retrains,
recalibrates, or promotes a model. A promotion still requires the
pre-registered out-of-sample bar and an explicit admin approval (see above).
The `/mlops` learning-loop card and `/analytics` page state this in the UI.

## Explainability and RSI context

- `GET /predictions/{prediction_id}/explanation` is immutable and generated
  only from the saved `features_snapshot` plus the SHA-verified champion
  artifact. TreeSHAP explains the pre-calibration model; isotonic calibration
  is disclosed as non-additive and attribution is explicitly not causal.
- `GET /predictions/stocks/{symbol}/rsi` computes Wilder RSI from persisted
  daily bars up to the latest close. The stock page labels RSI as context,
  never a trading instruction.
- E075 (`research/evaluations/rsi_e075.json`) tested RSI-only, RSI+existing,
  and regime-conditioned RSI against the frozen champion and technical
  baseline on identical 2020–2024 observations. RSI added no validated
  incremental signal (combined vs baseline Δacc −0.09%, 95% CI −0.59% to
  +0.42%), so the champion feature set is unchanged. All variants covered
  100% of eligible rows; the 40% edge-confidence subset is reported separately.

## Key invariants (all test-covered)

- v1.0 artifact bytes and thresholds frozen (`test_production_guard`).
- No burned range is usable for selection (`test_holdout_integrity`, runner `--purpose`).
- Scheduler loops never touch ORM instances after commit/rollback (`test_scheduler_jobs`).
- Rejected experiments cannot be approved; rollback restores the prior champion (`test_promotion_flow`).
- Zero-volume/flat bars rejected at ingestion; 5x intraday-range cap on quotes and bars.

## Limitations

- Fresh-data selection needs ≥60 matured eval points; until then the cycle
  honestly skips (monitor + resolve outcomes regardless).
- Fundamentals/timestamped news unavailable — excluded, not faked.
- sklearn unpickle version warnings in logs are benign (1.9.0 vs 1.9.1).
- No live-money trading exists anywhere in this system.
