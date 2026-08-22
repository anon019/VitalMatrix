from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.oura.client import OuraAPIError, OuraClient


@pytest.mark.asyncio
async def test_preserves_http_status_for_token_recovery():
    client = OuraClient()
    request = httpx.Request(
        "GET",
        "https://api.ouraring.com/v2/usercollection/personal_info",
    )
    client.http_client.request = AsyncMock(
        return_value=httpx.Response(
            401,
            request=request,
            json={"detail": "expired"},
        )
    )

    try:
        with pytest.raises(OuraAPIError) as exc_info:
            await client.validate_access_token("expired-token")
    finally:
        await client.close()

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_vo2_max_uses_case_sensitive_api_path():
    client = OuraClient()
    client._make_request = AsyncMock(return_value={"data": []})

    try:
        result = await client.get_vo2_max(
            "token",
            date(2026, 7, 25),
            date(2026, 7, 27),
        )
    finally:
        await client.close()

    assert result == []
    assert client._make_request.await_args.args[1] == "/usercollection/vO2_max"


@pytest.mark.asyncio
async def test_collection_pagination_follows_next_token():
    client = OuraClient()
    client._make_request = AsyncMock(
        side_effect=[
            {"data": [{"id": "first"}], "next_token": "page-2"},
            {"data": [{"id": "second"}]},
        ]
    )

    try:
        result = await client._get_paginated_collection(
            "/usercollection/workout",
            "token",
            {"start_date": "2026-01-01", "end_date": "2026-07-27"},
        )
    finally:
        await client.close()

    assert [item["id"] for item in result] == ["first", "second"]
    assert client._make_request.await_args_list[1].kwargs["params"]["next_token"] == "page-2"


@pytest.mark.asyncio
async def test_collection_pagination_rejects_repeated_token():
    client = OuraClient()
    client._make_request = AsyncMock(
        side_effect=[
            {"data": [], "next_token": "same"},
            {"data": [], "next_token": "same"},
        ]
    )

    try:
        with pytest.raises(OuraAPIError, match="分页令牌重复"):
            await client._get_paginated_collection(
                "/usercollection/workout", "token", {}
            )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_capability_probe_keeps_endpoint_401_isolated():
    client = OuraClient()

    async def fake_request(_method, endpoint, _token, **_kwargs):
        if endpoint == "/usercollection/ring_configuration":
            raise OuraAPIError("forbidden", status_code=401)
        return {"data": []}

    client._make_request = AsyncMock(side_effect=fake_request)
    try:
        result = await client.probe_capabilities("token", date(2026, 7, 27))
    finally:
        await client.close()

    assert result["workout"] == {"available": True, "status_code": 200}
    assert result["ring_configuration"] == {
        "available": False,
        "status_code": 401,
    }
