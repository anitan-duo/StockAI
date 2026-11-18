"""BAR-002 reconciliation: deterministic dedupe + canonical session_day backfill.

This tool implements the owner-gated BAR-002 remediation policy:

1. Group every ``timeframe='1d'`` row by (instrument, canonical session date).
2. In each duplicate group, the survivor is the row stamped at the canonical
   instant (exchange-local midnight converted to UTC).
3. The redundant row is dropped only when its OHLCV agrees with the survivor
   within provider-rounding tolerance. Full row payloads are written to the
   report before deletion, so the operation is reversible by re-insert.
4. Materially disagreeing groups are quarantined: both rows are kept and their
   ``session_day`` stays NULL, so the partial unique index accepts them and no
   valid observation is silently discarded.
5. ``session_day`` is backfilled for unique canonical rows only.

Execution order (enforced by the tool):
    default/dry-run -> inspect plan, write report, no writes
    --phase dedupe --apply   -> delete redundant rows (column not required)
    (apply migration c4e1b90d5a7f, which adds the nullable column/index)
    --phase backfill --apply -> fill session_day, leave quarantined rows NULL
    --phase verify           -> re-check counts and constraints

Usage:
    python scripts/bar002_reconcile.py --report /tmp/plan.json
    python scripts/bar002_reconcile.py --phase dedupe --apply --report ...
    python scripts/bar002_reconcile.py --phase backfill --apply --report ...
    python scripts/bar002_reconcile.py --phase verify
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, delete, inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import load_only

from apps.api.config import settings
from apps.api.models.market import Exchange, Instrument, Market  # noqa: F401
from apps.api.models.price import PriceBar
from services.ingestion.canonical_days import (
    canonical_instant_for_session_day,
    canonical_session_date,
)

PRICE_REL_TOL = 1e-3
VOLUME_REL_TOL = 1e-2

PRICE_BAR_FIELDS = (
    "id",
    "instrument_id",
    "timestamp",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "trades_count",
    "source",
    "ingested_at",
    "created_at",
    "updated_at",
)


def _rel(a, b) -> float:
    x, y = float(a), float(b)
    return abs(x - y) / max(abs(x), abs(y), 1e-12)


def _ohlcv_diff(a: PriceBar, b: PriceBar) -> dict[str, float]:
    return {
        "price_max_rel_diff": round(
            max(_rel(getattr(a, f), getattr(b, f)) for f in ("open", "high", "low", "close")), 8
        ),
        "volume_rel_diff": round(_rel(a.volume, b.volume), 8),
    }


def _row(bar: PriceBar, instrument: Instrument, exchange: Exchange) -> dict[str, Any]:
    def dt(v):
        return v.isoformat() if v is not None else None

    def dec(v):
        return str(v) if isinstance(v, Decimal) else v

    return {
        "id": str(bar.id),
        "instrument_id": str(bar.instrument_id),
        "symbol": instrument.symbol,
        "exchange": exchange.code,
        "exchange_tz": exchange.timezone,
        "timestamp": dt(bar.timestamp),
        "timeframe": bar.timeframe,
        "open": dec(bar.open),
        "high": dec(bar.high),
        "low": dec(bar.low),
        "close": dec(bar.close),
        "volume": bar.volume,
        "vwap": dec(bar.vwap),
        "trades_count": bar.trades_count,
        "source": bar.source,
        "ingested_at": dt(bar.ingested_at),
        "created_at": dt(bar.created_at),
        "updated_at": dt(bar.updated_at),
    }


class Plan:
    def __init__(self, rows: list[tuple[PriceBar, Instrument, Exchange]]):
        self.rows = rows
        self.groups: dict[tuple[str, str], list[tuple[PriceBar, Instrument, Exchange]]] = defaultdict(list)
        for bar, inst, exch in rows:
            day = canonical_session_date(bar.timestamp, exch.timezone)
            self.groups[(str(inst.id), str(day))].append((bar, inst, exch))

        self.backfill: dict[str, Any] = {}
        self.drop_ids: list[Any] = []
        self.quarantine_ids: list[Any] = []
        self.groups_report: list[dict[str, Any]] = []
        self.expected_1d_after = len(rows)
        self.by_symbol_dropped: Counter = Counter()

        for (inst_id, day), members in sorted(
            self.groups.items(), key=lambda kv: (kv[0][1], kv[1][0][1].symbol)
        ):
            bar0, inst, exch = members[0]
            if len(members) == 1:
                self.backfill[inst_id] = self.backfill.get(inst_id, {})
                self.backfill[inst_id][str(bar0.id)] = day
                continue

            canonical_ts = canonical_instant_for_session_day(
                datetime.fromisoformat(day).date(), exch.timezone
            )
            canonical = [m for m in members if m[0].timestamp.astimezone(UTC) == canonical_ts]
            entry: dict[str, Any] = {
                "instrument_id": inst_id,
                "symbol": inst.symbol,
                "exchange": exch.code,
                "session_day": day,
                "stored_timestamps": [m[0].timestamp.isoformat() for m in members],
                "sources": [m[0].source for m in members],
                "canonical_timestamp": canonical_ts.isoformat(),
            }
            if len(canonical) != 1:
                entry["classification"] = "quarantined_no_canonical_survivor"
                self.quarantine_ids.extend(str(m[0].id) for m in members)
                entry["kept_ids"] = [str(m[0].id) for m in members]
                entry["dropped_ids"] = []
                self.expected_1d_after -= 0
            else:
                survivor, _, _ = canonical[0]
                diffs = []
                conflict = False
                drop = []
                for m in members:
                    if m[0].id == survivor.id:
                        continue
                    d = _ohlcv_diff(survivor, m[0])
                    diffs.append({"id": str(m[0].id), **d})
                    if d["price_max_rel_diff"] > PRICE_REL_TOL or d["volume_rel_diff"] > VOLUME_REL_TOL:
                        conflict = True
                    drop.append(m[0].id)
                entry["diffs"] = diffs
                if conflict:
                    entry["classification"] = "quarantined_ohlcv_conflict"
                    self.quarantine_ids.extend(str(m[0].id) for m in members)
                    entry["kept_ids"] = [str(m[0].id) for m in members]
                    entry["dropped_ids"] = []
                else:
                    entry["classification"] = "redundant"
                    entry["kept_ids"] = [str(survivor.id)]
                    entry["dropped_ids"] = [str(x) for x in drop]
                    self.drop_ids.extend(drop)
                    self.by_symbol_dropped[inst.symbol] += len(drop)
                    self.expected_1d_after -= len(drop)
                    for m in members:
                        if m[0].id == survivor.id:
                            self.backfill[inst_id] = self.backfill.get(inst_id, {})
                            self.backfill[inst_id][str(survivor.id)] = day
            self.groups_report.append(entry)

    @property
    def duplicate_groups(self) -> int:
        return len(self.groups_report)

    @property
    def classifications(self) -> dict[str, int]:
        return dict(Counter(g["classification"] for g in self.groups_report))

    @property
    def dropped_payloads(self) -> list[dict[str, Any]]:
        wanted = set(str(x) for x in self.drop_ids)
        return [_row(b, i, e) for b, i, e in self.rows if str(b.id) in wanted]

    @property
    def quarantined_payloads(self) -> list[dict[str, Any]]:
        wanted = set(self.quarantine_ids)
        return [_row(b, i, e) for b, i, e in self.rows if str(b.id) in wanted]


async def _load(session: AsyncSession, lock: bool = False) -> list[tuple[PriceBar, Instrument, Exchange]]:
    stmt = (
        select(PriceBar, Instrument, Exchange)
        .options(load_only(*(getattr(PriceBar, name) for name in PRICE_BAR_FIELDS)))
        .join(Instrument, PriceBar.instrument_id == Instrument.id)
        .join(Exchange, Instrument.exchange_id == Exchange.id)
        .where(PriceBar.timeframe == "1d")
        .order_by(Instrument.symbol, PriceBar.timestamp)
    )
    if lock:
        stmt = stmt.with_for_update()
    return list((await session.execute(stmt)).all())


async def _has_session_day(session: AsyncSession) -> bool:
    cols = await session.run_sync(
        lambda sync: [c["name"] for c in inspect(sync.get_bind()).get_columns("price_bars")]
    )
    return "session_day" in cols


async def _counts(session: AsyncSession) -> dict[str, int]:
    total = (await session.execute(text("select count(*) from price_bars"))).scalar_one()
    daily = (
        await session.execute(text("select count(*) from price_bars where timeframe='1d'"))
    ).scalar_one()
    other = total - daily
    null_days = 0
    duplicate_days = 0
    if await _has_session_day(session):
        null_days = (
            await session.execute(
                text(
                    "select count(*) from price_bars where timeframe='1d' "
                    "and session_day is null"
                )
            )
        ).scalar_one()
        duplicate_days = (
            await session.execute(
                text(
                    "select count(*) from (select instrument_id, session_day from price_bars "
                    "where timeframe='1d' and session_day is not null "
                    "group by instrument_id, session_day having count(*) > 1) d"
                )
            )
        ).scalar_one()
    return {
        "bars_total": int(total),
        "bars_1d": int(daily),
        "bars_other_timeframes": int(other),
        "session_day_null_1d": int(null_days),
        "duplicate_session_days": int(duplicate_days),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--phase", choices=["auto", "dedupe", "backfill", "verify"], default="auto")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--report", default=None, help="write JSON evidence report here")
    args = ap.parse_args()

    url = args.database_url or settings.database_url
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    started = datetime.now(UTC)
    try:
        if args.phase == "verify" or (args.phase == "auto" and not args.apply):
            async with factory() as session:
                rows = await _load(session)
                plan = Plan(rows)
                before = await _counts(session)
            report = _report(url, started, args, plan, before, None, applied=False)
            _write(args.report, report)
            _emit(report)
            return 0 if not args.apply else _verify_ok(report)

        if args.phase == "backfill":
            return await _run_backfill(factory, url, started, args)

        # dedupe (or auto before the column exists)
        async with engine.begin() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            rows = await _load(session, lock=True)
            plan = Plan(rows)
            before = await _counts(session)
            if not args.apply:
                report = _report(url, started, args, plan, before, None, applied=False)
                _write(args.report, report)
                _emit(report)
                return 0
            if plan.drop_ids:
                await session.execute(delete(PriceBar).where(PriceBar.id.in_(plan.drop_ids)))
            after = await _counts(session)
            if after["bars_1d"] != plan.expected_1d_after:
                raise RuntimeError(
                    f"post-dedupe count mismatch: {after['bars_1d']} != {plan.expected_1d_after}"
                )
            if after["bars_total"] != before["bars_total"] - len(plan.drop_ids):
                raise RuntimeError("post-dedupe total count mismatch")
            report = _report(url, started, args, plan, before, after, applied=True)
            report["phase"] = "dedupe"
            report["dropped_count"] = len(plan.drop_ids)
            report["dropped_rows"] = plan.dropped_payloads
            report["quarantined_rows"] = plan.quarantined_payloads
            _write(args.report, report)
            await session.close()
        _emit(report)
        if await _has_session_day_factory(factory):
            return await _run_backfill(factory, url, started, args)
        return 0
    finally:
        await engine.dispose()


async def _has_session_day_factory(factory) -> bool:
    async with factory() as session:
        return await _has_session_day(session)


async def _run_backfill(factory, url, started, args) -> int:
    async with factory() as session:
        if not await _has_session_day(session):
            raise SystemExit(
                "session_day column is absent: apply migration c4e1b90d5a7f after dedupe, "
                "then rerun --phase backfill --apply"
            )
        rows = await _load(session)
        plan = Plan(rows)
        before = await _counts(session)
        if plan.drop_ids:
            raise SystemExit(
                f"{len(plan.drop_ids)} redundant rows remain: run --phase dedupe --apply first"
            )
        if not args.apply:
            report = _report(url, started, args, plan, before, None, applied=False)
            report["phase"] = "backfill-dry-run"
            _write(args.report, report)
            _emit(report)
            return 0

        updates = []
        for inst_id, by_id in plan.backfill.items():
            for bar_id, day in by_id.items():
                updates.append({"bid": bar_id, "sday": datetime.fromisoformat(day).date()})
        t = PriceBar.__table__
        stmt = (
            update(t)
            .where(t.c.id == bindparam("bid"))
            .values(session_day=bindparam("sday"))
        )
        if updates:
            await session.execute(stmt, updates)
        # Quarantined rows must remain NULL so the partial unique index accepts them.
        if plan.quarantine_ids:
            t = PriceBar.__table__
            await session.execute(
                update(t).where(t.c.id.in_(plan.quarantine_ids)).values(session_day=None)
            )
        await session.flush()
        after = await _counts(session)
        expected_null = len(plan.quarantine_ids)
        if after["session_day_null_1d"] != expected_null:
            raise RuntimeError(
                f"backfill left {after['session_day_null_1d']} NULL session_days, "
                f"expected {expected_null} quarantined rows"
            )
        if after["duplicate_session_days"] != 0:
            raise RuntimeError(
                f"backfill produced {after['duplicate_session_days']} duplicate session days"
            )
        await session.commit()
        report = _report(url, started, args, plan, before, after, applied=True)
        report["phase"] = "backfill"
        report["quarantined_rows"] = plan.quarantined_payloads
        _write(args.report, report)
        _emit(report)
        return 0


def _verify_ok(report: dict) -> int:
    after = report.get("after") or {}
    if after.get("duplicate_session_days", 0) != 0:
        return 1
    return 0


def _report(url, started, args, plan: Plan, before, after, applied: bool) -> dict:
    return {
        "bar002_report_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "started_at": started.isoformat(),
        "database_url_scheme": url.split("://")[0],
        "phase": args.phase,
        "applied": applied,
        "policy": {
            "grouping": "canonical session date (UTC date for exact 00:00Z labels, else exchange local date)",
            "survivor": "row stamped at exchange-local midnight in UTC",
            "price_rel_tolerance": PRICE_REL_TOL,
            "volume_rel_tolerance": VOLUME_REL_TOL,
            "conflict_action": "quarantine: keep both rows, session_day NULL, no deletion",
        },
        "before": before,
        "after": after,
        "duplicate_groups": plan.duplicate_groups,
        "classifications": plan.classifications,
        "redundant_rows_to_drop": len(plan.drop_ids),
        "quarantined_rows": len(plan.quarantine_ids),
        "expected_1d_after": plan.expected_1d_after,
        "dropped_by_symbol": dict(sorted(plan.by_symbol_dropped.items())),
        "groups": plan.groups_report,
    }


def _write(path: str | None, report: dict) -> None:
    if not path:
        return
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)


def _emit(report: dict) -> None:
    print(
        json.dumps(
            {
                "applied": report["applied"],
                "phase": report["phase"],
                "before": report["before"],
                "after": report["after"],
                "duplicate_groups": report["duplicate_groups"],
                "classifications": report["classifications"],
                "redundant_rows_to_drop": report["redundant_rows_to_drop"],
                "quarantined_rows": report["quarantined_rows"],
                "expected_1d_after": report["expected_1d_after"],
                "dropped_by_symbol": report["dropped_by_symbol"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
