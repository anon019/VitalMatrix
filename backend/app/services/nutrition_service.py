"""
营养服务 - 核心业务逻辑
"""
from __future__ import annotations

import logging
import hashlib
import time
import uuid
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, and_, desc, case, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.config import settings

from app.models.nutrition import MealRecord, FoodItem, NutritionDailySummary, MealType
from app.models.user import User
from app.services.codex_nutrition_service import get_codex_nutrition_service
from app.services.file_storage import get_file_storage
from app.utils.datetime_helper import date_hk, format_hk, now_hk, today_hk, start_of_day_hk
from app.utils.distributed_lock import distributed_lock

logger = logging.getLogger(__name__)


class NutritionService:
    """营养服务类"""

    def __init__(self):
        self.ai_service = get_codex_nutrition_service()
        self.file_storage = get_file_storage()

    @staticmethod
    def _calculate_nutrition_flags(
        total_calories: float,
        total_protein: float,
        total_carbs: float,
        total_fat: float,
        meals_count: int = 3,
    ) -> Dict[str, bool]:
        """根据每日营养汇总生成轻量级风险标记。

        说明：
        - 这里的 flags 主要用于页面展示与 AI 提示补充，不应因为缺失而阻断主流程。
        - 无餐食/全 0 数据时返回空字典，避免把“今天没记饮食”误判为营养异常。
        - 阈值采用保守的成年人日摄入参考区间，优先避免明显异常值漏报。
        """
        total_calories = float(total_calories or 0)
        total_protein = float(total_protein or 0)
        total_carbs = float(total_carbs or 0)
        total_fat = float(total_fat or 0)

        if total_calories <= 0 and total_protein <= 0 and total_carbs <= 0 and total_fat <= 0:
            return {}

        complete_day = meals_count >= 3
        return {
            "partial_day": not complete_day,
            "calorie_high": total_calories > 2400,
            "calorie_low": complete_day and 0 < total_calories < 1400,
            "protein_low": complete_day and 0 < total_protein < 60,
            "protein_high": total_protein > 180,
            "carbs_high": total_carbs > 320,
            "carbs_low": complete_day and 0 < total_carbs < 130,
            "fat_high": total_fat > 80,
            "fat_low": complete_day and 0 < total_fat < 35,
        }

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
        2. 调用 Codex Luna 分析照片
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
        image_sha256 = hashlib.sha256(image_content).hexdigest()
        duplicate_since = now_hk() - timedelta(minutes=10)
        duplicate_result = await db.execute(
            select(MealRecord)
            .options(selectinload(MealRecord.food_items))
            .where(
                and_(
                    MealRecord.user_id == user_id,
                    MealRecord.image_sha256 == image_sha256,
                    MealRecord.created_at >= duplicate_since,
                    MealRecord.analysis_status == "completed",
                )
            )
            .order_by(desc(MealRecord.created_at))
            .limit(1)
        )
        duplicate = duplicate_result.scalar_one_or_none()
        if duplicate:
            logger.warning(
                "Duplicate nutrition upload reused: user_id=%s meal_id=%s image_sha256=%s",
                user_id,
                duplicate.id,
                image_sha256[:12],
            )
            return {
                "meal_id": str(duplicate.id),
                "analysis": duplicate.ai_analysis or {},
                "meal_record": duplicate,
                "deduplicated": True,
            }

        meal_id = uuid.uuid4()
        photo_path = None
        thumbnail_path = None
        analysis_started_at = now_hk()
        pipeline_started = time.perf_counter()

        try:
            # 1. 保存照片文件（返回web路径和绝对路径）
            save_started = time.perf_counter()
            photo_path, thumbnail_path, abs_photo_path, _ = await self.file_storage.save_meal_photo(
                user_id=str(user_id),
                meal_id=str(meal_id),
                file_content=image_content,
                meal_time=meal_time,
                file_extension="jpg"
            )
            save_ms = (time.perf_counter() - save_started) * 1000

            # 2. 获取用户信息（用于个性化分析）
            user_context = await self._get_user_context(
                db,
                user_id,
                before_time=meal_time,
                include_history=False,
            )

            # 外部 AI 调用可能持续数分钟；先结束只读事务并释放连接。
            await db.commit()

            # 3. 调用 Codex Luna 分析（带重试机制）
            meal_time_str = format_hk(meal_time, "%Y-%m-%d %H:%M")
            ai_started = time.perf_counter()
            analysis_result = await self.ai_service.analyze_meal_photo_with_retry(
                image_path=abs_photo_path,
                meal_type=meal_type.value,
                meal_time=meal_time_str,
                user_context=user_context
            )
            ai_ms = (time.perf_counter() - ai_started) * 1000

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
                notes=notes,
                image_sha256=image_sha256,
                analysis_started_at=analysis_started_at,
            )

            # 5. 更新每日营养汇总
            await self.update_daily_summary(db, user_id, date_hk(meal_time), commit=False)
            await db.commit()

            logger.info(f"Meal analysis and save completed for user {user_id}, meal {meal_id}")
            logger.info(
                "Nutrition core pipeline timing: meal_id=%s bytes=%s save_ms=%.1f "
                "ai_ms=%.1f total_ms=%.1f",
                meal_id,
                len(image_content),
                save_ms,
                ai_ms,
                (time.perf_counter() - pipeline_started) * 1000,
            )

            return {
                "meal_id": str(meal_id),
                "analysis": analysis_result,
                "meal_record": meal_record,
                "deduplicated": False,
            }

        except Exception as e:
            if photo_path or thumbnail_path:
                try:
                    await db.rollback()
                except Exception:
                    pass
                self.file_storage.delete_meal_photos(photo_path, thumbnail_path)

            logger.error(f"Failed to analyze and save meal: {str(e)}", exc_info=True)
            raise

    async def _get_user_context(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        before_time: Optional[datetime] = None,
        exclude_meal_id: Optional[uuid.UUID] = None,
        include_history: bool = True,
    ) -> Dict[str, Any]:
        """获取用户画像和最近饮食上下文（用于 Codex 分析与推荐）。"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {}

        # 只有出生年月时无法判断具体生日是否已过，沿用用户声明的周岁口径。
        age = None
        if user.birth_year:
            current_date = today_hk()
            age = current_date.year - user.birth_year
            if user.birth_month and current_date.month < user.birth_month:
                age -= 1

        context = {
            "gender": user.gender or "未提供",
            "age": age or "未知",
            "weight": float(user.weight) if user.weight else "未知",
            "height": user.height or "未知",
            "health_goal": user.health_goal or "饮食健康、睡眠与综合健康管理",
            "training_plan": user.training_plan or "未设置",
        }
        if not include_history:
            return context

        history_end = before_time or now_hk()
        history_start = history_end - timedelta(days=7)
        meal_conditions = [
            MealRecord.user_id == user_id,
            MealRecord.meal_time < history_end,
            MealRecord.meal_time >= history_start,
        ]
        if exclude_meal_id:
            meal_conditions.append(MealRecord.id != exclude_meal_id)

        meals_result = await db.execute(
            select(MealRecord)
            .options(selectinload(MealRecord.food_items))
            .where(and_(*meal_conditions))
            .order_by(desc(MealRecord.meal_time))
            .limit(20)
        )
        recent_meals = meals_result.scalars().all()

        meal_type_labels = {
            MealType.BREAKFAST: "早餐",
            MealType.LUNCH: "午餐",
            MealType.DINNER: "晚餐",
            MealType.SNACK: "加餐",
        }
        recent_lines = []
        recommended_names = []
        for meal in recent_meals:
            food_names = [item.food_name for item in meal.food_items[:8] if item.food_name]
            if food_names:
                recent_lines.append(
                    f"{format_hk(meal.meal_time, '%m-%d')}"
                    f"{meal_type_labels.get(meal.meal_type, meal.meal_type.value)}："
                    f"{'、'.join(food_names)}"
                )

            recommendations = (meal.ai_analysis or {}).get("recommendations") or {}
            recipes = recommendations.get("next_meal_recipes") or []
            for recipe in recipes[:1]:
                for dish in (recipe.get("dishes") or [])[:4]:
                    name = dish.get("name")
                    if name and name not in recommended_names:
                        recommended_names.append(name)

        recent_context = "\n".join(recent_lines) if recent_lines else "近7天暂无已记录餐食"
        if recommended_names:
            recent_context += "\n最近已推荐菜品：" + "、".join(recommended_names[:12])

        context["recent_meals"] = recent_context
        return context

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
        notes: Optional[str],
        image_sha256: Optional[str] = None,
        analysis_started_at: Optional[datetime] = None,
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
            ai_analysis=analysis_result,
            notes=notes,
            analysis_status="completed",
            recommendation_status="pending",
            recommendation_attempts=0,
            analysis_error=None,
            image_sha256=image_sha256,
            analysis_started_at=analysis_started_at,
            analysis_completed_at=now_hk(),
            recommendation_updated_at=now_hk(),
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

        await db.flush()

        # 重新查询以加载 food_items 关联关系（解决 ResponseValidationError）
        result = await db.execute(
            select(MealRecord)
            .options(selectinload(MealRecord.food_items))
            .where(MealRecord.id == meal_id)
        )
        meal_record = result.scalar_one()

        logger.info(f"Created meal record {meal_id} with {len(identified_foods)} food items")
        return meal_record

    async def generate_recommendations_for_meal(
        self,
        meal_id: uuid.UUID,
        user_id: uuid.UUID,
        force: bool = False,
    ) -> bool:
        """生成扩展建议；使用独立会话，失败不影响已经保存的核心餐食。"""
        from app.database.session import AsyncSessionLocal

        lock_key = f"nutrition-recommendations:{meal_id}"
        async with distributed_lock(
            lock_key, ttl_seconds=settings.NUTRITION_RECOMMENDATION_TIMEOUT_SECONDS + 60
        ) as acquired:
            if not acquired:
                logger.info("Recommendation task already running: meal_id=%s", meal_id)
                return False

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(MealRecord)
                    .where(
                        and_(MealRecord.id == meal_id, MealRecord.user_id == user_id)
                    )
                    .with_for_update()
                )
                meal = result.scalar_one_or_none()
                if not meal or not meal.ai_analysis:
                    return False
                if meal.recommendation_status == "completed" and not force:
                    return True

                meal.recommendation_status = "processing"
                meal.recommendation_attempts = int(meal.recommendation_attempts or 0) + 1
                meal.analysis_error = None
                meal.recommendation_updated_at = now_hk()
                core_analysis = dict(meal.ai_analysis)
                meal_type = meal.meal_type.value
                meal_time = meal.meal_time
                user_context = await self._get_user_context(
                    db,
                    user_id,
                    before_time=meal_time,
                    exclude_meal_id=meal.id,
                )
                await db.commit()

            try:
                recommendations = await self.ai_service.generate_recommendations(
                    core_analysis=core_analysis,
                    meal_type=meal_type,
                    meal_time=format_hk(meal_time, "%Y-%m-%d %H:%M"),
                    user_context=user_context,
                )
            except Exception as exc:
                logger.exception(
                    "Recommendation generation failed: meal_id=%s", meal_id
                )
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(MealRecord).where(
                            and_(MealRecord.id == meal_id, MealRecord.user_id == user_id)
                        )
                    )
                    meal = result.scalar_one_or_none()
                    if meal:
                        meal.recommendation_status = "failed"
                        meal.analysis_error = str(exc)[:500]
                        meal.recommendation_updated_at = now_hk()
                        analysis = dict(meal.ai_analysis or {})
                        current = dict(analysis.get("recommendations") or {})
                        current["status"] = "failed"
                        analysis["recommendations"] = current
                        meal.ai_analysis = analysis
                        await db.commit()
                return False

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(MealRecord).where(
                        and_(MealRecord.id == meal_id, MealRecord.user_id == user_id)
                    )
                )
                meal = result.scalar_one_or_none()
                if not meal:
                    return False
                analysis = dict(meal.ai_analysis or {})
                analysis["recommendations"] = recommendations
                meal.ai_analysis = analysis
                meal.recommendation_status = "completed"
                meal.analysis_error = None
                meal.recommendation_updated_at = now_hk()
                await db.commit()
            logger.info("Recommendation generation completed: meal_id=%s", meal_id)
            return True

    async def resume_pending_recommendations(self, limit: int = 10) -> int:
        """恢复待处理、失败或超时中断的扩展建议任务。"""
        from app.database.session import AsyncSessionLocal

        stale_before = now_hk() - timedelta(minutes=10)
        retry_before = now_hk() - timedelta(minutes=10)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MealRecord.id, MealRecord.user_id)
                .where(
                    MealRecord.analysis_status == "completed",
                    MealRecord.recommendation_attempts < 3,
                    or_(
                        MealRecord.recommendation_status == "pending",
                        and_(
                            MealRecord.recommendation_status == "failed",
                            MealRecord.recommendation_updated_at < retry_before,
                        ),
                        and_(
                            MealRecord.recommendation_status == "processing",
                            MealRecord.recommendation_updated_at < stale_before,
                        ),
                    ),
                )
                .order_by(MealRecord.created_at)
                .limit(limit)
            )
            pending = result.all()

        completed = 0
        for pending_meal_id, pending_user_id in pending:
            if await self.generate_recommendations_for_meal(
                pending_meal_id, pending_user_id
            ):
                completed += 1
        return completed

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

    async def get_meal_analysis_status(
        self,
        db: AsyncSession,
        meal_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[Dict[str, Any]]:
        """轻量读取分析状态，避免轮询时加载 JSONB 和 food_items。"""
        result = await db.execute(
            select(
                MealRecord.id,
                MealRecord.analysis_status,
                MealRecord.recommendation_status,
                MealRecord.recommendation_attempts,
                MealRecord.analysis_error,
                MealRecord.analysis_completed_at,
                MealRecord.recommendation_updated_at,
            ).where(
                and_(
                    MealRecord.id == meal_id,
                    MealRecord.user_id == user_id,
                )
            )
        )
        row = result.one_or_none()
        if not row:
            return None
        return {
            "meal_id": str(row.id),
            "analysis_status": row.analysis_status,
            "recommendation_status": row.recommendation_status,
            "recommendation_attempts": row.recommendation_attempts,
            "analysis_error": row.analysis_error,
            "analysis_completed_at": row.analysis_completed_at,
            "recommendation_updated_at": row.recommendation_updated_at,
        }

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
            start_datetime = start_of_day_hk(start_date)
            conditions.append(MealRecord.meal_time >= start_datetime)

        if end_date:
            next_day = end_date + timedelta(days=1)
            conditions.append(MealRecord.meal_time < start_of_day_hk(next_day))

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

            # 获取餐次日期（用于后续更新daily summary）
            meal_date = date_hk(meal.meal_time)
            photo_path = meal.photo_path
            thumbnail_path = meal.thumbnail_path

            # 删除数据库记录（FoodItems会级联删除）
            await db.delete(meal)
            await self.update_daily_summary(db, user_id, meal_date, commit=False)
            await db.commit()

            if photo_path:
                try:
                    self.file_storage.delete_meal_photos(photo_path, thumbnail_path)
                except Exception as exc:
                    logger.warning(f"Meal {meal_id} 数据已删除，但清理图片失败: {str(exc)}")

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
        target_date: date,
        *,
        commit: bool = True,
    ) -> Optional[NutritionDailySummary]:
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
            digest = hashlib.sha256(f"{user_id}:{target_date}".encode()).digest()
            lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            await db.flush()
            start_datetime = start_of_day_hk(target_date)
            next_day = start_of_day_hk(target_date + timedelta(days=1))

            stats = await db.execute(
                select(
                    func.count(MealRecord.id).label("meals_count"),
                    func.coalesce(func.sum(MealRecord.total_calories), 0).label("total_calories"),
                    func.coalesce(func.sum(MealRecord.total_protein), 0).label("total_protein"),
                    func.coalesce(func.sum(MealRecord.total_carbs), 0).label("total_carbs"),
                    func.coalesce(func.sum(MealRecord.total_fat), 0).label("total_fat"),
                    func.coalesce(func.sum(MealRecord.total_fiber), 0).label("total_fiber"),
                    func.coalesce(
                        func.sum(
                            case(
                                (MealRecord.meal_type == MealType.BREAKFAST, MealRecord.total_calories),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("breakfast_calories"),
                    func.coalesce(
                        func.sum(
                            case(
                                (MealRecord.meal_type == MealType.LUNCH, MealRecord.total_calories),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("lunch_calories"),
                    func.coalesce(
                        func.sum(
                            case(
                                (MealRecord.meal_type == MealType.DINNER, MealRecord.total_calories),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("dinner_calories"),
                    func.coalesce(
                        func.sum(
                            case(
                                (MealRecord.meal_type == MealType.SNACK, MealRecord.total_calories),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("snack_calories"),
                )
                .where(
                    and_(
                        MealRecord.user_id == user_id,
                        MealRecord.meal_time >= start_datetime,
                        MealRecord.meal_time < next_day,
                    )
                )
            )
            row = stats.one()

            total_calories = float(row.total_calories or 0)
            total_protein = float(row.total_protein or 0)
            total_carbs = float(row.total_carbs or 0)
            total_fat = float(row.total_fat or 0)
            total_fiber = float(row.total_fiber or 0)
            breakfast_calories = float(row.breakfast_calories or 0)
            lunch_calories = float(row.lunch_calories or 0)
            dinner_calories = float(row.dinner_calories or 0)
            snack_calories = float(row.snack_calories or 0)

            meals_count = int(row.meals_count or 0)
            flags = self._calculate_nutrition_flags(
                total_calories, total_protein, total_carbs, total_fat, meals_count
            )

            summary_result = await db.execute(
                select(NutritionDailySummary).where(
                    and_(
                        NutritionDailySummary.user_id == user_id,
                        NutritionDailySummary.date == target_date
                    )
                )
            )
            summary = summary_result.scalar_one_or_none()

            if meals_count == 0:
                if summary:
                    await db.delete(summary)
                if commit:
                    await db.commit()
                else:
                    await db.flush()
                logger.info("Removed empty daily summary for %s", target_date)
                return None

            if summary:
                # 更新现有记录
                summary.total_calories = total_calories
                summary.total_protein = total_protein
                summary.total_carbs = total_carbs
                summary.total_fat = total_fat
                summary.total_fiber = total_fiber
                summary.meals_count = meals_count
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
                    meals_count=meals_count,
                    breakfast_calories=breakfast_calories,
                    lunch_calories=lunch_calories,
                    dinner_calories=dinner_calories,
                    snack_calories=snack_calories,
                    flags=flags
                )
                db.add(summary)

            if commit:
                await db.commit()
                await db.refresh(summary)
            else:
                await db.flush()

            logger.info(f"Updated daily summary for {target_date}: {total_calories}kcal")
            return summary

        except Exception as e:
            logger.error(f"Failed to update daily summary: {str(e)}", exc_info=True)
            if commit:
                await db.rollback()
            raise

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
        abs_photo_path = str(self.file_storage.get_absolute_path(photo_path))

        # 验证图片存在
        import os
        if not os.path.exists(abs_photo_path):
            raise ValueError("餐次原图不存在")

        # 获取用户上下文
        user_context = await self._get_user_context(
            db,
            user_id,
            before_time=meal.meal_time,
            exclude_meal_id=meal.id,
            include_history=False,
        )

        # 外部模型调用前释放只读事务和连接；ORM 配置为 expire_on_commit=False。
        await db.commit()

        # 重新调用 Codex Luna 分析（带重试）
        analysis_started_at = now_hk()
        meal_time_str = format_hk(meal.meal_time, "%Y-%m-%d %H:%M")
        analysis_result = await self.ai_service.analyze_meal_photo_with_retry(
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
        meal.ai_analysis = analysis_result
        meal.analysis_status = "completed"
        meal.recommendation_status = "pending"
        meal.recommendation_attempts = 0
        meal.analysis_error = None
        meal.analysis_started_at = analysis_started_at
        meal.analysis_completed_at = now_hk()
        meal.recommendation_updated_at = now_hk()

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

        # 更新每日营养汇总
        await self.update_daily_summary(db, user_id, date_hk(meal.meal_time), commit=False)
        await db.commit()

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
            end_date = today_hk()

        start_date = end_date - timedelta(days=6)

        result = await db.execute(
            select(NutritionDailySummary).where(
                and_(
                    NutritionDailySummary.user_id == user_id,
                    NutritionDailySummary.date >= start_date,
                    NutritionDailySummary.date <= end_date,
                    NutritionDailySummary.meals_count > 0,
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
