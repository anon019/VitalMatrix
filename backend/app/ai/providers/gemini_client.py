"""
Gemini 客户端工厂函数
支持 Vertex AI 和 API Key 双模式切换

通过环境变量 GEMINI_BACKEND 控制模式：
- "vertexai"：使用 Vertex AI 认证
- "api_key"（默认）：使用 GOOGLE_API_KEY 直接认证
"""
import os
import logging

from google import genai

logger = logging.getLogger(__name__)

# 模块级缓存，避免频繁创建 Client 实例
_cached_client: genai.Client | None = None
_cached_backend: str | None = None


def get_client() -> genai.Client:
    """获取 Gemini 客户端（带缓存），支持 Vertex AI 和 API Key 双模式。

    通过环境变量 GEMINI_BACKEND 控制模式：
    - "vertexai"：使用 Vertex AI 认证（需要 GOOGLE_CLOUD_PROJECT）
    - "api_key"（或未设置）：使用 GOOGLE_API_KEY 直接认证

    Client 实例会被缓存，相同 backend 模式下复用同一实例。

    Returns:
        genai.Client 实例
    """
    global _cached_client, _cached_backend

    backend = os.environ.get("GEMINI_BACKEND", "api_key").lower()

    # 缓存命中，直接返回
    if _cached_client is not None and _cached_backend == backend:
        return _cached_client

    if backend == "vertexai":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        if not project:
            raise ValueError(
                "Vertex AI 模式需要设置 GOOGLE_CLOUD_PROJECT 环境变量"
            )
        logger.info(f"创建 Gemini 客户端（Vertex AI）: project={project}, location={location}")
        _cached_client = genai.Client(vertexai=True, project=project, location=location)
    elif backend == "api_key":
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("API Key 模式需要设置 GOOGLE_API_KEY 环境变量")
        logger.info("创建 Gemini 客户端（API Key）")
        _cached_client = genai.Client(api_key=api_key)
    else:
        raise ValueError(
            f"不支持的 GEMINI_BACKEND 值: '{backend}'，可选值: 'vertexai', 'api_key'"
        )

    _cached_backend = backend
    return _cached_client
