"""为私有营养图片生成短期签名 URL。"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from app.config import settings


MEDIA_ROUTE = "/api/v1/nutrition/media"


def normalize_media_path(path: str) -> str:
    """把数据库中的 Web 路径规范化为存储根目录下的相对路径。"""
    value = (path or "").strip()
    if value.startswith("/uploads/nutrition/"):
        value = value[len("/uploads/nutrition/"):]
    elif value.startswith("uploads/nutrition/"):
        value = value[len("uploads/nutrition/"):]
    return value.lstrip("/")


def _signature(path: str, expires: int) -> str:
    payload = f"{path}\n{expires}".encode("utf-8")
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def create_signed_media_url(path: str, ttl_seconds: int | None = None) -> str:
    """生成浏览器和小程序可直接加载的限时 URL。"""
    if not path or path.startswith(MEDIA_ROUTE):
        return path
    normalized = normalize_media_path(path)
    expires = int(time.time()) + (ttl_seconds or settings.MEDIA_URL_TTL_SECONDS)
    query = urlencode({
        "path": normalized,
        "expires": expires,
        "signature": _signature(normalized, expires),
    })
    return f"{MEDIA_ROUTE}?{query}"


def verify_signed_media_url(path: str, expires: int, signature: str) -> str | None:
    """验证签名和有效期，成功时返回规范化相对路径。"""
    normalized = normalize_media_path(path)
    if not normalized or expires < int(time.time()):
        return None
    if not hmac.compare_digest(_signature(normalized, expires), signature):
        return None
    return normalized
