"""
Polar数据模型
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, DECIMAL, TIMESTAMP, ForeignKey, Text, Index, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.database.base import Base


class PolarAuth(Base):
    """Polar授权信息"""

    __tablename__ = "polar_auth"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    polar_user_id: Mapped[Optional[str]] = mapped_column(String(100), comment="Polar用户ID")

    # OAuth令牌
    access_token: Mapped[Optional[str]] = mapped_column(Text, comment="访问令牌")
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, comment="刷新令牌")
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), comment="令牌过期时间"
    )

    # 授权状态
    is_active: Mapped[bool] = mapped_column(default=True, comment="是否激活")
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), comment="最后同步时间"
    )

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="polar_auth")

    def __repr__(self):
        return f"<PolarAuth user_id={self.user_id}>"


class PolarExercise(Base):
    """Polar训练记录"""

    __tablename__ = "polar_exercises"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Polar原始数据
    exercise_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Polar唯一ID"
    )
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    sport_type: Mapped[Optional[str]] = mapped_column(String(50), comment="运动类型")

    # 基础指标
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, comment="总时长(秒)")
    avg_hr: Mapped[Optional[int]] = mapped_column(Integer, comment="平均心率")
    max_hr: Mapped[Optional[int]] = mapped_column(Integer, comment="最大心率")

    # 心率区间时长（核心数据）
    zone1_sec: Mapped[int] = mapped_column(Integer, default=0, comment="Zone1时长(秒)")
    zone2_sec: Mapped[int] = mapped_column(Integer, default=0, comment="Zone2时长(秒)")
    zone3_sec: Mapped[int] = mapped_column(Integer, default=0, comment="Zone3时长(秒)")
    zone4_sec: Mapped[int] = mapped_column(Integer, default=0, comment="Zone4时长(秒)")
    zone5_sec: Mapped[int] = mapped_column(Integer, default=0, comment="Zone5时长(秒)")

    # 心率区间边界（来自Polar API）
    zone1_lower: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone1下限心率(bpm)")
    zone1_upper: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone1上限心率(bpm)")
    zone2_lower: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone2下限心率(bpm)")
    zone2_upper: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone2上限心率(bpm)")
    zone3_lower: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone3下限心率(bpm)")
    zone3_upper: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone3上限心率(bpm)")
    zone4_lower: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone4下限心率(bpm)")
    zone4_upper: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone4上限心率(bpm)")
    zone5_lower: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone5下限心率(bpm)")
    zone5_upper: Mapped[Optional[int]] = mapped_column(Integer, comment="Zone5上限心率(bpm)")

    # 其他指标
    calories: Mapped[Optional[int]] = mapped_column(Integer, comment="消耗卡路里")
    cardio_load: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="Polar训练负荷（保留两位小数）"
    )
    distance_meters: Mapped[Optional[float]] = mapped_column(
        DECIMAL(10, 2), comment="距离(米)"
    )

    # 原始JSON数据（用于调试和未来扩展）
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="exercises")

    __table_args__ = (Index("idx_user_start_time", "user_id", "start_time"),)

    def __repr__(self):
        return f"<PolarExercise {self.sport_type} at {self.start_time}>"

    @property
    def zone2_min(self) -> int:
        """Zone2分钟数"""
        return self.zone2_sec // 60

    @property
    def hi_min(self) -> int:
        """高强度分钟数（Zone4+5）"""
        return (self.zone4_sec + self.zone5_sec) // 60

    @property
    def zone2_ratio(self) -> float:
        """Zone2占比"""
        if self.duration_sec == 0:
            return 0.0
        return self.zone2_sec / self.duration_sec

    @property
    def hi_ratio(self) -> float:
        """高强度占比"""
        if self.duration_sec == 0:
            return 0.0
        return (self.zone4_sec + self.zone5_sec) / self.duration_sec


class PolarSleep(Base):
    """Polar睡眠数据"""

    __tablename__ = "polar_sleep"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Polar原始数据
    polar_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Polar睡眠唯一ID"
    )
    sleep_date: Mapped[date] = mapped_column(Date, nullable=False, comment="睡眠日期")
    sleep_start_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, comment="入睡时间"
    )
    sleep_end_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, comment="醒来时间"
    )

    # 睡眠阶段时长(秒)
    deep_sleep_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="深睡时长(秒)"
    )
    light_sleep_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="浅睡时长(秒)"
    )
    rem_sleep_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="REM睡眠时长(秒)"
    )
    total_interruption_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="总中断时长(秒)"
    )

    # 睡眠质量指标
    sleep_score: Mapped[Optional[int]] = mapped_column(Integer, comment="睡眠评分(0-100)")
    continuity: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="睡眠连续性"
    )
    continuity_class: Mapped[Optional[int]] = mapped_column(
        Integer, comment="连续性分类(1-5)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="polar_sleep_records")

    __table_args__ = (Index("idx_polar_sleep_user_date", "user_id", "sleep_date"),)

    def __repr__(self):
        return f"<PolarSleep {self.sleep_date}>"


class PolarNightlyRecharge(Base):
    """Polar夜间恢复数据"""

    __tablename__ = "polar_nightly_recharge"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Polar原始数据
    polar_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Polar夜间恢复唯一ID"
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # ANS恢复指标(自主神经系统)
    ans_charge: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="ANS恢复评分(0-100)"
    )
    ans_charge_status: Mapped[Optional[int]] = mapped_column(
        Integer, comment="ANS状态(1-7: compromised到完全恢复)"
    )
    hrv_avg: Mapped[Optional[int]] = mapped_column(Integer, comment="平均HRV(ms)")
    breathing_rate_avg: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="平均呼吸频率(次/分)"
    )
    heart_rate_avg: Mapped[Optional[int]] = mapped_column(Integer, comment="平均心率(bpm)")
    rmssd: Mapped[Optional[int]] = mapped_column(Integer, comment="RMSSD(ms)")

    # 睡眠恢复指标
    sleep_charge: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="睡眠恢复评分(0-100)"
    )
    sleep_charge_status: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠状态(1-7)"
    )
    sleep_score: Mapped[Optional[int]] = mapped_column(Integer, comment="睡眠评分(0-100)")

    # Nightly Recharge总分
    nightly_recharge_status: Mapped[Optional[int]] = mapped_column(
        Integer, comment="总体恢复状态(1-7)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="polar_nightly_recharge_records")

    __table_args__ = (Index("idx_polar_recharge_user_date", "user_id", "date"),)

    def __repr__(self):
        return f"<PolarNightlyRecharge {self.date}>"
