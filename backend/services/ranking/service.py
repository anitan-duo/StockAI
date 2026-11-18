"""Cross-sectional ranking inference, persistence and outcome resolution.

The served objective is relative: which eligible instruments are expected to
outperform the same-market cross-sectional median over the requested horizon.
Scores are rank-only model scores (P(relative label=1)), not calibrated
absolute probabilities of a stock rising.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import joblib
import numpy as np
from scipy.stats import spearmanr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.market import Exchange, Instrument, Market
from apps.api.models.price import PriceBar
from apps.api.models.ranking import RankingEntry, RankingOutcome, RankingSnapshot
from services.ingestion.canonical_days import canonical_session_date
from services.ml.crosssec_ranking import (
    MIN_ELIGIBLE_SYMBOLS,
    RANKING_OBJECTIVE,
    predict_outperformance,
    score_cross_section,
)

HORIZON_DAYS = {"1d": 1, "5d": 5, "10d": 10}
HORIZON_LABELS = {v: k for k, v in HORIZON_DAYS.items()}
MIN_MARKET_UNIVERSE = 3
MIN_RELIABLE_OUTCOMES = 30
ABOVE_MEDIAN_SCORE = 0.5
ARTIFACT_VERSION = "ranking-v1"


class RankingError(Exception):
    status_code = 503
    code = "RANKING_UNAVAILABLE"

    def __init__(self, message: str, **detail: Any):
        super().__init__(message)
        self.detail = {"status": self.code, "reason": message, **detail}


class RankingModelUnavailableError(RankingError):
    code = "RANKING_MODEL_UNAVAILABLE"


class InsufficientUniverseError(RankingError):
    code = "INSUFFICIENT_UNIVERSE"
    status_code = 422


@dataclass
class _UniverseRow:
    instrument_id: UUID
    symbol: str
    exchange: str
    market: str
    timezone: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _artifact_candidates(horizon: int) -> list[Path]:
    rel = Path("model_artifacts") / "ranking" / "v1" / f"h{horizon}" / "model.pkl"
    root = _repo_root()
    return [
        root / rel,
        root / "backend" / rel,
        Path.cwd() / rel,
    ]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_ranking_artifact(horizon: int) -> tuple[dict[str, Any], str, Path]:
    """Load an artifact and verify its manifest hash when present."""
    errors = []
    for path in _artifact_candidates(horizon):
        if not path.exists():
            continue
        digest = _sha256(path)
        manifest_path = path.parent / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            expected = manifest.get("artifact_sha256")
            if expected and expected != digest:
                errors.append(f"{path}: sha mismatch")
                continue
        artifact = joblib.load(path)
        if artifact.get("horizon") != horizon:
            errors.append(f"{path}: horizon mismatch")
            continue
        if artifact.get("objective") != RANKING_OBJECTIVE:
            errors.append(f"{path}: objective mismatch")
            continue
        return artifact, digest, path
    detail = "; ".join(errors) if errors else "no artifact found"
    raise RankingModelUnavailableError(
        f"ranking model for {HORIZON_LABELS.get(horizon, horizon)} is unavailable ({detail})"
    )


class RankingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _universe(self) -> list[_UniverseRow]:
        rows = (
            await self.session.execute(
                select(Instrument, Exchange, Market)
                .join(Exchange, Instrument.exchange_id == Exchange.id)
                .join(Market, Exchange.market_id == Market.id)
                .where(Instrument.is_active.is_(True))
            )
        ).all()
        return [
            _UniverseRow(
                instrument_id=i.id,
                symbol=i.symbol,
                exchange=e.code,
                market=m.code,
                timezone=e.timezone,
            )
            for i, e, m in rows
        ]

    async def _bars_for(
        self, universe: list[_UniverseRow], limit: int = 400
    ) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for row in universe:
            key = f"{row.symbol}@{row.exchange}"
            bars = (
                await self.session.execute(
                    select(PriceBar)
                    .where(
                        PriceBar.instrument_id == row.instrument_id,
                        PriceBar.timeframe == "1d",
                    )
                    .order_by(PriceBar.timestamp.desc())
                    .limit(limit)
                )
            ).scalars().all()
            by_day: dict[date, PriceBar] = {}
            for bar in bars:
                day = bar.session_day or canonical_session_date(bar.timestamp, row.timezone)
                current = by_day.get(day)
                if current is None or bar.timestamp > current.timestamp:
                    by_day[day] = bar
            out[key] = [
                {
                    "date": day,
                    "timestamp": by_day[day].timestamp,
                    "open": float(by_day[day].open),
                    "high": float(by_day[day].high),
                    "low": float(by_day[day].low),
                    "close": float(by_day[day].close),
                    "volume": float(by_day[day].volume),
                }
                for day in sorted(by_day)
            ]
        return out

    def _select_as_of(
        self,
        bars: dict[str, list[dict[str, Any]]],
        markets: dict[str, str],
        market: str | None,
    ) -> date:
        counts: Counter[date] = Counter()
        market_counts: Counter[date] = Counter()
        for key, rows in bars.items():
            for b in rows:
                d = b["date"]
                counts[d] += 1
                if market is None or markets.get(key) == market:
                    market_counts[d] += 1
        eligible_dates = [
            d
            for d in counts
            if counts[d] >= MIN_ELIGIBLE_SYMBOLS
            and (market is None or market_counts[d] >= MIN_MARKET_UNIVERSE)
        ]
        if not eligible_dates:
            raise InsufficientUniverseError(
                "not enough instruments with a common trading session to rank",
                minimum=MIN_ELIGIBLE_SYMBOLS,
                market_minimum=MIN_MARKET_UNIVERSE,
                market=market,
            )
        return max(eligible_dates)

    async def rank(
        self,
        market: str | None = None,
        horizon: str = "1d",
        as_of: date | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if horizon not in HORIZON_DAYS:
            raise InsufficientUniverseError(
                f"unsupported ranking horizon '{horizon}'",
                supported=sorted(HORIZON_DAYS),
            )
        market_code = market.upper() if market else None
        h = HORIZON_DAYS[horizon]
        artifact, digest, artifact_path = load_ranking_artifact(h)

        universe = await self._universe()
        if not universe:
            raise InsufficientUniverseError("no active instruments")
        bars = await self._bars_for(universe)
        markets = {f"{r.symbol}@{r.exchange}": r.market for r in universe}
        chosen_as_of = as_of or self._select_as_of(bars, markets, market_code)
        if as_of is not None:
            for key in bars:
                bars[key] = [b for b in bars[key] if b["date"] <= as_of]

        eligible, feature_matrix, excluded = score_cross_section(
            bars, markets, chosen_as_of, artifact["feature_names"], h
        )
        if len(eligible) < MIN_ELIGIBLE_SYMBOLS:
            raise InsufficientUniverseError(
                "not enough instruments have complete features on the as-of session",
                as_of=chosen_as_of.isoformat(),
                eligible=len(eligible),
                excluded=dict(Counter(excluded.values())),
            )
        scores = predict_outperformance(artifact, feature_matrix)
        by_key = {f"{r.symbol}@{r.exchange}": r for r in universe}

        scored = []
        for i, (key, score) in enumerate(zip(eligible, scores, strict=True)):
            row = by_key[key]
            scored.append(
                {
                    "instrument_id": row.instrument_id,
                    "symbol": row.symbol,
                    "exchange": row.exchange,
                    "market": row.market,
                    "score": float(score),
                    "feature_hash": hashlib.sha256(
                        feature_matrix[i].astype(np.float64).tobytes()
                    ).hexdigest(),
                }
            )
        if market_code:
            scored = [s for s in scored if s["market"] == market_code]
        if len(scored) < MIN_MARKET_UNIVERSE:
            raise InsufficientUniverseError(
                f"only {len(scored)} instruments available in market {market_code}",
                as_of=chosen_as_of.isoformat(),
                market=market_code,
                minimum=MIN_MARKET_UNIVERSE,
            )

        scored.sort(key=lambda s: (-s["score"], s["symbol"], s["exchange"]))
        n = len(scored)
        for idx, row in enumerate(scored):
            rank = idx + 1
            row["rank"] = rank
            row["percentile"] = 100.0 if n == 1 else round((n - rank) / (n - 1) * 100.0, 3)
            row["quintile"] = min(5, (idx * 5) // n + 1)
            row["relative_label"] = (
                "expected_above_median"
                if row["score"] >= ABOVE_MEDIAN_SCORE
                else "expected_below_median"
            )
        if limit is not None:
            scored = scored[:limit]

        evaluation = artifact.get("evaluation", {})
        generated_at = datetime.now(UTC)
        return {
            "objective": RANKING_OBJECTIVE,
            "score_semantics": artifact.get("score_semantics"),
            "market": market_code,
            "horizon": horizon,
            "horizon_days": h,
            "as_of_date": chosen_as_of,
            "generated_at": generated_at,
            "model_version": artifact.get("artifact_version", ARTIFACT_VERSION),
            "artifact_sha": digest,
            "artifact_path": str(artifact_path),
            "feature_version": artifact.get("feature_version", "v1"),
            "universe_size": len(eligible),
            "market_universe_size": n,
            "ranked_count": len(scored),
            "excluded": dict(Counter(excluded.values())),
            "entries": scored,
            "evaluation": {
                k: evaluation.get(k)
                for k in ("protocol", "task", "n", "accuracy", "accuracy_wilson95",
                          "reversal1d_acc", "per_market")
            },
            "caveats": [
                "Relative objective: expected performance versus the eligible cross-section, "
                "not an absolute up/down forecast.",
                "Scores are uncalibrated rank scores; they are not probabilities that a "
                "stock rises.",
                "Research evidence is walk-forward on a 19-symbol development panel; "
                "universal generalisation and live profitability are not established.",
            ],
        }

    async def persist(self, result: dict[str, Any]) -> RankingSnapshot:
        existing = (
            await self.session.execute(
                select(RankingSnapshot).where(
                    RankingSnapshot.market == (result["market"] or "ALL"),
                    RankingSnapshot.horizon == result["horizon"],
                    RankingSnapshot.as_of_date == result["as_of_date"],
                    RankingSnapshot.model_version == result["model_version"],
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        snapshot = RankingSnapshot(
            market=result["market"] or "ALL",
            horizon=result["horizon"],
            as_of_date=result["as_of_date"],
            generated_at=result["generated_at"],
            objective=result["objective"],
            model_version=result["model_version"],
            artifact_sha=result["artifact_sha"],
            feature_version=result["feature_version"],
            universe_size=result["universe_size"],
            market_universe_size=result["market_universe_size"],
            metadata_json={
                "score_semantics": result["score_semantics"],
                "excluded": result["excluded"],
                "evaluation": result["evaluation"],
                "caveats": result["caveats"],
            },
        )
        self.session.add(snapshot)
        try:
            await self.session.flush()
            for entry in result["entries"]:
                self.session.add(
                    RankingEntry(
                        snapshot_id=snapshot.id,
                        instrument_id=entry["instrument_id"],
                        symbol=entry["symbol"],
                        exchange=entry["exchange"],
                        rank=entry["rank"],
                        score=Decimal(str(round(entry["score"], 6))),
                        percentile=Decimal(str(entry["percentile"])),
                        quintile=entry["quintile"],
                        relative_label=entry["relative_label"],
                        feature_hash=entry["feature_hash"],
                    )
                )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = (
                await self.session.execute(
                    select(RankingSnapshot).where(
                        RankingSnapshot.market == (result["market"] or "ALL"),
                        RankingSnapshot.horizon == result["horizon"],
                        RankingSnapshot.as_of_date == result["as_of_date"],
                        RankingSnapshot.model_version == result["model_version"],
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            raise
        return snapshot

    async def latest_snapshot(self, market: str | None, horizon: str) -> RankingSnapshot | None:
        stmt = (
            select(RankingSnapshot)
            .where(
                RankingSnapshot.market == (market.upper() if market else "ALL"),
                RankingSnapshot.horizon == horizon,
            )
            .order_by(RankingSnapshot.as_of_date.desc(), RankingSnapshot.generated_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def resolve_outcomes(  # noqa: PLR0912, PLR0915
        self, max_snapshots: int = 50
    ) -> dict[str, Any]:
        snapshots = (
            await self.session.execute(
                select(RankingSnapshot)
                .order_by(RankingSnapshot.as_of_date.desc())
                .limit(max_snapshots)
            )
        ).scalars().all()
        resolved = skipped = errors = 0
        details = []
        for snap in snapshots:
            entries = (
                await self.session.execute(
                    select(RankingEntry)
                    .where(RankingEntry.snapshot_id == snap.id)
                    .order_by(RankingEntry.rank)
                )
            ).scalars().all()
            if not entries:
                continue
            existing_ids = set(
                (
                    await self.session.execute(
                        select(RankingOutcome.entry_id).where(
                            RankingOutcome.entry_id.in_([e.id for e in entries])
                        )
                    )
                ).scalars()
            )
            pending = [e for e in entries if e.id not in existing_ids]
            if not pending:
                continue
            h = HORIZON_DAYS[snap.horizon]
            tz_rows = (
                await self.session.execute(
                    select(Instrument.id, Exchange.timezone)
                    .join(Exchange, Instrument.exchange_id == Exchange.id)
                    .where(Instrument.id.in_({e.instrument_id for e in pending}))
                )
            ).all()
            tz_by_instrument = dict(tz_rows)
            bars_by_instrument: dict[UUID, dict[date, PriceBar]] = defaultdict(dict)
            since = datetime.combine(
                snap.as_of_date - timedelta(days=7), datetime.min.time(), tzinfo=UTC
            )
            for iid in tz_by_instrument:
                rows = (
                    await self.session.execute(
                        select(PriceBar)
                        .where(
                            PriceBar.instrument_id == iid,
                            PriceBar.timeframe == "1d",
                            PriceBar.timestamp >= since,
                        )
                        .order_by(PriceBar.timestamp)
                    )
                ).scalars().all()
                for bar in rows:
                    day = bar.session_day or canonical_session_date(
                        bar.timestamp, tz_by_instrument.get(iid)
                    )
                    if day >= snap.as_of_date:
                        bars_by_instrument[iid][day] = bar
            calendar = sorted({d for m in bars_by_instrument.values() for d in m})
            if snap.as_of_date not in calendar:
                skipped += 1
                details.append({"snapshot": str(snap.id), "reason": "as_of_bar_missing"})
                continue
            idx = calendar.index(snap.as_of_date)
            if idx + h >= len(calendar):
                skipped += 1
                details.append({"snapshot": str(snap.id), "reason": "horizon_not_elapsed"})
                continue
            end_date = calendar[idx + h]
            returns = {}
            for entry in pending:
                start = bars_by_instrument[entry.instrument_id].get(snap.as_of_date)
                end = bars_by_instrument[entry.instrument_id].get(end_date)
                if start is None or end is None or not start.close:
                    continue
                returns[entry.id] = float(end.close) / float(start.close) - 1.0
            if len(returns) < MIN_MARKET_UNIVERSE:
                skipped += 1
                details.append({"snapshot": str(snap.id), "reason": "insufficient_outcomes"})
                continue
            median = float(np.median(list(returns.values())))
            for entry in pending:
                ret = returns.get(entry.id)
                if ret is None:
                    continue
                self.session.add(
                    RankingOutcome(
                        entry_id=entry.id,
                        resolved_at=datetime.now(UTC),
                        horizon_end_date=end_date,
                        forward_return=Decimal(str(round(ret, 6))),
                        cross_sectional_median_return=Decimal(str(round(median, 6))),
                        relative_return=Decimal(str(round(ret - median, 6))),
                        outperformed=ret > median,
                        source="price_bars",
                        note="resolved from canonical daily session days",
                    )
                )
                resolved += 1
            try:
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                errors += 1
                details.append({"snapshot": str(snap.id), "reason": "constraint_conflict"})
        return {"resolved": resolved, "skipped": skipped, "errors": errors, "details": details}

    async def performance(self, market: str | None, horizon: str) -> dict[str, Any]:
        stmt = (
            select(RankingEntry, RankingOutcome, RankingSnapshot)
            .join(RankingOutcome, RankingOutcome.entry_id == RankingEntry.id)
            .join(RankingSnapshot, RankingSnapshot.id == RankingEntry.snapshot_id)
            .where(RankingSnapshot.horizon == horizon)
        )
        if market:
            stmt = stmt.where(RankingSnapshot.market == market.upper())
        rows = (await self.session.execute(stmt)).all()
        n = len(rows)
        hits = 0
        by_quintile: dict[int, dict[str, int]] = defaultdict(lambda: {"n": 0, "hits": 0})
        ics = []
        by_snapshot: dict[UUID, list[tuple[int, float]]] = defaultdict(list)
        for entry, outcome, snap in rows:
            expected_above = entry.relative_label == "expected_above_median"
            hit = outcome.outperformed if expected_above else not outcome.outperformed
            hits += int(hit)
            q = by_quintile[entry.quintile]
            q["n"] += 1
            q["hits"] += int(hit)
            by_snapshot[snap.id].append((entry.rank, float(outcome.relative_return)))
        for pairs in by_snapshot.values():
            if len(pairs) >= MIN_MARKET_UNIVERSE:
                ranks = [p[0] for p in pairs]
                rets = [p[1] for p in pairs]
                if len(set(ranks)) > 1 and len(set(rets)) > 1:
                    rho, _ = spearmanr(ranks, rets)
                    if np.isfinite(rho):
                        ics.append(float(-rho))
        return {
            "market": market.upper() if market else "ALL",
            "horizon": horizon,
            "n_outcomes": n,
            "hit_rate": round(hits / n, 4) if n else None,
            "reliable": n >= MIN_RELIABLE_OUTCOMES,
            "mean_snapshot_rank_ic": round(float(np.mean(ics)), 4) if ics else None,
            "by_quintile": {
                str(k): {
                    "n": v["n"],
                    "hit_rate": round(v["hits"] / v["n"], 4) if v["n"] else None,
                }
                for k, v in sorted(by_quintile.items())
            },
        }

    async def snapshot_payload(self, snapshot: RankingSnapshot) -> dict[str, Any]:
        entries = (
            await self.session.execute(
                select(RankingEntry)
                .where(RankingEntry.snapshot_id == snapshot.id)
                .order_by(RankingEntry.rank)
            )
        ).scalars().all()
        return {
            "market": None if snapshot.market == "ALL" else snapshot.market,
            "horizon": snapshot.horizon,
            "as_of_date": snapshot.as_of_date,
            "generated_at": snapshot.generated_at,
            "objective": snapshot.objective,
            "model_version": snapshot.model_version,
            "artifact_sha": snapshot.artifact_sha,
            "feature_version": snapshot.feature_version,
            "universe_size": snapshot.universe_size,
            "market_universe_size": snapshot.market_universe_size,
            "ranked_count": len(entries),
            "excluded": snapshot.metadata_json.get("excluded", {}),
            "entries": [
                {
                    "instrument_id": e.instrument_id,
                    "symbol": e.symbol,
                    "exchange": e.exchange,
                    "rank": e.rank,
                    "score": float(e.score),
                    "percentile": float(e.percentile),
                    "quintile": e.quintile,
                    "relative_label": e.relative_label,
                }
                for e in entries
            ],
            "evaluation": snapshot.metadata_json.get("evaluation", {}),
            "caveats": snapshot.metadata_json.get("caveats", []),
            "score_semantics": snapshot.metadata_json.get("score_semantics"),
        }
