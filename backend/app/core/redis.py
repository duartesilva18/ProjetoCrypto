from __future__ import annotations

import redis.asyncio as redis

from app.config import get_settings

_pool: redis.ConnectionPool | None = None


async def get_redis_pool() -> redis.ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


async def get_redis() -> redis.Redis:
    pool = await get_redis_pool()
    return redis.Redis(connection_pool=pool)


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
