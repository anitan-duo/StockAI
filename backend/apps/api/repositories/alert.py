from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.alert import Alert, AlertStatus, AlertTrigger
from apps.api.models.market import Exchange, Instrument
from apps.api.repositories.base import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    """Alert repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Alert, session)

    async def get_user_alerts(
        self,
        user_id: UUID,
        status: str | None = None,
        include_instrument: bool = True,
    ) -> list[Alert]:
        """Get all alerts for a user."""
        query = select(Alert).where(Alert.user_id == user_id)
        if status:
            query = query.where(Alert.status == status)
        if include_instrument:
            query = query.options(
                selectinload(Alert.instrument).selectinload(Instrument.exchange).selectinload(Exchange.market)
            )
        query = query.order_by(desc(Alert.created_at))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_alerts_for_instrument(
        self, instrument_id: UUID, alert_type: str | None = None
    ) -> list[Alert]:
        """Get active alerts for an instrument."""
        query = select(Alert).where(
            Alert.instrument_id == instrument_id,
            Alert.status == AlertStatus.ACTIVE,
        )
        if alert_type:
            query = query.where(Alert.alert_type == alert_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_alerts_to_evaluate(
        self, alert_type: str | None = None, limit: int = 100
    ) -> list[Alert]:
        """Get alerts that need evaluation."""
        query = (
            select(Alert)
            .options(selectinload(Alert.instrument))
            .where(
                Alert.status == AlertStatus.ACTIVE,
                (Alert.expires_at.is_(None)) | (Alert.expires_at > datetime.now(UTC)),
            )
        )
        if alert_type:
            query = query.where(Alert.alert_type == alert_type)
        query = query.limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_alert(
        self,
        user_id: UUID,
        instrument_id: UUID,
        name: str,
        alert_type: str,
        condition: str,
        target_value: float,
        secondary_value: float | None = None,
        expires_at: datetime | None = None,
        notify_email: bool = True,
        notify_push: bool = False,
        notify_in_app: bool = True,
    ) -> Alert:
        """Create a new alert."""
        return await self.create(
            user_id=user_id,
            instrument_id=instrument_id,
            name=name,
            alert_type=alert_type,
            condition=condition,
            target_value=target_value,
            secondary_value=secondary_value,
            expires_at=expires_at,
            notify_email=notify_email,
            notify_push=notify_push,
            notify_in_app=notify_in_app,
        )

    async def update_status(
        self, alert_id: UUID, status: str, triggered_at: datetime | None = None
    ) -> bool:
        """Update alert status."""
        alert = await self.get(alert_id)
        if not alert:
            return False
        alert.status = status
        if triggered_at:
            alert.triggered_at = triggered_at
        await self.session.flush()
        return True

    async def acknowledge(self, alert_id: UUID) -> bool:
        """Acknowledge a triggered alert."""
        alert = await self.get(alert_id)
        if not alert or alert.status != AlertStatus.TRIGGERED:
            return False
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def disable(self, alert_id: UUID) -> bool:
        """Disable an alert."""
        alert = await self.get(alert_id)
        if not alert:
            return False
        alert.status = AlertStatus.DISABLED
        await self.session.flush()
        return True

    async def cleanup_expired(self) -> int:
        """Mark expired alerts."""
        from sqlalchemy import update

        result = await self.session.execute(
            update(Alert)
            .where(
                Alert.status == AlertStatus.ACTIVE,
                Alert.expires_at.is_not(None),
                Alert.expires_at < datetime.now(UTC),
            )
            .values(status=AlertStatus.EXPIRED)
        )
        return result.rowcount


class AlertTriggerRepository(BaseRepository[AlertTrigger]):
    """Alert trigger repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(AlertTrigger, session)

    async def create_trigger(
        self,
        alert_id: UUID,
        triggered_value: float,
        message: str,
    ) -> AlertTrigger:
        """Record an alert trigger."""
        return await self.create(
            alert_id=alert_id,
            triggered_value=triggered_value,
            message=message,
        )

    async def mark_notifications_sent(
        self,
        trigger_id: UUID,
        email: bool = False,
        push: bool = False,
        in_app: bool = False,
    ) -> bool:
        """Mark notifications as sent for a trigger."""
        trigger = await self.get(trigger_id)
        if not trigger:
            return False
        if email:
            trigger.email_sent = True
        if push:
            trigger.push_sent = True
        if in_app:
            trigger.in_app_sent = True
        await self.session.flush()
        return True

    async def get_alert_triggers(
        self, alert_id: UUID, limit: int = 50
    ) -> list[AlertTrigger]:
        """Get triggers for an alert."""
        query = (
            select(AlertTrigger)
            .where(AlertTrigger.alert_id == alert_id)
            .order_by(desc(AlertTrigger.created_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
