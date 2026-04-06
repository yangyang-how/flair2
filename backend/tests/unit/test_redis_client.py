"""Unit tests for RedisClient using fakeredis."""

import asyncio

import pytest
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from app.infra.redis_client import CACHE_SENTINEL, RedisClient


@pytest_asyncio.fixture
async def redis(monkeypatch):
    """RedisClient backed by fakeredis (no real Redis needed)."""
    fake = fake_aioredis.FakeRedis(decode_responses=True)
    client = RedisClient.__new__(RedisClient)
    client._redis = fake
    yield client
    await fake.aclose()


async def test_get_set(redis):
    await redis.set("foo", "bar")
    assert await redis.get("foo") == "bar"


async def test_get_missing(redis):
    assert await redis.get("nope") is None


async def test_set_with_ttl(redis):
    await redis.set("k", "v", ttl=10)
    assert await redis.get("k") == "v"
    ttl = await redis._redis.ttl("k")
    assert 0 < ttl <= 10


async def test_incr(redis):
    assert await redis.incr("counter") == 1
    assert await redis.incr("counter") == 2


async def test_incr_initializes_at_zero(redis):
    # Key doesn't exist yet — Redis INCR starts at 1
    count = await redis.incr("newkey")
    assert count == 1


async def test_rpush_blpop(redis):
    await redis.rpush("q", "hello")
    result = await redis.blpop("q", timeout=1)
    assert result == "hello"


async def test_setnx_no_ttl(redis):
    assert await redis.setnx("lock", "1") is True
    assert await redis.setnx("lock", "2") is False
    assert await redis.get("lock") == "1"


async def test_setnx_with_ttl(redis):
    assert await redis.setnx("lock2", "x", ttl=30) is True
    ttl = await redis._redis.ttl("lock2")
    assert 0 < ttl <= 30


async def test_delete(redis):
    await redis.set("del_me", "val")
    await redis.delete("del_me")
    assert await redis.get("del_me") is None


async def test_keys_pattern(redis):
    await redis.set("result:s1:run1:vid1", "a")
    await redis.set("result:s1:run1:vid2", "b")
    await redis.set("result:s1:run2:vid1", "c")
    keys = await redis.keys("result:s1:run1:*")
    assert set(keys) == {"result:s1:run1:vid1", "result:s1:run1:vid2"}


async def test_expire(redis):
    await redis.set("exp_key", "val")
    await redis.expire("exp_key", 60)
    ttl = await redis._redis.ttl("exp_key")
    assert 0 < ttl <= 60


async def test_checkpoint_write_read(redis):
    await redis.write_checkpoint("run1", "S1", 42)
    assert await redis.read_checkpoint("run1", "S1") == 42


async def test_checkpoint_missing(redis):
    assert await redis.read_checkpoint("run1", "S1") is None


async def test_xadd_xread(redis):
    msg_id = await redis.xadd("sse:run1", {"payload": '{"event":"test"}'})
    assert msg_id  # should be a stream ID like "1234-0"

    entries = await redis.xread({"sse:run1": "0-0"}, block=100, count=10)
    assert len(entries) == 1
    stream_name, messages = entries[0]
    assert len(messages) == 1
    _id, fields = messages[0]
    assert fields["payload"] == '{"event":"test"}'


async def test_cache_get_or_compute_miss(redis):
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return "result"

    val = await redis.cache_get_or_compute("cache:p:abc", compute)
    assert val == "result"
    assert calls == 1
    # Second call should be a cache hit
    val2 = await redis.cache_get_or_compute("cache:p:abc", compute)
    assert val2 == "result"
    assert calls == 1  # compute not called again


async def test_cache_get_or_compute_exception_clears_sentinel(redis):
    async def failing_compute():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await redis.cache_get_or_compute("cache:p:fail", failing_compute)

    # Sentinel should be cleared after exception
    assert await redis.get("cache:p:fail") is None


async def test_cache_get_or_compute_hit(redis):
    await redis.set("cache:p:hit", "cached_value")

    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        return "new"

    val = await redis.cache_get_or_compute("cache:p:hit", compute)
    assert val == "cached_value"
    assert calls == 0
