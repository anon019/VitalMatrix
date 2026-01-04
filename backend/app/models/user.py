"""
用户模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, DECIMAL, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.polar import PolarAuth, PolarExercise, PolarSleep, PolarNightlyRecharge
    from app.models.oura import (
        OuraAuth, OuraSleep, OuraDailyReadiness,
        OuraDailyActivity, OuraDailyStress, OuraDailySpo2,
        OuraCardiovascularAge, OuraResilience, OuraVO2Max
    )
    from app.models.training import DailyTrainingSummary, WeeklyTrainingSummary
    from app.models.ai import AIRecommendation
    from app.models.health_report import HealthReport
    from app.models.nutrition import MealRecord, NutritionDailySummary


class User(Base):
    """用户表"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    openid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(100))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    # 体能基础数据（可手动覆盖Polar值）
    hr_max: Mapped[Optional[int]] = mapped_column(Integer, comment="最大心率")
    resting_hr: Mapped[Optional[int]] = mapped_column(Integer, comment="静息心率")
    weight: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2), comment="体重(kg)")
    height: Mapped[Optional[int]] = mapped_column(Integer, comment="身高(cm)")
    birth_year: Mapped[Optional[int]] = mapped_column(Integer, comment="出生年份")

    # 用户设置
    health_goal: Mapped[Optional[str]] = mapped_column(
        String(500), default="降脂心血管健康优化", comment="健康目标"
    )
    training_plan: Mapped[Optional[str]] = mapped_column(
        String(200), default="Zone2 55分钟 + Zone4-5 2分钟", comment="训练方案"
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关联关系 - Polar
    polar_auth: Mapped[Optional["PolarAuth"]] = relationship(
        "PolarAuth", back_populates="user", uselist=False
    )
    exercises: Mapped[List["PolarExercise"]] = relationship(
        "PolarExercise", back_populates="user"
    )
    polar_sleep_records: Mapped[List["PolarSleep"]] = relationship(
        "PolarSleep", back_populates="user"
    )
    polar_nightly_recharge_records: Mapped[List["PolarNightlyRecharge"]] = relationship(
        "PolarNightlyRecharge", back_populates="user"
    )

    # 关联关系 - Oura
    oura_auth: Mapped[Optional["OuraAuth"]] = relationship(
        "OuraAuth", back_populates="user", uselist=False
    )
    oura_sleep_records: Mapped[List["OuraSleep"]] = relationship(
        "OuraSleep", back_populates="user"
    )
    oura_daily_sleep_records: Mapped[List["OuraDailySleep"]] = relationship(
        "OuraDailySleep", back_populates="user"
    )
    oura_readiness_records: Mapped[List["OuraDailyReadiness"]] = relationship(
        "OuraDailyReadiness", back_populates="user"
    )
    oura_activity_records: Mapped[List["OuraDailyActivity"]] = relationship(
        "OuraDailyActivity", back_populates="user"
    )
    oura_stress_records: Mapped[List["OuraDailyStress"]] = relationship(
        "OuraDailyStress", back_populates="user"
    )
    oura_spo2_records: Mapped[List["OuraDailySpo2"]] = relationship(
        "OuraDailySpo2", back_populates="user"
    )
    oura_cardiovascular_age_records: Mapped[List["OuraCardiovascularAge"]] = relationship(
        "OuraCardiovascularAge", back_populates="user"
    )
    oura_resilience_records: Mapped[List["OuraResilience"]] = relationship(
        "OuraResilience", back_populates="user"
    )
    oura_vo2_max_records: Mapped[List["OuraVO2Max"]] = relationship(
        "OuraVO2Max", back_populates="user"
    )

    # 关联关系 - 训练汇总
    daily_summaries: Mapped[List["DailyTrainingSummary"]] = relationship(
        "DailyTrainingSummary", back_populates="user"
    )
    weekly_summaries: Mapped[List["WeeklyTrainingSummary"]] = relationship(
        "WeeklyTrainingSummary", back_populates="user"
    )
    ai_recommendations: Mapped[List["AIRecommendation"]] = relationship(
        "AIRecommendation", back_populates="user"
    )

    # 关联关系 - 健康报告
    health_reports: Mapped[List["HealthReport"]] = relationship(
        "HealthReport", back_populates="user"
    )

    # 关联关系 - 营养饮食
    meal_records: Mapped[List["MealRecord"]] = relationship(
        "MealRecord", back_populates="user"
    )
    nutrition_daily_summaries: Mapped[List["NutritionDailySummary"]] = relationship(
        "NutritionDailySummary", back_populates="user"
    )

    def __repr__(self):
        return f"<User {self.nickname or self.openid}>"
