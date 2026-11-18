from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.market import Exchange, Instrument
from apps.api.models.watchlist import Watchlist, WatchlistItem
from apps.api.repositories.base import BaseRepository


class WatchlistRepository(BaseRepository[Watchlist]):
    """Watchlist repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Watchlist, session)

    async def get_user_watchlists(
        self, user_id: UUID, include_items: bool = False
    ) -> list[Watchlist]:
        """Get all watchlists for a user."""
        query = select(Watchlist).where(Watchlist.user_id == user_id)
        if include_items:
            query = query.options(selectinload(Watchlist.items).selectinload(WatchlistItem.instrument))
        query = query.order_by(Watchlist.is_default.desc(), Watchlist.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_default_watchlist(self, user_id: UUID) -> Watchlist | None:
        """Get user's default watchlist."""
        query = select(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.is_default.is_(True),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name(self, user_id: UUID, name: str) -> Watchlist | None:
        """Get watchlist by name for a user."""
        query = select(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.name == name,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_watchlist(
        self,
        user_id: UUID,
        name: str,
        description: str | None = None,
        is_default: bool = False,
    ) -> Watchlist:
        """Create a new watchlist."""
        # If this is default, unset other defaults
        if is_default:
            await self.session.execute(
                Watchlist.__table__.update()
                .where(Watchlist.user_id == user_id)
                .values(is_default=False)
            )

        return await self.create(
            user_id=user_id,
            name=name,
            description=description,
            is_default=is_default,
        )

    async def set_default(self, user_id: UUID, watchlist_id: UUID) -> bool:
        """Set a watchlist as default."""
        # Unset current default
        await self.session.execute(
            Watchlist.__table__.update()
            .where(Watchlist.user_id == user_id)
            .values(is_default=False)
        )

        # Set new default
        watchlist = await self.get(watchlist_id)
        if watchlist and watchlist.user_id == user_id:
            watchlist.is_default = True
            await self.session.flush()
            return True
        return False


class WatchlistItemRepository(BaseRepository[WatchlistItem]):
    """Watchlist item repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(WatchlistItem, session)

    async def get_watchlist_items(
        self, watchlist_id: UUID, include_instrument: bool = True
    ) -> list[WatchlistItem]:
        """Get all items in a watchlist."""
        query = select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        if include_instrument:
            query = query.options(
                selectinload(WatchlistItem.instrument).selectinload(Instrument.exchange).selectinload(Exchange.market)
            )
        query = query.order_by(WatchlistItem.sort_order, WatchlistItem.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def add_item(
        self,
        watchlist_id: UUID,
        instrument_id: UUID,
        notes: str | None = None,
    ) -> WatchlistItem | None:
        """Add item to watchlist."""
        # Check if already exists
        existing = await self.session.execute(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.instrument_id == instrument_id,
            )
        )
        if existing.scalar_one_or_none():
            return None

        # Get max sort_order
        max_order = await self.session.execute(
            select(func.max(WatchlistItem.sort_order)).where(
                WatchlistItem.watchlist_id == watchlist_id
            )
        )
        next_order = (max_order.scalar() or 0) + 1

        return await self.create(
            watchlist_id=watchlist_id,
            instrument_id=instrument_id,
            notes=notes,
            sort_order=next_order,
        )

    async def remove_item(self, watchlist_id: UUID, instrument_id: UUID) -> bool:
        """Remove item from watchlist."""
        result = await self.session.execute(
            delete(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.instrument_id == instrument_id,
            )
        )
        return result.rowcount > 0

    async def reorder_items(self, watchlist_id: UUID, item_ids: list[UUID]) -> bool:
        """Reorder watchlist items."""
        watchlist = await self.session.get(Watchlist, watchlist_id)
        if not watchlist:
            return False

        for index, item_id in enumerate(item_ids):
            await self.session.execute(
                WatchlistItem.__table__.update()
                .where(
                    WatchlistItem.watchlist_id == watchlist_id,
                    WatchlistItem.id == item_id,
                )
                .values(sort_order=index)
            )
        await self.session.flush()
        return True

    async def is_in_watchlist(self, watchlist_id: UUID, instrument_id: UUID) -> bool:
        """Check if instrument is in watchlist."""
        result = await self.session.execute(
            select(WatchlistItem.id).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.instrument_id == instrument_id,
            )
        )
        return result.scalar_one_or_none() is not None
