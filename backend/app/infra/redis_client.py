import asyncio
from collections.abc import Awaitable, Callable

import redis.asyncio as aioredis

CACHE_SENTINEL = "computing"
CACHE_SENTINEL_TTL = 60  # seconds — auto-expires if winner crashes
CACHE_POLL_INTERVAL = 0.5  # seconds between polls
CACHE_POLL_TIMEOUT = 30.0  # seconds before loser retries as winner


class RedisClient:
    def __init__(self, url: str):
        self._redis = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl is not None:
            await self._redis.set(key, value, ex=ttl)
        else:
            await self._redis.set(key, value)

    async def incr(self, key: str) -> int:
        return await self._redis.incr(key)

    async def rpush(self, key: str, value: str) -> None:
        await self._redis.rpush(key, value)

    async def blpop(self, key: str, timeout: int = 0) -> str | None:
        result = await self._redis.blpop(key, timeout=timeout)
        return result[1] if result is not None else None

    async def setnx(self, key: str, value: str, ttl: int | None = None) -> bool:
        if ttl is not None:
            result = await self._redis.set(key, value, nx=True, ex=ttl)
        else:
            result = await self._redis.setnx(key, value)
        return bool(result)

    async def keys(self, pattern: str) -> list[str]:
        return await self._redis.keys(pattern)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def expire(self, key: str, ttl: int) -> None:
        await self._redis.expire(key, ttl)

    async def xadd(self, stream: str, fields: dict) -> str:
        return await self._redis.xadd(stream, fields)

    async def xread(
        self,
        streams: dict[str, str],
        block: int = 5000,
        count: int = 10,
    ) -> list:
        return await self._redis.xread(streams, block=block, count=count)

    async def write_checkpoint(self, run_id: str, stage: str, index: int) -> None:
        await self.set(f"checkpoint:{run_id}:{stage}", str(index))

    async def read_checkpoint(self, run_id: str, stage: str) -> int | None:
        val = await self.get(f"checkpoint:{run_id}:{stage}")
        return int(val) if val is not None else None

    async def cache_get_or_compute(
        self,
        cache_key: str,
        compute_fn: Callable[[], Awaitable[str]],
        ttl: int = 3600,
    ) -> str:
        """SETNX pattern for cross-user LLM result deduplication.

        Three-layer defense against poison sentinels (see interface contract #71 v3):
        1. Sentinel SET NX EX 60 — auto-expires in 60s even if winner is killed
        2. Winner DELETEs sentinel on exception — fast cleanup for normal failures
        3. Loser polls with 30s timeout, then retries as winner — no infinite blocking
        """
        cached = await self.get(cache_key)
        if cached is not None and cached != CACHE_SENTINEL:
            return cached

        if cached is None:
            won = await self.setnx(cache_key, CACHE_SENTINEL, ttl=CACHE_SENTINEL_TTL)
            if won:
                try:
                    result = await compute_fn()
                    await self.set(cache_key, result, ttl=ttl)
                    return result
                except Exception:
                    await self.delete(cache_key)
                    raise

        # Loser path: poll until value appears or timeout
        elapsed = 0.0
        while elapsed < CACHE_POLL_TIMEOUT:
            await asyncio.sleep(CACHE_POLL_INTERVAL)
            elapsed += CACHE_POLL_INTERVAL
            val = await self.get(cache_key)
            if val is not None and val != CACHE_SENTINEL:
                return val

        # Timeout — sentinel's 60s TTL will eventually clear it; retry as winner
        return await self.cache_get_or_compute(cache_key, compute_fn, ttl)

    async def aclose(self) -> None:
        await self._redis.aclose()
