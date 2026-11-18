"""Pure alert-condition evaluator (no DB, no I/O).

Semantics (also documented in docs/production/PRODUCTION_READINESS.md):
- price_above/below: latest price vs target_value (crosses_* use previous_close).
- price_change_pct: snapshot change_percent vs target_value.
- volume_above: snapshot volume vs target_value.
- prediction_probability: latest prediction's max class probability vs target.
- expected_return / confidence: latest prediction fields vs target.
- rsi_above/below: RSI-14 from latest prediction features_snapshot; if absent
  the alert is UNEVALUABLE (never fires on missing data).
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class EvalResult:
    fires: bool
    value: Decimal | None
    message: str
    unevaluable: bool = False


def _cmp(value: Decimal, condition: str, target: Decimal) -> bool:
    if condition == "gt":
        return value > target
    if condition == "lt":
        return value < target
    if condition == "gte":
        return value >= target
    if condition == "lte":
        return value <= target
    if condition == "eq":
        return value == target
    raise ValueError(f"Unsupported condition for comparison: {condition}")


def evaluate(
    alert_type: str,
    condition: str,
    target_value: Decimal,
    snapshot: Any | None,
    prediction: Any | None,
) -> EvalResult:
    """Evaluate one alert. Returns fires=False (never raises for data gaps)."""
    target = Decimal(str(target_value))
    snap_price = lambda: Decimal(str(snapshot.price)) if snapshot else None  # noqa: E731

    if alert_type in ("price_above", "price_below"):
        price = snap_price()
        if price is None:
            return EvalResult(False, None, "no market snapshot", True)
        if condition in ("crosses_above", "crosses_below"):
            prior = Decimal(str(snapshot.previous_close)) if snapshot.previous_close else None
            if prior is None:
                return EvalResult(False, price, "no prior close", True)
            fires = (prior <= target < price) if condition == "crosses_above" else (prior >= target > price)
            return EvalResult(fires, price, f"price {price} vs {target}")
        return EvalResult(_cmp(price, condition, target), price, f"price {price} vs {target}")

    if alert_type == "price_change_pct":
        if snapshot is None or snapshot.change_percent is None:
            return EvalResult(False, None, "no change data", True)
        pct = Decimal(str(snapshot.change_percent))
        return EvalResult(_cmp(pct, condition, target), pct, f"change {pct}% vs {target}%")

    if alert_type == "volume_above":
        if snapshot is None or snapshot.volume is None:
            return EvalResult(False, None, "no volume data", True)
        vol = Decimal(str(snapshot.volume))
        return EvalResult(_cmp(vol, condition, target), vol, f"volume {vol} vs {target}")

    if prediction is None:
        return EvalResult(False, None, f"{alert_type}: no prediction", True)
    if alert_type == "prediction_probability":
        probs = [Decimal(str(prediction.up_probability)), Decimal(str(prediction.neutral_probability)), Decimal(str(prediction.down_probability))]
        top = max(probs)
        return EvalResult(_cmp(top, condition, target), top, f"top prob {top} vs {target}")
    if alert_type == "expected_return":
        ret = Decimal(str(prediction.expected_return))
        return EvalResult(_cmp(ret, condition, target), ret, f"expected return {ret} vs {target}")
    if alert_type == "confidence":
        conf = Decimal(str(prediction.confidence))
        return EvalResult(_cmp(conf, condition, target), conf, f"confidence {conf} vs {target}")
    if alert_type in ("rsi_above", "rsi_below"):
        snap = prediction.features_snapshot or {}
        rsi = snap.get("rsi_14")
        if rsi is None:
            return EvalResult(False, None, "no RSI in features", True)
        val = Decimal(str(rsi))
        return EvalResult(_cmp(val, condition, target), val, f"RSI {val} vs {target}")
    raise ValueError(f"Unknown alert type: {alert_type}")
