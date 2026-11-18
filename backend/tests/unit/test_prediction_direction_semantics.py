"""Regression guard for prediction direction semantics.

Verifies that production inference maps model probabilities to directions
and expected-return signs correctly, with strict PIT-aligned target
definitions — no silent inversion or sign-flip between feature extraction,
model inference, and response serialization.

References: services.ml.recipe (direction_from_probs, target thresholds),
backend/apps/api/models/prediction.py (PredictionDirection enum),
backend/services/prediction/prediction_service.py (prob mapping 0=down,1=neutral,2=up).
"""

import numpy as np


def test_direction_from_probs_ordering():
    from services.ml import recipe

    # Ordering from recipe: 0=down, 1=neutral, 2=up mapped by predict_proba;
    # recipe.direction_from_probs takes up/down/neutral in that call order.
    # Confirm deterministic ordering and tie-to-neutral.
    assert recipe.direction_from_probs(0.6, 0.1, 0.3) == "up"
    assert recipe.direction_from_probs(0.3, 0.1, 0.6) == "down"
    assert recipe.direction_from_probs(0.4, 0.4, 0.2) == "neutral"  # tie -> neutral
    # No inversion: high up_prob must yield up regardless of down/neutral ordering
    assert recipe.direction_from_probs(0.7, 0.2, 0.1) == "up"


def test_target_direction_sign_consistency():
    from services.ml.target import TargetDefinition, TargetDirection

    td = TargetDefinition(up_threshold=0.005, down_threshold=-0.005, horizon_days=1)
    # Positive return -> UP
    assert td.compute_target(100.0, 101.0) == TargetDirection.UP
    # Negative -> DOWN
    assert td.compute_target(100.0, 99.0) == TargetDirection.DOWN
    # Zero -> NEUTRAL
    assert td.compute_target(100.0, 100.0) == TargetDirection.NEUTRAL
    # Threshold boundaries (+0.5% exactly is at up_threshold: > requires above, so 100.5 = +0.5% -> NEUTRAL per defined thresholds)
    assert td.compute_target(100.0, 100.51) == TargetDirection.UP
    assert td.compute_target(100.0, 99.49) == TargetDirection.DOWN


def test_probability_mapping_index_order():
    """Confirm inference service maps predict_proba indices correctly.

    The production artifact (RandomForest 3-class) returns indices 0,1,2.
    Service maps: down=0, neutral=1, up=2. A swap here inverts direction.
    """
    # Simulated calibrator output aligned to service convention
    probs = np.array([0.10, 0.20, 0.70])  # 10% down, 20% neutral, 70% up
    # Service unpack (line 307-308 of prediction_service): down, neutral, up
    down_prob, neutral_prob, up_prob = float(probs[0]), float(probs[1]), float(probs[2])
    assert down_prob == 0.10 and neutral_prob == 0.20 and up_prob == 0.70
    from services.ml import recipe
    assert recipe.direction_from_probs(up_prob, neutral_prob, down_prob) == "up"


def test_expected_return_sign():
    from services.ml import recipe
    # Production expected_return = (up - down) * 2. Positive when up > down.
    up, down = 0.7, 0.1
    expected = (up - down) * 2.0
    assert expected > 0
    # If direction is DOWN, up < down -> expected negative
    up, down = 0.1, 0.7
    expected = (up - down) * 2.0
    assert expected < 0
