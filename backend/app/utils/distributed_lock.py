"""Redis 优先、进程内回退的异步互斥锁。"""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from app.utils.redis_client import RedisClient

logger = logging.getLogger(__name__)
_local_locks: dict[str, asyncio.Lock] = {}


@asynccontextmanager
async def distributed_lock(key: str, ttl_seconds: int = 180):
    token = uuid.uuid4().hex
    redis = None
    acquired = False
    try:
        redis = await RedisClient.get_instance()
        acquired = bool(await redis.set(f"lock:{key}", token, ex=ttl_seconds, nx=True))
    except Exception as exc:
        logger.warning("Redis lock unavailable for %s, using local lock: %s", key, exc)
        local = _local_locks.setdefault(key, asyncio.Lock())
        async with local:
            yield True
        return

    try:
        yield acquired
    finally:
        if acquired and redis is not None:
            try:
                await redis.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('del', KEYS[1]) else return 0 end",
                    1,
                    f"lock:{key}",
                    token,
                )
            except Exception as exc:
                logger.warning("Failed to release lock %s: %s", key, exc)
