import asyncio
import random

from app.infra.redis_client import RedisClient
from app.models.errors import RateLimitError


class RedisSemaphore:
    """Distributed concurrency cap backed by a Redis list of tokens.

    Models providers whose limit is "at most N in-flight requests" (e.g. Kimi
    Code: concurrency ≤ 30). One Redis list (`semaphore:{name}`) is seeded
    once with `max_slots` sentinel tokens. `acquire()` BLPOPs a token;
    `release()` RPUSHes one back.

    Seeding is idempotent via a companion SETNX flag — only the first caller
    fills the list. Changing `max_slots` in config requires deleting
    `semaphore:{name}` and `semaphore:{name}:seeded` to re-seed.

    A process crash between acquire and release leaks a token permanently;
    that is an acceptable prototype trade-off (upgrade to a Lua-scripted
    lease if it becomes a real issue).
    """

    def __init__(self, redis: RedisClient, name: str, max_slots: int):
        self._redis = redis
        self._name = name
        self._key = f"semaphore:{name}"
        self._seed_flag = f"semaphore:{name}:seeded"
        self._max_slots = max_slots

    async def _ensure_seeded(self) -> None:
        won = await self._redis.setnx(self._seed_flag, "1")
        if won:
            for _ in range(self._max_slots):
                await self._redis.rpush(self._key, "1")

    async def acquire(self, timeout: int = 60) -> None:
        await self._ensure_seeded()
        token = await self._redis.blpop(self._key, timeout=timeout)
        if token is None:
            raise RateLimitError(
                f"Semaphore {self._name} timed out after {timeout}s",
                provider=self._name,
            )

    async def release(self) -> None:
        await self._redis.rpush(self._key, "1")


class TokenBucketRateLimiter:
    """Sliding-window token bucket backed by Redis INCR + TTL.

    One Redis key per provider (`ratelimit:{provider}`).  The counter resets
    automatically when the TTL fires at the end of each window.

    Note: INCR and EXPIRE are not atomic.  If the process dies between them the
    key has no TTL, so the next INCR will re-set it.  This is an acceptable
    edge-case for a prototype; fix with a Lua script if stricter guarantees are
    needed.
    """

    def __init__(
        self,
        redis: RedisClient,
        provider: str,
        max_tokens: int,
        window_seconds: int,
    ):
        self._redis = redis
        self._key = f"ratelimit:{provider}"
        self._provider = provider
        self._max_tokens = max_tokens
        self._window_seconds = window_seconds

    async def acquire(self) -> bool:
        count = await self._redis.incr(self._key)
        if count == 1:
            await self._redis.expire(self._key, self._window_seconds)
        return count <= self._max_tokens

    async def wait_for_token(self, max_wait: float = 30.0) -> None:
        elapsed = 0.0
        while elapsed < max_wait:
            if await self.acquire():
                return
            delay = 1.0 + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
            elapsed += delay
        raise RateLimitError(
            f"Rate limiter timed out after {max_wait}s waiting for {self._provider}",
            provider=self._provider,
        )
