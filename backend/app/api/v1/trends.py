"""
趋势数据 API - 支持长时间范围的数据查询
"""
import logging
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.session import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.training import DailyTrainingSummary
from app.models.oura import (
    OuraSleep, OuraDailySleep, OuraDailyReadiness,
    OuraDailyActivity, OuraDailyStress
)

router = APIRouter()
logger = logging.getLogger(__name__)


class SleepTrend(BaseModel):
    scores: List[Optional[int]]
    deep_sleep_min: List[Optional[int]]
    rem_sleep_min: List[Optional[int]]
    light_sleep_min: List[Optional[int]]
    efficiency: List[Optional[int]]
    hrv: List[Optional[int]]
    resting_hr: List[Optional[int]]  # lowest heart rate during sleep


class ReadinessTrend(BaseModel):
    scores: List[Optional[int]]


class ActivityTrend(BaseModel):
    scores: List[Optional[int]]
    steps: List[Optional[int]]
    active_calories: List[Optional[int]]
    sedentary_min: List[Optional[int]]


class TrainingDay(BaseModel):
    date: date
    zone2_min: Optional[float] = None
    hi_min: Optional[float] = None
    trimp: Optional[float] = None
    total_min: Optional[float] = None


class StressTrend(BaseModel):
    high_min: List[Optional[int]]
    recovery_min: List[Optional[int]]


class TrendsResponse(BaseModel):
    dates: List[str]
    sleep: SleepTrend
    readiness: ReadinessTrend
    activity: ActivityTrend
    training: List[TrainingDay]
    stress: StressTrend


@router.get("/overview", response_model=TrendsResponse)
async def get_trends_overview(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取趋势数据概览

    返回指定日期范围内的所有健康数据趋势
    """
    # 生成日期列表
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    date_strs = [d.isoformat() for d in dates]

    # 初始化结果数组
    sleep_scores = []
    deep_sleep_min = []
    rem_sleep_min = []
    light_sleep_min = []
    efficiency = []
    hrv = []
    resting_hr = []
    readiness_scores = []
    activity_scores = []
    steps = []
    active_calories = []
    sedentary_min = []
    stress_high = []
    stress_recovery = []
    training_data = []

    # 批量查询数据
    # 1. 睡眠数据 - 每日综合评分
    sleep_result = await db.execute(
        select(OuraDailySleep).where(
            and_(
                OuraDailySleep.user_id == current_user.id,
                OuraDailySleep.day >= start_date,
                OuraDailySleep.day <= end_date
            )
        )
    )
    daily_sleep_map = {s.day: s for s in sleep_result.scalars().all()}

    # 睡眠详情
    sleep_detail_result = await db.execute(
        select(OuraSleep).where(
            and_(
                OuraSleep.user_id == current_user.id,
                OuraSleep.day >= start_date,
                OuraSleep.day <= end_date,
                OuraSleep.sleep_type == "long_sleep"
            )
        )
    )
    sleep_detail_map = {s.day: s for s in sleep_detail_result.scalars().all()}

    # 2. 准备度数据
    readiness_result = await db.execute(
        select(OuraDailyReadiness).where(
            and_(
                OuraDailyReadiness.user_id == current_user.id,
                OuraDailyReadiness.day >= start_date,
                OuraDailyReadiness.day <= end_date
            )
        )
    )
    readiness_map = {r.day: r for r in readiness_result.scalars().all()}

    # 3. 活动数据
    activity_result = await db.execute(
        select(OuraDailyActivity).where(
            and_(
                OuraDailyActivity.user_id == current_user.id,
                OuraDailyActivity.day >= start_date,
                OuraDailyActivity.day <= end_date
            )
        )
    )
    activity_map = {a.day: a for a in activity_result.scalars().all()}

    # 4. 压力数据
    stress_result = await db.execute(
        select(OuraDailyStress).where(
            and_(
                OuraDailyStress.user_id == current_user.id,
                OuraDailyStress.day >= start_date,
                OuraDailyStress.day <= end_date
            )
        )
    )
    stress_map = {s.day: s for s in stress_result.scalars().all()}

    # 5. 训练数据
    training_result = await db.execute(
        select(DailyTrainingSummary).where(
            and_(
                DailyTrainingSummary.user_id == current_user.id,
                DailyTrainingSummary.date >= start_date,
                DailyTrainingSummary.date <= end_date
            )
        )
    )
    training_map = {t.date: t for t in training_result.scalars().all()}

    # 按日期填充数据
    for d in dates:
        # 睡眠
        daily_sleep = daily_sleep_map.get(d)
        sleep_detail = sleep_detail_map.get(d)

        sleep_scores.append(daily_sleep.score if daily_sleep else None)
        deep_sleep_min.append(
            round(sleep_detail.deep_sleep_duration / 60)
            if sleep_detail and sleep_detail.deep_sleep_duration else None
        )
        rem_sleep_min.append(
            round(sleep_detail.rem_sleep_duration / 60)
            if sleep_detail and sleep_detail.rem_sleep_duration else None
        )
        light_sleep_min.append(
            round(sleep_detail.light_sleep_duration / 60)
            if sleep_detail and sleep_detail.light_sleep_duration else None
        )
        efficiency.append(sleep_detail.efficiency if sleep_detail else None)
        hrv.append(sleep_detail.average_hrv if sleep_detail else None)
        resting_hr.append(sleep_detail.lowest_heart_rate if sleep_detail else None)

        # 准备度
        readiness = readiness_map.get(d)
        readiness_scores.append(readiness.score if readiness else None)

        # 活动
        activity = activity_map.get(d)
        activity_scores.append(activity.score if activity else None)
        steps.append(activity.steps if activity else None)
        active_calories.append(activity.active_calories if activity else None)
        sedentary_min.append(activity.sedentary_time if activity else None)

        # 压力
        stress = stress_map.get(d)
        stress_high.append(
            round(stress.stress_high / 60) if stress and stress.stress_high else None
        )
        stress_recovery.append(
            round(stress.recovery_high / 60) if stress and stress.recovery_high else None
        )

        # 训练
        training = training_map.get(d)
        if training:
            training_data.append(TrainingDay(
                date=d,
                zone2_min=training.zone2_min,
                hi_min=training.hi_min,
                trimp=float(training.trimp) if training.trimp else None,
                total_min=training.total_duration_min
            ))

    return TrendsResponse(
        dates=date_strs,
        sleep=SleepTrend(
            scores=sleep_scores,
            deep_sleep_min=deep_sleep_min,
            rem_sleep_min=rem_sleep_min,
            light_sleep_min=light_sleep_min,
            efficiency=efficiency,
            hrv=hrv,
            resting_hr=resting_hr
        ),
        readiness=ReadinessTrend(scores=readiness_scores),
        activity=ActivityTrend(
            scores=activity_scores,
            steps=steps,
            active_calories=active_calories,
            sedentary_min=sedentary_min
        ),
        training=training_data,
        stress=StressTrend(
            high_min=stress_high,
            recovery_min=stress_recovery
        )
    )
