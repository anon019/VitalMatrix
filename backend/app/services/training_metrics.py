"""
训练指标计算引擎
"""
import logging
from datetime import date, timedelta
from typing import Optional, Dict
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.polar import PolarExercise
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.utils.datetime_helper import get_week_start, today_hk
from app.config import settings

logger = logging.getLogger(__name__)


class TrainingMetricsService:
    """训练指标计算服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def calculate_trimp(self, exercise: PolarExercise) -> float:
        """
        计算TRIMP训练负荷

        Args:
            exercise: 训练记录

        Returns:
            TRIMP值
        """
        # 如果Polar提供了cardio_load，优先使用
        if exercise.cardio_load:
            return float(exercise.cardio_load)

        # 否则自己计算TRIMP
        zone_weights = [1.0, 1.25, 1.5, 1.75, 2.0]
        zones = [
            int(exercise.zone1_sec),
            int(exercise.zone2_sec),
            int(exercise.zone3_sec),
            int(exercise.zone4_sec),
            int(exercise.zone5_sec),
        ]

        trimp = sum(z * w for z, w in zip(zones, zone_weights)) / 60
        return round(trimp, 2)

    async def calculate_daily_summary(
        self, user_id: uuid.UUID, target_date: date
    ) -> Optional[DailyTrainingSummary]:
        """
        计算日训练总结

        Args:
            user_id: 用户ID
            target_date: 目标日期

        Returns:
            日总结对象
        """
        # 查询目标日期汇总数据（数据库端聚合）
        from app.utils.datetime_helper import start_of_day_hk

        start_time = start_of_day_hk(target_date)
        end_time = start_of_day_hk(target_date + timedelta(days=1))

        result = await self.db.execute(
            select(
                func.count(PolarExercise.id).label("sessions_count"),
                func.coalesce(func.sum(PolarExercise.duration_sec), 0).label("total_duration_sec"),
                func.coalesce(func.sum(PolarExercise.zone2_sec), 0).label("total_zone2_sec"),
                func.coalesce(
                    func.sum(PolarExercise.zone4_sec + PolarExercise.zone5_sec), 0
                ).label("total_hi_sec"),
                func.coalesce(func.sum(PolarExercise.calories), 0).label("total_calories"),
                func.avg(PolarExercise.avg_hr).label("avg_hr"),
                func.coalesce(func.sum(PolarExercise.zone1_sec), 0).label("zone1_sec"),
                func.coalesce(func.sum(PolarExercise.zone2_sec), 0).label("zone2_agg_sec"),
                func.coalesce(func.sum(PolarExercise.zone3_sec), 0).label("zone3_sec"),
                func.coalesce(func.sum(PolarExercise.zone4_sec), 0).label("zone4_sec"),
                func.coalesce(func.sum(PolarExercise.zone5_sec), 0).label("zone5_sec"),
            )
            .where(
                and_(
                    PolarExercise.user_id == user_id,
                    PolarExercise.start_time >= start_time,
                    PolarExercise.start_time < end_time,
                )
            )
        )
        row = result.one()

        sessions_count = int(row.sessions_count or 0)
        if sessions_count == 0:
            logger.info(f"用户{user_id}在{target_date}无训练记录")
            return None

        total_duration_sec = int(row.total_duration_sec)
        total_zone2_sec = int(row.total_zone2_sec)
        total_hi_sec = int(row.total_hi_sec)
        total_calories = int(row.total_calories)
        avg_hr = int(row.avg_hr) if row.avg_hr is not None else None

        trimp = (
            float(row.zone1_sec) * 1.0
            + float(row.zone2_agg_sec) * 1.25
            + float(row.zone3_sec) * 1.5
            + float(row.zone4_sec) * 1.75
            + float(row.zone5_sec) * 2.0
        ) / 60
        trimp = round(trimp, 2)

        # 评估风险标记
        flags = await self._assess_daily_flags(
            zone2_min=total_zone2_sec // 60,
            hi_min=total_hi_sec // 60,
            user_id=user_id,
            target_date=target_date,
        )

        # 查询是否已存在
        result = await self.db.execute(
            select(DailyTrainingSummary).where(
                and_(
                    DailyTrainingSummary.user_id == user_id,
                    DailyTrainingSummary.date == target_date,
                )
            )
        )
        summary = result.scalar_one_or_none()

        if summary:
            # 更新
            summary.total_duration_min = total_duration_sec // 60
            summary.zone2_min = total_zone2_sec // 60
            summary.hi_min = total_hi_sec // 60
            summary.trimp = trimp
            summary.sessions_count = sessions_count
            summary.total_calories = total_calories if total_calories > 0 else None
            summary.avg_hr = avg_hr
            summary.flags = flags
        else:
            # 新建
            summary = DailyTrainingSummary(
                user_id=user_id,
                date=target_date,
                total_duration_min=total_duration_sec // 60,
                zone2_min=total_zone2_sec // 60,
                hi_min=total_hi_sec // 60,
                trimp=trimp,
                sessions_count=sessions_count,
                total_calories=total_calories if total_calories > 0 else None,
                avg_hr=avg_hr,
                flags=flags,
                created_at=func.now(),
            )
            self.db.add(summary)

        await self.db.commit()
        await self.db.refresh(summary)

        logger.info(
            f"日总结计算完成: user={user_id}, date={target_date}, "
            f"zone2={summary.zone2_min}min, hi={summary.hi_min}min"
        )

        # 训练数据更新后，触发AI重新生成今天的建议
        await self._trigger_ai_update(user_id, target_date)

        return summary

    async def calculate_weekly_summary(
        self, user_id: uuid.UUID, week_start_date: Optional[date] = None
    ) -> Optional[WeeklyTrainingSummary]:
        """
        计算周训练总结

        Args:
            user_id: 用户ID
            week_start_date: 周起始日期（默认为本周一）

        Returns:
            周总结对象
        """
        if week_start_date is None:
            week_start_date = get_week_start(today_hk())

        week_end_date = week_start_date + timedelta(days=6)

        result = await self.db.execute(
            select(
                func.coalesce(func.sum(DailyTrainingSummary.total_duration_min), 0).label("total_duration_min"),
                func.coalesce(func.sum(DailyTrainingSummary.zone2_min), 0).label("zone2_min"),
                func.coalesce(func.sum(DailyTrainingSummary.hi_min), 0).label("hi_min"),
                func.coalesce(func.sum(DailyTrainingSummary.trimp), 0).label("weekly_trimp"),
                func.count(DailyTrainingSummary.id).label("training_days"),
            )
            .where(
                and_(
                    DailyTrainingSummary.user_id == user_id,
                    DailyTrainingSummary.date >= week_start_date,
                    DailyTrainingSummary.date <= week_end_date,
                )
            )
            .order_by(DailyTrainingSummary.date)
        )
        row = result.one()

        training_days = int(row.training_days or 0)
        if training_days == 0:
            logger.info(f"用户{user_id}在周{week_start_date}无训练记录")
            return None

        total_duration_min = int(row.total_duration_min)
        zone2_min = int(row.zone2_min)
        hi_min = int(row.hi_min)
        weekly_trimp = float(row.weekly_trimp)
        rest_days = 7 - training_days

        # 查询是否已存在
        result = await self.db.execute(
            select(WeeklyTrainingSummary).where(
                and_(
                    WeeklyTrainingSummary.user_id == user_id,
                    WeeklyTrainingSummary.week_start_date == week_start_date,
                )
            )
        )
        summary = result.scalar_one_or_none()

        if summary:
            # 更新
            summary.total_duration_min = total_duration_min
            summary.zone2_min = zone2_min
            summary.hi_min = hi_min
            summary.weekly_trimp = weekly_trimp
            summary.training_days = training_days
            summary.rest_days = rest_days
        else:
            # 新建
            summary = WeeklyTrainingSummary(
                user_id=user_id,
                week_start_date=week_start_date,
                total_duration_min=total_duration_min,
                zone2_min=zone2_min,
                hi_min=hi_min,
                weekly_trimp=weekly_trimp,
                training_days=training_days,
                rest_days=rest_days,
                created_at=func.now(),
            )
            self.db.add(summary)

        await self.db.commit()
        await self.db.refresh(summary)

        logger.info(
            f"周总结计算完成: user={user_id}, week={week_start_date}, "
            f"days={training_days}, zone2={zone2_min}min"
        )

        return summary

    async def _assess_daily_flags(
        self, zone2_min: int, hi_min: int, user_id: uuid.UUID, target_date: date
    ) -> Dict[str, bool]:
        """评估日训练风险标记"""
        flags = {}

        # 规则1: Zone2不足
        if zone2_min < settings.TARGET_ZONE2_MIN_RANGE:
            flags["zone2_low"] = True

        # 规则2: 高强度过量
        if hi_min > settings.TARGET_HI_MAX_RANGE:
            flags["hi_excessive"] = True

        # 规则3: 检查连续高强度（最近3天）
        consecutive_days = await self._check_consecutive_high_intensity(
            user_id, target_date, days=3
        )
        if consecutive_days >= 3:
            flags["consecutive_high"] = True

        return flags

    async def _check_consecutive_high_intensity(
        self, user_id: uuid.UUID, end_date: date, days: int
    ) -> int:
        """检查连续高强度训练天数"""
        start_date = end_date - timedelta(days=days - 1)

        result = await self.db.execute(
            select(DailyTrainingSummary.date)
            .where(
                and_(
                    DailyTrainingSummary.user_id == user_id,
                    DailyTrainingSummary.date >= start_date,
                    DailyTrainingSummary.date <= end_date,
                    DailyTrainingSummary.hi_min > 5,  # 高强度超过5分钟
                )
            )
        )
        active_dates = {row[0] for row in result.all()}

        consecutive = 0
        current_date = end_date
        while current_date >= start_date:
            if current_date not in active_dates:
                break
            consecutive += 1
            current_date -= timedelta(days=1)

        return consecutive

    async def _trigger_ai_update(self, user_id: uuid.UUID, target_date: date):
        """
        触发AI重新生成建议（当训练数据更新时）

        Args:
            user_id: 用户ID
            target_date: 数据日期
        """
        try:
            from app.services.ai_service import AIService
            from app.utils.datetime_helper import today_hk

            # 只有更新的是昨天的训练数据时才触发（因为AI基于昨天的数据生成今天的建议）
            yesterday = today_hk() - timedelta(days=1)
            if target_date != yesterday:
                logger.debug(f"训练数据日期{target_date}不是昨天，跳过AI触发")
                return

            ai_service = AIService(self.db)
            today = today_hk()

            # 使用force_update=True强制重新生成今天的建议
            await ai_service.generate_daily_recommendation(
                user_id=user_id,
                target_date=today,
                force_update=True
            )

            logger.info(f"训练数据更新后触发AI重新生成成功: user_id={user_id}, training_date={target_date}")

        except Exception as e:
            # AI生成失败不应影响训练数据计算，只记录错误
            logger.error(f"训练数据更新后触发AI重新生成失败: user_id={user_id} - {str(e)}")
