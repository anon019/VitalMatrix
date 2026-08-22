"""
营养模块API端点
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional
import uuid

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form,
    Query, status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.config import settings
from app.models.user import User
from app.models.nutrition import MealType
from app.services.nutrition_service import get_nutrition_service
from app.services.poster_service import get_poster_service
from app.schemas.nutrition import (
    MealRecordResponse,
    MealListResponse,
    NutritionDailySummaryResponse,
    WeeklyNutritionTrend,
    DeleteResponse,
    MealTypeEnum,
    MealPosterResponse,
)
from app.utils.datetime_helper import now_hk, today_hk, HK_TZ
from app.utils.media_url import verify_signed_media_url
from app.utils.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nutrition", tags=["营养饮食"])

nutrition_service = get_nutrition_service()


@router.get("/media", response_class=FileResponse)
async def get_signed_nutrition_media(
    path: str = Query(...),
    expires: int = Query(...),
    signature: str = Query(..., min_length=64, max_length=64),
):
    """通过短期 HMAC URL 读取私有餐食照片或分享海报。"""
    normalized = verify_signed_media_url(path, expires, signature)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="媒体链接无效或已过期")
    try:
        file_path = nutrition_service.file_storage.get_absolute_path(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="媒体路径无效") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="媒体文件不存在")
    return FileResponse(
        file_path,
        media_type="image/png" if file_path.suffix.lower() == ".png" else "image/jpeg",
        headers={"Cache-Control": f"private, max-age={settings.MEDIA_URL_TTL_SECONDS}"},
    )


@router.post("/upload", response_model=MealRecordResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_analyze_meal(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="餐食照片"),
    meal_type: MealTypeEnum = Form(..., description="餐次类型"),
    meal_time: Optional[str] = Form(None, description="用餐时间（格式：2025-11-22 12:30）"),
    notes: Optional[str] = Form(None, max_length=500, description="用户备注"),
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
    await enforce_rate_limit(
        f"nutrition:upload:{current_user.id}", limit=20, window_seconds=86400
    )
    try:
        # 验证文件类型
        if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只支持 JPEG、PNG 或 WebP 图片"
            )

        # 验证文件大小（最大 10MB）
        max_size = 10 * 1024 * 1024  # 10MB
        # 只读取上限+1字节，避免恶意大文件在应用层占用过多内存。
        image_content = await image.read(max_size + 1)
        if len(image_content) > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件过大，最大支持 10MB"
            )

        # 解析用餐时间
        if meal_time:
            try:
                parsed_meal_time = HK_TZ.localize(
                    datetime.strptime(meal_time, "%Y-%m-%d %H:%M")
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="meal_time格式错误，应为：YYYY-MM-DD HH:MM"
                )
        else:
            parsed_meal_time = now_hk()

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
        if meal_record.recommendation_status != "completed":
            background_tasks.add_task(
                nutrition_service.generate_recommendations_for_meal,
                meal_record.id,
                current_user.id,
            )

        logger.info(f"User {current_user.id} uploaded meal {meal_record.id}")

        return meal_record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload and analyze meal: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="餐食分析失败，请稍后重试"
        )


@router.get("/meals", response_model=MealListResponse)
async def get_meals_list(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    meal_type: Optional[MealTypeEnum] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
            detail="获取餐食列表失败，请稍后重试"
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
            detail="获取餐食详情失败，请稍后重试"
        )


@router.post("/meals/{meal_id}/poster", response_model=MealPosterResponse)
async def generate_meal_poster(
    meal_id: uuid.UUID,
    force: bool = Query(False, description="是否忽略同内容缓存并重新生成"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户点击后才生成分享海报；相同内容默认复用，避免重复计费。"""
    meal = await nutrition_service.get_meal_by_id(
        db=db,
        meal_id=meal_id,
        user_id=current_user.id,
    )
    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="餐次记录不存在",
        )

    await enforce_rate_limit(
        f"nutrition:poster-request:{current_user.id}", limit=30, window_seconds=86400
    )

    try:
        # 外部图片生成耗时较长，先释放数据库连接。
        await db.commit()
        return await get_poster_service().generate(meal, force=force)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "Failed to generate poster for meal %s: %s",
            meal_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="海报生成失败，请稍后重试",
        ) from exc


@router.post("/meals/{meal_id}/reanalyze", response_model=MealRecordResponse)
async def reanalyze_meal(
    background_tasks: BackgroundTasks,
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
    await enforce_rate_limit(
        f"nutrition:reanalyze:{current_user.id}", limit=10, window_seconds=86400
    )
    try:
        meal = await nutrition_service.reanalyze_meal(
            db=db,
            meal_id=meal_id,
            user_id=current_user.id
        )

        logger.info(f"User {current_user.id} reanalyzed meal {meal_id}")

        background_tasks.add_task(
            nutrition_service.generate_recommendations_for_meal,
            meal.id,
            current_user.id,
        )

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
            detail="重新分析失败，请稍后重试"
        )


@router.get("/meals/{meal_id}/analysis-status")
async def get_meal_analysis_status(
    meal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询核心识图和扩展建议状态，供小程序轻量轮询。"""
    analysis_status = await nutrition_service.get_meal_analysis_status(
        db, meal_id, current_user.id
    )
    if not analysis_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="餐次记录不存在")
    return analysis_status


@router.post("/meals/{meal_id}/recommendations", status_code=status.HTTP_202_ACCEPTED)
async def generate_meal_recommendations(
    meal_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    force: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单独触发扩展建议；不重复上传或重新识图。"""
    analysis_status = await nutrition_service.get_meal_analysis_status(
        db, meal_id, current_user.id
    )
    if not analysis_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="餐次记录不存在")
    if analysis_status["analysis_status"] != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="核心识图尚未完成")
    should_generate = force or analysis_status["recommendation_status"] != "completed"
    if should_generate:
        background_tasks.add_task(
            nutrition_service.generate_recommendations_for_meal,
            meal_id,
            current_user.id,
            force,
        )
    return {
        "meal_id": str(meal_id),
        "analysis_status": analysis_status["analysis_status"],
        "recommendation_status": (
            "pending" if should_generate else "completed"
        ),
    }


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
            detail="删除餐次失败，请稍后重试"
        )


@router.get("/daily/{target_date}", response_model=Optional[NutritionDailySummaryResponse])
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
            detail="获取营养汇总失败，请稍后重试"
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
        if not end_date:
            end_date = today_hk()

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
            "weekly_avg_fat": round(weekly_avg_fat, 2),
            "recorded_days": len(daily_data),
            "expected_days": 7,
        }

    except Exception as e:
        logger.error(f"Failed to get weekly trend: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取营养趋势失败，请稍后重试"
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
            detail="获取食物列表失败，请稍后重试"
        )
