"""
FastAPI主应用
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database.session import engine
from app.database.base import Base

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# 初始化 MCP 应用（需要在 lifespan 之前创建以获取其 lifespan）
mcp_app = None
try:
    from app.mcp import get_mcp_app
    mcp_app = get_mcp_app()
    logger.info("🔌 MCP Server 初始化成功")
except Exception as e:
    logger.warning(f"⚠️ MCP Server 初始化失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理（含 MCP lifespan 整合）"""
    # 启动
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")

    # 创建数据库表（仅开发环境，生产使用Alembic）
    if settings.DEBUG:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("📊 数据库表创建完成（开发模式）")

    # 启动任务调度器
    from app.scheduler.jobs import start_scheduler
    start_scheduler()

    logger.info(f"✅ {settings.APP_NAME} 启动成功！")
    logger.info(f"📍 API文档: http://{settings.HOST}:{settings.PORT}/docs")

    # 如果 MCP 应用初始化成功，将其 lifespan 嵌套进来
    if mcp_app is not None:
        async with mcp_app.lifespan(mcp_app):
            logger.info("🔌 MCP Server lifespan 已启动")
            yield
            logger.info("🔌 MCP Server lifespan 正在关闭...")
    else:
        yield

    # 关闭
    logger.info(f"👋 {settings.APP_NAME} 关闭中...")

    # 关闭任务调度器
    from app.scheduler.jobs import shutdown_scheduler
    shutdown_scheduler()

    # 关闭AI Provider
    from app.ai.factory import AIProviderFactory
    await AIProviderFactory.close_all()

    # 关闭数据库连接
    await engine.dispose()
    logger.info("✅ 数据库连接已关闭")


# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="个人健康助理 - 基于Polar训练数据驱动的AI智能分析系统",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# 配置CORS（即使 DEBUG 模式也限制来源，防止误配置导致安全问题）
cors_origins = settings.ALLOWED_ORIGINS.copy()
if settings.DEBUG:
    # DEBUG 模式下添加本地开发地址
    cors_origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录（用于隐私政策、服务条款等）
import os
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# 全局异常处理器（生产环境隐藏内部错误详情）
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理：生产环境不暴露内部错误详情"""
    if settings.DEBUG:
        # DEBUG 模式显示详细错误
        return JSONResponse(
            status_code=500,
            content={"detail": f"内部错误: {str(exc)}"}
        )
    else:
        # 生产环境只返回通用错误信息
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误，请稍后重试"}
        )


# 健康检查端点
@app.get("/")
async def root():
    """根路径 - API信息"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


# 注册路由
from app.api.v1 import auth, polar, oura, training, ai, user, mcp, dashboard, nutrition, trends

app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(polar.router, prefix="/api/v1/polar", tags=["Polar"])
app.include_router(oura.router, prefix="/api/v1/oura", tags=["Oura"])
app.include_router(training.router, prefix="/api/v1/training", tags=["训练数据"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI建议"])
app.include_router(user.router, prefix="/api/v1/user", tags=["用户"])
app.include_router(mcp.router, prefix="/api/v1/mcp", tags=["MCP"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(nutrition.router, prefix="/api/v1", tags=["营养饮食"])
app.include_router(trends.router, prefix="/api/v1/trends", tags=["趋势数据"])

# 挂载 MCP Server (Model Context Protocol)
# MCP 应用在模块顶部初始化，lifespan 在 FastAPI lifespan 中管理
if mcp_app is not None:
    app.mount("", mcp_app)
    logger.info("🔌 MCP Server 已挂载到 /mcp (SSE: /mcp/sse)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
