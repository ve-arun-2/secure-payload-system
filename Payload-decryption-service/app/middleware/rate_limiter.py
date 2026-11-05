"""Rate-limiting middleware.

Runs BEFORE routing, validation and decryption: a rejected request never reaches
the crypto code. Because `partner_id` lives in the JSON body, the middleware
buffers the (size-capped) body, extracts the id, charges the token bucket, and
then replays the buffered body to the downstream app.

Request -> extract partner_id -> token bucket -> allowed: continue
                                              -> rejected: HTTP 429
"""

import json
import re
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import (
    CacheUnavailableException,
    RateLimitExceededException,
    PayloadTooLargeException,
    error_response,
)
from app.core.logger import bind_log_context, get_logger
from app.services.rate_limit_service import RateLimitService

logger = get_logger(__name__)

_PARTNER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

class RateLimiterMiddleware: 
    def __init__(
        self,
        app: ASGIApp,
        rate_limit_service: RateLimitService,
        protected_paths: Iterable[str],
        max_body_bytes: int,
    ) -> None:
        self.app = app
        self._service = rate_limit_service
        self._protected_paths = frozenset(protected_paths)
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self._protected_paths:
            await self.app(scope, receive, send)
            return

        try:
            body = await self._read_body(receive)
            print("====", body)
        except PayloadTooLargeException as exc:
            await error_response(exc)(scope, receive, send)
            return

        partner_id = self._extract_partner_id(body)
        # Requests without a usable partner_id share a per-client-IP bucket so that
        # junk traffic is still throttled and cannot create unbounded Redis keys.
        client_host = (scope.get("client") or ("unknown", 0))[0]
        bucket_owner = partner_id or f"ip:{client_host}"

        try:
            await self._service.check(bucket_owner)
        except RateLimitExceededException as exc:
            bind_log_context(partner_id=partner_id or bucket_owner)
            logger.warning("rate_limit_exceeded", extra={"retry_after": round(exc.retry_after, 3)})
            response = error_response(exc, {"X-RateLimit-Limit": str(self._service.capacity)})
            await response(scope, receive, send)
            return
        except CacheUnavailableException as exc:
            await error_response(exc)(scope, receive, send)
            return

        await self.app(scope, self._replay(body, receive), send)

    async def _read_body(self, receive: Receive) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self._max_body_bytes:
                raise PayloadTooLargeException
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    @staticmethod
    def _extract_partner_id(body: bytes) -> str | None:
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None
        partner_id = data.get("partner_id") if isinstance(data, dict) else None
        if isinstance(partner_id, str) and _PARTNER_ID_RE.fullmatch(partner_id):
            return partner_id
        return None

    @staticmethod
    def _replay(body: bytes, receive: Receive) -> Receive:
        """Feed the buffered body to the downstream app, then defer to the real receive()."""
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return replay
