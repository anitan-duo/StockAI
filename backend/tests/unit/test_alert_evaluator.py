"""Unit: alert evaluator semantics (no DB)."""

from decimal import Decimal

from services.alerts.evaluator import evaluate


class _Snap:
    def __init__(self, price=150, prev=149, change_pct=1.0, volume=1000):
        self.price = Decimal(str(price))
        self.previous_close = Decimal(str(prev))
        self.change_percent = Decimal(str(change_pct))
        self.volume = volume


class _Pred:
    def __init__(self, up=0.5, neu=0.2, down=0.3, ret=1.0, conf=70, rsi=65):
        self.up_probability = Decimal(str(up))
        self.neutral_probability = Decimal(str(neu))
        self.down_probability = Decimal(str(down))
        self.expected_return = Decimal(str(ret))
        self.confidence = conf
        self.features_snapshot = {"rsi_14": rsi}


def test_price_thresholds():
    assert evaluate("price_above", "gt", Decimal("140"), _Snap(), None).fires is True
    assert evaluate("price_above", "gt", Decimal("160"), _Snap(), None).fires is False
    assert evaluate("price_below", "lt", Decimal("160"), _Snap(), None).fires is True
    assert evaluate("price_above", "gte", Decimal("150"), _Snap(), None).fires is True


def test_crosses_uses_prior_close():
    assert evaluate("price_above", "crosses_above", Decimal("149.5"), _Snap(price=150, prev=149), None).fires is True
    assert evaluate("price_above", "crosses_above", Decimal("149.5"), _Snap(price=150, prev=151), None).fires is False
    assert evaluate("price_below", "crosses_below", Decimal("149.5"), _Snap(price=150, prev=149), None).fires is False


def test_change_volume_prediction_fields():
    assert evaluate("price_change_pct", "gt", Decimal("0.5"), _Snap(), None).fires is True
    assert evaluate("volume_above", "gt", Decimal("500"), _Snap(), None).fires is True
    assert evaluate("prediction_probability", "gt", Decimal("0.4"), None, _Pred()).fires is True
    assert evaluate("expected_return", "gt", Decimal("0.5"), None, _Pred()).fires is True
    assert evaluate("confidence", "gte", Decimal("60"), None, _Pred()).fires is True
    assert evaluate("rsi_above", "gt", Decimal("60"), None, _Pred()).fires is True
    assert evaluate("rsi_below", "lt", Decimal("60"), None, _Pred()).fires is False


def test_missing_data_never_fires():
    assert evaluate("price_above", "gt", Decimal("1"), None, None).unevaluable is True
    assert evaluate("prediction_probability", "gt", Decimal("0.1"), None, None).unevaluable is True
    r = evaluate("rsi_above", "gt", Decimal("10"), None, _Pred(rsi=None))
    assert r.fires is False and r.unevaluable is True
