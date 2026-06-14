"""
core/auth.py
------------
X-API-Key authentication middleware.

In production, set DASHBOARD_API_KEY to a strong random secret.
All /dashboard/* requests must include the header:
    X-API-Key: <your-key>

If DASHBOARD_API_KEY is empty the middleware is a no-op (dev mode only).
Generate a key with: python -c "import secrets; print(secrets.token_hex(32))"
"""

from __future__ import annotations

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_BYPASS_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self._api_key = api_key
        if not api_key:
            logger.warning(
                "DASHBOARD_API_KEY is not set — API authentication is DISABLED. "
                "Set this variable before deploying to production."
            )

    async def dispatch(self, request: Request, call_next):
        # No key configured → open access (dev convenience)
        if not self._api_key:
            return await call_next(request)

        # Health/docs paths are public
        if request.url.path in _BYPASS_PATHS:
            return await call_next(request)

        provided = request.headers.get("x-api-key", "")
        if provided != self._api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing X-API-Key header"},
            )

        return await call_next(request)
