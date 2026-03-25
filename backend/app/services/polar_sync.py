"""
Polar数据同步服务
"""
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio

from app.integrations.polar.provider import PolarProvider
from app.integrations.polar.client import PolarClient
from app.models.polar import PolarExercise, PolarSleep, PolarNightlyRecharge, PolarAuth
from app.models.user import User
from app.utils.datetime_helper import today_hk, get_week_start, now_hk
from app.services.training_metrics import TrainingMetricsService
from datetime import datetime

logger = logging.getLogger(__name__)
MAX_CONCURRENT_USER_TASKS = 8


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

            # 一次性查询已存在的训练记录
            session_ids = [session.external_id for session in training_sessions if session.external_id]
            if not session_ids:
                return (0, 0)

            existing_result = await self.db.execute(
                select(PolarExercise).where(PolarExercise.exercise_id.in_(session_ids))
            )
            existing_map = {row.exercise_id: row for row in existing_result.scalars().all()}

            new_count = 0
            total_new_duration_min = 0.0
            dates_to_update = set()
            changed = False
            exercises_to_add = []

            for session in training_sessions:
                if not session.external_id:
                    logger.warning("训练记录缺少external_id，跳过")
                    continue

                existing = existing_map.get(session.external_id)

                if existing and not force:
                    logger.debug(f"训练记录已存在，跳过: {session.external_id}")
                    continue

                dates_to_update.add(session.start_time.date())
                changed = True

                if existing:
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
                    logger.debug(f"更新训练记录: {session.external_id}")
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
                    exercises_to_add.append(exercise)
                    new_count += 1
                    total_new_duration_min += session.duration_sec / 60
                    logger.info(
                        f"新增训练记录: {session.external_id}, 时长: {session.duration_sec/60:.1f}分钟"
                    )

            if not changed:
                logger.info(f"Polar数据无需更新: user_id={user_id}, range={start_date} to {end_date}")
                return (0, 0)

            if exercises_to_add:
                self.db.add_all(exercises_to_add)

            await self.db.commit()

            logger.info(
                f"Polar数据同步完成: user_id={user_id}, "
                f"total={len(training_sessions)}, new={new_count}, new_duration={total_new_duration_min:.1f}分钟"
            )

            # 同步后自动计算受影响日期和周汇总
            await self._update_summaries(user_id, dates_to_update)

            return (new_count, int(total_new_duration_min))

        except Exception as e:
            logger.error(f"Polar数据同步失败: user_id={user_id} - {str(e)}")
            await self.db.rollback()
            raise

    async def _update_summaries(self, user_id: uuid.UUID, affected_dates: set[date]):
        """同步后更新受影响的日总结和周汇总"""
        try:
            metrics_service = TrainingMetricsService(self.db)

            if not affected_dates:
                return

            # 计算每个涉及日期的日总结
            for target_date in sorted(affected_dates):
                await metrics_service.calculate_daily_summary(user_id, target_date)
                logger.info(f"自动计算日总结: user={user_id}, date={target_date}")

            # 计算受影响周的周汇总（兼容跨周同步）
            week_starts = {get_week_start(target_date) for target_date in affected_dates}
            for week_start in sorted(week_starts):
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

            sync_stats: Dict[str, int] = {}

            async def _sync_user(user):
                try:
                    new_count, _ = await self.sync_user_exercises(user.id, days=days)
                    return new_count
                except Exception:
                    logger.error(f"用户数据同步失败: user_id={user.id}", exc_info=True)
                    return -1

            semaphore = asyncio.Semaphore(MAX_CONCURRENT_USER_TASKS)

            async def _runner(user):
                async with semaphore:
                    return await _sync_user(user)

            results = await asyncio.gather(
                *[_runner(user) for user in users],
                return_exceptions=True,
            )

            for user, result in zip(users, results):
                if isinstance(result, Exception):
                    logger.error(f"用户数据同步失败: user_id={user.id} - {str(result)}")
                    sync_stats[str(user.id)] = -1
                else:
                    sync_stats[str(user.id)] = result

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
            if not sleep_records:
                return 0

            polar_id_map = {}
            for sleep_data in sleep_records:
                polar_user = sleep_data.get("polar-user")
                sleep_date_str = sleep_data.get("date")
                if not polar_user or not sleep_date_str:
                    continue

                polar_id = f"{polar_user}/{sleep_date_str}"
                if polar_id in polar_id_map:
                    continue

                try:
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

                    polar_id_map[polar_id] = {
                        "sleep_date": sleep_date,
                        "sleep_start_time": sleep_start_time,
                        "sleep_end_time": sleep_end_time,
                        "deep_sleep_duration": sleep_data.get("deep_sleep"),
                        "light_sleep_duration": sleep_data.get("light_sleep"),
                        "rem_sleep_duration": sleep_data.get("rem_sleep"),
                        "total_interruption_duration": sleep_data.get("total_interruption_duration"),
                        "sleep_score": sleep_data.get("sleep_score"),
                        "continuity": sleep_data.get("continuity"),
                        "continuity_class": sleep_data.get("continuity_class"),
                        "raw_json": sleep_data,
                    }
                except Exception as e:
                    logger.error(f"处理Polar睡眠记录失败: {str(e)}")
                    continue

            if not polar_id_map:
                return 0

            result = await self.db.execute(
                select(PolarSleep).where(PolarSleep.polar_id.in_(polar_id_map.keys()))
            )
            existing_map = {row.polar_id: row for row in result.scalars().all()}

            new_count = 0
            items_to_add = []

            for polar_id, payload in polar_id_map.items():
                existing = existing_map.get(polar_id)
                if existing and not force:
                    continue

                if existing:
                    # 强制更新
                    existing.sleep_date = payload["sleep_date"]
                    existing.sleep_start_time = payload["sleep_start_time"]
                    existing.sleep_end_time = payload["sleep_end_time"]
                    existing.deep_sleep_duration = payload["deep_sleep_duration"]
                    existing.light_sleep_duration = payload["light_sleep_duration"]
                    existing.rem_sleep_duration = payload["rem_sleep_duration"]
                    existing.total_interruption_duration = payload["total_interruption_duration"]
                    existing.sleep_score = payload["sleep_score"]
                    existing.continuity = payload["continuity"]
                    existing.continuity_class = payload["continuity_class"]
                    existing.raw_json = payload["raw_json"]
                else:
                    items_to_add.append(
                        PolarSleep(
                            user_id=user_id,
                            polar_id=polar_id,
                            sleep_date=payload["sleep_date"],
                            sleep_start_time=payload["sleep_start_time"],
                            sleep_end_time=payload["sleep_end_time"],
                            deep_sleep_duration=payload["deep_sleep_duration"],
                            light_sleep_duration=payload["light_sleep_duration"],
                            rem_sleep_duration=payload["rem_sleep_duration"],
                            total_interruption_duration=payload["total_interruption_duration"],
                            sleep_score=payload["sleep_score"],
                            continuity=payload["continuity"],
                            continuity_class=payload["continuity_class"],
                            raw_json=payload["raw_json"],
                            created_at=now_hk(),
                        )
                    )
                    new_count += 1

            if items_to_add:
                self.db.add_all(items_to_add)

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
            if not recharge_records:
                return 0

            polar_id_map = {}
            for recharge_data in recharge_records:
                polar_user = recharge_data.get("polar-user")
                recharge_date_str = recharge_data.get("date")
                if not polar_user or not recharge_date_str:
                    continue

                polar_id = f"{polar_user}/{recharge_date_str}"
                if polar_id in polar_id_map:
                    continue

                try:
                    recharge_date = date.fromisoformat(recharge_date_str)
                    polar_id_map[polar_id] = {
                        "date": recharge_date,
                        "ans_charge": recharge_data.get("ans_charge"),
                        "ans_charge_status": recharge_data.get("ans_charge_status"),
                        "hrv_avg": recharge_data.get("hrv_avg"),
                        "breathing_rate_avg": recharge_data.get("breathing_rate_avg"),
                        "heart_rate_avg": recharge_data.get("heart_rate_avg"),
                        "rmssd": recharge_data.get("rmssd"),
                        "sleep_charge": recharge_data.get("sleep_charge"),
                        "sleep_charge_status": recharge_data.get("sleep_charge_status"),
                        "sleep_score": recharge_data.get("sleep_score"),
                        "nightly_recharge_status": recharge_data.get("nightly_recharge_status"),
                        "raw_json": recharge_data,
                    }
                except Exception as e:
                    logger.error(f"处理Polar夜间恢复记录失败: {str(e)}")
                    continue

            if not polar_id_map:
                return 0

            result = await self.db.execute(
                select(PolarNightlyRecharge).where(
                    PolarNightlyRecharge.polar_id.in_(polar_id_map.keys())
                )
            )
            existing_map = {row.polar_id: row for row in result.scalars().all()}

            new_count = 0
            items_to_add = []

            for polar_id, payload in polar_id_map.items():
                existing = existing_map.get(polar_id)
                if existing and not force:
                    continue

                if existing:
                    # 强制更新
                    existing.date = payload["date"]
                    existing.ans_charge = payload["ans_charge"]
                    existing.ans_charge_status = payload["ans_charge_status"]
                    existing.hrv_avg = payload["hrv_avg"]
                    existing.breathing_rate_avg = payload["breathing_rate_avg"]
                    existing.heart_rate_avg = payload["heart_rate_avg"]
                    existing.rmssd = payload["rmssd"]
                    existing.sleep_charge = payload["sleep_charge"]
                    existing.sleep_charge_status = payload["sleep_charge_status"]
                    existing.sleep_score = payload["sleep_score"]
                    existing.nightly_recharge_status = payload["nightly_recharge_status"]
                    existing.raw_json = payload["raw_json"]
                else:
                    items_to_add.append(
                        PolarNightlyRecharge(
                            user_id=user_id,
                            polar_id=polar_id,
                            date=payload["date"],
                            ans_charge=payload["ans_charge"],
                            ans_charge_status=payload["ans_charge_status"],
                            hrv_avg=payload["hrv_avg"],
                            breathing_rate_avg=payload["breathing_rate_avg"],
                            heart_rate_avg=payload["heart_rate_avg"],
                            rmssd=payload["rmssd"],
                            sleep_charge=payload["sleep_charge"],
                            sleep_charge_status=payload["sleep_charge_status"],
                            sleep_score=payload["sleep_score"],
                            nightly_recharge_status=payload["nightly_recharge_status"],
                            raw_json=payload["raw_json"],
                            created_at=now_hk(),
                        )
                    )
                    new_count += 1

            if items_to_add:
                self.db.add_all(items_to_add)

            await self.db.commit()
            logger.info(f"同步Polar夜间恢复数据完成: user_id={user_id}, new={new_count}")
            return new_count

        except Exception as e:
            logger.error(f"同步Polar夜间恢复数据失败: user_id={user_id} - {str(e)}")
            await self.db.rollback()
            return 0

