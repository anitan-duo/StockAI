"""Minimal operational scheduler (asyncio tasks, Valkey-locked).

Runs inside the API lifespan; no external task framework. Every cycle is
guarded by a Valkey lock so multi-worker deployments skip rather than double
(alert evaluation additionally fails CLOSED without Valkey to prevent
duplicate triggers). Disable with SCHEDULER_ENABLED=false.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("stockai.scheduler")


async def _with_lock(name: str, ttl: int, fn, *, require_lock: bool):
    """Run fn under a Valkey lock; skip (log) when lock is held/unavailable.

    Lock policy: hourly-or-slower jobs (alerts, predictions, outcomes,
    monitoring, evolution, shadow) REQUIRE the lock — with two API workers,
    fail-open duplicates predictions and races experiment registration.
    Skipping a cycle is safe (idempotent jobs, next cycle retries).
    Freshness-critical jobs (quotes, history backfill) stay fail-open:
    their upserts are idempotent and staleness costs more than a dupe.
    """
    from services.cache import get_valkey

    client = await get_valkey()
    if client is None:
        if require_lock:
            logger.warning("scheduler.skip", extra={"job": name, "reason": "valkey-unavailable"})
            return {"skipped": True, "reason": "valkey-unavailable"}
        logger.warning("scheduler.no-lock", extra={"job": name})
        return await fn()
    key = f"scheduler:lock:{name}"
    try:
        acquired = await client.set(key, "1", nx=True, ex=ttl)
    except Exception as e:
        logger.warning("scheduler.lock-error", extra={"job": name, "error": str(e)})
        return {"skipped": True, "reason": "lock-error"} if require_lock else await fn()
    if not acquired:
        logger.info("scheduler.lock-held", extra={"job": name})
        return {"skipped": True, "reason": "lock-held"}
    try:
        return await fn()
    finally:
        try:
            await client.delete(key)
        except Exception:
            pass


async def run_quote_ingestion() -> dict[str, Any]:
    """Ingest latest quotes for active instruments (idempotent upserts)."""
    from apps.api.config import settings
    from apps.api.database import async_session_factory
    from services.ingestion.ingestion_service import IngestionService
    from services.ingestion.providers.factory import ProviderFactory

    async def _run():
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from apps.api.models.market import Exchange, Instrument

        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(Instrument)
                    .options(selectinload(Instrument.exchange).selectinload(Exchange.market))
                    .where(Instrument.is_active.is_(True))
                    .limit(settings.ingestion_batch_size)
                )
            ).scalars().all()
            symbols = [
                (i.symbol, i.exchange.code if i.exchange else "", i.exchange.market.code if i.exchange and i.exchange.market else None)
                for i in rows
            ]
            svc = IngestionService(session, ProviderFactory.get_fallback_provider())
            result = await svc.ingest_quotes(symbols)
            await session.commit()
            return result

    async def _guarded():
        from services.cache import get_valkey

        out = await _with_lock("quotes", 300, _run, require_lock=False)
        client = await get_valkey()
        if client is not None and not out.get("skipped"):
            try:
                await client.set("scheduler:last_ingestion", datetime.now(UTC).isoformat(), ex=86400)
            except Exception:
                pass
        return out

    out = await _guarded()
    logger.info("scheduler.quotes", extra={"result": _summarize(out)})
    return out


async def run_alert_evaluation() -> dict[str, Any]:
    """Evaluate ACTIVE alerts once; fire → TRIGGERED + trigger row (idempotent)."""
    from decimal import Decimal

    from apps.api.database import async_session_factory
    from apps.api.models.alert import AlertStatus
    from apps.api.models.market import Instrument
    from apps.api.repositories.alert import AlertRepository, AlertTriggerRepository
    from apps.api.repositories.prediction import PredictionRepository
    from services.alerts.evaluator import evaluate

    async def _run():
        evaluated = fired = errors = 0
        async with async_session_factory() as session:
            alerts = await AlertRepository(session).get_alerts_to_evaluate(limit=500)
            # Plain specs first: loop commit()/rollback() expires ORM
            # instances, and later attribute access on them raises
            # MissingGreenlet (same class as the predictions-job stall).
            specs = [
                (
                    a.id,
                    str(a.alert_type),
                    str(a.condition),
                    Decimal(str(a.target_value)),
                    a.instrument_id,
                )
                for a in alerts
                if a.status == AlertStatus.ACTIVE
            ]
            repo = AlertRepository(session)
            for alert_id, alert_type, condition, target, instrument_id in specs:
                try:
                    instrument = await session.get(Instrument, instrument_id)
                    snap = None
                    if instrument is not None:
                        from apps.api.repositories.market import MarketSnapshotRepository

                        snap = await MarketSnapshotRepository(session).get_latest(instrument_id)
                    pred = await PredictionRepository(session).get_latest_for_instrument(
                        instrument_id, "1d"
                    )
                    res = evaluate(alert_type, condition, target, snap, pred)
                    evaluated += 1
                    if not res.fires or res.value is None:
                        continue
                    # Re-check ACTIVE via a fresh read (not refresh() on a
                    # possibly-stale instance), then fire.
                    fresh = await repo.get(alert_id)
                    if fresh is None or fresh.status != AlertStatus.ACTIVE:
                        continue
                    await AlertRepository(session).update_status(alert_id, AlertStatus.TRIGGERED, datetime.now(UTC))
                    await AlertTriggerRepository(session).create_trigger(alert_id, float(res.value), res.message[:500])
                    await session.commit()
                    fired += 1
                except Exception as e:
                    errors += 1
                    logger.warning("scheduler.alert-error", extra={"error": str(e)})
                    try:
                        await session.rollback()
                    except Exception:
                        pass
            return {"evaluated": evaluated, "fired": fired, "errors": errors}

    out = await _with_lock("alerts", 300, _run, require_lock=True)
    logger.info("scheduler.alerts", extra={"result": _summarize(out)})
    return out


async def run_prediction_generation() -> dict[str, Any]:
    """Generate today's predictions for instruments missing one (idempotent)."""
    from apps.api.database import async_session_factory
    from apps.api.repositories.market import InstrumentRepository
    from apps.api.repositories.prediction import PredictionRepository
    from services.prediction.prediction_service import PredictionService

    async def _run():
        success, skipped, failed = [], [], []
        async with async_session_factory() as session:
            instruments = await InstrumentRepository(session).get_active_instruments(limit=100)
            # Extract plain values BEFORE the loop: commit()/rollback() inside
            # the loop expires ORM instances, and any later attribute access
            # on them raises MissingGreenlet (async SQLAlchemy cannot lazily
            # refresh). This once silently capped the job at ~1 success/run.
            specs = [(inst.id, inst.symbol) for inst in instruments]
            for inst_id, symbol in specs:
                try:
                    existing = await PredictionRepository(session).get_latest_for_instrument(inst_id, "1d")
                    if existing and existing.prediction_timestamp.date() == datetime.now(UTC).date():
                        skipped.append(symbol)
                        continue
                    svc = PredictionService(session)
                    await svc.generate_prediction(inst_id, "1d")
                    await session.commit()
                    success.append(symbol)
                except Exception as e:
                    failed.append({"symbol": symbol, "error": str(e)[:200]})
                    try:
                        await session.rollback()
                    except Exception:
                        pass
        return {"success": success, "skipped": skipped, "failed": failed}

    out = await _with_lock("predictions", 3600, _run, require_lock=True)
    logger.info("scheduler.predictions", extra={"result": _summarize(out)})
    return out


async def run_history_backfill(lookback_days: int = 45) -> dict[str, Any]:
    """Incrementally backfill daily bars for active instruments (idempotent).

    QUOTES alone cannot heal multi-week gaps (e.g. Sep-2026 for US names):
    they only upsert the current day. This job asks each provider for bars
    newer than the latest persisted timestamp (the ingestion service skips
    anything already stored), so gaps close over successive runs without
    ever re-inserting duplicates or fabricating points.
    """
    from datetime import timedelta

    from apps.api.database import async_session_factory
    from services.ingestion.ingestion_service import IngestionService
    from services.ingestion.providers.factory import ProviderFactory

    async def _run():
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from apps.api.models.market import Exchange, Instrument

        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(Instrument)
                    .options(selectinload(Instrument.exchange).selectinload(Exchange.market))
                    .where(Instrument.is_active.is_(True))
                )
            ).scalars().all()
            end = datetime.now(UTC)
            start = end - timedelta(days=lookback_days)
            backfilled, up_to_date, failed = [], [], []
            # Plain tuples first (see run_prediction_generation: ORM instances
            # must not be touched after a loop commit/rollback expires them).
            specs = [
                (
                    inst.symbol,
                    inst.exchange.code if inst.exchange else "",
                    inst.exchange.market.code if inst.exchange and inst.exchange.market else None,
                )
                for inst in rows
            ]
            for symbol, exch_code, mkt in specs:
                try:
                    svc = IngestionService(session, ProviderFactory.get_fallback_provider())
                    res = await svc.ingest_historical(symbol, exch_code, mkt, "1d", start, end)
                    await session.commit()
                    if res.get("validated"):
                        backfilled.append(symbol)
                    else:
                        up_to_date.append(symbol)
                except Exception as e:
                    failed.append({"symbol": symbol, "error": str(e)[:200]})
                    try:
                        await session.rollback()
                    except Exception:
                        pass
            return {"backfilled": backfilled, "up_to_date": up_to_date, "failed": failed}

    out = await _with_lock("history", 21600, _run, require_lock=False)
    logger.info("scheduler.history", extra={"result": _summarize(out)})
    return out


async def run_outcome_resolution() -> dict[str, Any]:
    """Resolve matured 1d prediction outcomes (idempotent; see outcomes.py)."""
    from apps.api.database import async_session_factory
    from services.prediction.outcomes import resolve_matured_outcomes

    async def _run():
        async with async_session_factory() as session:
            return await resolve_matured_outcomes(session)

    out = await _with_lock("outcomes", 3600, _run, require_lock=True)
    logger.info("scheduler.outcomes", extra={"result": _summarize(out)})
    return out


async def run_model_monitoring() -> dict[str, Any]:
    """Compute matured-outcome performance + drift signals (provisional vs
    confirmed kept distinct: only resolved outcomes feed accuracy metrics)."""
    from apps.api.database import async_session_factory
    from services.mlops.monitor import compute_monitor_snapshot

    async def _run():
        async with async_session_factory() as session:
            return await compute_monitor_snapshot(session)

    out = await _with_lock("monitoring", 3600, _run, require_lock=True)
    logger.info("scheduler.monitoring", extra={"result": _summarize(out)})
    return out


async def run_challenger_cycle() -> dict[str, Any]:
    """Bounded autonomous research cycle (see services.mlops.evolution).

    Gated: runs only with enough newly matured outcomes; one experiment per
    cycle max; never promotes (candidates only — approval is a human/admin
    API action). Never touches the champion.
    """
    from apps.api.database import async_session_factory
    from services.mlops.evolution import run_evolution_cycle

    async def _run():
        async with async_session_factory() as session:
            return await run_evolution_cycle(session)

    out = await _with_lock("evolution", 86400, _run, require_lock=True)
    logger.info("scheduler.evolution", extra={"result": _summarize(out)})
    return out


async def run_ranking_generation() -> dict[str, Any]:
    """Persist cross-sectional rankings and resolve matured outcomes (ACC-001).

    Relative objective only: these snapshots are expected-performance ranks
    versus the eligible cross-section, not absolute up/down forecasts.
    """
    from apps.api.database import async_session_factory
    from services.ranking.service import RankingService

    async def _run():
        snapshots = []
        errors = []
        async with async_session_factory() as session:
            service = RankingService(session)
            for horizon in ("1d", "5d", "10d"):
                try:
                    result = await service.rank(horizon=horizon)
                    snap = await service.persist(result)
                    snapshots.append(
                        {
                            "horizon": horizon,
                            "as_of_date": result["as_of_date"].isoformat(),
                            "ranked": result["ranked_count"],
                            "snapshot_id": str(snap.id),
                        }
                    )
                except Exception as e:
                    errors.append({"horizon": horizon, "error": str(e)[:200]})
            outcomes = await service.resolve_outcomes(max_snapshots=200)
        return {"snapshots": snapshots, "outcomes": outcomes, "errors": errors}

    out = await _with_lock("rankings", 3600, _run, require_lock=True)
    logger.info("scheduler.rankings", extra={"result": out})
    return out


async def run_shadow_generation() -> dict[str, Any]:
    """Shadow predictions for candidate experiments (champion untouched)."""
    from apps.api.database import async_session_factory
    from services.mlops.shadow import run_shadow_generation as _shadow

    async def _run():
        async with async_session_factory() as session:
            return await _shadow(session)

    out = await _with_lock("shadow", 3600, _run, require_lock=True)
    logger.info("scheduler.shadow", extra={"result": _summarize(out)})
    return out


def _summarize(out: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(out, dict):
        return {"ok": True}
    summary = {k: (len(v) if isinstance(v, list) else v) for k, v in out.items() if k in ("evaluated", "fired", "errors", "skipped")}
    if "success" in out:
        summary["success"] = len(out["success"])
    if "failed" in out:
        summary["failed"] = len(out["failed"])
    return summary or {"ok": True}


class Scheduler:
    """Lifespan-owned periodic tasks. Intervals from settings/env."""

    def __init__(self, quotes_every_s: int = 300, alerts_every_s: int = 300, predictions_every_s: int = 3600, history_every_s: int = 21600,
                 outcomes_every_s: int = 3600, monitoring_every_s: int = 3600, evolution_every_s: int = 86400,
                 shadow_every_s: int = 3600, rankings_every_s: int = 21600):
        self.quotes_every_s = quotes_every_s
        self.alerts_every_s = alerts_every_s
        self.predictions_every_s = predictions_every_s
        self.history_every_s = history_every_s
        self.outcomes_every_s = outcomes_every_s
        self.monitoring_every_s = monitoring_every_s
        self.evolution_every_s = evolution_every_s
        self.shadow_every_s = shadow_every_s
        self.rankings_every_s = rankings_every_s
        self.quotes_every_s = quotes_every_s
        self.alerts_every_s = alerts_every_s
        self.predictions_every_s = predictions_every_s
        self.history_every_s = history_every_s
        self.outcomes_every_s = outcomes_every_s
        self.monitoring_every_s = monitoring_every_s
        self.evolution_every_s = evolution_every_s
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    async def _loop(self, name: str, every_s: int, fn, initial_delay_s: int = 0) -> None:
        # Stagger first runs so API boot stays fast: provider-heavy jobs
        # (quotes/history sweep 19 symbols through rate-limited vendors)
        # must not saturate the event loop before the server accepts traffic.
        if initial_delay_s > 0:
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=initial_delay_s)
            except TimeoutError:
                pass
        while not self._stop.is_set():
            try:
                await fn()
            except Exception:
                # logger.exception keeps the traceback: a bare job name with
                # no error detail once hid a real failure here for hours.
                logger.exception("scheduler.job-error", extra={"job": name})
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=every_s)
            except TimeoutError:
                pass

    def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._loop("quotes", self.quotes_every_s, run_quote_ingestion, initial_delay_s=15)),
            asyncio.create_task(self._loop("alerts", self.alerts_every_s, run_alert_evaluation, initial_delay_s=20)),
            asyncio.create_task(self._loop("predictions", self.predictions_every_s, run_prediction_generation, initial_delay_s=60)),
            asyncio.create_task(self._loop("history", self.history_every_s, run_history_backfill, initial_delay_s=120)),
            asyncio.create_task(self._loop("outcomes", self.outcomes_every_s, run_outcome_resolution, initial_delay_s=180)),
            asyncio.create_task(self._loop("monitoring", self.monitoring_every_s, run_model_monitoring, initial_delay_s=240)),
            asyncio.create_task(self._loop("evolution", self.evolution_every_s, run_challenger_cycle, initial_delay_s=300)),
            asyncio.create_task(self._loop("shadow", self.shadow_every_s, run_shadow_generation, initial_delay_s=360)),
            asyncio.create_task(self._loop("rankings", self.rankings_every_s, run_ranking_generation, initial_delay_s=420)),
        ]
        logger.info("scheduler.started")

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []
        logger.info("scheduler.stopped")
