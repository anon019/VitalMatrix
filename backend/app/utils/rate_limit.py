"""基于 Redis 的轻量级接口限流。"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


async def enforce_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """超过窗口次数时返回 429；Redis 故障时不阻断核心健康功能。"""
    try:
        count = await RedisClient.increment_with_expiry(f"rate:{key}", window_seconds)
    except Exception as exc:
        logger.warning("Rate limiter unavailable for %s: %s", key, exc)
        return
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="操作过于频繁，请稍后再试",
            headers={"Retry-After": str(window_seconds)},
        )
