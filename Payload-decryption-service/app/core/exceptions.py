"""Domain exceptions and their mapping to HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """Base class: carries the HTTP status and the public, client-safe error text."""

    status_code: int = 500
    error: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        # `detail` is for logs only and is never returned to the client.
        super().__init__(detail or self.error)
        self.detail = detail or self.error


class InvalidEncryptedPayloadException(AppException):
    status_code = 400
    error = "Invalid encrypted payload"


class InvalidPayloadException(AppException):
    status_code = 400
    error = "Malformed payload"


class RateLimitExceededException(AppException):
    status_code = 429
    error = "Rate limit exceeded"

    def __init__(self, retry_after: float = 1.0, detail: str | None = None) -> None:
        super().__init__(detail)
        self.retry_after = retry_after


class RabbitMQPublishException(AppException):
    status_code = 503
    error = "Failed to publish event"


class CacheUnavailableException(AppException):
    status_code = 503
    error = "Rate limiter unavailable"

class PayloadTooLargeException(AppException):
    status_code = 413
    error = "Request body too large"

def error_response(exc: AppException, extra_headers: dict[str, str] | None = None) -> JSONResponse:
    body = {"error": exc.error}
    headers = dict(extra_headers or {})
    if isinstance(exc, RateLimitExceededException):
        # `message` is kept alongside `error` so both documented contracts are satisfied.
        body["message"] = exc.error
        headers["Retry-After"] = str(max(1, int(exc.retry_after + 0.999)))
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "request_rejected",
            extra={"error": exc.error, "reason": exc.detail, "status_code": exc.status_code},
        )
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Only field locations and messages are returned; never the submitted values.
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": "Invalid request", "details": details})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)}, headers=exc.headers)

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", exc_info=exc)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
