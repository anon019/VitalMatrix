"""
训练数据Schemas
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field


class ZoneMetrics(BaseModel):
    """Zone指标"""

    zone2_min: int = Field(..., description="Zone2分钟数")
    zone2_ratio: float = Field(..., description="Zone2占比")
    hi_min: int = Field(..., description="高强度分钟数")
    hi_ratio: float = Field(..., description="高强度占比")


class ExerciseResponse(BaseModel):
    """训练记录响应"""

    id: str
    start_time: datetime
    end_time: datetime
    sport_type: Optional[str]
    duration_sec: int
    avg_hr: Optional[int]
    max_hr: Optional[int]
    zone1_sec: int
    zone2_sec: int
    zone3_sec: int
    zone4_sec: int
    zone5_sec: int
    # 心率区间边界
    zone1_lower: Optional[int] = Field(None, description="Zone1下限心率(bpm)")
    zone1_upper: Optional[int] = Field(None, description="Zone1上限心率(bpm)")
    zone2_lower: Optional[int] = Field(None, description="Zone2下限心率(bpm)")
    zone2_upper: Optional[int] = Field(None, description="Zone2上限心率(bpm)")
    zone3_lower: Optional[int] = Field(None, description="Zone3下限心率(bpm)")
    zone3_upper: Optional[int] = Field(None, description="Zone3上限心率(bpm)")
    zone4_lower: Optional[int] = Field(None, description="Zone4下限心率(bpm)")
    zone4_upper: Optional[int] = Field(None, description="Zone4上限心率(bpm)")
    zone5_lower: Optional[int] = Field(None, description="Zone5下限心率(bpm)")
    zone5_upper: Optional[int] = Field(None, description="Zone5上限心率(bpm)")
    calories: Optional[int]
    cardio_load: Optional[float] = Field(None, description="Polar训练负荷（DECIMAL 5,2）")
    distance_meters: Optional[float]

    # 计算字段
    zone2_min: int
    hi_min: int
    zone2_ratio: float
    hi_ratio: float

    class Config:
        from_attributes = True


class DailySummaryResponse(BaseModel):
    """日总结响应"""

    date: date
    total_duration_min: int
    zone2_min: int
    hi_min: int
    trimp: float
    sessions_count: int
    total_calories: Optional[int]
    avg_hr: Optional[int]
    flags: Optional[dict]

    class Config:
        from_attributes = True


class WeeklySummaryResponse(BaseModel):
    """周总结响应"""

    week_start_date: date
    total_duration_min: int
    zone2_min: int
    hi_min: int
    weekly_trimp: float
    training_days: int
    rest_days: int

    class Config:
        from_attributes = True


class TrainingHistoryResponse(BaseModel):
    """训练历史响应"""

    exercises: List[ExerciseResponse]
    total_count: int
    page: int
    page_size: int
