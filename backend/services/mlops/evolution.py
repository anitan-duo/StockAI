"""Autonomous challenger cycle: gated, bounded, never self-promoting.

Per scheduler invocation (daily lock) at most ONE experiment advances:
- capacity check on strictly unburned fresh data (post-2026-08-21);
  fewer than MIN_FRESH_EVALS matured eval points -> skip with reason
  (monitoring + outcome resolution continue regardless);
- frozen configs only (champion-equivalent baseline + evidence-backed
  normalized/context variants from P5/P6 dev results);
- same-window comparison vs baseline + majority; pre-registered bar;
- winner -> candidate + persisted hash-verified artifact; else rejected.
- NEVER promotes, NEVER touches the champion, NEVER reuses burned ranges
  (fresh eval ranges are recorded; overlapping reuse for selection refused).

Wall-clock budget enforced so interactive traffic is never starved.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

FRESH_START = datetime(2026, 8, 22, tzinfo=UTC)  # day after burned v1-holdout end
MIN_FRESH_EVALS = 60
CYCLE_BUDGET_S = 1800
MAX_TRAIN_ROWS = 400

# Frozen challenger grid (devidence: P5-E002 normalized +6.3pp, P6-E005
# context +5.8pp on dev; isotonic throughout — sigmoid showed no stacking).
CONFIGS: tuple[dict, ...] = (
    {"name": "baseline-full-iso", "feature_subset": "full", "market_context": False, "calibration": "isotonic"},
    {"name": "norm-iso", "feature_subset": "normalized", "market_context": False, "calibration": "isotonic"},
    {"name": "norm-ctx-iso", "feature_subset": "normalized", "market_context": True, "calibration": "isotonic"},
)


def _fresh_bars(all_bars: list, start, end) -> list:
    return sorted(
        [b for b in all_bars if start <= b.timestamp <= end],
        key=lambda b: b.timestamp,
    )


async def _load_panel(session, start, end) -> dict[str, list]:
    """All active instruments' bars in window (+400d lookback each for the
    252-bar feature warmup). Histories may extend into older data — only the
    EVAL positions are constrained to the fresh range (final-validation
    pattern, same as Phase-3 holdout protocol)."""

    from sqlalchemy import select

    from apps.api.models.market import Exchange, Instrument
    from apps.api.repositories.market import PriceBarRepository
    from sqlalchemy.orm import selectinload

    insts = (
        await session.execute(
            select(Instrument)
            .options(selectinload(Instrument.exchange))
            .where(Instrument.is_active.is_(True))
        )
    ).scalars().all()
    repo = PriceBarRepository(session)
    panel: dict[str, list] = {}
    for inst in insts:
        bars = await repo.get_range(
            inst.id, "1d", start - timedelta(days=400), end, limit=5000
        )
        if bars:
            panel[inst.symbol] = sorted(bars, key=lambda b: b.timestamp)
    return panel


def _eval_capacity(panel: dict[str, list], start, end, step: int = 10) -> int:
    total = 0
    for bars in panel.values():
        idx = [i for i, b in enumerate(bars) if start <= b.timestamp <= end]
        # Need 252 prior bars for features and a resolved next bar for labels.
        total += sum(1 for i in idx[::step] if i >= 252 and i + 1 < len(bars))
    return total


async def run_evolution_cycle(session, now: datetime | None = None) -> dict:
    """One bounded autonomous cycle. Returns a summary dict (never raises)."""
    from sqlalchemy import select

    from apps.api.models.mlops import Experiment
    from services.backtesting.backtest_service import BacktestEngine
    from services.mlops.experiments import (
        assert_selection_range_allowed,
        record_metrics,
        register_experiment,
        transition,
    )

    t0 = time.time()
    now = now or datetime.now(UTC)
    # Crash recovery: a worker killed mid-cycle must not wedge the system in
    # "training" forever. Stale non-terminal experiment rows are failed
    # explicitly (evidence preserved, never silently resumed).
    stale_cutoff = now - timedelta(hours=6)
    stale = (
        await session.execute(
            select(Experiment).where(
                Experiment.status.in_(["training", "evaluating"]),
                Experiment.updated_at < stale_cutoff,
            )
        )
    ).scalars().all()
    for s in stale:
        s.status = "failed"
        s.decision = "failed"
        s.decision_reason = "stale worker auto-fail: no heartbeat for 6h (crash-safe, see ledger)"
    if stale:
        await session.commit()
    end = now
    # Fresh window: unburned only; assert (raises before any compute on overlap).
    # Use trailing 120d clipped to the fresh range.

    start = max(FRESH_START, end - timedelta(days=120))
    try:
        assert_selection_range_allowed(start, end, "autonomous challenger selection")
    except ValueError as e:
        return {"skipped": True, "reason": f"burned overlap: {e}"}

    panel = await _load_panel(session, start, end)
    if len(panel) < 10:
        return {"skipped": True, "reason": f"panel too thin: {len(panel)} symbols"}
    capacity = _eval_capacity(panel, start, end)
    if capacity < MIN_FRESH_EVALS:
        return {
            "skipped": True,
            "reason": f"insufficient fresh eval points: {capacity} < {MIN_FRESH_EVALS}",
            "fresh_eval_points": capacity,
        }
    # Embargo: never re-select on an already-used fresh range.
    used = (
        await session.execute(
            select(Experiment).where(
                Experiment.experiment_id.like("AUTO-%"),
                Experiment.status.in_(["candidate", "approved", "rejected", "shadow", "retired"]),
            )
        )
    ).scalars().all()
    for exp in used:
        splits = exp.splits or {}
        fr = splits.get("fresh_eval")
        if fr and not (end.isoformat() <= fr[0] or start.isoformat() >= fr[1]):
            return {"skipped": True, "reason": f"fresh range overlaps used {exp.experiment_id}"}

    # Bounded job record (one row per calendar day; re-runs same-day reuse it).
    # Created only after all cheap gates pass, so skips leave no residue.
    from apps.api.models.mlops import TrainingJob

    job_key = f"evolution-{now.strftime('%Y%m%d')}"
    job = (
        await session.execute(
            select(TrainingJob).where(TrainingJob.job_key == job_key)
        )
    ).scalar_one_or_none()
    if job is None:
        job = TrainingJob(
            job_key=job_key, status="running", started_at=now,
            attempts=1, max_attempts=1, timeout_s=CYCLE_BUDGET_S,
        )
        session.add(job)
        await session.flush()
    elif job.status in ("succeeded", "failed", "cancelled"):
        return {"skipped": True, "reason": f"job {job_key} already {job.status}"}
    else:
        job.attempts = (job.attempts or 0) + 1
        job.status = "running"
        job.started_at = now
        await session.flush()

    stamp = now.strftime("%Y%m%d")
    base_n = 0
    while True:
        exp_id = f"AUTO-{stamp}-{base_n:02d}"
        exists = (
            await session.execute(
                select(Experiment).where(Experiment.experiment_id == exp_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            break
        base_n += 1
    exp = await register_experiment(
        session,
        experiment_id=exp_id,
        hypothesis=(
            "Autonomous confirmation: do P5/P6 dev directions (normalized "
            "features, cross-sectional context) transfer to fresh unburned data?"
        ),
        dataset_fingerprint=f"live-bars:{start.date()}->{end.date()}",
        feature_set="normalized+context-variants",
        target="v1-h1d-0.5pct",
        horizon="1d",
        model_family="logistic+rf300+gb200",
        hyperparameters={"configs": [c["name"] for c in CONFIGS]},
        seed=42,
        splits={"fresh_eval": [start.isoformat(), end.isoformat()], "step": 10, "max_rows": MAX_TRAIN_ROWS},
    )
    await transition(session, exp, "training", reason="capacity gate passed")
    await session.commit()

    full_panel = {s: bl for s, bl in panel.items()}
    results: dict[str, dict] = {}
    try:
        await transition(session, exp, "evaluating", reason="walk-forward on fresh window")
        for cfg in CONFIGS:
            if time.time() - t0 > CYCLE_BUDGET_S:
                raise TimeoutError(f"cycle budget {CYCLE_BUDGET_S}s exceeded")
            stats = await _evaluate_config(panel, full_panel, start, end, cfg)
            results[cfg["name"]] = stats
    except Exception as e:  # noqa: BLE001 - recorded, never raised
        await transition(session, exp, "failed", reason=str(e)[:500])
        job.experiment_id = exp.id
        job.status = "failed"
        job.error = str(e)[:500]
        job.finished_at = datetime.now(UTC)
        job.compute_seconds = time.time() - t0
        await session.commit()
        return {"experiment_id": exp_id, "status": "failed", "error": str(e)[:300]}

    verdict = _decide(results)
    await record_metrics(
        session, exp,
        metrics={k: {m: v[m] for m in ("n", "accuracy", "balanced_accuracy", "brier")} for k, v in results.items()},
        backtest={},
        compute_seconds=time.time() - t0,
    )
    if verdict["promote_to_candidate"]:
        from services.mlops.artifacts import persist_candidate_artifact

        winner_cfg = next(c for c in CONFIGS if c["name"] == verdict["winner"])
        art = await persist_candidate_artifact(exp, winner_cfg, panel)
        await record_metrics(
            session, exp, artifact_path=art["path"], artifact_sha=art["sha"],
        )
        await transition(session, exp, "candidate", reason=verdict["reason"])
    else:
        await transition(session, exp, "rejected", reason=verdict["reason"])
    job.experiment_id = exp.id
    job.status = "succeeded"
    job.finished_at = datetime.now(UTC)
    job.compute_seconds = time.time() - t0
    await session.commit()
    return {
        "experiment_id": exp_id,
        "status": exp.status,
        "results": {k: {"n": v["n"], "accuracy": v["accuracy"], "brier": v["brier"]} for k, v in results.items()},
        "reason": verdict["reason"],
    }


async def _evaluate_config(panel, full_panel, start, end, cfg: dict) -> dict:
    """Walk-forward per symbol on the fresh window; aggregate like the runner."""
    from services.backtesting.backtest_service import BacktestEngine
    from services.ml.recipe import TARGET_DOWN_THRESHOLD, TARGET_UP_THRESHOLD

    y_true: list[int] = []
    y_prob: list[list[float]] = []
    per_market: dict[str, dict] = {}
    for symbol, blist in sorted(panel.items()):
        preds, _ = BacktestEngine.generate_causal_predictions(
            blist, start, end, retrain_every_n_eval=2, eval_step_bars=10,
            max_train_rows=MAX_TRAIN_ROWS, calibration=cfg["calibration"],
            feature_subset=cfg["feature_subset"],
            market_context=cfg["market_context"],
            panel=full_panel if cfg["market_context"] else None,
            symbol=symbol if cfg["market_context"] else None,
        )
        closes = [float(b.close) for b in blist]
        idx = {b.timestamp: i for i, b in enumerate(blist)}
        for p in preds:
            i = idx.get(p.prediction_timestamp)
            if i is None or i + 1 >= len(blist):
                continue
            ret = (closes[i + 1] - closes[i]) / closes[i] if closes[i] else 0.0
            true = 2 if ret > TARGET_UP_THRESHOLD else (0 if ret < TARGET_DOWN_THRESHOLD else 1)
            y_true.append(true)
            y_prob.append([float(p.down_probability), float(p.neutral_probability), float(p.up_probability)])
    n = len(y_true)
    if n == 0:
        return {"n": 0, "accuracy": 0.0, "balanced_accuracy": 0.0, "brier": 1.0}
    import numpy as np

    yp = np.array(y_prob)
    yt = np.array(y_true)
    pred = yp.argmax(axis=1)
    brier = float(np.mean([((yt == c).astype(int) - yp[:, c]) ** 2 for c in range(3)]))
    bal = 0.0
    for c in range(3):
        mask = yt == c
        if mask.sum():
            bal += (pred[mask] == c).mean()
    bal /= 3
    return {
        "n": n,
        "accuracy": round(float((pred == yt).mean()), 4),
        "balanced_accuracy": round(float(bal), 4),
        "brier": round(brier, 4),
    }


def _decide(results: dict[str, dict]) -> dict:
    """Pre-registered bar vs the champion-equivalent baseline on the SAME
    fresh window (paired comparison, no burned data)."""
    base = results.get("baseline-full-iso")
    if base is None or base["n"] < MIN_FRESH_EVALS:
        return {"promote_to_candidate": False, "winner": None,
                "reason": "baseline lacks minimum fresh evals"}
    best_name, best = None, None
    for name, r in results.items():
        if name == "baseline-full-iso" or r["n"] < MIN_FRESH_EVALS:
            continue
        if best is None or (r["accuracy"], -r["brier"]) > (best["accuracy"], -best["brier"]):
            best_name, best = name, r
    if best is None:
        return {"promote_to_candidate": False, "winner": None, "reason": "no challenger cleared minimum evals"}
    d_acc = best["accuracy"] - base["accuracy"]
    d_brier = best["brier"] - base["brier"]
    if d_acc >= 0.05 and d_brier <= -0.01:
        return {"promote_to_candidate": True, "winner": best_name,
                "reason": f"{best_name}: acc {base['accuracy']}->{best['accuracy']} (Δ{d_acc:+.4f}), "
                          f"brier {base['brier']}->{best['brier']} (Δ{d_brier:+.4f}), n={best['n']}"}
    return {"promote_to_candidate": False, "winner": best_name,
            "reason": f"best {best_name} misses bar: Δacc {d_acc:+.4f} (need ≥+0.05), Δbrier {d_brier:+.4f} (need ≤-0.01)"}
