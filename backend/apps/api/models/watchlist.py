import uuid

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin
from apps.api.models.market import Instrument
from apps.api.models.user import User


class Watchlist(Base, UUIDMixin, TimestampMixin):
    """Watchlist model."""

    __tablename__ = "watchlists"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="watchlists")
    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_watchlist_user_name"),
        Index("ix_watchlists_user_default", "user_id", "is_default"),
    )

    def __repr__(self) -> str:
        return f"<Watchlist(id={self.id}, name={self.name})>"


class WatchlistItem(Base, UUIDMixin, TimestampMixin):
    """Watchlist item model."""

    __tablename__ = "watchlist_items"

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")
    instrument: Mapped["Instrument"] = relationship(back_populates="watchlist_items")

    __table_args__ = (
        UniqueConstraint(
            "watchlist_id", "instrument_id", name="uq_watchlist_item_unique"
        ),
        Index("ix_watchlist_items_watchlist_order", "watchlist_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<WatchlistItem(watchlist={self.watchlist_id}, instrument={self.instrument_id})>"
