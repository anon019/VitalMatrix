"""
认证API - 微信登录、JWT生成
"""
import hmac
import logging
import hashlib
from typing import Literal, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt
import httpx

from app.database.session import get_db
from app.api.dependencies import resolve_primary_user
from app.config import settings
from app.utils.rate_limit import enforce_rate_limit

router = APIRouter()
logger = logging.getLogger(__name__)


class WeChatLoginRequest(BaseModel):
    """微信登录请求"""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=256)  # 微信登录code

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("code 不能为空")
        return value


class SimpleLoginRequest(BaseModel):
    """简易登录请求"""
    password: Optional[str] = None  # 可选密码


class AuthResponse(BaseModel):
    """认证响应"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_in: int
    auth_mode: Literal["fixed_miniprogram", "fixed_web"]
    is_new_user: bool = False


async def exchange_wechat_code(code: str) -> str:
    """使用一次性 code 换取 OpenID，不记录微信凭证或完整响应。"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.weixin.qq.com/sns/jscode2session",
                params={
                    "appid": settings.WECHAT_APP_ID,
                    "secret": settings.WECHAT_APP_SECRET,
                    "js_code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("微信登录上游请求失败: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信认证服务暂时不可用",
        ) from exc

    if data.get("errcode", 0) != 0:
        logger.info("微信登录 code 无效: errcode=%s", data.get("errcode"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="微信登录凭证无效或已过期",
        )

    openid = data.get("openid")
    if not isinstance(openid, str) or not openid.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信认证响应无效",
        )
    return openid.strip()


@router.post("/miniprogram-login", response_model=AuthResponse)
@router.post("/wechat-login", response_model=AuthResponse, deprecated=True)
async def miniprogram_login(
    request: WeChatLoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """微信静默认证：只允许绑定身份，并始终签发固定主用户 token。"""
    client_ip = http_request.client.host if http_request.client else "unknown"
    await enforce_rate_limit(f"auth:miniprogram:{client_ip}", limit=20, window_seconds=900)

    try:
        user = await resolve_primary_user(db, require_configured=True)
        openid = await exchange_wechat_code(request.code)
        if not hmac.compare_digest(openid, user.openid):
            fingerprint = hashlib.sha256(openid.encode("utf-8")).hexdigest()[:12]
            logger.warning("未授权微信账号尝试登录: openid_fingerprint=%s", fingerprint)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前微信账号未获授权",
            )

        access_token = create_access_token(user.id, auth_mode="fixed_miniprogram")
        logger.info("小程序固定用户登录成功: user_id=%s", user.id)

        return AuthResponse(
            access_token=access_token,
            user_id=str(user.id),
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
            auth_mode="fixed_miniprogram",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("微信登录异常: %s", type(e).__name__, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败，请稍后重试"
        )


@router.post("/simple-login", response_model=AuthResponse)
async def simple_login(
    request: SimpleLoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    简易登录 - 仅适用于 Web 前端

    如果配置了密码则验证，否则直接登录
    返回 7 天有效期的 token
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    await enforce_rate_limit(f"auth:simple:{client_ip}", limit=10, window_seconds=900)

    if settings.REQUIRE_WEB_ACCESS_PASSWORD and not settings.WEB_ACCESS_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web 登录尚未配置访问密码",
        )

    # 配置了密码时必须验证（使用常数时间比较防止时序攻击）。
    if settings.WEB_ACCESS_PASSWORD and not hmac.compare_digest(
        request.password or "", settings.WEB_ACCESS_PASSWORD
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误"
        )

    try:
        user = await resolve_primary_user(db)

        # 生成 7 天有效期的 token
        access_token = create_access_token(
            user.id,
            expires_days=7,
            auth_mode="fixed_web",
        )

        logger.info(f"简易登录成功: user_id={user.id}")

        return AuthResponse(
            access_token=access_token,
            user_id=str(user.id),
            expires_in=7 * 24 * 60 * 60,
            auth_mode="fixed_web",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"简易登录异常: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败"
        )


def create_access_token(
    user_id,
    expires_days: int = None,
    auth_mode: Literal["fixed_miniprogram", "fixed_web"] | None = None,
) -> str:
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

    issued_at = datetime.now(timezone.utc)
    expire = issued_at + expires_delta

    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "iat": issued_at,
    }
    if auth_mode is not None:
        to_encode["auth_mode"] = auth_mode

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt
