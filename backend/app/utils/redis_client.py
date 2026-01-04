"""
Redis客户端
"""
import json
from typing import Optional, Any
from redis.asyncio import Redis
from app.config import settings


class RedisClient:
    """Redis异步客户端封装"""

    _instance: Optional[Redis] = None

    @classmethod
    async def get_instance(cls) -> Redis:
        """获取Redis单例"""
        if cls._instance is None:
            cls._instance = Redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return cls._instance

    @classmethod
    async def close(cls):
        """关闭Redis连接"""
        if cls._instance:
            await cls._instance.close()
            cls._instance = None

    @classmethod
    async def get(cls, key: str) -> Optional[str]:
        """获取值"""
        redis = await cls.get_instance()
        return await redis.get(key)

    @classmethod
    async def set(cls, key: str, value: Any, ex: Optional[int] = None):
        """设置值"""
        redis = await cls.get_instance()
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await redis.set(key, value, ex=ex)

    @classmethod
    async def get_json(cls, key: str) -> Optional[dict]:
        """获取JSON值"""
        value = await cls.get(key)
        if value:
            return json.loads(value)
        return None

    @classmethod
    async def delete(cls, key: str):
        """删除键"""
        redis = await cls.get_instance()
        await redis.delete(key)

    @classmethod
    async def exists(cls, key: str) -> bool:
        """检查键是否存在"""
        redis = await cls.get_instance()
        return await redis.exists(key) > 0
