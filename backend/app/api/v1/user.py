"""
用户API
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.api.dependencies import get_current_user
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


class UserProfileResponse(BaseModel):
    """用户信息响应"""
    user_id: str
    nickname: Optional[str]
    avatar_url: Optional[str]
    hr_max: Optional[int]
    resting_hr: Optional[int]
    weight: Optional[float]
    height: Optional[int]
    gender: Optional[str]
    birth_year: Optional[int]
    birth_month: Optional[int]
    health_goal: Optional[str]
    training_plan: Optional[str]


class UpdateProfileRequest(BaseModel):
    """更新用户信息请求"""
    nickname: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)
    hr_max: Optional[int] = Field(None, ge=80, le=240)
    resting_hr: Optional[int] = Field(None, ge=25, le=150)
    weight: Optional[float] = Field(None, ge=20, le=350)
    height: Optional[int] = Field(None, ge=80, le=250)
    gender: Optional[str] = Field(None, pattern="^(男|女|其他|不愿透露)$", max_length=20)
    birth_year: Optional[int] = Field(None, ge=1900, le=2100)
    birth_month: Optional[int] = Field(None, ge=1, le=12)
    health_goal: Optional[str] = Field(None, max_length=500)
    training_plan: Optional[str] = Field(None, max_length=200)


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    获取用户信息

    Returns:
        用户信息
    """
    return UserProfileResponse(
        user_id=str(current_user.id),
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url,
        hr_max=current_user.hr_max,
        resting_hr=current_user.resting_hr,
        weight=current_user.weight,
        height=current_user.height,
        gender=current_user.gender,
        birth_year=current_user.birth_year,
        birth_month=current_user.birth_month,
        health_goal=current_user.health_goal,
        training_plan=current_user.training_plan,
    )


@router.put("/profile", response_model=UserProfileResponse)
async def update_user_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    更新用户信息

    Args:
        request: 更新请求

    Returns:
        更新后的用户信息
    """
    try:
        # 更新字段
        if request.nickname is not None:
            current_user.nickname = request.nickname
        if request.avatar_url is not None:
            current_user.avatar_url = request.avatar_url
        if request.hr_max is not None:
            current_user.hr_max = request.hr_max
        if request.resting_hr is not None:
            current_user.resting_hr = request.resting_hr
        if request.weight is not None:
            current_user.weight = request.weight
        if request.height is not None:
            current_user.height = request.height
        if request.gender is not None:
            current_user.gender = request.gender
        if request.birth_year is not None:
            current_user.birth_year = request.birth_year
        if request.birth_month is not None:
            current_user.birth_month = request.birth_month
        if request.health_goal is not None:
            current_user.health_goal = request.health_goal
        if request.training_plan is not None:
            current_user.training_plan = request.training_plan

        # 保存到数据库
        await db.commit()
        await db.refresh(current_user)

        logger.info(f"用户信息更新成功: user_id={current_user.id}")

        return UserProfileResponse(
            user_id=str(current_user.id),
            nickname=current_user.nickname,
            avatar_url=current_user.avatar_url,
            hr_max=current_user.hr_max,
            resting_hr=current_user.resting_hr,
            weight=current_user.weight,
            height=current_user.height,
            gender=current_user.gender,
            birth_year=current_user.birth_year,
            birth_month=current_user.birth_month,
            health_goal=current_user.health_goal,
            training_plan=current_user.training_plan,
        )

    except Exception as e:
        logger.error(f"用户信息更新失败: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新失败，请稍后重试"
        )
