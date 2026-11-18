from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository class with common CRUD operations."""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: UUID) -> ModelType | None:
        """Get entity by ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_field(
        self, field: str, value: Any, include_deleted: bool = False
    ) -> ModelType | None:
        """Get entity by a specific field."""
        column = getattr(self.model, field)
        query = select(self.model).where(column == value)
        if not include_deleted and hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted.is_(False))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        filters: dict[str, Any] | None = None,
        include_deleted: bool = False,
    ) -> list[ModelType]:
        """List entities with pagination and filtering."""
        query = select(self.model)

        if not include_deleted and hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted.is_(False))

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    column = getattr(self.model, key)
                    if isinstance(value, list):
                        query = query.where(column.in_(value))
                    else:
                        query = query.where(column == value)

        if order_by and hasattr(self.model, order_by):
            query = query.order_by(getattr(self.model, order_by).desc())
        elif hasattr(self.model, "created_at"):
            query = query.order_by(self.model.created_at.desc())

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count entities with optional filters."""
        from sqlalchemy import func

        query = select(func.count(self.model.id))

        if hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted.is_(False))

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    column = getattr(self.model, key)
                    if isinstance(value, list):
                        query = query.where(column.in_(value))
                    else:
                        query = query.where(column == value)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(self, **kwargs) -> ModelType:
        """Create new entity."""
        entity = self.model(**kwargs)
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, id: UUID, **kwargs) -> ModelType | None:
        """Update entity by ID."""
        entity = await self.get(id)
        if not entity:
            return None
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, id: UUID, soft: bool = True) -> bool:
        """Delete entity by ID."""
        entity = await self.get(id)
        if not entity:
            return False

        if soft and hasattr(entity, "soft_delete"):
            entity.soft_delete()
        else:
            await self.session.delete(entity)

        await self.session.flush()
        return True

    async def exists(self, id: UUID) -> bool:
        """Check if entity exists."""
        from sqlalchemy import func

        query = select(func.count(self.model.id)).where(self.model.id == id)
        if hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted.is_(False))
        result = await self.session.execute(query)
        return result.scalar_one() > 0
