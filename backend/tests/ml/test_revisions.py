"""Tests for P18-E025 analyst-revision features (always-present path)."""

from datetime import UTC, datetime

from services.ml.revisions import (
    CAP_DAYS,
    FEATURE_NAMES,
    build_entries,
    grade_score,
    lookup,
)


def _dt(s):
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def _row(date, action="", frm="", to=""):
    return {"symbol": "X", "date": date, "action": action,
            "from_grade": frm, "to_grade": to}


def test_grade_score_mapping():
    assert grade_score("Strong Buy") == 5.0
    assert grade_score("Overweight") == 4.0
    assert grade_score("Hold") == 3.0
    assert grade_score("Sell") == 2.0
    assert grade_score("") is None
    assert grade_score("WeirdGrade") is None


def test_sentinel_before_first_event():
    entries = build_entries([_row("2024-02-01", to="Buy", frm="Hold")])
    f = lookup(entries, _dt("2023-12-31"))
    assert set(f) == set(FEATURE_NAMES)
    assert f["rev_days_since"] == CAP_DAYS
    assert f["rev_last_delta"] == 0.0
    assert f["rev_net_63"] == 0.0
    assert f["rev_count_63"] == 0.0
    assert f["rev_up_share_63"] == 0.0


def test_pit_gate_and_delta_from_grades():
    entries = build_entries([_row("2024-02-01", action="up", frm="Hold", to="Buy")])
    before = lookup(entries, _dt("2024-01-31"))
    on = lookup(entries, _dt("2024-02-01"))
    assert before["rev_count_63"] == 0.0
    assert on["rev_days_since"] == 0.0
    assert on["rev_last_delta"] == 1.0  # Buy(4) - Hold(3)
    assert on["rev_count_63"] == 1.0
    assert on["rev_up_share_63"] == 1.0


def test_delta_falls_back_to_action_when_grades_unknown():
    entries = build_entries([_row("2024-02-01", action="down", frm="", to="")])
    f = lookup(entries, _dt("2024-03-01"))
    assert f["rev_last_delta"] == -1.0
    assert f["rev_net_63"] == -1.0


def test_window_aggregation_and_decay():
    entries = build_entries([
        _row("2024-01-10", action="up"),
        _row("2024-02-01", action="down"),
        _row("2024-06-01", action="up"),
    ])
    f = lookup(entries, _dt("2024-03-01"))
    assert f["rev_count_63"] == 2.0
    assert f["rev_net_63"] == 0.0  # +1 -1
    assert f["rev_up_share_63"] == 0.5
    g = lookup(entries, _dt("2024-06-10"))  # only the 2024-06-01 event in window
    assert g["rev_count_63"] == 1.0
    assert g["rev_up_share_63"] == 1.0


def test_build_entries_skips_bad_dates_and_sorts():
    rows = [_row("bad", action="up"), _row("2024-05-01", action="up"),
            _row("2024-02-01", action="down")]
    e = build_entries(rows)
    assert [d.month for d, _ in e] == [2, 5]
    assert [m for _d, m in e] == [-1.0, 1.0]
