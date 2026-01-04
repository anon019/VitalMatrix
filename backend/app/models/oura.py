"""
Oura Ring数据模型
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, DECIMAL, TIMESTAMP, ForeignKey, Text, Index, Date, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.database.base import Base


class OuraAuth(Base):
    """Oura授权信息"""

    __tablename__ = "oura_auth"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

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
    user: Mapped["User"] = relationship("User", back_populates="oura_auth")

    def __repr__(self):
        return f"<OuraAuth user_id={self.user_id}>"


class OuraSleep(Base):
    """Oura睡眠数据"""

    __tablename__ = "oura_sleep"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="睡眠日期")

    # 睡眠时间
    bedtime_start: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), comment="入睡时间"
    )
    bedtime_end: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), comment="起床时间"
    )

    # 睡眠时长（秒）
    total_sleep_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="总睡眠时长(秒)"
    )
    deep_sleep_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="深睡时长(秒)"
    )
    light_sleep_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="浅睡时长(秒)"
    )
    rem_sleep_duration: Mapped[Optional[int]] = mapped_column(
        Integer, comment="REM时长(秒)"
    )
    awake_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="清醒时长(秒)"
    )

    # 心率数据
    average_heart_rate: Mapped[Optional[int]] = mapped_column(
        Integer, comment="平均心率"
    )
    lowest_heart_rate: Mapped[Optional[int]] = mapped_column(
        Integer, comment="最低心率"
    )

    # HRV（核心恢复指标）
    average_hrv: Mapped[Optional[int]] = mapped_column(
        Integer, comment="平均HRV(ms)"
    )

    # 呼吸与血氧
    average_breath: Mapped[Optional[float]] = mapped_column(
        DECIMAL(4, 2), comment="平均呼吸频率"
    )
    spo2_percentage: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="血氧饱和度(%)"
    )

    # 体温偏差
    temperature_deviation: Mapped[Optional[float]] = mapped_column(
        DECIMAL(4, 2), comment="体温偏差(°C)"
    )

    # 睡眠评分
    sleep_score: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠评分(0-100)"
    )

    # 效率
    efficiency: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠效率(%)"
    )

    # 睡眠贡献因子评分 (Summary.Contributors)
    contributor_total_sleep: Mapped[Optional[int]] = mapped_column(
        Integer, comment="总睡眠时长贡献分(0-100)"
    )
    contributor_efficiency: Mapped[Optional[int]] = mapped_column(
        Integer, comment="效率贡献分(0-100)"
    )
    contributor_restfulness: Mapped[Optional[int]] = mapped_column(
        Integer, comment="安稳度贡献分(0-100)"
    )
    contributor_rem_sleep: Mapped[Optional[int]] = mapped_column(
        Integer, comment="REM睡眠贡献分(0-100)"
    )
    contributor_deep_sleep: Mapped[Optional[int]] = mapped_column(
        Integer, comment="深睡贡献分(0-100)"
    )
    contributor_latency: Mapped[Optional[int]] = mapped_column(
        Integer, comment="入睡延迟贡献分(0-100)"
    )
    contributor_timing: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠时间贡献分(0-100)"
    )

    # Detail 字段
    sleep_type: Mapped[Optional[str]] = mapped_column(
        String(20), comment="睡眠类型(long_sleep/nap)"
    )
    time_in_bed: Mapped[Optional[int]] = mapped_column(
        Integer, comment="在床时间(秒)"
    )
    latency: Mapped[Optional[int]] = mapped_column(
        Integer, comment="入睡延迟(秒)"
    )
    restless_periods: Mapped[Optional[int]] = mapped_column(
        Integer, comment="躁动次数"
    )

    # 评分增量（午睡/小憩对当日总评分的贡献）
    sleep_score_delta: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠评分增量(午睡贡献,如+9)"
    )
    readiness_score_delta: Mapped[Optional[int]] = mapped_column(
        Integer, comment="准备度评分增量(午睡贡献)"
    )

    # Detail.Readiness (嵌入的准备度数据)
    readiness_score_embedded: Mapped[Optional[int]] = mapped_column(
        Integer, comment="嵌入的准备度评分(0-100)"
    )
    readiness_contributor_sleep_balance: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠平衡评分(0-100，睡眠债务指标)"
    )
    readiness_contributor_previous_night: Mapped[Optional[int]] = mapped_column(
        Integer, comment="前夜睡眠评分(0-100)"
    )
    readiness_contributor_recovery_index: Mapped[Optional[int]] = mapped_column(
        Integer, comment="恢复指数(0-100)"
    )
    readiness_contributor_activity_balance: Mapped[Optional[int]] = mapped_column(
        Integer, comment="活动平衡评分(0-100)"
    )
    readiness_contributor_body_temperature: Mapped[Optional[int]] = mapped_column(
        Integer, comment="体温评分(0-100)"
    )
    readiness_contributor_resting_heart_rate: Mapped[Optional[int]] = mapped_column(
        Integer, comment="静息心率评分(0-100)"
    )
    readiness_contributor_hrv_balance: Mapped[Optional[int]] = mapped_column(
        Integer, comment="HRV平衡评分(0-100)"
    )
    readiness_contributor_previous_day_activity: Mapped[Optional[int]] = mapped_column(
        Integer, comment="前日活动评分(0-100)"
    )
    readiness_temperature_deviation: Mapped[Optional[float]] = mapped_column(
        DECIMAL(4, 2), comment="体温偏差(°C)"
    )
    readiness_temperature_trend_deviation: Mapped[Optional[float]] = mapped_column(
        DECIMAL(4, 2), comment="体温趋势偏差(°C)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_sleep_records")

    __table_args__ = (Index("idx_oura_sleep_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraSleep {self.day} score={self.sleep_score}>"

    @property
    def total_sleep_hours(self) -> float:
        """总睡眠小时数"""
        if self.total_sleep_duration:
            return self.total_sleep_duration / 3600
        return 0.0

    @property
    def deep_sleep_ratio(self) -> float:
        """深睡占比"""
        if self.total_sleep_duration and self.deep_sleep_duration:
            return self.deep_sleep_duration / self.total_sleep_duration
        return 0.0


class OuraDailySleep(Base):
    """Oura每日睡眠综合评分

    存储 Oura daily_sleep API 的综合评分数据。
    与 OuraSleep（单次睡眠记录）不同，这里存储的是每日的综合评分。
    即使没有主睡眠(long_sleep)，也会有综合评分。
    """

    __tablename__ = "oura_daily_sleep"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # 综合睡眠评分（核心指标）
    score: Mapped[Optional[int]] = mapped_column(
        Integer, comment="每日综合睡眠评分(0-100)"
    )

    # 贡献因子（来自 contributors 字段）
    contributor_deep_sleep: Mapped[Optional[int]] = mapped_column(
        Integer, comment="深睡贡献分数"
    )
    contributor_efficiency: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠效率贡献分数"
    )
    contributor_latency: Mapped[Optional[int]] = mapped_column(
        Integer, comment="入睡延迟贡献分数"
    )
    contributor_rem_sleep: Mapped[Optional[int]] = mapped_column(
        Integer, comment="REM睡眠贡献分数"
    )
    contributor_restfulness: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠安稳度贡献分数"
    )
    contributor_timing: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠时间贡献分数"
    )
    contributor_total_sleep: Mapped[Optional[int]] = mapped_column(
        Integer, comment="总睡眠时长贡献分数"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_daily_sleep_records")

    __table_args__ = (Index("idx_oura_daily_sleep_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraDailySleep {self.day} score={self.score}>"


class OuraDailyReadiness(Base):
    """Oura每日准备度"""

    __tablename__ = "oura_daily_readiness"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # 准备度评分（核心指标）
    score: Mapped[Optional[int]] = mapped_column(
        Integer, comment="准备度评分(0-100)"
    )

    # 贡献因子
    temperature_deviation: Mapped[Optional[float]] = mapped_column(
        DECIMAL(4, 2), comment="体温偏差"
    )
    temperature_trend_deviation: Mapped[Optional[float]] = mapped_column(
        DECIMAL(4, 2), comment="体温趋势偏差"
    )
    activity_balance: Mapped[Optional[int]] = mapped_column(
        Integer, comment="活动平衡分数"
    )
    sleep_balance: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠平衡分数"
    )
    previous_night: Mapped[Optional[int]] = mapped_column(
        Integer, comment="前夜睡眠分数"
    )
    previous_day_activity: Mapped[Optional[int]] = mapped_column(
        Integer, comment="前日活动分数"
    )
    recovery_index: Mapped[Optional[int]] = mapped_column(
        Integer, comment="恢复指数"
    )
    resting_heart_rate: Mapped[Optional[int]] = mapped_column(
        Integer, comment="静息心率评分(0-100，非实际BPM)"
    )
    hrv_balance: Mapped[Optional[int]] = mapped_column(
        Integer, comment="HRV平衡分数"
    )
    body_temperature: Mapped[Optional[int]] = mapped_column(
        Integer, comment="体温分数"
    )
    sleep_regularity: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠规律性分数(0-100)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_readiness_records")

    __table_args__ = (Index("idx_oura_readiness_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraDailyReadiness {self.day} score={self.score}>"


class OuraDailyActivity(Base):
    """Oura每日活动数据"""

    __tablename__ = "oura_daily_activity"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # 活动评分
    score: Mapped[Optional[int]] = mapped_column(
        Integer, comment="活动评分(0-100)"
    )

    # 活动数据
    active_calories: Mapped[Optional[int]] = mapped_column(
        Integer, comment="活动消耗(千卡/kcal)"
    )
    total_calories: Mapped[Optional[int]] = mapped_column(
        Integer, comment="总消耗(千卡/kcal)"
    )
    steps: Mapped[Optional[int]] = mapped_column(
        Integer, comment="步数"
    )
    equivalent_walking_distance: Mapped[Optional[int]] = mapped_column(
        Integer, comment="等效步行距离(米)"
    )

    # 活动时长（分钟）
    high_activity_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="高强度活动时长(分钟)"
    )
    medium_activity_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="中强度活动时长(分钟)"
    )
    low_activity_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="低强度活动时长(分钟)"
    )
    sedentary_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="久坐时长(分钟)"
    )
    resting_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="休息时长(分钟)"
    )

    # 活动目标
    target_calories: Mapped[Optional[int]] = mapped_column(
        Integer, comment="目标卡路里"
    )
    target_meters: Mapped[Optional[int]] = mapped_column(
        Integer, comment="目标距离(米)"
    )

    # 活动贡献因子评分 (Contributors)
    contributor_stay_active: Mapped[Optional[int]] = mapped_column(
        Integer, comment="保持活跃评分(0-100)"
    )
    contributor_recovery_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="恢复时间评分(0-100)"
    )
    contributor_move_every_hour: Mapped[Optional[int]] = mapped_column(
        Integer, comment="每小时移动评分(0-100)"
    )
    contributor_training_volume: Mapped[Optional[int]] = mapped_column(
        Integer, comment="训练量评分(0-100)"
    )
    contributor_training_frequency: Mapped[Optional[int]] = mapped_column(
        Integer, comment="训练频率评分(0-100)"
    )
    contributor_meet_daily_targets: Mapped[Optional[int]] = mapped_column(
        Integer, comment="达成每日目标评分(0-100)"
    )

    # 其他活动指标
    non_wear_time: Mapped[Optional[int]] = mapped_column(
        Integer, comment="未佩戴时间(秒)"
    )
    meters_to_target: Mapped[Optional[int]] = mapped_column(
        Integer, comment="距离目标(米)"
    )
    inactivity_alerts: Mapped[Optional[int]] = mapped_column(
        Integer, comment="久坐提醒次数"
    )
    average_met_minutes: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 4), comment="平均MET分钟"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_activity_records")

    __table_args__ = (Index("idx_oura_activity_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraDailyActivity {self.day} steps={self.steps}>"


class OuraDailyStress(Base):
    """Oura每日压力数据"""

    __tablename__ = "oura_daily_stress"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # 压力数据
    stress_high: Mapped[Optional[int]] = mapped_column(
        Integer, comment="高压力时长(秒)"
    )
    recovery_high: Mapped[Optional[int]] = mapped_column(
        Integer, comment="高恢复时长(秒)"
    )
    day_summary: Mapped[Optional[str]] = mapped_column(
        String(50), comment="日间压力总结"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_stress_records")

    __table_args__ = (Index("idx_oura_stress_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraDailyStress {self.day}>"


class OuraDailySpo2(Base):
    """Oura每日血氧数据"""

    __tablename__ = "oura_daily_spo2"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # 血氧数据
    spo2_percentage: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="平均血氧(%)"
    )
    breathing_disturbance_index: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="呼吸紊乱指数"
    )
    breathing_regularity: Mapped[Optional[int]] = mapped_column(
        Integer, comment="呼吸规律性评分(0-100)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_spo2_records")

    __table_args__ = (Index("idx_oura_spo2_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraDailySpo2 {self.day} spo2={self.spo2_percentage}>"


class OuraCardiovascularAge(Base):
    """Oura心血管年龄数据"""

    __tablename__ = "oura_cardiovascular_age"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # 心血管年龄
    vascular_age: Mapped[Optional[int]] = mapped_column(
        Integer, comment="血管年龄(岁)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_cardiovascular_age_records")

    __table_args__ = (Index("idx_oura_cv_age_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraCardiovascularAge {self.day} age={self.vascular_age}>"


class OuraResilience(Base):
    """Oura韧性/恢复力数据"""

    __tablename__ = "oura_resilience"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # 韧性评分
    level: Mapped[Optional[str]] = mapped_column(
        String(50), comment="韧性等级(limited/adequate/solid/strong)"
    )

    # 贡献因子
    sleep_recovery: Mapped[Optional[int]] = mapped_column(
        Integer, comment="睡眠恢复贡献(0-100)"
    )
    daytime_recovery: Mapped[Optional[int]] = mapped_column(
        Integer, comment="日间恢复贡献(0-100)"
    )
    stress: Mapped[Optional[int]] = mapped_column(
        Integer, comment="压力评分(0-100)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_resilience_records")

    __table_args__ = (Index("idx_oura_resilience_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraResilience {self.day} level={self.level}>"


class OuraVO2Max(Base):
    """Oura VO2 Max数据"""

    __tablename__ = "oura_vo2_max"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Oura原始标识
    oura_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, comment="Oura唯一ID"
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, comment="日期")

    # VO2 Max值
    vo2_max: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2), comment="VO2 Max(ml/kg/min)"
    )

    # 原始JSON数据
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, comment="完整原始数据")

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="oura_vo2_max_records")

    __table_args__ = (Index("idx_oura_vo2_max_user_day", "user_id", "day"),)

    def __repr__(self):
        return f"<OuraVO2Max {self.day} vo2_max={self.vo2_max}>"


# 注意: OuraDailyHeartRate 模型已移除
# 方案A: 使用现有 sleep 表的 lowest_heart_rate/average_heart_rate 字段
# 如需活动心率数据，可从 Oura heartrate API 聚合（暂不实现）
