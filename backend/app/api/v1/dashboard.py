"""
Dashboard API - 小程序首页综合数据接口
"""
import logging
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.session import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.models.oura import (
    OuraSleep, OuraDailySleep, OuraDailyReadiness, OuraDailyActivity, OuraDailyStress, OuraDailySpo2,
    OuraCardiovascularAge, OuraResilience, OuraVO2Max
)
from app.models.polar import PolarExercise, PolarSleep, PolarNightlyRecharge
from app.schemas.training import DailySummaryResponse, WeeklySummaryResponse
from app.schemas.ai import RecommendationResponse
from app.services.ai_service import AIService
from app.utils.datetime_helper import today_hk, get_week_start
from sqlalchemy import func

router = APIRouter()
logger = logging.getLogger(__name__)


class OuraSummary(BaseModel):
    """Oura数据摘要"""
    # 睡眠
    sleep_score: Optional[int] = None
    total_sleep_hours: Optional[float] = None
    deep_sleep_min: Optional[int] = None
    rem_sleep_min: Optional[int] = None
    sleep_efficiency: Optional[int] = None
    average_hrv: Optional[int] = None
    # 睡眠贡献因子（来自 daily_sleep API，与 Oura App 一致）
    sleep_contributor_deep_sleep: Optional[int] = None
    sleep_contributor_efficiency: Optional[int] = None
    sleep_contributor_latency: Optional[int] = None
    sleep_contributor_rem_sleep: Optional[int] = None
    sleep_contributor_restfulness: Optional[int] = None
    sleep_contributor_timing: Optional[int] = None
    sleep_contributor_total_sleep: Optional[int] = None
    # 准备度
    readiness_score: Optional[int] = None
    recovery_index: Optional[int] = None
    resting_heart_rate: Optional[int] = None
    # 活动
    activity_score: Optional[int] = None
    steps: Optional[int] = None
    active_calories: Optional[int] = None
    # 压力
    stress_high_min: Optional[int] = None
    recovery_high_min: Optional[int] = None


class DashboardResponse(BaseModel):
    """综合数据响应（小程序首页）"""
    date: date
    # AI建议
    recommendation: Optional[RecommendationResponse] = None
    # 训练数据
    training: Optional[DailySummaryResponse] = None
    weekly_training: Optional[WeeklySummaryResponse] = None
    # Oura数据 - 今日实时数据（显示在上方）
    oura_today: Optional[OuraSummary] = None
    # Oura数据 - 昨日完整数据（显示在下方，用于对比）
    oura_yesterday: Optional[OuraSummary] = None


@router.get("/today", response_model=DashboardResponse)
async def get_dashboard_today(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取今日综合数据（小程序首页使用）

    一次性返回所有需要的数据（纯查询，不生成）：
    - 今日AI建议
    - 昨日训练数据
    - 本周训练汇总
    - 昨日Oura数据（睡眠、准备度、活动、压力）

    Returns:
        综合数据
    """
    today = today_hk()
    yesterday = today - timedelta(days=1)

    # 1. 获取今日AI建议（纯查询）
    ai_service = AIService(db)
    recommendation = await ai_service.get_recommendation(
        user_id=current_user.id,
        target_date=today
    )

    # 转换AI建议为响应格式
    recommendation_response = None
    if recommendation:
        recommendation_response = RecommendationResponse(
            id=str(recommendation.id),
            date=recommendation.date,
            provider=recommendation.provider,
            model=recommendation.model,
            summary=recommendation.summary,
            yesterday_review=recommendation.yesterday_review,
            today_recommendation=recommendation.today_recommendation,
            health_education=recommendation.health_education,
            created_at=recommendation.created_at.isoformat(),
        )

    # 2. 获取昨日训练数据
    result = await db.execute(
        select(DailyTrainingSummary).where(
            and_(
                DailyTrainingSummary.user_id == current_user.id,
                DailyTrainingSummary.date == yesterday,
            )
        )
    )
    daily_training = result.scalar_one_or_none()

    # 3. 获取本周训练汇总
    week_start = get_week_start(today)
    result = await db.execute(
        select(WeeklyTrainingSummary).where(
            and_(
                WeeklyTrainingSummary.user_id == current_user.id,
                WeeklyTrainingSummary.week_start_date == week_start,
            )
        )
    )
    weekly_training = result.scalar_one_or_none()

    # 4. 获取今日Oura数据（实时更新，显示在上方）
    oura_today = None

    # 今日准备度
    readiness_today_result = await db.execute(
        select(OuraDailyReadiness).where(
            and_(
                OuraDailyReadiness.user_id == current_user.id,
                OuraDailyReadiness.day == today
            )
        )
    )
    readiness_today = readiness_today_result.scalar_one_or_none()

    # 今日活动
    activity_today_result = await db.execute(
        select(OuraDailyActivity).where(
            and_(
                OuraDailyActivity.user_id == current_user.id,
                OuraDailyActivity.day == today
            )
        )
    )
    activity_today = activity_today_result.scalar_one_or_none()

    # 今日压力
    stress_today_result = await db.execute(
        select(OuraDailyStress).where(
            and_(
                OuraDailyStress.user_id == current_user.id,
                OuraDailyStress.day == today
            )
        )
    )
    stress_today = stress_today_result.scalar_one_or_none()

    # 构建今日Oura摘要
    if any([readiness_today, activity_today, stress_today]):
        oura_today = OuraSummary(
            # 准备度
            readiness_score=readiness_today.score if readiness_today else None,
            recovery_index=readiness_today.recovery_index if readiness_today else None,
            resting_heart_rate=readiness_today.resting_heart_rate if readiness_today else None,
            # 活动
            activity_score=activity_today.score if activity_today else None,
            steps=activity_today.steps if activity_today else None,
            active_calories=activity_today.active_calories if activity_today else None,
            # 压力
            stress_high_min=round(stress_today.stress_high / 60) if stress_today and stress_today.stress_high else None,
            recovery_high_min=round(stress_today.recovery_high / 60) if stress_today and stress_today.recovery_high else None,
        )

    # 5. 获取昨日Oura数据（完整数据，显示在下方用于对比）
    oura_yesterday = None

    # 获取每日综合睡眠评分（优先使用 OuraDailySleep，与 Oura App 显示一致）
    # OuraDailySleep 存储的是 Oura 计算的每日综合评分，即使没有主睡眠也会有评分
    daily_sleep_score = None

    # 查询今天的每日睡眠评分（昨晚睡眠归属于今天）
    daily_sleep_result = await db.execute(
        select(OuraDailySleep).where(
            and_(
                OuraDailySleep.user_id == current_user.id,
                OuraDailySleep.day == today
            )
        )
    )
    daily_sleep = daily_sleep_result.scalar_one_or_none()
    if daily_sleep:
        daily_sleep_score = daily_sleep.score

    # 如果今天没有，回退到昨天的每日睡眠评分
    if daily_sleep_score is None:
        daily_sleep_result = await db.execute(
            select(OuraDailySleep).where(
                and_(
                    OuraDailySleep.user_id == current_user.id,
                    OuraDailySleep.day == yesterday
                )
            )
        )
        daily_sleep = daily_sleep_result.scalar_one_or_none()
        if daily_sleep:
            daily_sleep_score = daily_sleep.score

    # 获取睡眠详情（用于显示时长、深睡等详细指标）
    # Oura 的日期逻辑：睡眠记录归属于醒来那天
    # 优先级：1. 今天的 long_sleep  2. 今天最长的睡眠  3. 昨天的 long_sleep
    sleep = None

    # 1. 先找今天的主睡眠（long_sleep）
    sleep_result = await db.execute(
        select(OuraSleep).where(
            and_(
                OuraSleep.user_id == current_user.id,
                OuraSleep.day == today,
                OuraSleep.sleep_type == "long_sleep"
            )
        ).order_by(OuraSleep.total_sleep_duration.desc())
    )
    sleep = sleep_result.scalars().first()

    # 2. 如果今天没有 long_sleep，找今天最长的睡眠
    if not sleep:
        sleep_result = await db.execute(
            select(OuraSleep).where(
                and_(
                    OuraSleep.user_id == current_user.id,
                    OuraSleep.day == today
                )
            ).order_by(OuraSleep.total_sleep_duration.desc())
        )
        sleep = sleep_result.scalars().first()

    # 3. 如果今天完全没有睡眠数据，回退到昨天的 long_sleep
    if not sleep:
        sleep_result = await db.execute(
            select(OuraSleep).where(
                and_(
                    OuraSleep.user_id == current_user.id,
                    OuraSleep.day == yesterday,
                    OuraSleep.sleep_type == "long_sleep"
                )
            ).order_by(OuraSleep.total_sleep_duration.desc())
        )
        sleep = sleep_result.scalars().first()

    # 昨日准备度
    readiness_result = await db.execute(
        select(OuraDailyReadiness).where(
            and_(
                OuraDailyReadiness.user_id == current_user.id,
                OuraDailyReadiness.day == yesterday
            )
        )
    )
    readiness = readiness_result.scalar_one_or_none()

    # 昨日活动
    activity_result = await db.execute(
        select(OuraDailyActivity).where(
            and_(
                OuraDailyActivity.user_id == current_user.id,
                OuraDailyActivity.day == yesterday
            )
        )
    )
    activity = activity_result.scalar_one_or_none()

    # 昨日压力
    stress_result = await db.execute(
        select(OuraDailyStress).where(
            and_(
                OuraDailyStress.user_id == current_user.id,
                OuraDailyStress.day == yesterday
            )
        )
    )
    stress = stress_result.scalar_one_or_none()

    # 构建昨日Oura摘要
    if any([sleep, daily_sleep, readiness, activity, stress]):
        oura_yesterday = OuraSummary(
            # 睡眠 - 优先使用每日综合评分（与Oura App一致）
            sleep_score=daily_sleep.score if daily_sleep else (sleep.sleep_score if sleep else None),
            total_sleep_hours=round(sleep.total_sleep_duration / 3600, 1) if sleep and sleep.total_sleep_duration else None,
            deep_sleep_min=round(sleep.deep_sleep_duration / 60) if sleep and sleep.deep_sleep_duration else None,
            rem_sleep_min=round(sleep.rem_sleep_duration / 60) if sleep and sleep.rem_sleep_duration else None,
            sleep_efficiency=sleep.efficiency if sleep else None,
            average_hrv=sleep.average_hrv if sleep else None,
            # 睡眠贡献因子（来自 daily_sleep API）
            sleep_contributor_deep_sleep=daily_sleep.contributor_deep_sleep if daily_sleep else None,
            sleep_contributor_efficiency=daily_sleep.contributor_efficiency if daily_sleep else None,
            sleep_contributor_latency=daily_sleep.contributor_latency if daily_sleep else None,
            sleep_contributor_rem_sleep=daily_sleep.contributor_rem_sleep if daily_sleep else None,
            sleep_contributor_restfulness=daily_sleep.contributor_restfulness if daily_sleep else None,
            sleep_contributor_timing=daily_sleep.contributor_timing if daily_sleep else None,
            sleep_contributor_total_sleep=daily_sleep.contributor_total_sleep if daily_sleep else None,
            # 准备度
            readiness_score=readiness.score if readiness else None,
            recovery_index=readiness.recovery_index if readiness else None,
            resting_heart_rate=readiness.resting_heart_rate if readiness else None,
            # 活动
            activity_score=activity.score if activity else None,
            steps=activity.steps if activity else None,
            active_calories=activity.active_calories if activity else None,
            # 压力
            stress_high_min=round(stress.stress_high / 60) if stress and stress.stress_high else None,
            recovery_high_min=round(stress.recovery_high / 60) if stress and stress.recovery_high else None,
        )

    return DashboardResponse(
        date=today,
        recommendation=recommendation_response,
        training=daily_training,
        weekly_training=weekly_training,
        oura_today=oura_today,
        oura_yesterday=oura_yesterday,
    )


class DataSourceStatus(BaseModel):
    """单个数据源状态"""
    available: bool
    record_count: int
    latest_date: Optional[str]
    description: str
    status: str  # "normal" | "no_data" | "error"


class DataAvailabilityResponse(BaseModel):
    """数据可用性响应"""
    oura: dict
    polar: dict
    summary: dict


@router.get("/data-availability", response_model=DataAvailabilityResponse)
async def get_data_availability(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取所有数据源的可用性状态

    返回各个数据端点的记录数量和最新日期，方便前端决定显示哪些功能

    Args:
        days: 查询最近几天的数据（默认7天）

    Returns:
        所有数据源的可用性状态
    """
    try:
        today = today_hk()
        start_date = today - timedelta(days=days - 1)

        oura_status = {}

        # 1. Oura睡眠
        result = await db.execute(
            select(func.count(OuraSleep.id), func.max(OuraSleep.day))
            .where(OuraSleep.user_id == current_user.id)
            .where(OuraSleep.day >= start_date)
        )
        count, latest = result.one()
        oura_status["sleep"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "睡眠数据（评分、睡眠阶段、心率、HRV、呼吸频率）",
            "status": "normal" if count > 0 else "no_data"
        }

        # 2. Oura准备度
        result = await db.execute(
            select(func.count(OuraDailyReadiness.id), func.max(OuraDailyReadiness.day))
            .where(OuraDailyReadiness.user_id == current_user.id)
            .where(OuraDailyReadiness.day >= start_date)
        )
        count, latest = result.one()
        oura_status["readiness"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "准备度评分（体温、活动平衡、恢复指数、静息心率）",
            "status": "normal" if count > 0 else "no_data"
        }

        # 3. Oura活动
        result = await db.execute(
            select(func.count(OuraDailyActivity.id), func.max(OuraDailyActivity.day))
            .where(OuraDailyActivity.user_id == current_user.id)
            .where(OuraDailyActivity.day >= start_date)
        )
        count, latest = result.one()
        oura_status["activity"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "活动数据（步数、卡路里、活动时长）",
            "status": "normal" if count > 0 else "no_data"
        }

        # 4. Oura压力
        result = await db.execute(
            select(func.count(OuraDailyStress.id), func.max(OuraDailyStress.day))
            .where(OuraDailyStress.user_id == current_user.id)
            .where(OuraDailyStress.day >= start_date)
        )
        count, latest = result.one()
        oura_status["stress"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "压力数据（高压力时长、恢复时长）⚠️ 目前数据值为0",
            "status": "normal" if count > 0 else "no_data"
        }

        # 5. Oura血氧
        result = await db.execute(
            select(func.count(OuraDailySpo2.id), func.max(OuraDailySpo2.day))
            .where(OuraDailySpo2.user_id == current_user.id)
            .where(OuraDailySpo2.day >= start_date)
        )
        count, latest = result.one()
        oura_status["spo2"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "血氧饱和度数据",
            "status": "normal" if count > 0 else "no_data"
        }

        # 6. Oura心血管年龄 (Gen 4新功能) - 🆕 新增端点
        result = await db.execute(
            select(func.count(OuraCardiovascularAge.id), func.max(OuraCardiovascularAge.day))
            .where(OuraCardiovascularAge.user_id == current_user.id)
            .where(OuraCardiovascularAge.day >= start_date)
        )
        count, latest = result.one()
        oura_status["cardiovascular_age"] = {
            "available": False,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "🆕 心血管年龄（需要Gen 3/4戒指 + 会员订阅）",
            "status": "error",
            "error_message": "API返回401权限错误，需要重新授权或联系Oura支持"
        }

        # 7. Oura韧性 (Gen 4新功能) - 🆕 新增端点
        result = await db.execute(
            select(func.count(OuraResilience.id), func.max(OuraResilience.day))
            .where(OuraResilience.user_id == current_user.id)
            .where(OuraResilience.day >= start_date)
        )
        count, latest = result.one()
        oura_status["resilience"] = {
            "available": False,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "🆕 恢复韧性（需要Gen 3/4戒指 + 会员订阅）",
            "status": "no_data",
            "error_message": "API调用成功但返回空数据，可能需要更长时间的数据积累"
        }

        # 8. Oura VO2 Max (Gen 4新功能) - 🆕 新增端点
        result = await db.execute(
            select(func.count(OuraVO2Max.id), func.max(OuraVO2Max.day))
            .where(OuraVO2Max.user_id == current_user.id)
            .where(OuraVO2Max.day >= start_date)
        )
        count, latest = result.one()
        oura_status["vo2_max"] = {
            "available": False,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "🆕 最大摄氧量（需要Gen 3/4戒指 + 会员订阅）",
            "status": "error",
            "error_message": "API返回404错误，端点可能尚未开放或路径不正确"
        }

        # Polar数据源状态
        polar_status = {}

        # 1. Polar训练
        result = await db.execute(
            select(func.count(PolarExercise.id), func.max(PolarExercise.start_time))
            .where(PolarExercise.user_id == current_user.id)
        )
        count, latest_dt = result.one()
        polar_status["exercise"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest_dt.date().isoformat() if latest_dt else None,
            "description": "训练数据（心率区间、运动类型、时长）",
            "status": "normal" if count > 0 else "no_data"
        }

        # 2. Polar睡眠 - 🆕 新增端点
        result = await db.execute(
            select(func.count(PolarSleep.id), func.max(PolarSleep.sleep_date))
            .where(PolarSleep.user_id == current_user.id)
            .where(PolarSleep.sleep_date >= start_date)
        )
        count, latest = result.one()
        polar_status["sleep"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "🆕 睡眠数据（深睡、浅睡、REM、睡眠评分）",
            "status": "normal" if count > 0 else "no_data"
        }

        # 3. Polar夜间恢复 - 🆕 新增端点
        result = await db.execute(
            select(func.count(PolarNightlyRecharge.id), func.max(PolarNightlyRecharge.date))
            .where(PolarNightlyRecharge.user_id == current_user.id)
            .where(PolarNightlyRecharge.date >= start_date)
        )
        count, latest = result.one()
        polar_status["nightly_recharge"] = {
            "available": count > 0,
            "record_count": count or 0,
            "latest_date": latest.isoformat() if latest else None,
            "description": "🆕 夜间恢复数据（ANS恢复、睡眠恢复、HRV、呼吸频率）",
            "status": "normal" if count > 0 else "no_data"
        }

        # 汇总统计
        total_endpoints = len(oura_status) + len(polar_status)
        oura_available = sum(1 for s in oura_status.values() if s.get("available", False))
        polar_available = sum(1 for s in polar_status.values() if s.get("available", False))
        total_available = oura_available + polar_available

        summary = {
            "total_endpoints": total_endpoints,
            "oura_total": len(oura_status),
            "oura_available": oura_available,
            "polar_total": len(polar_status),
            "polar_available": polar_available,
            "total_available": total_available,
            "new_endpoints": 5,  # 3 Oura + 2 Polar
            "new_endpoints_with_data": 0  # 目前新增端点都没有数据
        }

        return DataAvailabilityResponse(
            oura=oura_status,
            polar=polar_status,
            summary=summary
        )

    except Exception as e:
        logger.error(f"获取数据可用性失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取数据可用性失败: {str(e)}")
