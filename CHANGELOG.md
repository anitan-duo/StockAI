# Changelog

All notable changes to StockAI are documented here. Dates are UTC.

## [Unreleased] — Phase 7 directional-signal investigation (V1.0 RETAINED)

- Diagnosis (dev E001, n=415): balanced classes, model 0.340 ≈ majority
  0.345, UP over-predicted at 0.339 precision → neutral-band-noise hypothesis.
- `label_spec` engine support (`direction3-1d` bit-identical default,
  `binary-1d` excluding neutrals, `direction3-5d` from closes[k+4], ±1.5%);
  runner `--target` with class-aware metrics and no trading claims for new
  targets; fixed the merger's hardcoded 3-class mapping (was reporting
  Brier 0.34/log-loss 17.9 for binary data — corrected to 0.2695/0.7339,
  verified two ways).
- P7-E006 binary: acc 0.4388, block-boot95 [0.373, 0.481] (bar ≥0.57 FAIL),
  Brier 0.2695 (bar ≤0.235 FAIL), below binary majority (0.514) and momentum
  (0.514) → REJECTED. P7-E007 5d: acc 0.4145, block-boot95 [0.385, 0.450],
  vs same-task majority 0.4024 (+0.012, inside noise) → REJECTED
  (cross-task Δ-vs-E001 comparison was ill-posed across different base
  rates; corrected transparently in P7_LEDGER.md). No holdout opened or
  burned; v1.0 untouched.
- Standing finding (4-for-4 across phases): accuracy lifts without
  calibrated-probability improvement; 1d signal does not transfer to 5d/20d.
- Infra: block-bootstrap CIs (+ Wilson) in merger (bugfix: single-block
  sampling → proper n_blocks resampling); paired `compare_configs.py`;
  new tests: `test_label_specs` (4), `test_tasks` (3), `test_merge_batches` (2).

## [Unreleased] — scenario lab + multi-horizon tasks + trading policy

### Three forecast tasks (frozen definitions, research scope)
- `services/ml/tasks.py`: h1d (±0.5%, production v1.0), h5d (±1.5%),
  h20d (±3.0%) — separate targets/metrics/eligibility, shared feature
  library. Long-only BUY/SELL/HOLD policy with pre-registered cost-band
  correctness (`judge_action`); SELL exits, never shorts; HOLD must sit
  inside the band (never correct by default).
- Champion scored on all three over dev (n=415 each,
  `v2_dev/champion_horizons.json`): direction acc h1d 0.376 / h5d 0.357 /
  h20d 0.359 — the 1d signal does not transfer; independent evidence for
  the 1d-only production horizon. Action accuracy ~0.09: the champion
  effectively abstains (matches NO CLEAR EDGE).

### Historical scenario lab (blind predict-then-reveal)
- New tables (migration `a7e4c9d12f5b`): scenarios, challenge_attempts,
  streaks, error_diagnoses. Server-enforced blindness (bars ≤ cutoff only),
  eligible-session date mapping, frozen idempotent reveals, repeat tracking
  (repeats never extend streaks), final-split training quarantine.
- 10/10 streak engine + rule-based error auto-diagnosis (stale-data,
  volatility-regime, threshold, miscalibration, unclassified-as-noise).
- API `/scenarios/*` (auth; 422/404/409 honest states) + `/scenarios` Lab UI
  (blind chart, commit, reveal, streaks, history, diagnoses) + nav entry.
- Verified live end-to-end (submit → reveal → streak) and by E2E
  (`scenarios.spec.ts`: blind flow + unauth 401); backend integration tests
  cover blindness, idempotency, repeats, quarantine, multi-horizon labels.

## [Unreleased] — continuous model improvement system

### MLOps architecture (new)
- DB registries via migration `9f3c1a2b7d4e`: `experiments`, `training_jobs`,
  `model_champions` (partial unique index = one current champion),
  `model_promotions`, `drift_observations`, plus `source`/`note` on
  `prediction_outcomes`. Verified on a clean database.
- Champion: v1.0 row seeded (`ensemble-v1.0`, sha `cafe9216…`); inference
  resolves the champion and hash-verifies bytes (fail closed); pinned-hash
  fallback only on fresh DBs.
- Outcome resolution job (hourly): resolves matured 1d labels from real bars
  with the original ±0.5% target; idempotent; 65 outcomes resolved, 0 dupes;
  live 30d accuracy 0.385 / Brier 0.227 — matching research OOS.
- Challenger cycle (daily, locked, budgeted): skips without ≥60 fresh
  unburned evals; frozen configs; embargo on reused ranges; stale-worker
  auto-fail; never promotes. First live cycle completed and honestly rejected
  (n=38 < 60).
- Shadow evaluation (hourly): hash-verified challenger inference under
  challenger versions; production listings untouched.
- Monitoring (hourly): confirmed-vs-provisional split, drift alarms (n≥30,
  deduped), acknowledge flow.
- Admin API `/mlops/*` (reads authenticated, mutations superuser-only):
  champion (with live hash verification), experiments, jobs, promotions,
  monitoring, approve (server-side bar re-verification + atomic switch),
  reject, rollback (reversing row), manual evolution trigger.
- `/mlops` UI: champion card, monitoring, drift, experiments with
  approve/reject, jobs, promotions; role-gated controls, honest empties.
- Removed dead snapshot-based outcome evaluator (competing semantics).
- `ModelRegistry` index persists (activate survives restarts).
- New tests: lifecycle, champion, outcomes-idempotency, mlops API/auth,
  promotion/rollback mechanics, shadow, scheduler-jobs, registry.

## [Unreleased] — 2026-10-08 (one-shot production completion)

### Phase 6 result: V1.0 RETAINED (information ceiling, not mechanics)
- Single bounded information-set experiment P6-E005 (6 cross-sectional market
  features from the frozen 19-symbol panel, strictly historical per row,
  `--market-context` engine+runner plumbing, base = E002 normalized):
  n=415, acc **0.3976** (Δ +0.058, passes) / Brier **0.2215** (Δ −0.005,
  fails pre-registered −0.01). No E006, no holdout opened, nothing promoted.
- Full ledger: `research/evaluations/P6_LEDGER.md`. Batch records
  `v2_dev/p6_e005_b{1,2,3}.json` + merged file.
- New tests: `test_market_context` (5), `test_market_context_engine` (3).

### Scheduler expiry stall (found live: predictions capped at ~1/run)
- All three scheduler loops touched ORM instances after loop
  commit/rollback expired them → `MissingGreenlet` cascade swallowed
  per-item, so only the first instrument per run ever succeeded. Loops now
  extract plain tuples up front; alerts re-checks ACTIVE via fresh read
  (guard preserved). Scheduler errors now log tracebacks (`logger.exception`).
- New regression test: multi-iteration commit/rollback loop over real rows.
- Follow-up: hourly+ jobs now `require_lock=True` (dual workers duplicated
  predictions: 38 same-instrument-hour groups); freshness-critical
  quotes/history stay fail-open. Policy documented in scheduler + mlops.md.

### Zero-volume quarantine + corrupt-bar cleanup (found live: 10/19 symbols unpredicted)
- 60 zero-volume holiday/weekend stubs (all IN/EU, all yahoo) poisoned
  `vol_price_corr_20d` (inf pct-change → NaN → inference fail-closed for
  weeks). Ingestion now rejects **all** zero-volume bars plus a 5x
  intraday-range cap (quotes and bars); 60 stubs deleted (audited counts);
  quote-derived bars skipped when volume-less and stamped with the real
  adapter name. After cleanup: predictions 19/19 succeeding, 0 failed.
- Caught in the same sweep: an INFY 2026-10-07 bar (open 10.41 vs high
  1009.00 — 100x provider unit error) that passed OHLC checks; the range
  cap now rejects this class. New tests: 3 validation cases.

### Exchange-endpoint MissingGreenlet (found by route fuzz: 31/32 clean)
- `GET /markets/exchanges/{code}` 400'd on lazy `exchange.market`;
  `ExchangeRepository` now eager-loads market for all callers.

### Screener zero-price fabrication (found by route fuzz follow-up)
- `ScreenerResult.price/change_percent` were `Decimal("0")` without snapshot
  data — a fabricated price. Now nullable (None, rendered "—"); price filters
  fail closed on missing prices; `volatility` reads the real unified key
  (`realized_vol_20d`, was always-null `volatility_20`). New integration
  tests: `test_screener_honesty.py` (2).

### Champion-scoped production reads (found live: test challenger rows reachable)
- Integration-test shadow predictions were technically servable as production
  through unfiltered latest/top/screener/alert queries. All production reads
  now filter to the champion version id (audit/shadow paths unaffected).
  New regression test: `test_champion_scoping.py`.

### Prediction age + version transparency (§16)
- Top-list responses carry `prediction_timestamp` + `model_version`;
  history items carry `model_version`. Predictions page cards show
  "as of Xh ago · ensemble-v1.0" with >24h stale styling; dashboard edge
  shows relative age. New E2E assertions + contract test fields.

## [Unreleased] — 2026-10-08 (one-shot production completion)

### Horizon honesty (§15 — the "horizon lie" is fixed)
- The v1.0 model natively forecasts the **next trading day**, but the API
  accepted `horizon=1w|1m` and the UI promised "estimate for the next 1
  week/month". Now: all 4 prediction endpoints return **422
  UNSUPPORTED_HORIZON** for non-`1d` horizons, and every prediction response
  carries `model_horizon: "1d"` (new `MODEL_NATIVE_HORIZON` recipe constant).
- Frontend: stock page horizon tabs replaced with a fixed "1D · next trading
  day" chip; predictions filter locked to 1D; settings default-horizon lists
  only the supported window. Verified live (422 + `model_horizon` + real
  factor output). New integration tests: `test_prediction_horizons.py` (4).
- Factors endpoint repaired: it read nonexistent snapshot keys
  (`macd`-as-dict, `relative_volume_20`, `volatility_20`) and always emitted
  empty output; now reads the unified schema (`macd_histogram`,
  `rel_volume_20d`, `realized_vol_20d`) — e.g. AAPL returns MACD/SMA/RSI
  statements from real features.

### Hydration robustness (React #418 class bug, found by E2E)
- `/backtesting` threw a hydration text-mismatch whenever the static
  prerender date differed from the visit date (date defaults computed during
  render). Defaults are now client-only (`useState('')` + mount effect);
  same latent pattern fixed in settings (`lastRefresh`). `routes.spec`
  (zero-pageerror assertions on all 9 routes) is the regression guard.
- Emoji flags replaced with US/IN/EU code chips everywhere functional
  (markets, predictions, settings, landing, utils) — headless/minimal
  systems lack emoji fonts and rendered tofu boxes.

### Registry (§28, bounded)
- `ModelRegistry` index (`models` + `active_versions`) now persists to
  `registry_index.json`: `activate`/`register` survive restarts and work
  across requests (previously in-memory only — forgotten immediately).
  Corrupt index fails open to the filesystem fallback. v1.0 serving path
  untouched. New tests: `test_registry_persistence.py` (2).

## [Unreleased] — 2026-10-06 (Phase 5: predictive-intelligence research)

Question: does the data contain stronger predictive signal than v1.0, capturable
with a reproducible, causally valid model? Answer: **no promotable improvement
found — v1.0 stays** (successful research conclusion, consistent with Phase 3).

- **Baseline re-verified**: `model.pkl` sha256 `cafe9216…` intact (guard tests
  13 passed); E0 dev reproduction bit-identical (P5-E001: n=415, acc 0.3398,
  Brier 0.2261 vs E0 0.340/0.226). v1.0 artifacts, recipe, thresholds, and both
  burned holdouts untouched; no holdout opened in Phase 5.
- **Dataset audit (live DB)**: 19 symbols, 9,441 bars, 0 OHLC violations,
  0 non-positive, 0 future, 0 duplicates; survivorship/multi-currency caveats
  recorded in `research/evaluations/P5_LEDGER.md`.
- **Framework** (all pre-registered in the ledger before running): P5-E00x IDs,
  promotion rule (dev Δacc ≥ +0.05 AND ΔBrier ≤ −0.01, same sign in 2/3
  markets), single bounded follow-up, then stop. Runner now enforces
  burned-range refusal for selection (`--purpose selection|final-eval`) and
  supports leak-proof `--feature-subset full|normalized` (post-computation
  column restriction threaded through training + eval).
- **Results** (identical dev grid, n=415): E002 normalized+isotonic acc
  **0.4024** (Δ +0.0626, passes acc leg) but Brier 0.2225 (Δ −0.0036, fails
  Brier leg) → no promotion. E004 normalized+sigmoid acc 0.3494 / Brier
  0.2217 (fails both; gains do not stack). Bound respected: no E005, no new
  holdout, no artifact change.
- **Tests**: new `test_target_definition` (6), `test_feature_subset` (7),
  `test_p5_runner_guard` (2); fixed 2 regressions my changes introduced
  (scheduler 4-task wiring test; failure-injection nameless stub → defensive
  production `getattr`). Backend total 112+15 new green; vitest 27 green.
- Full ledger: `research/evaluations/P5_LEDGER.md` (rules, audit, per-market
  tables, decision). Batch records: `v2_dev/p5_e001/e002/e004_{b1,b2,b3}.json`
  + merged files.

## [Unreleased] — 2026-10-04 (autonomous completion: live-stack verification)

Verified against the real stack (Postgres 16 + Valkey 8 + API + prod frontend
build, all running locally — including fully containerized via
`docker compose up --build`: 4/4 containers healthy). E2E: **20/20 green**
(smoke 6, charts 5, routes 9) + 4 visual captures reviewed. Backend:
**112 passed** (unit+ml+providers+integration 91, causal+cutoff 7,
live backtesting 7, research holdout 7). Frontend: vitest 27, `tsc` 0 errors,
16-route production build. Clean-DB migration verified (19 tables from zero).

### Bugs found by live testing and fixed
- **`GET /markets/instruments/{symbol}` 500** (MissingGreenlet on
  `exchange.market` during response validation) — now eager-loads
  exchange+market. Found because watchlist/alert instrument resolution failed
  at runtime; covered by new charts/routes E2E.
- **Historical gaps never healed**: `ingest_historical` was forward-only
  (`start = latest + 1µs`), so the Sep-2026 gap (bars ended Aug-21, quotes only
  added Oct days) could never backfill. Now gap-aware (indexed existing-
  timestamp scan in `[start, end]`, skip only those). Proved live: AAPL
  412 → 440+ bars, continuous Aug→Oct, all from real provider data.
- **New `run_history_backfill` scheduler job** (every 6h,
  `SCHEDULER_HISTORY_SECONDS=21600`, Valkey-locked, staggered start) using the
  gap-aware path. Scheduler startup staggered (quotes +15s … history +120s)
  so boot stays fast ("Application startup complete" in ~40s).
- **Provenance**: historical bars were stamped `source="fallback"`.
  The fallback router now stamps the real adapter name into `bar.metadata`,
  and ingestion persists it (defensive `getattr`, covered by failure-injection
  test with a nameless stub).
- **Alerts UI used wrong enums** (`price`/`above` → backend 422). Form now
  uses `price_above/price_below/price_change_pct/volume_above` +
  `gt/lt/gte/lte/crosses_*`. Verified end-to-end: create → list → ack
  semantics → IDOR 404.
- **Markets page**: `^STOXX50E` mis-regioned as United States (added `^STOXX`
  key); emoji flags replaced with US/IN/EU code chips (headless systems lack
  emoji fonts); removed false "Showing sampled data" copy (the error path
  never had sampled data) — now states sections stay empty and labeled.
- **E2E selectors**: login tests matched both header and form "Sign in"
  buttons (strict-mode violation) — scoped to `form button[type=submit]`;
  NaN assertion narrowed to `\bNaN\b` ("financial" contains "nan").
- **`GET /markets/overview` parallelized** (`asyncio.gather`, order
  preserved, no session use): warm-cache 0.2s; cold Sunday ~7s documented
  (Alpha 5/min limiter serializes fallthrough under scheduler contention).

### Live-verified behavior (Sunday 2026-10-04, markets closed)
- Quote: AAPL $333.69 via live fetch, honestly `DELAYED` (Friday close).
- History: limits 7/30/90/365/1250/2500 all newest-biased, sorted, zero
  pre-2005 bars; MAX returns full available history (440), never clipped.
- Failure states: ingest-without-token 401, bad symbol/exchange 404,
  duplicate watchlist item 409, ack-on-ACTIVE honestly rejected,
  cross-user alert access 404, unknown stock page shows honest empty state.
- Screenshots reviewed: dashboard command center, markets (8 live indices),
  stock candlestick + SMA20 + prediction panel, mobile 390px (selector rows
  scroll horizontally after `overflow-x-auto` fix).

### Residual risks (documented, not hidden)
- `npm audit`: 6 high via `braces` (transitive through shadcn CLI tooling,
  unreachable from the prod bundle; fix needs breaking shadcn downgrade).
- Cold-cache overview ~7s on weekends under scheduler contention (warm 0.2s).
- Real provider keys live in untracked `.env` files — rotate before any
  public push. Never committed (verified: no `.env` in `git ls-files` or
  history).
- No global API rate limit / TrustedHost (only login throttle + auth-gated
  ingest); noted for operations.

## [Unreleased] — 2026-10-04 (professional charting system)

### Charting (mandatory spec)
- **Engine replaced**: `ChartContainer` previously emulated candlesticks with
  four recharts `Line` series (no real OHLC rendering). It is now a thin
  adapter over **`ProChart` + lightweight-charts v5** — true candlestick, OHLC
  bars, line, area, baseline, plus real-volume histogram. Single source of
  truth: every type consumes the same backend `HistoricalBar[]`; switching
  types only reshapes, never changes values (test-locked).
- **Indicators from real data** (`src/lib/indicators.ts`, no randomness, gaps
  never filled): SMA/EMA (classic seed), anchored VWAP, Bollinger (20,2),
  RSI 14 (Wilder), MACD 12/26/9, Stochastic 14/3, ATR 14 (Wilder), relative
  volume 20, %-change rebasing, objective swing H/L markers. Warmup periods
  emit honest gaps.
- **Sub-chart panes** (`IndicatorPane`): RSI / MACD / Stochastic / ATR /
  RelVol with reference bands (30/70, zero, 20/80) labeled as guides — zero
  buy/sell language.
- **Stock page**: 9 timeframes (added **5D**), 5 chart types, VWAP/BB overlays,
  oscillator panes, **%-change (rebased) view**, swing markers, volume toggle,
  **fullscreen (esc to exit)**, crosshair legend with exact UTC timestamp +
  OHLCV, honest unavailable/empty states naming the provider/timeframe.
- **Tests**: `src/lib/indicators.test.ts` — 27 vitest cases (hand-computed
  SMA/EMA/RSI/MACD/Stoch/ATR expectations, mapping purity, 2001 regression).
  `npm run test:unit` → **27 passed**. `tsc --noEmit` 0 errors, `npm run build`
  16 routes OK. Backend unit suite still **42 passed, 1 skipped**.
- **No fake data**: `Math.random` appears only in `generateId()` (toast ids);
  charts contain zero randomness; missing data renders gaps/UNAVAILABLE.

## [Unreleased] — 2026-10-04 (stale-data root-cause + command-center pass)

### Root causes fixed (why 2001-era data could appear as current)
- **Market-code mismatch (IN/EU vs India/Europe)**: DB seeds `US/IN/EU` but the
  provider router only registered `US/India/Europe`, so every IN/EU live lookup
  found zero providers and silently fell back to persisted bars. Fixed by
  registering both spellings (`factory.py`) + alias-aware
  `ProviderRouter.get_all_providers` + `normalize_market_code` + `INDEX_UNIVERSE`
  now uses DB codes `US/IN/EU`. New tests: `test_data_integrity.py`.
- **History returned oldest-N, not newest-N**: `PriceBarRepository.get_range`
  used `ASC + LIMIT`, so a 30-bar chart over a decade-long series showed the
  oldest (e.g. 2001) candles. Now fetches `DESC + LIMIT` (newest) and returns
  ASC for rendering.
- **History window clipped MAX/5Y to 1Y**: `GET history` defaulted
  `start=end-365d` regardless of `limit`. Now sizes the window from `limit`
  (daily bars ×1.6 for weekends, weekly/monthly scaled) so 5Y/MAX work.
- **Future-timestamp guard**: `ingest_historical` now rejects bars >5 min in the
  future; ancient bars remain valid *history* but classify `STALE` and are never
  `presentable_as_current` (regression test locks this).

### Backend hardening
- `POST /instruments/{symbol}/ingest` now requires auth (`get_current_user`) —
  previously unauthenticated quota-burn/DoS vector.
- Docs (`/docs`, `/redoc`, `/openapi.json`) disabled when `DEBUG=false`;
  added `GZipMiddleware` for history/chart payloads.

### Frontend — command-center redesign
- New premium dashboard (`/dashboard`): ticker tape, live-coverage strip,
  market overview with provider/freshness, movers, model edge, alerts panel,
  ⌘K search, 60s auto-refresh, honest empty/stale states.
- New global command palette (`⌘K`): backend-ranked instrument search +
  jump-to commands, keyboard navigable, `esc` to close.
- Header search now autocompletes with exchange-disambiguated results
  (`SYM + EXCHANGE + company + market`) instead of blind ticker push.
- New `/alerts` page (was API-only): create/acknowledge/delete, auth-gated,
  exchange-aware instrument resolution.
- Design system: Tailwind v4 (`@import "tailwindcss"` + `@config`),
  `tw-animate-css`, glass/terminal surfaces, ticker tape, `kbd` style,
  `prefers-reduced-motion` support; `cn()` now uses `clsx` + `tailwind-merge`.
- New `not-found.tsx` / `error.tsx` / `loading.tsx` boundaries.
- Build: 16 routes (was 15), `tsc --noEmit` 0 errors.

## [Unreleased] — 2026-10-04 (prior)

Data-correctness and freshness-hardening pass (evidence-based audit fixes).

- **Freshness engine** (`backend/services/freshness.py`): formal
  `FRESH / RECENT / DELAYED / STALE / UNAVAILABLE` classification with
  session-aware thresholds (open vs closed markets; 4-day closed-market
  tolerance for weekends/holidays; future-timestamp rejection; ingestion-time
  bound). Unit-tested in `tests/unit/test_freshness.py`.
- **Quote endpoint rebuilt** (`GET /markets/instruments/{symbol}/quote`):
  - now attempts a live provider fetch (30s Valkey-cached, stale responses
    are never seeded into the cache);
  - falls back to the latest persisted snapshot with an honest freshness
    label instead of presenting it as a real-time quote;
  - the last-resort daily-bar fallback no longer fabricates
    `previous_close = bar.open`; it derives the previous close from the
    prior session bar and labels the result `stale`.
  - response now carries `provider`, `freshness`, `delayed`,
    `source_timestamp`, `ingested_at`, `exchange`, `currency`.
- **New `GET /markets/overview`**: major index quotes (S&P 500, NASDAQ,
  Dow, NIFTY, SENSEX, DAX, FTSE, EURO STOXX 50) fetched live with 60s
  caching plus top gainers/losers from persisted snapshots. Missing data is
  absent — never synthesized.
- **Fixed broken endpoint** `POST /markets/instruments/{symbol}/ingest`
  (called `ingest_quotes` with a wrong tuple arity and a nonexistent
  positional argument; also now commits the session).
- **Yahoo provider timestamps**: historical bars now convert
  exchange-local timestamps to UTC instead of relabeling wall time
  (`replace(tzinfo=utc)` bug); quote metadata carries provider currency.
- **Frontend consumes backend freshness** (no client-side staleness
  heuristics): new `FreshnessBadge` (LIVE/RECENT/DELAYED/STALE/DATA
  UNAVAILABLE + relative age) on the stock page, markets page index cards,
  and dashboard overview cards. Dashboard and markets page now use
  `/markets/overview` instead of market-table rows that had no prices.
  Removed the client-side "Live/Delayed" fabrication on index cards.
- TypeScript check passes (`tsc --noEmit` 0 errors).

Runtime-verification fixes (found live-probing the new endpoints):

- **Provider source-timestamp honesty (all four adapters)**: quotes
  previously stamped `datetime.now()` as the data time and Alpha Vantage
  additionally hardcoded `market_status="open"`, so a weekend fetch of
  Friday's close was served as a `fresh`/live quote. Now:
  - Yahoo uses `regularMarketTime` (epoch) and maps `marketState`
    (REGULAR/PRE/POST/CLOSED) honestly;
  - Finnhub uses the quote's own `t` epoch and reports session state as
    unknown (its payload carries none);
  - Alpha Vantage uses `07. latest trading day`, flags the payload
    `source_date_only`, and labels prior-session data `end_of_day`;
  - Twelve Data requests `timezone=UTC` and parses the quote's `datetime`.
  When no source instant exists at all, the provider falls back to fetch
  time with session status `unknown` (never presented as live).
- **Market-session engine** (`backend/services/market_session.py`): pure
  calendar/session helper over the Market row (IANA timezone, trading
  hours) returning `pre-market | open | after-hours | closed`. The quote
  and overview routes resolve provider `unknown` session status through it
  and refine date-only source timestamps to the provable session-open
  bound (never newer than the truth). Weekends are always closed; exchange
  holidays are not modeled (documented limitation). Unit-tested in
  `tests/unit/test_market_session.py`.
- **Async lazy-load crashes in markets routes**: `exchange.market` (a lazy
  relationship) was accessed inside async request paths, raising
  `MissingGreenlet` — the quote endpoint 500ed and the overview movers
  query failed silently (empty gainers/losers). The movers query now
  eager-loads `Exchange.market`, the quote/ingest routes select the Market
  row by FK, and the movers failure path logs instead of swallowing.
- **`stale` overview flag** now also considers movers-section failures
  observable via logging (empty movers = unavailable, not "no movers").

## [1.0.0] — 2026-10-02

First verified release.

- Backend: FastAPI + SQLAlchemy 2 + Postgres + Valkey; JWT auth with rotation
  and revocation; watchlists, alerts (with scheduled evaluation), screener,
  backtesting (causal walk-forward default), training endpoints (admin-gated).
- ML: 87-feature pipeline (252-bar lookback), logistic/RF300/GB200 ensemble
  with isotonic calibration, shared `services/ml/recipe.py`; honest
  `NO CLEAR EDGE` / `UNAVAILABLE` semantics; versioned artifacts with SHA-256
  manifests.
- Frontend: 15 Next.js routes, TypeScript-clean production build, headless
  Chromium E2E smoke suite (6/6).
- Research: frozen protocol, snapshots with hashes, negative Phase 2 result
  (accuracy 0.425 < majority 0.466) and rejected Phase 3 candidate preserved;
  v1.0 model frozen; holdouts burned and guarded.
- Verification at release: 80/80 backend tests, tsc 0 errors, 15-route build,
  6/6 E2E, 4/4 Docker healthy, Alembic at head, npm audit 0 vulnerabilities.

Known limitations: predictive evidence is modest by measurement; email/push
delivery is not implemented; E2E covers smoke paths only. See README and
`docs/production/PRODUCTION_READINESS.md`.
