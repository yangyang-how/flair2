"""Unit tests for TokenBucketRateLimiter using fakeredis."""

import pytest
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from app.infra.rate_limiter import TokenBucketRateLimiter
from app.infra.redis_client import RedisClient
from app.models.errors import RateLimitError


@pytest_asyncio.fixture
async def redis():
    fake = fake_aioredis.FakeRedis(decode_responses=True)
    client = RedisClient.__new__(RedisClient)
    client._redis = fake
    yield client
    await fake.aclose()


async def test_acquire_within_limit(redis):
    limiter = TokenBucketRateLimiter(redis, "gemini", max_tokens=5, window_seconds=60)
    for _ in range(5):
        assert await limiter.acquire() is True


async def test_acquire_over_limit(redis):
    limiter = TokenBucketRateLimiter(redis, "kimi", max_tokens=3, window_seconds=60)
    for _ in range(3):
        await limiter.acquire()
    # 4th request exceeds limit
    assert await limiter.acquire() is False


async def test_wait_for_token_succeeds(redis):
    limiter = TokenBucketRateLimiter(redis, "openai", max_tokens=2, window_seconds=60)
    # Use 1 of 2 tokens
    await limiter.acquire()
    # Should succeed immediately (1 token remaining)
    await limiter.wait_for_token(max_wait=5.0)


async def test_wait_for_token_times_out(redis):
    limiter = TokenBucketRateLimiter(redis, "gemini2", max_tokens=1, window_seconds=3600)
    await limiter.acquire()  # exhaust the 1 token
    with pytest.raises(RateLimitError):
        await limiter.wait_for_token(max_wait=1.5)


async def test_ttl_set_on_first_acquire(redis):
    limiter = TokenBucketRateLimiter(redis, "testprovider", max_tokens=10, window_seconds=30)
    await limiter.acquire()
    ttl = await redis._redis.ttl("ratelimit:testprovider")
    assert 0 < ttl <= 30
