"""
认证API - 微信登录、JWT生成
"""
import logging
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt
import httpx

from app.database.session import get_db
from app.models.user import User
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class WeChatLoginRequest(BaseModel):
    """微信登录请求"""
    code: str  # 微信登录code


class SimpleLoginRequest(BaseModel):
    """简易登录请求"""
    password: Optional[str] = None  # 可选密码


class AuthResponse(BaseModel):
    """认证响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    is_new_user: bool


@router.post("/wechat-login", response_model=AuthResponse)
async def wechat_login(
    request: WeChatLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    微信小程序登录

    流程:
    1. 用code换取openid
    2. 查询或创建用户
    3. 生成JWT token
    """
    try:
        # 1. 调用微信API获取openid
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.WECHAT_APP_ID,
                    "secret": settings.WECHAT_APP_SECRET,
                    "js_code": request.code,
                    "grant_type": "authorization_code",
                }
            )
            data = response.json()

        if "errcode" in data and data["errcode"] != 0:
            logger.error(f"微信登录失败: {data}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"微信登录失败: {data.get('errmsg', '未知错误')}"
            )

        openid = data.get("openid")
        if not openid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="获取openid失败"
            )

        # 2. 查询或创建用户
        result = await db.execute(
            select(User).where(User.openid == openid)
        )
        user = result.scalar_one_or_none()

        is_new_user = False
        if not user:
            # 创建新用户
            user = User(
                openid=openid,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            is_new_user = True
            logger.info(f"新用户注册: openid={openid}, user_id={user.id}")
        else:
            logger.info(f"用户登录: openid={openid}, user_id={user.id}")

        # 3. 生成JWT token
        access_token = create_access_token(user.id)

        return AuthResponse(
            access_token=access_token,
            user_id=str(user.id),
            is_new_user=is_new_user
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"微信登录异常: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败，请稍后重试"
        )


@router.post("/simple-login", response_model=AuthResponse)
async def simple_login(
    request: SimpleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    简易登录 - 适用于单用户场景（Web 前端 / 微信小程序）

    如果配置了密码则验证，否则直接登录
    返回 7 天有效期的 token
    """
    # 如果配置了密码，则需要验证
    if settings.WEB_ACCESS_PASSWORD:
        if request.password != settings.WEB_ACCESS_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="密码错误"
            )

    try:
        # 查询第一个用户
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="系统中没有用户"
            )

        # 生成 7 天有效期的 token
        access_token = create_access_token(user.id, expires_days=7)

        logger.info(f"简易登录成功: user_id={user.id}")

        return AuthResponse(
            access_token=access_token,
            user_id=str(user.id),
            is_new_user=False
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"简易登录异常: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败"
        )


def create_access_token(user_id, expires_days: int = None) -> str:
    """
    创建JWT访问令牌

    Args:
        user_id: 用户ID
        expires_days: 过期天数（可选，默认使用配置中的分钟数）

    Returns:
        JWT token
    """
    if expires_days:
        expires_delta = timedelta(days=expires_days)
    else:
        expires_delta = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)

    expire = datetime.utcnow() + expires_delta

    to_encode = {
        "sub": str(user_id),
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt
