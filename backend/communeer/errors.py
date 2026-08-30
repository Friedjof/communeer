"""`{"error": {"code", "message"}}` error envelope, used for every error
response the API returns — including 401s (auth) and 422s (validation),
which FastAPI/Starlette would otherwise shape differently.
"""

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("communeer.errors")


class ApiError(Exception):
    """Raise anywhere in a route/service to produce a shaped error response."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def _envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def unauthorized(message: str = "Authentication required.") -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, "unauthorized", message)


def not_found(message: str = "Resource not found.") -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", message)


def forbidden(message: str = "You do not have access to this resource.") -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "forbidden", message)


def bad_request(message: str) -> ApiError:
    return ApiError(status.HTTP_400_BAD_REQUEST, "bad_request", message)


def service_unavailable(message: str) -> ApiError:
    return ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, "service_unavailable", message)


def conflict(message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, "conflict", message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("validation_error", "Request validation failed."),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = {
            status.HTTP_401_UNAUTHORIZED: "unauthorized",
            status.HTTP_403_FORBIDDEN: "forbidden",
            status.HTTP_404_NOT_FOUND: "not_found",
        }.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "An error occurred."
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, message))

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception while processing %s %s", request.method, request.url)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "An unexpected error occurred."),
        )
