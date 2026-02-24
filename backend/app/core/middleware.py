"""
FastAPI exception handlers and middleware.

Converts all AppError subclasses and unexpected exceptions into
consistent JSON responses. Injects correlation IDs into every request.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.errors import AppError, ErrorCode

_log = structlog.get_logger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a correlation ID into every request/response cycle.

    The ID is taken from the ``X-Correlation-ID`` request header if
    present; otherwise a new UUID4 is generated. The ID is bound to
    structlog context so that all log statements within the request
    automatically include it.
    """

    HEADER = "X-Correlation-ID"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = request.headers.get(self.HEADER) or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        response.headers[self.HEADER] = correlation_id
        _log.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security-relevant HTTP response headers to every response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cache-Control"] = "no-store"
        return response


# ── Exception handlers ────────────────────────────────────────────────── #


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert a domain AppError to a structured JSON response."""
    _log.warning(
        "application_error",
        error_code=exc.code.value,
        message=exc.message,
        http_status=exc.http_status,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(),
        headers={"X-Correlation-ID": getattr(request.state, "correlation_id", "")},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected exceptions.

    Never leaks internal detail to the client.
    """
    _log.exception("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected internal error occurred.",
                "detail": {},
            }
        },
        headers={"X-Correlation-ID": getattr(request.state, "correlation_id", "")},
    )
