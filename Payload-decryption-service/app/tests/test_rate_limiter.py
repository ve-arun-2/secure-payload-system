import pytest

from app.cache.redis_cache import RedisCache
from app.core.exceptions import CacheUnavailableException, RateLimitExceededException
from app.schemas.internal import BucketDecision, refill_tokens
from app.services.rate_limit_service import RateLimitService
from app.tests.conftest import ManualClock
from app.tests.fakes import InMemoryCache


# --- pure refill maths -----------------------------------------------------------------------
def test_refill_adds_elapsed_times_rate() -> None:
    assert refill_tokens(tokens=2, last_refill=0, now=0.3, capacity=10, refill_per_second=10) == pytest.approx(5)


def test_refill_never_exceeds_capacity() -> None:
    assert refill_tokens(tokens=9, last_refill=0, now=100, capacity=10, refill_per_second=10) == 10


def test_refill_ignores_backwards_clock() -> None:
    assert refill_tokens(tokens=4, last_refill=50, now=40, capacity=10, refill_per_second=10) == 4


# --- bucket behaviour ------------------------------------------------------------------------
@pytest.fixture
def limiter(clock: ManualClock) -> RateLimitService:
    return RateLimitService(InMemoryCache(clock=clock), capacity=10, refill_per_second=10)


async def test_burst_of_capacity_is_allowed_then_rejected(limiter: RateLimitService) -> None:
    for _ in range(10):
        await limiter.check("partner-1")
    with pytest.raises(RateLimitExceededException) as exc_info:
        await limiter.check("partner-1")
    assert exc_info.value.retry_after == pytest.approx(0.1)  # 1 token at 10/s


async def test_tokens_refill_over_time(limiter: RateLimitService, clock: ManualClock) -> None:
    for _ in range(10):
        await limiter.check("partner-1")

    clock.advance(0.25)  # +2.5 tokens
    await limiter.check("partner-1")
    await limiter.check("partner-1")
    with pytest.raises(RateLimitExceededException):
        await limiter.check("partner-1")


async def test_sustained_rate_is_ten_per_second(limiter: RateLimitService, clock: ManualClock) -> None:
    for _ in range(10):
        await limiter.check("partner-1")
    for _ in range(50):  # one request every 100 ms == 10 rps
        clock.advance(0.1)
        await limiter.check("partner-1")


async def test_partners_have_independent_buckets(limiter: RateLimitService) -> None:
    for _ in range(10):
        await limiter.check("partner-a")
    with pytest.raises(RateLimitExceededException):
        await limiter.check("partner-a")
    await limiter.check("partner-b")


async def test_bucket_key_format(limiter: RateLimitService) -> None:
    assert limiter.bucket_key("partner-123") == "rate_limit:partner-123"


# --- Redis outage policy ---------------------------------------------------------------------
class BrokenCache(InMemoryCache):
    async def consume_token_bucket(self, *args, **kwargs) -> BucketDecision:
        raise CacheUnavailableException("down")


async def test_fail_closed_by_default() -> None:
    with pytest.raises(CacheUnavailableException):
        await RateLimitService(BrokenCache()).check("p")


async def test_fail_open_when_configured() -> None:
    cache: RedisCache = BrokenCache()
    decision = await RateLimitService(cache, fail_open=True).check("p")
    assert decision.allowed
