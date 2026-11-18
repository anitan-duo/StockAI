"""Production/causal parity: shared recipe math is deterministic and consistent."""

import pytest


def test_direction_ties_resolve_neutral():
    from services.ml.recipe import direction_from_probs

    assert direction_from_probs(0.5, 0.2, 0.3) == "up"
    assert direction_from_probs(0.2, 0.3, 0.5) == "down"
    assert direction_from_probs(0.2, 0.5, 0.2) == "neutral"
    assert direction_from_probs(0.4, 0.4, 0.2) == "neutral"


def test_no_edge_threshold_and_confidence_cap():
    from services.ml import recipe

    assert recipe.has_clear_edge(0.39, 0.31, 0.30) is False
    assert recipe.has_clear_edge(0.40, 0.30, 0.30) is True
    assert recipe.confidence_from_probs(0.39, 0.30, 0.39) <= 55
    assert recipe.confidence_from_probs(0.7, 0.1, 0.7) > 55


def test_normalize_rejects_degenerate():
    from services.ml.recipe import normalize_probs

    up, neu, down = normalize_probs(0.3579, 0.2771, 0.3650)
    assert abs(up + neu + down - 1.0) < 1e-9
    with pytest.raises(ValueError):
        normalize_probs(0.0, 0.0, 0.0)


def test_ensemble_mean_is_deterministic():
    from services.ml.recipe import combine_ensemble

    out = combine_ensemble([[0.5, 0.3, 0.2], [0.3, 0.3, 0.4]])
    assert out == pytest.approx([0.4, 0.3, 0.3])
    with pytest.raises(ValueError):
        combine_ensemble([])


def test_recipe_hyperparams_match_trainer():
    from services.ml.recipe import get_base_models
    from services.ml.training import ModelTrainer

    trainer = ModelTrainer()
    for name, model in get_base_models().items():
        assert name in trainer.get_base_models()
        assert model.get_params() == trainer.get_base_models()[name].get_params()
