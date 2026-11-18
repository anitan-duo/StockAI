from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.market import Exchange, Instrument, Market
from apps.api.models.price import MarketSnapshot, PriceBar
from apps.api.repositories.base import BaseRepository


class MarketRepository(BaseRepository[Market]):
    """Market repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Market, session)

    async def get_by_code(self, code: str) -> Market | None:
        """Get market by code."""
        return await self.get_by_field("code", code.upper())

    async def get_active_markets(self) -> list[Market]:
        """Get all active markets."""
        return await self.list(filters={"is_active": True}, order_by="code")


class ExchangeRepository(BaseRepository[Exchange]):
    """Exchange repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Exchange, session)

    async def get_by_code(self, code: str, market_id: int | None = None) -> Exchange | None:
        """Get exchange by code (market eager-loaded: ExchangeResponse nests
        exchange.market, and lazy access raises MissingGreenlet under async)."""
        from sqlalchemy.orm import selectinload

        query = (
            select(Exchange)
            .options(selectinload(Exchange.market))
            .where(Exchange.code == code.upper())
        )
        if market_id:
            query = query.where(Exchange.market_id == market_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_market(self, market_id: int, active_only: bool = True) -> list[Exchange]:
        """Get exchanges for a market (market eager-loaded, see get_by_code)."""
        from sqlalchemy.orm import selectinload

        query = (
            select(Exchange)
            .options(selectinload(Exchange.market))
            .where(Exchange.market_id == market_id)
        )
        if active_only:
            query = query.where(Exchange.is_active.is_(True))
        query = query.order_by(Exchange.code)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class InstrumentRepository(BaseRepository[Instrument]):
    """Instrument repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Instrument, session)

    async def get_by_symbol_exchange(
        self, symbol: str, exchange_id: int
    ) -> Instrument | None:
        """Get instrument by symbol and exchange."""
        query = select(Instrument).where(
            Instrument.symbol == symbol.upper(),
            Instrument.exchange_id == exchange_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def search(
        self,
        query: str,
        market: str | None = None,
        exchange: str | None = None,
        type: str | None = None,
        limit: int = 20,
    ) -> list[Instrument]:
        """Search instruments by symbol or name."""

        search_query = f"%{query.upper()}%"

        stmt = select(Instrument).options(
            selectinload(Instrument.exchange).selectinload(Exchange.market)
        ).where(
            or_(
                Instrument.symbol.ilike(search_query),
                Instrument.name.ilike(search_query),
            )
        )

        if market:
            stmt = stmt.join(Exchange).join(Market).where(Market.code == market.upper())

        if exchange:
            stmt = stmt.join(Exchange).where(Exchange.code == exchange.upper())

        if type:
            stmt = stmt.where(Instrument.type == type)

        stmt = stmt.where(Instrument.is_active.is_(True)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_instruments(
        self,
        exchange_id: int | None = None,
        type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Instrument]:
        """Get active instruments with filters."""
        filters = {"is_active": True}
        if exchange_id:
            filters["exchange_id"] = exchange_id
        if type:
            filters["type"] = type
        return await self.list(filters=filters, skip=skip, limit=limit, order_by="symbol")

    async def get_by_ids(self, ids: list[UUID]) -> list[Instrument]:
        """Get instruments by list of IDs."""
        query = select(Instrument).where(Instrument.id.in_(ids))
        result = await self.session.execute(query)
        return list(result.scalars().all())


class PriceBarRepository(BaseRepository[PriceBar]):
    """Price bar repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(PriceBar, session)

    async def get_latest(
        self,
        instrument_id: UUID,
        timeframe: str = "1d",
        limit: int = 1,
    ) -> list[PriceBar]:
        """Get latest price bars for an instrument."""
        query = (
            select(PriceBar)
            .where(
                PriceBar.instrument_id == instrument_id,
                PriceBar.timeframe == timeframe,
            )
            .order_by(desc(PriceBar.timestamp))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_range(
        self,
        instrument_id: UUID,
        timeframe: str,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[PriceBar]:
        """Get price bars in a date range, newest-biased.

        Previous implementation used ASC + LIMIT which returned the OLDEST N
        rows in the window — so a chart asking for the last 30 bars of a
        decade-long series would show ancient (e.g. 2001-era) candles as if
        current. We now fetch DESC + LIMIT (newest) then return ASC for charts.
        """
        from sqlalchemy import desc as _desc

        if limit:
            inner = (
                select(PriceBar)
                .where(
                    PriceBar.instrument_id == instrument_id,
                    PriceBar.timeframe == timeframe,
                    PriceBar.timestamp >= start,
                    PriceBar.timestamp <= end,
                )
                .order_by(_desc(PriceBar.timestamp))
                .limit(limit)
            )
            result = await self.session.execute(inner)
            rows = list(result.scalars().all())
            rows.reverse()
            return rows
        query = (
            select(PriceBar)
            .where(
                PriceBar.instrument_id == instrument_id,
                PriceBar.timeframe == timeframe,
                PriceBar.timestamp >= start,
                PriceBar.timestamp <= end,
            )
            .order_by(PriceBar.timestamp)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_bar(
        self, instrument_id: UUID, timestamp: datetime, timeframe: str
    ) -> PriceBar | None:
        """Get a single price bar (for idempotent re-ingestion)."""
        result = await self.session.execute(
            select(PriceBar).where(
                PriceBar.instrument_id == instrument_id,
                PriceBar.timestamp == timestamp,
                PriceBar.timeframe == timeframe,
            )
        )
        return result.scalar_one_or_none()

    async def bulk_upsert(self, bars: list[dict]) -> int:
        """Bulk upsert price bars."""
        from sqlalchemy.dialects.postgresql import insert

        if not bars:
            return 0

        stmt = insert(PriceBar).values(bars)
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "timestamp", "timeframe"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "vwap": stmt.excluded.vwap,
                "trades_count": stmt.excluded.trades_count,
                "source": stmt.excluded.source,
                "ingested_at": stmt.excluded.ingested_at,
                "updated_at": func.now(),
            },
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def get_latest_timestamp(
        self, instrument_id: UUID, timeframe: str
    ) -> datetime | None:
        """Get the latest timestamp for an instrument/timeframe."""
        query = (
            select(func.max(PriceBar.timestamp))
            .where(
                PriceBar.instrument_id == instrument_id,
                PriceBar.timeframe == timeframe,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_timestamps_in_range(
        self,
        instrument_id: UUID,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> set[datetime]:
        """Timestamps already persisted in [start, end] (gap-fill support)."""
        query = select(PriceBar.timestamp).where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.timeframe == timeframe,
            PriceBar.timestamp >= start,
            PriceBar.timestamp <= end,
        )
        result = await self.session.execute(query)
        return set(result.scalars().all())


class MarketSnapshotRepository(BaseRepository[MarketSnapshot]):
    """Market snapshot repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(MarketSnapshot, session)

    async def get_latest(self, instrument_id: UUID) -> MarketSnapshot | None:
        """Get latest market snapshot for an instrument."""
        query = (
            select(MarketSnapshot)
            .where(MarketSnapshot.instrument_id == instrument_id)
            .order_by(desc(MarketSnapshot.timestamp))
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_latest_batch(self, instrument_ids: list[UUID]) -> list[MarketSnapshot]:
        """Get latest snapshots for multiple instruments."""
        if not instrument_ids:
            return []

        # Use a subquery to get latest timestamp per instrument
        subquery = (
            select(
                MarketSnapshot.instrument_id,
                func.max(MarketSnapshot.timestamp).label("max_ts"),
            )
            .where(MarketSnapshot.instrument_id.in_(instrument_ids))
            .group_by(MarketSnapshot.instrument_id)
            .subquery()
        )

        query = (
            select(MarketSnapshot)
            .join(
                subquery,
                and_(
                    MarketSnapshot.instrument_id == subquery.c.instrument_id,
                    MarketSnapshot.timestamp == subquery.c.max_ts,
                ),
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
