"""Candidate artifact persistence: immutable, hashed, manifest-bearing.

Artifacts live under model_artifacts/challengers/<experiment-id>/ (never in
Postgres). The DB records path + SHA; inference hash-verifies before trusting.
Champion artifacts are never written here and never overwritten.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

CHALLENGER_ROOT_CANDIDATES = [
    Path("model_artifacts/challengers"),
    Path("backend/model_artifacts/challengers"),
]


def challenger_root() -> Path:
    for p in CHALLENGER_ROOT_CANDIDATES:
        if p.exists() or p.parent.exists():
            return p
    return CHALLENGER_ROOT_CANDIDATES[0]


def sha_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


async def persist_candidate_artifact(experiment, cfg: dict, panel) -> dict:
    """Refit the winning config on the full fresh window and persist it.

    Uses the same causal row builder (no future rows) with eval_index =
    len(bars) so every row's label resolves in-sample — legitimate for a
    TRAINING artifact (walk-forward OOS numbers, not this fit, are the
    evidence). Fail closed on insufficient rows/classes.
    """
    import numpy as np
    import pandas as pd
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.preprocessing import StandardScaler

    from services.backtesting.backtest_service import BacktestEngine
    from services.ml import recipe
    all_rows: list[list[float]] = []
    all_labels: list[int] = []
    feat_cols: list[str] | None = None
    for symbol, blist in sorted(panel.items()):
        rows, labels, cols, _ = BacktestEngine.build_window_training_rows(
            blist, len(blist), max_train_rows=10_000,
            feature_subset=cfg["feature_subset"],
            market_context=cfg["market_context"],
            panel={s: b for s, b in panel.items()} if cfg["market_context"] else None,
            symbol=symbol if cfg["market_context"] else None,
        )
        if not rows or cols is None:
            continue
        if feat_cols is None:
            feat_cols = cols
        elif cols != feat_cols:
            continue  # schema drift across symbols: skip, never coerce
        all_rows.extend(rows)
        all_labels.extend(labels)
    if not all_rows or feat_cols is None:
        raise ValueError("no training rows for candidate artifact")
    y = np.array(all_labels)
    if len(set(all_labels)) < 2:
        raise ValueError("single-class training window")
    X = pd.DataFrame(all_rows, columns=feat_cols)
    scaler = StandardScaler()
    Xs = pd.DataFrame(scaler.fit_transform(X), columns=feat_cols)
    fitted: dict[str, tuple] = {}
    for name, base in recipe.get_base_models().items():
        m = base.__class__(**base.get_params())
        m.fit(Xs, y)
        cal = None
        if cfg["calibration"] != "none" and len(all_rows) >= recipe.CALIBRATION_MIN_SAMPLES:
            cal = CalibratedClassifierCV(m, method=cfg["calibration"], cv=recipe.CALIBRATION_CV_FOLDS)
            cal.fit(Xs, y)
        fitted[name] = (m, cal)

    out_dir = challenger_root() / experiment.experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)
    import joblib

    model_path = out_dir / "model.pkl"
    joblib.dump(
        {
            "model": fitted["random_forest"][0],
            "scaler": scaler,
            "features": feat_cols,
            "feature_names": feat_cols,
            "calibrator": fitted["random_forest"][1],
            "ensemble": fitted,
            "config": cfg,
        },
        model_path,
    )
    sha = sha_of_file(model_path)
    manifest = {
        "experiment_id": experiment.experiment_id,
        "config": cfg,
        "feature_schema": feat_cols,
        "n_features": len(feat_cols),
        "n_rows": len(all_rows),
        "target": "v1-h1d-0.5pct",
        "horizon": "1d",
        "created_at": datetime.now(UTC).isoformat(),
        "files": {"model.pkl": sha},
        "note": "challenger artifact: shadow evaluation only, never production without approval",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"path": str(model_path), "sha": sha, "manifest": manifest}
