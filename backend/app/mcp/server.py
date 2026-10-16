"""
FastMCP Server Configuration

配置 MCP 服务器，支持 Streamable HTTP + API Key 认证
"""
import hmac
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

        if not settings.MCP_API_KEY:
            return JSONResponse(status_code=503, content={"error": "Health data access key not configured"})

        # 获取 Authorization header
        auth_header = request.headers.get("Authorization", "")

        # 验证 Bearer token（使用常数时间比较防止时序攻击）
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # 去掉 "Bearer " 前缀
            if hmac.compare_digest(token.encode(), settings.MCP_API_KEY.encode()):
                return await call_next(request)

        # 也支持 X-API-Key header（兼容某些客户端）
        api_key = request.headers.get("X-API-Key", "")
        if api_key and hmac.compare_digest(api_key.encode(), settings.MCP_API_KEY.encode()):
            return await call_next(request)

        # 认证失败
        logger.warning("MCP auth failed")
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

    深度研究优先使用统一研究工具：get_research_catalog、get_research_profile、
    get_research_context、get_research_days、query_health_records、explore_health_pattern。
    它们包含来源、覆盖率、缺失与过时状态，可查询完整历史（分页）。
    先读取catalog与profile，再取context；必要时下钻records及高频采样。
    日期按UTC+8；不要把记录缺失当成零，不要把AI估算当成测量。
    滞后相关仅用于探索，不代表因果或诊断。
    """
)


def get_mcp_app():
    """获取 MCP ASGI 应用（带 API Key 认证）"""
    # 导入 tools 以注册所有工具
    from . import tools  # noqa: F401
    from . import research_tools  # noqa: F401

    # 获取 MCP HTTP 应用
    mcp_app = mcp.http_app(path="/mcp", transport="streamable-http")

    # 添加 API Key 认证中间件
    mcp_app.add_middleware(APIKeyAuthMiddleware)
    logger.info("MCP Server initialized with required API Key auth: %s", mcp.name)

    return mcp_app
