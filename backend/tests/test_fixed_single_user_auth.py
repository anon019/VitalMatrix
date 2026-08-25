"""固定单用户认证边界的回归测试。"""
from __future__ import annotations

from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from pydantic import ValidationError
from starlette.requests import Request

from app.api.dependencies import get_configured_primary_user_id, get_current_user
from app.api.v1 import auth
from app.config import settings
from app.mcp.tools import get_default_user as get_embedded_mcp_user


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _ReadOnlyDB:
    def __init__(self, user):
        self.user = user
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        return _Result(self.user)

    def add(self, _value):
        raise AssertionError("认证流程不得创建用户")

    async def commit(self):
        raise AssertionError("认证流程不得写入数据库")


def _request() -> Request:
    return Request({"type": "http", "client": ("127.0.0.1", 12345)})


def _configure_primary(monkeypatch, user_id: uuid.UUID) -> None:
    monkeypatch.setattr(settings, "PRIMARY_USER_ID", str(user_id))
    monkeypatch.setattr(settings, "DEFAULT_USER_ID", "")


@pytest.mark.asyncio
async def test_allowed_wechat_identity_gets_primary_user_token(monkeypatch):
    primary = SimpleNamespace(id=uuid.uuid4(), openid="allowed-openid")
    db = _ReadOnlyDB(primary)
    _configure_primary(monkeypatch, primary.id)

    async def exchange(_code):
        return primary.openid

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth, "exchange_wechat_code", exchange)
    monkeypatch.setattr(auth, "enforce_rate_limit", no_rate_limit)

    response = await auth.miniprogram_login(
        auth.WeChatLoginRequest(code="valid-code"),
        _request(),
        db,
    )
    payload = jwt.decode(
        response.access_token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert response.user_id == str(primary.id)
    assert response.auth_mode == "fixed_miniprogram"
    assert response.is_new_user is False
    assert payload["sub"] == str(primary.id)
    assert payload["auth_mode"] == "fixed_miniprogram"
    assert db.execute_count == 1


@pytest.mark.asyncio
async def test_unknown_wechat_identity_is_forbidden_without_database_write(monkeypatch):
    primary = SimpleNamespace(id=uuid.uuid4(), openid="allowed-openid")
    db = _ReadOnlyDB(primary)
    _configure_primary(monkeypatch, primary.id)

    async def exchange(_code):
        return "different-openid"

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth, "exchange_wechat_code", exchange)
    monkeypatch.setattr(auth, "enforce_rate_limit", no_rate_limit)

    with pytest.raises(HTTPException) as exc_info:
        await auth.miniprogram_login(
            auth.WeChatLoginRequest(code="valid-code"),
            _request(),
            db,
        )

    assert exc_info.value.status_code == 403
    assert db.execute_count == 1


@pytest.mark.asyncio
async def test_repeated_miniprogram_login_never_creates_users(monkeypatch):
    primary = SimpleNamespace(id=uuid.uuid4(), openid="allowed-openid")
    db = _ReadOnlyDB(primary)
    _configure_primary(monkeypatch, primary.id)

    async def exchange(_code):
        return primary.openid

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth, "exchange_wechat_code", exchange)
    monkeypatch.setattr(auth, "enforce_rate_limit", no_rate_limit)

    for _ in range(3):
        response = await auth.miniprogram_login(
            auth.WeChatLoginRequest(code="valid-code"),
            _request(),
            db,
        )
        assert response.user_id == str(primary.id)

    assert db.execute_count == 3


@pytest.mark.asyncio
async def test_missing_primary_configuration_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "PRIMARY_USER_ID", "")
    monkeypatch.setattr(settings, "DEFAULT_USER_ID", "")

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth, "enforce_rate_limit", no_rate_limit)

    with pytest.raises(HTTPException) as exc_info:
        await auth.miniprogram_login(
            auth.WeChatLoginRequest(code="valid-code"),
            _request(),
            _ReadOnlyDB(None),
        )

    assert exc_info.value.status_code == 503


def test_miniprogram_login_rejects_web_password_field():
    with pytest.raises(ValidationError):
        auth.WeChatLoginRequest.model_validate(
            {"code": "valid-code", "password": "must-not-be-accepted"}
        )


def test_equivalent_primary_uuid_spellings_do_not_conflict(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "PRIMARY_USER_ID", str(user_id))
    monkeypatch.setattr(settings, "DEFAULT_USER_ID", user_id.hex.upper())

    assert get_configured_primary_user_id(required=True) == user_id


@pytest.mark.asyncio
async def test_non_primary_legacy_token_is_rejected_before_database_lookup(monkeypatch):
    primary_id = uuid.uuid4()
    other_id = uuid.uuid4()
    _configure_primary(monkeypatch, primary_id)
    token = auth.create_access_token(other_id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = _ReadOnlyDB(SimpleNamespace(id=other_id))

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == 401
    assert db.execute_count == 0


@pytest.mark.asyncio
async def test_web_password_login_still_issues_primary_token(monkeypatch):
    primary = SimpleNamespace(id=uuid.uuid4(), openid="allowed-openid")
    db = _ReadOnlyDB(primary)
    _configure_primary(monkeypatch, primary.id)
    monkeypatch.setattr(settings, "WEB_ACCESS_PASSWORD", "correct-password")
    monkeypatch.setattr(settings, "REQUIRE_WEB_ACCESS_PASSWORD", True)

    async def no_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth, "enforce_rate_limit", no_rate_limit)
    response = await auth.simple_login(
        auth.SimpleLoginRequest(password="correct-password"),
        _request(),
        db,
    )

    assert response.user_id == str(primary.id)
    assert response.auth_mode == "fixed_web"


@pytest.mark.asyncio
async def test_embedded_mcp_uses_configured_primary_user(monkeypatch):
    primary = SimpleNamespace(id=uuid.uuid4(), openid="allowed-openid")
    _configure_primary(monkeypatch, primary.id)
    db = _ReadOnlyDB(primary)

    resolved = await get_embedded_mcp_user(db)

    assert resolved is primary
    assert db.execute_count == 1
