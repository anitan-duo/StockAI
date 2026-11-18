"""Live performance monitoring from matured outcomes only.

CONFIRMED performance metrics use resolved PredictionOutcome rows exclusively.
Provisional signals (freshness, coverage, pending labels) are reported as-is and
never counted as evidence. Drift alarms fire only with minimum samples and are
recorded once (until acknowledged) to avoid alert spam.

The learning loop is diagnostic, not autonomous: outcomes measure calibration,
version quality, and regime-specific behavior, but nothing here retrains or
promotes a model. Promotion still requires the pre-registered OOS bar and an
explicit admin action.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select

from services.prediction.evaluation import score_records as canonical_score

ACCURACY_FLOOR = 0.34  # below random-ish 1/3 + margin over 30d window
BRIER_CEILING = 0.26  # per-class mean Brier (production convention)
ECE_CEILING = 0.08
MIN_MATURED_N = 30
CALIBRATION_BINS = (
    (0.0, 0.4, "<40%"),
    (0.4, 0.5, "40-50%"),
    (0.5, 0.6, "50-60%"),
    (0.6, 0.7, "60-70%"),
    (0.7, 1.0001, "70%+"),
)


def normalize_direction(value) -> str:
    return str(value.value if hasattr(value, "value") else value)


def as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _probabilities(pred) -> dict[str, float]:
    return {
        "down": float(pred.down_probability),
        "neutral": float(pred.neutral_probability),
        "up": float(pred.up_probability),
    }


def brier_score(probs: dict[str, float], actual: str) -> float:
    """Per-class mean Brier, matching the production research convention."""
    return float(np.mean([(probs[c] - (1.0 if actual == c else 0.0)) ** 2 for c in probs]))


def log_loss(probs: dict[str, float], actual: str, eps: float = 1e-12) -> float:
    return float(-np.log(max(eps, min(1.0 - eps, probs.get(actual, eps)))))


def metric_cell(records: list[dict]) -> dict:
    """Grouped performance cell derived from the canonical evaluation engine.

    ``accuracy`` is directional (UP/DOWN calls only); neutral predictions are
    reported separately. Brier remains a 3-class diagnostic over the same
    evaluated rows. Stored ``is_correct`` flags are never trusted here.
    """
    scored = canonical_score(records, min_sample=MIN_MATURED_N)
    cell = {
        "n": scored["evaluated"],
        "accuracy": scored["accuracy"],
        "directional_n": scored["directional_n"],
        "directional_correct": scored["directional_correct"],
        "directional_incorrect": scored["directional_incorrect"],
        "neutral_n": scored["neutral_n"],
        "neutral_correct": scored["neutral_correct"],
        "reliable": scored["reliable"],
        "minimum_sample": scored["minimum_sample"],
        "confidence_interval": scored["confidence_interval"],
        "pending": scored["pending"],
        "brier": None,
    }
    if cell["n"] >= MIN_MATURED_N:
        cell["brier"] = round(float(np.mean([r["brier"] for r in records])), 4)
    return cell


def calibration_report(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"n": 0, "bins": [], "ece": None}
    bins = []
    ece = 0.0
    for low, high, label in CALIBRATION_BINS:
        cell = [
            r
            for r in records
            if (r["confidence"] >= low)
            and (r["confidence"] < high or (high >= 1.0 and r["confidence"] <= 1.0))
        ]
        if not cell:
            bins.append({"bin": label, "n": 0})
            continue
        mean_conf = float(np.mean([r["confidence"] for r in cell]))
        observed = float(np.mean([r["correct"] for r in cell]))
        gap = observed - mean_conf
        ece += (len(cell) / n) * abs(gap)
        bins.append(
            {
                "bin": label,
                "n": len(cell),
                "mean_confidence": round(mean_conf, 4),
                "observed_accuracy": round(observed, 4),
                "gap": round(gap, 4),
                "reliable": len(cell) >= 5,
            }
        )
    return {"n": n, "bins": bins, "ece": round(float(ece), 4)}


def regime_report(records: list[dict]) -> dict:
    out: dict = {}
    for key, label in (
        ("high_vol_regime", "high_volatility"),
        ("uptrend_regime", "uptrend_50_200"),
    ):
        known = [r for r in records if r.get(key) is not None]
        if not known:
            continue
        on = [r for r in known if float(r[key]) >= 0.5]
        off = [r for r in known if float(r[key]) < 0.5]
        out[label] = {"on": metric_cell(on), "off": metric_cell(off)}
    return out


async def compute_monitor_snapshot(session) -> dict:
    """Compute and persist monitoring snapshot. Returns the snapshot."""
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.mlops import DriftObservation
    from apps.api.models.prediction import ModelVersion, Prediction, PredictionOutcome

    now = datetime.now(UTC)
    snapshot: dict = {
        "observed_at": now.isoformat(),
        "confirmed": {},
        "provisional": {},
        "learning": {},
        "drift": [],
    }

    # ---- confirmed: matured outcomes, last 30d of evaluation time ----
    cutoff = now - timedelta(days=30)
    rows = (
        await session.execute(
            select(PredictionOutcome, Prediction, ModelVersion, Instrument, Exchange, Market)
            .join(Prediction, PredictionOutcome.prediction_id == Prediction.id)
            .join(ModelVersion, Prediction.model_version_id == ModelVersion.id)
            .join(Instrument, Prediction.instrument_id == Instrument.id)
            .join(Exchange, Instrument.exchange_id == Exchange.id)
            .join(Market, Exchange.market_id == Market.id)
            .where(PredictionOutcome.evaluated_at >= cutoff)
        )
    ).all()

    records: list[dict] = []
    seen_bars: set[tuple] = set()
    from services.prediction.bar_identity import bar_day, load_bar_day_index

    bar_index = await load_bar_day_index(session)
    for outcome, pred, version, _instrument, _exchange, market in rows:
        bar_key = (
            pred.instrument_id,
            pred.horizon,
            pred.model_version_id,
            bar_day(bar_index, pred.instrument_id, pred.prediction_timestamp),
        )
        if bar_key in seen_bars:
            continue
        seen_bars.add(bar_key)
        probs = _probabilities(pred)
        actual = normalize_direction(outcome.actual_direction)
        predicted = normalize_direction(pred.predicted_direction)
        snap = pred.features_snapshot or {}
        records.append(
            {
                "correct": normalize_direction(pred.predicted_direction)
                == normalize_direction(outcome.actual_direction),
                "brier": brier_score(probs, actual),
                "log_loss": log_loss(probs, actual),
                "confidence": max(probs.values()),
                "predicted": predicted,
                "actual": actual,
                "version": version.version,
                "market": market.code,
                "high_vol_regime": snap.get("high_vol_regime"),
                "uptrend_regime": snap.get("uptrend_regime"),
                "latency_hours": max(
                    0.0,
                    (
                        as_aware(outcome.evaluated_at) - as_aware(pred.prediction_timestamp)
                    ).total_seconds()
                    / 3600.0,
                ),
                "evaluated_at": outcome.evaluated_at,
            }
        )

    n = len(records)
    confirmed: dict = {"n_matured_30d": n}
    if n > 0:
        overall = canonical_score(records, min_sample=MIN_MATURED_N)
        confirmed["accuracy_30d"] = overall["accuracy"]
        confirmed["directional_accuracy_30d"] = overall["accuracy"]
        confirmed["all_class_accuracy_30d"] = overall["all_class_accuracy"]
        confirmed["directional_n_30d"] = overall["directional_n"]
        confirmed["neutral_predictions_30d"] = overall["neutral_n"]
        confirmed["accuracy_ci_30d"] = overall["confidence_interval"]
        confirmed["accuracy_reliable_30d"] = overall["reliable"]
        confirmed["scoring_policy"] = overall["scoring_policy"]
        confirmed["brier_30d"] = round(float(np.mean([r["brier"] for r in records])), 4)
        confirmed["log_loss_30d"] = round(float(np.mean([r["log_loss"] for r in records])), 4)

        by_market: dict[str, list[dict]] = {}
        by_version: dict[str, list[dict]] = {}
        by_direction: dict[str, list[dict]] = {}
        for r in records:
            by_market.setdefault(r["market"], []).append(r)
            by_version.setdefault(r["version"], []).append(r)
            by_direction.setdefault(r["predicted"], []).append(r)
        confirmed["by_market"] = {k: metric_cell(v) for k, v in sorted(by_market.items())}
        confirmed["by_model_version"] = {
            k: {**metric_cell(v), "calibration": calibration_report(v)}
            for k, v in sorted(by_version.items())
        }
        confirmed["by_predicted_direction"] = {
            k: metric_cell(v) for k, v in sorted(by_direction.items())
        }
        confirmed["by_regime"] = regime_report(records)

        calibration = calibration_report(records)
        confirmed["calibration_30d"] = calibration
        confirmed["ece_30d"] = calibration["ece"]
        confirmed["latency_hours_median"] = round(
            float(np.median([r["latency_hours"] for r in records])), 2
        )

        recent_cutoff = now - timedelta(days=7)
        recent = [r for r in records if as_aware(r["evaluated_at"]) >= recent_cutoff]
        prior = [r for r in records if as_aware(r["evaluated_at"]) < recent_cutoff]
        recent_cell = metric_cell(recent)
        prior_cell = metric_cell(prior)
        confirmed["recent_7d"] = {
            "n": recent_cell["n"],
            "accuracy": recent_cell["accuracy"],
            "prior_23d": {
                "n": prior_cell["n"],
                "accuracy": prior_cell["accuracy"],
            },
            "provisional": not recent_cell["reliable"],
        }
    snapshot["confirmed"] = confirmed

    # ---- provisional: freshness / coverage (not performance evidence) ----
    day_ago = now - timedelta(days=1)
    cov = (
        await session.execute(
            select(func.count(func.distinct(Prediction.instrument_id))).where(
                Prediction.prediction_timestamp >= day_ago
            )
        )
    ).scalar() or 0
    total_inst = (
        await session.execute(
            select(func.count(Instrument.id)).where(Instrument.is_active.is_(True))
        )
    ).scalar() or 0
    pending = (
        await session.execute(
            select(func.count(Prediction.id))
            .select_from(Prediction)
            .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .where(PredictionOutcome.id.is_(None), Prediction.horizon == "1d")
        )
    ).scalar() or 0
    snapshot["provisional"] = {
        "instruments_covered_24h": int(cov),
        "instruments_active": int(total_inst),
        "predictions_pending_outcome": int(pending),
        "coverage_24h": round(cov / total_inst, 4) if total_inst else None,
    }

    # ---- learning-loop state: diagnostic only, never auto-promotion ----
    state = "collecting"
    if n >= MIN_MATURED_N:
        state = "monitoring"
        if confirmed.get("ece_30d") is not None and confirmed["ece_30d"] > ECE_CEILING:
            state = "calibration_review"
    snapshot["learning"] = {
        "state": state,
        "min_matured_n": MIN_MATURED_N,
        "confirmed_only": True,
        "automatic_retraining": False,
        "automatic_promotion": False,
        "next_action": (
            "collect matured outcomes; do not interpret provisional signals as performance"
            if n < MIN_MATURED_N
            else "review calibration/drift; promotion requires a separate OOS experiment and admin approval"
        ),
    }

    # ---- drift: confirmed-only alarms, minimum samples, deduped ----
    alerts: list[dict] = []
    if n >= MIN_MATURED_N:
        checks = [
            ("accuracy_30d", confirmed.get("accuracy_30d"), ACCURACY_FLOOR, "below"),
            ("brier_30d", confirmed.get("brier_30d"), BRIER_CEILING, "above"),
            ("ece_30d", confirmed.get("ece_30d"), ECE_CEILING, "above"),
        ]
        for metric, value, threshold, direction in checks:
            if value is None:
                continue
            tripped = value < threshold if direction == "below" else value > threshold
            if not tripped:
                continue
            open_row = (
                await session.execute(
                    select(DriftObservation).where(
                        DriftObservation.scope == "global",
                        DriftObservation.metric == metric,
                        DriftObservation.acknowledged.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if open_row is None:
                session.add(
                    DriftObservation(
                        scope="global",
                        metric=metric,
                        value=float(value),
                        threshold=float(threshold),
                        observed_at=now,
                        note=f"Confirmed on {n} matured outcomes (30d). Provisional signals excluded.",
                    )
                )
            alerts.append({"metric": metric, "value": value, "threshold": threshold})
    else:
        alerts.append(
            {
                "metric": "sample_size",
                "value": n,
                "threshold": MIN_MATURED_N,
                "note": "provisional only: fewer than 30 matured outcomes",
            }
        )
    await session.commit()
    snapshot["drift"] = alerts
    return snapshot
