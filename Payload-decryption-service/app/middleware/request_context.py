"""Pure-ASGI middleware: request id, response timing and the structured access log."""

import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logger import bind_log_context, get_log_context, get_logger, init_log_context

logger = get_logger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        init_log_context()

        # Accept an upstream id only if it is well-formed (prevents log injection).
        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode(), b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        bind_log_context(request_id=request_id)

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request_completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "response_time_ms": round((time.perf_counter() - started) * 1000, 2),
                    "event_publish_status": get_log_context().get("event_publish_status", "not_attempted"),
                },
            )
