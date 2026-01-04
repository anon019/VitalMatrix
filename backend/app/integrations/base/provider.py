"""
数据源Provider抽象接口
"""
from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel
import uuid


class AuthResult(BaseModel):
    """授权结果"""

    success: bool
    user_id: Optional[uuid.UUID] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    error_message: Optional[str] = None


class TrainingSession(BaseModel):
    """训练会话（通用格式）"""

    external_id: str  # 外部系统ID
    start_time: datetime
    end_time: datetime
    sport_type: Optional[str]
    duration_sec: int
    avg_hr: Optional[int]
    max_hr: Optional[int]
    # 心率区间时长
    zone1_sec: int = 0
    zone2_sec: int = 0
    zone3_sec: int = 0
    zone4_sec: int = 0
    zone5_sec: int = 0
    # 心率区间边界（来自Polar API）
    zone1_lower: Optional[int] = None
    zone1_upper: Optional[int] = None
    zone2_lower: Optional[int] = None
    zone2_upper: Optional[int] = None
    zone3_lower: Optional[int] = None
    zone3_upper: Optional[int] = None
    zone4_lower: Optional[int] = None
    zone4_upper: Optional[int] = None
    zone5_lower: Optional[int] = None
    zone5_upper: Optional[int] = None
    calories: Optional[int]
    distance_meters: Optional[float]
    raw_data: Optional[dict]  # 原始数据


class SleepSession(BaseModel):
    """睡眠会话（通用格式）"""

    external_id: str
    start_time: datetime
    end_time: datetime
    total_sleep_min: int
    deep_sleep_min: Optional[int]
    rem_sleep_min: Optional[int]
    light_sleep_min: Optional[int]
    sleep_score: Optional[int]
    raw_data: Optional[dict]


class DataSourceProvider(ABC):
    """数据源提供商抽象接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""
        pass

    @abstractmethod
    async def authorize(self, user_id: uuid.UUID, auth_code: str) -> AuthResult:
        """
        授权流程

        Args:
            user_id: 用户ID
            auth_code: 授权码

        Returns:
            授权结果
        """
        pass

    @abstractmethod
    async def refresh_token(self, user_id: uuid.UUID) -> AuthResult:
        """
        刷新访问令牌

        Args:
            user_id: 用户ID

        Returns:
            新的授权结果
        """
        pass

    @abstractmethod
    async def fetch_training_data(
        self, user_id: uuid.UUID, start_date: date, end_date: date
    ) -> List[TrainingSession]:
        """
        拉取训练数据

        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            训练会话列表
        """
        pass

    @abstractmethod
    async def fetch_sleep_data(
        self, user_id: uuid.UUID, start_date: date, end_date: date
    ) -> List[SleepSession]:
        """
        拉取睡眠数据

        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            睡眠会话列表
        """
        pass

    @abstractmethod
    async def check_connection(self, user_id: uuid.UUID) -> bool:
        """
        检查连接状态

        Args:
            user_id: 用户ID

        Returns:
            是否连接正常
        """
        pass
