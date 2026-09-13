"""Problem+json (RFC 9457) error responses."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = structlog.get_logger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ApiError(Exception):
    status: int = 400
    title: str = "Bad Request"

    def __init__(self, detail: str, *, status: int | None = None, **extra: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        if status is not None:
            self.status = status
        self.extra = extra


class NotFound(ApiError):
    status = 404
    title = "Not Found"


class Conflict(ApiError):
    """The request is fine but the server is in the wrong state for it (e.g. Spotify off)."""

    status = 409
    title = "Conflict"


class UnprocessableError(ApiError):
    status = 422
    title = "Unprocessable Content"


def problem(status: int, title: str, detail: str, request: Request, **extra: Any) -> JSONResponse:
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return problem(exc.status, exc.title, exc.detail, request, **exc.extra)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return problem(exc.status_code, "HTTP Error", str(exc.detail), request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # A field_validator that raises ValueError puts the exception itself in the error ``ctx``;
        # encode before serializing or the 422 turns into a 500.
        return problem(
            422,
            "Validation Error",
            "request validation failed",
            request,
            errors=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return problem(500, "Internal Server Error", "unexpected error", request)
