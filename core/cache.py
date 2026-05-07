"""
Redis cache with automatic in-memory fallback.
If Redis is unavailable, logs a warning and falls back to a plain dict.
Sensitive credentials (REDIS_URL) are read from environment variables only.
"""
import asyncio
import json
import logging
import os
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

_cache_instance: Optional[Union["RedisCache", "InMemoryCache"]] = None
_init_lock = asyncio.Lock()


class InMemoryCache:
    """Single-process in-memory fallback — data is lost on restart."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        logger.warning(
            "Using in-memory cache — data will not persist across restarts. "
            "Start Redis and set REDIS_URL to enable persistence."
        )

    async def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def close(self) -> None:
        pass


class RedisCache:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def get(self, key: str) -> Optional[Any]:
        raw = await self._client.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        await self._client.setex(key, ttl, json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def close(self) -> None:
        await self._client.aclose()


async def get_cache() -> Union[RedisCache, InMemoryCache]:
    """Return the singleton cache instance, initializing it on first call."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    async with _init_lock:
        if _cache_instance is not None:
            return _cache_instance

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            await client.ping()
            logger.info("Connected to Redis at %s", redis_url)
            _cache_instance = RedisCache(client)
        except Exception as exc:
            logger.warning(
                "Redis connection failed (%s) — using in-memory dict fallback", exc
            )
            _cache_instance = InMemoryCache()

    return _cache_instance
