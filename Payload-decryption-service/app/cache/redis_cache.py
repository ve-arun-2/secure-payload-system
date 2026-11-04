"""Cache abstraction + Redis / in-memory implementations.

`RedisCache` is the interface the rest of the app depends on. Besides the
requested get/set/increment it exposes `consume_token_bucket`, because a
token bucket needs a *single atomic* read-modify-write: doing get() then set()
from several pods would race and let bursts through.
"""

import time
from abc import ABC, abstractmethod
from collections.abc import Callable

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.exceptions import CacheUnavailableException
from app.core.logger import get_logger
from app.schemas.internal import BucketDecision, refill_tokens

logger = get_logger(__name__)


class RedisCache(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...

    @abstractmethod
    async def increment(self, key: str, amount: int = 1) -> int: ...

    @abstractmethod
    async def consume_token_bucket(
        self, key: str, capacity: int, refill_per_second: float, cost: int = 1
    ) -> BucketDecision:
        """Atomically refill the bucket stored at `key`, then try to take `cost` tokens."""

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...


# Executed inside Redis, so refill + consume is one atomic step no matter how many
# API pods call it concurrently. Redis TIME is used as the clock so that pods with
# skewed system clocks still agree on elapsed time.
_TOKEN_BUCKET_LUA = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local cost     = tonumber(ARGV[3])
local ttl      = tonumber(ARGV[4])

local t   = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000

local data   = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts     = tonumber(data[2])

if tokens == nil or ts == nil then
  -- First request from this partner: start with a full bucket.
  tokens = capacity
  ts = now
end

-- Refill: tokens = min(capacity, tokens + elapsed * rate)
local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * rate)

local allowed = 0
local retry_after = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_after = (cost - tokens) / rate
end

redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', key, ttl)

-- Lua numbers become truncated integers in replies, so return strings.
return {allowed, tostring(tokens), tostring(retry_after)}
"""


class RedisCacheImpl(RedisCache):
    def __init__(self, url: str) -> None:
        self._client = aioredis.from_url(url, decode_responses=True, socket_timeout=1.0, socket_connect_timeout=1.0)
        self._token_bucket = self._client.register_script(_TOKEN_BUCKET_LUA)

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except RedisError as exc:
            raise self._unavailable(exc) from exc

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        try:
            await self._client.set(key, value, ex=ttl_seconds)
        except RedisError as exc:
            raise self._unavailable(exc) from exc

    async def increment(self, key: str, amount: int = 1) -> int:
        try:
            return int(await self._client.incrby(key, amount))
        except RedisError as exc:
            raise self._unavailable(exc) from exc

    async def consume_token_bucket(
        self, key: str, capacity: int, refill_per_second: float, cost: int = 1
    ) -> BucketDecision:
        # Idle buckets are refilled to full after capacity/rate seconds; keep the key a bit
        # longer than that and let Redis evict it, so memory is bounded by *active* partners.
        ttl = int(capacity / refill_per_second) + 2
        try:
            allowed, tokens, retry_after = await self._token_bucket(
                keys=[key], args=[capacity, refill_per_second, cost, ttl]
            )
        except RedisError as exc:
            raise self._unavailable(exc) from exc
        return BucketDecision(bool(int(allowed)), float(tokens), float(retry_after))

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except RedisError:
            return False

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _unavailable(exc: Exception) -> CacheUnavailableException:
        logger.error("redis_error", extra={"error_type": type(exc).__name__})
        return CacheUnavailableException(f"redis error: {type(exc).__name__}")


class InMemoryCache(RedisCache):
    """Single-process implementation for tests / local runs. NOT distributed-safe."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[str, str] = {}
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refill)

    async def get(self, key: str) -> str | None:
        return self._values.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._values[key] = value

    async def increment(self, key: str, amount: int = 1) -> int:
        new_value = int(self._values.get(key, "0")) + amount
        self._values[key] = str(new_value)
        return new_value

    async def consume_token_bucket(
        self, key: str, capacity: int, refill_per_second: float, cost: int = 1
    ) -> BucketDecision:
        # No `await` between read and write, so this is atomic on the event loop.
        now = self._clock()
        tokens, last = self._buckets.get(key, (float(capacity), now))
        tokens = refill_tokens(tokens, last, now, capacity, refill_per_second)

        if tokens >= cost:
            tokens -= cost
            decision = BucketDecision(True, tokens, 0.0)
        else:
            decision = BucketDecision(False, tokens, (cost - tokens) / refill_per_second)

        self._buckets[key] = (tokens, now)
        return decision

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None
