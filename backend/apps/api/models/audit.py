import enum
import uuid
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import Base, TimestampMixin, UUIDMixin
from apps.api.models.user import User


class AuditAction(str, enum.Enum):
    """Audit action enumeration."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET = "password_reset"
    TOKEN_REFRESH = "token_refresh"
    PERMISSION_CHANGE = "permission_change"
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    BACKTEST_START = "backtest_start"
    BACKTEST_COMPLETE = "backtest_complete"
    PREDICTION_REQUEST = "prediction_request"
    ALERT_TRIGGER = "alert_trigger"
    WATCHLIST_ADD = "watchlist_add"
    WATCHLIST_REMOVE = "watchlist_remove"


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Audit log model for security and compliance."""

    __tablename__ = "audit_logs"

    # User context (nullable for system actions)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Action details
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Result
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional metadata
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    user: Mapped[Optional["User"]] = relationship()
    session: Mapped[Optional["Session"]] = relationship()

    __table_args__ = (
        Index("ix_audit_logs_user_action_ts", "user_id", "action", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_ip_ts", "ip_address", "created_at"),
        Index("ix_audit_logs_success_ts", "success", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(user={self.user_id}, action={self.action}, success={self.success})>"
