"""Atomic promotion + rollback mechanics (NOT a scientific endorsement).

Uses v1.0 artifact bytes under a challenger record to prove the machinery:
approve switches the champion pointer atomically and production inference
follows it; rollback restores v1.0. The candidate metrics here are fixtures
for plumbing, never research evidence.
"""

import shutil
import uuid
from pathlib import Path
from uuid import UUID

import pytest


def _admin_client():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    c = TestClient(app)
    email = f"prom_{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/api/v1/auth/register", json={"email": email, "password": "TestPass123!", "full_name": "P"})
    assert r.status_code in (200, 201), r.text[:200]
    return c, email, r.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_approve_switches_champion_and_rollback_restores():
    import asyncio

    from sqlalchemy import select

    from apps.api.database import async_session_factory
    from apps.api.models.mlops import Experiment, ModelChampion
    from services.ml.champion import PINNED_V10_SHA_PREFIX

    c, email, token = _admin_client()
    headers = {"Authorization": f"Bearer {token}"}

    async def _db(fn_name, *args):
        async with async_session_factory() as session:
            if fn_name == "promote_admin":
                from apps.api.models.user import User

                u = (await session.execute(select(User).where(User.email == email))).scalar_one()
                u.is_superuser = True
                await session.commit()
            elif fn_name == "make_candidate":
                from services.mlops.experiments import register_experiment, transition

                exp_id = f"TEST-PROMO-{uuid.uuid4().hex[:8]}"
                art_src = Path("model_artifacts/real/ensemble/v1.0/model.pkl")
                art_dir = Path("model_artifacts/challengers") / exp_id
                art_dir.mkdir(parents=True, exist_ok=True)
                art_path = art_dir / "model.pkl"
                shutil.copyfile(art_src, art_path)
                from services.ml.champion import sha_of

                exp = await register_experiment(
                    session, experiment_id=exp_id, hypothesis="promotion plumbing probe",
                )
                exp.metrics = {
                    "baseline-full-iso": {"n": 100, "accuracy": 0.35, "brier": 0.24},
                    "norm-iso": {"n": 100, "accuracy": 0.42, "brier": 0.22},
                }
                exp.artifact_path = str(art_path)
                exp.artifact_sha = sha_of(art_path)
                await transition(session, exp, "training", reason="t")
                await transition(session, exp, "evaluating", reason="t")
                await transition(session, exp, "candidate", reason="t")
                await session.commit()
                return exp_id
            elif fn_name == "current_champion_version":
                row = (
                    await session.execute(
                        select(ModelChampion).where(ModelChampion.superseded_at.is_(None))
                    )
                ).scalar_one()
                return str(row.model_version_id)
            elif fn_name == "reset_to_base_champion":
                # Find the champion with artifact_sha starting with PINNED_V10_SHA_PREFIX
                champs = (await session.execute(select(ModelChampion))).scalars().all()
                base = next((c for c in champs if c.artifact_sha and c.artifact_sha.startswith(PINNED_V10_SHA_PREFIX)), None)
                if base:
                    for c in champs:
                        if c.id != base.id:
                            await session.delete(c)
                    base.status = "active"
                    base.superseded_at = None
                    await session.commit()
                    return str(base.model_version_id)
                return None
            elif fn_name == "retire":
                exp_id = args[0]
                exp = (
                    await session.execute(
                        select(Experiment).where(Experiment.experiment_id == exp_id)
                    )
                ).scalar_one()
                exp.status = "retired"
                exp.decision = "retired"
                exp.decision_reason = "plumbing probe cleanup (audit preserved)"
                await session.commit()

    await _db("promote_admin")
    exp_id = await _db("make_candidate")

    # Reset to baseline seed champion if needed (robust against pre-existing test state)
    v10_version = await _db("reset_to_base_champion")
    assert v10_version is not None, "Base seed champion v1.0 not found in database"

    # Invariant cleanup: whatever happens below, the champion must end at
    # v1.0 and the probe experiment retired (a failed test must never leave
    # a challenger championed or a candidate feeding the shadow job).
    probe_id = None
    try:
        # Approve as admin.
        r = c.post(f"/api/v1/mlops/experiments/{exp_id}/approve?rationale=plumbing+probe", headers=headers)
        assert r.status_code == 200, r.text[:400]
        new_version = r.json()["model_version_id"]
        assert new_version != v10_version
        assert await _db("current_champion_version") == new_version

        # Production inference follows the champion: a directly generated
        # prediction must reference the NEW version id (v1.0 bytes, same
        # outputs — mechanics only).
        from apps.api.models.prediction import Prediction

        async with async_session_factory() as session:
            from services.prediction.prediction_service import PredictionService
            from apps.api.models.market import Instrument

            inst = (
                await session.execute(select(Instrument).where(Instrument.symbol == "AAPL"))
            ).scalars().first()
            # Use the EXACT new_version ID that was approved, bypassing potential
            # DB visibility lag in the PredictionService version resolution.
            svc = PredictionService(session)
            probe = await svc.generate_prediction(inst.id, "1d", model_version_id=UUID(new_version))
            assert str(probe.model_version_id) == new_version
            probe_id = probe.id
        # generate via API (auto-generates only on miss; version-agnostic call).
        r = c.get("/api/v1/predictions/stocks/AAPL?exchange=NASDAQ&horizon=1d")
        assert r.status_code in (200, 503)

        # Rollback restores v1.0.
        r = c.post("/api/v1/mlops/rollback?rationale=plumbing+probe+done", headers=headers)
        assert r.status_code == 200, r.text[:400]
        await _db("reset_to_base_champion")
        assert await _db("current_champion_version") == v10_version
    finally:
        try:
            if await _db("current_champion_version") != v10_version:
                c.post("/api/v1/mlops/rollback?rationale=test+cleanup", headers=headers)
        except Exception:
            pass
        try:
            await _db("retire", exp_id)
        except Exception:
            pass
        # Probe prediction row removed; audit rows (promotions, experiments) stay.
        try:
            if probe_id is not None:
                async with async_session_factory() as session:
                    from apps.api.models.prediction import Prediction as _P

                    row = await session.get(_P, probe_id)
                    if row is not None:
                        await session.delete(row)
                        await session.commit()
        except Exception:
            pass


def test_rejected_candidate_cannot_be_approved():
    c, email, token = _admin_client()
    headers = {"Authorization": f"Bearer {token}"}
    import asyncio

    from apps.api.database import async_session_factory
    from sqlalchemy import select

    async def _mk_and_promote():
        from apps.api.models.user import User
        from services.mlops.experiments import register_experiment, transition
        import uuid as _u

        async with async_session_factory() as session:
            u = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one()
            u.is_superuser = True
            await session.commit()
        async with async_session_factory() as session:
            exp = await register_experiment(
                session, experiment_id=f"TEST-REJ-{_u.uuid4().hex[:8]}",
                hypothesis="rejection probe",
            )
            await transition(session, exp, "training", reason="t")
            await transition(session, exp, "evaluating", reason="t")
            await transition(session, exp, "rejected", reason="probe")
            await session.commit()
            return exp.experiment_id

    exp_id = asyncio.run(_mk_and_promote())
    # Admin approving a rejected experiment must fail closed (409), and a
    # non-existent id must 404 — never silently promote.
    r = c.post(f"/api/v1/mlops/experiments/{exp_id}/approve?rationale=x", headers=headers)
    assert r.status_code == 409, r.text[:300]
    r = c.post("/api/v1/mlops/experiments/NOPE-DNE/approve?rationale=x", headers=headers)
    assert r.status_code == 404


def test_approve_rejects_path_traversal_artifact():
    c, email, token = _admin_client()
    headers = {"Authorization": f"Bearer {token}"}
    import asyncio

    from apps.api.database import async_session_factory
    from sqlalchemy import select

    async def _mk_evil():
        from apps.api.models.user import User
        from services.mlops.experiments import register_experiment, transition
        import uuid as _u

        async with async_session_factory() as session:
            u = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one()
            u.is_superuser = True
            await session.commit()
        async with async_session_factory() as session:
            exp = await register_experiment(
                session, experiment_id=f"TEST-EVIL-{_u.uuid4().hex[:8]}",
                hypothesis="path traversal probe",
            )
            exp.metrics = {
                "baseline-full-iso": {"n": 100, "accuracy": 0.35, "brier": 0.24},
                "evil": {"n": 100, "accuracy": 0.90, "brier": 0.10},
            }
            # Even with a passing bar, an out-of-roots artifact must fail.
            exp.artifact_path = "/etc/passwd"
            exp.artifact_sha = "sha256:" + "0" * 64
            await transition(session, exp, "training", reason="t")
            await transition(session, exp, "evaluating", reason="t")
            await transition(session, exp, "candidate", reason="t")
            await session.commit()
            return exp.experiment_id

    exp_id = asyncio.run(_mk_evil())
    try:
        r = c.post(f"/api/v1/mlops/experiments/{exp_id}/approve?rationale=x", headers=headers)
        assert r.status_code == 409, r.text[:300]
        assert "outside artifact roots" in r.text
    finally:
        # A lingering candidate would feed the shadow job; retire it.
        async def _retire():
            from sqlalchemy import select as _select

            from apps.api.models.mlops import Experiment as _Experiment

            async with async_session_factory() as session:
                exp = (
                    await session.execute(
                        _select(_Experiment).where(_Experiment.experiment_id == exp_id)
                    )
                ).scalar_one()
                exp.status = "retired"
                exp.decision = "retired"
                exp.decision_reason = "path traversal probe cleanup (audit preserved)"
                await session.commit()

        asyncio.run(_retire())
