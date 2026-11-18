"""Historical scenario lab: blind challenges with server-enforced blindness.

Blindness guarantees (all server-side, never trusted to the client):
- bars endpoint returns ONLY bars with timestamp <= data_cutoff;
- predictions commit before any outcome exists for the attempt;
- reveal reads strictly-later bars and freezes the row (idempotent);
- repeats never extend streaks; final-split rows can never train.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.models.scenarios import ChallengeAttempt, ErrorDiagnosis, Scenario, Streak
from apps.api.routes.auth import get_current_user
from services.ml.tasks import HORIZON_TO_TASK, TASKS
from services.mlops.scenarios import (
    ScenarioError,
    create_scenario,
    get_scenario_bars,
    reveal_attempt,
    submit_prediction,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _scenario_to_dict(s: Scenario) -> dict:
    return {
        "id": str(s.id),
        "scenario_key": s.scenario_key,
        "instrument_id": str(s.instrument_id),
        "decision_ts": s.decision_ts.isoformat() if s.decision_ts else None,
        "horizon": s.horizon,
        "target_version": s.target_version,
        "data_cutoff": s.data_cutoff.isoformat() if s.data_cutoff else None,
        "feature_schema_version": s.feature_schema_version,
        "split": s.split,
        "seen_by_model": s.seen_by_model,
        "used_for_training": s.used_for_training,
        "outcome_status": s.outcome_status,
        "unavailable_reason": s.unavailable_reason,
        "snapshot_hash": s.snapshot_hash,
    }


def _attempt_to_dict(a: ChallengeAttempt, *, reveal: bool = False) -> dict:
    d = {
        "id": str(a.id),
        "scenario_id": str(a.scenario_id),
        "experiment_id": a.experiment_id,
        "model_version": a.model_version,
        "artifact_sha": a.artifact_sha,
        "horizon": a.horizon,
        "pred_up": a.pred_up,
        "pred_neutral": a.pred_neutral,
        "pred_down": a.pred_down,
        "action": a.action,
        "committed_at": a.committed_at.isoformat() if a.committed_at else None,
        "is_repeat": a.is_repeat,
    }
    # Outcome fields leave this object ONLY after reveal.
    if reveal and a.revealed_at is not None:
        d.update(
            {
                "revealed_at": a.revealed_at.isoformat(),
                "actual_return_pct": a.actual_return_pct,
                "actual_direction": a.actual_direction,
                "correct": a.correct,
            }
        )
    else:
        d.update(
            {
                "revealed_at": a.revealed_at.isoformat() if a.revealed_at else None,
                "actual_return_pct": None,
                "actual_direction": None,
                "correct": a.correct,
            }
        )
    return d


@router.get("/tasks")
async def list_tasks(
    user: dict = Depends(get_current_user),
) -> dict:
    """The three forecast tasks with frozen definitions."""
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "horizon": t.task_id,
                "horizon_sessions": t.horizon_sessions,
                "up_threshold": t.up_threshold,
                "down_threshold": t.down_threshold,
                "target_version": t.target_version,
                "cost_band_pct": t.cost_band_pct,
                "production": t.production,
            }
            for t in TASKS.values()
        ],
        "horizons": HORIZON_TO_TASK,
    }


@router.post("")
async def create_scenario_route(
    symbol: str = Query(...),
    exchange: str = Query(...),
    decision_date: str = Query(...),
    task_id: str = Query(default="h1d"),
    split: str = Query(default="train"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create (or fetch existing) scenario for a date+symbol+horizon."""
    try:
        scen = await create_scenario(
            session, symbol=symbol, exchange=exchange,
            decision_date=decision_date, task_id=task_id, split=split,
        )
        await session.commit()
    except ScenarioError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _scenario_to_dict(scen)


@router.get("")
async def list_scenarios(
    split: str | None = Query(default=None),
    horizon: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """List scenarios (metadata only — outcomes resolve per attempt)."""
    q = select(Scenario).order_by(desc(Scenario.decision_ts)).limit(limit)
    if split:
        q = q.where(Scenario.split == split)
    if horizon:
        q = q.where(Scenario.horizon == horizon)
    rows = (await session.execute(q)).scalars().all()
    return {"scenarios": [_scenario_to_dict(s) for s in rows]}


@router.get("/{scenario_id}/bars")
async def scenario_bars(
    scenario_id: UUID,
    limit: int = Query(default=400, ge=1, le=1000),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Decision-time bars ONLY (timestamp <= data_cutoff). The blindness wall."""
    scen = await session.get(Scenario, scenario_id)
    if scen is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    bars = await get_scenario_bars(session, scen, limit=limit)
    return {
        "scenario_id": str(scen.id),
        "data_cutoff": scen.data_cutoff.isoformat(),
        "bars": [
            {
                "timestamp": b.timestamp.isoformat(),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": int(b.volume or 0),
            }
            for b in bars
        ],
    }


@router.post("/{scenario_id}/submit")
async def submit_challenge(
    scenario_id: UUID,
    experiment_id: str = Query(...),
    up: float = Query(...),
    neutral: float = Query(...),
    down: float = Query(...),
    action: str = Query(...),
    model_version: str = Query(default="ensemble-v1.0"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Commit a blind forecast (frozen at commit time)."""
    try:
        attempt = await submit_prediction(
            session, scenario_id=scenario_id, experiment_id=experiment_id,
            up=up, neutral=neutral, down=down, action=action,
            model_version=model_version,
        )
        await session.commit()
    except ScenarioError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _attempt_to_dict(attempt)


@router.post("/attempts/{attempt_id}/reveal")
async def reveal_challenge(
    attempt_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reveal the outcome from genuine subsequent bars (idempotent)."""
    try:
        attempt = await reveal_attempt(session, attempt_id)
        await session.commit()
    except ScenarioError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _attempt_to_dict(attempt, reveal=True)


@router.get("/attempts")
async def list_attempts(
    experiment_id: str | None = Query(default=None),
    revealed: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Challenge history (unrevealed attempts expose no outcome fields)."""
    q = select(ChallengeAttempt).order_by(desc(ChallengeAttempt.committed_at)).limit(limit)
    if experiment_id:
        q = q.where(ChallengeAttempt.experiment_id == experiment_id)
    if revealed is True:
        q = q.where(ChallengeAttempt.revealed_at.is_not(None))
    elif revealed is False:
        q = q.where(ChallengeAttempt.revealed_at.is_(None))
    rows = (await session.execute(q)).scalars().all()
    return {"attempts": [_attempt_to_dict(a, reveal=a.revealed_at is not None) for a in rows]}


@router.get("/streaks")
async def list_streaks(
    experiment_id: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """10/10 streak state per (experiment, horizon)."""
    q = select(Streak).order_by(desc(Streak.updated_at)).limit(100)
    if experiment_id:
        q = q.where(Streak.experiment_id == experiment_id)
    rows = (await session.execute(q)).scalars().all()
    return {
        "streaks": [
            {
                "streak_key": s.streak_key,
                "experiment_id": s.experiment_id,
                "horizon": s.horizon,
                "correctness_rule": s.correctness_rule,
                "current": s.current,
                "longest": s.longest,
                "attempts": s.attempts,
                "unique_scenarios": s.unique_scenarios,
                "correct_count": s.correct_count,
                "incorrect_count": s.incorrect_count,
                "completed_10_of_10": s.completed_10_of_10,
            }
            for s in rows
        ]
    }


@router.get("/attempts/{attempt_id}/diagnosis")
async def get_diagnosis(
    attempt_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Structured error diagnosis for a revealed miss."""
    diag = (
        await session.execute(
            select(ErrorDiagnosis).where(ErrorDiagnosis.attempt_id == attempt_id)
        )
    ).scalar_one_or_none()
    if diag is None:
        raise HTTPException(status_code=404, detail="No diagnosis for this attempt")
    return {
        "id": str(diag.id),
        "attempt_id": str(diag.attempt_id),
        "category": diag.category,
        "evidence": diag.evidence,
        "alternatives": diag.alternatives,
        "confidence": diag.confidence,
        "intervention": diag.intervention,
        "success_metric": diag.success_metric,
        "result": diag.result,
    }


@router.post("/attempts/{attempt_id}/diagnose")
async def submit_diagnosis(
    attempt_id: UUID,
    category: str = Query(...),
    evidence: str = Query(default="{}"),
    confidence: str = Query(default="low"),
    intervention: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Operator hypothesis (supersedes the auto-suggestion with audit trail:
    the auto row is updated in place and keeps its origin in evidence)."""
    import json as _json

    attempt = await session.get(ChallengeAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.revealed_at is None:
        raise HTTPException(status_code=409, detail="Attempt not yet revealed")
    try:
        ev = _json.loads(evidence) if isinstance(evidence, str) else dict(evidence)
    except Exception:
        raise HTTPException(status_code=422, detail="evidence must be JSON")
    diag = (
        await session.execute(
            select(ErrorDiagnosis).where(ErrorDiagnosis.attempt_id == attempt_id)
        )
    ).scalar_one_or_none()
    if diag is None:
        diag = ErrorDiagnosis(attempt_id=attempt.id, category=category)
        session.add(diag)
    else:
        ev.setdefault("auto_category", diag.category)
        ev.setdefault("auto_evidence", diag.evidence)
    diag.category = category
    diag.evidence = ev
    diag.confidence = confidence
    diag.intervention = intervention
    await session.commit()
    return {"status": "recorded", "attempt_id": str(attempt_id), "category": category}


@router.post("/{scenario_id}/mark-training-use")
async def mark_training_use(
    scenario_id: UUID,
    used: bool = Query(default=True),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Flag training use (final-split rows refuse — 409)."""

    try:
        await mark_training_use(session, scenario_id, used=used)
        await session.commit()
    except ScenarioError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"status": "recorded", "scenario_id": str(scenario_id), "used_for_training": used}
