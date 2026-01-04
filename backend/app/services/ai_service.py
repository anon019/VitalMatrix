"""
AI服务 - AI建议生成与管理
"""
import logging
from datetime import date, timedelta
from typing import Optional, List
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.ai.factory import AIProviderFactory
from app.ai.base import UserContext, TrainingData, OuraData
from app.models.user import User
from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
from app.models.ai import AIRecommendation
from app.models.oura import OuraSleep, OuraDailyReadiness, OuraDailyActivity, OuraDailyStress
from app.utils.datetime_helper import today_hk, get_week_start
from app.config import settings

logger = logging.getLogger(__name__)


class AIService:
    """AI服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_daily_recommendation(
        self,
        user_id: uuid.UUID,
        target_date: date = None,
        provider_name: str = None,
        force_update: bool = False
    ) -> AIRecommendation:
        """
        生成每日AI建议（每次生成新记录，保留历史）

        Args:
            user_id: 用户ID
            target_date: 目标日期（默认今天）
            provider_name: AI Provider名称（默认使用配置）
            force_update: 是否强制生成（True=总是生成新记录，False=如已存在则跳过）

        Returns:
            AI建议记录
        """
        if target_date is None:
            target_date = today_hk()

        try:
            # 去重逻辑：检查今天是否已有建议（用于兜底任务避免重复）
            if not force_update:
                existing = await self.get_recommendation(user_id, target_date)
                if existing:
                    logger.info(f"今日AI建议已存在，跳过生成: user_id={user_id}, date={target_date}")
                    return existing

            logger.info(f"开始生成AI建议（新记录）: user_id={user_id}, date={target_date}, force={force_update}")

            # 1. 获取用户上下文
            user_context = await self._get_user_context(user_id)

            # 2. 获取训练数据
            training_data = await self._get_training_data(user_id, target_date)

            # 3. 调用AI生成建议
            ai_provider = AIProviderFactory.create(provider_name)
            recommendation = await ai_provider.generate_recommendation(
                user_context=user_context,
                training_data=training_data,
                date=target_date.isoformat(),
            )

            # 4. 保存到数据库（每次生成新记录）
            ai_record = await self._create_recommendation(
                user_id=user_id,
                date=target_date,
                provider=ai_provider.name,
                model=ai_provider.model,
                recommendation=recommendation,
            )

            logger.info(
                f"AI建议生成成功: user_id={user_id}, date={target_date}, "
                f"provider={ai_provider.name}, tokens={recommendation.total_tokens}"
            )

            return ai_record

        except Exception as e:
            logger.error(f"AI建议生成失败: user_id={user_id}, date={target_date} - {str(e)}")
            raise

    async def get_recommendation(
        self,
        user_id: uuid.UUID,
        target_date: date = None
    ) -> Optional[AIRecommendation]:
        """
        获取AI建议

        优先返回目标日期的建议，如不存在则返回最新一条有效建议。
        这样在凌晨还没有当天睡眠数据时，仍然能展示最近有数据的建议。

        Args:
            user_id: 用户ID
            target_date: 目标日期（默认今天）

        Returns:
            AI建议记录（如不存在返回None）
        """
        if target_date is None:
            target_date = today_hk()

        from sqlalchemy import desc

        # 先尝试获取目标日期的建议
        result = await self.db.execute(
            select(AIRecommendation)
            .where(
                and_(
                    AIRecommendation.user_id == user_id,
                    AIRecommendation.date == target_date,
                )
            )
            .order_by(desc(AIRecommendation.created_at))
            .limit(1)
        )
        recommendation = result.scalar_one_or_none()

        # 如果目标日期没有，返回最新一条（不限日期）
        if recommendation is None:
            result = await self.db.execute(
                select(AIRecommendation)
                .where(AIRecommendation.user_id == user_id)
                .order_by(desc(AIRecommendation.created_at))
                .limit(1)
            )
            recommendation = result.scalar_one_or_none()

        return recommendation

    async def regenerate_recommendation(
        self,
        user_id: uuid.UUID,
        target_date: date,
        provider_name: str = None
    ) -> AIRecommendation:
        """
        重新生成AI建议（删除旧记录）

        Args:
            user_id: 用户ID
            target_date: 目标日期
            provider_name: AI Provider名称（可切换模型）

        Returns:
            新的AI建议记录
        """
        # 删除旧记录
        result = await self.db.execute(
            select(AIRecommendation).where(
                and_(
                    AIRecommendation.user_id == user_id,
                    AIRecommendation.date == target_date,
                )
            )
        )
        old_record = result.scalar_one_or_none()
        if old_record:
            await self.db.delete(old_record)
            await self.db.commit()
            logger.info(f"删除旧AI建议: user_id={user_id}, date={target_date}")

        # 生成新建议
        return await self.generate_daily_recommendation(user_id, target_date, provider_name)

    async def chat(
        self,
        user_id: uuid.UUID,
        messages: List[dict],
        provider_name: str = None
    ):
        """
        AI对话

        Args:
            user_id: 用户ID
            messages: 消息历史 [{role, content}]
            provider_name: AI Provider名称

        Returns:
            AI回复
        """
        try:
            # 获取用户上下文作为对话背景
            user_context = await self._get_user_context(user_id)
            context_dict = user_context.dict()

            # 调用AI Provider
            ai_provider = AIProviderFactory.create(provider_name)

            from app.ai.base import Message
            message_objects = [Message(**msg) for msg in messages]

            response = await ai_provider.chat(message_objects, context=context_dict)

            logger.info(f"AI对话成功: user_id={user_id}, tokens={response.usage}")

            return response

        except Exception as e:
            logger.error(f"AI对话失败: user_id={user_id} - {str(e)}")
            raise

    async def _get_user_context(self, user_id: uuid.UUID) -> UserContext:
        """获取用户上下文"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"用户不存在: {user_id}")

        # 计算年龄
        age = None
        if user.birth_year:
            current_year = today_hk().year
            age = current_year - user.birth_year

        return UserContext(
            user_id=str(user.id),
            nickname=user.nickname,
            health_goal=user.health_goal or "降脂心血管健康优化",
            training_plan=user.training_plan or "Zone2 55分钟 + Zone4-5 2分钟",
            hr_max=user.hr_max,
            resting_hr=user.resting_hr,
            weight=float(user.weight) if user.weight else None,
            height=user.height,
            age=age,
        )

    async def _get_training_data(self, user_id: uuid.UUID, target_date: date) -> TrainingData:
        """获取训练数据"""
        # 获取昨日训练总结
        yesterday = target_date - timedelta(days=1)
        result = await self.db.execute(
            select(DailyTrainingSummary).where(
                and_(
                    DailyTrainingSummary.user_id == user_id,
                    DailyTrainingSummary.date == yesterday,
                )
            )
        )
        daily_summary = result.scalar_one_or_none()

        # 获取本周训练总结
        week_start = get_week_start(target_date)
        result = await self.db.execute(
            select(WeeklyTrainingSummary).where(
                and_(
                    WeeklyTrainingSummary.user_id == user_id,
                    WeeklyTrainingSummary.week_start_date == week_start,
                )
            )
        )
        weekly_summary = result.scalar_one_or_none()

        # 构建训练数据
        if daily_summary:
            zone2_min = daily_summary.zone2_min
            hi_min = daily_summary.hi_min
            total_duration_min = daily_summary.total_duration_min
            trimp = float(daily_summary.trimp)
            avg_hr = daily_summary.avg_hr
            flags = daily_summary.flags or {}
        else:
            # 昨天没有训练
            zone2_min = 0
            hi_min = 0
            total_duration_min = 0
            trimp = 0.0
            avg_hr = None
            flags = {"no_training_yesterday": True}

        if weekly_summary:
            weekly_zone2 = weekly_summary.zone2_min
            weekly_hi = weekly_summary.hi_min
            weekly_total = weekly_summary.total_duration_min
            weekly_trimp = float(weekly_summary.weekly_trimp)
            training_days = weekly_summary.training_days
            rest_days = weekly_summary.rest_days
        else:
            weekly_zone2 = 0
            weekly_hi = 0
            weekly_total = 0
            weekly_trimp = 0.0
            training_days = 0
            rest_days = 7

        # 获取 Oura 数据
        oura_data = await self._get_oura_data(user_id, target_date)

        return TrainingData(
            zone2_min=zone2_min,
            hi_min=hi_min,
            total_duration_min=total_duration_min,
            trimp=trimp,
            avg_hr=avg_hr,
            sport_type=None,  # 可以从最近一次训练中获取
            weekly_zone2=weekly_zone2,
            weekly_hi=weekly_hi,
            weekly_total=weekly_total,
            weekly_trimp=weekly_trimp,
            training_days=training_days,
            rest_days=rest_days,
            flags=flags,
            oura_data=oura_data,
        )

    async def _get_oura_data(self, user_id: uuid.UUID, target_date: date) -> Optional[OuraData]:
        """获取 Oura 数据（睡眠、准备度、压力、活动）

        注意：
        - 睡眠/准备度：使用target_date（今天），因为昨晚睡到今早的数据归属到今天
        - 活动/压力：使用昨天的数据，因为需要评估昨天一整天的活动和压力状态
        """
        yesterday = target_date - timedelta(days=1)

        # 睡眠数据（今天的数据 = 昨晚睡到今早醒来的睡眠 + 午睡）
        # 策略：获取所有睡眠记录，累加时长，使用long_sleep的日汇总评分
        sleep_result = await self.db.execute(
            select(OuraSleep)
            .where(and_(
                OuraSleep.user_id == user_id,
                OuraSleep.day == target_date
            ))
            .order_by(
                # long_sleep优先（它包含日汇总评分）
                (OuraSleep.sleep_type == 'long_sleep').desc()
            )
        )
        all_sleeps = sleep_result.scalars().all()

        # 初始化睡眠汇总数据
        sleep = None
        total_sleep_duration = 0
        total_deep_sleep = 0
        total_rem_sleep = 0
        total_light_sleep = 0
        sleep_score = None
        sleep_efficiency = None
        average_hrv = None
        lowest_heart_rate = None

        for s in all_sleeps:
            # 累加时长
            if s.total_sleep_duration:
                total_sleep_duration += s.total_sleep_duration
            if s.deep_sleep_duration:
                total_deep_sleep += s.deep_sleep_duration
            if s.rem_sleep_duration:
                total_rem_sleep += s.rem_sleep_duration
            if s.light_sleep_duration:
                total_light_sleep += s.light_sleep_duration

            # 使用long_sleep的评分和其他指标（它包含日汇总评分）
            if s.sleep_type == 'long_sleep':
                sleep = s
                sleep_score = s.sleep_score
                sleep_efficiency = s.efficiency
                average_hrv = s.average_hrv
                lowest_heart_rate = s.lowest_heart_rate

        # 如果没有long_sleep但有其他睡眠记录，使用第一条
        if not sleep and all_sleeps:
            sleep = all_sleeps[0]
            sleep_score = sleep.sleep_score
            sleep_efficiency = sleep.efficiency
            average_hrv = sleep.average_hrv
            lowest_heart_rate = sleep.lowest_heart_rate

        # 记录累加后的睡眠数据（调试用）
        logger.info(
            f"睡眠数据累加结果: 记录数={len(all_sleeps)}, "
            f"总时长={round(total_sleep_duration/3600, 1)}h, "
            f"深睡={round(total_deep_sleep/60)}min, "
            f"REM={round(total_rem_sleep/60)}min, "
            f"浅睡={round(total_light_sleep/60)}min, "
            f"评分={sleep_score}"
        )

        # 准备度数据（今天的数据 = 基于今早醒来状态的准备度评分）
        readiness_result = await self.db.execute(
            select(OuraDailyReadiness)
            .where(and_(
                OuraDailyReadiness.user_id == user_id,
                OuraDailyReadiness.day == target_date  # 使用今天的数据
            ))
        )
        readiness = readiness_result.scalar_one_or_none()

        # 活动数据（昨天的完整数据 = 昨天一整天的活动统计）
        activity_result = await self.db.execute(
            select(OuraDailyActivity)
            .where(and_(
                OuraDailyActivity.user_id == user_id,
                OuraDailyActivity.day == yesterday  # 使用昨天的数据
            ))
        )
        activity = activity_result.scalar_one_or_none()

        # 压力数据（昨天的完整数据 = 昨天一整天的压力统计）
        stress_result = await self.db.execute(
            select(OuraDailyStress)
            .where(and_(
                OuraDailyStress.user_id == user_id,
                OuraDailyStress.day == yesterday  # 使用昨天的数据
            ))
        )
        stress = stress_result.scalar_one_or_none()

        # 如果所有数据都没有，返回 None
        if not any([sleep, readiness, activity, stress]):
            return None

        return OuraData(
            # 睡眠（使用累加后的时长数据）
            sleep_score=sleep_score,
            total_sleep_hours=round(total_sleep_duration / 3600, 1) if total_sleep_duration else None,
            deep_sleep_min=round(total_deep_sleep / 60) if total_deep_sleep else None,
            rem_sleep_min=round(total_rem_sleep / 60) if total_rem_sleep else None,
            sleep_efficiency=sleep_efficiency,
            average_hrv=average_hrv,
            # 准备度
            readiness_score=readiness.score if readiness else None,
            recovery_index=readiness.recovery_index if readiness else None,
            resting_heart_rate=lowest_heart_rate,  # 从睡眠数据获取实际BPM
            hrv_balance=readiness.hrv_balance if readiness else None,
            # 压力
            stress_high_min=round(stress.stress_high / 60) if stress and stress.stress_high else None,
            recovery_high_min=round(stress.recovery_high / 60) if stress and stress.recovery_high else None,
            day_summary=stress.day_summary if stress else None,
            # 活动
            activity_score=activity.score if activity else None,
            steps=activity.steps if activity else None,
            active_calories=activity.active_calories if activity else None,
        )

    async def _create_recommendation(
        self,
        user_id: uuid.UUID,
        date: date,
        provider: str,
        model: str,
        recommendation,
    ) -> AIRecommendation:
        """创建新的AI建议记录（每次都创建新记录，保留历史）"""
        from app.utils.datetime_helper import now_hk

        ai_record = AIRecommendation(
            user_id=user_id,
            date=date,
            provider=provider,
            model=model,
            summary=recommendation.summary,
            yesterday_review=recommendation.yesterday_review,
            today_recommendation=recommendation.today_recommendation,
            health_education=recommendation.health_education,
            prompt_tokens=recommendation.prompt_tokens,
            completion_tokens=recommendation.completion_tokens,
            created_at=now_hk(),
        )
        self.db.add(ai_record)

        await self.db.commit()
        await self.db.refresh(ai_record)

        return ai_record
