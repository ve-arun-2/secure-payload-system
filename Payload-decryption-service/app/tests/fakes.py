"""Test doubles."""

import time
from collections.abc import Callable

from app.schemas.internal import BucketDecision, refill_tokens


class InMemoryCache:
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
