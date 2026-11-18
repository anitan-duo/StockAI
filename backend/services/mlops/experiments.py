"""Durable experiment registry: hypotheses, transitions, decisions.

Every autonomous research action is a row: reproducible (dataset fingerprint,
code revision, seed, splits, artifact hash) and auditable (status history via
updated timestamps, decision + reason frozen on close). Burned holdouts are
refused for selection here, not just in offline scripts.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

# research -> training -> evaluating -> candidate -> shadow -> approved
# (direct candidate -> approved is permitted when the evidence already
# justifies it, e.g. frozen one-shot evaluations; shadow remains recommended
# for live-serve comparison before approval).
VALID_TRANSITIONS: dict[str, set[str]] = {
    "research": {"training", "rejected", "failed"},
    "training": {"evaluating", "failed"},
    "evaluating": {"candidate", "rejected", "failed"},
    "candidate": {"shadow", "approved", "rejected", "failed"},
    "shadow": {"approved", "rejected", "failed", "retired"},
    "approved": {"retired"},
    "rejected": set(),
    "failed": {"research"},
    "retired": set(),
}

TERMINAL = {"rejected", "failed", "retired", "approved"}


class ExperimentError(Exception):
    """Invalid experiment operation."""


async def register_experiment(
    session,
    *,
    experiment_id: str,
    hypothesis: str,
    dataset_fingerprint: str = "",
    feature_set: str = "full",
    target: str = "v1-h1d-0.5pct",
    horizon: str = "1d",
    model_family: str = "",
    hyperparameters: dict | None = None,
    seed: int | None = 42,
    splits: dict | None = None,
    code_revision: str | None = None,
) -> object:
    """Create a research-stage experiment (idempotent by experiment_id)."""
    from apps.api.models.mlops import Experiment

    existing = (
        await session.execute(
            select(Experiment).where(Experiment.experiment_id == experiment_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    exp = Experiment(
        experiment_id=experiment_id,
        hypothesis=hypothesis,
        status="research",
        dataset_fingerprint=dataset_fingerprint,
        feature_set=feature_set,
        target=target,
        horizon=horizon,
        model_family=model_family,
        hyperparameters=hyperparameters or {},
        seed=seed,
        splits=splits or {},
        code_revision=code_revision or _code_revision(),
    )
    session.add(exp)
    await session.flush()
    return exp


async def transition(session, experiment, to_status: str, *, reason: str = "") -> object:
    """Move an experiment along the lifecycle (guarded, transactional)."""
    allowed = VALID_TRANSITIONS.get(experiment.status, set())
    if to_status not in allowed:
        raise ExperimentError(
            f"Illegal transition {experiment.status} -> {to_status} "
            f"for {experiment.experiment_id}"
        )
    experiment.status = to_status
    if to_status in ("rejected", "failed", "approved", "retired"):
        experiment.decision = to_status
        experiment.decision_reason = reason
    await session.flush()
    return experiment


async def record_metrics(
    session, experiment, *, metrics: dict | None = None, backtest: dict | None = None,
    artifact_path: str | None = None, artifact_sha: str | None = None,
    compute_seconds: float = 0.0,
) -> object:
    """Attach evaluation evidence (never overwrites a closed decision)."""
    if experiment.status in ("approved", "rejected", "retired"):
        raise ExperimentError(f"Experiment {experiment.experiment_id} is closed ({experiment.status})")
    if metrics is not None:
        experiment.metrics = metrics
    if backtest is not None:
        experiment.backtest = backtest
    if artifact_path is not None:
        experiment.artifact_path = artifact_path
    if artifact_sha is not None:
        experiment.artifact_sha = artifact_sha
    experiment.compute_seconds = float(experiment.compute_seconds or 0.0) + compute_seconds
    await session.flush()
    return experiment


def assert_selection_range_allowed(start, end, purpose: str) -> None:
    """Refuse burned holdouts for any selection use (raises on overlap)."""
    from research.burned import assert_not_burned

    assert_not_burned(start, end, purpose)


def _code_revision() -> str:
    try:
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
