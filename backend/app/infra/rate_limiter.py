import asyncio

from app.infra.redis_client import RedisClient
from app.models.errors import RateLimitError


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
            await asyncio.sleep(1.0)
            elapsed += 1.0
        raise RateLimitError(
            f"Rate limiter timed out after {max_wait}s waiting for {self._provider}",
            provider=self._provider,
        )
