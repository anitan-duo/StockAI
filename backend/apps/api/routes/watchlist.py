from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.repositories.market import InstrumentRepository, MarketSnapshotRepository
from apps.api.repositories.prediction import PredictionRepository
from apps.api.repositories.watchlist import WatchlistItemRepository, WatchlistRepository
from apps.api.routes.auth import get_current_user
from packages.schemas.watchlist import (
    WatchlistCreate,
    WatchlistItemResponse,
    WatchlistResponse,
    WatchlistUpdate,
    WatchlistWithItemsResponse,
)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _get_user_id(user) -> UUID:
    """Handle User ORM, dict, or string identity without recursion."""
    if hasattr(user, "id"):
        uid = user.id  # type: ignore
        return uid if isinstance(uid, UUID) else UUID(str(uid))
    if isinstance(user, dict):
        for key in ("id", "user_id", "sub"):
            if user.get(key):
                return UUID(str(user[key]))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")
    if isinstance(user, str):
        return UUID(user)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")


@router.get("", response_model=list[WatchlistResponse])
async def list_watchlists(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistResponse]:
    """List user's watchlists."""
    repo = WatchlistRepository(session)
    watchlists = await repo.get_user_watchlists(_get_user_id(user))
    return [WatchlistResponse.model_validate(w) for w in watchlists]


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    data: WatchlistCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WatchlistResponse:
    """Create a new watchlist."""
    repo = WatchlistRepository(session)

    # Check name uniqueness
    existing = await repo.get_by_name(_get_user_id(user), data.name)
    if existing:
        raise HTTPException(status_code=409, detail="Watchlist with this name already exists")

    watchlist = await repo.create_watchlist(
        user_id=_get_user_id(user),
        name=data.name,
        description=data.description,
        is_default=data.is_default,
    )
    await session.commit()
    return WatchlistResponse.model_validate(watchlist)


@router.get("/{watchlist_id}", response_model=WatchlistWithItemsResponse)
async def get_watchlist(
    watchlist_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WatchlistWithItemsResponse:
    """Get watchlist with items."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get(watchlist_id)

    if not watchlist or watchlist.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Get items with full details
    item_repo = WatchlistItemRepository(session)
    items = await item_repo.get_watchlist_items(watchlist_id)

    # Enrich with quotes and predictions - handle async loading safely
    snapshot_repo = MarketSnapshotRepository(session)
    prediction_repo = PredictionRepository(session)

    enriched_items = []
    for item in items:
        quote = await snapshot_repo.get_latest(item.instrument_id)
        prediction = await prediction_repo.get_latest_for_instrument(item.instrument_id)
        # Manually build instrument response to avoid lazy load issues
        # instrument is already loaded via selectinload
        try:
            # Try to use loaded instrument, fallback to query
            inst = item.instrument
            if inst is None:
                inst_repo = InstrumentRepository(session)
                inst = await inst_repo.get(item.instrument_id)
        except Exception:
            inst_repo = InstrumentRepository(session)
            inst = await inst_repo.get(item.instrument_id)

        # Build instrument dict manually to avoid ORM serialization
        if inst is not None:
            try:
                instrument_dict = {
                    "symbol": inst.symbol,
                    "name": inst.name,
                    "exchange": inst.exchange.code if hasattr(inst, "exchange") and inst.exchange else None,
                    "exchange_name": inst.exchange.name if hasattr(inst, "exchange") and inst.exchange else None,
                    "market": inst.exchange.market.code if hasattr(inst, "exchange") and inst.exchange and hasattr(inst.exchange, "market") and inst.exchange.market else None,
                    "currency": inst.currency,
                    "sector": getattr(inst, "sector", None),
                    "id": str(inst.id),
                }
            except Exception:
                instrument_dict = {"symbol": getattr(inst, "symbol", "UNKNOWN"), "name": getattr(inst, "name", ""), "id": str(inst.id) if hasattr(inst, "id") else str(item.instrument_id)}
        else:
            instrument_dict = {"symbol": "UNKNOWN", "name": "", "id": str(item.instrument_id)}

        enriched_items.append(WatchlistItemResponse(
            id=item.id,
            watchlist_id=item.watchlist_id,
            instrument_id=item.instrument_id,
            notes=item.notes,
            sort_order=item.sort_order,
            created_at=item.created_at,
            updated_at=item.updated_at,
            instrument=instrument_dict,  # type: ignore
            quote=None,  # type: ignore - avoid lazy load issues, frontend will fetch separately
            prediction=None,  # type: ignore
        ))

    # Build response manually to avoid MissingGreenlet on watchlist.items
    return WatchlistWithItemsResponse(
        id=watchlist.id,
        user_id=watchlist.user_id,
        name=watchlist.name,
        description=watchlist.description,
        is_default=watchlist.is_default,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
        item_count=len(enriched_items),
        items=enriched_items,  # type: ignore
    )


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: UUID,
    data: WatchlistUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WatchlistResponse:
    """Update watchlist."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get(watchlist_id)

    if not watchlist or watchlist.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Check name uniqueness if changing
    if data.name and data.name != watchlist.name:
        existing = await repo.get_by_name(_get_user_id(user), data.name)
        if existing:
            raise HTTPException(status_code=409, detail="Watchlist with this name already exists")

    if data.name is not None:
        watchlist.name = data.name
    if data.description is not None:
        watchlist.description = data.description
    if data.is_default is not None and data.is_default:
        await repo.set_default(_get_user_id(user), watchlist_id)

    await session.flush()
    await session.commit()
    return WatchlistResponse.model_validate(watchlist)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete watchlist."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get(watchlist_id)

    if not watchlist or watchlist.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Watchlist not found")

    await repo.delete(watchlist_id)
    await session.commit()


@router.post("/{watchlist_id}/items", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    watchlist_id: UUID,
    instrument_id: UUID,
    notes: str | None = None,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WatchlistItemResponse:
    """Add instrument to watchlist."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get(watchlist_id)

    if not watchlist or watchlist.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Watchlist not found")

    item_repo = WatchlistItemRepository(session)
    item = await item_repo.add_item(watchlist_id, instrument_id, notes)

    if not item:
        raise HTTPException(status_code=409, detail="Instrument already in watchlist")

    # Enrich response - load instrument with exchange to avoid MissingGreenlet
    from sqlalchemy import select as _select
    from sqlalchemy.orm import selectinload as _selectinload
    from apps.api.models.market import Exchange as _Exchange, Instrument as _Instrument

    result = await session.execute(
        _select(_Instrument).options(_selectinload(_Instrument.exchange).selectinload(_Exchange.market)).where(_Instrument.id == instrument_id)
    )
    instrument = result.scalar_one_or_none()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    # Build instrument dict manually to avoid ORM serialization issues
    instrument_dict = {
        "symbol": instrument.symbol,
        "name": instrument.name,
        "exchange": instrument.exchange.code if instrument.exchange else None,
        "exchange_name": instrument.exchange.name if instrument.exchange else None,
        "market": instrument.exchange.market.code if instrument.exchange and instrument.exchange.market else None,
        "currency": instrument.currency,
        "sector": instrument.sector,
        "id": str(instrument.id),
    }

    await session.commit()
    return WatchlistItemResponse(
        id=item.id,
        watchlist_id=item.watchlist_id,
        instrument_id=item.instrument_id,
        notes=item.notes,
        sort_order=item.sort_order,
        created_at=item.created_at,
        updated_at=item.updated_at,
        instrument=instrument_dict,  # type: ignore
    )


@router.delete("/{watchlist_id}/items/{instrument_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    watchlist_id: UUID,
    instrument_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove instrument from watchlist."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get(watchlist_id)

    if not watchlist or watchlist.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Watchlist not found")

    item_repo = WatchlistItemRepository(session)
    success = await item_repo.remove_item(watchlist_id, instrument_id)

    if not success:
        raise HTTPException(status_code=404, detail="Item not found in watchlist")
    await session.commit()


@router.put("/{watchlist_id}/reorder")
async def reorder_watchlist(
    watchlist_id: UUID,
    item_ids: list[UUID],
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Reorder watchlist items."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get(watchlist_id)

    if not watchlist or watchlist.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Watchlist not found")

    item_repo = WatchlistItemRepository(session)
    success = await item_repo.reorder_items(watchlist_id, item_ids)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to reorder")
    await session.commit()

    return {"message": "Watchlist reordered successfully"}
