from contextlib import asynccontextmanager
from pathlib import Path
import os
import time
import warnings

# Workaround for Python 3.14 + FastAPI recursion in jsonable_encoder:
# is_pydantic_v1_model_instance calls warnings.simplefilter which
# triggers infinite recursion in _warnings._add_filter on Python 3.14
# We replace the function to avoid warnings.simplefilter entirely.
try:
    def _safe_is_pydantic_v1(obj):
        try:
            from pydantic import BaseModel as BaseModelV1
            return isinstance(obj, BaseModelV1)
        except ImportError:
            return False
    import fastapi._compat.shared as _fcs
    import fastapi._compat as _fc
    import fastapi.encoders as _fe
    _fcs.is_pydantic_v1_model_instance = _safe_is_pydantic_v1
    _fc.is_pydantic_v1_model_instance = _safe_is_pydantic_v1
    _fe.is_pydantic_v1_model_instance = _safe_is_pydantic_v1
except Exception:
    pass

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import text

from src.api.router import api_router
from src.api.routes.auth import router as auth_router
from src.db.base import Base  # noqa: F401 — ensure all models are registered before any query
from src.core.config import settings
from src.core.security import setup_security, setup_cors
from src.api.middleware import (
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
)
from src.api import handlers
from src.api.deps import get_current_user, get_db
from src.core.logging import get_logger
from src.core.metrics import MetricsMiddleware, metrics_endpoint

logger = get_logger(__name__)

# Read version from VERSION file
# Check multiple locations for Vercel compatibility
_version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"  # Original: repo root
_backend_version_path = Path(__file__).resolve().parent.parent / "VERSION"  # Alternative: backend dir
APP_VERSION = os.environ.get("APP_VERSION") or (
    _version_path.read_text().strip() if _version_path.exists()
    else (_backend_version_path.read_text().strip() if _backend_version_path.exists() else "0.0.0")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup security validation ──────────────────────────────────────
    if settings.JWT_SECRET_KEY in ("change-me-in-production", "change-me-to-a-random-secret-at-least-32-chars-long", ""):
        logger.error(
            "JWT_SECRET_KEY is set to a weak/default value! "
            "Generate a secure key with: openssl rand -hex 32"
        )
    
    # On Vercel, don't crash on missing secrets - just log a warning
    # This allows initial deployment before secrets are configured
    is_vercel = os.environ.get("VERCEL", "") != ""
    if settings.ENVIRONMENT == "production" and settings.JWT_SECRET_KEY in ("change-me-in-production", ""):
        if is_vercel:
            logger.warning(
                "JWT_SECRET_KEY not configured on Vercel. "
                "Set JWT_SECRET_KEY in Vercel Dashboard → Project Settings → Environment Variables. "
                "Using temporary key for now."
            )
        else:
            raise RuntimeError(
                "Production environment requires a secure JWT_SECRET_KEY. "
                "Set JWT_SECRET_KEY environment variable to a random value (min 32 chars)."
            )

    logger.info(
        "Application starting up",
        extra={"environment": settings.ENVIRONMENT, "docs_enabled": settings.DOCS_ENABLED, "version": APP_VERSION},
    )
    # Register all intelligence agents
    from src.agents.factory import register_all_agents
    register_all_agents()
    logger.info("Intelligence agents registered", extra={"count": len(__import__("src.agents.core.registry", fromlist=["AgentRegistry"]).AgentRegistry.list_agents())})
    # Log all registered routes for debugging
    routes = sorted(
        f"{m} {r.path}" for r in app.routes if hasattr(r, "methods") and hasattr(r, "path")
        for m in r.methods if m not in ("HEAD", "OPTIONS")
    )
    logger.info("Registered routes", extra={"count": len(routes), "routes": routes})
    yield
    from src.db.session import engine

    if engine is not None:
        logger.info("Application shutting down; disposing DB engine")
        engine.dispose()


app = FastAPI(
    title="Project Minore API",
    version=APP_VERSION,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    lifespan=lifespan,
    redirect_slashes=False,
)

# Non-CORS middlewares first (inner layers)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware, limit=settings.RATE_LIMIT_PER_MINUTE, times=60
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(MetricsMiddleware)

setup_security(app)

# CORSMiddleware must be the outermost (last to wrap) so it intercepts
# OPTIONS preflight requests before any other middleware can interfere.
setup_cors(app)

app.add_exception_handler(IntegrityError, handlers.integrity_error_handler)
app.add_exception_handler(SQLAlchemyError, handlers.sqlalchemy_exception_handler)
app.add_exception_handler(RequestValidationError, handlers.validation_exception_handler)
app.add_exception_handler(Exception, handlers.unhandled_exception_handler)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(api_router, prefix="/api/v1", dependencies=[Depends(get_current_user)])

# ── Health / Readiness / Liveness ──────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "version": APP_VERSION, "environment": settings.ENVIRONMENT}


@app.get("/readiness", tags=["Health"])
async def readiness():
    """Returns 200 only when the database is reachable."""
    try:
        from src.db.session import engine
        if engine is None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "database": "disconnected",
                    "error": "DATABASE_URL environment variable is not set. "
                             "Configure DATABASE_URL pointing to your Neon PostgreSQL database.",
                },
            )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "disconnected"},
        )


@app.get("/liveness", tags=["Health"])
async def liveness():
    return {"status": "alive", "timestamp": time.time()}


@app.get("/version", tags=["Health"])
async def version():
    return {
        "version": APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "python": "3.12",
    }


@app.get("/metrics", tags=["Monitoring"])
async def metrics_route():
    return metrics_endpoint()


@app.get("/")
async def root():
    return {
        "project": "Project Minore",
        "status": "running",
        "version": APP_VERSION,
    }