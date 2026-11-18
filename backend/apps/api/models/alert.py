import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin
from apps.api.models.market import Instrument
from apps.api.models.user import User


class AlertType(str, enum.Enum):
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


class AlertCondition(str, enum.Enum):
    """Alert condition enumeration."""

    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN_OR_EQUAL = "lte"
    EQUAL = "eq"
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class AlertStatus(str, enum.Enum):
    """Alert status enumeration."""

    ACTIVE = "active"
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    EXPIRED = "expired"
    DISABLED = "disabled"


class Alert(Base, UUIDMixin, TimestampMixin):
    """Alert model."""

    __tablename__ = "alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Alert configuration
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    alert_type: Mapped[AlertType] = mapped_column(String(30), nullable=False)
    condition: Mapped[AlertCondition] = mapped_column(
        String(30), nullable=False
    )
    target_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    # Optional secondary value (e.g., for range alerts)
    secondary_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )

    # Status
    status: Mapped[AlertStatus] = mapped_column(
        String(30), default=AlertStatus.ACTIVE, nullable=False
    )

    # Timing
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Notification settings
    notify_email: Mapped[bool] = mapped_column(default=True, nullable=False)
    notify_push: Mapped[bool] = mapped_column(default=False, nullable=False)
    notify_in_app: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="alerts")
    instrument: Mapped["Instrument"] = relationship()
    triggers: Mapped[list["AlertTrigger"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_alerts_user_status", "user_id", "status"),
        Index("ix_alerts_instrument_type", "instrument_id", "alert_type"),
        Index("ix_alerts_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, type={self.alert_type}, status={self.status})>"


class AlertTrigger(Base, UUIDMixin, TimestampMixin):
    """Alert trigger record."""

    __tablename__ = "alert_triggers"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Trigger details
    triggered_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)

    # Notification status
    email_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    push_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    in_app_sent: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    alert: Mapped["Alert"] = relationship(back_populates="triggers")

    __table_args__ = (
        Index("ix_alert_triggers_alert_ts", "alert_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AlertTrigger(alert={self.alert_id}, value={self.triggered_value})>"
