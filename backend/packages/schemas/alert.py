from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import ConfigDict, Field

from packages.schemas.base import BaseSchema


class AlertType(str):
    """Alert type enumeration."""

    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CHANGE_PCT = "price_change_pct"
    VOLUME_ABOVE = "volume_above"
    PREDICTION_PROBABILITY = "prediction_probability"
    EXPECTED_RETURN = "expected_return"
    CONFIDENCE = "confidence"
    RSI_ABOVE = "rsi_above"
    RSI_BELOW = "rsi_below"


class AlertCondition(str):
    """Alert condition enumeration."""

    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"
    EQUAL = "eq"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class AlertStatus(str):
    """Alert status enumeration."""

    ACTIVE = "active"
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    EXPIRED = "expired"
    DISABLED = "disabled"


class AlertBase(BaseSchema):
    """Base alert schema."""

    instrument_id: UUID
    name: str = Field(..., max_length=100)
    alert_type: str = Field(..., pattern="^(price_above|price_below|price_change_pct|volume_above|prediction_probability|expected_return|confidence|rsi_above|rsi_below)$")
    condition: str = Field(..., pattern="^(gt|lt|gte|lte|eq|crosses_above|crosses_below)$")
    target_value: Decimal
    secondary_value: Decimal | None = None
    expires_at: datetime | None = None
    notify_email: bool = True
    notify_push: bool = False
    notify_in_app: bool = True


class AlertCreate(AlertBase):
    """Alert creation schema."""

    pass


class AlertUpdate(BaseSchema):
    """Alert update schema."""

    name: str | None = Field(default=None, max_length=100)
    target_value: Decimal | None = None
    secondary_value: Decimal | None = None
    expires_at: datetime | None = None
    notify_email: bool | None = None
    notify_push: bool | None = None
    notify_in_app: bool | None = None
    status: str | None = Field(
        default=None, pattern="^(active|triggered|acknowledged|expired|disabled)$"
    )


class AlertResponse(AlertBase):
    """Alert response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    user_id: UUID
    status: str
    triggered_at: datetime | None = None
    acknowledged_at: datetime | None = None
    instrument: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class AlertTriggerResponse(BaseSchema):
    """Alert trigger response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    alert_id: UUID
    triggered_value: Decimal
    message: str
    email_sent: bool
    push_sent: bool
    in_app_sent: bool

    model_config = ConfigDict(from_attributes=True)
