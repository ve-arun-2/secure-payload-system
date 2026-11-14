"""Redis-backed cache.

Exposes `consume_token_bucket` as a single atomic Lua script, because a token
bucket needs an atomic read-modify-write: doing a separate GET then SET from
several pods would race and let bursts through.
"""

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.exceptions import CacheUnavailableException
from app.core.logger import get_logger
from app.schemas.internal import BucketDecision

logger = get_logger(__name__)


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


class RedisCache:
    def __init__(self, url: str) -> None:
        self._client = aioredis.from_url(url, decode_responses=True, socket_timeout=1.0, socket_connect_timeout=1.0)
        self._token_bucket = self._client.register_script(_TOKEN_BUCKET_LUA)

    async def consume_token_bucket(
        self, key: str, capacity: int, refill_per_second: float, cost: int = 1
    ) -> BucketDecision:
        # Idle buckets are refilled to full after capacity/rate seconds; keep the key a bit
        # longer than that and let Redis evict it, so memory is bounded by *active* partners.
        ttl = 5
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
