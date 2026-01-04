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
from app.utils.datetime_helper import get_week_start
from app.config import settings

logger = logging.getLogger(__name__)


class TrainingMetricsService:
    """训练指标计算服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_trimp(self, exercise: PolarExercise) -> float:
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
            exercise.zone1_sec,
            exercise.zone2_sec,
            exercise.zone3_sec,
            exercise.zone4_sec,
            exercise.zone5_sec,
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
        # 查询当日所有训练
        result = await self.db.execute(
            select(PolarExercise)
            .where(
                and_(
                    PolarExercise.user_id == user_id,
                    func.date(PolarExercise.start_time) == target_date,
                )
            )
            .order_by(PolarExercise.start_time)
        )
        exercises = result.scalars().all()

        if not exercises:
            logger.info(f"用户{user_id}在{target_date}无训练记录")
            return None

        # 聚合计算
        total_duration_sec = sum(e.duration_sec for e in exercises)
        total_zone2_sec = sum(e.zone2_sec for e in exercises)
        total_hi_sec = sum(e.zone4_sec + e.zone5_sec for e in exercises)
        total_calories = sum(e.calories or 0 for e in exercises)
        
        # 计算平均心率
        avg_hrs = [e.avg_hr for e in exercises if e.avg_hr]
        avg_hr = int(sum(avg_hrs) / len(avg_hrs)) if avg_hrs else None

        # 计算总TRIMP
        trimp = sum([await self.calculate_trimp(e) for e in exercises])

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
            summary.sessions_count = len(exercises)
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
                sessions_count=len(exercises),
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
            week_start_date = get_week_start(date.today())

        week_end_date = week_start_date + timedelta(days=6)

        # 查询该周的日总结
        result = await self.db.execute(
            select(DailyTrainingSummary)
            .where(
                and_(
                    DailyTrainingSummary.user_id == user_id,
                    DailyTrainingSummary.date >= week_start_date,
                    DailyTrainingSummary.date <= week_end_date,
                )
            )
            .order_by(DailyTrainingSummary.date)
        )
        daily_summaries = result.scalars().all()

        if not daily_summaries:
            logger.info(f"用户{user_id}在周{week_start_date}无训练记录")
            return None

        # 聚合计算
        total_duration_min = sum(d.total_duration_min for d in daily_summaries)
        zone2_min = sum(d.zone2_min for d in daily_summaries)
        hi_min = sum(d.hi_min for d in daily_summaries)
        weekly_trimp = sum(d.trimp for d in daily_summaries)

        training_days = len(daily_summaries)
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
            select(DailyTrainingSummary)
            .where(
                and_(
                    DailyTrainingSummary.user_id == user_id,
                    DailyTrainingSummary.date >= start_date,
                    DailyTrainingSummary.date <= end_date,
                    DailyTrainingSummary.hi_min > 5,  # 高强度超过5分钟
                )
            )
            .order_by(DailyTrainingSummary.date)
        )
        summaries = result.scalars().all()

        # 检查是否连续
        if len(summaries) < days:
            return len(summaries)

        # 简单检查：如果数量等于天数，认为是连续的
        return len(summaries)

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
