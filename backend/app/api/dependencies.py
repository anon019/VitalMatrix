"""
API依赖项
"""
import hmac
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database.session import get_db
from app.models.user import User
from app.config import settings

# JWT Bearer认证
security = HTTPBearer()

# API Key认证（用于MCP）
api_key_header = HTTPBearer(auto_error=False)


def get_configured_primary_user_id(*, required: bool = False) -> uuid.UUID | None:
    """读取固定单用户 ID，并对新旧配置冲突 fail closed。"""
    primary_value = settings.PRIMARY_USER_ID.strip()
    legacy_value = settings.DEFAULT_USER_ID.strip()

    if not primary_value and not legacy_value:
        if required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="主用户尚未配置",
            )
        return None

    try:
        primary_id = uuid.UUID(primary_value) if primary_value else None
        legacy_id = uuid.UUID(legacy_value) if legacy_value else None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="主用户配置无效",
        ) from exc

    if primary_id is not None and legacy_id is not None and primary_id != legacy_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="主用户配置冲突",
        )
    return primary_id or legacy_id


async def verify_mcp_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(api_key_header)
) -> bool:
    """
    验证MCP API Key

    Args:
        credentials: API Key凭证

    Returns:
        验证成功返回True

    Raises:
        HTTPException: API Key无效
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少API Key",
        )

    # 使用常数时间比较防止时序攻击
    if not hmac.compare_digest(credentials.credentials, settings.MCP_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的API Key",
        )

    return True


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    获取当前登录用户

    Args:
        credentials: JWT凭证
        db: 数据库会话

    Returns:
        当前用户对象

    Raises:
        HTTPException: 认证失败
    """
    token = credentials.credentials

    # 解析JWT
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id_str = payload.get("sub")
        if not isinstance(user_id_str, str) or not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证凭证",
            )
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
        )

    primary_user_id = get_configured_primary_user_id(required=True)
    if primary_user_id is not None and user_id != primary_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
        )

    # 查询用户
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    return user


async def resolve_primary_user(
    db: AsyncSession,
    *,
    require_configured: bool = True,
) -> User:
    """解析固定单用户；配置存在时绝不回退到任意数据库记录。"""
    user_id = get_configured_primary_user_id(required=require_configured)

    if user_id is not None:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="主用户不存在",
            )
        return user

    result = await db.execute(
        select(User)
        .order_by(User.created_at.asc(), User.id.asc())
        .limit(2)
    )
    users = result.scalars().all()

    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="系统中没有用户",
        )

    if len(users) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="检测到多个用户，请配置 PRIMARY_USER_ID",
        )

    return users[0]


async def resolve_default_user(db: AsyncSession) -> User:
    """兼容旧调用方；统一委托给固定主用户解析器。"""
    return await resolve_primary_user(db)
