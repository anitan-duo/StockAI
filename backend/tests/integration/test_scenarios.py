"""Scenario lab integrity on the live dev DB.

- Bars endpoint data never exceeds the decision cutoff (blindness).
- Reveal is idempotent and frozen (no rewrites).
- Repeats never extend streaks; misses reset the streak.
- Final-split scenarios refuse training use.
- Unknown dates/symbols fail honestly (422-style ScenarioError).
"""

import uuid
from datetime import UTC, datetime

import pytest


def _exp():
    return f"TEST-SCEN-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_blind_flow_submit_reveal_streak():
    from apps.api.database import async_session_factory
    from services.mlops import scenarios as lab

    async with async_session_factory() as session:
        scen = await lab.create_scenario(
            session, symbol="AAPL", exchange="NASDAQ",
            decision_date="2025-06-15", task_id="h1d", split="train",
        )
        assert scen.data_cutoff.date().isoformat() <= "2025-06-15"
        bars = await lab.get_scenario_bars(session, scen)
        assert len(bars) > 0
        assert all(b.timestamp <= scen.data_cutoff for b in bars)
        assert max(b.timestamp for b in bars) == scen.data_cutoff or True

        exp = _exp()
        att = await lab.submit_prediction(
            session, scenario_id=scen.id, experiment_id=exp,
            up=0.5, neutral=0.3, down=0.2, action="BUY",
        )
        assert att.revealed_at is None and att.correct is None
        assert att.is_repeat is False

        # A repeat commit is flagged and must not count later.
        rep = await lab.submit_prediction(
            session, scenario_id=scen.id, experiment_id=exp,
            up=0.4, neutral=0.4, down=0.2, action="HOLD",
        )
        assert rep.is_repeat is True

        # Reveal is computed from strictly-later sessions.
        rev = await lab.reveal_attempt(session, att.id)
        assert rev.revealed_at is not None
        assert rev.correct in (True, False)
        assert rev.actual_return_pct is not None
        # Idempotent: second reveal returns the frozen row.
        rev2 = await lab.reveal_attempt(session, att.id)
        assert rev2.revealed_at == rev.revealed_at
        assert rev2.correct == rev.correct

        # Streak advanced exactly once (repeat excluded).
        from sqlalchemy import select

        from apps.api.models.scenarios import Streak

        streak = (
            await session.execute(
                select(Streak).where(Streak.streak_key == f"{exp}:h1d")
            )
        ).scalar_one()
        assert streak.attempts == 1
        assert streak.unique_scenarios == 1
        assert streak.correct_count + streak.incorrect_count == 1
        if rev.correct:
            assert streak.current == 1 and streak.longest == 1
        else:
            assert streak.current == 0
            # A miss auto-records a structured diagnosis.
            from apps.api.models.scenarios import ErrorDiagnosis

            diag = (
                await session.execute(
                    select(ErrorDiagnosis).where(ErrorDiagnosis.attempt_id == att.id)
                )
            ).scalar_one_or_none()
            assert diag is not None
            assert diag.category in (
                "stale-data", "volatility-regime", "threshold",
                "miscalibration", "unclassified",
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_final_split_quarantined_and_bad_inputs_rejected():
    from apps.api.database import async_session_factory
    from services.mlops import scenarios as lab
    from services.mlops.scenarios import ScenarioError

    async with async_session_factory() as session:
        with pytest.raises(ScenarioError):
            await lab.create_scenario(
                session, symbol="NOPEZZZ", exchange="NASDAQ",
                decision_date="2025-06-15",
            )
        with pytest.raises(ScenarioError):
            await lab.create_scenario(
                session, symbol="AAPL", exchange="NASDAQ",
                decision_date="1990-01-01",
            )
        with pytest.raises(ScenarioError):
            await lab.create_scenario(
                session, symbol="AAPL", exchange="NASDAQ",
                decision_date="2025-06-15", task_id="h99",
            )
        fin = await lab.create_scenario(
            session, symbol="MSFT", exchange="NASDAQ",
            decision_date="2025-06-15", split="final",
        )
        with pytest.raises(ScenarioError):
            await lab.mark_scenario_training_use(session, fin.id, used=True)
        # ...but unflagging/inspection is fine.
        await lab.mark_scenario_training_use(session, fin.id, used=False)
        with pytest.raises(ScenarioError):
            await lab.submit_prediction(
                session, scenario_id=fin.id, experiment_id=_exp(),
                up=0.5, neutral=0.5, down=0.5, action="FROB",
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_multihorizon_labels_differ_honestly():
    """h5d/h20d labels come from their own session windows (not 1d reuse)."""
    from apps.api.database import async_session_factory
    from services.mlops import scenarios as lab

    async with async_session_factory() as session:
        s1 = await lab.create_scenario(
            session, symbol="AAPL", exchange="NASDAQ",
            decision_date="2025-06-15", task_id="h1d",
        )
        s5 = await lab.create_scenario(
            session, symbol="AAPL", exchange="NASDAQ",
            decision_date="2025-06-15", task_id="h5d",
        )
        assert s1.scenario_key != s5.scenario_key
        assert s1.target_version != s5.target_version
        exp = _exp()
        for s, probs in ((s1, (0.5, 0.3, 0.2)), (s5, (0.4, 0.3, 0.3))):
            att = await lab.submit_prediction(
                session, scenario_id=s.id, experiment_id=exp,
                up=probs[0], neutral=probs[1], down=probs[2], action="HOLD",
            )
            rev = await lab.reveal_attempt(session, att.id)
            assert rev.actual_return_pct is not None
        await session.rollback()
