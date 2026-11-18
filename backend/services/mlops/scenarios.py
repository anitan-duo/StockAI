"""Historical scenario lab: blind predict-then-reveal challenges.

Blindness is enforced server-side at every step:
- scenario bars endpoint returns ONLY bars with timestamp <= data_cutoff;
- predictions commit BEFORE any outcome is computed or revealed;
- reveal reads strictly-later bars and freezes the attempt row;
- repeats (same scenario + experiment) never extend streaks;
- final-split scenarios can never be marked used_for_training.

Streak rule (pre-registered): action correctness per
services.ml.tasks.judge_action (long-only; SELL = exit, never short).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select


class ScenarioError(Exception):
    """Invalid scenario operation."""


def _scenario_key(symbol: str, exchange: str, decision_date: str, task_id: str) -> str:
    return f"{symbol.upper()}:{exchange.upper()}:{decision_date}:{task_id}"


async def create_scenario(
    session,
    *,
    symbol: str,
    exchange: str,
    decision_date: str,
    task_id: str = "h1d",
    split: str = "train",
) -> object:
    """Create (or return existing) scenario for a date+symbol+horizon.

    Eligible-session mapping: the decision timestamp is the latest persisted
    daily bar at or before the requested date. Dates with no session at all
    (e.g. before coverage) raise ScenarioError — never invented.
    """
    from datetime import date as _date

    from apps.api.models.market import Exchange, Instrument
    from apps.api.models.price import PriceBar
    from apps.api.models.scenarios import Scenario
    from services.ml.tasks import get_task

    try:
        task = get_task(task_id)
    except ValueError as e:
        raise ScenarioError(str(e)) from None
    if split not in ("train", "validation", "final"):
        raise ScenarioError(f"Unknown split: {split}")
    try:
        day = _date.fromisoformat(decision_date)
    except ValueError:
        raise ScenarioError(f"Bad date: {decision_date}") from None

    exch = (
        await session.execute(select(Exchange).where(Exchange.code == exchange.upper()))
    ).scalar_one_or_none()
    if exch is None:
        raise ScenarioError(f"Unknown exchange: {exchange}")
    inst = (
        await session.execute(
            select(Instrument).where(
                Instrument.symbol == symbol.upper(),
                Instrument.exchange_id == exch.id,
            )
        )
    ).scalar_one_or_none()
    if inst is None:
        raise ScenarioError(f"Unknown instrument: {symbol} on {exchange}")

    key = _scenario_key(symbol, exchange, day.isoformat(), task.task_id)
    existing = (
        await session.execute(select(Scenario).where(Scenario.scenario_key == key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # Latest bar at or before the requested date (eligible session mapping).
    bars = (
        await session.execute(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == inst.id,
                PriceBar.timeframe == "1d",
                PriceBar.timestamp
                < datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=UTC),
            )
            .order_by(PriceBar.timestamp.desc())
            .limit(400)
        )
    ).scalars().all()
    if not bars:
        raise ScenarioError(f"No session at or before {day} for {symbol}")
    decision_ts = max(b.timestamp for b in bars)
    # Snapshot hash: the exact input set (reproducible replay detection).
    digest = hashlib.sha256()
    for b in sorted(bars, key=lambda x: x.timestamp):
        digest.update(f"{b.timestamp.isoformat()}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}".encode())
    scen = Scenario(
        scenario_key=key,
        instrument_id=inst.id,
        decision_ts=decision_ts,
        horizon=task.task_id,
        target_version=task.target_version,
        data_cutoff=decision_ts,
        feature_schema_version="v1",
        split=split,
        outcome_status="pending",
        snapshot_hash="sha256:" + digest.hexdigest(),
    )
    session.add(scen)
    await session.flush()
    return scen


async def get_scenario_bars(session, scenario, limit: int = 400) -> list:
    """Bars visible at decision time: timestamp <= data_cutoff, newest last.

    THE blindness boundary. Callers must never merge later bars into this.
    """
    from apps.api.models.price import PriceBar

    rows = (
        await session.execute(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == scenario.instrument_id,
                PriceBar.timeframe == "1d",
                PriceBar.timestamp <= scenario.data_cutoff,
            )
            .order_by(PriceBar.timestamp.desc())
            .limit(limit)
        )
    ).scalars().all()
    return sorted(rows, key=lambda b: b.timestamp)


async def submit_prediction(
    session,
    *,
    scenario_id,
    experiment_id: str,
    up: float,
    neutral: float,
    down: float,
    action: str,
    model_version: str = "ensemble-v1.0",
    artifact_sha: str | None = None,
) -> object:
    """Commit a blind forecast. The outcome is unknown at this point by
    construction (reveal is a separate call that reads later bars)."""
    from apps.api.models.scenarios import ChallengeAttempt, Scenario

    action = action.upper()
    if action not in ("BUY", "SELL", "HOLD"):
        raise ScenarioError(f"Unknown action: {action}")
    total = float(up) + float(neutral) + float(down)
    if abs(total - 1.0) > 1e-3:
        raise ScenarioError(f"Probabilities must sum to 1, got {total}")
    for v in (up, neutral, down):
        if not 0.0 <= float(v) <= 1.0:
            raise ScenarioError("Probabilities must be in [0, 1]")
    scen = await session.get(Scenario, scenario_id)
    if scen is None:
        raise ScenarioError("Scenario not found")
    prior = (
        await session.execute(
            select(ChallengeAttempt).where(
                ChallengeAttempt.scenario_id == scen.id,
                ChallengeAttempt.experiment_id == experiment_id,
            )
        )
    ).scalars().all()
    attempt = ChallengeAttempt(
        scenario_id=scen.id,
        experiment_id=experiment_id,
        model_version=model_version,
        artifact_sha=artifact_sha,
        horizon=scen.horizon,
        pred_up=float(up),
        pred_neutral=float(neutral),
        pred_down=float(down),
        action=action,
        committed_at=datetime.now(UTC),
        is_repeat=len(prior) > 0,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def reveal_attempt(session, attempt_id) -> object:
    """Reveal the outcome from genuine subsequent bars and freeze the row.

    Label: task return over the next N TRADING sessions after the decision
    date (sessions that exist in the DB, never calendar arithmetic), then
    task thresholds + the pre-registered action-correctness rule. Holidays
    simply shift which bars count. Missing future bars -> unavailable
    (attempt stays committed-but-unrevealed, never defaulted).
    """
    from apps.api.models.price import PriceBar
    from apps.api.models.scenarios import ChallengeAttempt, Scenario
    from services.ml.tasks import get_task, judge_action, label_return

    attempt = await session.get(ChallengeAttempt, attempt_id)
    if attempt is None:
        raise ScenarioError("Attempt not found")
    if attempt.revealed_at is not None:
        return attempt  # idempotent: frozen rows are never rewritten
    scen = await session.get(Scenario, attempt.scenario_id)
    task = get_task(scen.horizon)
    bars = (
        await session.execute(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == scen.instrument_id,
                PriceBar.timeframe == "1d",
                PriceBar.timestamp > scen.data_cutoff,
            )
            .order_by(PriceBar.timestamp)
            .limit(task.horizon_sessions + 2)
        )
    ).scalars().all()
    # N eligible sessions strictly after the decision date.
    future = [b for b in bars if b.timestamp.date() > scen.data_cutoff.date()]
    if len(future) < task.horizon_sessions:
        scen.outcome_status = "pending"
        await session.flush()
        raise ScenarioError(
            f"Outcome not yet matured: {len(future)}/{task.horizon_sessions} sessions"
        )
    window = future[: task.horizon_sessions]
    # Base price: latest bar at/before cutoff with positive close.
    base_rows = (
        await session.execute(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == scen.instrument_id,
                PriceBar.timeframe == "1d",
                PriceBar.timestamp <= scen.data_cutoff,
            )
            .order_by(PriceBar.timestamp.desc())
            .limit(1)
        )
    ).scalars().all()
    if not base_rows or float(base_rows[0].close) <= 0:
        raise ScenarioError("No valid base price at decision time")
    base = float(base_rows[0].close)
    last = window[-1]
    if float(last.close) <= 0 or int(last.volume or 0) < 0:
        raise ScenarioError("Invalid evaluation bar")
    ret = float(last.close) / base - 1.0
    attempt.actual_return_pct = round(ret * 100, 4)
    attempt.actual_direction = label_return(task, ret)
    attempt.correct = judge_action(task, attempt.action, ret)
    attempt.revealed_at = datetime.now(UTC)
    scen.outcome_status = "matured"
    await session.flush()
    await _update_streak(session, attempt)
    await _auto_diagnose(session, attempt, scen, window, base, ret)
    await session.flush()
    return attempt


async def _update_streak(session, attempt) -> None:
    """Streak accounting: repeats never extend; miss resets current."""
    from apps.api.models.scenarios import Streak

    key = f"{attempt.experiment_id}:{attempt.horizon}"
    streak = (
        await session.execute(select(Streak).where(Streak.streak_key == key))
    ).scalar_one_or_none()
    if streak is None:
        streak = Streak(
            streak_key=key, experiment_id=attempt.experiment_id,
            horizon=attempt.horizon, correctness_rule="action-vs-cost-band",
        )
        session.add(streak)
        await session.flush()
    if attempt.is_repeat:
        return  # deterministic replays are recorded, never counted
    streak.attempts += 1
    streak.unique_scenarios += 1
    if attempt.correct:
        streak.correct_count += 1
        streak.current += 1
        streak.longest = max(streak.longest, streak.current)
        if streak.current >= 10:
            streak.completed_10_of_10 = True
    else:
        streak.incorrect_count += 1
        streak.current = 0


async def _auto_diagnose(session, attempt, scen, window, base: float, ret: float) -> None:
    """Rule-based first-pass diagnosis recorded as evidence (hypotheses, not
    verdicts). A human/operator hypothesis can supersede via the API."""
    if attempt.correct:
        return
    from apps.api.models.price import PriceBar
    from apps.api.models.scenarios import ErrorDiagnosis

    task_id = scen.horizon
    evidence: dict = {
        "action": attempt.action,
        "realized_return_pct": round(ret * 100, 4),
        "window_sessions": len(window),
        "predicted": {"up": attempt.pred_up, "neutral": attempt.pred_neutral, "down": attempt.pred_down},
    }
    alternatives = ["unclassified-noise"]
    category = "unclassified"
    confidence = "low"
    # Stale input: gap between decision bar and previous session.
    prior = (
        await session.execute(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == scen.instrument_id,
                PriceBar.timeframe == "1d",
                PriceBar.timestamp < scen.data_cutoff,
            )
            .order_by(PriceBar.timestamp.desc())
            .limit(1)
        )
    ).scalars().all()
    if prior:
        gap_days = (scen.data_cutoff.date() - prior[0].timestamp.date()).days
        evidence["prior_session_gap_days"] = gap_days
        if gap_days > 5:
            category, confidence = "stale-data", "medium"
            alternatives.append("volatility-regime")
    # Volatility regime: 20d realized range percentile vs trailing 120d.
    hist = (
        await session.execute(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == scen.instrument_id,
                PriceBar.timeframe == "1d",
                PriceBar.timestamp <= scen.data_cutoff,
            )
            .order_by(PriceBar.timestamp.desc())
            .limit(140)
        )
    ).scalars().all()
    hist = sorted(hist, key=lambda b: b.timestamp)
    if len(hist) >= 40:

        ranges = [(float(b.high) - float(b.low)) / float(b.close) for b in hist if float(b.close) > 0]
        if ranges:
            cur = sum(ranges[-20:]) / min(20, len(ranges))
            ref = sorted(ranges[:-20]) if len(ranges) > 20 else sorted(ranges)
            pct = sum(1 for r in ref if r <= cur) / len(ref)
            evidence["range_percentile_120d"] = round(pct, 3)
            if pct >= 0.8 and category == "unclassified":
                category, confidence = "volatility-regime", "medium"
                alternatives.append("stale-data")
    # Threshold: aggressive action inside the cost band.
    from services.ml.tasks import get_task as _gt

    band = _gt(task_id).cost_band_pct / 100.0
    if attempt.action in ("BUY", "SELL") and abs(ret) <= band:
        evidence["inside_cost_band"] = True
        if category == "unclassified":
            category, confidence = "threshold", "medium"
            alternatives.append("miscalibration")
    # Miscalibration: extreme confidence, wrong direction.
    max_prob = max(attempt.pred_up, attempt.pred_neutral, attempt.pred_down)
    evidence["max_probability"] = round(max_prob, 4)
    if max_prob >= 0.7 and category == "unclassified":
        category, confidence = "miscalibration", "low"
        alternatives.append("overfitting")
    session.add(
        ErrorDiagnosis(
            attempt_id=attempt.id,
            category=category,
            evidence=evidence,
            alternatives=alternatives,
            confidence=confidence,
            intervention=None,
            success_metric="next-20-same-task-challenges accuracy delta vs current streak rate",
        )
    )


async def mark_scenario_training_use(session, scenario_id, used: bool = True) -> None:
    """Flag training use. FINAL-split scenarios may never be flagged."""
    from apps.api.models.scenarios import Scenario

    scen = await session.get(Scenario, scenario_id)
    if scen is None:
        raise ScenarioError("Scenario not found")
    if scen.split == "final" and used:
        raise ScenarioError("final-split scenarios are quarantined from training")
    scen.seen_by_model = True
    scen.used_for_training = used
    await session.flush()
