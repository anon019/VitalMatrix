"""
AI建议API
"""
import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.ai_service import AIService
from app.schemas.ai import RecommendationResponse, ChatRequest, ChatResponse
from app.utils.datetime_helper import today_hk
from app.utils.rate_limit import enforce_rate_limit

router = APIRouter()
logger = logging.getLogger(__name__)


def _recommendation_response(recommendation, requested_date: date) -> RecommendationResponse:
    """统一返回来源日期，避免历史回退被前端误认为当天建议。"""
    source_date = recommendation.date
    return RecommendationResponse(
        id=str(recommendation.id),
        date=source_date,
        provider=recommendation.provider,
        model=recommendation.model,
        summary=recommendation.summary,
        yesterday_review=recommendation.yesterday_review,
        today_recommendation=recommendation.today_recommendation,
        health_education=recommendation.health_education,
        created_at=recommendation.created_at.isoformat(),
        requested_date=requested_date,
        source_date=source_date,
        is_stale=source_date != requested_date,
        generation_metadata=recommendation.generation_metadata,
    )


class RegenerateRequest(BaseModel):
    """重新生成请求"""
    date: date
    provider: Optional[str] = None  # 可选：切换AI模型


@router.get("/recommendation/today", response_model=Optional[RecommendationResponse])
async def get_today_recommendation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取今日AI建议（纯查询，不生成）

    Returns:
        今日AI建议，如果不存在则返回None
    """
    try:
        ai_service = AIService(db)

        # 纯查询，不触发生成
        recommendation = await ai_service.get_recommendation(
            user_id=current_user.id,
            target_date=today_hk()
        )

        if not recommendation:
            logger.debug(f"今日建议不存在: user_id={current_user.id}")
            return None

        return _recommendation_response(recommendation, today_hk())

    except Exception as e:
        logger.error(f"获取AI建议失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取AI建议失败，请稍后重试"
        )


@router.get("/recommendation/{target_date}", response_model=Optional[RecommendationResponse])
async def get_recommendation_by_date(
    target_date: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定日期的AI建议

    Args:
        target_date: 目标日期

    Returns:
        AI建议（如不存在返回None）
    """
    try:
        ai_service = AIService(db)
        recommendation = await ai_service.get_recommendation(
            user_id=current_user.id,
            target_date=target_date,
            allow_fallback=False,
        )

        if not recommendation:
            return None

        return _recommendation_response(recommendation, target_date)

    except Exception as e:
        logger.error(f"获取AI建议失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取AI建议失败"
        )


@router.post("/regenerate", response_model=RecommendationResponse)
async def regenerate_recommendation(
    request: RegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    重新生成AI建议

    可选：切换AI模型

    Args:
        request: 重新生成请求

    Returns:
        新的AI建议
    """
    await enforce_rate_limit(
        f"ai:regenerate:{current_user.id}", limit=10, window_seconds=86400
    )
    try:
        ai_service = AIService(db)

        logger.info(
            f"重新生成AI建议: user_id={current_user.id}, "
            f"date={request.date}, provider={request.provider}"
        )

        recommendation = await ai_service.regenerate_recommendation(
            user_id=current_user.id,
            target_date=request.date,
            provider_name=request.provider
        )

        return _recommendation_response(recommendation, request.date)

    except Exception as e:
        logger.error(f"重新生成AI建议失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="重新生成失败，请稍后重试"
        )


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    AI对话

    可以询问训练相关问题

    Args:
        request: 对话请求（消息历史）

    Returns:
        AI回复
    """
    await enforce_rate_limit(
        f"ai:chat:{current_user.id}", limit=60, window_seconds=86400
    )
    try:
        ai_service = AIService(db)

        # 转换消息格式
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # 调用AI对话
        response = await ai_service.chat(
            user_id=current_user.id,
            messages=messages,
            provider_name=None,  # 使用默认Provider
            client_context=request.context,
        )

        return ChatResponse(
            message=response.message,
            usage=response.usage
        )

    except Exception as e:
        logger.error(f"AI对话失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI对话失败，请稍后重试"
        )
