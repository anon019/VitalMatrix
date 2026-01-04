"""
营养饮食相关模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, DECIMAL, TIMESTAMP, Date, Text, ForeignKey, Enum as SQLEnum, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid
import enum

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class MealType(str, enum.Enum):
    """餐次类型"""
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class FoodCategory(str, enum.Enum):
    """食物分类"""
    STAPLE = "staple"  # 主食
    PROTEIN = "protein"  # 蛋白质
    VEGETABLE = "vegetable"  # 蔬菜
    FRUIT = "fruit"  # 水果
    DAIRY = "dairy"  # 乳制品
    FAT = "fat"  # 油脂
    BEVERAGE = "beverage"  # 饮品
    SNACK = "snack"  # 零食
    OTHER = "other"  # 其他


class MealRecord(Base):
    """餐次记录主表"""

    __tablename__ = "meal_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 餐次信息
    meal_type: Mapped[MealType] = mapped_column(
        SQLEnum(MealType, native_enum=False), nullable=False, comment="餐次类型"
    )
    meal_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True, comment="用餐时间"
    )

    # 照片存储路径
    photo_path: Mapped[Optional[str]] = mapped_column(String(500), comment="原图存储路径")
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), comment="缩略图路径")

    # 营养总计（从food_items聚合计算）
    total_calories: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总热量 (kcal)"
    )
    total_protein: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总蛋白质 (g)"
    )
    total_carbs: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总碳水化合物 (g)"
    )
    total_fat: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总脂肪 (g)"
    )
    total_fiber: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总膳食纤维 (g)"
    )

    # AI分析相关
    ai_model: Mapped[Optional[str]] = mapped_column(
        String(100), comment="使用的AI模型名称（如 gemini-3-pro-preview）"
    )
    gemini_analysis: Mapped[Optional[dict]] = mapped_column(
        JSONB, comment="AI完整输出（包含分析、建议等）"
    )

    # 用户备注
    notes: Mapped[Optional[str]] = mapped_column(Text, comment="用户备注")

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="meal_records")
    food_items: Mapped[List["FoodItem"]] = relationship(
        "FoodItem", back_populates="meal", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<MealRecord {self.meal_type} at {self.meal_time}>"


class FoodItem(Base):
    """食物明细表"""

    __tablename__ = "food_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meal_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 食物基本信息
    food_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True, comment="食物名称")
    category: Mapped[Optional[FoodCategory]] = mapped_column(
        SQLEnum(FoodCategory, native_enum=False), comment="食物分类"
    )
    estimated_weight: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="估计重量 (g)"
    )

    # 营养成分（单个食物项）
    calories: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="热量 (kcal)"
    )
    protein: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="蛋白质 (g)"
    )
    carbs: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="碳水化合物 (g)"
    )
    fat: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="脂肪 (g)"
    )
    fiber: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="膳食纤维 (g)"
    )

    # 额外微量营养素（可选）
    sodium: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="钠 (mg)"
    )
    sugar: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="糖分 (g)"
    )

    # 备注
    notes: Mapped[Optional[str]] = mapped_column(Text, comment="备注信息")

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    # 关联关系
    meal: Mapped["MealRecord"] = relationship("MealRecord", back_populates="food_items")

    def __repr__(self):
        return f"<FoodItem {self.food_name} ({self.calories}kcal)>"


class NutritionDailySummary(Base):
    """每日营养汇总表"""

    __tablename__ = "nutrition_daily_summary"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[datetime] = mapped_column(
        Date, nullable=False, index=True, comment="日期"
    )

    # 每日营养总计
    total_calories: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总热量 (kcal)"
    )
    total_protein: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总蛋白质 (g)"
    )
    total_carbs: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总碳水化合物 (g)"
    )
    total_fat: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总脂肪 (g)"
    )
    total_fiber: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="总膳食纤维 (g)"
    )

    # 餐次统计
    meals_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="餐次数量"
    )
    breakfast_calories: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="早餐热量"
    )
    lunch_calories: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="午餐热量"
    )
    dinner_calories: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="晚餐热量"
    )
    snack_calories: Mapped[Optional[float]] = mapped_column(
        DECIMAL(8, 2), comment="加餐热量"
    )

    # 营养警示标记（JSONB）
    flags: Mapped[Optional[dict]] = mapped_column(
        JSONB, comment="营养警示标记（如热量过高、蛋白质不足等）"
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="nutrition_daily_summaries")

    def __repr__(self):
        return f"<NutritionDailySummary {self.date} - {self.total_calories}kcal>"
