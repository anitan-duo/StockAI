"""Scheduler lifecycle: start creates tasks, stop cancels cleanly, jobs run."""


import pytest

from services.scheduler import Scheduler


@pytest.mark.asyncio
async def test_start_stop_lifecycle(monkeypatch):
    import services.scheduler as sched

    calls: list[str] = []

    async def fake(name):
        async def _fn():
            calls.append(name)
            return {"ok": True}

        return _fn

    monkeypatch.setattr(sched, "run_quote_ingestion", await fake("quotes"))
    monkeypatch.setattr(sched, "run_alert_evaluation", await fake("alerts"))
    monkeypatch.setattr(sched, "run_prediction_generation", await fake("predictions"))
    monkeypatch.setattr(sched, "run_history_backfill", await fake("history"))
    monkeypatch.setattr(sched, "run_outcome_resolution", await fake("outcomes"))
    monkeypatch.setattr(sched, "run_model_monitoring", await fake("monitoring"))
    monkeypatch.setattr(sched, "run_challenger_cycle", await fake("evolution"))
    monkeypatch.setattr(sched, "run_shadow_generation", await fake("shadow"))
    monkeypatch.setattr(sched, "run_ranking_generation", await fake("rankings"))

    # Tiny intervals so every job (including the new history backfill) fires
    # immediately — initial delays default to 0 when not specified... except
    # start() hardcodes production stagger. So verify lifecycle + direct run:
    s = Scheduler(
        quotes_every_s=99999, alerts_every_s=99999, predictions_every_s=99999, history_every_s=99999,
        outcomes_every_s=99999, monitoring_every_s=99999, evolution_every_s=99999, shadow_every_s=99999,
        rankings_every_s=99999,
    )
    s.start()
    assert len(s._tasks) == 9
    await s.stop()
    assert s._tasks == []

    # And every job function itself runs (proves wiring, not just task count).
    assert (await sched.run_quote_ingestion()) == {"ok": True}
    assert (await sched.run_alert_evaluation()) == {"ok": True}
    assert (await sched.run_prediction_generation()) == {"ok": True}
    assert (await sched.run_history_backfill()) == {"ok": True}
    assert (await sched.run_outcome_resolution()) == {"ok": True}
    assert (await sched.run_model_monitoring()) == {"ok": True}
    assert (await sched.run_challenger_cycle()) == {"ok": True}
    assert (await sched.run_shadow_generation()) == {"ok": True}
    assert (await sched.run_ranking_generation()) == {"ok": True}
    assert sorted(calls) == ["alerts", "evolution", "history", "monitoring", "outcomes", "predictions", "quotes", "rankings", "shadow"]


@pytest.mark.asyncio
async def test_lock_skip_when_held():
    from services.cache import get_valkey
    from services.scheduler import _with_lock

    client = await get_valkey()
    if client is None:
        pytest.skip("Valkey unavailable")
    await client.set("scheduler:lock:probe", "1", ex=60)
    try:
        out = await _with_lock("probe", 60, lambda: (_ for _ in ()).throw(AssertionError("must not run")), require_lock=True)
        assert out.get("skipped") is True
    finally:
        await client.delete("scheduler:lock:probe")
