import json
import logging
import re
import sys
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from apps.api.config import settings
from apps.api.database import close_db, init_db

# Request ID is bound in middleware so exception handlers can correlate
# client responses with detailed server-side logs.
_current_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# Patterns that must never reach a client response body. A message matching
# ANY of these is replaced wholesale — substring redaction cannot be trusted
# to catch every variant, so a sensitive message is never echoed in part.
_SENSITIVE_PATTERNS = [
    # artifact/secret file paths (extension-anchored)
    re.compile(r"/[\w./-]{2,}\.(?:pkl|db|sqlite3?|env|pem|key|passwd|shadow|htpasswd)\b", re.I),
    # absolute internal paths (extension-less included: /etc/passwd, /app/x/model.pkl)
    re.compile(r"/(?:etc|app|srv|home|root|var|usr|opt|tmp|mnt|proc|sys)/[\w./-]*"),
    # SQL fragments (keyword pairs or Postgres catalog errors)
    re.compile(r"\b(?:select|insert|update|delete|drop|alter|create|truncate)\b.{0,60}\b(?:from|into|table|set|where|values)\b", re.I | re.S),
    re.compile(r'\brelation\s+"[\w.]+"\s+does not exist', re.I),
    re.compile(r"\b(?:syntax error|psql:|pgcode|psycopg\b|cursor|execute\()", re.I),
    # connection strings / DSNs
    re.compile(r"\b(?:postgres(?:ql)?|mysql|redis|amqp|mongodb|mssql|jdbc):\/\/[^\s'\"]+", re.I),
    # driver / library / traceback internals
    re.compile(r"\b(?:sqlalchemy|asyncpg|aiosqlite|psycopg\d*|pymysql|httpx?|aiohttp|valkey|redis-py)\b", re.I),
    re.compile(r"\b(?:OperationalError|ProgrammingError|IntegrityError|InterfaceError|Traceback)\b"),
    re.compile(r'\bFile\s+"[^"]+",\s+line\s+\d+'),
    re.compile(r"\bline\s+\d+,\s+in\s+\w+"),
    # server config / secret-bearing identifiers
    re.compile(r"\b(?:SECRET_KEY|DATABASE_URL|ALLOWED_HOSTS|CORS_ORIGINS|AUTH_THROTTLE)\w*\b", re.I),
    # provider/key material (with or without an assignment separator)
    re.compile(r"\b(?:api[_-]?key|apikey|private[_-]?key|connection string|dsn)\b", re.I),
    # secret assignments
    re.compile(r"\b(?:password|passwd|secret|token)\w*\b\s*[:=]", re.I),
]

# Same intent, but for the internal log copy: redact values, keep context.
_REDACT_ASSIGN = re.compile(r"(\b(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|dsn)\b\s*[:=]\s*)(\S+)", re.I)
_REDACT_URI_CREDS = re.compile(r"(\b\w+://)([^/\s:]+):([^/\s@]+)@")


def _safe_detail(exc: ValueError | PermissionError) -> str:
    """Client-safe detail: keep user-input echoes, drop internals wholesale."""
    text = str(exc)
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            return "Request could not be processed. Reference ID has been logged."
    return text


def _redact_for_log(text: str) -> str:
    """Redact credential-shaped values from the internal log copy."""
    text = _REDACT_ASSIGN.sub(r"\1***", text)
    text = _REDACT_URI_CREDS.sub(r"\1***:***@", text)
    return text


def _configure_logging() -> None:
    """Wire LOG_LEVEL/LOG_FORMAT (previously declared but never applied)."""
    level_name = (settings.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if (settings.log_format or "json").lower() == "json":
        class _Json(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload = {
                    "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                if getattr(record, "request_id", None):
                    payload["request_id"] = record.request_id
                if record.exc_info:
                    payload["exc"] = self.formatException(record.exc_info)
                return json.dumps(payload)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_Json())
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(level)
    else:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_configure_logging()
from apps.api.routes import (
    alerts,
    analytics,
    auth,
    backtests,
    health,
    markets,
    mlops,
    predictions,
    rankings,
    scenarios,
    screener,
    training,
    watchlist,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    scheduler = None
    if settings.scheduler_enabled:
        from services.scheduler import Scheduler

        scheduler = Scheduler(
            quotes_every_s=settings.scheduler_quotes_seconds,
            alerts_every_s=settings.scheduler_alerts_seconds,
            predictions_every_s=settings.scheduler_predictions_seconds,
            history_every_s=settings.scheduler_history_seconds,
            outcomes_every_s=settings.scheduler_outcomes_seconds,
            monitoring_every_s=settings.scheduler_monitoring_seconds,
            evolution_every_s=settings.scheduler_evolution_seconds,
            shadow_every_s=settings.scheduler_shadow_seconds,
            rankings_every_s=settings.scheduler_ranking_seconds,
        )
        scheduler.start()
        app.state.scheduler = scheduler
    yield
    # Shutdown
    if scheduler is not None:
        await scheduler.stop()
    await close_db()


app = FastAPI(
    title=settings.project_name,
    description="StockAI - AI-powered stock market analysis platform API",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# Trusted hosts — reject unknown Host headers (400) before routing.
# Runs outermost (added first) so bad hosts never reach the app.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts or ["*"],
)

# GZip responses (charts/history payloads compress well)
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers (defence-in-depth; API returns JSON only)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time + request ID headers; structured access log (no secrets)."""
    import logging
    import time
    import uuid

    start_time = time.time()
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    token = _current_request_id.set(request_id)
    try:
        response = await call_next(request)
    except Exception:
        logging.getLogger("stockai.api").exception(
            "request failed",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )
        raise
    finally:
        _current_request_id.reset(token)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id
    logging.getLogger("stockai.api").info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_s": round(process_time, 4),
        },
    )
    return response


# Exception handlers
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Sanitized 400: user-facing validation text only, full detail to logs.

    ``str(exc)`` can carry internal paths, SQL fragments, provider/connection
    detail, or artifact locations depending on the raise site; ``_safe_detail``
    classifies and suppresses those wholesale. The unsanitized message is
    logged with the request ID for operator correlation.
    """
    import logging

    request_id = _current_request_id.get()
    safe = _safe_detail(exc)
    if safe != str(exc):
        logging.getLogger("stockai.api").warning(
            "value_error sanitized",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "detail": str(exc),
            },
        )
    return JSONResponse(
        status_code=400,
        headers={"X-Request-ID": request_id or ""},
        content={"detail": safe, "type": "validation_error"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Generic 500: generic detail only, preserve request ID for correlation."""
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": _current_request_id.get() or request.headers.get("x-request-id", "")},
        content={"detail": "Internal server error", "type": "internal_error"},
    )


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    """Sanitized 403 — PermissionError messages may carry internal detail."""
    import logging

    request_id = _current_request_id.get()
    safe = _safe_detail(exc)
    if safe != str(exc):
        logging.getLogger("stockai.api").warning(
            "permission_error sanitized",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "detail": str(exc),
            },
        )
    return JSONResponse(
        status_code=403,
        headers={"X-Request-ID": request_id or ""},
        content={"detail": safe, "type": "permission_error"},
    )


# Include routers
app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(markets.router, prefix=settings.api_v1_prefix)
app.include_router(predictions.router, prefix=settings.api_v1_prefix)
app.include_router(rankings.router, prefix=settings.api_v1_prefix)
app.include_router(screener.router, prefix=settings.api_v1_prefix)
app.include_router(training.router, prefix=settings.api_v1_prefix)
app.include_router(watchlist.router, prefix=settings.api_v1_prefix)
app.include_router(alerts.router, prefix=settings.api_v1_prefix)
app.include_router(backtests.router, prefix=settings.api_v1_prefix)
app.include_router(mlops.router, prefix=settings.api_v1_prefix)
app.include_router(scenarios.router, prefix=settings.api_v1_prefix)
app.include_router(analytics.router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.project_name,
        "version": "0.1.0",
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
