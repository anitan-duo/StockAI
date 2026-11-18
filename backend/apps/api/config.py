import os
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Test-mode override: when STOCKAI_TEST_MODE is set, DATABASE_URL from the
# environment wins over .env so conftests/orchestrator can force SQLite
# (unit) or an isolated *_test Postgres DB (integration). In production
# (no STOCKAI_TEST_MODE), .env is honoured as before. This is resolved
# here — before any other module reads settings — so the engine singleton
# in apps.api.database is deterministically bound.
_TEST_MODE = os.environ.get("STOCKAI_TEST_MODE", "").strip().lower()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env" if not _TEST_MODE else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://stockai:stockai@localhost:5432/stockai",
        validation_alias="DATABASE_URL",
    )

    # Valkey (Redis-compatible)
    valkey_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="VALKEY_URL",
    )
    # Keep REDIS_URL as alias for backwards compatibility
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )

    # Security
    secret_key: str = Field(
        default="your-secret-key-change-in-production-min-32-chars",
        validation_alias="SECRET_KEY",
    )

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        if len(v) < 32 or "change-in-production" in v:
            raise ValueError("SECRET_KEY must be set to a unique value of at least 32 characters")
        return v
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(
        default=7, validation_alias="REFRESH_TOKEN_EXPIRE_DAYS"
    )

    # API
    api_v1_prefix: str = Field(default="/api/v1", validation_alias="API_V1_PREFIX")
    project_name: str = Field(default="StockAI", validation_alias="PROJECT_NAME")
    debug: bool = Field(default=False, validation_alias="DEBUG")

    # Trusted hosts (Host-header defence; comma-separated or JSON array).
    # Defaults cover local dev + testclient; production must override.
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default=["localhost", "127.0.0.1", "testserver"],
        validation_alias="ALLOWED_HOSTS",
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def _parse_allowed_hosts(cls, v: object) -> list[str]:
        """Accept JSON-array or comma-separated host list (NoDecode)."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                import json

                try:
                    parsed = json.loads(v)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"ALLOWED_HOSTS JSON parse error: {exc}") from exc
                return [str(x).strip() for x in parsed if str(x).strip()]
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        if v is None:
            return []
        return [str(v).strip()]

    # CORS
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://localhost:3001"],
        validation_alias="BACKEND_CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        """Accept JSON-array or comma-separated CORS origins.

        Annotated with `NoDecode` so pydantic-settings hands this
        validator the raw string from the environment instead of
        JSON-decoding it first (which would raise SettingsError on
        the comma form used in `.env.example`). Modes: list stays;
        `[...]` JSON decodes; a bare string splits on commas.
        """
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                import json

                try:
                    parsed = json.loads(v)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"BACKEND_CORS_ORIGINS JSON parse error: {exc}") from exc
                return [str(x).strip() for x in parsed if str(x).strip()]
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        if v is None:
            return []
        return [str(v).strip()]

    # Market Data Provider
    google_finance_enabled: bool = Field(
        default=False, validation_alias="GOOGLE_FINANCE_ENABLED"
    )
    google_finance_api_key: str | None = Field(
        default=None, validation_alias="GOOGLE_FINANCE_API_KEY"
    )
    google_finance_rate_limit: int = Field(
        default=100, validation_alias="GOOGLE_FINANCE_RATE_LIMIT"
    )

    # Finnhub Provider
    finnhub_enabled: bool = Field(
        default=False, validation_alias="FINNHUB_ENABLED"
    )
    finnhub_api_key: str | None = Field(
        default=None, validation_alias="FINNHUB_API_KEY"
    )
    finnhub_rate_limit: int = Field(
        default=60, validation_alias="FINNHUB_RATE_LIMIT"
    )

    # TwelveData Provider
    twelvedata_enabled: bool = Field(
        default=False, validation_alias="TWELVEDATA_ENABLED"
    )
    twelvedata_api_key: str | None = Field(
        default=None, validation_alias="TWELVEDATA_API_KEY"
    )
    twelvedata_rate_limit: int = Field(
        default=800, validation_alias="TWELVEDATA_RATE_LIMIT"
    )

    # Alpha Vantage Provider
    alphavantage_enabled: bool = Field(
        default=False, validation_alias="ALPHAVANTAGE_ENABLED"
    )
    alphavantage_api_key: str | None = Field(
        default=None, validation_alias="ALPHAVANTAGE_API_KEY"
    )
    alphavantage_rate_limit: int = Field(
        default=5, validation_alias="ALPHAVANTAGE_RATE_LIMIT"
    )

    # Yahoo Finance Provider
    yahoo_finance_enabled: bool = Field(
        default=False, validation_alias="YAHOO_FINANCE_ENABLED"
    )
    yahoo_finance_rate_limit: int = Field(
        default=100, validation_alias="YAHOO_FINANCE_RATE_LIMIT"
    )

    # Ingestion
    ingestion_interval_minutes: int = Field(
        default=5, validation_alias="INGESTION_INTERVAL_MINUTES"
    )
    ingestion_batch_size: int = Field(
        default=100, validation_alias="INGESTION_BATCH_SIZE"
    )
    ingestion_retry_attempts: int = Field(
        default=3, validation_alias="INGESTION_RETRY_ATTEMPTS"
    )
    ingestion_timeout_seconds: int = Field(
        default=30, validation_alias="INGESTION_TIMEOUT_SECONDS"
    )

    # Scheduler (asyncio tasks in API lifespan; Valkey-locked)
    scheduler_enabled: bool = Field(default=True, validation_alias="SCHEDULER_ENABLED")
    scheduler_quotes_seconds: int = Field(default=300, validation_alias="SCHEDULER_QUOTES_SECONDS")
    scheduler_alerts_seconds: int = Field(default=300, validation_alias="SCHEDULER_ALERTS_SECONDS")
    scheduler_predictions_seconds: int = Field(default=3600, validation_alias="SCHEDULER_PREDICTIONS_SECONDS")
    scheduler_history_seconds: int = Field(default=21600, validation_alias="SCHEDULER_HISTORY_SECONDS")
    scheduler_outcomes_seconds: int = Field(default=3600, validation_alias="SCHEDULER_OUTCOMES_SECONDS")
    scheduler_monitoring_seconds: int = Field(default=3600, validation_alias="SCHEDULER_MONITORING_SECONDS")
    scheduler_evolution_seconds: int = Field(default=86400, validation_alias="SCHEDULER_EVOLUTION_SECONDS")
    scheduler_shadow_seconds: int = Field(default=3600, validation_alias="SCHEDULER_SHADOW_SECONDS")
    scheduler_ranking_seconds: int = Field(default=21600, validation_alias="SCHEDULER_RANKING_SECONDS")

    # Logging
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(default="json", validation_alias="LOG_FORMAT")

    # Auth rate limiting (Valkey-backed throttles; fail open if Valkey down)
    auth_login_max_attempts: int = Field(
        default=30, validation_alias="AUTH_LOGIN_MAX_ATTEMPTS"
    )
    auth_register_max_attempts: int = Field(
        default=30, validation_alias="AUTH_REGISTER_MAX_ATTEMPTS"
    )
    auth_throttle_window_seconds: int = Field(
        default=900, validation_alias="AUTH_THROTTLE_WINDOW_SECONDS"
    )

    # Prediction
    prediction_horizon_hours: int = Field(
        default=24, validation_alias="PREDICTION_HORIZON_HOURS"
    )
    prediction_model_version: str = Field(
        default="ensemble-v1.0", validation_alias="PREDICTION_MODEL_VERSION"
    )


settings = Settings()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
