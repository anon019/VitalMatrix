"""
Oura数据同步服务
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.oura.client import OuraClient
from app.models.oura import (
    OuraAuth, OuraSleep, OuraDailySleep, OuraDailyReadiness,
    OuraDailyActivity, OuraDailyStress, OuraDailySpo2,
    OuraCardiovascularAge, OuraResilience, OuraVO2Max
)
from app.models.user import User
from app.utils.datetime_helper import today_hk, now_hk

logger = logging.getLogger(__name__)


class OuraSyncService:
    """Oura数据同步服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.oura_client = OuraClient()

    async def get_access_token(self, user_id: uuid.UUID) -> Optional[str]:
        """
        获取用户的Oura访问令牌

        Args:
            user_id: 用户ID

        Returns:
            访问令牌
        """
        result = await self.db.execute(
            select(OuraAuth).where(
                OuraAuth.user_id == user_id,
                OuraAuth.is_active == True
            )
        )
        auth = result.scalar_one_or_none()

        if not auth or not auth.access_token:
            return None

        # 检查是否需要刷新令牌
        if auth.token_expires_at and auth.token_expires_at < now_hk():
            if auth.refresh_token:
                try:
                    token_data = await self.oura_client.refresh_access_token(auth.refresh_token)
                    auth.access_token = token_data["access_token"]
                    auth.refresh_token = token_data.get("refresh_token", auth.refresh_token)
                    expires_in = token_data.get("expires_in", 86400)
                    auth.token_expires_at = now_hk() + timedelta(seconds=expires_in)
                    auth.updated_at = now_hk()
                    await self.db.commit()
                    logger.info(f"已刷新Oura令牌: user_id={user_id}")
                except Exception as e:
                    logger.error(f"刷新Oura令牌失败: user_id={user_id} - {str(e)}")
                    return None
            else:
                logger.warning(f"Oura令牌已过期且无法刷新: user_id={user_id}")
                return None

        return auth.access_token

    async def sync_user_data(
        self,
        user_id: uuid.UUID,
        days: int = 7,
        force: bool = False,
        force_today: bool = False,
        force_recent_days: int = 0
    ) -> Dict[str, int]:
        """
        同步用户所有Oura数据

        Args:
            user_id: 用户ID
            days: 同步最近几天的数据
            force: 是否强制重新同步所有数据
            force_today: 是否仅强制更新今天的数据（用于轮询，确保当天数据实时更新）
            force_recent_days: 强制更新最近N天的数据（0=不启用，2=更新今天和昨天）

        Returns:
            同步统计 {数据类型: 新增数量}
        """
        try:
            access_token = await self.get_access_token(user_id)
            if not access_token:
                logger.error(f"无法获取Oura访问令牌: user_id={user_id}")
                return {}

            # 计算日期范围
            # 重要：Oura API 的日期范围是左闭右开 [start_date, end_date)
            # 即 end_date 当天的数据不会返回，需要 +1 天才能包含今天的午睡等数据
            end_date = today_hk() + timedelta(days=1)  # 明天，确保包含今天的所有数据
            start_date = today_hk() - timedelta(days=days - 1)

            logger.info(
                f"开始同步Oura数据: user_id={user_id}, "
                f"range={start_date} to {end_date}"
            )

            # 获取所有数据
            all_data = await self.oura_client.get_all_daily_data(
                access_token, start_date, end_date
            )

            stats = {
                "sleep": 0,
                "daily_sleep": 0,
                "readiness": 0,
                "activity": 0,
                "stress": 0,
                "spo2": 0,
                "cardiovascular_age": 0,
                "resilience": 0,
                "vo2_max": 0,
            }

            # 同步各类数据
            # force_today: 仅更新今天的数据
            # force_recent_days: 更新最近N天的数据（用于处理API延迟更新的情况）
            today = today_hk()
            force_recent_date = today - timedelta(days=force_recent_days - 1) if force_recent_days > 0 else None

            stats["sleep"], has_significant_sleep_change = await self._sync_sleep_data(
                user_id, all_data.get("sleep", []), all_data.get("sleep_details", []), force, force_today, today, force_recent_date
            )
            stats["daily_sleep"], has_daily_sleep_change = await self._sync_daily_sleep_data(
                user_id, all_data.get("sleep", []), force, force_today, today, force_recent_date
            )

            # 合并两个睡眠变化标志（单次睡眠记录变化 或 每日评分变化）
            has_significant_sleep_change = has_significant_sleep_change or has_daily_sleep_change
            stats["readiness"] = await self._sync_readiness_data(
                user_id, all_data.get("readiness", []), force, force_today, today, force_recent_date
            )
            stats["activity"] = await self._sync_activity_data(
                user_id, all_data.get("activity", []), force, force_today, today, force_recent_date
            )
            stats["stress"] = await self._sync_stress_data(
                user_id, all_data.get("stress", []), force, force_today, today, force_recent_date
            )
            stats["spo2"] = await self._sync_spo2_data(
                user_id, all_data.get("spo2", []), force, force_today, today, force_recent_date
            )
            stats["cardiovascular_age"] = await self._sync_cardiovascular_age_data(
                user_id, all_data.get("cardiovascular_age", []), force, force_today, today, force_recent_date
            )
            stats["resilience"] = await self._sync_resilience_data(
                user_id, all_data.get("resilience", []), force, force_today, today, force_recent_date
            )
            stats["vo2_max"] = await self._sync_vo2_max_data(
                user_id, all_data.get("vo2_max", []), force, force_today, today, force_recent_date
            )

            # 更新最后同步时间
            result = await self.db.execute(
                select(OuraAuth).where(OuraAuth.user_id == user_id)
            )
            auth = result.scalar_one_or_none()
            if auth:
                auth.last_sync_at = now_hk()
                auth.updated_at = now_hk()

            await self.db.commit()

            logger.info(f"Oura数据同步完成: user_id={user_id}, stats={stats}")

            # 注意：不再在数据同步时触发AI更新
            # AI更新统一由 11:35 的 generate_ai_recommendations_job 定时任务处理
            # 这样确保所有数据（Polar + Oura）都同步完成后再生成AI建议
            if has_significant_sleep_change:
                logger.info(f"睡眠数据有实质性变化: user_id={user_id} (AI将在定时任务中统一更新)")

            return stats

        except Exception as e:
            import traceback
            logger.error(f"Oura数据同步失败: user_id={user_id} - {str(e)}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            await self.db.rollback()
            raise

    async def _sync_sleep_data(
        self,
        user_id: uuid.UUID,
        sleep_data: list,
        sleep_details: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> Tuple[int, bool]:
        """同步睡眠数据 - 存储所有睡眠片段（主睡眠+午休+小憩）

        改用 Detail ID 作为主键，每个睡眠片段独立存储。
        Daily Sleep Summary 的 score 和 contributors 关联到主睡眠(long_sleep)记录。

        Returns:
            (new_count, has_significant_change): 新增/更新数量, 是否有实质性变化
        """
        import pytz
        hk_tz = pytz.timezone("Asia/Hong_Kong")

        new_count = 0
        has_significant_change = False

        # 创建 Daily Sleep Summary 映射（按日期），用于关联 score 和 contributors 到主睡眠
        summary_map = {}
        for item in sleep_data:
            day = item.get("day")
            if day:
                summary_map[day] = item

        logger.info(
            f"睡眠数据同步: sleep_details={len(sleep_details)}条片段, "
            f"sleep_summary={len(sleep_data)}条汇总"
        )

        # 遍历所有睡眠片段（每个片段独立存储）
        for detail in sleep_details:
            detail_id = detail.get("id")
            if not detail_id:
                continue

            # 检查是否已存在（使用 Detail ID）
            result = await self.db.execute(
                select(OuraSleep).where(OuraSleep.oura_id == detail_id)
            )
            existing = result.scalar_one_or_none()

            day = detail.get("day")
            sleep_type = detail.get("type")  # long_sleep 或 sleep

            # 获取对应的 Summary（只有主睡眠关联 Summary 的 score）
            summary = summary_map.get(day, {}) if sleep_type == "long_sleep" else {}

            # 判断是否需要更新
            needs_update = False
            item_has_change = False

            # 解析日期用于判断
            item_date = date.fromisoformat(day) if day else None

            if existing and not force:
                if existing.total_sleep_duration is None:
                    needs_update = True
                else:
                    # 判断是否需要强制更新（与其他同步方法保持一致）
                    # 1. force_today: 仅更新今天
                    # 2. force_recent_date: 更新该日期及之后的数据
                    if force_today and item_date == today:
                        needs_update = True
                    elif force_recent_date and item_date and item_date >= force_recent_date:
                        needs_update = True

                    # 检测关键字段是否有实质性变化（用于触发AI更新）
                    # 1. 时长变化 ≥5分钟
                    new_duration = detail.get("total_sleep_duration")
                    if new_duration and existing.total_sleep_duration:
                        duration_diff = abs(new_duration - existing.total_sleep_duration)
                        if duration_diff >= 300:  # 5分钟
                            item_has_change = True
                            needs_update = True

                    # 2. 评分变化（主睡眠检查 summary.score，午睡检查 sleep_score_delta）
                    if sleep_type == "long_sleep":
                        new_score = summary.get("score")
                        if new_score and existing.sleep_score and new_score != existing.sleep_score:
                            item_has_change = True
                            needs_update = True
                            logger.info(f"主睡眠评分变化: {existing.sleep_score} -> {new_score}")
                    else:
                        new_delta = detail.get("sleep_score_delta")
                        if new_delta is not None and existing.sleep_score_delta is not None:
                            if new_delta != existing.sleep_score_delta:
                                item_has_change = True
                                needs_update = True
                                logger.info(f"午睡评分增量变化: {existing.sleep_score_delta} -> {new_delta}")

                    if not needs_update:
                        continue

            # 解析时间
            bedtime_start = None
            bedtime_end = None
            if detail.get("bedtime_start"):
                bedtime_start = datetime.fromisoformat(
                    detail["bedtime_start"].replace("Z", "+00:00")
                )
            if detail.get("bedtime_end"):
                bedtime_end = datetime.fromisoformat(
                    detail["bedtime_end"].replace("Z", "+00:00")
                )

            # 确定睡眠归属日期：使用睡眠结束日期（香港时间）
            if bedtime_end:
                bedtime_end_hk = bedtime_end.astimezone(hk_tz)
                sleep_day = bedtime_end_hk.date()
            else:
                sleep_day = date.fromisoformat(day) if day else today_hk()

            # 提取 Detail.Readiness
            readiness = detail.get("readiness")
            readiness_contributors = readiness.get("contributors", {}) if readiness else {}

            # 提取 Summary.Contributors（仅主睡眠）
            summary_contributors = summary.get("contributors", {})

            if existing and (force or needs_update):
                # 更新现有记录
                existing.day = sleep_day
                existing.bedtime_start = bedtime_start
                existing.bedtime_end = bedtime_end
                existing.total_sleep_duration = detail.get("total_sleep_duration")
                existing.deep_sleep_duration = detail.get("deep_sleep_duration")
                existing.light_sleep_duration = detail.get("light_sleep_duration")
                existing.rem_sleep_duration = detail.get("rem_sleep_duration")
                existing.awake_time = detail.get("awake_time")
                existing.average_heart_rate = detail.get("average_heart_rate")
                existing.lowest_heart_rate = detail.get("lowest_heart_rate")
                existing.average_hrv = detail.get("average_hrv")
                existing.average_breath = detail.get("average_breath")
                existing.efficiency = detail.get("efficiency")

                # sleep_score: 主睡眠用 Summary.score，午休用 Detail.readiness.score
                if sleep_type == "long_sleep" and summary.get("score"):
                    existing.sleep_score = summary.get("score")
                elif readiness:
                    existing.sleep_score = readiness.get("score")

                # 睡眠贡献因子（仅主睡眠有 Summary.Contributors）
                existing.contributor_total_sleep = summary_contributors.get("total_sleep")
                existing.contributor_efficiency = summary_contributors.get("efficiency")
                existing.contributor_restfulness = summary_contributors.get("restfulness")
                existing.contributor_rem_sleep = summary_contributors.get("rem_sleep")
                existing.contributor_deep_sleep = summary_contributors.get("deep_sleep")
                existing.contributor_latency = summary_contributors.get("latency")
                existing.contributor_timing = summary_contributors.get("timing")

                # Detail 字段
                existing.sleep_type = sleep_type
                existing.time_in_bed = detail.get("time_in_bed")
                existing.latency = detail.get("latency")
                existing.restless_periods = detail.get("restless_periods")

                # Detail.Readiness
                if readiness:
                    existing.readiness_score_embedded = readiness.get("score")
                    existing.readiness_contributor_sleep_balance = readiness_contributors.get("sleep_balance")
                    existing.readiness_contributor_previous_night = readiness_contributors.get("previous_night")
                    existing.readiness_contributor_recovery_index = readiness_contributors.get("recovery_index")
                    existing.readiness_contributor_activity_balance = readiness_contributors.get("activity_balance")
                    existing.readiness_contributor_body_temperature = readiness_contributors.get("body_temperature")
                    existing.readiness_contributor_resting_heart_rate = readiness_contributors.get("resting_heart_rate")
                    existing.readiness_contributor_hrv_balance = readiness_contributors.get("hrv_balance")
                    existing.readiness_contributor_previous_day_activity = readiness_contributors.get("previous_day_activity")
                    existing.readiness_temperature_deviation = readiness.get("temperature_deviation")
                    existing.readiness_temperature_trend_deviation = readiness.get("temperature_trend_deviation")

                # 评分增量（午睡对当日总评分的贡献）
                existing.sleep_score_delta = detail.get("sleep_score_delta")
                existing.readiness_score_delta = detail.get("readiness_score_delta")

                existing.raw_json = {"summary": summary, "detail": detail}

                if needs_update:
                    new_count += 1
                    if item_has_change:
                        has_significant_change = True
                        logger.info(
                            f"睡眠片段更新: user_id={user_id}, day={sleep_day}, "
                            f"type={sleep_type}, duration={detail.get('total_sleep_duration', 0)//60}min"
                        )
            elif not existing:
                # 新建记录
                # sleep_score: 主睡眠用 Summary.score，午休用 Detail.readiness.score
                sleep_score = None
                if sleep_type == "long_sleep" and summary.get("score"):
                    sleep_score = summary.get("score")
                elif readiness:
                    sleep_score = readiness.get("score")

                sleep_record = OuraSleep(
                    user_id=user_id,
                    oura_id=detail_id,
                    day=sleep_day,
                    bedtime_start=bedtime_start,
                    bedtime_end=bedtime_end,
                    total_sleep_duration=detail.get("total_sleep_duration"),
                    deep_sleep_duration=detail.get("deep_sleep_duration"),
                    light_sleep_duration=detail.get("light_sleep_duration"),
                    rem_sleep_duration=detail.get("rem_sleep_duration"),
                    awake_time=detail.get("awake_time"),
                    average_heart_rate=detail.get("average_heart_rate"),
                    lowest_heart_rate=detail.get("lowest_heart_rate"),
                    average_hrv=detail.get("average_hrv"),
                    average_breath=detail.get("average_breath"),
                    sleep_score=sleep_score,
                    efficiency=detail.get("efficiency"),
                    # 睡眠贡献因子（仅主睡眠）
                    contributor_total_sleep=summary_contributors.get("total_sleep"),
                    contributor_efficiency=summary_contributors.get("efficiency"),
                    contributor_restfulness=summary_contributors.get("restfulness"),
                    contributor_rem_sleep=summary_contributors.get("rem_sleep"),
                    contributor_deep_sleep=summary_contributors.get("deep_sleep"),
                    contributor_latency=summary_contributors.get("latency"),
                    contributor_timing=summary_contributors.get("timing"),
                    # Detail 字段
                    sleep_type=sleep_type,
                    time_in_bed=detail.get("time_in_bed"),
                    latency=detail.get("latency"),
                    restless_periods=detail.get("restless_periods"),
                    # Detail.Readiness
                    readiness_score_embedded=readiness.get("score") if readiness else None,
                    readiness_contributor_sleep_balance=readiness_contributors.get("sleep_balance"),
                    readiness_contributor_previous_night=readiness_contributors.get("previous_night"),
                    readiness_contributor_recovery_index=readiness_contributors.get("recovery_index"),
                    readiness_contributor_activity_balance=readiness_contributors.get("activity_balance"),
                    readiness_contributor_body_temperature=readiness_contributors.get("body_temperature"),
                    readiness_contributor_resting_heart_rate=readiness_contributors.get("resting_heart_rate"),
                    readiness_contributor_hrv_balance=readiness_contributors.get("hrv_balance"),
                    readiness_contributor_previous_day_activity=readiness_contributors.get("previous_day_activity"),
                    readiness_temperature_deviation=readiness.get("temperature_deviation") if readiness else None,
                    readiness_temperature_trend_deviation=readiness.get("temperature_trend_deviation") if readiness else None,
                    # 评分增量（午睡对当日总评分的贡献）
                    sleep_score_delta=detail.get("sleep_score_delta"),
                    readiness_score_delta=detail.get("readiness_score_delta"),
                    raw_json={"summary": summary, "detail": detail},
                    created_at=now_hk(),
                )
                self.db.add(sleep_record)
                new_count += 1

                # 新增睡眠记录且时长≥5分钟，标记为实质性变化，触发AI更新
                new_duration = detail.get("total_sleep_duration", 0)
                if new_duration >= 300:  # 5分钟 = 300秒
                    has_significant_change = True
                    logger.info(
                        f"新增睡眠片段触发AI更新: user_id={user_id}, day={sleep_day}, "
                        f"type={sleep_type}, duration={new_duration//60}min"
                    )
                else:
                    logger.info(
                        f"新增睡眠片段(短于5分钟，不触发AI): user_id={user_id}, day={sleep_day}, "
                        f"type={sleep_type}, duration={new_duration//60}min"
                    )

        return (new_count, has_significant_change)

    async def _sync_daily_sleep_data(
        self,
        user_id: uuid.UUID,
        sleep_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> Tuple[int, bool]:
        """同步每日睡眠综合评分数据

        存储 Oura daily_sleep API 返回的综合评分。
        与 OuraSleep（单次睡眠记录）不同，这里存储的是每日的综合评分。
        即使没有主睡眠(long_sleep)，Oura 也会根据午睡等计算综合评分。

        Returns:
            (new_count, has_significant_change): 新增/更新数量, 是否有实质性变化
        """
        new_count = 0
        has_significant_change = False

        for item in sleep_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            # 检查是否已存在
            result = await self.db.execute(
                select(OuraDailySleep).where(OuraDailySleep.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            # 判断是否需要强制更新
            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            # 提取 contributors
            contributors = item.get("contributors", {})

            if existing and should_force:
                # 更新现有记录
                old_score = existing.score
                new_score = item.get("score")

                existing.day = date.fromisoformat(day) if day else existing.day
                existing.score = new_score
                existing.contributor_deep_sleep = contributors.get("deep_sleep")
                existing.contributor_efficiency = contributors.get("efficiency")
                existing.contributor_latency = contributors.get("latency")
                existing.contributor_rem_sleep = contributors.get("rem_sleep")
                existing.contributor_restfulness = contributors.get("restfulness")
                existing.contributor_timing = contributors.get("timing")
                existing.contributor_total_sleep = contributors.get("total_sleep")
                existing.raw_json = item
                new_count += 1

                # 检测分数是否有实质性变化（≥3分视为显著变化）
                if old_score is not None and new_score is not None:
                    score_change = abs(new_score - old_score)
                    if score_change >= 3:
                        has_significant_change = True
                        logger.info(
                            f"每日睡眠评分有显著变化，触发AI更新: user_id={user_id}, day={day}, "
                            f"score: {old_score} -> {new_score} (变化: {score_change}分)"
                        )
                    else:
                        logger.info(f"更新每日睡眠评分: user_id={user_id}, day={day}, score={new_score}")
                else:
                    logger.info(f"更新每日睡眠评分: user_id={user_id}, day={day}, score={new_score}")
            else:
                # 新建记录
                daily_sleep = OuraDailySleep(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    score=item.get("score"),
                    contributor_deep_sleep=contributors.get("deep_sleep"),
                    contributor_efficiency=contributors.get("efficiency"),
                    contributor_latency=contributors.get("latency"),
                    contributor_rem_sleep=contributors.get("rem_sleep"),
                    contributor_restfulness=contributors.get("restfulness"),
                    contributor_timing=contributors.get("timing"),
                    contributor_total_sleep=contributors.get("total_sleep"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(daily_sleep)
                new_count += 1

                # 新增每日睡眠评分，视为实质性变化，触发AI更新
                has_significant_change = True
                logger.info(
                    f"新增每日睡眠评分，触发AI更新: user_id={user_id}, day={day}, score={item.get('score')}"
                )

        return (new_count, has_significant_change)

    async def _sync_readiness_data(
        self,
        user_id: uuid.UUID,
        readiness_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> int:
        """同步准备度数据"""
        new_count = 0

        for item in readiness_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            result = await self.db.execute(
                select(OuraDailyReadiness).where(OuraDailyReadiness.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            # 判断是否需要强制更新
            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            contributors = item.get("contributors", {})

            if existing and should_force:
                existing.day = date.fromisoformat(day) if day else existing.day
                existing.score = item.get("score")
                existing.temperature_deviation = item.get("temperature_deviation")
                existing.temperature_trend_deviation = item.get("temperature_trend_deviation")
                existing.activity_balance = contributors.get("activity_balance")
                existing.sleep_balance = contributors.get("sleep_balance")
                existing.previous_night = contributors.get("previous_night")
                existing.previous_day_activity = contributors.get("previous_day_activity")
                existing.recovery_index = contributors.get("recovery_index")
                existing.resting_heart_rate = contributors.get("resting_heart_rate")
                existing.hrv_balance = contributors.get("hrv_balance")
                existing.body_temperature = contributors.get("body_temperature")
                existing.sleep_regularity = contributors.get("sleep_regularity")
                existing.raw_json = item
            else:
                readiness = OuraDailyReadiness(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    score=item.get("score"),
                    temperature_deviation=item.get("temperature_deviation"),
                    temperature_trend_deviation=item.get("temperature_trend_deviation"),
                    activity_balance=contributors.get("activity_balance"),
                    sleep_balance=contributors.get("sleep_balance"),
                    previous_night=contributors.get("previous_night"),
                    previous_day_activity=contributors.get("previous_day_activity"),
                    recovery_index=contributors.get("recovery_index"),
                    resting_heart_rate=contributors.get("resting_heart_rate"),
                    hrv_balance=contributors.get("hrv_balance"),
                    body_temperature=contributors.get("body_temperature"),
                    sleep_regularity=contributors.get("sleep_regularity"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(readiness)
                new_count += 1

        return new_count

    async def _sync_activity_data(
        self,
        user_id: uuid.UUID,
        activity_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> int:
        """同步活动数据"""
        new_count = 0

        for item in activity_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            result = await self.db.execute(
                select(OuraDailyActivity).where(OuraDailyActivity.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            # 判断是否需要强制更新
            # 1. force=True: 强制更新所有数据
            # 2. force_today=True 且是今天的数据: 强制更新今天的数据
            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            if existing and should_force:
                existing.day = date.fromisoformat(day) if day else existing.day
                existing.score = item.get("score")
                existing.active_calories = item.get("active_calories")
                existing.total_calories = item.get("total_calories")
                existing.steps = item.get("steps")
                existing.equivalent_walking_distance = item.get("equivalent_walking_distance")
                existing.high_activity_time = item.get("high_activity_time")
                existing.medium_activity_time = item.get("medium_activity_time")
                existing.low_activity_time = item.get("low_activity_time")
                existing.sedentary_time = item.get("sedentary_time")
                existing.resting_time = item.get("resting_time")
                existing.target_calories = item.get("target_calories")
                existing.target_meters = item.get("target_meters")

                # 提取活动贡献因子
                contributors = item.get("contributors", {})
                existing.contributor_stay_active = contributors.get("stay_active")
                existing.contributor_recovery_time = contributors.get("recovery_time")
                existing.contributor_move_every_hour = contributors.get("move_every_hour")
                existing.contributor_training_volume = contributors.get("training_volume")
                existing.contributor_training_frequency = contributors.get("training_frequency")
                existing.contributor_meet_daily_targets = contributors.get("meet_daily_targets")

                # 提取其他活动指标
                existing.non_wear_time = item.get("non_wear_time")
                existing.meters_to_target = item.get("meters_to_target")
                existing.inactivity_alerts = item.get("inactivity_alerts")
                existing.average_met_minutes = item.get("average_met_minutes")

                existing.raw_json = item
            else:
                # 提取活动贡献因子
                contributors = item.get("contributors", {})

                activity = OuraDailyActivity(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    score=item.get("score"),
                    active_calories=item.get("active_calories"),
                    total_calories=item.get("total_calories"),
                    steps=item.get("steps"),
                    equivalent_walking_distance=item.get("equivalent_walking_distance"),
                    high_activity_time=item.get("high_activity_time"),
                    medium_activity_time=item.get("medium_activity_time"),
                    low_activity_time=item.get("low_activity_time"),
                    sedentary_time=item.get("sedentary_time"),
                    resting_time=item.get("resting_time"),
                    target_calories=item.get("target_calories"),
                    target_meters=item.get("target_meters"),
                    # 活动贡献因子
                    contributor_stay_active=contributors.get("stay_active"),
                    contributor_recovery_time=contributors.get("recovery_time"),
                    contributor_move_every_hour=contributors.get("move_every_hour"),
                    contributor_training_volume=contributors.get("training_volume"),
                    contributor_training_frequency=contributors.get("training_frequency"),
                    contributor_meet_daily_targets=contributors.get("meet_daily_targets"),
                    # 其他活动指标
                    non_wear_time=item.get("non_wear_time"),
                    meters_to_target=item.get("meters_to_target"),
                    inactivity_alerts=item.get("inactivity_alerts"),
                    average_met_minutes=item.get("average_met_minutes"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(activity)
                new_count += 1

        return new_count

    async def _sync_stress_data(
        self,
        user_id: uuid.UUID,
        stress_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> int:
        """同步压力数据"""
        new_count = 0

        for item in stress_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            result = await self.db.execute(
                select(OuraDailyStress).where(OuraDailyStress.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            # 判断是否需要强制更新
            # force: 强制更新所有
            # force_today: 仅更新今天
            # force_recent_date: 更新该日期及之后的数据
            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            if existing and should_force:
                existing.day = date.fromisoformat(day) if day else existing.day
                existing.stress_high = item.get("stress_high")
                existing.recovery_high = item.get("recovery_high")
                existing.day_summary = item.get("day_summary")
                existing.raw_json = item
            else:
                stress = OuraDailyStress(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    stress_high=item.get("stress_high"),
                    recovery_high=item.get("recovery_high"),
                    day_summary=item.get("day_summary"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(stress)
                new_count += 1

        return new_count

    async def _sync_spo2_data(
        self,
        user_id: uuid.UUID,
        spo2_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> int:
        """同步血氧数据"""
        new_count = 0

        for item in spo2_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            result = await self.db.execute(
                select(OuraDailySpo2).where(OuraDailySpo2.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            # 判断是否需要强制更新
            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            # 安全获取 spo2_percentage，处理值为 None 的情况
            spo2_obj = item.get("spo2_percentage")
            spo2_avg = spo2_obj.get("average") if spo2_obj else None

            if existing and should_force:
                existing.day = date.fromisoformat(day) if day else existing.day
                existing.spo2_percentage = spo2_avg
                existing.breathing_disturbance_index = item.get("breathing_disturbance_index")
                existing.breathing_regularity = item.get("breathing_regularity")
                existing.raw_json = item
            else:
                spo2 = OuraDailySpo2(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    spo2_percentage=spo2_avg,
                    breathing_disturbance_index=item.get("breathing_disturbance_index"),
                    breathing_regularity=item.get("breathing_regularity"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(spo2)
                new_count += 1

        return new_count

    async def _sync_cardiovascular_age_data(
        self,
        user_id: uuid.UUID,
        cv_age_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> int:
        """同步心血管年龄数据"""
        new_count = 0

        for item in cv_age_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            result = await self.db.execute(
                select(OuraCardiovascularAge).where(OuraCardiovascularAge.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            if existing and should_force:
                existing.day = date.fromisoformat(day) if day else existing.day
                existing.vascular_age = item.get("vascular_age")
                existing.raw_json = item
            else:
                cv_age = OuraCardiovascularAge(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    vascular_age=item.get("vascular_age"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(cv_age)
                new_count += 1

        return new_count

    async def _sync_resilience_data(
        self,
        user_id: uuid.UUID,
        resilience_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> int:
        """同步韧性数据"""
        new_count = 0

        for item in resilience_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            result = await self.db.execute(
                select(OuraResilience).where(OuraResilience.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            contributors = item.get("contributors", {})

            if existing and should_force:
                existing.day = date.fromisoformat(day) if day else existing.day
                existing.level = item.get("level")
                existing.sleep_recovery = contributors.get("sleep_recovery")
                existing.daytime_recovery = contributors.get("daytime_recovery")
                existing.stress = contributors.get("stress")
                existing.raw_json = item
            else:
                resilience = OuraResilience(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    level=item.get("level"),
                    sleep_recovery=contributors.get("sleep_recovery"),
                    daytime_recovery=contributors.get("daytime_recovery"),
                    stress=contributors.get("stress"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(resilience)
                new_count += 1

        return new_count

    async def _sync_vo2_max_data(
        self,
        user_id: uuid.UUID,
        vo2_max_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> int:
        """同步VO2 Max数据"""
        new_count = 0

        for item in vo2_max_data:
            oura_id = item.get("id")
            if not oura_id:
                continue

            result = await self.db.execute(
                select(OuraVO2Max).where(OuraVO2Max.oura_id == oura_id)
            )
            existing = result.scalar_one_or_none()

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            should_force = force or (force_today and item_date == today) or (force_recent_date and item_date and item_date >= force_recent_date)

            if existing and not should_force:
                continue

            if existing and should_force:
                existing.day = date.fromisoformat(day) if day else existing.day
                existing.vo2_max = item.get("vo2_max")
                existing.raw_json = item
            else:
                vo2_max = OuraVO2Max(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    vo2_max=item.get("vo2_max"),
                    raw_json=item,
                    created_at=now_hk(),
                )
                self.db.add(vo2_max)
                new_count += 1

        return new_count

    async def sync_all_active_users(self, days: int = 2) -> Dict[str, Dict[str, int]]:
        """
        同步所有活跃用户的数据

        Args:
            days: 同步最近几天的数据

        Returns:
            同步统计 {user_id: {数据类型: 数量}}
        """
        try:
            # 获取所有有Oura授权的用户
            result = await self.db.execute(
                select(User)
                .join(User.oura_auth)
                .where(User.oura_auth.has(is_active=True))
            )
            users = result.scalars().all()

            logger.info(f"开始批量同步Oura数据: users={len(users)}, days={days}")

            sync_stats = {}
            for user in users:
                try:
                    stats = await self.sync_user_data(user.id, days=days)
                    sync_stats[str(user.id)] = stats
                except Exception as e:
                    logger.error(f"用户Oura数据同步失败: user_id={user.id} - {str(e)}")
                    sync_stats[str(user.id)] = {"error": str(e)}

            logger.info(f"批量Oura同步完成: stats={sync_stats}")
            return sync_stats

        except Exception as e:
            logger.error(f"批量Oura同步失败: {str(e)}")
            raise

    async def _trigger_ai_update(self, user_id: uuid.UUID):
        """
        触发AI重新生成今天的建议（当Oura数据更新时）

        Args:
            user_id: 用户ID
        """
        try:
            from app.services.ai_service import AIService

            ai_service = AIService(self.db)
            today = today_hk()

            # 使用force_update=True强制重新生成今天的建议
            await ai_service.generate_daily_recommendation(
                user_id=user_id,
                target_date=today,
                force_update=True
            )

            logger.info(f"Oura数据更新后触发AI重新生成成功: user_id={user_id}, date={today}")

        except Exception as e:
            # AI生成失败不应影响数据同步，只记录错误
            logger.error(f"Oura数据更新后触发AI重新生成失败: user_id={user_id} - {str(e)}")

    async def check_connection(self, user_id: uuid.UUID) -> bool:
        """
        检查Oura连接状态

        Args:
            user_id: 用户ID

        Returns:
            是否连接正常
        """
        try:
            access_token = await self.get_access_token(user_id)
            if not access_token:
                return False

            # 尝试获取个人信息来验证连接
            personal_info = await self.oura_client.get_personal_info(access_token)
            return personal_info is not None

        except Exception as e:
            logger.error(f"Oura连接检查失败: user_id={user_id} - {str(e)}")
            return False
