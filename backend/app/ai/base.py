"""
AI Provider抽象接口
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class Message(BaseModel):
    """聊天消息"""
    role: str  # user, assistant, system
    content: str


class UserContext(BaseModel):
    """用户上下文"""
    user_id: str
    nickname: Optional[str] = None
    health_goal: str
    training_plan: str
    hr_max: Optional[int] = None
    resting_hr: Optional[int] = None
    weight: Optional[float] = None  # kg
    height: Optional[int] = None  # cm
    age: Optional[int] = None  # 年龄


class OuraData(BaseModel):
    """Oura数据（睡眠、准备度、压力）"""
    # 睡眠数据
    sleep_score: Optional[int] = None
    total_sleep_hours: Optional[float] = None
    deep_sleep_min: Optional[int] = None
    rem_sleep_min: Optional[int] = None
    sleep_efficiency: Optional[int] = None
    average_hrv: Optional[int] = None

    # 准备度数据
    readiness_score: Optional[int] = None
    recovery_index: Optional[int] = None
    resting_heart_rate: Optional[int] = None  # 睡眠期间最低心率(BPM)，代表静息心率
    hrv_balance: Optional[int] = None  # HRV平衡评分(0-100)

    # 压力数据
    stress_high_min: Optional[int] = None  # 高压力时长（分钟）
    recovery_high_min: Optional[int] = None  # 高恢复时长（分钟）
    day_summary: Optional[str] = None

    # 活动数据
    activity_score: Optional[int] = None
    steps: Optional[int] = None
    active_calories: Optional[int] = None


class TrainingData(BaseModel):
    """训练数据"""
    # 昨日数据
    zone2_min: int
    hi_min: int
    total_duration_min: int
    trimp: float
    avg_hr: Optional[int]
    sport_type: Optional[str]

    # 周数据
    weekly_zone2: int
    weekly_hi: int
    weekly_total: int
    weekly_trimp: float
    training_days: int
    rest_days: int

    # 风险标记
    flags: Dict[str, bool]

    # Oura数据（可选）
    oura_data: Optional[OuraData] = None


class Recommendation(BaseModel):
    """AI建议（新结构）"""
    summary: str
    yesterday_review: Dict[str, Any]  # 昨日评价（JSON结构）
    today_recommendation: Dict[str, Any]  # 今日建议（JSON结构）
    health_education: Dict[str, Any]  # 健康科普（JSON结构）

    # Token使用
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    """聊天响应"""
    message: str
    usage: Optional[Dict[str, int]] = None


class AIProvider(ABC):
    """AI服务提供商抽象接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """模型名称"""
        pass

    @abstractmethod
    async def generate_recommendation(
        self,
        user_context: UserContext,
        training_data: TrainingData,
        date: str,
    ) -> Recommendation:
        """
        生成训练建议

        Args:
            user_context: 用户上下文
            training_data: 训练数据
            date: 日期

        Returns:
            AI建议
        """
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        context: Optional[Dict[str, Any]] = None
    ) -> ChatResponse:
        """
        对话接口

        Args:
            messages: 消息历史
            context: 上下文数据（可选）

        Returns:
            AI回复
        """
        pass

    @abstractmethod
    async def close(self):
        """关闭客户端连接"""
        pass
