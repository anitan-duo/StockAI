"""Experiment lifecycle: the full happy path must be traversable.

Regression: evolution.py once contained a dead `evaluating -> evaluating`
self-transition that failed every autonomous cycle at runtime (caught only
by a live run, not by stage-by-stage unit tests). This test walks the exact
sequence the cycle uses, so a duplicated/invalid transition breaks here.
"""

from types import SimpleNamespace

import pytest


class _FakeSession:
    async def flush(self):
        return None


def _exp(status="research"):
    return SimpleNamespace(status=status, decision=None, decision_reason=None,
                           experiment_id="TEST-PATH-001")


@pytest.mark.asyncio
async def test_full_promotion_path_traversable():
    from services.mlops.experiments import transition

    s, exp = _FakeSession(), _exp("research")
    for nxt in ("training", "evaluating", "candidate", "shadow", "approved", "retired"):
        await transition(s, exp, nxt, reason="t")
    assert exp.status == "retired"
    assert exp.decision == "retired"


@pytest.mark.asyncio
async def test_rejection_paths():
    from services.mlops.experiments import ExperimentError, transition

    s = _FakeSession()
    for start, nxt in (("research", "rejected"), ("evaluating", "rejected"),
                       ("candidate", "rejected"), ("shadow", "retired")):
        exp = _exp(start)
        await transition(s, exp, nxt, reason="t")
        assert exp.status == nxt
    # Terminal states are terminal.
    with pytest.raises(ExperimentError):
        await transition(s, _exp("rejected"), "shadow")
    with pytest.raises(ExperimentError):
        await transition(s, _exp("approved"), "shadow")
    # Failed work can restart research.
    exp = _exp("failed")
    await transition(s, exp, "research", reason="retry")
    assert exp.status == "research"
