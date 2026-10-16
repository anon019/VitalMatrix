"""Read-only MCP adapters to the same service used by REST."""

from datetime import date

from mcp.types import ToolAnnotations

from app.api.dependencies import resolve_default_user
from app.api.v1.research import profile_data
from app.database.session import AsyncSessionLocal
from app.services.research_service import ResearchService
from app.utils.datetime_helper import today_hk
from .server import mcp

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, openWorldHint=False
)


@mcp.tool(annotations=READ_ONLY)
async def get_research_catalog() -> dict:
    """先调用：列出个人健康数据集、字段、指标单位、日期覆盖、设备能力和治理进度。"""
    async with AsyncSessionLocal() as db:
        user = await resolve_default_user(db)
        return await ResearchService(db).catalog(user.id)


@mcp.tool(annotations=READ_ONLY)
async def get_research_profile() -> dict:
    """读取当前身体资料与目标；历史体重/体检/用药请查询journal，不把当前资料当历史。"""
    async with AsyncSessionLocal() as db:
        user = await resolve_default_user(db)
        return await profile_data(user, db)


@mcp.tool(annotations=READ_ONLY)
async def get_research_context(target_date: str | None = None) -> dict:
    """指定YYYY-MM-DD的统一上下文：近期每日指标、7/30/90天基线、证据和缺失/过时状态。"""
    async with AsyncSessionLocal() as db:
        user = await resolve_default_user(db)
        result = await ResearchService(db).context(
            user.id, date.fromisoformat(target_date) if target_date else today_hk()
        )
        result.update(await profile_data(user, db))
        return result


@mcp.tool(annotations=READ_ONLY)
async def query_health_records(
    dataset: str,
    start: str,
    end: str,
    limit: int = 100,
    offset: int = 0,
    include_raw: bool = False,
    include_samples: bool = False,
    include_superseded: bool = False,
) -> dict:
    """按catalog中的dataset与UTC+8日期读取明细；每窗最多366天，可翻页查询任意历史。
    营养含食物明细。高频序列/原始JSON需显式请求（每页最多25条）；next_offset用于翻页。
    """
    async with AsyncSessionLocal() as db:
        user = await resolve_default_user(db)
        return await ResearchService(db).records(
            user.id,
            dataset,
            date.fromisoformat(start),
            date.fromisoformat(end),
            limit,
            offset,
            include_raw,
            include_samples,
            include_superseded,
        )


@mcp.tool(annotations=READ_ONLY)
async def get_research_days(
    start: str, end: str, metrics: list[str] | None = None
) -> dict:
    """读取已沉淀的每日研究数据（最多366天/窗）；保留空值、来源ID、质量和stale状态。"""
    async with AsyncSessionLocal() as db:
        user = await resolve_default_user(db)
        return await ResearchService(db).days(
            user.id, date.fromisoformat(start), date.fromisoformat(end), metrics
        )


@mcp.tool(annotations=READ_ONLY)
async def explore_health_pattern(
    start: str, end: str, x: str, y: str, lag: int = 1, min_pairs: int = 20
) -> dict:
    """探索x(D)与y(D+lag)的Pearson相关（lag=0..14）。指标名来自catalog。
    至少20个有效日对；排除过时/未完成日，营养要求确认全天完整。无因果/诊断结论。
    """
    async with AsyncSessionLocal() as db:
        user = await resolve_default_user(db)
        return await ResearchService(db).association(
            user.id,
            date.fromisoformat(start),
            date.fromisoformat(end),
            x,
            y,
            lag,
            min_pairs,
        )
