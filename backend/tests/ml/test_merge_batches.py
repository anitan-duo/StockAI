"""Merger spec-awareness: binary batches must not be scored with 3-class
column positions (once reported Brier 0.34 / log-loss 17.9 for genuinely
~0.27/0.73 data by comparing UP labels against a zero column)."""

import importlib.util
import json
from pathlib import Path


def _load_merger():
    path = Path(__file__).resolve().parents[2] / "scripts" / "merge_dev_batches.py"
    spec = importlib.util.spec_from_file_location("merge_dev_batches", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _batch(path, spec, recs):
    path.write_text(json.dumps({
        "eval_config": {"target_spec": spec},
        "eval_records": recs,
        "per_symbol": {},
        "baselines": {"momentum_directional_hits": 0, "momentum_denominator": 0},
    }))


def _rec(symbol, ts, true, pred, down, neutral, up):
    return {"symbol": symbol, "market": "US", "timestamp": ts, "true": true,
            "pred": pred, "down": down, "neutral": neutral, "up": up}


def test_binary_merge_uses_two_columns(tmp_path, monkeypatch, capsys):
    mod = _load_merger()
    monkeypatch.setattr(mod, "D", tmp_path)
    recs = (
        [_rec("A", f"2024-01-{d:02d}T00:00:00+00:00", 1, 1, 0.3, 0.0, 0.7) for d in range(1, 11)]
        + [_rec("A", f"2024-02-{d:02d}T00:00:00+00:00", 0, 0, 0.7, 0.0, 0.3) for d in range(1, 11)]
    )
    for i in (1, 2, 3):
        _batch(tmp_path / f"t_b{i}.json", "binary-1d", recs)
    monkeypatch.setattr("sys.argv", ["x", "--prefix", "t", "--out", "t_merged.json"])
    mod.main()
    out = json.loads((tmp_path / "t_merged.json").read_text())
    assert out["target_spec"] == "binary-1d"
    assert out["n_labeled"] == 60
    assert out["accuracy"] == 1.0
    # Sane probability quality for perfect confident-ish forecasts (would be
    # ~0.34/17.9 under the old misaligned mapping).
    assert out["brier"] < 0.15
    assert out["log_loss"] < 0.5


def test_mixed_specs_refuse_to_merge(tmp_path, monkeypatch):
    import pytest

    mod = _load_merger()
    monkeypatch.setattr(mod, "D", tmp_path)
    recs = [_rec("A", "2024-01-01T00:00:00+00:00", 1, 1, 0.3, 0.0, 0.7)]
    _batch(tmp_path / "m_b1.json", "binary-1d", recs)
    _batch(tmp_path / "m_b2.json", "direction3-1d", recs)
    _batch(tmp_path / "m_b3.json", "binary-1d", recs)
    monkeypatch.setattr("sys.argv", ["x", "--prefix", "m", "--out", "m_merged.json"])
    with pytest.raises(SystemExit):
        mod.main()
