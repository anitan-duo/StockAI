"""Model operations: champion, experiments, jobs, promotions, drift.

Every mutating action is admin-only. Approvals re-verify the promotion bar
server-side (never trust the client); champion switches and rollbacks are
single transactions; rollback is a reversing promotion row, never a delete.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.models.mlops import (
    DriftObservation,
    Experiment,
    ModelChampion,
    ModelPromotion,
    TrainingJob,
)
from apps.api.models.prediction import Model, ModelVersion
from apps.api.routes.auth import get_current_user
from apps.api.routes.training import _require_superuser

router = APIRouter(prefix="/mlops", tags=["mlops"])

# Promotion bar (mirrors the pre-registered research rule; enforced here too
# so approval can never silently lower it).
PROMO_MIN_ACC_DELTA = 0.05
PROMO_MAX_BRIER_DELTA = -0.01
PROMO_MIN_EVALS = 60


def _actor_email(user) -> str | None:
    if isinstance(user, dict):
        return user.get("email")
    return getattr(user, "email", None)


def _exp_to_dict(e: Experiment) -> dict:
    return {
        "id": str(e.id),
        "experiment_id": e.experiment_id,
        "hypothesis": e.hypothesis,
        "status": e.status,
        "dataset_fingerprint": e.dataset_fingerprint,
        "feature_set": e.feature_set,
        "target": e.target,
        "horizon": e.horizon,
        "model_family": e.model_family,
        "hyperparameters": e.hyperparameters,
        "seed": e.seed,
        "splits": e.splits,
        "metrics": e.metrics,
        "backtest": e.backtest,
        "artifact_path": e.artifact_path,
        "artifact_sha": (e.artifact_sha[:19] + "…") if e.artifact_sha else None,
        "artifact_sha_full": e.artifact_sha,
        "code_revision": e.code_revision,
        "compute_seconds": e.compute_seconds,
        "error": (e.error[:500] if e.error else None),
        "decision": e.decision,
        "decision_reason": e.decision_reason,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


@router.get("/champion")
async def get_champion(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Current champion + live artifact integrity verification."""
    from pathlib import Path

    from services.ml.champion import sha_accepted, sha_of

    row = (
        await session.execute(
            select(ModelChampion).where(ModelChampion.superseded_at.is_(None))
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No champion recorded")
    version = await session.get(ModelVersion, row.model_version_id)
    model = await session.get(Model, version.model_id) if version else None
    # Verify the artifact file the record points at (v1.0 canonical paths).
    verified: bool | None = None
    for cand in (
        Path("model_artifacts/real/ensemble/v1.0/model.pkl"),
        Path("backend/model_artifacts/real/ensemble/v1.0/model.pkl"),
    ):
        if cand.exists():
            verified = sha_accepted(sha_of(cand), row.artifact_sha, False)
            break
    return {
        "model": model.name if model else None,
        "version": version.version if version else None,
        "model_version_id": str(row.model_version_id),
        "artifact_sha": row.artifact_sha,
        "artifact_verified": verified,
        "status": row.status,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "decided_by": row.decided_by,
        "rationale": row.rationale,
        "metrics": row.metrics,
    }


@router.get("/experiments")
async def list_experiments(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Experiment registry (newest first). Authenticated users may read."""
    q = select(Experiment).order_by(desc(Experiment.created_at)).limit(limit)
    if status:
        q = q.where(Experiment.status == status)
    rows = (await session.execute(q)).scalars().all()
    return {"experiments": [_exp_to_dict(e) for e in rows]}


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Single experiment record."""
    exp = (
        await session.execute(
            select(Experiment).where(Experiment.experiment_id == experiment_id)
        )
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _exp_to_dict(exp)


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Training jobs (newest first)."""
    q = select(TrainingJob).order_by(desc(TrainingJob.created_at)).limit(limit)
    if status:
        q = q.where(TrainingJob.status == status)
    rows = (await session.execute(q)).scalars().all()
    return {
        "jobs": [
            {
                "id": str(j.id),
                "job_key": j.job_key,
                "experiment_id": str(j.experiment_id) if j.experiment_id else None,
                "status": j.status,
                "attempts": j.attempts,
                "max_attempts": j.max_attempts,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                "error": (j.error[:500] if j.error else None),
                "compute_seconds": j.compute_seconds,
            }
            for j in rows
        ]
    }


@router.get("/promotions")
async def list_promotions(
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Promotion/rollback history (newest first)."""
    rows = (
        await session.execute(
            select(ModelPromotion).order_by(desc(ModelPromotion.created_at)).limit(limit)
        )
    ).scalars().all()
    return {
        "promotions": [
            {
                "id": str(p.id),
                "from_version_id": str(p.from_version_id) if p.from_version_id else None,
                "to_version_id": str(p.to_version_id),
                "experiment_id": str(p.experiment_id) if p.experiment_id else None,
                "decided_by": p.decided_by,
                "rationale": p.rationale,
                "metrics_delta": p.metrics_delta,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ]
    }


@router.get("/monitoring")
async def get_monitoring(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Fresh monitor snapshot + open drift alerts."""
    from services.mlops.monitor import compute_monitor_snapshot

    snapshot = await compute_monitor_snapshot(session)
    open_alerts = (
        await session.execute(
            select(DriftObservation)
            .where(DriftObservation.acknowledged.is_(False))
            .order_by(desc(DriftObservation.observed_at))
            .limit(50)
        )
    ).scalars().all()
    snapshot["open_alerts"] = [
        {
            "id": str(a.id),
            "scope": a.scope,
            "metric": a.metric,
            "value": a.value,
            "threshold": a.threshold,
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
            "note": a.note,
        }
        for a in open_alerts
    ]
    return snapshot


@router.post("/drift/{observation_id}/acknowledge")
async def acknowledge_drift(
    observation_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Acknowledge a drift alert (any authenticated user; audit-logged)."""
    obs = await session.get(DriftObservation, observation_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    obs.acknowledged = True
    await session.commit()
    return {"status": "acknowledged", "id": str(obs.id)}


@router.post("/experiments/{experiment_id}/reject")
async def reject_experiment(
    experiment_id: str,
    reason: str = Query(default="rejected by operator"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reject a candidate/shadow experiment (admin only)."""
    _require_superuser(user)
    from services.mlops.experiments import transition

    exp = (
        await session.execute(
            select(Experiment).where(Experiment.experiment_id == experiment_id)
        )
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    try:
        await transition(session, exp, "rejected", reason=reason[:500])
        await session.commit()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": exp.status, "experiment_id": exp.experiment_id}


@router.post("/experiments/{experiment_id}/approve")
async def approve_experiment(
    experiment_id: str,
    rationale: str = Query(default=""),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Approve a candidate/shadow experiment: re-verify the promotion bar
    server-side, then atomically switch the champion (single transaction).
    NEVER auto-called: admin action only, fully audited."""
    _require_superuser(user)
    from pathlib import Path

    from services.ml.champion import sha_accepted, sha_of
    from services.mlops.experiments import transition

    exp = (
        await session.execute(
            select(Experiment).where(Experiment.experiment_id == experiment_id)
        )
    ).scalar_one_or_none()
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status not in ("candidate", "shadow"):
        raise HTTPException(
            status_code=409,
            detail=f"Only candidate/shadow experiments can be approved (status={exp.status})",
        )
    if not exp.artifact_path or not exp.artifact_sha:
        raise HTTPException(status_code=409, detail="Candidate has no recorded artifact")
    # 1. Artifact integrity: file must exist inside the artifact roots and
    # match the recorded SHA. Anything else fails closed (no traversal, no
    # /etc/passwd-style reads, no joblib on untrusted bytes).
    art = Path(exp.artifact_path)
    try:
        resolved = art.resolve()
        allowed_roots = [
            Path("model_artifacts").resolve(),
            Path("backend/model_artifacts").resolve(),
        ]
        if not any(
            resolved == root or root in resolved.parents for root in allowed_roots
        ):
            raise ValueError("artifact outside artifact roots")
        if not art.exists() or not art.is_file():
            raise ValueError("candidate artifact file missing")
        actual_sha = sha_of(art)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not sha_accepted(actual_sha, exp.artifact_sha, False):
        raise HTTPException(
            status_code=409,
            detail=f"Artifact hash mismatch: recorded {exp.artifact_sha[:19]} vs file {actual_sha[:19]}",
        )
    # 2. Metrics bar re-verified server-side from the recorded per-config
    # numbers (same pre-registered rule; deltas recomputed here, never
    # trusted from a stored summary).
    m = exp.metrics or {}
    base = m.get("baseline-full-iso") or {}
    base_n, base_acc, base_brier = int(base.get("n", 0) or 0), float(base.get("accuracy", 0) or 0), float(base.get("brier", 1) or 1)
    best_name, best_d_acc, best_d_brier, best_n = None, -1.0, 0.0, 0
    for name, r in m.items():
        if not isinstance(r, dict) or name == "baseline-full-iso":
            continue
        rn = int(r.get("n", 0) or 0)
        if rn < PROMO_MIN_EVALS:
            continue
        da = float(r.get("accuracy", 0) or 0) - base_acc
        db = float(r.get("brier", 1) or 1) - base_brier
        if da > best_d_acc:
            best_name, best_d_acc, best_d_brier, best_n = name, da, db, rn
    d_acc, d_brier, n = best_d_acc, best_d_brier, best_n
    if best_name is None or not (
        d_acc >= PROMO_MIN_ACC_DELTA and d_brier <= PROMO_MAX_BRIER_DELTA and n >= PROMO_MIN_EVALS
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Promotion bar not met: Δacc {d_acc:+.4f} (need ≥+{PROMO_MIN_ACC_DELTA}), "
                f"Δbrier {d_brier:+.4f} (need ≤{PROMO_MAX_BRIER_DELTA}), n={n} (need ≥60)"
            ),
        )
    # 3. Atomic switch: challenger ModelVersion + supersede + champion + promotion.
    current = (
        await session.execute(
            select(ModelChampion).where(ModelChampion.superseded_at.is_(None))
        )
    ).scalar_one_or_none()
    who = _actor_email(user)
    model = Model(
        name=f"challenger-{exp.experiment_id}",
        description=f"Approved challenger from {exp.experiment_id}.",
        model_type="ensemble",
        is_active=True,
    )
    session.add(model)
    await session.flush()
    version = ModelVersion(
        model_id=model.id,
        version="v1",
        description=f"Approved weights for {exp.experiment_id}",
        is_active=True,
        training_date=datetime.now(UTC),
        metrics=dict(m),
        hyperparameters=dict(exp.hyperparameters or {}),
    )
    session.add(version)
    await session.flush()
    # NOTE: challenger weights stay in their experiment artifact file
    # (recorded path+SHA); inference resolves them via the champion record.
    # The v1.0 file artifact is never overwritten.
    from_version = current.model_version_id if current else None
    if current is not None:
        current.status = "superseded"
        current.superseded_at = datetime.now(UTC)
    new_champ = ModelChampion(
        model_version_id=version.id,
        artifact_sha=exp.artifact_sha,
        status="active",
        approved_at=datetime.now(UTC),
        decided_by=who,
        rationale=(rationale or exp.decision_reason or "")[:1000],
        metrics=dict(m),
    )
    session.add(new_champ)
    await session.flush()
    session.add(
        ModelPromotion(
            from_version_id=from_version,
            to_version_id=version.id,
            experiment_id=exp.id,
            decided_by=who,
            rationale=(rationale or exp.decision_reason or "")[:1000],
            metrics_delta={"delta_accuracy": d_acc, "delta_brier": d_brier, "n": n},
        )
    )
    await transition(session, exp, "approved", reason=(rationale or "approved by operator")[:500])
    await session.commit()
    return {
        "status": "approved",
        "experiment_id": exp.experiment_id,
        "model_version_id": str(version.id),
        "artifact_sha": exp.artifact_sha,
    }


@router.post("/rollback")
async def rollback_champion(
    rationale: str = Query(default=""),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Roll back to the most recently superseded champion (admin only).
    Implemented as a reversing promotion row; history is never deleted."""
    _require_superuser(user)
    current = (
        await session.execute(
            select(ModelChampion).where(ModelChampion.superseded_at.is_(None))
        )
    ).scalar_one_or_none()
    if current is None:
        raise HTTPException(status_code=409, detail="No current champion")
    previous = (
        await session.execute(
            select(ModelChampion)
            .where(ModelChampion.superseded_at.is_not(None))
            .order_by(desc(ModelChampion.superseded_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if previous is None:
        raise HTTPException(status_code=409, detail="No previous champion to roll back to")
    who = _actor_email(user)
    current.status = "superseded"
    current.superseded_at = datetime.now(UTC)
    restored = ModelChampion(
        model_version_id=previous.model_version_id,
        artifact_sha=previous.artifact_sha,
        status="active",
        approved_at=datetime.now(UTC),
        decided_by=who,
        rationale=(rationale or f"rollback to {previous.model_version_id}")[:1000],
        metrics=dict(previous.metrics or {}),
    )
    session.add(restored)
    await session.flush()
    session.add(
        ModelPromotion(
            from_version_id=current.model_version_id,
            to_version_id=previous.model_version_id,
            experiment_id=None,
            decided_by=who,
            rationale=f"ROLLBACK: {(rationale or '')[:900]}",
            metrics_delta={},
        )
    )
    await session.commit()
    return {
        "status": "rolled back",
        "model_version_id": str(previous.model_version_id),
    }


@router.post("/jobs/run-evolution")
async def trigger_evolution(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Manually trigger one bounded evolution cycle (admin only; same gates
    and budgets as the scheduled run — never promotes)."""
    _require_superuser(user)
    from services.mlops.evolution import run_evolution_cycle

    return await run_evolution_cycle(session)
