"""
Oura数据同步服务 - 重构版本
使用泛型同步方法减少代码重复
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.oura.client import OuraClient
from app.models.oura import (
    OuraAuth, OuraSleep, OuraDailySleep, OuraDailyReadiness,
    OuraDailyActivity, OuraDailyStress, OuraDailySpo2,
    OuraCardiovascularAge, OuraResilience, OuraVO2Max,
    OuraSleepTime
)
from app.models.user import User
from app.utils.datetime_helper import today_hk, now_hk

logger = logging.getLogger(__name__)


# ============================================================================
# 数据同步配置
# 每个配置定义了如何将 API 数据映射到 ORM 模型
# ============================================================================

SYNC_CONFIGS = {
    "readiness": {
        "model": OuraDailyReadiness,
        "fields": {
            "score": "score",
            "temperature_deviation": "temperature_deviation",
            "temperature_trend_deviation": "temperature_trend_deviation",
        },
        "contributor_fields": {
            "activity_balance": "activity_balance",
            "sleep_balance": "sleep_balance",
            "previous_night": "previous_night",
            "previous_day_activity": "previous_day_activity",
            "recovery_index": "recovery_index",
            "resting_heart_rate": "resting_heart_rate",
            "hrv_balance": "hrv_balance",
            "body_temperature": "body_temperature",
            "sleep_regularity": "sleep_regularity",
        },
    },
    "activity": {
        "model": OuraDailyActivity,
        "fields": {
            "score": "score",
            "active_calories": "active_calories",
            "total_calories": "total_calories",
            "steps": "steps",
            "equivalent_walking_distance": "equivalent_walking_distance",
            "high_activity_time": "high_activity_time",
            "medium_activity_time": "medium_activity_time",
            "low_activity_time": "low_activity_time",
            "sedentary_time": "sedentary_time",
            "resting_time": "resting_time",
            "target_calories": "target_calories",
            "target_meters": "target_meters",
            "non_wear_time": "non_wear_time",
            "meters_to_target": "meters_to_target",
            "inactivity_alerts": "inactivity_alerts",
            "average_met_minutes": "average_met_minutes",
        },
        "contributor_fields": {
            "stay_active": "contributor_stay_active",
            "recovery_time": "contributor_recovery_time",
            "move_every_hour": "contributor_move_every_hour",
            "training_volume": "contributor_training_volume",
            "training_frequency": "contributor_training_frequency",
            "meet_daily_targets": "contributor_meet_daily_targets",
        },
    },
    "stress": {
        "model": OuraDailyStress,
        "fields": {
            "stress_high": "stress_high",
            "recovery_high": "recovery_high",
            "day_summary": "day_summary",
        },
        "contributor_fields": {},
    },
    "spo2": {
        "model": OuraDailySpo2,
        "fields": {
            "breathing_disturbance_index": "breathing_disturbance_index",
            "breathing_regularity": "breathing_regularity",
        },
        "contributor_fields": {},
        "custom_extractor": lambda item: {
            "spo2_percentage": (item.get("spo2_percentage") or {}).get("average")
        },
    },
    "cardiovascular_age": {
        "model": OuraCardiovascularAge,
        "fields": {
            "vascular_age": "vascular_age",
        },
        "contributor_fields": {},
    },
    "resilience": {
        "model": OuraResilience,
        "fields": {
            "level": "level",
        },
        "contributor_fields": {
            "sleep_recovery": "sleep_recovery",
            "daytime_recovery": "daytime_recovery",
            "stress": "stress",
        },
    },
    "vo2_max": {
        "model": OuraVO2Max,
        "fields": {
            "vo2_max": "vo2_max",
        },
        "contributor_fields": {},
    },
    "sleep_time": {
        "model": OuraSleepTime,
        "fields": {
            "recommendation": "recommendation",
            "status": "status",
        },
        "contributor_fields": {},
        "custom_extractor": lambda item: {
            "optimal_bedtime_start": (item.get("optimal_bedtime") or {}).get("start_offset"),
            "optimal_bedtime_end": (item.get("optimal_bedtime") or {}).get("end_offset"),
            "day_tz": (item.get("optimal_bedtime") or {}).get("day_tz"),
        },
    },
}


class OuraSyncService:
    """Oura数据同步服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.oura_client = OuraClient()

    # ========================================================================
    # 公共方法
    # ========================================================================

    async def get_access_token(self, user_id: uuid.UUID) -> Optional[str]:
        """获取用户的Oura访问令牌"""
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
        """同步用户所有Oura数据"""
        try:
            access_token = await self.get_access_token(user_id)
            if not access_token:
                logger.error(f"无法获取Oura访问令牌: user_id={user_id}")
                return {}

            # 计算日期范围
            end_date = today_hk() + timedelta(days=1)
            start_date = today_hk() - timedelta(days=days - 1)

            logger.info(
                f"开始同步Oura数据: user_id={user_id}, range={start_date} to {end_date}"
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
                "sleep_time": 0,
            }

            today = today_hk()
            force_recent_date = today - timedelta(days=force_recent_days - 1) if force_recent_days > 0 else None

            # 同步睡眠数据（特殊处理）
            stats["sleep"], has_significant_sleep_change = await self._sync_sleep_data(
                user_id, all_data.get("sleep", []), all_data.get("sleep_details", []),
                force, force_today, today, force_recent_date
            )
            stats["daily_sleep"], has_daily_sleep_change = await self._sync_daily_sleep_data(
                user_id, all_data.get("sleep", []),
                force, force_today, today, force_recent_date
            )
            has_significant_sleep_change = has_significant_sleep_change or has_daily_sleep_change

            # 使用泛型方法同步其他数据
            for data_type, config in SYNC_CONFIGS.items():
                stats[data_type] = await self._sync_generic_data(
                    user_id=user_id,
                    data_list=all_data.get(data_type, []),
                    config=config,
                    force=force,
                    force_today=force_today,
                    today=today,
                    force_recent_date=force_recent_date,
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

            if has_significant_sleep_change:
                logger.info(f"睡眠数据有实质性变化: user_id={user_id} (AI将在定时任务中统一更新)")

            return stats

        except Exception as e:
            import traceback
            logger.error(f"Oura数据同步失败: user_id={user_id} - {str(e)}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            await self.db.rollback()
            raise

    # ========================================================================
    # 泛型同步方法
    # ========================================================================

    def _should_force_update(
        self,
        item_date: Optional[date],
        force: bool,
        force_today: bool,
        today: date,
        force_recent_date: Optional[date]
    ) -> bool:
        """判断是否需要强制更新"""
        if force:
            return True
        if force_today and item_date == today:
            return True
        if force_recent_date and item_date and item_date >= force_recent_date:
            return True
        return False

    async def _sync_generic_data(
        self,
        user_id: uuid.UUID,
        data_list: List[Dict],
        config: Dict[str, Any],
        force: bool,
        force_today: bool,
        today: date,
        force_recent_date: Optional[date],
    ) -> int:
        """
        泛型数据同步方法

        根据配置自动处理各类 Oura 数据的同步
        """
        model_class = config["model"]
        field_mapping = config["fields"]
        contributor_mapping = config.get("contributor_fields", {})
        custom_extractor = config.get("custom_extractor")

        if not data_list:
            return 0

        new_count = 0

        ids = [str(item.get("id")) for item in data_list if item.get("id")]
        existing_records = {}
        if ids:
            result = await self.db.execute(
                select(model_class).where(model_class.oura_id.in_(ids))
            )
            existing_records = {
                str(record.oura_id): record for record in result.scalars().all()
            }

        for item in data_list:
            oura_id = str(item.get("id")) if item.get("id") else None
            if not oura_id:
                continue

            existing = existing_records.get(oura_id)

            # 解析日期
            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None

            # 判断是否需要更新
            should_force = self._should_force_update(
                item_date, force, force_today, today, force_recent_date
            )

            if existing and not should_force:
                continue

            # 提取 contributors
            contributors = item.get("contributors", {})

            # 构建字段值
            field_values = {}

            # 基础字段
            for api_field, model_field in field_mapping.items():
                field_values[model_field] = item.get(api_field)

            # contributor 字段
            for api_field, model_field in contributor_mapping.items():
                field_values[model_field] = contributors.get(api_field)

            # 自定义提取器
            if custom_extractor:
                field_values.update(custom_extractor(item))

            if existing and should_force:
                # 更新现有记录
                existing.day = date.fromisoformat(day) if day else existing.day
                for field_name, value in field_values.items():
                    setattr(existing, field_name, value)
                existing.raw_json = item
            else:
                # 新建记录
                record = model_class(
                    user_id=user_id,
                    oura_id=oura_id,
                    day=date.fromisoformat(day) if day else today_hk(),
                    raw_json=item,
                    created_at=now_hk(),
                    **field_values
                )
                self.db.add(record)
                new_count += 1

        return new_count
    # ========================================================================
    # 睡眠数据同步（需要特殊处理，保持原有逻辑）
    # ========================================================================

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
        """同步睡眠数据 - 存储所有睡眠片段（主睡眠+午休+小憩）"""
        import pytz
        hk_tz = pytz.timezone("Asia/Hong_Kong")

        new_count = 0
        has_significant_change = False

        # 创建 Daily Sleep Summary 映射
        summary_map = {item.get("day"): item for item in sleep_data if item.get("day")}

        detail_ids = [str(detail.get("id")) for detail in sleep_details if detail.get("id")]
        existing_records = {}
        if detail_ids:
            result = await self.db.execute(
                select(OuraSleep).where(OuraSleep.oura_id.in_(detail_ids))
            )
            existing_records = {
                str(record.oura_id): record for record in result.scalars().all()
            }

        logger.info(
            f"睡眠数据同步: sleep_details={len(sleep_details)}条片段, "
            f"sleep_summary={len(sleep_data)}条汇总"
        )

        for detail in sleep_details:
            detail_id = str(detail.get("id"))
            if not detail_id:
                continue

            existing = existing_records.get(detail_id)

            day = detail.get("day")
            sleep_type = detail.get("type")
            summary = summary_map.get(day, {}) if sleep_type == "long_sleep" else {}

            # 判断是否需要更新
            needs_update = False
            item_has_change = False
            item_date = date.fromisoformat(day) if day else None

            if existing and not force:
                if existing.total_sleep_duration is None:
                    needs_update = True
                else:
                    should_force = self._should_force_update(
                        item_date, force, force_today, today, force_recent_date
                    )
                    if should_force:
                        needs_update = True

                    # 检测关键字段变化
                    new_duration = detail.get("total_sleep_duration")
                    if new_duration and existing.total_sleep_duration:
                        if abs(new_duration - existing.total_sleep_duration) >= 300:
                            item_has_change = True
                            needs_update = True

                    if sleep_type == "long_sleep":
                        new_score = summary.get("score")
                        if new_score and existing.sleep_score and new_score != existing.sleep_score:
                            item_has_change = True
                            needs_update = True
                    else:
                        new_delta = detail.get("sleep_score_delta")
                        if new_delta is not None and existing.sleep_score_delta is not None:
                            if new_delta != existing.sleep_score_delta:
                                item_has_change = True
                                needs_update = True

                    if not needs_update:
                        continue

            # 解析时间
            bedtime_start = self._parse_datetime(detail.get("bedtime_start"))
            bedtime_end = self._parse_datetime(detail.get("bedtime_end"))

            # 确定睡眠归属日期
            if bedtime_end:
                sleep_day = bedtime_end.astimezone(hk_tz).date()
            else:
                sleep_day = date.fromisoformat(day) if day else today_hk()

            # 提取数据
            readiness = detail.get("readiness")
            readiness_contributors = readiness.get("contributors", {}) if readiness else {}
            summary_contributors = summary.get("contributors", {})

            # 构建睡眠记录数据
            sleep_data_dict = self._build_sleep_data(
                detail, summary, readiness, readiness_contributors, summary_contributors, sleep_type
            )

            if existing and (force or needs_update):
                self._update_sleep_record(existing, sleep_day, bedtime_start, bedtime_end, sleep_data_dict, summary, detail)
                if needs_update:
                    new_count += 1
                    if item_has_change:
                        has_significant_change = True
                        logger.info(
                            f"睡眠片段更新: user_id={user_id}, day={sleep_day}, "
                            f"type={sleep_type}, duration={detail.get('total_sleep_duration', 0)//60}min"
                        )
            elif not existing:
                sleep_record = self._create_sleep_record(
                    user_id, detail_id, sleep_day, bedtime_start, bedtime_end,
                    sleep_data_dict, summary, detail
                )
                self.db.add(sleep_record)
                new_count += 1

                new_duration = detail.get("total_sleep_duration", 0)
                if new_duration >= 300:
                    has_significant_change = True
                    logger.info(
                        f"新增睡眠片段触发AI更新: user_id={user_id}, day={sleep_day}, "
                        f"type={sleep_type}, duration={new_duration//60}min"
                    )

        return (new_count, has_significant_change)
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """解析 ISO 格式日期时间"""
        if not dt_str:
            return None
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    def _build_sleep_data(
        self,
        detail: Dict,
        summary: Dict,
        readiness: Optional[Dict],
        readiness_contributors: Dict,
        summary_contributors: Dict,
        sleep_type: str
    ) -> Dict:
        """构建睡眠记录数据字典"""
        # 确定 sleep_score
        if sleep_type == "long_sleep" and summary.get("score"):
            sleep_score = summary.get("score")
        elif readiness:
            sleep_score = readiness.get("score")
        else:
            sleep_score = None

        return {
            "total_sleep_duration": detail.get("total_sleep_duration"),
            "deep_sleep_duration": detail.get("deep_sleep_duration"),
            "light_sleep_duration": detail.get("light_sleep_duration"),
            "rem_sleep_duration": detail.get("rem_sleep_duration"),
            "awake_time": detail.get("awake_time"),
            "average_heart_rate": detail.get("average_heart_rate"),
            "lowest_heart_rate": detail.get("lowest_heart_rate"),
            "average_hrv": detail.get("average_hrv"),
            "average_breath": detail.get("average_breath"),
            "efficiency": detail.get("efficiency"),
            "sleep_score": sleep_score,
            "sleep_type": sleep_type,
            "time_in_bed": detail.get("time_in_bed"),
            "latency": detail.get("latency"),
            "restless_periods": detail.get("restless_periods"),
            "sleep_score_delta": detail.get("sleep_score_delta"),
            "readiness_score_delta": detail.get("readiness_score_delta"),
            # Summary contributors
            "contributor_total_sleep": summary_contributors.get("total_sleep"),
            "contributor_efficiency": summary_contributors.get("efficiency"),
            "contributor_restfulness": summary_contributors.get("restfulness"),
            "contributor_rem_sleep": summary_contributors.get("rem_sleep"),
            "contributor_deep_sleep": summary_contributors.get("deep_sleep"),
            "contributor_latency": summary_contributors.get("latency"),
            "contributor_timing": summary_contributors.get("timing"),
            # Readiness
            "readiness_score_embedded": readiness.get("score") if readiness else None,
            "readiness_contributor_sleep_balance": readiness_contributors.get("sleep_balance"),
            "readiness_contributor_previous_night": readiness_contributors.get("previous_night"),
            "readiness_contributor_recovery_index": readiness_contributors.get("recovery_index"),
            "readiness_contributor_activity_balance": readiness_contributors.get("activity_balance"),
            "readiness_contributor_body_temperature": readiness_contributors.get("body_temperature"),
            "readiness_contributor_resting_heart_rate": readiness_contributors.get("resting_heart_rate"),
            "readiness_contributor_hrv_balance": readiness_contributors.get("hrv_balance"),
            "readiness_contributor_previous_day_activity": readiness_contributors.get("previous_day_activity"),
            "readiness_temperature_deviation": readiness.get("temperature_deviation") if readiness else None,
            "readiness_temperature_trend_deviation": readiness.get("temperature_trend_deviation") if readiness else None,
        }

    def _update_sleep_record(
        self,
        existing: OuraSleep,
        sleep_day: date,
        bedtime_start: Optional[datetime],
        bedtime_end: Optional[datetime],
        data: Dict,
        summary: Dict,
        detail: Dict
    ):
        """更新现有睡眠记录"""
        existing.day = sleep_day
        existing.bedtime_start = bedtime_start
        existing.bedtime_end = bedtime_end
        for key, value in data.items():
            setattr(existing, key, value)
        existing.raw_json = {"summary": summary, "detail": detail}

    def _create_sleep_record(
        self,
        user_id: uuid.UUID,
        oura_id: str,
        sleep_day: date,
        bedtime_start: Optional[datetime],
        bedtime_end: Optional[datetime],
        data: Dict,
        summary: Dict,
        detail: Dict
    ) -> OuraSleep:
        """创建新的睡眠记录"""
        return OuraSleep(
            user_id=user_id,
            oura_id=oura_id,
            day=sleep_day,
            bedtime_start=bedtime_start,
            bedtime_end=bedtime_end,
            raw_json={"summary": summary, "detail": detail},
            created_at=now_hk(),
            **data
        )

    async def _sync_daily_sleep_data(
        self,
        user_id: uuid.UUID,
        sleep_data: list,
        force: bool,
        force_today: bool = False,
        today: date = None,
        force_recent_date: date = None
    ) -> Tuple[int, bool]:
        """同步每日睡眠综合评分数据"""
        new_count = 0
        has_significant_change = False

        ids = [str(item.get("id")) for item in sleep_data if item.get("id")]
        existing_records = {}
        if ids:
            result = await self.db.execute(
                select(OuraDailySleep).where(OuraDailySleep.oura_id.in_(ids))
            )
            existing_records = {
                str(record.oura_id): record for record in result.scalars().all()
            }

        for item in sleep_data:
            oura_id = str(item.get("id"))
            if not oura_id:
                continue

            existing = existing_records.get(oura_id)

            day = item.get("day")
            item_date = date.fromisoformat(day) if day else None
            should_force = self._should_force_update(
                item_date, force, force_today, today, force_recent_date
            )

            if existing and not should_force:
                continue

            contributors = item.get("contributors", {})

            if existing and should_force:
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

                if old_score is not None and new_score is not None:
                    score_change = abs(new_score - old_score)
                    if score_change >= 3:
                        has_significant_change = True
                        logger.info(
                            f"每日睡眠评分有显著变化: user_id={user_id}, day={day}, "
                            f"score: {old_score} -> {new_score}"
                        )
            else:
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
                has_significant_change = True
                logger.info(f"新增每日睡眠评分: user_id={user_id}, day={day}")

        return (new_count, has_significant_change)
    # ========================================================================
    # 其他公共方法
    # ========================================================================

    async def sync_all_active_users(self, days: int = 2) -> Dict[str, Dict[str, int]]:
        """同步所有活跃用户的数据"""
        try:
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
        """触发AI重新生成今天的建议"""
        try:
            from app.services.ai_service import AIService

            ai_service = AIService(self.db)
            today = today_hk()

            await ai_service.generate_daily_recommendation(
                user_id=user_id,
                target_date=today,
                force_update=True
            )

            logger.info(f"Oura数据更新后触发AI重新生成成功: user_id={user_id}, date={today}")

        except Exception as e:
            logger.error(f"Oura数据更新后触发AI重新生成失败: user_id={user_id} - {str(e)}")

    async def check_connection(self, user_id: uuid.UUID) -> bool:
        """检查Oura连接状态"""
        try:
            access_token = await self.get_access_token(user_id)
            if not access_token:
                return False

            personal_info = await self.oura_client.get_personal_info(access_token)
            return personal_info is not None

        except Exception as e:
            logger.error(f"Oura连接检查失败: user_id={user_id} - {str(e)}")
            return False
