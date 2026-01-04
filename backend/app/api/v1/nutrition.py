"""
营养模块API端点
"""
import logging
from datetime import datetime, date
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.nutrition import MealType
from app.services.nutrition_service import get_nutrition_service
from app.schemas.nutrition import (
    MealRecordResponse,
    MealListResponse,
    NutritionDailySummaryResponse,
    WeeklyNutritionTrend,
    DeleteResponse,
    MealTypeEnum
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nutrition", tags=["营养饮食"])

nutrition_service = get_nutrition_service()


@router.post("/upload", response_model=MealRecordResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_analyze_meal(
    image: UploadFile = File(..., description="餐食照片"),
    meal_type: MealTypeEnum = Form(..., description="餐次类型"),
    meal_time: Optional[str] = Form(None, description="用餐时间（格式：2025-11-22 12:30）"),
    notes: Optional[str] = Form(None, description="用户备注"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    上传餐食照片并自动分析保存

    完整流程：
    1. 上传照片
    2. Gemini自动分析
    3. 保存餐次记录和食物明细
    4. 更新每日营养汇总

    Returns:
        完整的餐次记录（包含食物明细）
    """
    try:
        # 验证文件类型
        if not image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只支持图片文件"
            )

        # 解析用餐时间
        if meal_time:
            try:
                parsed_meal_time = datetime.strptime(meal_time, "%Y-%m-%d %H:%M")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="meal_time格式错误，应为：YYYY-MM-DD HH:MM"
                )
        else:
            parsed_meal_time = datetime.now()

        # 读取图片内容
        image_content = await image.read()

        # 调用服务分析并保存
        result = await nutrition_service.analyze_and_save_meal(
            db=db,
            user_id=current_user.id,
            meal_type=MealType(meal_type.value),
            meal_time=parsed_meal_time,
            image_content=image_content,
            notes=notes
        )

        # 返回餐次记录
        meal_record = result["meal_record"]

        logger.info(f"User {current_user.id} uploaded meal {meal_record.id}")

        return meal_record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload and analyze meal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析失败：{str(e)}"
        )


@router.get("/meals", response_model=MealListResponse)
async def get_meals_list(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[MealTypeEnum] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取餐次列表（分页）

    Query Parameters:
        - start_date: 开始日期（YYYY-MM-DD）
        - end_date: 结束日期（YYYY-MM-DD）
        - meal_type: 餐次类型（breakfast/lunch/dinner/snack）
        - page: 页码（从1开始）
        - page_size: 每页数量（默认20）

    Returns:
        餐次列表和分页信息
    """
    try:
        meals, total = await nutrition_service.get_meals_list(
            db=db,
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            meal_type=MealType(meal_type.value) if meal_type else None,
            page=page,
            page_size=page_size
        )

        return {
            "meals": meals,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Failed to get meals list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取列表失败：{str(e)}"
        )


@router.get("/meals/{meal_id}", response_model=MealRecordResponse)
async def get_meal_detail(
    meal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取餐次详情

    Path Parameters:
        - meal_id: 餐次ID

    Returns:
        餐次详细信息（包含食物明细）
    """
    try:
        meal = await nutrition_service.get_meal_by_id(
            db=db,
            meal_id=meal_id,
            user_id=current_user.id
        )

        if not meal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="餐次记录不存在"
            )

        return meal

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get meal detail: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取详情失败：{str(e)}"
        )


@router.post("/meals/{meal_id}/reanalyze", response_model=MealRecordResponse)
async def reanalyze_meal(
    meal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    重新分析餐次照片

    当AI分析失败或结果不准确时，可以调用此接口重新分析

    Path Parameters:
        - meal_id: 餐次ID

    Returns:
        重新分析后的餐次记录
    """
    try:
        meal = await nutrition_service.reanalyze_meal(
            db=db,
            meal_id=meal_id,
            user_id=current_user.id
        )

        logger.info(f"User {current_user.id} reanalyzed meal {meal_id}")

        return meal

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to reanalyze meal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新分析失败：{str(e)}"
        )


@router.delete("/meals/{meal_id}", response_model=DeleteResponse)
async def delete_meal(
    meal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    删除餐次记录

    Path Parameters:
        - meal_id: 餐次ID

    Returns:
        删除结果
    """
    try:
        success = await nutrition_service.delete_meal(
            db=db,
            meal_id=meal_id,
            user_id=current_user.id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="餐次记录不存在或删除失败"
            )

        return {
            "status": "success",
            "message": "餐次记录已删除",
            "deleted_id": meal_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete meal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除失败：{str(e)}"
        )


@router.get("/daily/{target_date}", response_model=NutritionDailySummaryResponse)
async def get_daily_summary(
    target_date: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定日期的营养汇总

    Path Parameters:
        - target_date: 目标日期（YYYY-MM-DD）

    Returns:
        每日营养汇总
    """
    try:
        summary = await nutrition_service.get_daily_summary(
            db=db,
            user_id=current_user.id,
            target_date=target_date
        )

        if not summary:
            # 如果没有汇总，可能是当天还没有餐次记录
            # 尝试计算并创建
            summary = await nutrition_service.update_daily_summary(
                db=db,
                user_id=current_user.id,
                target_date=target_date
            )

        return summary

    except Exception as e:
        logger.error(f"Failed to get daily summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取汇总失败：{str(e)}"
        )


@router.get("/weekly", response_model=WeeklyNutritionTrend)
async def get_weekly_trend(
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取7日营养趋势

    Query Parameters:
        - end_date: 结束日期（默认今天）

    Returns:
        7天营养趋势数据
    """
    try:
        from datetime import timedelta

        if not end_date:
            end_date = date.today()

        start_date = end_date - timedelta(days=6)

        # 获取7天数据
        daily_data = await nutrition_service.get_weekly_trend(
            db=db,
            user_id=current_user.id,
            end_date=end_date
        )

        # 计算周平均
        if daily_data:
            weekly_avg_calories = sum(d.total_calories or 0 for d in daily_data) / len(daily_data)
            weekly_avg_protein = sum(d.total_protein or 0 for d in daily_data) / len(daily_data)
            weekly_avg_carbs = sum(d.total_carbs or 0 for d in daily_data) / len(daily_data)
            weekly_avg_fat = sum(d.total_fat or 0 for d in daily_data) / len(daily_data)
        else:
            weekly_avg_calories = weekly_avg_protein = weekly_avg_carbs = weekly_avg_fat = 0

        return {
            "start_date": start_date,
            "end_date": end_date,
            "daily_data": daily_data,
            "weekly_avg_calories": round(weekly_avg_calories, 2),
            "weekly_avg_protein": round(weekly_avg_protein, 2),
            "weekly_avg_carbs": round(weekly_avg_carbs, 2),
            "weekly_avg_fat": round(weekly_avg_fat, 2)
        }

    except Exception as e:
        logger.error(f"Failed to get weekly trend: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取趋势失败：{str(e)}"
        )


@router.get("/foods", response_model=list)
async def get_foods_list(
    meal_id: Optional[uuid.UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取食物明细列表

    Query Parameters:
        - meal_id: 餐次ID（可选，获取指定餐次的食物）
        - start_date: 开始日期（可选）
        - end_date: 结束日期（可选）

    Returns:
        食物明细列表
    """
    try:
        # 如果指定了meal_id，直接返回该餐次的食物
        if meal_id:
            meal = await nutrition_service.get_meal_by_id(
                db=db,
                meal_id=meal_id,
                user_id=current_user.id
            )
            if not meal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="餐次记录不存在"
                )
            return meal.food_items

        # 否则获取时间范围内所有餐次的食物
        meals, _ = await nutrition_service.get_meals_list(
            db=db,
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            page=1,
            page_size=1000  # 大数量，获取所有
        )

        # 汇总所有食物
        all_foods = []
        for meal in meals:
            all_foods.extend(meal.food_items)

        return all_foods

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get foods list: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取食物列表失败：{str(e)}"
        )
