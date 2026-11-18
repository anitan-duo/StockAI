"""Forecast-task definitions: frozen thresholds, honest action judging."""

import pytest

from services.ml.tasks import HORIZON_TO_TASK, TASKS, get_task, judge_action, label_return


def test_three_tasks_frozen():
    assert set(TASKS) == {"h1d", "h5d", "h20d"}
    assert (TASKS["h1d"].up_threshold, TASKS["h1d"].down_threshold) == (0.005, -0.005)
    assert (TASKS["h5d"].up_threshold, TASKS["h5d"].down_threshold) == (0.015, -0.015)
    assert (TASKS["h20d"].up_threshold, TASKS["h20d"].down_threshold) == (0.03, -0.03)
    assert TASKS["h1d"].production is True
    assert TASKS["h5d"].production is False
    assert TASKS["h20d"].production is False
    assert HORIZON_TO_TASK == {"1d": "h1d", "5d": "h5d", "20d": "h20d"}
    with pytest.raises(ValueError):
        get_task("h99")


def test_labels_strict_thresholds():
    t = get_task("h1d")
    assert label_return(t, 0.005) == "neutral"
    assert label_return(t, -0.005) == "neutral"
    assert label_return(t, 0.0051) == "up"
    assert label_return(t, -0.0051) == "down"


def test_hold_never_correct_by_default():
    t = get_task("h1d")
    assert judge_action(t, "HOLD", 0.0) is True
    assert judge_action(t, "HOLD", 0.001) is True
    assert judge_action(t, "HOLD", 0.002) is False
    assert judge_action(t, "BUY", 0.0) is False
    assert judge_action(t, "SELL", 0.0) is False
    assert judge_action(t, "BUY", 0.002) is True
    assert judge_action(t, "SELL", -0.002) is True
    with pytest.raises(ValueError):
        judge_action(t, "FROB", 0.0)
