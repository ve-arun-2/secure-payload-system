"""Per-partner rate limiting with a custom Token Bucket (no third-party limiter).

Algorithm
---------
Every partner owns a bucket that holds up to `capacity` tokens.

* A request costs 1 token.
* Tokens are NOT added by a timer. Instead, whenever a request arrives we
  compute how many tokens *would have* been added since the bucket was last
  touched (lazy refill):

      tokens = min(capacity, tokens + (now - last_refill) * refill_per_second)

* If tokens >= 1 the request is allowed and one token is removed.
  Otherwise it is rejected, and `retry_after = (1 - tokens) / refill_per_second`
  tells the caller when a token will be available.

With capacity=10 and refill=10/s a partner may burst 10 requests instantly and
then sustain 10 requests per second. State per partner is two numbers
(tokens, last_refill timestamp) stored under `rate_limit:{partner_id}`.

Distributed safety: the refill + consume step runs atomically inside Redis
(Lua script, see cache/redis_cache.py), so all API pods share one bucket per
partner and concurrent requests can never overspend tokens. The refill maths
itself lives in `schemas.internal.refill_tokens` and is unit-tested.
"""

from app.cache.redis_cache import RedisCache
from app.core.exceptions import CacheUnavailableException, RateLimitExceededException
from app.core.logger import get_logger
from app.schemas.internal import BucketDecision

logger = get_logger(__name__)


class RateLimitService:
    KEY_PREFIX = "rate_limit:"

    def __init__(
        self,
        cache: RedisCache,
        capacity: int = 10,
        refill_per_second: float = 10.0,
        fail_open: bool = False,
    ) -> None:
        self._cache = cache
        self._capacity = capacity
        self._refill_per_second = refill_per_second
        self._fail_open = fail_open

    @property
    def capacity(self) -> int:
        return self._capacity

    def bucket_key(self, partner_id: str) -> str:
        return f"{self.KEY_PREFIX}{partner_id}"

    async def check(self, partner_id: str) -> BucketDecision:
        """Consume one token for `partner_id`; raise RateLimitExceededException if none is left."""
        try:
            decision = await self._cache.consume_token_bucket(
                self.bucket_key(partner_id), self._capacity, self._refill_per_second
            )
        except CacheUnavailableException:
            if self._fail_open:
                logger.error("rate_limiter_unavailable_failing_open", extra={"partner_id": partner_id})
                return BucketDecision(True, float(self._capacity), 0.0)
            raise

        if not decision.allowed:
            raise RateLimitExceededException(retry_after=decision.retry_after, detail="token bucket empty")
        return decision
