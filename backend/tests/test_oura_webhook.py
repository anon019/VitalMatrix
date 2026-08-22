import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import oura


def _test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(oura.router)
    return app


def test_webhook_challenge_uses_derived_secret(monkeypatch):
    monkeypatch.setattr(oura.settings, "OURA_CLIENT_SECRET", "client-secret")
    client = TestClient(_test_app())

    response = client.get(
        "/webhook",
        params={
            "verification_token": oura._webhook_verification_token(),
            "challenge": "oura-challenge",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"challenge": "oura-challenge"}


def test_webhook_signature_and_background_dispatch(monkeypatch):
    monkeypatch.setattr(oura.settings, "OURA_CLIENT_SECRET", "client-secret")
    processor = AsyncMock()
    monkeypatch.setattr(oura, "_process_oura_webhook", processor)
    client = TestClient(_test_app())
    payload = {
        "event_type": "update",
        "data_type": "sleep",
        "object_id": "sleep-id",
        "event_time": "2026-07-27T06:00:00Z",
        "user_id": "oura-user-id",
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = "1785132000"
    signature = hmac.new(
        b"client-secret", timestamp.encode() + body, hashlib.sha256
    ).hexdigest().upper()

    response = client.post(
        "/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-oura-timestamp": timestamp,
            "x-oura-signature": signature,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    processor.assert_awaited_once_with(payload)


def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(oura.settings, "OURA_CLIENT_SECRET", "client-secret")
    client = TestClient(_test_app())

    response = client.post(
        "/webhook",
        json={
            "event_type": "create",
            "data_type": "workout",
            "object_id": "workout-id",
            "user_id": "oura-user-id",
        },
        headers={
            "x-oura-timestamp": "1785132000",
            "x-oura-signature": "invalid",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_coalesces_events_for_same_user(monkeypatch):
    oura._webhook_sync_locks.clear()
    oura._webhook_pending_payloads.clear()
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def fake_sync(payload):
        calls.append(payload)
        if len(calls) == 1:
            started.set()
            await release.wait()

    monkeypatch.setattr(oura, "_sync_oura_webhook_payload", fake_sync)
    first = {"user_id": "u1", "object_id": "first"}
    middle = {"user_id": "u1", "object_id": "middle"}
    latest = {"user_id": "u1", "object_id": "latest"}

    first_task = asyncio.create_task(oura._process_oura_webhook(first))
    await started.wait()
    await asyncio.gather(
        oura._process_oura_webhook(middle),
        oura._process_oura_webhook(latest),
    )
    release.set()
    await first_task

    assert calls == [first, latest]
    assert not oura._webhook_pending_payloads
