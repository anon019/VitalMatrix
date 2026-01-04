"""
MCP (Model Context Protocol) API端点
供本地MCP服务器调用，获取健康数据
"""
import logging
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.session import get_db
from app.api.dependencies import verify_mcp_api_key
from app.models.polar import PolarExercise
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.models.oura import (
    OuraSleep, OuraDailyReadiness, OuraDailyActivity,
    OuraDailyStress, OuraDailySpo2
)
from app.models.health_report import HealthReport
from app.models.user import User
from app.utils.datetime_helper import today_hk
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ 响应模型 ============

class TrainingSession(BaseModel):
    """训练课程"""
    date: str
    sport: str
    duration_min: int
    zone2_min: float
    zone4_5_min: float
    avg_hr: Optional[int]
    max_hr: Optional[int]
    calories: Optional[int]


class TrainingSummaryResponse(BaseModel):
    """训练汇总响应"""
    period_days: int
    total_sessions: int
    total_duration_min: int
    total_zone2_min: float
    total_zone4_5_min: float
    sessions: List[TrainingSession]
    daily_summaries: List[Dict[str, Any]]


class SleepRecord(BaseModel):
    """睡眠记录"""
    date: str
    score: Optional[int]
    total_sleep_min: Optional[int]
    rem_min: Optional[int]
    deep_min: Optional[int]
    light_min: Optional[int]
    awake_min: Optional[int]
    efficiency: Optional[int]
    avg_hrv: Optional[float]


class SleepDataResponse(BaseModel):
    """睡眠数据响应"""
    period_days: int
    records: List[SleepRecord]
    avg_score: Optional[float]
    avg_duration_min: Optional[float]


class ReadinessRecord(BaseModel):
    """准备度记录"""
    date: str
    score: Optional[int]
    temperature_deviation: Optional[float]
    activity_balance: Optional[int]
    body_temperature: Optional[int]
    hrv_balance: Optional[int]
    previous_day_activity: Optional[int]
    previous_night: Optional[int]
    recovery_index: Optional[int]
    resting_heart_rate: Optional[int]
    sleep_balance: Optional[int]


class ReadinessDataResponse(BaseModel):
    """准备度数据响应"""
    period_days: int
    records: List[ReadinessRecord]
    avg_score: Optional[float]


class ActivityRecord(BaseModel):
    """活动记录"""
    date: str
    score: Optional[int]
    active_calories: Optional[int]
    steps: Optional[int]
    equivalent_walking_distance: Optional[int]
    high_activity_min: Optional[int]
    medium_activity_min: Optional[int]
    low_activity_min: Optional[int]
    sedentary_min: Optional[int]


class ActivityDataResponse(BaseModel):
    """活动数据响应"""
    period_days: int
    records: List[ActivityRecord]
    avg_steps: Optional[float]
    avg_active_calories: Optional[float]


class StressRecord(BaseModel):
    """压力记录"""
    date: str
    stress_high: Optional[int]
    recovery_high: Optional[int]
    day_summary: Optional[str]


class StressDataResponse(BaseModel):
    """压力数据响应"""
    period_days: int
    records: List[StressRecord]


class RiskFlag(BaseModel):
    """风险指标"""
    flag: str
    level: str  # low, medium, high
    message: str


class RiskFlagsResponse(BaseModel):
    """风险指标响应"""
    flags: List[RiskFlag]
    overall_status: str  # good, caution, warning


class DailyReportResponse(BaseModel):
    """预生成每日报告响应"""
    report_date: str
    report_type: str
    training_data: Optional[Dict[str, Any]]
    sleep_data: Optional[Dict[str, Any]]
    readiness_data: Optional[Dict[str, Any]]
    activity_data: Optional[Dict[str, Any]]
    stress_data: Optional[Dict[str, Any]]
    risk_flags: Optional[List[Dict[str, Any]]]
    overall_status: Optional[str]
    summary: Optional[str]
    generated_at: str


class HealthOverviewResponse(BaseModel):
    """综合健康概览响应"""
    date: str

    # 训练数据
    training: Dict[str, Any]

    # Oura数据
    sleep: Dict[str, Any]
    readiness: Dict[str, Any]
    activity: Dict[str, Any]
    stress: Dict[str, Any]

    # 风险评估
    risk_flags: List[RiskFlag]

    # 建议摘要
    summary: str


class WeeklyTrendsResponse(BaseModel):
    """周趋势响应"""
    week_start: str
    week_end: str

    # 训练趋势
    training_trend: Dict[str, Any]

    # 睡眠趋势
    sleep_trend: Dict[str, Any]

    # 准备度趋势
    readiness_trend: Dict[str, Any]

    # 活动趋势
    activity_trend: Dict[str, Any]


# ============ 辅助函数 ============

async def get_default_user(db: AsyncSession) -> User:
    """获取默认用户（单用户模式）"""
    result = await db.execute(select(User).limit(1))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到用户"
        )
    return user


# ============ API端点 ============

@router.get("/health-overview", response_model=HealthOverviewResponse)
async def get_health_overview(
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取综合健康概览

    包含训练、睡眠、准备度、活动、压力等所有数据的综合视图
    """
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

        # 获取昨日Oura数据
        sleep_result = await db.execute(
            select(OuraSleep)
            .where(OuraSleep.user_id == user.id)
            .where(OuraSleep.day == yesterday)
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

        # 构建训练数据
        training_data = {
            "yesterday": {
                "has_data": daily_training is not None,
                "duration_min": daily_training.total_duration_min if daily_training else 0,
                "zone2_min": daily_training.zone2_min if daily_training else 0,
                "zone4_5_min": daily_training.hi_min if daily_training else 0,
                "sessions": daily_training.sessions_count if daily_training else 0,
                "trimp": daily_training.trimp if daily_training else 0,
            },
            "weekly": {
                "has_data": weekly_training is not None,
                "total_min": weekly_training.total_duration_min if weekly_training else 0,
                "zone2_min": weekly_training.zone2_min if weekly_training else 0,
                "zone4_5_min": weekly_training.hi_min if weekly_training else 0,
                "trimp": weekly_training.weekly_trimp if weekly_training else 0,
            }
        }

        # 构建睡眠数据
        sleep_data = {
            "has_data": sleep is not None,
            "score": sleep.score if sleep else None,
            "total_min": sleep.total_sleep_duration if sleep else None,
            "efficiency": sleep.efficiency if sleep else None,
        }

        # 构建准备度数据
        readiness_data = {
            "has_data": readiness is not None,
            "score": readiness.score if readiness else None,
            "hrv_balance": readiness.contributors_hrv_balance if readiness else None,
            "recovery_index": readiness.contributors_recovery_index if readiness else None,
        }

        # 构建活动数据
        activity_data = {
            "has_data": activity is not None,
            "score": activity.score if activity else None,
            "steps": activity.steps if activity else None,
            "active_calories": activity.active_calories if activity else None,
        }

        # 构建压力数据
        stress_data = {
            "has_data": stress is not None,
            "stress_high": stress.stress_high if stress else None,
            "recovery_high": stress.recovery_high if stress else None,
            "day_summary": stress.day_summary if stress else None,
        }

        # 计算风险指标
        risk_flags = []

        # Zone2不足
        if daily_training and daily_training.zone2_min < settings.TARGET_ZONE2_MIN_RANGE:
            risk_flags.append(RiskFlag(
                flag="zone2_low",
                level="medium",
                message=f"昨日Zone2时长{daily_training.zone2_min:.0f}分钟，低于目标{settings.TARGET_ZONE2_MIN_RANGE}分钟"
            ))

        # 高强度过多
        if daily_training and daily_training.hi_min > settings.TARGET_HI_MAX_RANGE:
            risk_flags.append(RiskFlag(
                flag="hi_excessive",
                level="high",
                message=f"昨日高强度{daily_training.hi_min:.0f}分钟，超过上限{settings.TARGET_HI_MAX_RANGE}分钟"
            ))

        # 周训练量不足
        if weekly_training and weekly_training.zone2_min < settings.TARGET_WEEKLY_ZONE2_MIN:
            risk_flags.append(RiskFlag(
                flag="weekly_low",
                level="medium",
                message=f"本周Zone2累计{weekly_training.zone2_min:.0f}分钟，低于目标{settings.TARGET_WEEKLY_ZONE2_MIN}分钟"
            ))

        # 周高强度过多
        if weekly_training and weekly_training.hi_min > settings.TARGET_WEEKLY_HI_MAX:
            risk_flags.append(RiskFlag(
                flag="weekly_hi_overload",
                level="high",
                message=f"本周高强度累计{weekly_training.hi_min:.0f}分钟，超过上限{settings.TARGET_WEEKLY_HI_MAX}分钟"
            ))

        # 准备度低
        if readiness and readiness.score and readiness.score < 70:
            risk_flags.append(RiskFlag(
                flag="low_readiness",
                level="high" if readiness.score < 60 else "medium",
                message=f"准备度评分{readiness.score}，身体恢复不足"
            ))

        # 睡眠质量差
        if sleep and sleep.score and sleep.score < 70:
            risk_flags.append(RiskFlag(
                flag="poor_sleep",
                level="medium",
                message=f"睡眠评分{sleep.score}，睡眠质量欠佳"
            ))

        # 判断整体状态
        high_risks = [f for f in risk_flags if f.level == "high"]
        medium_risks = [f for f in risk_flags if f.level == "medium"]

        if high_risks:
            overall_status = "warning"
        elif medium_risks:
            overall_status = "caution"
        else:
            overall_status = "good"

        # 生成摘要
        if overall_status == "good":
            summary = "身体状态良好，可以进行正常训练"
        elif overall_status == "caution":
            summary = "有轻微风险指标，建议适当调整训练强度"
        else:
            summary = "存在较高风险，建议休息或进行轻度恢复性训练"

        return HealthOverviewResponse(
            date=today.isoformat(),
            training=training_data,
            sleep=sleep_data,
            readiness=readiness_data,
            activity=activity_data,
            stress=stress_data,
            risk_flags=risk_flags,
            summary=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取健康概览失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/training-summary", response_model=TrainingSummaryResponse)
async def get_training_summary(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取训练数据汇总

    包含指定天数内的所有训练课程和每日汇总
    """
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
            sessions.append(TrainingSession(
                date=ex.start_time.date().isoformat(),
                sport=ex.sport_type or "unknown",
                duration_min=ex.duration_sec // 60 if ex.duration_sec else 0,
                zone2_min=(ex.zone2_sec or 0) / 60,
                zone4_5_min=zone4_5_min,
                avg_hr=ex.avg_hr,
                max_hr=ex.max_hr,
                calories=ex.calories
            ))

        # 构建每日汇总列表
        daily_list = []
        for ds in daily_summaries:
            daily_list.append({
                "date": ds.date.isoformat(),
                "total_min": ds.total_duration_min,
                "zone2_min": ds.zone2_min,
                "hi_min": ds.hi_min,
                "trimp": ds.trimp,
                "sessions_count": ds.sessions_count
            })

        # 计算汇总统计
        total_sessions = len(sessions)
        total_duration = sum(s.duration_min for s in sessions)
        total_zone2 = sum(s.zone2_min for s in sessions)
        total_zone4_5 = sum(s.zone4_5_min for s in sessions)

        return TrainingSummaryResponse(
            period_days=days,
            total_sessions=total_sessions,
            total_duration_min=total_duration,
            total_zone2_min=total_zone2,
            total_zone4_5_min=total_zone4_5,
            sessions=sessions,
            daily_summaries=daily_list
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取训练汇总失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/sleep-data", response_model=SleepDataResponse)
async def get_sleep_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取睡眠数据

    包含指定天数内的睡眠记录
    """
    try:
        user = await get_default_user(db)
        today = today_hk()
        start_date = today - timedelta(days=days)

        # 获取睡眠记录
        result = await db.execute(
            select(OuraSleep)
            .where(OuraSleep.user_id == user.id)
            .where(OuraSleep.day >= start_date)
            .order_by(desc(OuraSleep.day))
        )
        sleep_records = result.scalars().all()

        # 构建记录列表
        records = []
        scores = []
        durations = []

        for sr in sleep_records:
            records.append(SleepRecord(
                date=sr.day.isoformat(),
                score=sr.score,
                total_sleep_min=sr.total_sleep_duration,
                rem_min=sr.rem_sleep_duration,
                deep_min=sr.deep_sleep_duration,
                light_min=sr.light_sleep_duration,
                awake_min=sr.awake_time,
                efficiency=sr.efficiency,
                avg_hrv=sr.average_hrv
            ))

            if sr.score:
                scores.append(sr.score)
            if sr.total_sleep_duration:
                durations.append(sr.total_sleep_duration)

        # 计算平均值
        avg_score = sum(scores) / len(scores) if scores else None
        avg_duration = sum(durations) / len(durations) if durations else None

        return SleepDataResponse(
            period_days=days,
            records=records,
            avg_score=avg_score,
            avg_duration_min=avg_duration
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取睡眠数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/readiness-data", response_model=ReadinessDataResponse)
async def get_readiness_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取准备度数据

    包含指定天数内的准备度记录
    """
    try:
        user = await get_default_user(db)
        today = today_hk()
        start_date = today - timedelta(days=days)

        # 获取准备度记录
        result = await db.execute(
            select(OuraDailyReadiness)
            .where(OuraDailyReadiness.user_id == user.id)
            .where(OuraDailyReadiness.day >= start_date)
            .order_by(desc(OuraDailyReadiness.day))
        )
        readiness_records = result.scalars().all()

        # 构建记录列表
        records = []
        scores = []

        for rr in readiness_records:
            records.append(ReadinessRecord(
                date=rr.day.isoformat(),
                score=rr.score,
                temperature_deviation=rr.temperature_deviation,
                activity_balance=rr.contributors_activity_balance,
                body_temperature=rr.contributors_body_temperature,
                hrv_balance=rr.contributors_hrv_balance,
                previous_day_activity=rr.contributors_previous_day_activity,
                previous_night=rr.contributors_previous_night,
                recovery_index=rr.contributors_recovery_index,
                resting_heart_rate=rr.contributors_resting_heart_rate,
                sleep_balance=rr.contributors_sleep_balance
            ))

            if rr.score:
                scores.append(rr.score)

        # 计算平均值
        avg_score = sum(scores) / len(scores) if scores else None

        return ReadinessDataResponse(
            period_days=days,
            records=records,
            avg_score=avg_score
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取准备度数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/activity-data", response_model=ActivityDataResponse)
async def get_activity_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取活动数据

    包含指定天数内的活动记录
    """
    try:
        user = await get_default_user(db)
        today = today_hk()
        start_date = today - timedelta(days=days)

        # 获取活动记录
        result = await db.execute(
            select(OuraDailyActivity)
            .where(OuraDailyActivity.user_id == user.id)
            .where(OuraDailyActivity.day >= start_date)
            .order_by(desc(OuraDailyActivity.day))
        )
        activity_records = result.scalars().all()

        # 构建记录列表
        records = []
        steps_list = []
        calories_list = []

        for ar in activity_records:
            records.append(ActivityRecord(
                date=ar.day.isoformat(),
                score=ar.score,
                active_calories=ar.active_calories,
                steps=ar.steps,
                equivalent_walking_distance=ar.equivalent_walking_distance,
                high_activity_min=ar.high_activity_time,
                medium_activity_min=ar.medium_activity_time,
                low_activity_min=ar.low_activity_time,
                sedentary_min=ar.sedentary_time
            ))

            if ar.steps:
                steps_list.append(ar.steps)
            if ar.active_calories:
                calories_list.append(ar.active_calories)

        # 计算平均值
        avg_steps = sum(steps_list) / len(steps_list) if steps_list else None
        avg_calories = sum(calories_list) / len(calories_list) if calories_list else None

        return ActivityDataResponse(
            period_days=days,
            records=records,
            avg_steps=avg_steps,
            avg_active_calories=avg_calories
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取活动数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/stress-data", response_model=StressDataResponse)
async def get_stress_data(
    days: int = Query(7, ge=1, le=30, description="查询天数"),
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取压力数据

    包含指定天数内的压力记录
    """
    try:
        user = await get_default_user(db)
        today = today_hk()
        start_date = today - timedelta(days=days)

        # 获取压力记录
        result = await db.execute(
            select(OuraDailyStress)
            .where(OuraDailyStress.user_id == user.id)
            .where(OuraDailyStress.day >= start_date)
            .order_by(desc(OuraDailyStress.day))
        )
        stress_records = result.scalars().all()

        # 构建记录列表
        records = []
        for sr in stress_records:
            records.append(StressRecord(
                date=sr.day.isoformat(),
                stress_high=sr.stress_high,
                recovery_high=sr.recovery_high,
                day_summary=sr.day_summary
            ))

        return StressDataResponse(
            period_days=days,
            records=records
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取压力数据失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/weekly-trends", response_model=WeeklyTrendsResponse)
async def get_weekly_trends(
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取周趋势数据

    包含本周训练、睡眠、准备度、活动的趋势分析
    """
    try:
        user = await get_default_user(db)
        today = today_hk()

        # 计算本周起止日期（周一开始）
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        # 获取本周每日数据
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

            # 睡眠
            sleep_result = await db.execute(
                select(OuraSleep)
                .where(OuraSleep.user_id == user.id)
                .where(OuraSleep.day == day)
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
                "training": {
                    "total_min": training.total_duration_min if training else 0,
                    "zone2_min": training.zone2_min if training else 0,
                    "hi_min": training.hi_min if training else 0,
                },
                "sleep_score": sleep.score if sleep else None,
                "readiness_score": readiness.score if readiness else None,
                "steps": activity.steps if activity else None,
            })

        # 计算训练趋势
        training_mins = [d["training"]["total_min"] for d in days_data]
        zone2_mins = [d["training"]["zone2_min"] for d in days_data]
        training_trend = {
            "daily_minutes": training_mins,
            "total_minutes": sum(training_mins),
            "total_zone2": sum(zone2_mins),
            "training_days": sum(1 for m in training_mins if m > 0),
        }

        # 计算睡眠趋势
        sleep_scores = [d["sleep_score"] for d in days_data if d["sleep_score"]]
        sleep_trend = {
            "daily_scores": [d["sleep_score"] for d in days_data],
            "avg_score": sum(sleep_scores) / len(sleep_scores) if sleep_scores else None,
        }

        # 计算准备度趋势
        readiness_scores = [d["readiness_score"] for d in days_data if d["readiness_score"]]
        readiness_trend = {
            "daily_scores": [d["readiness_score"] for d in days_data],
            "avg_score": sum(readiness_scores) / len(readiness_scores) if readiness_scores else None,
        }

        # 计算活动趋势
        steps = [d["steps"] for d in days_data if d["steps"]]
        activity_trend = {
            "daily_steps": [d["steps"] for d in days_data],
            "avg_steps": sum(steps) / len(steps) if steps else None,
            "total_steps": sum(steps) if steps else 0,
        }

        return WeeklyTrendsResponse(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            training_trend=training_trend,
            sleep_trend=sleep_trend,
            readiness_trend=readiness_trend,
            activity_trend=activity_trend
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取周趋势失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/risk-flags", response_model=RiskFlagsResponse)
async def get_risk_flags(
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取当前风险指标

    实时计算并返回所有风险警告
    """
    try:
        # 调用health-overview并提取风险指标
        overview = await get_health_overview(_, db)

        # 判断整体状态
        high_risks = [f for f in overview.risk_flags if f.level == "high"]
        medium_risks = [f for f in overview.risk_flags if f.level == "medium"]

        if high_risks:
            overall_status = "warning"
        elif medium_risks:
            overall_status = "caution"
        else:
            overall_status = "good"

        return RiskFlagsResponse(
            flags=overview.risk_flags,
            overall_status=overall_status
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取风险指标失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )


@router.get("/daily-report", response_model=DailyReportResponse)
async def get_daily_report(
    _: bool = Depends(verify_mcp_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    获取预生成的每日健康报告

    快速返回预生成的报告，无需实时计算
    """
    try:
        user = await get_default_user(db)
        today = today_hk()

        # 获取今日报告
        result = await db.execute(
            select(HealthReport)
            .where(HealthReport.user_id == user.id)
            .where(HealthReport.report_date == today)
            .where(HealthReport.report_type == "daily")
        )
        report = result.scalar_one_or_none()

        if not report:
            # 如果没有预生成报告，返回空报告
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="今日报告尚未生成，请稍后再试或使用 /health-overview 获取实时数据"
            )

        return DailyReportResponse(
            report_date=report.report_date.isoformat(),
            report_type=report.report_type,
            training_data=report.training_data,
            sleep_data=report.sleep_data,
            readiness_data=report.readiness_data,
            activity_data=report.activity_data,
            stress_data=report.stress_data,
            risk_flags=report.risk_flags,
            overall_status=report.overall_status,
            summary=report.summary,
            generated_at=report.updated_at.isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取每日报告失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据失败: {str(e)}"
        )
