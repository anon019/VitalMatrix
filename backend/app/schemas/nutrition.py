"""
营养模块的Pydantic Schemas
"""
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_serializer
from enum import Enum
import uuid


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

    class Config:
        from_attributes = True


# ===== 餐次记录Schema =====

class MealRecordBase(BaseModel):
    """餐次记录基础Schema"""
    meal_type: MealTypeEnum = Field(..., description="餐次类型")
    meal_time: datetime = Field(..., description="用餐时间")
    notes: Optional[str] = Field(None, description="用户备注")


class MealRecordCreate(MealRecordBase):
    """创建餐次记录Schema（用于确认保存）"""
    gemini_analysis: Dict[str, Any] = Field(..., description="Gemini完整分析结果")
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
    gemini_analysis: Optional[Dict[str, Any]]
    food_items: List[FoodItemResponse] = []
    created_at: datetime
    updated_at: datetime

    @field_serializer('photo_path', 'thumbnail_path')
    def _normalize_path(self, path: Optional[str]) -> Optional[str]:
        """规范化路径：确保路径以 /uploads/nutrition/ 开头（序列化时自动应用）"""
        if not path:
            return path
        if path.startswith("/uploads/nutrition/"):
            return path  # 已经是正确格式
        # 旧格式路径，添加前缀
        return f"/uploads/nutrition/{path}"

    class Config:
        from_attributes = True


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
    analysis: Dict[str, Any] = Field(..., description="Gemini完整分析结果")
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

    class Config:
        from_attributes = True


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
