"""
AI Provider工厂 - 支持动态切换AI模型
"""
import logging
from typing import Dict, Type
from app.ai.base import AIProvider
from app.ai.providers.deepseek import DeepSeekProvider
from app.ai.providers.qwen import QwenProvider
from app.config import settings

logger = logging.getLogger(__name__)


class AIProviderFactory:
    """AI Provider工厂"""

    _providers: Dict[str, Type[AIProvider]] = {
        "deepseek": DeepSeekProvider,
        "qwen": QwenProvider,
        # 未来可扩展
        # "openai": OpenAIProvider,
        # "claude": ClaudeProvider,
    }

    _instance: Dict[str, AIProvider] = {}

    @classmethod
    def create(cls, provider_name: str = None) -> AIProvider:
        """
        创建AI Provider实例

        Args:
            provider_name: Provider名称（默认使用配置中的AI_PROVIDER）

        Returns:
            AI Provider实例

        Raises:
            ValueError: 未知的Provider名称
        """
        if provider_name is None:
            provider_name = settings.AI_PROVIDER

        # 如果已经有实例，直接返回（单例模式）
        if provider_name in cls._instance:
            return cls._instance[provider_name]

        # 创建新实例
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"未知的AI Provider: {provider_name}. "
                f"可用的Provider: {available}"
            )

        try:
            instance = provider_class()
            cls._instance[provider_name] = instance
            logger.info(f"AI Provider创建成功: {provider_name} ({instance.model})")
            return instance
        except Exception as e:
            logger.error(f"AI Provider创建失败: {provider_name} - {str(e)}")
            raise

    @classmethod
    def get_default_provider(cls) -> AIProvider:
        """
        获取默认Provider

        Returns:
            默认的AI Provider实例
        """
        return cls.create(settings.AI_PROVIDER)

    @classmethod
    async def close_all(cls):
        """关闭所有Provider实例"""
        for provider_name, instance in cls._instance.items():
            try:
                await instance.close()
                logger.info(f"AI Provider已关闭: {provider_name}")
            except Exception as e:
                logger.error(f"关闭AI Provider失败: {provider_name} - {str(e)}")

        cls._instance.clear()
