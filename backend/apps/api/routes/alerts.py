from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_session
from apps.api.models.alert import AlertCondition, AlertStatus, AlertType
from apps.api.repositories.alert import AlertRepository, AlertTriggerRepository
from apps.api.repositories.market import InstrumentRepository
from apps.api.routes.auth import get_current_user

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
from packages.schemas.alert import (
    AlertCreate,
    AlertResponse,
    AlertTriggerResponse,
    AlertUpdate,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AlertResponse]:
    """List user's alerts."""
    repo = AlertRepository(session)
    alerts = await repo.get_user_alerts(_get_user_id(user), status_filter)
    for a in alerts:
        try:
            session.expunge(a)
        except Exception:
            pass
        a.instrument = None  # type: ignore
    return [AlertResponse.model_validate(a) for a in alerts]


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    data: AlertCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    """Create a new alert."""
    # Validate instrument exists
    instrument_repo = InstrumentRepository(session)
    instrument = await instrument_repo.get(data.instrument_id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    repo = AlertRepository(session)
    alert = await repo.create_alert(
        user_id=_get_user_id(user),
        instrument_id=data.instrument_id,
        name=data.name,
        alert_type=data.alert_type,
        condition=data.condition,
        target_value=data.target_value,
        secondary_value=data.secondary_value,
        expires_at=data.expires_at,
        notify_email=data.notify_email,
        notify_push=data.notify_push,
        notify_in_app=data.notify_in_app,
    )
    await session.commit()
    try:
        session.expunge(alert)
    except Exception:
        pass
    alert.instrument = None  # type: ignore
    return AlertResponse.model_validate(alert)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    """Get alert by ID."""
    repo = AlertRepository(session)
    alert = await repo.get(alert_id)

    if not alert or alert.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Alert not found")

    try:
        session.expunge(alert)
    except Exception:
        pass
    alert.instrument = None  # type: ignore
    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: UUID,
    data: AlertUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    """Update alert."""
    repo = AlertRepository(session)
    alert = await repo.get(alert_id)

    if not alert or alert.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Alert not found")

    if data.name is not None:
        alert.name = data.name
    if data.target_value is not None:
        alert.target_value = data.target_value
    if data.secondary_value is not None:
        alert.secondary_value = data.secondary_value
    if data.expires_at is not None:
        alert.expires_at = data.expires_at
    if data.notify_email is not None:
        alert.notify_email = data.notify_email
    if data.notify_push is not None:
        alert.notify_push = data.notify_push
    if data.notify_in_app is not None:
        alert.notify_in_app = data.notify_in_app
    if data.status is not None:
        alert.status = data.status

    await session.flush()
    await session.commit()
    try:
        session.expunge(alert)
    except Exception:
        pass
    alert.instrument = None  # type: ignore
    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    """Acknowledge a triggered alert."""
    repo = AlertRepository(session)
    alert = await repo.get(alert_id)

    if not alert or alert.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.status != AlertStatus.TRIGGERED:
        raise HTTPException(status_code=400, detail="Alert is not triggered")

    await repo.acknowledge(alert_id)
    await session.commit()
    await session.refresh(alert)
    try:
        session.expunge(alert)
    except Exception:
        pass
    alert.instrument = None  # type: ignore
    return AlertResponse.model_validate(alert)


@router.post("/{alert_id}/disable", response_model=AlertResponse)
async def disable_alert(
    alert_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertResponse:
    """Disable an alert."""
    repo = AlertRepository(session)
    alert = await repo.get(alert_id)

    if not alert or alert.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Alert not found")

    await repo.disable(alert_id)
    await session.commit()
    await session.refresh(alert)
    try:
        session.expunge(alert)
    except Exception:
        pass
    alert.instrument = None  # type: ignore
    return AlertResponse.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete alert."""
    repo = AlertRepository(session)
    alert = await repo.get(alert_id)

    if not alert or alert.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Alert not found")

    await repo.delete(alert_id)
    await session.commit()


@router.get("/{alert_id}/triggers", response_model=list[AlertTriggerResponse])
async def get_alert_triggers(
    alert_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AlertTriggerResponse]:
    """Get alert trigger history."""
    repo = AlertRepository(session)
    alert = await repo.get(alert_id)

    if not alert or alert.user_id != _get_user_id(user):
        raise HTTPException(status_code=404, detail="Alert not found")

    trigger_repo = AlertTriggerRepository(session)
    triggers = await trigger_repo.get_alert_triggers(alert_id, limit)
    return [AlertTriggerResponse.model_validate(t) for t in triggers]


@router.get("/types/available")
async def get_available_alert_types() -> dict:
    """Get available alert types and conditions."""
    return {
        "types": [
            {"value": t.value, "label": t.value.replace("_", " ").title()}
            for t in AlertType
        ],
        "conditions": [
            {"value": c.value, "label": c.value.replace("_", " ").title()}
            for c in AlertCondition
        ],
    }
