"""
训练数据API
"""
import logging
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.database.session import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.polar import PolarExercise
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.models.oura import OuraSleep, OuraDailyReadiness, OuraDailyActivity, OuraDailyStress
from app.models.ai import AIRecommendation
from app.schemas.training import (
    ExerciseResponse,
    DailySummaryResponse,
    WeeklySummaryResponse,
    TrainingHistoryResponse
)
from app.schemas.ai import RecommendationResponse
from app.services.ai_service import AIService
from app.services.training_metrics import TrainingMetricsService
from app.utils.datetime_helper import today_hk, get_week_start

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/today", response_model=Optional[DailySummaryResponse])
async def get_today_training(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取今日训练数据（实际是昨天的数据）

    Returns:
        昨日训练总结
    """
    yesterday = today_hk() - timedelta(days=1)

    result = await db.execute(
        select(DailyTrainingSummary).where(
            and_(
                DailyTrainingSummary.user_id == current_user.id,
                DailyTrainingSummary.date == yesterday,
            )
        )
    )
    summary = result.scalar_one_or_none()

    return summary


@router.get("/weekly", response_model=Optional[WeeklySummaryResponse])
async def get_weekly_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取本周训练总结

    Returns:
        周训练总结
    """
    week_start = get_week_start(today_hk())

    result = await db.execute(
        select(WeeklyTrainingSummary).where(
            and_(
                WeeklyTrainingSummary.user_id == current_user.id,
                WeeklyTrainingSummary.week_start_date == week_start,
            )
        )
    )
    summary = result.scalar_one_or_none()

    return summary


@router.get("/history", response_model=TrainingHistoryResponse)
async def get_training_history(
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取训练历史记录

    Args:
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
        page: 页码
        page_size: 每页数量

    Returns:
        训练历史列表
    """
    # 构建查询条件
    conditions = [PolarExercise.user_id == current_user.id]

    if start_date:
        conditions.append(func.date(PolarExercise.start_time) >= start_date)
    if end_date:
        conditions.append(func.date(PolarExercise.start_time) <= end_date)

    # 查询总数
    count_result = await db.execute(
        select(func.count()).select_from(PolarExercise).where(and_(*conditions))
    )
    total_count = count_result.scalar()

    # 查询数据（分页）
    offset = (page - 1) * page_size
    result = await db.execute(
        select(PolarExercise)
        .where(and_(*conditions))
        .order_by(PolarExercise.start_time.desc())
        .limit(page_size)
        .offset(offset)
    )
    exercises = result.scalars().all()

    # 转换为响应格式
    exercise_responses = []
    for exercise in exercises:
        exercise_responses.append(
            ExerciseResponse(
                id=str(exercise.id),
                start_time=exercise.start_time,
                end_time=exercise.end_time,
                sport_type=exercise.sport_type,
                duration_sec=exercise.duration_sec,
                avg_hr=exercise.avg_hr,
                max_hr=exercise.max_hr,
                zone1_sec=exercise.zone1_sec,
                zone2_sec=exercise.zone2_sec,
                zone3_sec=exercise.zone3_sec,
                zone4_sec=exercise.zone4_sec,
                zone5_sec=exercise.zone5_sec,
                # Zone boundaries
                zone1_lower=exercise.zone1_lower,
                zone1_upper=exercise.zone1_upper,
                zone2_lower=exercise.zone2_lower,
                zone2_upper=exercise.zone2_upper,
                zone3_lower=exercise.zone3_lower,
                zone3_upper=exercise.zone3_upper,
                zone4_lower=exercise.zone4_lower,
                zone4_upper=exercise.zone4_upper,
                zone5_lower=exercise.zone5_lower,
                zone5_upper=exercise.zone5_upper,
                calories=exercise.calories,
                cardio_load=exercise.cardio_load,
                distance_meters=exercise.distance_meters,
                zone2_min=exercise.zone2_min,
                hi_min=exercise.hi_min,
                zone2_ratio=exercise.zone2_ratio,
                hi_ratio=exercise.hi_ratio,
            )
        )

    return TrainingHistoryResponse(
        exercises=exercise_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/daily/{target_date}", response_model=Optional[DailySummaryResponse])
async def get_daily_summary(
    target_date: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定日期的训练总结

    Args:
        target_date: 目标日期

    Returns:
        日训练总结
    """
    result = await db.execute(
        select(DailyTrainingSummary).where(
            and_(
                DailyTrainingSummary.user_id == current_user.id,
                DailyTrainingSummary.date == target_date,
            )
        )
    )
    summary = result.scalar_one_or_none()

    return summary


# ============ 综合数据接口 ============

class OuraSummary(BaseModel):
    """Oura数据摘要"""
    # 睡眠
    sleep_score: Optional[int] = None
    total_sleep_hours: Optional[float] = None
    deep_sleep_min: Optional[int] = None
    rem_sleep_min: Optional[int] = None
    sleep_efficiency: Optional[int] = None
    average_hrv: Optional[int] = None
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
    # Oura数据
    oura: Optional[OuraSummary] = None


@router.get("/summary", response_model=DashboardResponse)
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取综合数据摘要（小程序首页使用）

    包含（纯查询，不生成）：
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

    # 4. 获取昨日Oura数据
    oura_summary = None

    # 睡眠
    sleep_result = await db.execute(
        select(OuraSleep).where(
            and_(
                OuraSleep.user_id == current_user.id,
                OuraSleep.day == yesterday
            )
        )
    )
    sleep = sleep_result.scalar_one_or_none()

    # 准备度
    readiness_result = await db.execute(
        select(OuraDailyReadiness).where(
            and_(
                OuraDailyReadiness.user_id == current_user.id,
                OuraDailyReadiness.day == yesterday
            )
        )
    )
    readiness = readiness_result.scalar_one_or_none()

    # 活动
    activity_result = await db.execute(
        select(OuraDailyActivity).where(
            and_(
                OuraDailyActivity.user_id == current_user.id,
                OuraDailyActivity.day == yesterday
            )
        )
    )
    activity = activity_result.scalar_one_or_none()

    # 压力
    stress_result = await db.execute(
        select(OuraDailyStress).where(
            and_(
                OuraDailyStress.user_id == current_user.id,
                OuraDailyStress.day == yesterday
            )
        )
    )
    stress = stress_result.scalar_one_or_none()

    # 构建Oura摘要
    if any([sleep, readiness, activity, stress]):
        oura_summary = OuraSummary(
            # 睡眠
            sleep_score=sleep.sleep_score if sleep else None,
            total_sleep_hours=round(sleep.total_sleep_duration / 3600, 1) if sleep and sleep.total_sleep_duration else None,
            deep_sleep_min=round(sleep.deep_sleep_duration / 60) if sleep and sleep.deep_sleep_duration else None,
            rem_sleep_min=round(sleep.rem_sleep_duration / 60) if sleep and sleep.rem_sleep_duration else None,
            sleep_efficiency=sleep.efficiency if sleep else None,
            average_hrv=sleep.average_hrv if sleep else None,
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
        oura=oura_summary,
    )


class RecalculateResponse(BaseModel):
    """重新计算响应"""
    success: bool
    message: str
    daily_summaries_updated: int
    weekly_summary_updated: bool


@router.post("/recalculate", response_model=RecalculateResponse)
async def recalculate_metrics(
    days: int = Query(7, ge=1, le=30, description="重新计算最近几天的数据"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    手动触发重新计算训练指标

    用于修复日总结和周汇总数据

    Args:
        days: 重新计算最近几天的数据

    Returns:
        计算结果
    """
    try:
        today = today_hk()
        metrics_service = TrainingMetricsService(db)

        # 计算每天的日总结
        daily_count = 0
        for i in range(days):
            target_date = today - timedelta(days=i)
            summary = await metrics_service.calculate_daily_summary(
                current_user.id, target_date
            )
            if summary:
                daily_count += 1
                logger.info(f"重新计算日总结: user={current_user.id}, date={target_date}")

        # 计算本周汇总
        week_start = get_week_start(today)
        weekly_summary = await metrics_service.calculate_weekly_summary(
            current_user.id, week_start
        )

        logger.info(
            f"重新计算完成: user={current_user.id}, "
            f"daily={daily_count}, weekly={weekly_summary is not None}"
        )

        return RecalculateResponse(
            success=True,
            message=f"成功重新计算{daily_count}天的数据",
            daily_summaries_updated=daily_count,
            weekly_summary_updated=weekly_summary is not None,
        )

    except Exception as e:
        logger.error(f"重新计算失败: {str(e)}")
        return RecalculateResponse(
            success=False,
            message=f"计算失败: {str(e)}",
            daily_summaries_updated=0,
            weekly_summary_updated=False,
        )
