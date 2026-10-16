"""Verify official collection paths and response shape handling without network."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.integrations.polar.client import PolarClient
from app.integrations.oura.client import OuraClient


@pytest.mark.asyncio
async def test_polar_empty_heart_rates_are_not_a_measured_record():
    client = PolarClient()
    client._make_request = AsyncMock(return_value={"heart_rates": []})
    try:
        rows = await client.get_research_collection(
            "continuous_heart_rate", "token", date(2026, 10, 1), date(2026, 10, 2)
        )
        assert rows == []
        assert client._make_request.call_args.kwargs["params"] == {
            "from": "2026-10-01",
            "to": "2026-10-02",
        }
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_polar_sleep_collection_is_complete_and_normalizes_provider_keys():
    client = PolarClient()
    client._make_request = AsyncMock(
        return_value={
            "nights": [
                {"date": "2026-10-01", "polar_user": "device-user", "sleep_score": 80}
            ]
        }
    )
    try:
        rows = await client.get_sleep_data(
            "token", date(2026, 10, 1), date(2026, 10, 2)
        )
        assert rows[0]["polar-user"] == "device-user"
        assert client._make_request.call_args.args[1].endswith("/users/sleep")
        assert client._make_request.await_count == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_oura_sessions_follow_collection_pagination():
    client = OuraClient()
    client._make_request = AsyncMock(
        side_effect=[
            {"data": [{"id": "one"}], "next_token": "two"},
            {"data": [{"id": "two"}]},
        ]
    )
    try:
        rows = await client.get_sessions("token", date(2026, 10, 1), date(2026, 10, 2))
        assert [r["id"] for r in rows] == ["one", "two"]
        assert client._make_request.call_args.args[1] == "/usercollection/session"
    finally:
        await client.close()
