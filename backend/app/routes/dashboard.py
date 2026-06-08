"""
routes/dashboard.py
-----------------
Thin route handlers for dashboard endpoints.
Calls business logic from services/dashboard_service.py.

FIX 4: Moved `import asyncio` to module top (was re-imported inside every handler).
FIX 9: stats endpoint now uses settings.stats_cache_ttl_seconds instead of
       hardcoded 60 (add stats_cache_ttl_seconds = 60 to settings.py).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.config.settings import get_settings
from app.core.response_cache import cached_response_fast
from app.services.dashboard_service import (
    build_dashboard_stats,
    build_recruiting_status,
    build_today_submissions,
    build_bdm_performance,
    build_high_priority_requirements,
    build_raw_data,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
settings = get_settings()

HIGH_PRIORITY_TTL = settings.high_priority_cache_ttl_seconds
# FIX 9: was hardcoded as 60 — now reads from settings
STATS_TTL = getattr(settings, "stats_cache_ttl_seconds", 60)


@router.get("/stats")
async def get_dashboard_stats():
    """Get dashboard statistics."""
    # FIX 4: no `import asyncio` here — already at module level
    return await cached_response_fast("dashboard:stats", STATS_TTL, build_dashboard_stats)


@router.get("/status")
async def get_recruiting_status():
    """Get recruiting status for today."""
    today = datetime.now().date()

    async def build():
        return await build_recruiting_status(today)

    return await cached_response_fast(
        f"dashboard:status:{today.isoformat()}",
        settings.status_cache_ttl_seconds,
        build,
    )


@router.get("/today-submissions")
async def get_today_submissions():
    """Get today's submissions."""
    today = datetime.now().date()

    async def build():
        return await build_today_submissions(today)

    return await cached_response_fast(
        f"dashboard:today-submissions:{today.isoformat()}",
        settings.today_submissions_cache_ttl_seconds,
        build,
    )


@router.get("/bdm-performance")
async def get_bdm_performance(period: str = Query("today", pattern="^(today|yesterday)$")):
    """Get BDM performance metrics."""
    cache_key = f"dashboard:bdm-performance:{period}:{datetime.now().date().isoformat()}"

    async def build():
        return await build_bdm_performance(period)

    return await cached_response_fast(
        cache_key,
        settings.bdm_performance_cache_ttl_seconds,
        build,
    )


@router.get("/high-priority")
async def get_high_priority_requirements(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Get high priority requirements, optionally filtered by date range."""
    p_from = _parse_date_yyyy_mm_dd(date_from)
    p_to = _parse_date_yyyy_mm_dd(date_to)

    if not p_from and not p_to:
        p_from = datetime.now().date() - timedelta(days=1)
        p_to = p_from

    cache_key = (
        f"dashboard:high-priority:"
        f"{p_from.isoformat() if p_from else ''}:"
        f"{p_to.isoformat() if p_to else ''}"
    )

    async def build():
        return await asyncio.to_thread(
            build_high_priority_requirements,
            date_from,
            date_to,
        )

    return await cached_response_fast(cache_key, HIGH_PRIORITY_TTL, build)


def _parse_date_yyyy_mm_dd(value: Optional[str]) -> Optional[datetime]:
    """Parse YYYY-MM-DD date string."""
    from app.core.utils import _parse_date_yyyy_mm_dd as parse_fn
    return parse_fn(value)


@router.get("/raw-data")
async def get_raw_data():
    """Get raw data for debugging (development only)."""
    if settings.app_env.lower() != "development":
        raise HTTPException(status_code=404, detail="Not found")

    return await asyncio.to_thread(build_raw_data)