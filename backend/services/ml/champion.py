"""Champion resolution: deterministic, hash-verified production pointer.

- The current champion is the single `model_champions` row with
  `superseded_at IS NULL` (partial unique index enforces this).
- Before any artifact bytes are trusted, their SHA-256 must equal the
  recorded `artifact_sha` (fail closed on mismatch or tampering).
- With no champion row (fresh database), the pinned v1.0 baseline hash is
  the only acceptable fallback — never an arbitrary newer file.
"""

import hashlib
from pathlib import Path

# Frozen v1.0 baseline identity (Phase 3/5/6 evidence; production-guard test).
PINNED_V10_SHA_PREFIX = "sha256:cafe9216074afd5b"

# Canonical search order for the v1.0 artifact (mirrors inference fallback).
V10_CANDIDATE_PATHS = [
    Path("model_artifacts/real/ensemble/v1.0/model.pkl"),
    Path("backend/model_artifacts/real/ensemble/v1.0/model.pkl"),
]


class NoChampionError(Exception):
    """No verifiable champion artifact is available."""


def sha_of(path: Path) -> str:
    """SHA-256 of an artifact file (streamed, no full read into RAM)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


async def resolve_champion(session) -> dict:
    """Resolve the current champion: version id + expected artifact SHA.

    Returns {"model_version_id": UUID|None, "artifact_sha": str,
    "sha_is_prefix": bool}. With no champion row (fresh database before
    seeding), falls back to the pinned v1.0 prefix — the file itself is
    still hash-verified by the caller before any bytes are trusted.
    """
    from sqlalchemy import select

    from apps.api.models.mlops import ModelChampion

    row = (
        await session.execute(
            select(ModelChampion).where(ModelChampion.superseded_at.is_(None))
        )
    ).scalar_one_or_none()
    if row is not None:
        return {
            "model_version_id": row.model_version_id,
            "artifact_sha": row.artifact_sha,
            "sha_is_prefix": False,
        }
    return {
        "model_version_id": None,
        "artifact_sha": PINNED_V10_SHA_PREFIX,
        "sha_is_prefix": True,
    }


def sha_accepted(actual: str, expected: str, prefix_ok: bool) -> bool:
    """True when the artifact hash satisfies the champion record."""
    if prefix_ok:
        return actual.startswith(expected)
    return actual == expected


async def resolve_champion_artifact(session) -> dict:
    """Resolve WHAT to load for production inference.

    Returns one of:
    - {"kind": "pinned-v1.0", "model_version_id": <db id or None>,
       "artifact_sha": <pinned prefix>, "sha_is_prefix": True}
    - {"kind": "experiment", "model_version_id": ..., "artifact_sha": ...,
       "sha_is_prefix": False, "artifact_path": ...}
    The experiment artifact path comes from the approving promotion's
    experiment record (hash-verified by the caller before trusting bytes).
    """
    from sqlalchemy import desc, select

    from apps.api.models.mlops import ModelChampion, ModelPromotion

    row = (
        await session.execute(
            select(ModelChampion).where(ModelChampion.superseded_at.is_(None))
        )
    ).scalar_one_or_none()
    if row is None:
        return {
            "kind": "pinned-v1.0",
            "model_version_id": None,
            "artifact_sha": PINNED_V10_SHA_PREFIX,
            "sha_is_prefix": True,
        }
    promo = (
        await session.execute(
            select(ModelPromotion)
            .where(ModelPromotion.to_version_id == row.model_version_id)
            .order_by(desc(ModelPromotion.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    exp_path = None
    if promo is not None and promo.experiment_id is not None:
        from apps.api.models.mlops import Experiment

        exp = await session.get(Experiment, promo.experiment_id)
        if exp is not None:
            exp_path = exp.artifact_path
    if exp_path:
        return {
            "kind": "experiment",
            "model_version_id": row.model_version_id,
            "artifact_sha": row.artifact_sha,
            "sha_is_prefix": False,
            "artifact_path": exp_path,
        }
    # Seeded v1.0 champion (no promotion row): pinned filesystem artifact.
    return {
        "kind": "pinned-v1.0",
        "model_version_id": row.model_version_id,
        "artifact_sha": row.artifact_sha,
        "sha_is_prefix": False,
    }
