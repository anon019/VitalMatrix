"""
FastMCP Server Configuration

配置 MCP 服务器，支持 SSE transport + API Key 认证
"""
import logging
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件"""

    async def dispatch(self, request, call_next):
        # 跳过 OPTIONS 预检请求
        if request.method == "OPTIONS":
            return await call_next(request)

        # 获取 Authorization header
        auth_header = request.headers.get("Authorization", "")

        # 验证 Bearer token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # 去掉 "Bearer " 前缀
            if token == settings.MCP_API_KEY:
                return await call_next(request)

        # 也支持 X-API-Key header（兼容某些客户端）
        api_key = request.headers.get("X-API-Key", "")
        if api_key == settings.MCP_API_KEY:
            return await call_next(request)

        # 如果没有配置 API Key，允许访问（向后兼容）
        if not settings.MCP_API_KEY:
            logger.warning("MCP_API_KEY not configured, allowing unauthenticated access")
            return await call_next(request)

        # 认证失败
        logger.warning(f"MCP auth failed from {request.client.host}")
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "id": "auth-error",
                "error": {
                    "code": -32001,
                    "message": "Unauthorized: Invalid or missing API key"
                }
            }
        )


# 创建 FastMCP 实例
mcp = FastMCP(
    name="Health Assistant",
    instructions="""
    你是一个健康数据助手，可以访问用户的训练、睡眠、活动、压力和饮食数据。

    可用的工具：
    - get_health_overview: 获取综合健康概览（训练、睡眠、准备度、活动、压力 + 风险评估）
    - get_training_data: 获取训练数据（支持 1-30 天范围）
    - get_sleep_analysis: 获取睡眠分析
    - get_readiness_score: 获取身体准备度评分
    - get_weekly_trends: 获取周趋势分析
    - get_risk_assessment: 获取健康风险评估
    - get_ai_recommendation: 获取 AI 健康建议
    - get_nutrition_data: 获取饮食营养数据

    数据来源：
    - 训练数据：Polar 运动手表
    - 睡眠/准备度/活动/压力：Oura Ring
    - 饮食：用户上传的餐食照片 + AI 分析
    """
)


def get_mcp_app():
    """获取 MCP ASGI 应用（带 API Key 认证）"""
    # 导入 tools 以注册所有工具
    from . import tools  # noqa: F401

    # 获取 MCP HTTP 应用
    mcp_app = mcp.http_app()

    # 添加 API Key 认证中间件
    if settings.MCP_API_KEY:
        mcp_app.add_middleware(APIKeyAuthMiddleware)
        logger.info(f"MCP Server initialized with API Key auth: {mcp.name}")
    else:
        logger.warning(f"MCP Server initialized WITHOUT auth: {mcp.name}")

    return mcp_app
