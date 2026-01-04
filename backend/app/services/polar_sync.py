"""
Polar数据同步服务
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.polar.provider import PolarProvider
from app.integrations.polar.client import PolarClient
from app.models.polar import PolarExercise, PolarSleep, PolarNightlyRecharge, PolarAuth
from app.models.user import User
from app.utils.datetime_helper import today_hk, get_week_start, now_hk
from app.services.training_metrics import TrainingMetricsService
from datetime import datetime

logger = logging.getLogger(__name__)


class PolarSyncService:
    """Polar数据同步服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.polar_provider = PolarProvider()
        self.polar_client = PolarClient()

    async def sync_user_exercises(
        self,
        user_id: uuid.UUID,
        days: int = 7,
        force: bool = False
    ) -> Tuple[int, int]:
        """
        同步用户训练数据

        Args:
            user_id: 用户ID
            days: 同步最近几天的数据
            force: 是否强制重新同步

        Returns:
            (新增的训练记录数量, 新增的总训练时长分钟数)
        """
        try:
            # 计算日期范围
            end_date = today_hk()
            start_date = end_date - timedelta(days=days - 1)

            logger.info(
                f"开始同步Polar数据: user_id={user_id}, "
                f"range={start_date} to {end_date}"
            )

            # 拉取训练数据
            training_sessions = await self.polar_provider.fetch_training_data(
                user_id, start_date, end_date
            )

            if not training_sessions:
                logger.info(f"未获取到新的训练数据: user_id={user_id}")
                return (0, 0)

            # 保存到数据库（幂等性处理）
            new_count = 0
            total_new_duration_min = 0  # 新增训练总时长（分钟）
            for session in training_sessions:
                # 检查是否已存在
                result = await self.db.execute(
                    select(PolarExercise).where(
                        PolarExercise.exercise_id == session.external_id
                    )
                )
                existing = result.scalar_one_or_none()

                if existing and not force:
                    logger.debug(f"训练记录已存在，跳过: {session.external_id}")
                    continue

                if existing and force:
                    # 强制更新
                    existing.start_time = session.start_time
                    existing.end_time = session.end_time
                    existing.sport_type = session.sport_type
                    existing.duration_sec = session.duration_sec
                    existing.avg_hr = session.avg_hr
                    existing.max_hr = session.max_hr
                    existing.zone1_sec = session.zone1_sec
                    existing.zone2_sec = session.zone2_sec
                    existing.zone3_sec = session.zone3_sec
                    existing.zone4_sec = session.zone4_sec
                    existing.zone5_sec = session.zone5_sec
                    # Zone boundaries
                    existing.zone1_lower = session.zone1_lower
                    existing.zone1_upper = session.zone1_upper
                    existing.zone2_lower = session.zone2_lower
                    existing.zone2_upper = session.zone2_upper
                    existing.zone3_lower = session.zone3_lower
                    existing.zone3_upper = session.zone3_upper
                    existing.zone4_lower = session.zone4_lower
                    existing.zone4_upper = session.zone4_upper
                    existing.zone5_lower = session.zone5_lower
                    existing.zone5_upper = session.zone5_upper
                    existing.calories = session.calories
                    existing.distance_meters = session.distance_meters
                    existing.raw_json = session.raw_data
                    logger.info(f"更新训练记录: {session.external_id}")
                else:
                    # 新建记录
                    exercise = PolarExercise(
                        user_id=user_id,
                        exercise_id=session.external_id,
                        start_time=session.start_time,
                        end_time=session.end_time,
                        sport_type=session.sport_type,
                        duration_sec=session.duration_sec,
                        avg_hr=session.avg_hr,
                        max_hr=session.max_hr,
                        zone1_sec=session.zone1_sec,
                        zone2_sec=session.zone2_sec,
                        zone3_sec=session.zone3_sec,
                        zone4_sec=session.zone4_sec,
                        zone5_sec=session.zone5_sec,
                        # Zone boundaries
                        zone1_lower=session.zone1_lower,
                        zone1_upper=session.zone1_upper,
                        zone2_lower=session.zone2_lower,
                        zone2_upper=session.zone2_upper,
                        zone3_lower=session.zone3_lower,
                        zone3_upper=session.zone3_upper,
                        zone4_lower=session.zone4_lower,
                        zone4_upper=session.zone4_upper,
                        zone5_lower=session.zone5_lower,
                        zone5_upper=session.zone5_upper,
                        calories=session.calories,
                        distance_meters=session.distance_meters,
                        raw_json=session.raw_data,
                        created_at=today_hk(),
                    )
                    self.db.add(exercise)
                    new_count += 1
                    total_new_duration_min += session.duration_sec / 60  # 累加新增时长（转为分钟）
                    logger.info(f"新增训练记录: {session.external_id}, 时长: {session.duration_sec/60:.1f}分钟")

            await self.db.commit()

            logger.info(
                f"Polar数据同步完成: user_id={user_id}, "
                f"total={len(training_sessions)}, new={new_count}, new_duration={total_new_duration_min:.1f}分钟"
            )

            # 同步后自动计算日总结和周汇总
            if new_count > 0:
                await self._update_summaries(user_id, training_sessions)

            return (new_count, int(total_new_duration_min))

        except Exception as e:
            logger.error(f"Polar数据同步失败: user_id={user_id} - {str(e)}")
            await self.db.rollback()
            raise

    async def _update_summaries(self, user_id: uuid.UUID, training_sessions):
        """同步后更新日总结和周汇总"""
        try:
            metrics_service = TrainingMetricsService(self.db)

            # 获取所有涉及的日期
            dates_to_update = set()
            for session in training_sessions:
                session_date = session.start_time.date()
                dates_to_update.add(session_date)

            # 计算每个日期的日总结
            for target_date in dates_to_update:
                await metrics_service.calculate_daily_summary(user_id, target_date)
                logger.info(f"自动计算日总结: user={user_id}, date={target_date}")

            # 计算本周汇总
            week_start = get_week_start(today_hk())
            await metrics_service.calculate_weekly_summary(user_id, week_start)
            logger.info(f"自动计算周汇总: user={user_id}, week={week_start}")

        except Exception as e:
            logger.error(f"自动计算汇总失败: user_id={user_id} - {str(e)}")
            # 不抛出异常，避免影响同步流程

    async def sync_all_active_users(self, days: int = 2) -> Dict[str, int]:
        """
        同步所有活跃用户的数据

        Args:
            days: 同步最近几天的数据

        Returns:
            同步统计 {user_id: new_count}
        """
        try:
            # 获取所有有Polar授权的用户
            result = await self.db.execute(
                select(User)
                .join(User.polar_auth)
                .where(User.polar_auth.has(is_active=True))
            )
            users = result.scalars().all()

            logger.info(f"开始批量同步Polar数据: users={len(users)}, days={days}")

            sync_stats = {}
            for user in users:
                try:
                    new_count = await self.sync_user_exercises(user.id, days=days)
                    sync_stats[str(user.id)] = new_count
                except Exception as e:
                    logger.error(f"用户数据同步失败: user_id={user.id} - {str(e)}")
                    sync_stats[str(user.id)] = -1  # 标记为失败

            logger.info(f"批量同步完成: stats={sync_stats}")
            return sync_stats

        except Exception as e:
            logger.error(f"批量同步失败: {str(e)}")
            raise

    async def check_connection(self, user_id: uuid.UUID) -> bool:
        """
        检查Polar连接状态

        Args:
            user_id: 用户ID

        Returns:
            是否连接正常
        """
        try:
            return await self.polar_provider.check_connection(user_id)
        except Exception as e:
            logger.error(f"Polar连接检查失败: user_id={user_id} - {str(e)}")
            return False

    async def get_access_token(self, user_id: uuid.UUID) -> Optional[str]:
        """
        获取用户的Polar访问令牌

        Args:
            user_id: 用户ID

        Returns:
            访问令牌
        """
        result = await self.db.execute(
            select(PolarAuth).where(
                PolarAuth.user_id == user_id,
                PolarAuth.is_active == True
            )
        )
        auth = result.scalar_one_or_none()

        if not auth or not auth.access_token:
            return None

        # 检查是否需要刷新令牌
        if auth.token_expires_at and auth.token_expires_at < now_hk():
            if auth.refresh_token:
                try:
                    token_data = await self.polar_client.refresh_access_token(auth.refresh_token)
                    auth.access_token = token_data["access_token"]
                    auth.refresh_token = token_data.get("refresh_token", auth.refresh_token)
                    expires_in = token_data.get("expires_in", 86400)
                    auth.token_expires_at = now_hk() + timedelta(seconds=expires_in)
                    auth.updated_at = now_hk()
                    await self.db.commit()
                    logger.info(f"已刷新Polar令牌: user_id={user_id}")
                except Exception as e:
                    logger.error(f"刷新Polar令牌失败: user_id={user_id} - {str(e)}")
                    return None
            else:
                logger.warning(f"Polar令牌已过期且无法刷新: user_id={user_id}")
                return None

        return auth.access_token

    async def sync_sleep_data(
        self,
        user_id: uuid.UUID,
        days: int = 7,
        force: bool = False
    ) -> int:
        """
        同步Polar睡眠数据

        Args:
            user_id: 用户ID
            days: 同步最近几天的数据
            force: 是否强制重新同步

        Returns:
            新增记录数
        """
        try:
            access_token = await self.get_access_token(user_id)
            if not access_token:
                logger.error(f"无法获取Polar访问令牌: user_id={user_id}")
                return 0

            # 计算日期范围
            end_date = today_hk()
            start_date = end_date - timedelta(days=days - 1)

            # 获取睡眠数据
            sleep_records = await self.polar_client.get_sleep_data(
                access_token, start_date, end_date
            )

            new_count = 0

            for sleep_data in sleep_records:
                try:
                    # 使用polar-user和date组合作为唯一ID
                    polar_user = sleep_data.get("polar-user")
                    sleep_date_str = sleep_data.get("date")

                    if not polar_user or not sleep_date_str:
                        continue

                    polar_id = f"{polar_user}/{sleep_date_str}"

                    # 检查是否已存在
                    result = await self.db.execute(
                        select(PolarSleep).where(PolarSleep.polar_id == polar_id)
                    )
                    existing = result.scalar_one_or_none()

                    if existing and not force:
                        continue

                    # 解析日期时间
                    sleep_date = date.fromisoformat(sleep_date_str)
                    sleep_start_time_str = sleep_data.get("sleep_start_time")
                    sleep_end_time_str = sleep_data.get("sleep_end_time")

                    if sleep_start_time_str:
                        sleep_start_time = datetime.fromisoformat(
                            sleep_start_time_str.replace("Z", "+00:00")
                        )
                    else:
                        continue

                    if sleep_end_time_str:
                        sleep_end_time = datetime.fromisoformat(
                            sleep_end_time_str.replace("Z", "+00:00")
                        )
                    else:
                        continue

                    # 提取睡眠阶段时长(秒)
                    deep_sleep = sleep_data.get("deep_sleep")
                    light_sleep = sleep_data.get("light_sleep")
                    rem_sleep = sleep_data.get("rem_sleep")
                    interruption = sleep_data.get("total_interruption_duration")

                    # 提取睡眠质量指标
                    sleep_score = sleep_data.get("sleep_score")
                    continuity = sleep_data.get("continuity")
                    continuity_class = sleep_data.get("continuity_class")

                    if existing and force:
                        # 更新现有记录
                        existing.sleep_date = sleep_date
                        existing.sleep_start_time = sleep_start_time
                        existing.sleep_end_time = sleep_end_time
                        existing.deep_sleep_duration = deep_sleep
                        existing.light_sleep_duration = light_sleep
                        existing.rem_sleep_duration = rem_sleep
                        existing.total_interruption_duration = interruption
                        existing.sleep_score = sleep_score
                        existing.continuity = continuity
                        existing.continuity_class = continuity_class
                        existing.raw_json = sleep_data
                    else:
                        # 创建新记录
                        polar_sleep = PolarSleep(
                            user_id=user_id,
                            polar_id=polar_id,
                            sleep_date=sleep_date,
                            sleep_start_time=sleep_start_time,
                            sleep_end_time=sleep_end_time,
                            deep_sleep_duration=deep_sleep,
                            light_sleep_duration=light_sleep,
                            rem_sleep_duration=rem_sleep,
                            total_interruption_duration=interruption,
                            sleep_score=sleep_score,
                            continuity=continuity,
                            continuity_class=continuity_class,
                            raw_json=sleep_data,
                            created_at=now_hk(),
                        )
                        self.db.add(polar_sleep)
                        new_count += 1

                except Exception as e:
                    logger.error(f"处理Polar睡眠记录失败: {str(e)}")
                    continue

            await self.db.commit()
            logger.info(f"同步Polar睡眠数据完成: user_id={user_id}, new={new_count}")
            return new_count

        except Exception as e:
            logger.error(f"同步Polar睡眠数据失败: user_id={user_id} - {str(e)}")
            await self.db.rollback()
            return 0

    async def sync_nightly_recharge_data(
        self,
        user_id: uuid.UUID,
        days: int = 7,
        force: bool = False
    ) -> int:
        """
        同步Polar夜间恢复数据

        Args:
            user_id: 用户ID
            days: 同步最近几天的数据
            force: 是否强制重新同步

        Returns:
            新增记录数
        """
        try:
            access_token = await self.get_access_token(user_id)
            if not access_token:
                logger.error(f"无法获取Polar访问令牌: user_id={user_id}")
                return 0

            # 计算日期范围
            end_date = today_hk()
            start_date = end_date - timedelta(days=days - 1)

            # 获取夜间恢复数据
            recharge_records = await self.polar_client.get_nightly_recharge_data(
                access_token, start_date, end_date
            )

            new_count = 0

            for recharge_data in recharge_records:
                try:
                    # 使用polar-user和date组合作为唯一ID
                    polar_user = recharge_data.get("polar-user")
                    recharge_date_str = recharge_data.get("date")

                    if not polar_user or not recharge_date_str:
                        continue

                    polar_id = f"{polar_user}/{recharge_date_str}"

                    # 检查是否已存在
                    result = await self.db.execute(
                        select(PolarNightlyRecharge).where(
                            PolarNightlyRecharge.polar_id == polar_id
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing and not force:
                        continue

                    # 解析日期
                    recharge_date = date.fromisoformat(recharge_date_str)

                    # 提取ANS恢复指标
                    ans_charge = recharge_data.get("ans_charge")
                    ans_charge_status = recharge_data.get("ans_charge_status")
                    hrv_avg = recharge_data.get("hrv_avg")
                    breathing_rate_avg = recharge_data.get("breathing_rate_avg")
                    heart_rate_avg = recharge_data.get("heart_rate_avg")
                    rmssd = recharge_data.get("rmssd")

                    # 提取睡眠恢复指标
                    sleep_charge = recharge_data.get("sleep_charge")
                    sleep_charge_status = recharge_data.get("sleep_charge_status")
                    sleep_score = recharge_data.get("sleep_score")

                    # Nightly Recharge总分
                    nightly_recharge_status = recharge_data.get("nightly_recharge_status")

                    if existing and force:
                        # 更新现有记录
                        existing.date = recharge_date
                        existing.ans_charge = ans_charge
                        existing.ans_charge_status = ans_charge_status
                        existing.hrv_avg = hrv_avg
                        existing.breathing_rate_avg = breathing_rate_avg
                        existing.heart_rate_avg = heart_rate_avg
                        existing.rmssd = rmssd
                        existing.sleep_charge = sleep_charge
                        existing.sleep_charge_status = sleep_charge_status
                        existing.sleep_score = sleep_score
                        existing.nightly_recharge_status = nightly_recharge_status
                        existing.raw_json = recharge_data
                    else:
                        # 创建新记录
                        polar_recharge = PolarNightlyRecharge(
                            user_id=user_id,
                            polar_id=polar_id,
                            date=recharge_date,
                            ans_charge=ans_charge,
                            ans_charge_status=ans_charge_status,
                            hrv_avg=hrv_avg,
                            breathing_rate_avg=breathing_rate_avg,
                            heart_rate_avg=heart_rate_avg,
                            rmssd=rmssd,
                            sleep_charge=sleep_charge,
                            sleep_charge_status=sleep_charge_status,
                            sleep_score=sleep_score,
                            nightly_recharge_status=nightly_recharge_status,
                            raw_json=recharge_data,
                            created_at=now_hk(),
                        )
                        self.db.add(polar_recharge)
                        new_count += 1

                except Exception as e:
                    logger.error(f"处理Polar夜间恢复记录失败: {str(e)}")
                    continue

            await self.db.commit()
            logger.info(f"同步Polar夜间恢复数据完成: user_id={user_id}, new={new_count}")
            return new_count

        except Exception as e:
            logger.error(f"同步Polar夜间恢复数据失败: user_id={user_id} - {str(e)}")
            await self.db.rollback()
            return 0
