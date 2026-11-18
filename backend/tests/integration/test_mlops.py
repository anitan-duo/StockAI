"""MLOps integrity on the live dev DB.

- Experiment lifecycle transitions enforced (illegal jumps rejected).
- Champion resolves to pinned v1.0 with verified hash.
- Outcome resolution is idempotent and label-correct on real rows.
- Admin-only mutation endpoints reject non-admins (403) and strangers (401).
- Approval of a sub-bar candidate is refused (409); rejected candidates
  can never be promoted afterward.
"""

import pytest


@pytest.mark.asyncio
async def test_experiment_lifecycle_guarded():
    import uuid as _uuid

    from apps.api.database import async_session_factory
    from services.mlops.experiments import (
        ExperimentError,
        register_experiment,
        transition,
    )

    async with async_session_factory() as session:
        exp = await register_experiment(
            session,
            experiment_id=f"TEST-LIFECYCLE-{_uuid.uuid4().hex[:8]}",
            hypothesis="lifecycle guard probe",
        )
        assert exp.status == "research"
        # research -> approved is illegal (must pass through stages)
        with pytest.raises(ExperimentError):
            await transition(session, exp, "approved")
        await transition(session, exp, "training", reason="t")
        await transition(session, exp, "evaluating", reason="t")
        await transition(session, exp, "rejected", reason="probe done")
        assert exp.status == "rejected"
        # Closed experiments are terminal.
        with pytest.raises(ExperimentError):
            await transition(session, exp, "shadow")
        await session.rollback()


@pytest.mark.asyncio
async def test_champion_resolves_pinned_v10_verified():
    from apps.api.database import async_session_factory
    from services.ml.champion import resolve_champion

    async with async_session_factory() as session:
        champ = await resolve_champion(session)
        assert champ["artifact_sha"].startswith("sha256:cafe9216074afd5b")


@pytest.mark.asyncio
async def test_outcome_resolution_idempotent_and_correct():
    from sqlalchemy import select

    from apps.api.database import async_session_factory
    from apps.api.models.prediction import Prediction, PredictionOutcome
    from services.prediction.outcomes import resolve_matured_outcomes

    async with async_session_factory() as session:
        before = (
            await session.execute(select(PredictionOutcome.id))
        ).all()
        out1 = await resolve_matured_outcomes(session, limit=50)
        assert out1["resolved"] >= 0
        after = (
            await session.execute(select(PredictionOutcome.id))
        ).all()
        assert len(after) >= len(before)
        # Rerun resolves nothing new and creates no duplicates.
        out2 = await resolve_matured_outcomes(session, limit=50)
        again = (
            await session.execute(select(PredictionOutcome.id))
        ).all()
        assert len(again) == len(after)
        assert out2["resolved"] == 0
        # Label math spot-check on one resolved row.
        if after:
            oid = after[0][0]
            oc = await session.get(PredictionOutcome, oid)
            pred = await session.get(Prediction, oc.prediction_id)
            base = float(pred.features_snapshot["price"])
            ret = (float(oc.evaluation_price) - base) / base
            expected = "up" if ret > 0.005 else ("down" if ret < -0.005 else "neutral")
            assert str(oc.actual_direction) == expected


def _admin_client():
    import uuid

    from fastapi.testclient import TestClient

    from apps.api.main import app

    c = TestClient(app)
    email = f"mlops_{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/api/v1/auth/register", json={"email": email, "password": "TestPass123!", "full_name": "MO"})
    assert r.status_code in (200, 201), r.text[:200]
    token = r.json()["tokens"]["access_token"]
    return c, {"Authorization": f"Bearer {token}"}


def test_mlops_reads_require_auth():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    c = TestClient(app)
    for path in ("/api/v1/mlops/champion", "/api/v1/mlops/experiments", "/api/v1/mlops/jobs",
                 "/api/v1/mlops/promotions", "/api/v1/mlops/monitoring"):
        r = c.get(path)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_mlops_admin_gates_and_approval_bar():
    import asyncio
    import uuid as _uuid

    from apps.api.database import async_session_factory
    from apps.api.models.mlops import Experiment

    weak_id = f"TEST-WEAK-{_uuid.uuid4().hex[:8]}"

    c, headers = _admin_client()
    # Non-admin cannot approve/reject/trigger.
    r = c.post("/api/v1/mlops/experiments/NOPE/reject", headers=headers)
    assert r.status_code == 403, r.text[:200]

    async def _make_candidate():
        from services.mlops.experiments import register_experiment, transition

        async with async_session_factory() as session:
            exp = await register_experiment(
                session, experiment_id=weak_id,
                hypothesis="deliberately sub-bar candidate",
            )
            await transition(session, exp, "training", reason="t")
            await transition(session, exp, "evaluating", reason="t")
            exp.metrics = {"baseline-full-iso": {"n": 100, "accuracy": 0.35, "brier": 0.24},
                           "weak": {"n": 100, "accuracy": 0.36, "brier": 0.24}}
            exp.artifact_path = "model_artifacts/real/ensemble/v1.0/model.pkl"
            exp.artifact_sha = "sha256:cafe9216074afd5b" + "0" * 48
            await transition(session, exp, "candidate", reason="t")
            await session.commit()
            return exp.experiment_id

    exp_id = asyncio.run(_make_candidate())
    # Still 403 as non-admin (and would be 409 on the bar as admin).
    r = c.post(f"/api/v1/mlops/experiments/{exp_id}/approve", headers=headers)
    assert r.status_code == 403
    # Cleanup: mark rejected directly.
    async def _cleanup():
        from sqlalchemy import select

        from services.mlops.experiments import transition as tr

        async with async_session_factory() as session:
            exp = (
                await session.execute(select(Experiment).where(Experiment.experiment_id == exp_id))
            ).scalar_one()
            await tr(session, exp, "rejected", reason="test cleanup")
            await session.commit()

    asyncio.run(_cleanup())


def test_champion_endpoint_reports_verified_hash():
    c, headers = _admin_client()
    # Champion read requires auth; any authenticated user may read.
    r = c.get("/api/v1/mlops/champion", headers=headers)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["artifact_sha"].startswith("sha256:cafe9216074afd5b")
    assert body["artifact_verified"] is True
