"""
main.py
-------
FastAPI application entry point.

- Registers CORS middleware (origins from settings)
- Registers X-API-Key auth middleware
- Mounts all route modules
- Swagger UI only enabled outside production
- Uses lifespan context manager for startup/shutdown
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.core.auth import ApiKeyMiddleware
from app.core.logging import RequestLogMiddleware, configure_json_logging
from app.routes import dashboard
from app.services.ceipal_service import start_priority_cache_loader
from app.services.dashboard_service import warm_dashboard_caches

configure_json_logging(logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# CORS — warn loudly if production has no real origins configured
# ---------------------------------------------------------------------------
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
_localhost_only = all("localhost" in o or "127.0.0.1" in o for o in _cors_origins)
if settings.app_env.lower() == "production" and _localhost_only:
    logger.warning(
        "CORS_ORIGINS is set to localhost-only values while APP_ENV=production. "
        "Browser requests from your real domain will be blocked. "
        "Set CORS_ORIGINS to your production domain in .env."
    )


# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_priority_cache_loader()
    asyncio.create_task(warm_dashboard_caches())
    yield
    # shutdown: nothing to tear down (daemon threads and tasks die with process)


# ---------------------------------------------------------------------------
# App — docs only outside production
# ---------------------------------------------------------------------------
_is_prod = settings.app_env.lower() == "production"

app = FastAPI(
    title="CEIPAL Analytics Dashboard API",
    description=(
        "Backend proxy for the CEIPAL ATS APIs. "
        "Authenticates with CEIPAL, fetches jobs / users / applicants, "
        "and returns enriched analytics data for the React dashboard."
    ),
    version="1.0.0",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware — order matters: auth runs before request logging
# ---------------------------------------------------------------------------
app.add_middleware(ApiKeyMiddleware, api_key=settings.dashboard_api_key)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type", "authorization", "x-request-id", "x-api-key"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(dashboard.router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "message": "CEIPAL Analytics API is running."}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
