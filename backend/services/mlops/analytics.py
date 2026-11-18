"""Read-only performance analytics for the analyst workspace.

Uses resolved PredictionOutcome rows only. No provisional or imagined metrics.
This service never retrains or promotes anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select

from services.mlops.monitor import (
    as_aware,
    brier_score,
    calibration_report,
    log_loss,
    metric_cell,
    normalize_direction,
    regime_report,
)
from services.prediction.evaluation import score_records as canonical_score

MAX_DAYS = 365
MIN_SAMPLE = 30


def _probabilities(pred) -> dict[str, float]:
    return {
        "down": float(pred.down_probability),
        "neutral": float(pred.neutral_probability),
        "up": float(pred.up_probability),
    }


async def compute_performance_analytics(
    session,
    days: int = 90,
    symbol: str | None = None,
    exchange: str | None = None,
    recent_limit: int = 25,
) -> dict:
    from apps.api.models.market import Exchange, Instrument, Market
    from apps.api.models.prediction import ModelVersion, Prediction, PredictionOutcome

    days = max(1, min(int(days), MAX_DAYS))
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    filters = [PredictionOutcome.evaluated_at >= cutoff]
    if symbol:
        filters.append(Instrument.symbol == symbol.upper())
    if exchange:
        filters.append(Exchange.code == exchange.upper())

    query = (
        select(PredictionOutcome, Prediction, ModelVersion, Instrument, Exchange, Market)
        .join(Prediction, PredictionOutcome.prediction_id == Prediction.id)
        .join(ModelVersion, Prediction.model_version_id == ModelVersion.id)
        .join(Instrument, Prediction.instrument_id == Instrument.id)
        .join(Exchange, Instrument.exchange_id == Exchange.id)
        .join(Market, Exchange.market_id == Market.id)
        .where(*filters)
        .order_by(PredictionOutcome.evaluated_at.desc())
    )
    rows = (await session.execute(query)).all()

    records = []
    symbols: dict[str, list[dict]] = {}
    directions: dict[str, list[dict]] = {}
    versions: dict[str, list[dict]] = {}
    markets: dict[str, list[dict]] = {}
    seen_bars: set[tuple] = set()
    from services.prediction.bar_identity import bar_day, load_bar_day_index

    bar_index = await load_bar_day_index(session)
    for outcome, pred, version, instrument, ex, market in rows:
        # Legacy duplicate rows for the same bar are counted once. A new
        # model version on the same bar is a distinct, attributable forecast.
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
        record = {
            "symbol": instrument.symbol,
            "exchange": ex.code,
            "market": market.code,
            "correct": normalize_direction(pred.predicted_direction)
            == normalize_direction(outcome.actual_direction),
            "brier": brier_score(probs, actual),
            "log_loss": log_loss(probs, actual),
            "confidence": max(probs.values()),
            "predicted": predicted,
            "actual": actual,
            "version": version.version,
            "high_vol_regime": snap.get("high_vol_regime"),
            "uptrend_regime": snap.get("uptrend_regime"),
            "latency_hours": max(
                0.0,
                (
                    as_aware(outcome.evaluated_at) - as_aware(pred.prediction_timestamp)
                ).total_seconds()
                / 3600.0,
            ),
        }
        records.append(record)
        symbols.setdefault(f"{instrument.symbol}:{ex.code}", []).append(record)
        directions.setdefault(predicted, []).append(record)
        versions.setdefault(version.version, []).append(record)
        markets.setdefault(market.code, []).append(record)

    n = len(records)
    scored = canonical_score(records, min_sample=MIN_SAMPLE)
    summary: dict = {
        "n": n,
        "evaluated": scored["evaluated"],
        "pending": scored["pending"],
        "invalid": scored["invalid"],
        "expired": scored["expired"],
        "minimum_sample": MIN_SAMPLE,
        "sufficient_sample": n >= MIN_SAMPLE,
        "reliable": scored["reliable"],
        "directional_n": scored["directional_n"],
        "directional_correct": scored["directional_correct"],
        "directional_incorrect": scored["directional_incorrect"],
        "neutral_n": scored["neutral_n"],
        "neutral_correct": scored["neutral_correct"],
        "coverage": scored["coverage"],
        "confidence_interval": scored["confidence_interval"],
        "all_class_accuracy": scored["all_class_accuracy"],
        "scoring_policy": scored["scoring_policy"],
        "coverage_note": (
            "Headline accuracy is directional (UP/DOWN calls only). Neutral "
            "predictions are reported separately. Resolved outcomes only; "
            "pending rows are never counted as incorrect."
        ),
    }
    if n >= MIN_SAMPLE:
        summary.update(
            {
                "accuracy": scored["accuracy"],
                "brier": round(float(np.mean([r["brier"] for r in records])), 4),
                "log_loss": round(float(np.mean([r["log_loss"] for r in records])), 4),
                "latency_hours_median": round(
                    float(np.median([r["latency_hours"] for r in records])), 2
                ),
            }
        )
    else:
        summary.update(
            {
                "accuracy": None,
                "brier": None,
                "log_loss": None,
                "coverage_note": (
                    f"Insufficient sample size (n={n} < {MIN_SAMPLE}); "
                    "accuracy is withheld. Neutral predictions are never "
                    "counted as directional wins."
                ),
            }
        )
    calibration = calibration_report(records)
    summary["ece"] = calibration.get("ece") if n >= MIN_SAMPLE else None

    by_symbol = {k: metric_cell(v) for k, v in sorted(symbols.items(), key=lambda kv: -len(kv[1]))}
    by_symbol_top = dict(list(by_symbol.items())[:50])

    # Pending / coverage snapshot for the same scope (never mixed into accuracy).
    pending_filters = [
        PredictionOutcome.id.is_(None),
        Prediction.horizon == "1d",
        Prediction.prediction_timestamp >= cutoff,
    ]
    if symbol:
        pending_filters.append(Instrument.symbol == symbol.upper())
    if exchange:
        pending_filters.append(Exchange.code == exchange.upper())
    pending = (
        await session.execute(
            select(func.count(Prediction.id))
            .select_from(Prediction)
            .join(Instrument, Prediction.instrument_id == Instrument.id)
            .join(Exchange, Instrument.exchange_id == Exchange.id)
            .outerjoin(PredictionOutcome, PredictionOutcome.prediction_id == Prediction.id)
            .where(*pending_filters)
        )
    ).scalar() or 0

    recent = [
        {
            "symbol": r["symbol"],
            "exchange": r["exchange"],
            "predicted": r["predicted"],
            "actual": r["actual"],
            "correct": r["predicted"] == r["actual"],
            "directional": r["predicted"] in {"up", "down"},
            "counted_in_accuracy": r["predicted"] in {"up", "down"},
            "confidence": round(r["confidence"], 4),
            "brier": round(r["brier"], 4),
            "evaluated_at": rows[i][0].evaluated_at.isoformat(),
            "version": r["version"],
        }
        for i, r in enumerate(records[:recent_limit])
    ]

    return {
        "generated_at": now.isoformat(),
        "scope": {
            "days": days,
            "symbol": symbol.upper() if symbol else None,
            "exchange": exchange.upper() if exchange else None,
            "since": cutoff.isoformat(),
            "confirmed_only": True,
        },
        "summary": summary,
        "calibration": calibration,
        "by_symbol": by_symbol_top,
        "by_direction": {k: metric_cell(v) for k, v in sorted(directions.items())},
        "by_version": {k: metric_cell(v) for k, v in sorted(versions.items())},
        "by_market": {k: metric_cell(v) for k, v in sorted(markets.items())},
        "by_regime": regime_report(records),
        "pending_outcomes": int(pending),
        "recent_outcomes": recent,
        "caveats": [
            "Resolved outcomes only; pending predictions are excluded from performance.",
            f"Small samples: cells below {MIN_SAMPLE} are not statistically reliable.",
            "No causal claim: regime cells are observational, not randomized.",
            "Analytics is read-only; it never retrains or promotes a model.",
        ],
    }
