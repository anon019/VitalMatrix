"""Shared prompt sections for structured training and Oura context."""
from typing import Optional
from datetime import date, timedelta

from app.ai.base import OuraData, TrainingData


def _value(value, suffix: str = "") -> str:
    return f"{value}{suffix}" if value is not None else "N/A"


def build_training_section(training_data: TrainingData) -> str:
    """Render aggregates plus per-session details without assuming one sport type."""
    sections = [
        "## 昨日训练汇总",
        f"- 总时长：{training_data.total_duration_min}分钟",
        f"- Zone2时长：{training_data.zone2_min}分钟",
        f"- 高强度（Zone4-5）：{training_data.hi_min}分钟",
        f"- 训练负荷（TRIMP）：{training_data.trimp}",
        f"- 平均心率：{_value(training_data.avg_hr, 'bpm')}",
        f"- 运动类型：{training_data.sport_type or '昨日无训练明细'}",
        "",
        "## 近7天逐次训练明细",
    ]

    if training_data.sessions:
        for session in training_data.sessions:
            detail = [
                f"{session.date} {session.start_time}-{session.end_time}",
                session.sport_type,
                f"{session.duration_min}分钟",
                f"心率均值/峰值 {_value(session.avg_hr, 'bpm')}/{_value(session.max_hr, 'bpm')}",
                "心率区间 Z1/Z2/Z3/Z4/Z5 "
                f"{session.zone1_min}/{session.zone2_min}/{session.zone3_min}/"
                f"{session.zone4_min}/{session.zone5_min}分钟",
            ]
            if session.cardio_load is not None:
                detail.append(f"负荷{session.cardio_load:g}")
            if session.calories is not None:
                detail.append(f"消耗{session.calories}kcal")
            if session.distance_km is not None:
                detail.append(f"距离{session.distance_km:g}km")
            sections.append(f"- {'；'.join(detail)}")
    else:
        sections.append("- 暂无逐次训练记录")

    sections.extend([
        "",
        "分析要求：逐次识别运动类型、时长、发生时间、心率区间和负荷；不同类型分开评估，"
        "不要用单一 Zone2/TRIMP 指标替代专项分析。若出现新的运动类型，先根据其动作模式、"
        "主要供能系统和常见负荷特征判断，再结合恢复状态给建议。",
        "",
        "## 本周训练汇总",
        f"- 总时长：{training_data.weekly_total}分钟",
        f"- Zone2累计：{training_data.weekly_zone2}分钟",
        f"- 高强度累计：{training_data.weekly_hi}分钟",
        f"- 周训练负荷：{training_data.weekly_trimp}",
        f"- 训练天数：{training_data.training_days}天",
        f"- 休息天数：{training_data.rest_days}天",
    ])
    if training_data.target_date:
        target = date.fromisoformat(training_data.target_date)
        sections.append(f"统计口径：逐次明细为{target - timedelta(days=7)}至{target - timedelta(days=1)}；本周汇总从{target - timedelta(days=target.weekday())}开始，是不完整自然周，与滚动7天不可直接比较。")
    return "\n".join(sections)


def build_oura_data_section(oura_data: Optional[OuraData], target_date: Optional[str] = None) -> str:
    """Render current recovery signals and a compact seven-day Oura timeline."""
    if not oura_data:
        return "## Oura综合上下文\n暂无数据"

    sections = ["## Oura当前恢复与昨日活动"]
    if oura_data.sleep_score is not None:
        sections.append(
            "- 睡眠："
            f"评分{oura_data.sleep_score}/100，时长{_value(oura_data.total_sleep_hours, '小时')}，"
            f"深睡{_value(oura_data.deep_sleep_min, '分钟')}，REM{_value(oura_data.rem_sleep_min, '分钟')}，"
            f"效率{_value(oura_data.sleep_efficiency, '%')}，HRV{_value(oura_data.average_hrv, 'ms')}"
        )
    if oura_data.readiness_score is not None:
        sections.append(
            "- 准备度："
            f"评分{oura_data.readiness_score}/100，恢复指数{_value(oura_data.recovery_index)}，"
            f"静息心率{_value(oura_data.resting_heart_rate, 'bpm')}，"
            f"HRV平衡{_value(oura_data.hrv_balance)}"
        )
    if any(value is not None for value in (
        oura_data.activity_score,
        oura_data.steps,
        oura_data.active_calories,
        oura_data.sedentary_min,
        oura_data.inactivity_alerts,
    )):
        sections.append(
            "- 活动："
            f"评分{_value(oura_data.activity_score, '/100')}，步数{_value(oura_data.steps)}，"
            f"活动消耗{_value(oura_data.active_calories, 'kcal')}，"
            f"久坐{_value(oura_data.sedentary_min, '分钟')}，"
            f"久坐提醒{_value(oura_data.inactivity_alerts, '次')}"
        )
    if oura_data.stress_high_min is not None or oura_data.day_summary:
        sections.append(
            "- 压力："
            f"状态{oura_data.day_summary or 'N/A'}，"
            f"高压力{_value(oura_data.stress_high_min, '分钟')}，"
            f"高恢复{_value(oura_data.recovery_high_min, '分钟')}"
        )

    sections.append("\n## 近7天 Oura 日级上下文")
    if not oura_data.recent_days:
        sections.append("- 暂无可用日级数据")
    else:
        cutoff = (date.fromisoformat(target_date) - timedelta(days=6)).isoformat() if target_date else ""
        for day in oura_data.recent_days[-7:]:
            if day.date < cutoff:
                continue
            sections.append(
                f"- {day.date}：睡眠评分{_value(day.sleep_score)}，睡眠{_value(day.total_sleep_hours, '小时')}，"
                f"HRV{_value(day.average_hrv, 'ms')}，静息心率{_value(day.resting_heart_rate, 'bpm')}，"
                f"准备度{_value(day.readiness_score)}，活动评分{_value(day.activity_score)}，"
                f"步数{_value(day.steps)}，活动消耗{_value(day.active_calories, 'kcal')}，高/中/低强度活动"
                f"{_value(day.high_activity_min)}/{_value(day.medium_activity_min)}/{_value(day.low_activity_min)}分钟，"
                f"久坐{_value(day.sedentary_min, '分钟')}，久坐提醒{_value(day.inactivity_alerts, '次')}，"
                f"高压力/高恢复{_value(day.stress_high_min)}/{_value(day.recovery_high_min)}分钟，"
                f"日状态{day.day_summary or 'N/A'}"
            )

    sections.append(
        "分析要求：把睡眠、准备度、日常活动、久坐、压力与专项训练放在同一时间轴上综合判断；"
        "优先使用连续多日模式，单日数据不足时明确不确定性，不把相关性写成因果。"
    )
    return "\n".join(sections)
