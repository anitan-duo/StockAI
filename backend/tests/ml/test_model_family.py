"""P9 model-family ablation mechanics: restriction-only, production default intact.

Unit tests on recipe helpers and small causal-engine fixtures. Restricting to
one family fits a subset of the same models with the same calibration path;
``ensemble`` (default) is byte-identical v1 behavior; unknown names fail loudly.
"""

import pytest

from services.ml import recipe


def test_families_advertised():
    assert set(recipe.MODEL_FAMILIES) == {
        "ensemble", "logistic", "random_forest", "gradient_boosting",
    }


def test_ensemble_is_all_three_models():
    models = recipe.get_family_models("ensemble")
    assert set(models) == {"logistic", "random_forest", "gradient_boosting"}
    assert set(models) == set(recipe.get_base_models())


def test_single_family_restricts_only():
    models = recipe.get_family_models("logistic")
    assert set(models) == {"logistic"}
    assert models["logistic"].get_params() == recipe.get_base_models()["logistic"].get_params()


def test_unknown_family_raises():
    with pytest.raises(ValueError):
        recipe.get_family_models("bogus")


def _bars(n: int = 400, start: float = 100.0):
    from datetime import datetime, timedelta, timezone

    from tests.ml.test_feature_subset import _Bar

    out = []
    px = start
    for i in range(n):
        phase = (i // 5) % 4
        step = 0.012 if phase == 0 else (-0.011 if phase == 2 else 0.001)
        px *= 1.0 + step
        out.append(
            _Bar(
                datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                px,
                i,
            )
        )
    return out


def test_engine_logistic_only_end_to_end():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    preds, method = BacktestEngine.generate_causal_predictions(
        bars, bars[380].timestamp, bars[-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5,
        max_train_rows=100, calibration="none", model_family="logistic",
    )
    assert method["model_family"] == "logistic"
    assert len(preds) > 0
    for p in preds:
        assert p.window_fit_date < p.prediction_timestamp
        assert float(p.up_probability) + float(p.neutral_probability) + float(p.down_probability) == pytest.approx(1.0, abs=1e-4)


def test_engine_default_is_ensemble():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    _, method = BacktestEngine.generate_causal_predictions(
        bars, bars[380].timestamp, bars[-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5,
        max_train_rows=100, calibration="none",
    )
    assert method["model_family"] == "ensemble"
    assert method["model"] == "production-family-logistic+rf300+gb200"


def test_engine_unknown_family_raises():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    with pytest.raises(ValueError):
        BacktestEngine.generate_causal_predictions(
            bars, bars[380].timestamp, bars[-1].timestamp, model_family="bogus",
        )


def test_recency_weights_values():
    from services.ml.recipe import recency_weights

    w = recency_weights(400, 100.0)
    assert len(w) == 400
    assert w[-1] == pytest.approx(1.0)
    assert w[0] == pytest.approx(0.5 ** (399 / 100.0))
    assert all(a < b for a, b in zip(w, w[1:]))  # strictly increasing
    with pytest.raises(ValueError):
        recency_weights(100, 0.0)
    with pytest.raises(ValueError):
        recency_weights(100, -5.0)
    with pytest.raises(ValueError):
        recency_weights(0, 100.0)


def test_engine_recency_end_to_end_and_default_off():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars(400)
    preds, method = BacktestEngine.generate_causal_predictions(
        bars, bars[380].timestamp, bars[-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5,
        max_train_rows=100, calibration="none", recency_halflife=100.0,
    )
    assert method["recency_halflife"] == 100.0
    assert len(preds) > 0
    for p in preds:
        assert p.window_fit_date < p.prediction_timestamp
        assert float(p.up_probability) + float(p.neutral_probability) + float(p.down_probability) == pytest.approx(1.0, abs=1e-4)
    _, method0 = BacktestEngine.generate_causal_predictions(
        bars, bars[380].timestamp, bars[-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5,
        max_train_rows=100, calibration="none",
    )
    assert method0["recency_halflife"] is None
    with pytest.raises(ValueError):
        BacktestEngine.generate_causal_predictions(
            bars, bars[380].timestamp, bars[-1].timestamp, recency_halflife=-1.0,
        )
