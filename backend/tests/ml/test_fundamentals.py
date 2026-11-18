"""E011 PIT fundamentals: anniversary matching, fail-closed gating, engine wiring.

Pure unit tests on inline fixtures (never the frozen snapshot, never the
network). Filing-date gating is the load-bearing invariant: period-end dates
must never grant availability.
"""

from datetime import UTC, datetime, timedelta

import pytest

from services.ml import fundamentals as F


def _report(filed, end, quarter, year, revenue, ni=10.0):
    return {
        "filedDate": filed, "endDate": end, "form": "10-Q",
        "quarter": quarter, "year": year, "revenue": revenue, "net_income": ni,
    }


def _payload(reports):
    out = {"data": []}
    for r in reports:
        out["data"].append({
            "filedDate": r["filedDate"].strftime("%Y-%m-%d %H:%M:%S"),
            "endDate": r["endDate"], "form": "10-Q",
            "quarter": r["quarter"], "year": r["year"],
            "report": {"ic": [
                {"concept": "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
                 "value": r["revenue"]},
                {"concept": "us-gaap_NetIncomeLoss", "value": r["net_income"]},
            ]},
        })
    return out


def _quarterly_series():
    # 9 quarters across 3 years (Q1-Q3 only per year, mimicking the real
    # omission of Q4 from quarterly files).
    reps = []
    rev = 100.0
    for year in (2019, 2020, 2021):
        for q, me in ((1, "03-28"), (2, "06-27"), (3, "09-26")):
            rev *= 1.05
            reps.append(_report(None, f"{year}-{me}", q, year, rev))
    # fix filed dates properly
    dates = [(2019, 4, 30), (2019, 7, 31), (2019, 10, 30),
             (2020, 4, 30), (2020, 7, 31), (2020, 10, 30),
             (2021, 4, 30), (2021, 7, 30), (2021, 10, 29)]
    for r, (y, m, d) in zip(reps, dates):
        r["filedDate"] = datetime(y, m, d, tzinfo=UTC)
    return reps


def test_extract_skips_reports_without_fileddate():
    reps = _quarterly_series()
    assert len(F.extract_reports(_payload(reps))) == 9
    payload = {"data": [{
        "endDate": "2020-03-28", "form": "10-Q", "quarter": 1, "year": 2020,
        "report": {"ic": [{"concept": "us-gaap_Revenues", "value": 50.0}]},
    }]}
    assert F.extract_reports(payload) == []


def test_yoy_matches_anniversary_not_position():
    # Positional 4-back on Q1-Q3-only data compares mismatched quarters;
    # anniversary matching must recover the true compounding: with Q4 absent,
    # same-quarter-next-year is 3 filings later, i.e. 1.05^3 - 1 ≈ 0.1576.
    entries = F.build_entries(F.extract_reports(_payload(_quarterly_series())))
    full = [e for e in entries if e[3] is not None]
    assert len(full) == 6  # the 6 year-2/3 quarters have an anniversary base
    for e in full:
        assert e[3] == pytest.approx(0.1576, abs=1e-3)


def test_lookup_gates_on_fileddate_not_period():
    entries = F.build_entries(F.extract_reports(_payload(_quarterly_series())))
    # Period Q2'20 ended 2020-06-27 but filed 2020-07-31: unusable July-15.
    assert F.lookup(entries, datetime(2020, 7, 15, tzinfo=UTC))["fund_days_since_filing"] > 70
    # At the exact filing stamp it becomes usable.
    got = F.lookup(entries, datetime(2020, 7, 31, tzinfo=UTC))
    assert got["fund_days_since_filing"] == 0.0


def test_lookup_fail_closed_and_naive_raises():
    assert F.lookup([], datetime(2021, 1, 1, tzinfo=UTC)) is None
    entries = F.build_entries(F.extract_reports(_payload(_quarterly_series())))
    with pytest.raises(ValueError):
        F.lookup(entries, datetime(2021, 1, 1))


def test_revenue_concept_fallback():
    payload = {"data": [{
        "filedDate": "2021-04-30 00:00:00", "endDate": "2021-03-28",
        "form": "10-Q", "quarter": 1, "year": 2021,
        "report": {"ic": [{"concept": "us-gaap_SalesRevenueNet", "value": 77.0},
                          {"concept": "us-gaap_NetIncomeLoss", "value": 7.0}]},
    }]}
    reps = F.extract_reports(payload)
    assert reps[0]["revenue"] == 77.0


def _bars(n=400):
    from datetime import timedelta
    from tests.ml.test_feature_subset import _Bar

    out = []
    px = 100.0
    for i in range(n):
        phase = (i // 5) % 4
        step = 0.012 if phase == 0 else (-0.011 if phase == 2 else 0.001)
        px *= 1.0 + step
        out.append(_Bar(
            datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i), px, i))
    return out


def _panel():
    base = datetime(2023, 1, 1, tzinfo=UTC)
    return {"SYM": [(base + timedelta(days=90 * i), 100.0 + i, 10.0 + i,
                     0.05, 0.1) for i in range(1, 9)]}


def test_engine_appends_three_fund_columns():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    for b in bars:
        b.timestamp = b.timestamp.replace(year=2024)
    rows, labels, cols, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, fundamentals=True,
        fund_panel=_panel(), symbol="SYM",
    )
    assert cols[-3:] == list(F.FEATURE_NAMES)
    assert len(rows) > 0 and all(len(r) == len(cols) for r in rows)


def test_engine_fund_fail_closed_unknown_symbol():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    rows, _, _, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, fundamentals=True,
        fund_panel=_panel(), symbol="NOFILINGS",
    )
    assert rows == []


def test_engine_combo_and_missing_panel_raise():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    with pytest.raises(ValueError):
        BacktestEngine.build_window_training_rows(
            bars, 380, max_train_rows=50, market_context=True, fundamentals=True,
            panel={}, fund_panel=_panel(), symbol="SYM")
    with pytest.raises(ValueError):
        BacktestEngine.build_window_training_rows(
            bars, 380, max_train_rows=50, fundamentals=True, symbol="SYM")
    with pytest.raises(ValueError):
        BacktestEngine.generate_causal_predictions(
            bars, bars[380].timestamp, bars[-1].timestamp,
            fundamentals=True, symbol="SYM")


def test_engine_methodology_records_fundamentals():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    _, method = BacktestEngine.generate_causal_predictions(
        bars, bars[380].timestamp, bars[-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5, max_train_rows=100,
        calibration="none", fundamentals=True, fund_panel=_panel(), symbol="SYM",
    )
    assert method["fundamentals"] is True


def test_engine_default_has_no_fundamentals():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    _, method = BacktestEngine.generate_causal_predictions(
        bars, bars[380].timestamp, bars[-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5, max_train_rows=100,
        calibration="none",
    )
    assert method["fundamentals"] is False


def test_event_lookup_boundaries():
    base = datetime(2024, 5, 1, tzinfo=UTC)
    entries = [(base, 100.0, 10.0, 0.05, 0.1)]
    assert F.event_lookup(entries, base) == {"fund_event_5d": 1.0}
    assert F.event_lookup(entries, base + timedelta(days=5)) == {"fund_event_5d": 1.0}
    assert F.event_lookup(entries, base + timedelta(days=6)) == {"fund_event_5d": 0.0}
    # Future filing never leaks: same period, later stamp is unusable.
    assert F.event_lookup(entries, base - timedelta(seconds=1)) is None
    assert F.event_lookup([], base) is None
    with pytest.raises(ValueError):
        F.event_lookup(entries, datetime(2024, 5, 1))
    with pytest.raises(ValueError):
        F.event_lookup(entries, base, window_days=-1)


def test_event_lookup_needs_only_fileddate():
    # Marker works even when computed features are absent (partial filing).
    base = datetime(2024, 5, 1, tzinfo=UTC)
    entries = [(base, None, None, None, None)]
    assert F.event_lookup(entries, base + timedelta(days=2)) == {"fund_event_5d": 1.0}


def test_engine_event_appends_single_binary_column():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    rows, _, cols, _ = BacktestEngine.build_window_training_rows(
        bars, 380, max_train_rows=50, event_only=True,
        fund_panel=_panel(), symbol="SYM",
    )
    assert cols[-1:] == list(F.EVENT_FEATURE_NAMES)
    assert len(rows) > 0
    for r in rows:
        assert r[-1] in (0.0, 1.0)


def test_engine_event_combos_raise_and_methodology():
    from services.backtesting.backtest_service import BacktestEngine

    bars = _bars()
    with pytest.raises(ValueError):
        BacktestEngine.build_window_training_rows(
            bars, 380, max_train_rows=50, event_only=True, fundamentals=True,
            fund_panel=_panel(), symbol="SYM")
    with pytest.raises(ValueError):
        BacktestEngine.generate_causal_predictions(
            bars, bars[380].timestamp, bars[-1].timestamp,
            event_only=True, symbol="SYM")
    _, method = BacktestEngine.generate_causal_predictions(
        bars, bars[380].timestamp, bars[-1].timestamp,
        retrain_every_n_eval=4, eval_step_bars=5, max_train_rows=100,
        calibration="none", event_only=True, fund_panel=_panel(), symbol="SYM",
    )
    assert method["event_only"] is True
    assert method["fundamentals"] is False
