"""
训练数据模型
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, DECIMAL, TIMESTAMP, ForeignKey, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.database.base import Base


class DailyTrainingSummary(Base):
    """日训练总结"""

    __tablename__ = "daily_training_summary"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, comment="训练日期")

    # 聚合指标
    total_duration_min: Mapped[int] = mapped_column(Integer, default=0, comment="总时长(分钟)")
    zone2_min: Mapped[int] = mapped_column(Integer, default=0, comment="Zone2时长(分钟)")
    hi_min: Mapped[int] = mapped_column(Integer, default=0, comment="高强度时长(分钟)")
    trimp: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0, comment="训练负荷")

    sessions_count: Mapped[int] = mapped_column(Integer, default=0, comment="训练次数")
    total_calories: Mapped[Optional[int]] = mapped_column(Integer, comment="总卡路里")
    avg_hr: Mapped[Optional[int]] = mapped_column(Integer, comment="平均心率")

    # 风险标记
    flags: Mapped[Optional[dict]] = mapped_column(JSONB, comment="风险标记")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="daily_summaries")

    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

    def __repr__(self):
        return f"<DailyTrainingSummary {self.date} Zone2={self.zone2_min}min HI={self.hi_min}min>"


class WeeklyTrainingSummary(Base):
    """周训练总结"""

    __tablename__ = "weekly_training_summary"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    week_start_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="周起始日期(周一)"
    )

    # 周聚合指标
    total_duration_min: Mapped[int] = mapped_column(Integer, default=0, comment="周总时长(分钟)")
    zone2_min: Mapped[int] = mapped_column(Integer, default=0, comment="周Zone2时长(分钟)")
    hi_min: Mapped[int] = mapped_column(Integer, default=0, comment="周高强度时长(分钟)")
    weekly_trimp: Mapped[float] = mapped_column(DECIMAL(10, 2), default=0, comment="周训练负荷")

    training_days: Mapped[int] = mapped_column(Integer, default=0, comment="训练天数")
    rest_days: Mapped[int] = mapped_column(Integer, default=0, comment="休息天数")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="weekly_summaries")

    __table_args__ = (UniqueConstraint("user_id", "week_start_date", name="uq_user_week"),)

    def __repr__(self):
        return f"<WeeklyTrainingSummary week={self.week_start_date} days={self.training_days}>"
