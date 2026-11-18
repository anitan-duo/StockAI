"""Formal freshness model for market data.

Every market-data response served by the API must carry a machine-readable
freshness classification. The frontend MUST consume this classification and
must not invent its own staleness heuristics (see §17 of the product spec).

Categories (mutually exclusive, ordered from best to worst):

    FRESH        Source timestamp within the live-quote window of an open
                 session (default <= 60s) and ingestion is recent.
    RECENT       Source timestamp within the delayed-tolerance window
                 (default <= 15 min). Typical for 15-min-delayed feeds.
    DELAYED      Source timestamp within the same trading day but older
                 than the delayed-tolerance window, OR the market is closed
                 and the snapshot is from the last session.
    STALE        Older than the current session could plausibly explain
                 (default > 24h). Must never be presented as current.
    UNAVAILABLE  No timestamp / no data at all.

The classification depends on market session context: a snapshot from the
previous close is DELAYED (normal overnight condition), not STALE.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Optional


class Freshness(str, Enum):
    """Freshness classification for market data."""

    FRESH = "fresh"
    RECENT = "recent"
    DELAYED = "delayed"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


# Thresholds (seconds). Tuned for 15-min-delayed consolidated-tape style
# feeds and 5-min scheduler ingestion cadence. Documented in ARCHITECTURE.md.
FRESH_MAX_AGE_S = 60          # live-quote window while the market is open
RECENT_MAX_AGE_S = 15 * 60    # delayed feed tolerance
DELAYED_MAX_AGE_S = 12 * 3600  # same-session data older than RECENT
STALE_MAX_AGE_S = 24 * 3600   # open-session data older than this is stale

# When the market is CLOSED, the last tick is naturally old: a Friday close
# viewed on Sunday is ~48h old and still correct. Allow up to 4 days (covers
# weekends + a single holiday) before closed-session data counts as stale.
CLOSED_SESSION_TOLERANCE_S = 4 * 24 * 3600

# Market statuses under which a recent snapshot is expected to tick.
OPEN_STATUSES = {"open", "pre-market", "after-hours", "pre_market", "post_market"}


def classify_freshness(
    source_timestamp: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    ingested_at: Optional[datetime] = None,
    market_status: Optional[str] = None,
) -> Freshness:
    """Classify the freshness of a market-data point.

    Args:
        source_timestamp: When the provider says the data is from.
        now: Current time (UTC). Defaults to real UTC now; injectable in tests.
        ingested_at: When our system persisted the data. Used only as a
            secondary bound so persisted-in-the-past data cannot look fresh.
        market_status: "open"/"closed"/"pre-market"/... Controls whether the
            previous-session snapshot is DELAYED (normal) or STALE.

    Returns:
        Freshness enum value. Never raises on bad input — unknown input
        classifies as UNAVAILABLE (fail honest, not fail loud).
    """
    if source_timestamp is None:
        return Freshness.UNAVAILABLE

    if now is None:
        now = datetime.now(UTC)

    ts = _as_utc(source_timestamp)
    if ts is None:
        return Freshness.UNAVAILABLE

    # Future timestamps are a data-integrity violation, not freshness.
    if ts > now + timedelta(minutes=5):
        return Freshness.UNAVAILABLE

    age = now - ts
    age_s = age.total_seconds()

    # The ingestion timestamp bounds how recently *we* saw the data.
    ingested_bound = None
    if ingested_at is not None:
        ing = _as_utc(ingested_at)
        if ing is not None and ing <= now:
            ingested_bound = (now - ing).total_seconds()

    if market_status and str(market_status).lower() in OPEN_STATUSES:
        # Open session: ages map directly to the tiers.
        if age_s <= FRESH_MAX_AGE_S and (ingested_bound is None or ingested_bound <= FRESH_MAX_AGE_S):
            return Freshness.FRESH
        if age_s <= RECENT_MAX_AGE_S:
            return Freshness.RECENT
        if age_s <= DELAYED_MAX_AGE_S:
            return Freshness.DELAYED
        return Freshness.STALE

    if market_status and str(market_status).lower() in {"closed", "holiday"}:
        # Closed session (or holiday): the last tick is naturally old.
        # A snapshot from the last session is DELAYED (normal overnight /
        # weekend condition) up to the closed-session tolerance.
        if age_s <= CLOSED_SESSION_TOLERANCE_S and (
            ingested_bound is None or ingested_bound <= CLOSED_SESSION_TOLERANCE_S
        ):
            return Freshness.DELAYED
        return Freshness.STALE

    # Unknown market status: be conservative — do not inflate freshness.
    if age_s <= RECENT_MAX_AGE_S:
        return Freshness.RECENT
    if age_s <= STALE_MAX_AGE_S:
        return Freshness.DELAYED
    return Freshness.STALE


def _as_utc(dt: datetime) -> Optional[datetime]:
    """Normalize a datetime to aware UTC. Naive datetimes are assumed UTC
    only when they are plausibly already UTC — callers should always store
    timezone-aware timestamps (DB columns are DateTime(timezone=True))."""
    if dt is None:
        return None
    try:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, OverflowError, OSError):
        return None


def freshness_rank(f: Freshness) -> int:
    """Lower is better. Useful for picking the best of several sources."""
    order = {
        Freshness.FRESH: 0,
        Freshness.RECENT: 1,
        Freshness.DELAYED: 2,
        Freshness.STALE: 3,
        Freshness.UNAVAILABLE: 4,
    }
    return order[f]


def is_presentable_as_current(f: Freshness) -> bool:
    """Only FRESH/RECENT/DELAYED may be shown as a current price.
    STALE/UNAVAILABLE must surface an explicit data-status warning in the UI."""
    return f in (Freshness.FRESH, Freshness.RECENT, Freshness.DELAYED)