"""
营养模块的Pydantic Schemas
"""
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer
from enum import Enum
import uuid

from app.utils.media_url import create_signed_media_url
from app.config import settings
from app.utils.datetime_helper import ensure_hk


class MealTypeEnum(str, Enum):
    """餐次类型枚举"""
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class FoodCategoryEnum(str, Enum):
    """食物分类枚举"""
    STAPLE = "staple"
    PROTEIN = "protein"
    VEGETABLE = "vegetable"
    FRUIT = "fruit"
    DAIRY = "dairy"
    FAT = "fat"
    BEVERAGE = "beverage"
    SNACK = "snack"
    OTHER = "other"


# ===== 食物项Schema =====

class FoodItemBase(BaseModel):
    """食物项基础Schema"""
    food_name: str = Field(..., description="食物名称")
    category: Optional[FoodCategoryEnum] = Field(None, description="食物分类")
    estimated_weight: Optional[float] = Field(None, description="估计重量(g)")
    calories: Optional[float] = Field(None, description="热量(kcal)")
    protein: Optional[float] = Field(None, description="蛋白质(g)")
    carbs: Optional[float] = Field(None, description="碳水化合物(g)")
    fat: Optional[float] = Field(None, description="脂肪(g)")
    fiber: Optional[float] = Field(None, description="膳食纤维(g)")
    sodium: Optional[float] = Field(None, description="钠(mg)")
    sugar: Optional[float] = Field(None, description="糖分(g)")
    notes: Optional[str] = Field(None, description="备注")


class FoodItemCreate(FoodItemBase):
    """创建食物项Schema"""
    pass


class FoodItemResponse(FoodItemBase):
    """食物项响应Schema"""
    id: uuid.UUID
    meal_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== 餐次记录Schema =====

class MealRecordBase(BaseModel):
    """餐次记录基础Schema"""
    meal_type: MealTypeEnum = Field(..., description="餐次类型")
    meal_time: datetime = Field(..., description="用餐时间")
    notes: Optional[str] = Field(None, description="用户备注")


class MealRecordCreate(MealRecordBase):
    """创建餐次记录Schema（用于确认保存）"""
    ai_analysis: Dict[str, Any] = Field(..., description="AI完整分析结果")
    food_items: List[FoodItemCreate] = Field(..., description="食物明细列表")


class MealRecordResponse(MealRecordBase):
    """餐次记录响应Schema"""
    id: uuid.UUID
    user_id: uuid.UUID
    photo_path: Optional[str]
    thumbnail_path: Optional[str]
    total_calories: Optional[float]
    total_protein: Optional[float]
    total_carbs: Optional[float]
    total_fat: Optional[float]
    total_fiber: Optional[float]
    ai_model: Optional[str] = Field(None, description="使用的AI模型名称")
    ai_analysis: Optional[Dict[str, Any]]
    analysis_status: str = Field("completed", description="核心识图状态")
    recommendation_status: str = Field("completed", description="扩展建议状态")
    recommendation_attempts: int = Field(0, description="扩展建议已尝试次数")
    analysis_error: Optional[str] = Field(None, description="处理失败的可读错误")
    analysis_started_at: Optional[datetime] = None
    analysis_completed_at: Optional[datetime] = None
    recommendation_updated_at: Optional[datetime] = None
    food_items: List[FoodItemResponse] = []
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def current_ai_model(self) -> str:
        return settings.CODEX_MODEL

    @computed_field
    @property
    def analysis_is_legacy(self) -> bool:
        return bool(self.ai_model and self.ai_model != settings.CODEX_MODEL)

    @field_serializer('photo_path', 'thumbnail_path')
    def _normalize_path(self, path: Optional[str]) -> Optional[str]:
        """规范化路径：确保路径以 /uploads/nutrition/ 开头（序列化时自动应用）"""
        if not path:
            return path
        return create_signed_media_url(path)

    @field_serializer("meal_time")
    def _serialize_meal_time_hk(self, value: datetime) -> str:
        return ensure_hk(value).isoformat()

    model_config = ConfigDict(from_attributes=True)


class MealListResponse(BaseModel):
    """餐次列表响应Schema"""
    meals: List[MealRecordResponse]
    total: int
    page: int
    page_size: int


# ===== 照片分析Schema =====

class AnalyzeMealRequest(BaseModel):
    """分析餐食照片请求Schema（metadata）"""
    meal_type: MealTypeEnum = Field(..., description="餐次类型")
    meal_time: Optional[datetime] = Field(None, description="用餐时间（默认当前时间）")
    notes: Optional[str] = Field(None, description="用户备注")


class AnalyzeMealResponse(BaseModel):
    """分析餐食照片响应Schema"""
    analysis: Dict[str, Any] = Field(..., description="AI完整分析结果")
    parsed_data: Dict[str, Any] = Field(..., description="解析后的结构化数据")
    temp_image_path: Optional[str] = Field(None, description="临时图片路径")


# ===== 每日营养汇总Schema =====

class NutritionDailySummaryResponse(BaseModel):
    """每日营养汇总响应Schema"""
    id: uuid.UUID
    user_id: uuid.UUID
    date: date
    total_calories: Optional[float]
    total_protein: Optional[float]
    total_carbs: Optional[float]
    total_fat: Optional[float]
    total_fiber: Optional[float]
    meals_count: int
    breakfast_calories: Optional[float]
    lunch_calories: Optional[float]
    dinner_calories: Optional[float]
    snack_calories: Optional[float]
    flags: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== 周营养趋势Schema =====

class WeeklyNutritionTrend(BaseModel):
    """周营养趋势Schema"""
    start_date: date
    end_date: date
    daily_data: List[NutritionDailySummaryResponse]
    weekly_avg_calories: Optional[float]
    weekly_avg_protein: Optional[float]
    weekly_avg_carbs: Optional[float]
    weekly_avg_fat: Optional[float]
    recorded_days: int = Field(description="7 天窗口中实际有饮食记录的天数")
    expected_days: int = 7


# ===== 通用响应Schema =====

class AnalysisStatusResponse(BaseModel):
    """分析状态响应Schema"""
    status: str = Field(..., description="状态：success/error")
    message: str = Field(..., description="消息")
    data: Optional[Dict[str, Any]] = Field(None, description="额外数据")


class DeleteResponse(BaseModel):
    """删除操作响应Schema"""
    status: str
    message: str
    deleted_id: Optional[uuid.UUID] = None


class MealPosterResponse(BaseModel):
    """按需生成的分享海报。"""
    poster_url: str
    generated: bool = Field(description="本次是否实际调用了图片模型；false 表示复用缓存")
    model: str
    verified_metrics: Dict[str, Any]
    content_digest: str
    layout_version: str

    @field_serializer("poster_url")
    def _sign_poster_url(self, path: str) -> str:
        return create_signed_media_url(path)
