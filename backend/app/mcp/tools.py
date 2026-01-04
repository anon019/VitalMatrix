"""
MCP Tools Implementation

8 个精心设计的健康数据查询工具
"""
import logging
from datetime import date, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.models.polar import PolarExercise
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.models.oura import (
    OuraSleep, OuraDailyReadiness, OuraDailyActivity, OuraDailyStress
)
from app.models.ai import AIRecommendation
from app.models.nutrition import MealRecord, NutritionDailySummary
from app.models.user import User
from app.utils.datetime_helper import today_hk
from app.config import settings

from .server import mcp

logger = logging.getLogger(__name__)


# ============ 辅助函数 ============

async def get_default_user(db: AsyncSession) -> User:
    """获取默认用户（单用户模式）"""
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("未找到用户")
    return user


# ============ MCP Tools ============

@mcp.tool
async def get_health_overview() -> Dict[str, Any]:
    """
    获取综合健康概览

    返回昨日训练、睡眠、准备度、活动、压力数据，以及风险评估和整体状态。
    这是获取健康状态的最佳起点。

    Returns:
        训练数据（昨日+周汇总）、睡眠评分、准备度、活动、压力、风险指标、整体状态摘要
    """
    async with AsyncSessionLocal() as db:
        try:
            user = await get_default_user(db)
            today = today_hk()
            yesterday = today - timedelta(days=1)

            # 获取昨日训练数据
            training_result = await db.execute(
                select(DailyTrainingSummary)
                .where(DailyTrainingSummary.user_id == user.id)
                .where(DailyTrainingSummary.date == yesterday)
            )
            daily_training = training_result.scalar_one_or_none()

            # 获取周训练汇总
            weekly_result = await db.execute(
                select(WeeklyTrainingSummary)
                .where(WeeklyTrainingSummary.user_id == user.id)
                .order_by(desc(WeeklyTrainingSummary.week_start_date))
                .limit(1)
            )
            weekly_training = weekly_result.scalar_one_or_none()

            # 获取昨日 Oura 数据（取最长睡眠记录，排除午睡）
            sleep_result = await db.execute(
                select(OuraSleep)
                .where(OuraSleep.user_id == user.id)
                .where(OuraSleep.day == yesterday)
                .order_by(desc(OuraSleep.total_sleep_duration))
                .limit(1)
            )
            sleep = sleep_result.scalar_one_or_none()

            readiness_result = await db.execute(
                select(OuraDailyReadiness)
                .where(OuraDailyReadiness.user_id == user.id)
                .where(OuraDailyReadiness.day == yesterday)
            )
            readiness = readiness_result.scalar_one_or_none()

            activity_result = await db.execute(
                select(OuraDailyActivity)
                .where(OuraDailyActivity.user_id == user.id)
                .where(OuraDailyActivity.day == yesterday)
            )
            activity = activity_result.scalar_one_or_none()

            stress_result = await db.execute(
                select(OuraDailyStress)
                .where(OuraDailyStress.user_id == user.id)
                .where(OuraDailyStress.day == yesterday)
            )
            stress = stress_result.scalar_one_or_none()

            # 构建数据
            training_data = {
                "yesterday": {
                    "has_data": daily_training is not None,
                    "duration_min": daily_training.total_duration_min if daily_training else 0,
                    "zone2_min": float(daily_training.zone2_min) if daily_training else 0,
                    "zone4_5_min": float(daily_training.hi_min) if daily_training else 0,
                    "sessions": daily_training.sessions_count if daily_training else 0,
                    "trimp": float(daily_training.trimp) if daily_training and daily_training.trimp else 0,
                },
                "weekly": {
                    "has_data": weekly_training is not None,
                    "total_min": weekly_training.total_duration_min if weekly_training else 0,
                    "zone2_min": float(weekly_training.zone2_min) if weekly_training else 0,
                    "zone4_5_min": float(weekly_training.hi_min) if weekly_training else 0,
                    "trimp": float(weekly_training.weekly_trimp) if weekly_training and weekly_training.weekly_trimp else 0,
                }
            }

            sleep_data = {
                "has_data": sleep is not None,
                "score": sleep.sleep_score if sleep else None,
                "total_min": sleep.total_sleep_duration if sleep else None,
                "efficiency": sleep.efficiency if sleep else None,
            }

            readiness_data = {
                "has_data": readiness is not None,
                "score": readiness.score if readiness else None,
                "hrv_balance": readiness.hrv_balance if readiness else None,
                "recovery_index": readiness.recovery_index if readiness else None,
            }

            activity_data = {
                "has_data": activity is not None,
                "score": activity.score if activity else None,
                "steps": activity.steps if activity else None,
                "active_calories": activity.active_calories if activity else None,
            }

            stress_data = {
                "has_data": stress is not None,
                "stress_high": stress.stress_high if stress else None,
                "recovery_high": stress.recovery_high if stress else None,
                "day_summary": stress.day_summary if stress else None,
            }

            # 计算风险指标
            risk_flags = []

            if daily_training and daily_training.zone2_min < settings.TARGET_ZONE2_MIN_RANGE:
                risk_flags.append({
                    "flag": "zone2_low",
                    "level": "medium",
                    "message": f"昨日Zone2时长{daily_training.zone2_min:.0f}分钟，低于目标{settings.TARGET_ZONE2_MIN_RANGE}分钟"
                })

            if daily_training and daily_training.hi_min > settings.TARGET_HI_MAX_RANGE:
                risk_flags.append({
                    "flag": "hi_excessive",
                    "level": "high",
                    "message": f"昨日高强度{daily_training.hi_min:.0f}分钟，超过上限{settings.TARGET_HI_MAX_RANGE}分钟"
                })

            if weekly_training and weekly_training.zone2_min < settings.TARGET_WEEKLY_ZONE2_MIN:
                risk_flags.append({
                    "flag": "weekly_low",
                    "level": "medium",
                    "message": f"本周Zone2累计{weekly_training.zone2_min:.0f}分钟，低于目标{settings.TARGET_WEEKLY_ZONE2_MIN}分钟"
                })

            if weekly_training and weekly_training.hi_min > settings.TARGET_WEEKLY_HI_MAX:
                risk_flags.append({
                    "flag": "weekly_hi_overload",
                    "level": "high",
                    "message": f"本周高强度累计{weekly_training.hi_min:.0f}分钟，超过上限{settings.TARGET_WEEKLY_HI_MAX}分钟"
                })

            if readiness and readiness.score and readiness.score < 70:
                risk_flags.append({
                    "flag": "low_readiness",
                    "level": "high" if readiness.score < 60 else "medium",
                    "message": f"准备度评分{readiness.score}，身体恢复不足"
                })

            if sleep and sleep.sleep_score and sleep.sleep_score < 70:
                risk_flags.append({
                    "flag": "poor_sleep",
                    "level": "medium",
                    "message": f"睡眠评分{sleep.sleep_score}，睡眠质量欠佳"
                })

            # 判断整体状态
            high_risks = [f for f in risk_flags if f["level"] == "high"]
            medium_risks = [f for f in risk_flags if f["level"] == "medium"]

            if high_risks:
                overall_status = "warning"
                summary = "存在较高风险，建议休息或进行轻度恢复性训练"
            elif medium_risks:
                overall_status = "caution"
                summary = "有轻微风险指标，建议适当调整训练强度"
            else:
                overall_status = "good"
                summary = "身体状态良好，可以进行正常训练"

            return {
                "date": today.isoformat(),
                "training": training_data,
                "sleep": sleep_data,
                "readiness": readiness_data,
                "activity": activity_data,
                "stress": stress_data,
                "risk_flags": risk_flags,
                "overall_status": overall_status,
                "summary": summary
            }

        except Exception as e:
            logger.error(f"获取健康概览失败: {str(e)}")
            return {"error": str(e)}


@mcp.tool
async def get_training_data(days: int = 7) -> Dict[str, Any]:
    """
    获取训练数据

    查询指定天数内的所有训练课程和每日汇总。

    Args:
        days: 查询天数 (1-30, 默认7)

    Returns:
        训练课程列表（运动类型、时长、心率区间）、每日汇总、统计数据
    """
    days = max(1, min(30, days))

    async with AsyncSessionLocal() as db:
        try:
            user = await get_default_user(db)
            today = today_hk()
            start_date = today - timedelta(days=days)

            # 获取训练课程
            exercises_result = await db.execute(
                select(PolarExercise)
                .where(PolarExercise.user_id == user.id)
                .where(PolarExercise.start_time >= start_date)
                .order_by(desc(PolarExercise.start_time))
            )
            exercises = exercises_result.scalars().all()

            # 获取每日汇总
            daily_result = await db.execute(
                select(DailyTrainingSummary)
                .where(DailyTrainingSummary.user_id == user.id)
                .where(DailyTrainingSummary.date >= start_date)
                .order_by(desc(DailyTrainingSummary.date))
            )
            daily_summaries = daily_result.scalars().all()

            # 构建训练课程列表
            sessions = []
            for ex in exercises:
                zone4_5_min = ((ex.zone4_sec or 0) + (ex.zone5_sec or 0)) / 60
                sessions.append({
                    "date": ex.start_time.date().isoformat(),
                    "sport": ex.sport_type or "unknown",
                    "duration_min": ex.duration_sec // 60 if ex.duration_sec else 0,
                    "zone2_min": (ex.zone2_sec or 0) / 60,
                    "zone4_5_min": zone4_5_min,
                    "avg_hr": ex.avg_hr,
                    "max_hr": ex.max_hr,
                    "calories": ex.calories
                })

            # 构建每日汇总
            daily_list = []
            for ds in daily_summaries:
                daily_list.append({
                    "date": ds.date.isoformat(),
                    "total_min": ds.total_duration_min,
                    "zone2_min": float(ds.zone2_min) if ds.zone2_min else 0,
                    "hi_min": float(ds.hi_min) if ds.hi_min else 0,
                    "trimp": float(ds.trimp) if ds.trimp else 0,
                    "sessions_count": ds.sessions_count
                })

            # 统计
            total_sessions = len(sessions)
            total_duration = sum(s["duration_min"] for s in sessions)
            total_zone2 = sum(s["zone2_min"] for s in sessions)
            total_zone4_5 = sum(s["zone4_5_min"] for s in sessions)

            return {
                "period_days": days,
                "total_sessions": total_sessions,
                "total_duration_min": total_duration,
                "total_zone2_min": total_zone2,
                "total_zone4_5_min": total_zone4_5,
                "sessions": sessions,
                "daily_summaries": daily_list
            }

        except Exception as e:
            logger.error(f"获取训练数据失败: {str(e)}")
            return {"error": str(e)}


@mcp.tool
async def get_sleep_analysis(days: int = 7) -> Dict[str, Any]:
    """
    获取睡眠质量分析

    查询指定天数内的睡眠记录，包括评分、时长分解、HRV等。

    Args:
        days: 查询天数 (1-30, 默认7)

    Returns:
        睡眠记录列表、平均评分、平均时长
    """
    days = max(1, min(30, days))

    async with AsyncSessionLocal() as db:
        try:
            user = await get_default_user(db)
            today = today_hk()
            start_date = today - timedelta(days=days)

            result = await db.execute(
                select(OuraSleep)
                .where(OuraSleep.user_id == user.id)
                .where(OuraSleep.day >= start_date)
                .order_by(desc(OuraSleep.day))
            )
            sleep_records = result.scalars().all()

            records = []
            scores = []
            durations = []

            for sr in sleep_records:
                records.append({
                    "date": sr.day.isoformat(),
                    "score": sr.sleep_score,
                    "total_sleep_min": sr.total_sleep_duration,
                    "rem_min": sr.rem_sleep_duration,
                    "deep_min": sr.deep_sleep_duration,
                    "light_min": sr.light_sleep_duration,
                    "awake_min": sr.awake_time,
                    "efficiency": sr.efficiency,
                    "avg_hrv": float(sr.average_hrv) if sr.average_hrv else None
                })

                if sr.sleep_score:
                    scores.append(sr.sleep_score)
                if sr.total_sleep_duration:
                    durations.append(sr.total_sleep_duration)

            return {
                "period_days": days,
                "records": records,
                "avg_score": sum(scores) / len(scores) if scores else None,
                "avg_duration_min": sum(durations) / len(durations) if durations else None
            }

        except Exception as e:
            logger.error(f"获取睡眠数据失败: {str(e)}")
            return {"error": str(e)}


@mcp.tool
async def get_readiness_score(days: int = 7) -> Dict[str, Any]:
    """
    获取身体准备度评分

    查询指定天数内的准备度记录，包括 HRV 平衡、恢复指数等贡献因子。

    Args:
        days: 查询天数 (1-30, 默认7)

    Returns:
        准备度记录列表、平均评分、各贡献因子
    """
    days = max(1, min(30, days))

    async with AsyncSessionLocal() as db:
        try:
            user = await get_default_user(db)
            today = today_hk()
            start_date = today - timedelta(days=days)

            result = await db.execute(
                select(OuraDailyReadiness)
                .where(OuraDailyReadiness.user_id == user.id)
                .where(OuraDailyReadiness.day >= start_date)
                .order_by(desc(OuraDailyReadiness.day))
            )
            readiness_records = result.scalars().all()

            records = []
            scores = []

            for rr in readiness_records:
                records.append({
                    "date": rr.day.isoformat(),
                    "score": rr.score,
                    "temperature_deviation": float(rr.temperature_deviation) if rr.temperature_deviation else None,
                    "activity_balance": rr.activity_balance,
                    "body_temperature": rr.body_temperature,
                    "hrv_balance": rr.hrv_balance,
                    "previous_day_activity": rr.previous_day_activity,
                    "previous_night": rr.previous_night,
                    "recovery_index": rr.recovery_index,
                    "resting_heart_rate": rr.resting_heart_rate,
                    "sleep_balance": rr.sleep_balance
                })

                if rr.score:
                    scores.append(rr.score)

            return {
                "period_days": days,
                "records": records,
                "avg_score": sum(scores) / len(scores) if scores else None
            }

        except Exception as e:
            logger.error(f"获取准备度数据失败: {str(e)}")
            return {"error": str(e)}


@mcp.tool
async def get_weekly_trends() -> Dict[str, Any]:
    """
    获取周趋势分析

    返回本周的训练、睡眠、准备度、活动趋势数据。

    Returns:
        训练趋势（每日分钟、Zone2）、睡眠趋势、准备度趋势、活动趋势
    """
    async with AsyncSessionLocal() as db:
        try:
            user = await get_default_user(db)
            today = today_hk()

            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)

            days_data = []
            for i in range(7):
                day = week_start + timedelta(days=i)
                if day > today:
                    break

                # 训练
                training_result = await db.execute(
                    select(DailyTrainingSummary)
                    .where(DailyTrainingSummary.user_id == user.id)
                    .where(DailyTrainingSummary.date == day)
                )
                training = training_result.scalar_one_or_none()

                # 睡眠（取最长睡眠记录，排除午睡）
                sleep_result = await db.execute(
                    select(OuraSleep)
                    .where(OuraSleep.user_id == user.id)
                    .where(OuraSleep.day == day)
                    .order_by(desc(OuraSleep.total_sleep_duration))
                    .limit(1)
                )
                sleep = sleep_result.scalar_one_or_none()

                # 准备度
                readiness_result = await db.execute(
                    select(OuraDailyReadiness)
                    .where(OuraDailyReadiness.user_id == user.id)
                    .where(OuraDailyReadiness.day == day)
                )
                readiness = readiness_result.scalar_one_or_none()

                # 活动
                activity_result = await db.execute(
                    select(OuraDailyActivity)
                    .where(OuraDailyActivity.user_id == user.id)
                    .where(OuraDailyActivity.day == day)
                )
                activity = activity_result.scalar_one_or_none()

                days_data.append({
                    "date": day.isoformat(),
                    "training_min": training.total_duration_min if training else 0,
                    "zone2_min": float(training.zone2_min) if training else 0,
                    "sleep_score": sleep.sleep_score if sleep else None,
                    "readiness_score": readiness.score if readiness else None,
                    "steps": activity.steps if activity else None,
                })

            # 汇总趋势
            training_mins = [d["training_min"] for d in days_data]
            zone2_mins = [d["zone2_min"] for d in days_data]
            sleep_scores = [d["sleep_score"] for d in days_data if d["sleep_score"]]
            readiness_scores = [d["readiness_score"] for d in days_data if d["readiness_score"]]
            steps_list = [d["steps"] for d in days_data if d["steps"]]

            return {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "daily_data": days_data,
                "training_trend": {
                    "total_min": sum(training_mins),
                    "total_zone2_min": sum(zone2_mins),
                    "training_days": sum(1 for m in training_mins if m > 0),
                },
                "sleep_trend": {
                    "avg_score": sum(sleep_scores) / len(sleep_scores) if sleep_scores else None,
                },
                "readiness_trend": {
                    "avg_score": sum(readiness_scores) / len(readiness_scores) if readiness_scores else None,
                },
                "activity_trend": {
                    "avg_steps": sum(steps_list) / len(steps_list) if steps_list else None,
                    "total_steps": sum(steps_list) if steps_list else 0,
                }
            }

        except Exception as e:
            logger.error(f"获取周趋势失败: {str(e)}")
            return {"error": str(e)}


@mcp.tool
async def get_risk_assessment() -> Dict[str, Any]:
    """
    获取健康风险评估

    实时计算当前的健康风险指标，包括 Zone2 不足、高强度过多、准备度低等警告。

    Returns:
        风险指标列表（标志、级别、消息）、整体状态（good/caution/warning）
    """
    # 复用 health_overview 的风险计算逻辑
    overview = await get_health_overview()

    if "error" in overview:
        return overview

    return {
        "risk_flags": overview.get("risk_flags", []),
        "overall_status": overview.get("overall_status", "unknown"),
        "summary": overview.get("summary", "")
    }


@mcp.tool
async def get_ai_recommendation(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    获取 AI 健康建议

    获取指定日期的 AI 生成健康建议，包括昨日评价、今日建议、健康科普。

    Args:
        target_date: 目标日期，格式 YYYY-MM-DD，默认今天

    Returns:
        AI 建议摘要、昨日评价、今日建议、健康科普
    """
    async with AsyncSessionLocal() as db:
        try:
            user = await get_default_user(db)

            if target_date:
                from datetime import datetime
                dt = datetime.fromisoformat(target_date).date()
            else:
                dt = today_hk()

            result = await db.execute(
                select(AIRecommendation)
                .where(AIRecommendation.user_id == user.id)
                .where(AIRecommendation.date == dt)
                .order_by(desc(AIRecommendation.created_at))
                .limit(1)
            )
            recommendation = result.scalar_one_or_none()

            if recommendation:
                return {
                    "date": recommendation.date.isoformat(),
                    "summary": recommendation.summary,
                    "yesterday_review": recommendation.yesterday_review,
                    "today_recommendation": recommendation.today_recommendation,
                    "health_education": recommendation.health_education,
                    "provider": recommendation.provider,
                    "generated_at": recommendation.created_at.isoformat() if recommendation.created_at else None
                }
            else:
                return {
                    "date": dt.isoformat(),
                    "summary": "暂无 AI 建议",
                    "message": "该日期的 AI 建议尚未生成，请使用 get_health_overview 获取实时数据"
                }

        except Exception as e:
            logger.error(f"获取 AI 建议失败: {str(e)}")
            return {"error": str(e)}


@mcp.tool
async def get_nutrition_data(days: int = 7) -> Dict[str, Any]:
    """
    获取饮食营养数据

    查询指定天数内的餐食记录和营养汇总。

    Args:
        days: 查询天数 (1-30, 默认7)

    Returns:
        餐食记录列表、每日营养汇总、周平均热量/蛋白质/碳水/脂肪
    """
    days = max(1, min(30, days))

    async with AsyncSessionLocal() as db:
        try:
            user = await get_default_user(db)
            today = today_hk()
            start_date = today - timedelta(days=days)

            # 获取餐食记录
            meals_result = await db.execute(
                select(MealRecord)
                .where(MealRecord.user_id == user.id)
                .where(MealRecord.meal_time >= start_date)
                .order_by(desc(MealRecord.meal_time))
            )
            meals = meals_result.scalars().all()

            # 获取每日营养汇总
            summaries_result = await db.execute(
                select(NutritionDailySummary)
                .where(NutritionDailySummary.user_id == user.id)
                .where(NutritionDailySummary.date >= start_date)
                .order_by(desc(NutritionDailySummary.date))
            )
            summaries = summaries_result.scalars().all()

            # 构建餐食列表
            meal_list = []
            for meal in meals:
                meal_list.append({
                    "date": meal.meal_time.date().isoformat(),
                    "time": meal.meal_time.strftime("%H:%M"),
                    "meal_type": meal.meal_type.value if meal.meal_type else None,
                    "total_calories": float(meal.total_calories) if meal.total_calories else None,
                    "total_protein": float(meal.total_protein) if meal.total_protein else None,
                    "total_carbs": float(meal.total_carbs) if meal.total_carbs else None,
                    "total_fat": float(meal.total_fat) if meal.total_fat else None,
                    "notes": meal.notes
                })

            # 构建每日汇总
            daily_list = []
            total_calories = []
            total_protein = []
            total_carbs = []
            total_fat = []

            for s in summaries:
                daily_list.append({
                    "date": s.date.isoformat(),
                    "total_calories": float(s.total_calories) if s.total_calories else 0,
                    "total_protein": float(s.total_protein) if s.total_protein else 0,
                    "total_carbs": float(s.total_carbs) if s.total_carbs else 0,
                    "total_fat": float(s.total_fat) if s.total_fat else 0,
                    "meals_count": s.meals_count
                })

                if s.total_calories:
                    total_calories.append(float(s.total_calories))
                if s.total_protein:
                    total_protein.append(float(s.total_protein))
                if s.total_carbs:
                    total_carbs.append(float(s.total_carbs))
                if s.total_fat:
                    total_fat.append(float(s.total_fat))

            return {
                "period_days": days,
                "total_meals": len(meals),
                "meals": meal_list,
                "daily_summaries": daily_list,
                "averages": {
                    "avg_calories": sum(total_calories) / len(total_calories) if total_calories else None,
                    "avg_protein": sum(total_protein) / len(total_protein) if total_protein else None,
                    "avg_carbs": sum(total_carbs) / len(total_carbs) if total_carbs else None,
                    "avg_fat": sum(total_fat) / len(total_fat) if total_fat else None,
                }
            }

        except Exception as e:
            logger.error(f"获取营养数据失败: {str(e)}")
            return {"error": str(e)}
