from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.market import Exchange, Instrument
from apps.api.models.prediction import (
    Model,
    ModelVersion,
    Prediction,
    PredictionDirection,
    PredictionOutcome,
)
from apps.api.repositories.base import BaseRepository


class ModelRepository(BaseRepository[Model]):
    """Model repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Model, session)

    async def get_by_name(self, name: str) -> Model | None:
        """Get model by name."""
        return await self.get_by_field("name", name)

    async def get_active_models(self) -> list[Model]:
        """Get all active models."""
        return await self.list(filters={"is_active": True}, order_by="name")


class ModelVersionRepository(BaseRepository[ModelVersion]):
    """Model version repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(ModelVersion, session)

    async def get_by_model_version(
        self, model_id: UUID, version: str
    ) -> ModelVersion | None:
        """Get model version by model and version."""
        query = select(ModelVersion).where(
            ModelVersion.model_id == model_id,
            ModelVersion.version == version,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_versions(self, model_id: UUID) -> list[ModelVersion]:
        """Get active versions for a model."""
        return await self.list(
            filters={"model_id": model_id, "is_active": True}, order_by="version"
        )

    async def get_latest_active(self, model_id: UUID) -> ModelVersion | None:
        """Get latest active version for a model."""
        query = (
            select(ModelVersion)
            .where(
                ModelVersion.model_id == model_id,
                ModelVersion.is_active.is_(True),
            )
            .order_by(desc(ModelVersion.created_at))
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class PredictionRepository(BaseRepository[Prediction]):
    """Prediction repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Prediction, session)

    async def _champion_version_id(self) -> UUID | None:
        """Current champion version id, or None (fresh DB: no filtering).

        Production reads (latest/top/screener/alerts) scope to the champion
        so shadow and retired-challenger rows can never surface as production
        predictions. History/audit paths pass champion_only=False.
        """
        from apps.api.models.mlops import ModelChampion

        row = (
            await self.session.execute(
                select(ModelChampion.model_version_id).where(
                    ModelChampion.superseded_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        return row

    async def get_latest_for_instrument(
        self,
        instrument_id: UUID,
        horizon: str = "1d",
        model_version_id: UUID | None = None,
        champion_only: bool = True,
    ) -> Prediction | None:
        """Get latest prediction for an instrument."""
        query = (
            select(Prediction)
            .options(
                selectinload(Prediction.instrument),
                selectinload(Prediction.model_version),
                selectinload(Prediction.outcome),
            )
            .where(
                Prediction.instrument_id == instrument_id,
                Prediction.horizon == horizon,
            )
        )
        if model_version_id:
            query = query.where(Prediction.model_version_id == model_version_id)
        elif champion_only:
            champ = await self._champion_version_id()
            if champ is not None:
                query = query.where(Prediction.model_version_id == champ)
        # Deterministic tiebreak: legacy rows can share a bar timestamp with
        # different generation quality (pre-PIT wall-clock runs); always serve
        # the most recently generated row for that bar.
        query = query.order_by(
            desc(Prediction.prediction_timestamp), desc(Prediction.created_at)
        ).limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_for_bar(
        self,
        instrument_id: UUID,
        horizon: str,
        model_version_id: UUID,
        bar_timestamp: datetime,
    ) -> Prediction | None:
        """Return the existing prediction for one data bar (idempotency).

        One instrument/horizon/model/bar yields exactly one production
        prediction. Re-running inference on the same closed bar must not
        create a second row, which would double-count outcomes later.
        """
        query = (
            select(Prediction)
            .options(
                selectinload(Prediction.instrument),
                selectinload(Prediction.model_version),
                selectinload(Prediction.outcome),
            )
            .where(
                Prediction.instrument_id == instrument_id,
                Prediction.horizon == horizon,
                Prediction.model_version_id == model_version_id,
                Prediction.prediction_timestamp == bar_timestamp,
            )
            .limit(1)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_history(
        self,
        instrument_id: UUID,
        horizon: str = "1d",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[Prediction]:
        """Get prediction history for an instrument."""
        query = (
            select(Prediction)
            .options(
                selectinload(Prediction.outcome),
                selectinload(Prediction.model_version),
            )
            .where(
                Prediction.instrument_id == instrument_id,
                Prediction.horizon == horizon,
            )
        )
        if start_date:
            query = query.where(Prediction.prediction_timestamp >= start_date)
        if end_date:
            query = query.where(Prediction.prediction_timestamp <= end_date)
        query = query.order_by(
            desc(Prediction.prediction_timestamp), desc(Prediction.created_at)
        ).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending_outcomes(
        self,
        horizon: str = "1d",
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[Prediction]:
        """Get predictions that need outcome evaluation."""
        if before is None:
            before = datetime.now(UTC)

        query = (
            select(Prediction)
            .where(
                Prediction.horizon == horizon,
                Prediction.prediction_timestamp < before,
                ~Prediction.id.in_(
                    select(PredictionOutcome.prediction_id)
                ),
            )
            .order_by(Prediction.prediction_timestamp)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_top_predictions(
        self,
        horizon: str = "1d",
        direction: str | None = None,
        confidence_min: int | None = None,
        expected_return_min: Decimal | None = None,
        limit: int = 50,
        champion_only: bool = True,
    ) -> list[Prediction]:
        """Get top predictions by confidence (champion versions only)."""
        query = (
            select(Prediction)
            .options(
                selectinload(Prediction.instrument).selectinload(Instrument.exchange).selectinload(Exchange.market),
                selectinload(Prediction.model_version),
            )
            .where(
                Prediction.horizon == horizon,
                Prediction.prediction_timestamp >= datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
            )
        )
        if champion_only:
            champ = await self._champion_version_id()
            if champ is not None:
                query = query.where(Prediction.model_version_id == champ)
        if direction:
            query = query.where(Prediction.predicted_direction == direction)
        if confidence_min:
            query = query.where(Prediction.confidence >= confidence_min)
        if expected_return_min:
            query = query.where(Prediction.expected_return >= expected_return_min)
        query = query.order_by(desc(Prediction.confidence), desc(Prediction.expected_return)).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_prediction(self, **kwargs) -> Prediction:
        """Create a new prediction with validation."""
        # Validate probabilities sum to 1
        up = kwargs.get("up_probability", Decimal("0"))
        neutral = kwargs.get("neutral_probability", Decimal("0"))
        down = kwargs.get("down_probability", Decimal("0"))
        total = up + neutral + down
        if abs(total - Decimal("1")) > Decimal("0.001"):
            raise ValueError(f"Probabilities must sum to 1, got {total}")

        # Validate range
        range_lower = kwargs.get("range_lower", Decimal("0"))
        range_upper = kwargs.get("range_upper", Decimal("0"))
        if range_lower > range_upper:
            raise ValueError("range_lower must be <= range_upper")

        return await self.create(**kwargs)


class PredictionOutcomeRepository(BaseRepository[PredictionOutcome]):
    """Prediction outcome repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(PredictionOutcome, session)

    async def get_by_prediction(self, prediction_id: UUID) -> PredictionOutcome | None:
        """Get outcome for a prediction."""
        return await self.get_by_field("prediction_id", prediction_id)

    async def create_outcome(self, **kwargs) -> PredictionOutcome:
        """Create a new prediction outcome."""
        return await self.create(**kwargs)

    async def evaluate_prediction(
        self,
        prediction: Prediction,
        actual_return: Decimal,
        actual_direction: PredictionDirection,
        evaluation_price: Decimal,
        evaluation_timestamp: datetime,
    ) -> PredictionOutcome:
        """Evaluate a prediction and create outcome."""
        is_correct = prediction.predicted_direction == actual_direction

        outcome = await self.create(
            prediction_id=prediction.id,
            actual_return=actual_return,
            actual_direction=actual_direction,
            is_correct=is_correct,
            evaluation_price=evaluation_price,
            evaluation_timestamp=evaluation_timestamp,
        )
        return outcome
