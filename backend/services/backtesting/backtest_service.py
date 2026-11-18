from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.backtest import Backtest, BacktestStatus
from apps.api.models.prediction import Prediction, PredictionDirection
from apps.api.repositories.backtest import BacktestRepository, BacktestTradeRepository
from apps.api.repositories.market import PriceBarRepository
from apps.api.repositories.prediction import PredictionRepository


class BacktestEngine:
    """Backtesting engine using walk-forward methodology."""

    #: Allowed per-window calibration choices (production default first).
    CALIBRATION_CHOICES = ("isotonic", "sigmoid", "none")

    #: Allowed training-label specs (P7). The eval-time direction mapping
    #: must agree with the spec; unknown specs raise instead of guessing.
    #: P10 adds "direction3-1d-1pct" (±1.0% band, same 1d horizon).
    LABEL_SPECS = ("direction3-1d", "binary-1d", "direction3-5d", "direction3-1d-1pct")

    @staticmethod
    def _label_for_row(label_spec: str, closes: list[float], k: int, n_bars: int) -> int | None:
        """Training label for row k (features use bars[:k], i.e. through k-1).

        Returns None for rows that must be skipped (binary neutral zone; 5d
        window running past the series end; zero base price). Skips are
        documented gaps, never imputed. direction3-1d reproduces v1 exactly.
        """
        from services.ml import recipe
        from services.ml.tasks import TASKS

        if label_spec == "direction3-1d":
            base = closes[k - 1]
            ret = (closes[k] - base) / base if base else 0.0
            return 2 if ret > recipe.TARGET_UP_THRESHOLD else (0 if ret < recipe.TARGET_DOWN_THRESHOLD else 1)
        if label_spec == "binary-1d":
            base = closes[k - 1]
            if not base:
                return None
            ret = (closes[k] - base) / base
            if ret > recipe.TARGET_UP_THRESHOLD:
                return 1
            if ret < recipe.TARGET_DOWN_THRESHOLD:
                return 0
            return None
        if label_spec == "direction3-5d":
            task = TASKS["h5d"]
            if k + 4 >= n_bars:
                return None
            base = closes[k - 1]
            if not base:
                return 1
            ret = (closes[k + 4] - base) / base
            return 2 if ret > task.up_threshold else (0 if ret < task.down_threshold else 1)
        if label_spec == "direction3-1d-1pct":
            base = closes[k - 1]
            if not base:
                return 1
            ret = (closes[k] - base) / base
            return 2 if ret > recipe.TARGET_WIDE_UP_THRESHOLD else (0 if ret < recipe.TARGET_WIDE_DOWN_THRESHOLD else 1)
        raise ValueError(f"Unknown label spec: {label_spec}")



    def __init__(self, session: AsyncSession):
        self.session = session
        self.price_bar_repo = PriceBarRepository(session)
        self.prediction_repo = PredictionRepository(session)

    async def run_backtest(self, backtest: Backtest) -> dict[str, Any]:
        """
        Run a walk-forward backtest with real model predictions on historical data.
        If no stored predictions exist for the period, generate them on-the-fly using the model
        and historical price bars (no look-ahead, 252-bar minimum).
        """
        # Try to get stored predictions for the period first
        predictions = await self.prediction_repo.get_history(
            backtest.instrument_id,
            backtest.horizon,
            start_date=backtest.start_date,
            end_date=backtest.end_date,
            limit=10000,
        )

        # If none, generate historical predictions using the model and price bars
        if not predictions:
            # Generate predictions for each day in the period using the unified pipeline
            # This ensures backtest is not blocked by lack of pre-generated predictions
            from datetime import timedelta

            # Get price bars for the full period plus lookback
            lookback_start = backtest.start_date - timedelta(days=400)
            price_bars = await self.price_bar_repo.get_range(
                backtest.instrument_id,
                "1d",
                lookback_start,
                backtest.end_date,
                limit=5000,
            )
            if len(price_bars) < 252:
                return {
                    "error": f"Insufficient price data for backtest: need 252 bars, have {len(price_bars)}",
                    "trades": [],
                }
            # We need to generate predictions for each trading day in the period
            # For efficiency, generate predictions for the period's trading days by reusing the PredictionService
            # but only for dates where we have enough history
            # For now, generate a single prediction at start and use it? No, need per-day
            # Simplest: generate predictions for the period by iterating over price bars and calling the model
            # Use the PredictionService to generate predictions for each day in the period where possible
            # To avoid hammering, generate for every 5th trading day
            generated = []
            # Find price bars within the backtest period
            period_bars = [b for b in price_bars if backtest.start_date <= b.timestamp <= backtest.end_date]
            # Sample every 5 trading days to generate predictions
            for i in range(0, len(period_bars), 5):
                bar = period_bars[i]
                # Need to ensure we have 252 bars before this bar
                idx = price_bars.index(bar)
                if idx < 252:
                    continue
                # Generate prediction for this historical point by using the price bars up to this bar
                # We can call the prediction service with a historical reference date
                # For now, just create a mock prediction based on the model? No, use real model
                # Use the unified pipeline with a temporary cutoff
                try:
                    # Create a temporary prediction by calling the engine with a historical cutoff
                    # We need to generate features for this specific date
                    from services.ml.features import FeaturePipeline
                    import pandas as pd

                    # Build OHLCV up to this bar
                    ohlcv_df = pd.DataFrame(
                        [
                            {"open": float(b.open), "high": float(b.high), "low": float(b.low), "close": float(b.close), "volume": float(b.volume), "timestamp": b.timestamp}
                            for b in price_bars[: idx + 1]
                        ]
                    )
                    ohlcv_df["timestamp"] = pd.to_datetime(ohlcv_df["timestamp"])
                    ohlcv_df.set_index("timestamp", inplace=True)
                    ohlcv_df.sort_index(inplace=True)
                    ohlcv_df = ohlcv_df[["open", "high", "low", "close", "volume"]]
                    pipeline = FeaturePipeline()
                    feats = pipeline.compute_all_features(ohlcv_df)
                    if feats.empty or feats.iloc[-1].isna().any():
                        continue
                    # Load model and predict
                    from services.prediction.prediction_service import PredictionEngine
                    engine = PredictionEngine(self.session)
                    fs_model = engine._load_filesystem_model()
                    if not fs_model:
                        continue
                    model, scaler, feature_names, calibrator, _ = fs_model
                    # Build vector
                    latest = feats.iloc[-1]
                    vec = [float(latest[f]) for f in feature_names]
                    import numpy as np
                    import pandas as pd

                    X = np.array([vec])
                    X_df = pd.DataFrame(X, columns=feature_names)
                    X_scaled = scaler.transform(X_df)
                    X_pred = pd.DataFrame(X_scaled, columns=feature_names)
                    if calibrator is not None:
                        probs = calibrator.predict_proba(X_pred)[0]
                    else:
                        probs = model.predict_proba(X_pred)[0]
                    # Map to prediction
                    from apps.api.models.prediction import PredictionDirection
                    from decimal import Decimal

                    if len(probs) == 3:
                        down_prob, neutral_prob, up_prob = float(probs[0]), float(probs[1]), float(probs[2])
                    else:
                        continue
                    total = up_prob + neutral_prob + down_prob
                    up_prob /= total
                    neutral_prob /= total
                    down_prob /= total
                    if up_prob > down_prob and up_prob > neutral_prob:
                        direction = PredictionDirection.UP
                    elif down_prob > up_prob and down_prob > neutral_prob:
                        direction = PredictionDirection.DOWN
                    else:
                        direction = PredictionDirection.NEUTRAL
                    # Create a pseudo-prediction object
                    class PseudoPred:
                        def __init__(self, direction, up, neutral, down, timestamp, pred_id):
                            self.predicted_direction = direction
                            self.up_probability = Decimal(str(up))
                            self.neutral_probability = Decimal(str(neutral))
                            self.down_probability = Decimal(str(down))
                            self.confidence = int(50 + abs(up - down) * 40)
                            self.prediction_timestamp = timestamp
                            self.id = pred_id
                            self.expected_return = Decimal(str((up - down) * 2.0))

                    import uuid

                    pseudo = PseudoPred(direction, up_prob, neutral_prob, down_prob, bar.timestamp, uuid.uuid4())
                    generated.append(pseudo)
                except Exception:
                    continue
            if generated:
                predictions = generated
            else:
                return {
                    "error": "No predictions could be generated for backtest period (insufficient history or model failure)",
                    "trades": [],
                }

        # Get price data for simulation
        price_bars = await self.price_bar_repo.get_range(
            backtest.instrument_id,
            backtest.horizon,
            backtest.start_date,
            backtest.end_date,
        )

        if not price_bars:
            return {
                "error": "No price data available for backtest period",
                "trades": [],
            }

        # Create price lookup
        price_map = {bar.timestamp: bar for bar in price_bars}

        # Simulate trades
        trades = self._simulate_trades(
            backtest, predictions, price_map, price_bars
        )

        # Calculate metrics
        metrics = self._calculate_metrics(backtest, trades, price_bars, method="final-model-non-causal")

        return {
            "trades": trades,
            "metrics": metrics,
            "equity_curve": metrics["equity_curve"],
            "drawdown_curve": metrics["drawdown_curve"],
            "returns_distribution": metrics["returns_distribution"],
            "methodology": {
                "method": "final-model-non-causal",
                "warning": "Predictions reuse the final production artifact for all historical timestamps; optimistic vs causal evaluation. Prefer method=causal.",
            },
        }

    @staticmethod
    def build_window_training_rows(
        bars: list, eval_index: int, max_train_rows: int = 500, feat_cache: dict | None = None,
        feature_subset: str = "full", market_context: bool = False,
        panel: dict | None = None, symbol: str | None = None,
        label_spec: str = "direction3-1d",
        fundamentals: bool = False, fund_panel: dict | None = None,
        event_only: bool = False,
        earnings: bool = False, earnings_panel: dict | None = None,
    ):
        """Build (X_rows, y, feat_cols) for retraining ahead of eval bar ``eval_index``.

        Boundary contract (temporal cutoff): every training row k satisfies
        k < eval_index, its features use bars[:k] only, and its label resolves
        on bar k whose timestamp is strictly before bars[eval_index]. No
        feature, label, scaler statistic, or calibration observation may come
        from bars[eval_index] or later.

        ``feature_subset`` (recipe.apply_feature_subset) restricts the computed
        columns AFTER computation: removing columns cannot leak. The eval-time
        feature vector must use the same restriction (enforced by the caller).

        ``market_context`` appends the six cross-sectional features
        (services.ml.market_context) computed from ``panel`` strictly at or
        before each row's own bar date. Rows whose context is unavailable are
        dropped (fail closed). Requires ``panel`` + ``symbol``; mismatch
        raises ValueError loudly instead of silently training mismatched rows.

        ``label_spec`` selects the training label without touching features:
        "direction3-1d" (v1 behavior), "binary-1d" (neutral rows dropped),
        "direction3-5d" (label from closes[k+4], ±1.5%),
        "direction3-1d-1pct" (P10: same 1d labels at ±1.0%). Unknown specs raise.

        ``fundamentals`` appends 3 PIT-gated filing features
        (services.ml.fundamentals) from ``fund_panel`` (symbol -> filedDate-ordered
        entries) strictly at or before each row's own bar date. Rows without a
        gated filing are dropped (fail closed). Requires ``fund_panel`` +
        ``symbol``; combining with ``market_context`` raises (untested combo).

        ``event_only`` appends just the binary filing-event marker
        (fund_event_5d, P12) from the same ``fund_panel``. Requires
        ``fund_panel`` + ``symbol``; combining with ``market_context`` or
        ``fundamentals`` raises (untested combos).
        """
        if label_spec not in BacktestEngine.LABEL_SPECS:
            raise ValueError(f"Unknown label spec: {label_spec}")
        if market_context and fundamentals:
            raise ValueError("market_context + fundamentals combo is untested (refusing)")
        if event_only and (market_context or fundamentals):
            raise ValueError("event_only combos are untested (refusing)")
        if earnings and (market_context or fundamentals or event_only):
            raise ValueError("earnings combos are untested (refusing)")
        import pandas as pd

        from services.ml import recipe
        from services.ml.features import FeaturePipeline

        bars = sorted(bars, key=lambda b: b.timestamp)
        closes = [float(b.close) for b in bars]
        pipeline = FeaturePipeline()
        rows: list[list[float]] = []
        labels: list[int] = []
        feat_cols: list[str] | None = None
        row_label_bars: list[int] = []
        start_k = max(252, eval_index - max_train_rows)
        for k in range(start_k, eval_index):
            cached = (feat_cache or {}).get(k)
            if cached is None:
                ohlcv = pd.DataFrame(
                    [
                        {"open": float(b.open), "high": float(b.high), "low": float(b.low), "close": float(b.close), "volume": float(b.volume), "timestamp": b.timestamp}
                        for b in bars[:k]
                    ]
                )
                ohlcv["timestamp"] = pd.to_datetime(ohlcv["timestamp"])
                ohlcv.set_index("timestamp", inplace=True)
                ohlcv.sort_index(inplace=True)
                ohlcv = ohlcv[["open", "high", "low", "close", "volume"]]
                feats = pipeline.compute_all_features(ohlcv)
                if feats.empty or feats.iloc[-1].isna().any():
                    continue
                cached = ([float(feats.iloc[-1][c]) for c in feats.columns], list(feats.columns))
                if feat_cache is not None:
                    feat_cache[k] = cached
            row, cols = cached
            feat_cols = feat_cols or cols
            lab = BacktestEngine._label_for_row(label_spec, closes, k, len(bars))
            if lab is None:
                continue  # documented skip (binary neutral zone / 5d window end)
            labels.append(lab)
            rows.append([float(v) for v in row])
            row_label_bars.append(k)
        if feat_cols is None:
            return rows, labels, feat_cols, row_label_bars
        # Restrict AFTER computation (raw full rows stay cached for reuse).
        keep = recipe.apply_feature_subset(feat_cols, feature_subset)
        idx = [feat_cols.index(c) for c in keep]
        if market_context:
            if panel is None or symbol is None:
                raise ValueError("market_context=True requires panel and symbol")
            from services.ml.market_context import FEATURE_NAMES as _CTX_NAMES
            from services.ml.market_context import cross_sectional_context as _ctx

            panel_closes = {
                s: [(b.timestamp, float(b.close)) for b in bl]
                for s, bl in panel.items()
            }
            kept_rows: list[list[float]] = []
            kept_labels: list[int] = []
            kept_bars: list[int] = []
            for r, lab, k in zip(rows, labels, row_label_bars):
                ctx = _ctx(panel_closes, symbol, bars[k - 1].timestamp)
                if ctx is None:
                    continue  # fail closed: no imputed context, ever
                kept_rows.append([r[j] for j in idx] + [ctx[c] for c in _CTX_NAMES])
                kept_labels.append(lab)
                kept_bars.append(k)
            return kept_rows, kept_labels, keep + list(_CTX_NAMES), kept_bars
        if fundamentals:
            if fund_panel is None or symbol is None:
                raise ValueError("fundamentals=True requires fund_panel and symbol")
            from services.ml.fundamentals import FEATURE_NAMES as _FUND_NAMES
            from services.ml.fundamentals import lookup as _fund_lookup

            entries = fund_panel.get(symbol, [])
            kept_rows = []
            kept_labels = []
            kept_bars = []
            for r, lab, k in zip(rows, labels, row_label_bars):
                fund = _fund_lookup(entries, bars[k - 1].timestamp)
                if fund is None:
                    continue  # fail closed: no gated filing, ever imputed
                kept_rows.append([r[j] for j in idx] + [fund[c] for c in _FUND_NAMES])
                kept_labels.append(lab)
                kept_bars.append(k)
            return kept_rows, kept_labels, keep + list(_FUND_NAMES), kept_bars
        if event_only:
            if fund_panel is None or symbol is None:
                raise ValueError("event_only=True requires fund_panel and symbol")
            from services.ml.fundamentals import EVENT_FEATURE_NAMES as _EVT_NAMES
            from services.ml.fundamentals import event_lookup as _event_lookup

            entries = fund_panel.get(symbol, [])
            kept_rows = []
            kept_labels = []
            kept_bars = []
            for r, lab, k in zip(rows, labels, row_label_bars):
                evt = _event_lookup(entries, bars[k - 1].timestamp)
                if evt is None:
                    continue  # fail closed: no gated filing history at all
                kept_rows.append([r[j] for j in idx] + [evt[c] for c in _EVT_NAMES])
                kept_labels.append(lab)
                kept_bars.append(k)
            return kept_rows, kept_labels, keep + list(_EVT_NAMES), kept_bars
        if earnings:
            if earnings_panel is None or symbol is None:
                raise ValueError("earnings=True requires earnings_panel and symbol")
            from services.ml.earnings import FEATURE_NAMES as _EARN_NAMES
            from services.ml.earnings import lookup as _earn_lookup

            entries = earnings_panel.get(symbol, [])
            kept_rows = []
            for r, k in zip(rows, row_label_bars):
                e = _earn_lookup(entries, bars[k - 1].timestamp)  # always present
                kept_rows.append([r[j] for j in idx] + [e[c] for c in _EARN_NAMES])
            return kept_rows, labels, keep + list(_EARN_NAMES), row_label_bars
        rows = [[r[j] for j in idx] for r in rows]
        return rows, labels, keep, row_label_bars

    @staticmethod
    def generate_causal_predictions(
        bars: list,
        period_start,
        period_end,
        retrain_every_n_eval: int = 4,
        eval_step_bars: int = 5,
        max_train_rows: int = 500,
        calibration: str = "isotonic",
        feature_subset: str = "full",
        market_context: bool = False,
        panel: dict | None = None,
        symbol: str | None = None,
        label_spec: str = "direction3-1d",
        model_family: str = "ensemble",
        fundamentals: bool = False,
        fund_panel: dict | None = None,
        event_only: bool = False,
        recency_halflife: float | None = None,
        earnings: bool = False,
        earnings_panel: dict | None = None,
    ) -> tuple[list, dict]:
        """Pure causal prediction generator (no DB): bars sorted by timestamp.

        Returns (predictions, methodology). Each prediction carries
        ``window_fit_date`` proving its model was fitted before its timestamp.
        Used by run_causal_backtest; unit-tested for temporal causality.

        ``feature_subset`` must match between training rows and the eval-time
        vector (same recipe helper both sides); unknown names raise ValueError.
        ``market_context`` appends cross-sectional features from ``panel``
        (same dates-or-earlier rule); requires ``panel`` + ``symbol``.
        ``label_spec`` selects training labels (direction3-1d default);
        binary specs emit 2-class probabilities with neutral fixed at 0.
        ``model_family`` restricts the fitted models to one family (P9
        ablation); ``ensemble`` (default) is the v1 three-model behavior.
        """
        from datetime import timedelta  # noqa: F401 (kept for signature symmetry)

        import pandas as pd
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.preprocessing import StandardScaler

        from services.ml import recipe
        from services.ml.features import FeaturePipeline

        bars = sorted(bars, key=lambda b: b.timestamp)
        if calibration not in BacktestEngine.CALIBRATION_CHOICES:
            raise ValueError(f"Unknown calibration: {calibration}")
        if feature_subset not in recipe.FEATURE_SUBSET_NAMES:
            raise ValueError(f"Unknown feature subset: {feature_subset}")
        if label_spec not in BacktestEngine.LABEL_SPECS:
            raise ValueError(f"Unknown label spec: {label_spec}")
        if model_family not in recipe.MODEL_FAMILIES:
            raise ValueError(f"Unknown model family: {model_family}")
        if market_context and (panel is None or symbol is None):
            raise ValueError("market_context=True requires panel and symbol")
        if fundamentals and (fund_panel is None or symbol is None):
            raise ValueError("fundamentals=True requires fund_panel and symbol")
        if market_context and fundamentals:
            raise ValueError("market_context + fundamentals combo is untested (refusing)")
        if event_only and (market_context or fundamentals):
            raise ValueError("event_only combos are untested (refusing)")
        if earnings and (market_context or fundamentals or event_only):
            raise ValueError("earnings combos are untested (refusing)")
        if earnings and (earnings_panel is None or symbol is None):
            raise ValueError("earnings=True requires earnings_panel and symbol")
        if recency_halflife is not None and recency_halflife <= 0:
            raise ValueError("recency_halflife must be positive")
        period_idx = [i for i, b in enumerate(bars) if period_start <= b.timestamp <= period_end]
        eval_idx = [i for i in period_idx[::eval_step_bars] if i >= 252]
        methodology: dict[str, Any] = {
            "method": "causal-walk-forward",
            "model": "production-family-logistic+rf300+gb200" if model_family == "ensemble" else f"single-family-{model_family}",
            "model_family": model_family,
            "fundamentals": fundamentals,
            "event_only": event_only,
            "earnings": earnings,
            "recency_halflife": recency_halflife,
            "calibration": f"{calibration}-cv3-if-n>=60-else-uncalibrated",
            "feature_subset": feature_subset,
            "label_spec": label_spec,
            "market_context": market_context,
            "retrain_every_n_eval": retrain_every_n_eval,
            "eval_step_bars": eval_step_bars,
            "n_eval_dates": len(eval_idx),
        }
        if not eval_idx:
            return [], methodology

        pipeline = FeaturePipeline()
        window_models = window_scaler = None
        window_fit_date = None
        n_windows = 0
        generated: list = []
        # Memoize per-k feature rows within this call (identical pipeline +
        # cutoffs, so cached values equal recomputation; ~10x fewer fits).
        feat_cache: dict[int, tuple[list[float], list[str]]] = {}

        for n, i in enumerate(eval_idx):
            if n % retrain_every_n_eval == 0 or window_models is None:
                rows, labels, feat_cols, _ = BacktestEngine.build_window_training_rows(
                    bars, i, max_train_rows=max_train_rows, feat_cache=feat_cache,
                    feature_subset=feature_subset, market_context=market_context,
                    panel=panel, symbol=symbol, label_spec=label_spec,
                    fundamentals=fundamentals, fund_panel=fund_panel,
                    event_only=event_only,
                    earnings=earnings, earnings_panel=earnings_panel,
                )
                import numpy as np

                if feat_cols is None or len(set(labels)) < 2 or len(rows) < 30:
                    continue
                X_train = pd.DataFrame(rows, columns=feat_cols)
                y_train = np.array(labels)
                scaler = StandardScaler()
                X_scaled = pd.DataFrame(scaler.fit_transform(X_train), columns=feat_cols)
                # P16 recency weighting: exponential weights over row positions
                # (oldest->newest) to base + calibration fits only. The scaler
                # stays unweighted (preregistered); eval vectors are unweighted.
                sw = (np.array(recipe.recency_weights(len(rows), recency_halflife))
                      if recency_halflife is not None else None)
                # Production model family (shared recipe): ensemble or one P9
                # ablation family; same calibration path for every arm.
                fitted: dict[str, Any] = {}
                for name, base in recipe.get_family_models(model_family).items():
                    try:
                        m = base.__class__(**base.get_params())
                        m.fit(X_scaled, y_train, sample_weight=sw)
                    except Exception:
                        continue
                    cal = None
                    if calibration != "none" and len(rows) >= recipe.CALIBRATION_MIN_SAMPLES:
                        try:
                            cal = CalibratedClassifierCV(m, method=calibration, cv=recipe.CALIBRATION_CV_FOLDS)
                            cal.fit(X_scaled, y_train, sample_weight=sw)
                        except Exception:
                            cal = None
                    fitted[name] = (m, cal)
                if not fitted:
                    continue
                window_models, window_scaler = fitted, scaler
                window_fit_date = bars[i - 1].timestamp
                n_windows += 1
            if window_models is None:
                continue
            ohlcv = pd.DataFrame(
                [
                    {"open": float(b.open), "high": float(b.high), "low": float(b.low), "close": float(b.close), "volume": float(b.volume), "timestamp": b.timestamp}
                    for b in bars[:i]
                ]
            )
            ohlcv["timestamp"] = pd.to_datetime(ohlcv["timestamp"])
            ohlcv.set_index("timestamp", inplace=True)
            ohlcv.sort_index(inplace=True)
            ohlcv = ohlcv[["open", "high", "low", "close", "volume"]]
            feats = pipeline.compute_all_features(ohlcv)
            if feats.empty or feats.iloc[-1].isna().any():
                continue
            import numpy as np

            # Same subset as training (fail closed if a subset column is
            # missing at eval time — never silently substitute full features).
            try:
                cols = recipe.apply_feature_subset(list(feats.columns), feature_subset)
            except ValueError:
                continue
            if any(c not in feats.columns for c in cols):
                continue
            eval_vals = [float(feats.iloc[-1][c]) for c in cols]
            if market_context:
                from services.ml.market_context import FEATURE_NAMES as _CTX_NAMES
                from services.ml.market_context import cross_sectional_context as _ctx

                panel_closes = {
                    s: [(b.timestamp, float(b.close)) for b in bl]
                    for s, bl in (panel or {}).items()
                }
                ctx = _ctx(panel_closes, symbol or "", bars[i - 1].timestamp)
                if ctx is None:
                    continue  # fail closed: no imputed context, ever
                cols = cols + list(_CTX_NAMES)
                eval_vals = eval_vals + [ctx[c] for c in _CTX_NAMES]
            if fundamentals:
                from services.ml.fundamentals import FEATURE_NAMES as _FUND_NAMES
                from services.ml.fundamentals import lookup as _fund_lookup

                fund = _fund_lookup((fund_panel or {}).get(symbol or "", []), bars[i - 1].timestamp)
                if fund is None:
                    continue  # fail closed: no gated filing, ever imputed
                cols = cols + list(_FUND_NAMES)
                eval_vals = eval_vals + [fund[c] for c in _FUND_NAMES]
            if event_only:
                from services.ml.fundamentals import EVENT_FEATURE_NAMES as _EVT_NAMES
                from services.ml.fundamentals import event_lookup as _event_lookup

                evt = _event_lookup((fund_panel or {}).get(symbol or "", []), bars[i - 1].timestamp)
                if evt is None:
                    continue  # fail closed: no gated filing history at all
                cols = cols + list(_EVT_NAMES)
                eval_vals = eval_vals + [evt[c] for c in _EVT_NAMES]
            if earnings:
                from services.ml.earnings import FEATURE_NAMES as _EARN_NAMES
                from services.ml.earnings import lookup as _earn_lookup

                e = _earn_lookup((earnings_panel or {}).get(symbol or "", []),
                                 bars[i - 1].timestamp)  # always present
                cols = cols + list(_EARN_NAMES)
                eval_vals = eval_vals + [e[c] for c in _EARN_NAMES]
            X = pd.DataFrame([eval_vals], columns=cols)
            X_scaled = pd.DataFrame(window_scaler.transform(X), columns=cols)
            try:
                vectors = []
                for _name, (_m, _cal) in window_models.items():
                    vectors.append((_cal.predict_proba(X_scaled) if _cal is not None else _m.predict_proba(X_scaled))[0])
                probs = recipe.combine_ensemble(vectors)
            except Exception:
                continue
            if label_spec == "binary-1d":
                # 2-class models: classes [0=down, 1=up]; neutral is fixed at
                # 0 by task definition (documented, not hidden).
                if len(probs) != 2:
                    continue
                down_prob, up_prob = float(probs[0]), float(probs[1])
                total = down_prob + up_prob
                if total <= 0:
                    continue
                down_prob, up_prob = down_prob / total, up_prob / total
                neutral_prob = 0.0
                direction = PredictionDirection.UP if up_prob > down_prob else PredictionDirection.DOWN
            else:
                if len(probs) != 3:
                    continue
                # Canonical class order from training: 0=down, 1=neutral, 2=up
                down_prob, neutral_prob, up_prob = (float(probs[0]), float(probs[1]), float(probs[2]))
                try:
                    up_prob, neutral_prob, down_prob = recipe.normalize_probs(up_prob, neutral_prob, down_prob)
                except ValueError:
                    continue
                direction = PredictionDirection(recipe.direction_from_probs(up_prob, neutral_prob, down_prob))

            class PseudoPred:
                def __init__(self, direction, up, neutral, down, timestamp, pred_id, fit_date):
                    self.predicted_direction = direction
                    self.up_probability = Decimal(str(up))
                    self.neutral_probability = Decimal(str(neutral))
                    self.down_probability = Decimal(str(down))
                    self.confidence = recipe.confidence_from_probs(up, down, max(up, neutral, down))
                    self.prediction_timestamp = timestamp
                    self.id = pred_id
                    self.expected_return = Decimal(str((up - down) * 2.0))
                    self.window_fit_date = fit_date

            import uuid

            generated.append(PseudoPred(direction, up_prob, neutral_prob, down_prob, bars[i].timestamp, uuid.uuid4(), window_fit_date))
        methodology["n_windows"] = n_windows
        methodology["execution"] = "signal from bars<i, fill at bar-i close; costs 0.1%+0.05% slippage; stop 5%; TP 10%; entry confidence>=60"
        return generated, methodology

    async def run_causal_backtest(
        self,
        backtest: Backtest,
        retrain_every_n_eval: int = 4,
        eval_step_bars: int = 5,
        max_train_rows: int = 500,
        calibration: str = "isotonic",
    ) -> dict[str, Any]:
        """Causal walk-forward backtest.

        For each evaluation date (every ``eval_step_bars``-th bar in the period),
        predictions come from a model fitted ONLY on bars strictly before that
        date (monthly-ish retraining: refit every ``retrain_every_n_eval`` evals).
        Per window: fresh StandardScaler + production model family
        (logistic/RF300/GB200 per services.ml.recipe) + isotonic calibration
        when sample size allows.

        Execution convention (disclosed): the signal for eval bar *i* uses only
        closes of bars *< i*; the fill is at bar *i*'s close. Costs: 0.1% +
        0.05% slippage, stop 5%, take-profit 10%, confidence>=60 entry gate
        (shared with _simulate_trades).
        """
        from datetime import timedelta

        lookback_start = backtest.start_date - timedelta(days=400)
        price_bars = await self.price_bar_repo.get_range(
            backtest.instrument_id, "1d", lookback_start, backtest.end_date, limit=5000
        )
        if len(price_bars) < 252:
            return {
                "error": f"Insufficient price data for backtest: need 252 bars, have {len(price_bars)}",
                "trades": [],
                "methodology": {"method": "causal-walk-forward"},
            }
        price_bars = sorted(price_bars, key=lambda b: b.timestamp)
        generated, methodology = BacktestEngine.generate_causal_predictions(
            price_bars,
            backtest.start_date,
            backtest.end_date,
            retrain_every_n_eval=retrain_every_n_eval,
            eval_step_bars=eval_step_bars,
            max_train_rows=max_train_rows,
            calibration=calibration,
        )
        if not generated:
            methodology.setdefault("n_windows", 0)
            return {
                "error": "No causal predictions could be generated (insufficient window history or single-class windows)",
                "trades": [],
                "methodology": methodology,
            }

        period_bars = [b for b in price_bars if backtest.start_date <= b.timestamp <= backtest.end_date]
        price_map = {bar.timestamp: bar for bar in period_bars}
        trades = self._simulate_trades(backtest, generated, price_map, period_bars)
        metrics = self._calculate_metrics(backtest, trades, period_bars, method="causal-walk-forward")
        return {
            "trades": trades,
            "metrics": metrics,
            "equity_curve": metrics["equity_curve"],
            "drawdown_curve": metrics["drawdown_curve"],
            "returns_distribution": metrics["returns_distribution"],
            "methodology": methodology,
        }

    def _simulate_trades(
        self,
        backtest: Backtest,
        predictions: list[Prediction],
        price_map: dict,
        price_bars: list,
        transaction_cost_rate: float = 0.001,
        slippage_rate: float = 0.0005,
        confidence_min: int = 60,
    ) -> list[dict]:
        """Simulate trades based on predictions.

        Defaults are the production execution assumptions. Research scenarios
        may pass alternates; production callers must use defaults.
        """
        trades = []
        position = None  # Current position: {'side': 'long'/'short', 'entry_price', 'shares', 'entry_date', 'prediction_id'}
        cash = float(backtest.initial_capital)
        _tc, _sl, _conf = transaction_cost_rate, slippage_rate, confidence_min

        for prediction in predictions:
            pred_date = prediction.prediction_timestamp
            pred_price = price_map.get(pred_date)

            if not pred_price:
                # Find closest price bar
                pred_price = min(
                    price_bars,
                    key=lambda b: abs((b.timestamp - pred_date).total_seconds()),
                )

            current_price = float(pred_price.close)

            # Guard: impossible fills must never create positions
            if not np.isfinite(current_price) or current_price <= 0:
                continue

            # Check if we should exit existing position
            if position:
                exit_signal = self._should_exit(position, prediction, current_price)
                if exit_signal:
                    # Close position with costs (production: 0.1% + 0.05% slippage)
                    transaction_cost_rate = _tc
                    slippage_rate = _sl
                    effective_exit = current_price * (1 - slippage_rate - transaction_cost_rate) if position["side"] == "long" else current_price * (1 + slippage_rate + transaction_cost_rate)
                    pnl = self._calculate_pnl(position, effective_exit)
                    cash += position["shares"] * effective_exit
                    # Use effective price for trade record
                    current_price = effective_exit

                    trades.append({
                        "entry_date": position["entry_date"].isoformat() if hasattr(position["entry_date"], "isoformat") else str(position["entry_date"]),
                        "exit_date": pred_date.isoformat() if hasattr(pred_date, "isoformat") else str(pred_date),
                        "entry_price": Decimal(str(position["entry_price"])),
                        "exit_price": Decimal(str(current_price)),
                        "shares": position["shares"],
                        "side": position["side"],
                        "pnl": Decimal(str(pnl)),
                        "return_pct": Decimal(str((pnl / (position["shares"] * position["entry_price"])) * 100)),
                        "is_winner": pnl > 0,
                        "prediction_id": str(position.get("prediction_id", "")),
                    })
                    position = None

            # Check if we should enter new position
            if not position:
                entry_signal = self._should_enter(prediction, _conf)
                if entry_signal:
                    # Enter position with explicit costs (production: 0.1% + 0.05%)
                    transaction_cost_rate = _tc
                    slippage_rate = _sl
                    effective_entry = current_price * (1 + slippage_rate + transaction_cost_rate) if entry_signal == "long" else current_price * (1 - slippage_rate - transaction_cost_rate)
                    shares = int(cash * 0.95 / effective_entry)  # Use 95% of cash
                    if shares > 0:
                        position = {
                            "side": "long" if entry_signal == "long" else "short",
                            "entry_price": effective_entry,
                            "raw_entry_price": current_price,
                            "shares": shares,
                            "entry_date": pred_date,
                            "prediction_id": str(prediction.id),
                        }
                        cash -= shares * effective_entry

        # Close any remaining position at end with costs
        if position and price_bars:
            last_price_raw = float(price_bars[-1].close)
            transaction_cost_rate = _tc
            slippage_rate = _sl
            last_price = last_price_raw * (1 - slippage_rate - transaction_cost_rate) if position["side"] == "long" else last_price_raw * (1 + slippage_rate + transaction_cost_rate)
            pnl = self._calculate_pnl(position, last_price)
            cash += position["shares"] * last_price

            trades.append({
                "entry_date": position["entry_date"].isoformat() if hasattr(position["entry_date"], "isoformat") else str(position["entry_date"]),
                "exit_date": price_bars[-1].timestamp.isoformat(),
                "entry_price": Decimal(str(position["entry_price"])),
                "exit_price": Decimal(str(last_price)),
                "shares": position["shares"],
                "side": position["side"],
                "pnl": Decimal(str(pnl)),
                "return_pct": Decimal(str((pnl / (position["shares"] * position["entry_price"])) * 100)),
                "is_winner": pnl > 0,
                "prediction_id": str(position.get("prediction_id", "")),
            })

        return trades

    def _should_enter(self, prediction: Prediction, confidence_min: int = 60) -> str | None:
        """Determine if we should enter a position based on prediction.

        Production gate is confidence>=60 and prob>0.5 (shared with live signals);
        research sensitivity scenarios pass alternates explicitly.
        """
        # Enter long on UP predictions with high confidence
        if prediction.predicted_direction == PredictionDirection.UP:
            if prediction.confidence >= confidence_min and prediction.up_probability > Decimal("0.5"):
                return "long"
        # Enter short on DOWN predictions with high confidence
        elif prediction.predicted_direction == PredictionDirection.DOWN:
            if prediction.confidence >= confidence_min and prediction.down_probability > Decimal("0.5"):
                return "short"
        return None

    def _should_exit(
        self, position: dict, prediction: Prediction, current_price: float
    ) -> bool:
        """Determine if we should exit a position."""
        # Exit on opposite signal
        if position["side"] == "long" and prediction.predicted_direction == PredictionDirection.DOWN:
            return True
        if position["side"] == "short" and prediction.predicted_direction == PredictionDirection.UP:
            return True

        # Exit on stop loss (5%)
        entry_price = position["entry_price"]
        if position["side"] == "long":
            if current_price <= entry_price * 0.95:
                return True
        elif current_price >= entry_price * 1.05:
            return True

        # Exit on take profit (10%)
        if position["side"] == "long":
            if current_price >= entry_price * 1.10:
                return True
        elif current_price <= entry_price * 0.90:
            return True

        return False

    def _calculate_pnl(self, position: dict, exit_price: float) -> float:
        """Calculate P&L for a position."""
        entry_price = position["entry_price"]
        shares = position["shares"]

        if position["side"] == "long":
            return (exit_price - entry_price) * shares
        return (entry_price - exit_price) * shares

    def _calculate_metrics(
        self,
        backtest: Backtest,
        trades: list[dict],
        price_bars: list,
        method: str = "causal-walk-forward",
    ) -> dict[str, Any]:
        """Calculate backtest performance metrics with honest zero-trade handling."""
        # Benchmark buy-and-hold over same period
        benchmark_return = Decimal("0")
        if price_bars:
            first_close = float(price_bars[0].close)
            last_close = float(price_bars[-1].close)
            if first_close > 0:
                benchmark_return = Decimal(str(round(((last_close - first_close) / first_close) * 100, 2)))

        if not trades:
            return {
                "total_return": Decimal("0"),
                "annualized_return": Decimal("0"),
                "sharpe_ratio": None,  # unavailable when no trades
                "max_drawdown": Decimal("0"),
                "win_rate": None,  # unavailable, not 0% (would imply losses)
                "profit_factor": None,  # unavailable
                "equity_curve": [],
                "drawdown_curve": [],
                "returns_distribution": [],
                "benchmark_return": benchmark_return,
                "excess_return": Decimal(str(round(float(Decimal("0") - benchmark_return), 2))),
                "trade_count": 0,
                "assumptions": {
                    "is_walk_forward": True,
                    "method": method,
                    "note": ("Causal walk-forward: per-window models fitted only on data before each evaluation date." if method == "causal-walk-forward" else "Historical simulation using final production model (trained on all data up to 2026-08-20), not retrained per period; not strictly out-of-sample. Prefer method=causal."),
                    "transaction_cost": "0.1% per trade (entry+exit)",
                    "slippage": "0.05% per trade",
                    "position_sizing": "95% cash, long/short, single position, 5% stop-loss, 10% take-profit, opposite signal exit",
                    "benchmark": "Buy-and-hold same instrument same period",
                },
            }

        # Equity curve
        initial_capital = float(backtest.initial_capital)
        equity = initial_capital
        equity_curve = []
        peak = initial_capital
        drawdown_curve = []

        for trade in trades:
            pnl = float(trade["pnl"])
            equity += pnl
            equity_curve.append({
                "date": trade["exit_date"],
                "value": round(equity, 2),
            })

            peak = max(peak, equity)
            drawdown = ((equity - peak) / peak) * 100
            drawdown_curve.append({
                "date": trade["exit_date"],
                "value": round(drawdown, 2),
            })

        # Returns distribution
        returns = [float(t["return_pct"]) for t in trades]
        returns_distribution = self._calculate_returns_distribution(returns)

        # Metrics
        total_return = ((equity - initial_capital) / initial_capital) * 100

        # Annualized return
        days = (backtest.end_date - backtest.start_date).days
        if days > 0:
            annualized_return = ((1 + total_return / 100) ** (365 / days) - 1) * 100
        else:
            annualized_return = 0

        # Sharpe ratio (simplified, null if insufficient)
        if len(returns) > 1:
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else None
        else:
            sharpe_ratio = None

        # Max drawdown
        max_drawdown = min([d["value"] for d in drawdown_curve]) if drawdown_curve else 0

        # Win rate (null if no trades already handled, here at least 1 trade so compute)
        winners = sum(1 for t in trades if t["is_winner"])
        win_rate = (winners / len(trades)) * 100 if trades else None

        # Profit factor
        gross_profit = sum(float(t["pnl"]) for t in trades if t["is_winner"])
        gross_loss = abs(sum(float(t["pnl"]) for t in trades if not t["is_winner"]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (Decimal("inf") if gross_profit > 0 else None)
        if profit_factor == Decimal("inf"):
            profit_factor = None

        # Benchmark
        benchmark_return = Decimal("0")
        if price_bars:
            first_close = float(price_bars[0].close)
            last_close = float(price_bars[-1].close)
            if first_close > 0:
                benchmark_return = Decimal(str(round(((last_close - first_close) / first_close) * 100, 2)))
        excess_return = Decimal(str(round(float(total_return - float(benchmark_return)), 2)))

        return {
            "total_return": Decimal(str(round(total_return, 2))),
            "annualized_return": Decimal(str(round(annualized_return, 2))),
            "sharpe_ratio": Decimal(str(round(sharpe_ratio, 2))) if sharpe_ratio is not None else None,
            "max_drawdown": Decimal(str(round(max_drawdown, 2))),
            "win_rate": Decimal(str(round(win_rate, 1))) if win_rate is not None else None,
            "profit_factor": Decimal(str(round(float(profit_factor), 2))) if profit_factor is not None else None,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "returns_distribution": returns_distribution,
            "benchmark_return": benchmark_return,
            "excess_return": excess_return,
            "trade_count": len(trades),
            "assumptions": {
                "is_walk_forward": True,
                "method": method,
                "note": ("Causal walk-forward: per-window models fitted only on data before each evaluation date." if method == "causal-walk-forward" else "Historical simulation using final production model (trained on all data up to 2026-08-20), not retrained per period; not strictly out-of-sample. Prefer method=causal."),
                "transaction_cost": "0.1% per trade (entry+exit)",
                "slippage": "0.05% per trade",
                "position_sizing": "95% cash, long/short, single position, 5% stop-loss, 10% take-profit, opposite signal exit",
                "benchmark": "Buy-and-hold same instrument same period",
            },
        }

    def _calculate_returns_distribution(self, returns: list[float]) -> list[dict]:
        """Calculate returns distribution histogram."""
        bins = [
            (float("-inf"), -3),
            (-3, -2),
            (-2, -1),
            (-1, 0),
            (0, 1),
            (1, 2),
            (2, 3),
            (3, float("inf")),
        ]

        distribution = []
        for low, high in bins:
            if low == float("-inf"):
                count = sum(1 for r in returns if r < high)
                label = f"< {high}%"
            elif high == float("inf"):
                count = sum(1 for r in returns if r >= low)
                label = f"> {low}%"
            else:
                count = sum(1 for r in returns if low <= r < high)
                label = f"{low}% to {high}%"

            distribution.append({"range": label, "count": count})

        return distribution


class BacktestService:
    """Backtest service for managing backtests."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.engine = BacktestEngine(session)
        self.backtest_repo = BacktestRepository(session)
        self.trade_repo = BacktestTradeRepository(session)

    async def create_backtest(
        self,
        user_id: UUID,
        instrument_id: UUID,
        model_version_id: UUID,
        start_date: datetime,
        end_date: datetime,
        horizon: str,
        initial_capital: Decimal,
    ) -> Backtest:
        """Create a new backtest."""
        # Validate dates
        if start_date >= end_date:
            raise ValueError("start_date must be before end_date")
        if end_date > datetime.now(UTC):
            raise ValueError("end_date cannot be in the future")

        backtest = await self.backtest_repo.create_backtest(
            user_id=user_id,
            instrument_id=instrument_id,
            model_version_id=model_version_id,
            start_date=start_date,
            end_date=end_date,
            horizon=horizon,
            initial_capital=initial_capital,
        )
        return backtest

    async def run_backtest(self, backtest_id: UUID, method: str = "causal") -> Backtest:
        """Run a backtest (causal walk-forward by default; method='final' for legacy)."""
        backtest = await self.backtest_repo.get_by_id_with_details(backtest_id)
        if not backtest:
            raise ValueError("Backtest not found")

        if backtest.status == BacktestStatus.RUNNING:
            raise ValueError("Backtest already running")

        # Update status
        await self.backtest_repo.update_status(backtest_id, BacktestStatus.RUNNING)

        try:
            # Run backtest
            if method == "final":
                result = await self.engine.run_backtest(backtest)
            else:
                result = await self.engine.run_causal_backtest(backtest)

            if "error" in result:
                await self.backtest_repo.update_status(
                    backtest_id, BacktestStatus.FAILED, result["error"]
                )
                return backtest

            # Save trades
            trade_data = [
                {
                    "backtest_id": backtest_id,
                    "entry_date": datetime.fromisoformat(t["entry_date"]),
                    "exit_date": datetime.fromisoformat(t["exit_date"])
                    if t.get("exit_date")
                    else None,
                    "entry_price": t["entry_price"],
                    "exit_price": t["exit_price"],
                    "shares": t["shares"],
                    "side": t["side"],
                    "pnl": t["pnl"],
                    "return_pct": t["return_pct"],
                    "is_winner": t["is_winner"],
                    "prediction_id": UUID(t["prediction_id"])
                    if t.get("prediction_id")
                    else None,
                }
                for t in result["trades"]
            ]
            await self.trade_repo.bulk_create_trades(trade_data)

            # Update results
            metrics = result["metrics"]
            await self.backtest_repo.update_results(
                backtest_id=backtest_id,
                total_return=metrics["total_return"],
                annualized_return=metrics["annualized_return"],
                sharpe_ratio=metrics["sharpe_ratio"],
                max_drawdown=metrics["max_drawdown"],
                win_rate=metrics["win_rate"],
                profit_factor=metrics["profit_factor"],
                equity_curve=metrics["equity_curve"],
                drawdown_curve=metrics["drawdown_curve"],
                returns_distribution=metrics["returns_distribution"],
                trades=result["trades"],
            )
            await self.session.commit()

            return await self.backtest_repo.get_by_id_with_details(backtest_id)

        except Exception as e:
            await self.backtest_repo.update_status(
                backtest_id, BacktestStatus.FAILED, str(e)
            )
            raise

    async def get_backtest(self, backtest_id: UUID) -> Backtest | None:
        """Get backtest by ID."""
        return await self.backtest_repo.get_by_id_with_details(backtest_id)

    async def get_user_backtests(
        self, user_id: UUID, skip: int = 0, limit: int = 20
    ) -> list[Backtest]:
        """Get user's backtests."""
        return await self.backtest_repo.get_user_backtests(user_id, skip=skip, limit=limit)
