import pytest
import math
from services.ml.recipe import normalize_probs

def test_normalize_probs_finite():
    assert normalize_probs(0.2, 0.2, 0.6) == (0.2, 0.2, 0.6)

def test_normalize_probs_nan_raises():
    with pytest.raises(ValueError, match="Non-finite probability input"):
        normalize_probs(math.nan, 0.2, 0.6)

def test_normalize_probs_inf_raises():
    with pytest.raises(ValueError, match="Non-finite probability input"):
        normalize_probs(math.inf, 0.2, 0.6)

def test_normalize_probs_sum_zero_raises():
    with pytest.raises(ValueError, match="Non-positive probability mass"):
        normalize_probs(0.0, 0.0, 0.0)
