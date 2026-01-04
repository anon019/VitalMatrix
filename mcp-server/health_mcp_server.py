#!/usr/bin/env python3
"""
健康助手 MCP 服务器

运行在本地电脑上，连接到云端健康数据API
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Prompt, PromptMessage, PromptArgument

# 配置
HEALTH_API_URL = os.environ.get("HEALTH_API_URL", "https://your-domain.com")
HEALTH_API_KEY = os.environ.get("HEALTH_API_KEY", "")

# 创建MCP服务器
server = Server("health-assistant")


def format_training_summary(data: dict) -> str:
    """格式化训练汇总数据"""
    lines = [
        f"## 训练数据汇总 (最近{data['period_days']}天)",
        "",
        f"- 总训练次数: {data['total_sessions']}次",
        f"- 总训练时长: {data['total_duration_min']}分钟",
        f"- Zone2累计: {data['total_zone2_min']:.1f}分钟",
        f"- Zone4-5累计: {data['total_zone4_5_min']:.1f}分钟",
        "",
        "### 训练记录",
    ]

    for session in data.get("sessions", []):
        lines.append(
            f"- {session['date']} | {session['sport']} | "
            f"{session['duration_min']}分钟 | "
            f"Z2: {session['zone2_min']:.1f}分 | "
            f"Z4-5: {session['zone4_5_min']:.1f}分"
        )

    return "\n".join(lines)


def format_sleep_data(data: dict) -> str:
    """格式化睡眠数据"""
    lines = [
        f"## 睡眠数据 (最近{data['period_days']}天)",
        "",
    ]

    if data.get("avg_score"):
        lines.append(f"- 平均睡眠评分: {data['avg_score']:.1f}")
    if data.get("avg_duration_min"):
        lines.append(f"- 平均睡眠时长: {data['avg_duration_min']:.0f}分钟")

    lines.append("")
    lines.append("### 睡眠记录")

    for record in data.get("records", []):
        score_str = f"评分{record['score']}" if record.get('score') else "无评分"
        duration_str = f"{record['total_sleep_min']}分钟" if record.get('total_sleep_min') else "无数据"
        lines.append(f"- {record['date']} | {score_str} | {duration_str}")

    return "\n".join(lines)


def format_readiness_data(data: dict) -> str:
    """格式化准备度数据"""
    lines = [
        f"## 准备度数据 (最近{data['period_days']}天)",
        "",
    ]

    if data.get("avg_score"):
        lines.append(f"- 平均准备度: {data['avg_score']:.1f}")

    lines.append("")
    lines.append("### 准备度记录")

    for record in data.get("records", []):
        score_str = f"评分{record['score']}" if record.get('score') else "无评分"
        lines.append(f"- {record['date']} | {score_str}")

    return "\n".join(lines)


def format_activity_data(data: dict) -> str:
    """格式化活动数据"""
    lines = [
        f"## 活动数据 (最近{data['period_days']}天)",
        "",
    ]

    if data.get("avg_steps"):
        lines.append(f"- 平均步数: {data['avg_steps']:.0f}")
    if data.get("avg_active_calories"):
        lines.append(f"- 平均活动卡路里: {data['avg_active_calories']:.0f}")

    lines.append("")
    lines.append("### 活动记录")

    for record in data.get("records", []):
        steps_str = f"{record['steps']}步" if record.get('steps') else "无数据"
        cal_str = f"{record['active_calories']}卡" if record.get('active_calories') else ""
        lines.append(f"- {record['date']} | {steps_str} {cal_str}")

    return "\n".join(lines)


def format_stress_data(data: dict) -> str:
    """格式化压力数据"""
    lines = [
        f"## 压力数据 (最近{data['period_days']}天)",
        "",
        "### 压力记录",
    ]

    for record in data.get("records", []):
        summary = record.get('day_summary', '无数据')
        lines.append(f"- {record['date']} | {summary}")

    return "\n".join(lines)


def format_health_overview(data: dict) -> str:
    """格式化健康概览"""
    lines = [
        f"# 健康概览 ({data['date']})",
        "",
        "## 训练",
    ]

    training = data.get("training", {})
    yesterday = training.get("yesterday", {})
    weekly = training.get("weekly", {})

    if yesterday.get("has_data"):
        lines.extend([
            f"- 昨日训练: {yesterday['duration_min']}分钟",
            f"- Zone2: {yesterday['zone2_min']:.1f}分钟",
            f"- Zone4-5: {yesterday['zone4_5_min']:.1f}分钟",
        ])
    else:
        lines.append("- 昨日无训练数据")

    if weekly.get("has_data"):
        lines.extend([
            f"- 本周累计: {weekly['total_min']}分钟",
            f"- 周Zone2: {weekly['zone2_min']:.1f}分钟",
        ])

    lines.append("")
    lines.append("## 恢复状态")

    sleep = data.get("sleep", {})
    readiness = data.get("readiness", {})

    if sleep.get("has_data") and sleep.get("score"):
        lines.append(f"- 睡眠评分: {sleep['score']}")
    if readiness.get("has_data") and readiness.get("score"):
        lines.append(f"- 准备度: {readiness['score']}")

    activity = data.get("activity", {})
    if activity.get("has_data") and activity.get("steps"):
        lines.append(f"- 步数: {activity['steps']}")

    stress = data.get("stress", {})
    if stress.get("has_data") and stress.get("day_summary"):
        lines.append(f"- 压力: {stress['day_summary']}")

    # 风险指标
    risk_flags = data.get("risk_flags", [])
    if risk_flags:
        lines.append("")
        lines.append("## 风险指标")
        for flag in risk_flags:
            level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(flag.get("level"), "⚪")
            lines.append(f"{level_emoji} {flag.get('message', '')}")

    lines.append("")
    lines.append(f"**综合评估**: {data.get('summary', '无')}")

    return "\n".join(lines)


def format_weekly_trends(data: dict) -> str:
    """格式化周趋势"""
    lines = [
        f"# 周趋势分析",
        f"周期: {data['week_start']} 至 {data['week_end']}",
        "",
    ]

    # 训练趋势
    training = data.get("training_trend", {})
    lines.extend([
        "## 训练趋势",
        f"- 总训练时长: {training.get('total_minutes', 0)}分钟",
        f"- Zone2累计: {training.get('total_zone2', 0):.1f}分钟",
        f"- 训练天数: {training.get('training_days', 0)}天",
        "",
    ])

    # 睡眠趋势
    sleep = data.get("sleep_trend", {})
    if sleep.get("avg_score"):
        lines.extend([
            "## 睡眠趋势",
            f"- 平均评分: {sleep['avg_score']:.1f}",
            "",
        ])

    # 准备度趋势
    readiness = data.get("readiness_trend", {})
    if readiness.get("avg_score"):
        lines.extend([
            "## 准备度趋势",
            f"- 平均评分: {readiness['avg_score']:.1f}",
            "",
        ])

    # 活动趋势
    activity = data.get("activity_trend", {})
    if activity.get("avg_steps"):
        lines.extend([
            "## 活动趋势",
            f"- 平均步数: {activity['avg_steps']:.0f}",
            f"- 总步数: {activity.get('total_steps', 0)}",
        ])

    return "\n".join(lines)


def format_risk_flags(data: dict) -> str:
    """格式化风险指标"""
    lines = [
        "# 风险指标评估",
        "",
    ]

    overall = data.get("overall_status", "unknown")
    status_map = {
        "good": "🟢 状态良好",
        "caution": "🟡 需要注意",
        "warning": "🔴 存在风险"
    }
    lines.append(f"**整体状态**: {status_map.get(overall, overall)}")
    lines.append("")

    flags = data.get("flags", [])
    if flags:
        lines.append("## 详细指标")
        for flag in flags:
            level_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(flag.get("level"), "⚪")
            lines.append(f"{level_emoji} [{flag.get('flag', '')}] {flag.get('message', '')}")
    else:
        lines.append("无风险指标，状态良好！")

    return "\n".join(lines)


async def fetch_api(endpoint: str, params: dict = None) -> dict:
    """调用健康数据API"""
    if not HEALTH_API_KEY:
        raise Exception("未配置 HEALTH_API_KEY 环境变量")

    url = f"{HEALTH_API_URL}/api/v1/mcp{endpoint}"
    headers = {"Authorization": f"Bearer {HEALTH_API_KEY}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


# ============ MCP Tools ============

@server.list_tools()
async def list_tools():
    """列出可用工具"""
    return [
        Tool(
            name="get_health_overview",
            description="获取综合健康概览，包含训练、睡眠、准备度、活动、压力等数据及风险评估",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_training_data",
            description="获取Polar训练数据，包含心率区间分布、训练时长等详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "查询天数，默认7天",
                        "default": 7
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_sleep_data",
            description="获取Oura睡眠数据，包含睡眠评分、时长、效率等",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "查询天数，默认7天",
                        "default": 7
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_readiness_data",
            description="获取Oura准备度数据，评估身体恢复状态",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "查询天数，默认7天",
                        "default": 7
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_activity_data",
            description="获取Oura活动数据，包含步数、卡路里等",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "查询天数，默认7天",
                        "default": 7
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_stress_data",
            description="获取Oura压力数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "查询天数，默认7天",
                        "default": 7
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_weekly_trends",
            description="获取本周趋势分析，包含训练、睡眠、准备度、活动的变化趋势",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_risk_flags",
            description="获取当前风险指标，检测训练过度、恢复不足等风险",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """执行工具调用"""
    try:
        if name == "get_health_overview":
            data = await fetch_api("/health-overview")
            text = format_health_overview(data)

        elif name == "get_training_data":
            days = arguments.get("days", 7)
            data = await fetch_api("/training-summary", {"days": days})
            text = format_training_summary(data)

        elif name == "get_sleep_data":
            days = arguments.get("days", 7)
            data = await fetch_api("/sleep-data", {"days": days})
            text = format_sleep_data(data)

        elif name == "get_readiness_data":
            days = arguments.get("days", 7)
            data = await fetch_api("/readiness-data", {"days": days})
            text = format_readiness_data(data)

        elif name == "get_activity_data":
            days = arguments.get("days", 7)
            data = await fetch_api("/activity-data", {"days": days})
            text = format_activity_data(data)

        elif name == "get_stress_data":
            days = arguments.get("days", 7)
            data = await fetch_api("/stress-data", {"days": days})
            text = format_stress_data(data)

        elif name == "get_weekly_trends":
            data = await fetch_api("/weekly-trends")
            text = format_weekly_trends(data)

        elif name == "get_risk_flags":
            data = await fetch_api("/risk-flags")
            text = format_risk_flags(data)

        else:
            text = f"未知工具: {name}"

        return [TextContent(type="text", text=text)]

    except httpx.HTTPStatusError as e:
        error_msg = f"API请求失败: {e.response.status_code}"
        try:
            detail = e.response.json().get("detail", "")
            if detail:
                error_msg += f" - {detail}"
        except:
            pass
        return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        return [TextContent(type="text", text=f"工具执行失败: {str(e)}")]


# ============ MCP Prompts ============

@server.list_prompts()
async def list_prompts():
    """列出可用提示词模板"""
    return [
        Prompt(
            name="daily_health_check",
            description="进行每日健康检查，全面评估训练和恢复状态",
            arguments=[]
        ),
        Prompt(
            name="training_recommendation",
            description="根据当前身体状态生成今日训练建议",
            arguments=[]
        ),
        Prompt(
            name="weekly_review",
            description="生成本周健康和训练回顾报告",
            arguments=[]
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict = None):
    """获取提示词模板"""
    if name == "daily_health_check":
        return PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text="""请帮我进行每日健康检查。

请执行以下步骤：
1. 使用 get_health_overview 工具获取我的综合健康数据
2. 分析我的训练、睡眠、准备度数据
3. 评估当前身体状态
4. 指出任何需要注意的风险指标
5. 给出简短的健康评估总结

用中文回复，格式清晰简洁。"""
            )
        )

    elif name == "training_recommendation":
        return PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text="""请根据我的身体状态给出今日训练建议。

请执行以下步骤：
1. 使用 get_health_overview 获取综合健康数据
2. 使用 get_risk_flags 检查风险指标
3. 根据以下标准评估：
   - Zone2目标：每次45-60分钟
   - Zone4-5目标：每次1-5分钟
   - 周Zone2累计：200-300分钟
   - 关注准备度评分（<70需要休息）
4. 给出具体的训练建议，包括：
   - 是否应该训练
   - 建议的训练强度和时长
   - 需要注意的事项

用中文回复，建议要具体可执行。"""
            )
        )

    elif name == "weekly_review":
        return PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text="""请生成本周健康和训练回顾报告。

请执行以下步骤：
1. 使用 get_weekly_trends 获取周趋势数据
2. 使用 get_training_data 获取详细训练记录
3. 使用 get_sleep_data 获取睡眠数据
4. 分析并总结：
   - 本周训练完成情况（与目标对比）
   - 睡眠质量趋势
   - 恢复状态变化
   - 存在的问题
5. 给出下周建议

用中文回复，数据要具体，建议要可行。"""
            )
        )

    raise ValueError(f"未知提示词: {name}")


async def main():
    """主函数"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
