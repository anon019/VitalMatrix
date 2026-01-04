"""
营养服务 - 核心业务逻辑
"""
from __future__ import annotations

import os
import logging
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.nutrition import MealRecord, FoodItem, NutritionDailySummary, MealType
from app.models.user import User
from app.services.gemini_service import get_gemini_service
from app.services.file_storage import get_file_storage
from app.schemas.nutrition import (
    MealRecordCreate,
    FoodItemCreate,
    MealRecordResponse,
    NutritionDailySummaryResponse
)

logger = logging.getLogger(__name__)

# 获取 backend 根目录
BACKEND_ROOT = Path(__file__).parent.parent.parent


class NutritionService:
    """营养服务类"""

    def __init__(self):
        self.gemini_service = get_gemini_service()
        self.file_storage = get_file_storage()

    async def analyze_and_save_meal(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        meal_type: MealType,
        meal_time: datetime,
        image_content: bytes,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        分析餐食照片并保存

        完整流程：
        1. 保存照片文件（原图+缩略图）
        2. 调用Gemini分析照片
        3. 保存餐次记录和食物明细到数据库
        4. 更新每日营养汇总

        Args:
            db: 数据库会话
            user_id: 用户ID
            meal_type: 餐次类型
            meal_time: 用餐时间
            image_content: 图片二进制内容
            notes: 用户备注

        Returns:
            分析结果和保存的meal_id
        """
        try:
            # 生成meal_id（用于文件命名）
            meal_id = uuid.uuid4()

            # 1. 保存照片文件（返回web路径和绝对路径）
            photo_path, thumbnail_path, abs_photo_path, abs_thumbnail_path = await self.file_storage.save_meal_photo(
                user_id=str(user_id),
                meal_id=str(meal_id),
                file_content=image_content,
                meal_time=meal_time,
                file_extension="jpg"
            )

            # 2. 获取用户信息（用于个性化分析）
            user_context = await self._get_user_context(db, user_id)

            # 3. 调用Gemini分析（带重试机制）
            meal_time_str = meal_time.strftime("%Y-%m-%d %H:%M")
            analysis_result = await self.gemini_service.analyze_meal_photo_with_retry(
                image_path=abs_photo_path,
                meal_type=meal_type.value,
                meal_time=meal_time_str,
                user_context=user_context
            )

            # 4. 解析分析结果，创建MealRecord
            meal_record = await self._create_meal_record(
                db=db,
                meal_id=meal_id,
                user_id=user_id,
                meal_type=meal_type,
                meal_time=meal_time,
                photo_path=photo_path,
                thumbnail_path=thumbnail_path,
                analysis_result=analysis_result,
                notes=notes
            )

            # 5. 更新每日营养汇总
            await self.update_daily_summary(db, user_id, meal_time.date())

            logger.info(f"Meal analysis and save completed for user {user_id}, meal {meal_id}")

            return {
                "meal_id": str(meal_id),
                "analysis": analysis_result,
                "meal_record": meal_record
            }

        except Exception as e:
            logger.error(f"Failed to analyze and save meal: {str(e)}", exc_info=True)
            raise

    async def _get_user_context(self, db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
        """获取用户上下文信息（用于Gemini分析）"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {}

        # 计算年龄
        age = None
        if user.birth_year:
            age = datetime.now().year - user.birth_year

        return {
            "gender": "男",  # 暂时写死，后续可以从用户表添加gender字段
            "age": age or "未知",
            "weight": float(user.weight) if user.weight else "未知",
            "height": user.height or "未知",
            "health_goal": user.health_goal or "未设置",
            "training_plan": user.training_plan or "未设置"
        }

    async def _create_meal_record(
        self,
        db: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID,
        meal_type: MealType,
        meal_time: datetime,
        photo_path: str,
        thumbnail_path: str,
        analysis_result: Dict[str, Any],
        notes: Optional[str]
    ) -> MealRecord:
        """创建餐次记录和食物明细"""

        # 从分析结果中提取数据
        identified_foods = analysis_result.get("identified_foods", [])
        nutrition_summary = analysis_result.get("nutrition_summary", {})
        ai_model = analysis_result.get("_ai_model")  # 提取AI模型名称

        # 创建MealRecord
        meal_record = MealRecord(
            id=meal_id,
            user_id=user_id,
            meal_type=meal_type,
            meal_time=meal_time,
            photo_path=photo_path,
            thumbnail_path=thumbnail_path,
            total_calories=nutrition_summary.get("total_calories"),
            total_protein=nutrition_summary.get("total_protein"),
            total_carbs=nutrition_summary.get("total_carbs"),
            total_fat=nutrition_summary.get("total_fat"),
            total_fiber=nutrition_summary.get("total_fiber"),
            ai_model=ai_model,  # 保存AI模型名称
            gemini_analysis=analysis_result,
            notes=notes
        )

        db.add(meal_record)

        # 创建FoodItems
        for food_data in identified_foods:
            food_item = FoodItem(
                meal_id=meal_id,
                food_name=food_data.get("name", "未知食物"),
                category=food_data.get("category"),
                estimated_weight=food_data.get("weight_g"),
                calories=food_data.get("calories"),
                protein=food_data.get("protein"),
                carbs=food_data.get("carbs"),
                fat=food_data.get("fat"),
                fiber=food_data.get("fiber"),
                sodium=food_data.get("sodium"),
                sugar=food_data.get("sugar"),
                notes=food_data.get("notes")
            )
            db.add(food_item)

        await db.commit()

        # 重新查询以加载 food_items 关联关系（解决 ResponseValidationError）
        result = await db.execute(
            select(MealRecord)
            .options(selectinload(MealRecord.food_items))
            .where(MealRecord.id == meal_id)
        )
        meal_record = result.scalar_one()

        logger.info(f"Created meal record {meal_id} with {len(identified_foods)} food items")
        return meal_record

    async def get_meal_by_id(
        self,
        db: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Optional[MealRecord]:
        """获取餐次详情（包含food_items）"""
        result = await db.execute(
            select(MealRecord)
            .options(selectinload(MealRecord.food_items))
            .where(
                and_(
                    MealRecord.id == meal_id,
                    MealRecord.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_meals_list(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        meal_type: Optional[MealType] = None,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[MealRecord], int]:
        """
        获取餐次列表（分页）

        Args:
            db: 数据库会话
            user_id: 用户ID
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            meal_type: 餐次类型（可选）
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            (餐次列表, 总数) 元组
        """
        # 构建查询条件
        conditions = [MealRecord.user_id == user_id]

        if start_date:
            conditions.append(func.date(MealRecord.meal_time) >= start_date)

        if end_date:
            conditions.append(func.date(MealRecord.meal_time) <= end_date)

        if meal_type:
            conditions.append(MealRecord.meal_type == meal_type)

        # 查询总数
        count_result = await db.execute(
            select(func.count(MealRecord.id)).where(and_(*conditions))
        )
        total = count_result.scalar()

        # 查询数据（分页，按时间倒序）
        offset = (page - 1) * page_size
        result = await db.execute(
            select(MealRecord)
            .options(selectinload(MealRecord.food_items))
            .where(and_(*conditions))
            .order_by(desc(MealRecord.meal_time))
            .offset(offset)
            .limit(page_size)
        )
        meals = result.scalars().all()

        return list(meals), total

    async def delete_meal(
        self,
        db: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> bool:
        """
        删除餐次记录

        Args:
            db: 数据库会话
            meal_id: 餐次ID
            user_id: 用户ID

        Returns:
            是否删除成功
        """
        try:
            # 查找餐次记录
            meal = await self.get_meal_by_id(db, meal_id, user_id)
            if not meal:
                logger.warning(f"Meal {meal_id} not found for user {user_id}")
                return False

            # 删除照片文件
            if meal.photo_path:
                self.file_storage.delete_meal_photos(meal.photo_path, meal.thumbnail_path)

            # 获取餐次日期（用于后续更新daily summary）
            meal_date = meal.meal_time.date()

            # 删除数据库记录（FoodItems会级联删除）
            await db.delete(meal)
            await db.commit()

            # 更新每日营养汇总
            await self.update_daily_summary(db, user_id, meal_date)

            logger.info(f"Deleted meal {meal_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete meal {meal_id}: {str(e)}", exc_info=True)
            await db.rollback()
            return False

    async def update_daily_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        target_date: date
    ) -> NutritionDailySummary:
        """
        计算并更新每日营养汇总

        Args:
            db: 数据库会话
            user_id: 用户ID
            target_date: 目标日期

        Returns:
            更新后的每日汇总记录
        """
        try:
            # 查询当日所有餐次
            result = await db.execute(
                select(MealRecord).where(
                    and_(
                        MealRecord.user_id == user_id,
                        func.date(MealRecord.meal_time) == target_date
                    )
                )
            )
            meals = result.scalars().all()

            # 计算总营养（转换为float避免Decimal混用问题）
            total_calories = sum(float(m.total_calories or 0) for m in meals)
            total_protein = sum(float(m.total_protein or 0) for m in meals)
            total_carbs = sum(float(m.total_carbs or 0) for m in meals)
            total_fat = sum(float(m.total_fat or 0) for m in meals)
            total_fiber = sum(float(m.total_fiber or 0) for m in meals)

            # 按餐次类型统计热量
            breakfast_calories = sum(
                float(m.total_calories or 0) for m in meals if m.meal_type == MealType.BREAKFAST
            )
            lunch_calories = sum(
                float(m.total_calories or 0) for m in meals if m.meal_type == MealType.LUNCH
            )
            dinner_calories = sum(
                float(m.total_calories or 0) for m in meals if m.meal_type == MealType.DINNER
            )
            snack_calories = sum(
                float(m.total_calories or 0) for m in meals if m.meal_type == MealType.SNACK
            )

            # 计算营养警示标记
            flags = self._calculate_nutrition_flags(
                total_calories, total_protein, total_carbs, total_fat
            )

            # 查找或创建NutritionDailySummary
            summary_result = await db.execute(
                select(NutritionDailySummary).where(
                    and_(
                        NutritionDailySummary.user_id == user_id,
                        NutritionDailySummary.date == target_date
                    )
                )
            )
            summary = summary_result.scalar_one_or_none()

            if summary:
                # 更新现有记录
                summary.total_calories = total_calories
                summary.total_protein = total_protein
                summary.total_carbs = total_carbs
                summary.total_fat = total_fat
                summary.total_fiber = total_fiber
                summary.meals_count = len(meals)
                summary.breakfast_calories = breakfast_calories
                summary.lunch_calories = lunch_calories
                summary.dinner_calories = dinner_calories
                summary.snack_calories = snack_calories
                summary.flags = flags
            else:
                # 创建新记录
                summary = NutritionDailySummary(
                    user_id=user_id,
                    date=target_date,
                    total_calories=total_calories,
                    total_protein=total_protein,
                    total_carbs=total_carbs,
                    total_fat=total_fat,
                    total_fiber=total_fiber,
                    meals_count=len(meals),
                    breakfast_calories=breakfast_calories,
                    lunch_calories=lunch_calories,
                    dinner_calories=dinner_calories,
                    snack_calories=snack_calories,
                    flags=flags
                )
                db.add(summary)

            await db.commit()
            await db.refresh(summary)

            logger.info(f"Updated daily summary for {target_date}: {total_calories}kcal")
            return summary

        except Exception as e:
            logger.error(f"Failed to update daily summary: {str(e)}", exc_info=True)
            await db.rollback()
            raise

    def _calculate_nutrition_flags(
        self,
        total_calories: float,
        total_protein: float,
        total_carbs: float,
        total_fat: float
    ) -> Dict[str, Any]:
        """
        计算营养警示标记

        Args:
            total_calories: 总热量
            total_protein: 总蛋白质
            total_carbs: 总碳水
            total_fat: 总脂肪

        Returns:
            警示标记字典
        """
        flags = {}

        # 热量警示（基于2000kcal/天标准）
        if total_calories > 2500:
            flags["calorie_high"] = True
        elif total_calories < 1200:
            flags["calorie_low"] = True

        # 蛋白质警示（建议1.0-1.2g/kg，假设70kg体重）
        if total_protein < 50:
            flags["protein_low"] = True
        elif total_protein > 150:
            flags["protein_high"] = True

        # 碳水警示（占总热量50-60%）
        if total_calories > 0:
            carbs_ratio = (total_carbs * 4) / total_calories
            if carbs_ratio > 0.65:
                flags["carbs_high"] = True
            elif carbs_ratio < 0.40:
                flags["carbs_low"] = True

        # 脂肪警示（占总热量20-30%）
        if total_calories > 0:
            fat_ratio = (total_fat * 9) / total_calories
            if fat_ratio > 0.35:
                flags["fat_high"] = True
            elif fat_ratio < 0.15:
                flags["fat_low"] = True

        return flags

    async def get_daily_summary(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        target_date: date
    ) -> Optional[NutritionDailySummary]:
        """获取指定日期的营养汇总"""
        result = await db.execute(
            select(NutritionDailySummary).where(
                and_(
                    NutritionDailySummary.user_id == user_id,
                    NutritionDailySummary.date == target_date
                )
            )
        )
        return result.scalar_one_or_none()

    async def reanalyze_meal(
        self,
        db: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> MealRecord:
        """
        重新分析已上传的餐次照片

        用于分析失败或用户希望重新分析时使用

        Args:
            db: 数据库会话
            meal_id: 餐次ID
            user_id: 用户ID

        Returns:
            更新后的MealRecord

        Raises:
            ValueError: 餐次不存在或图片不存在
        """
        # 获取餐次记录
        meal = await self.get_meal_by_id(db, meal_id, user_id)
        if not meal:
            raise ValueError("餐次记录不存在")

        # 构建图片绝对路径
        photo_path = meal.photo_path
        if photo_path.startswith("/uploads"):
            abs_photo_path = str(BACKEND_ROOT / photo_path.lstrip("/"))
        else:
            abs_photo_path = photo_path

        # 验证图片存在
        import os
        if not os.path.exists(abs_photo_path):
            raise ValueError(f"图片文件不存在: {abs_photo_path}")

        # 获取用户上下文
        user_context = await self._get_user_context(db, user_id)

        # 重新调用Gemini分析（带重试）
        meal_time_str = meal.meal_time.strftime("%Y-%m-%d %H:%M")
        analysis_result = await self.gemini_service.analyze_meal_photo_with_retry(
            image_path=abs_photo_path,
            meal_type=meal.meal_type.value,
            meal_time=meal_time_str,
            user_context=user_context
        )

        # 从分析结果中提取数据
        identified_foods = analysis_result.get("identified_foods", [])
        nutrition_summary = analysis_result.get("nutrition_summary", {})
        ai_model = analysis_result.get("_ai_model")

        # 更新MealRecord
        meal.total_calories = nutrition_summary.get("total_calories")
        meal.total_protein = nutrition_summary.get("total_protein")
        meal.total_carbs = nutrition_summary.get("total_carbs")
        meal.total_fat = nutrition_summary.get("total_fat")
        meal.total_fiber = nutrition_summary.get("total_fiber")
        meal.ai_model = ai_model
        meal.gemini_analysis = analysis_result

        # 删除旧的FoodItems
        from sqlalchemy import delete
        await db.execute(
            delete(FoodItem).where(FoodItem.meal_id == meal_id)
        )

        # 创建新的FoodItems
        for food_data in identified_foods:
            food_item = FoodItem(
                meal_id=meal_id,
                food_name=food_data.get("name", "未知食物"),
                category=food_data.get("category"),
                estimated_weight=food_data.get("weight_g"),
                calories=food_data.get("calories"),
                protein=food_data.get("protein"),
                carbs=food_data.get("carbs"),
                fat=food_data.get("fat"),
                fiber=food_data.get("fiber"),
                sodium=food_data.get("sodium"),
                sugar=food_data.get("sugar"),
                notes=food_data.get("notes")
            )
            db.add(food_item)

        await db.commit()

        # 更新每日营养汇总
        await self.update_daily_summary(db, user_id, meal.meal_time.date())

        # 重新查询以加载 food_items
        result = await db.execute(
            select(MealRecord)
            .options(selectinload(MealRecord.food_items))
            .where(MealRecord.id == meal_id)
        )
        meal_record = result.scalar_one()

        logger.info(f"Reanalyzed meal {meal_id} with {len(identified_foods)} food items")
        return meal_record

    async def get_weekly_trend(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        end_date: Optional[date] = None
    ) -> List[NutritionDailySummary]:
        """
        获取7日营养趋势

        Args:
            db: 数据库会话
            user_id: 用户ID
            end_date: 结束日期（默认今天）

        Returns:
            7天的每日汇总列表
        """
        if not end_date:
            end_date = date.today()

        start_date = end_date - timedelta(days=6)

        result = await db.execute(
            select(NutritionDailySummary).where(
                and_(
                    NutritionDailySummary.user_id == user_id,
                    NutritionDailySummary.date >= start_date,
                    NutritionDailySummary.date <= end_date
                )
            ).order_by(NutritionDailySummary.date)
        )

        return list(result.scalars().all())


# 全局单例
_nutrition_service_instance = None


def get_nutrition_service() -> NutritionService:
    """获取营养服务单例"""
    global _nutrition_service_instance
    if _nutrition_service_instance is None:
        _nutrition_service_instance = NutritionService()
    return _nutrition_service_instance
