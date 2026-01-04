"""
睡眠指标计算服务

复刻 Oura 的睡眠债务计算算法
"""
import logging
from datetime import date, timedelta
from typing import Optional
import uuid
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.oura import OuraSleep
from app.utils.datetime_helper import today_hk

logger = logging.getLogger(__name__)


class SleepMetricsService:
    """睡眠指标计算服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_sleep_debt(
        self, user_id: uuid.UUID, target_date: Optional[date] = None
    ) -> Optional[dict]:
        """
        计算睡眠债务（复刻 Oura 算法）

        算法说明（基于 Oura 官方文档）：
        1. 计算过去90天平均睡眠时长（排除异常值）作为个人睡眠需求
        2. 过去14天每日: 债务 = 个人需求 - 实际睡眠
        3. 加权求和（最近的天数权重更高）
        4. 需要至少5晚数据才能计算

        参数:
            user_id: 用户ID
            target_date: 目标日期（默认今天）

        返回:
            {
                "sleep_debt_minutes": int,  # 睡眠债务（分钟），正数表示欠债，负数表示多睡
                "baseline_sleep_minutes": int,  # 个人睡眠需求（分钟）
                "recent_14d_avg_minutes": int,  # 最近14天平均睡眠（分钟）
                "debt_trend": str,  # "improving" | "stable" | "worsening"
                "sleep_balance_score": int,  # 复刻的睡眠平衡评分（0-100）
                "data_quality": str,  # "good" | "limited" | "insufficient"
            }
        """
        if not target_date:
            target_date = today_hk()

        # 1. 计算个人睡眠需求基线（过去90天平均，排除异常值）
        baseline_minutes = await self._calculate_baseline_sleep(user_id, target_date)
        if baseline_minutes is None:
            logger.warning(f"无法计算睡眠基线: user_id={user_id}, date={target_date}")
            return None

        # 2. 获取过去14天的睡眠数据
        start_date = target_date - timedelta(days=13)
        result = await self.db.execute(
            select(OuraSleep)
            .where(
                OuraSleep.user_id == user_id,
                OuraSleep.day >= start_date,
                OuraSleep.day <= target_date,
                OuraSleep.total_sleep_duration.isnot(None),
            )
            .order_by(OuraSleep.day.desc())
        )
        sleep_records = result.scalars().all()

        if len(sleep_records) < 5:
            logger.warning(
                f"过去14天睡眠数据不足（需要至少5晚）: user_id={user_id}, "
                f"actual={len(sleep_records)}"
            )
            return {
                "sleep_debt_minutes": None,
                "baseline_sleep_minutes": baseline_minutes,
                "recent_14d_avg_minutes": None,
                "debt_trend": "unknown",
                "sleep_balance_score": None,
                "data_quality": "insufficient",
            }

        # 3. 计算加权睡眠债务
        weighted_debt = 0.0
        total_weight = 0.0
        daily_debts = []

        for i, record in enumerate(sleep_records):
            actual_minutes = record.total_sleep_duration / 60
            daily_debt = baseline_minutes - actual_minutes
            daily_debts.append(daily_debt)

            # 权重：最近的天数权重更高（线性递减：1.0 → 0.5）
            # 第0天（今天）权重1.0，第13天权重0.5
            weight = 1.0 - (i * 0.5 / 13)
            weighted_debt += daily_debt * weight
            total_weight += weight

        sleep_debt_minutes = int(weighted_debt / total_weight) if total_weight > 0 else 0

        # 4. 计算最近14天平均睡眠
        recent_avg_minutes = int(
            np.mean([r.total_sleep_duration / 60 for r in sleep_records])
        )

        # 5. 判断债务趋势（对比最近3天 vs 前4-7天）
        if len(sleep_records) >= 7:
            recent_3d = [r.total_sleep_duration / 60 for r in sleep_records[:3]]
            previous_4d = [r.total_sleep_duration / 60 for r in sleep_records[3:7]]
            recent_avg = np.mean(recent_3d)
            previous_avg = np.mean(previous_4d)

            if recent_avg > previous_avg + 15:  # 改善15分钟以上
                debt_trend = "improving"
            elif recent_avg < previous_avg - 15:  # 恶化15分钟以上
                debt_trend = "worsening"
            else:
                debt_trend = "stable"
        else:
            debt_trend = "stable"

        # 6. 计算睡眠平衡评分（0-100）
        # 算法：基于债务程度线性映射
        # -60分钟 → 100分（多睡）
        # 0分钟 → 85分（平衡）
        # +120分钟 → 0分（严重欠债）
        if sleep_debt_minutes <= -60:
            sleep_balance_score = 100
        elif sleep_debt_minutes >= 120:
            sleep_balance_score = 0
        else:
            # 线性映射：-60 → 100, 0 → 85, 120 → 0
            if sleep_debt_minutes <= 0:
                # -60 到 0 映射到 100 到 85
                sleep_balance_score = 85 + int((abs(sleep_debt_minutes) / 60) * 15)
            else:
                # 0 到 120 映射到 85 到 0
                sleep_balance_score = max(0, 85 - int((sleep_debt_minutes / 120) * 85))

        # 7. 数据质量评估
        if len(sleep_records) >= 12:
            data_quality = "good"
        elif len(sleep_records) >= 8:
            data_quality = "moderate"
        else:
            data_quality = "limited"

        result = {
            "sleep_debt_minutes": sleep_debt_minutes,
            "baseline_sleep_minutes": baseline_minutes,
            "recent_14d_avg_minutes": recent_avg_minutes,
            "debt_trend": debt_trend,
            "sleep_balance_score": sleep_balance_score,
            "data_quality": data_quality,
        }

        logger.info(
            f"睡眠债务计算完成: user_id={user_id}, date={target_date}, "
            f"debt={sleep_debt_minutes}min, balance_score={sleep_balance_score}"
        )

        return result

    async def _calculate_baseline_sleep(
        self, user_id: uuid.UUID, target_date: date
    ) -> Optional[int]:
        """
        计算个人睡眠需求基线（过去90天平均，排除异常值）

        异常值定义：
        - 小于3小时（180分钟）
        - 大于12小时（720分钟）
        - 使用四分位数法排除极端值

        返回:
            平均睡眠时长（分钟）
        """
        start_date = target_date - timedelta(days=89)

        result = await self.db.execute(
            select(OuraSleep.total_sleep_duration)
            .where(
                OuraSleep.user_id == user_id,
                OuraSleep.day >= start_date,
                OuraSleep.day <= target_date,
                OuraSleep.total_sleep_duration.isnot(None),
                OuraSleep.total_sleep_duration >= 180 * 60,  # >= 3小时
                OuraSleep.total_sleep_duration <= 720 * 60,  # <= 12小时
            )
        )
        durations = [row[0] / 60 for row in result.all()]  # 转换为分钟

        if len(durations) < 30:  # 至少需要30天数据
            logger.warning(
                f"过去90天睡眠数据不足（需要至少30天）: user_id={user_id}, "
                f"actual={len(durations)}"
            )
            return None

        # 使用四分位数法排除极端值
        q1 = np.percentile(durations, 25)
        q3 = np.percentile(durations, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        filtered_durations = [
            d for d in durations if lower_bound <= d <= upper_bound
        ]

        if len(filtered_durations) < 20:
            logger.warning(
                f"过滤后睡眠数据不足: user_id={user_id}, "
                f"filtered={len(filtered_durations)}"
            )
            # 如果过滤后数据太少，使用未过滤的数据
            filtered_durations = durations

        baseline_minutes = int(np.mean(filtered_durations))

        logger.info(
            f"睡眠基线计算完成: user_id={user_id}, baseline={baseline_minutes}min, "
            f"sample_size={len(filtered_durations)}/{len(durations)}"
        )

        return baseline_minutes

    async def get_sleep_summary(
        self, user_id: uuid.UUID, target_date: Optional[date] = None
    ) -> Optional[dict]:
        """
        获取综合睡眠摘要（包含睡眠债务）

        返回:
            {
                "date": date,
                "total_sleep_hours": float,
                "sleep_score": int,
                "sleep_debt": {...},  # calculate_sleep_debt 的返回值
                "contributors": {...},  # 睡眠贡献因子
                "readiness": {...},  # 嵌入的准备度数据
            }
        """
        if not target_date:
            target_date = today_hk()

        # 获取当日睡眠数据
        result = await self.db.execute(
            select(OuraSleep)
            .where(
                OuraSleep.user_id == user_id,
                OuraSleep.day == target_date,
            )
        )
        sleep = result.scalar_one_or_none()

        if not sleep:
            return None

        # 计算睡眠债务
        sleep_debt = await self.calculate_sleep_debt(user_id, target_date)

        return {
            "date": target_date,
            "total_sleep_hours": sleep.total_sleep_hours,
            "sleep_score": sleep.sleep_score,
            "sleep_debt": sleep_debt,
            "contributors": {
                "total_sleep": sleep.contributor_total_sleep,
                "efficiency": sleep.contributor_efficiency,
                "restfulness": sleep.contributor_restfulness,
                "rem_sleep": sleep.contributor_rem_sleep,
                "deep_sleep": sleep.contributor_deep_sleep,
                "latency": sleep.contributor_latency,
                "timing": sleep.contributor_timing,
            },
            "readiness": {
                "score": sleep.readiness_score_embedded,
                "sleep_balance": sleep.readiness_contributor_sleep_balance,
                "previous_night": sleep.readiness_contributor_previous_night,
                "recovery_index": sleep.readiness_contributor_recovery_index,
                "activity_balance": sleep.readiness_contributor_activity_balance,
                "body_temperature": sleep.readiness_contributor_body_temperature,
                "resting_heart_rate": sleep.readiness_contributor_resting_heart_rate,
                "hrv_balance": sleep.readiness_contributor_hrv_balance,
                "previous_day_activity": sleep.readiness_contributor_previous_day_activity,
                "temperature_deviation": float(sleep.readiness_temperature_deviation)
                if sleep.readiness_temperature_deviation
                else None,
                "temperature_trend_deviation": float(
                    sleep.readiness_temperature_trend_deviation
                )
                if sleep.readiness_temperature_trend_deviation
                else None,
            },
        }
