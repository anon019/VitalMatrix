"""Research contracts, time alignment, source deduplication and auth boundaries."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from app.api.dependencies import verify_mcp_api_key
from app.config import settings
from app.mcp.server import APIKeyAuthMiddleware
from app.schemas.research import JournalEntryCreate
from app.services.provider_research import duration_minutes, save_provider_records
from app.services.research_schema import metric_definitions
from app.services.research_service import (
    ResearchService,
    build_day,
    compact_payload,
    match_workouts,
)
from app.utils.datetime_helper import HK_TZ


def row(**kwargs):
    return {"id": uuid.uuid4(), **kwargs}


def test_missing_is_not_zero_and_contribution_score_is_not_bpm():
    data = build_day(date(2026, 10, 1), {"readiness": [row(resting_heart_rate=90)]}, [])
    assert data["metrics"]["readiness.resting_heart_rate"] == 90
    assert metric_definitions()["readiness.resting_heart_rate"]["unit"] == "score"
    assert data["metrics"]["sleep.lowest_heart_rate"] is None
    assert data["metrics"]["training.sessions"] is None
    assert data["metrics"]["nutrition.calories"] is None


def test_sleep_main_nap_rest_and_timezone():
    data = build_day(
        date(2026, 10, 1),
        {
            "sleep": [
                row(
                    sleep_type="short_sleep", total_sleep_duration=1800, average_hrv=80
                ),
                row(
                    sleep_type="long_sleep",
                    total_sleep_duration=21600,
                    average_hrv=50,
                    bedtime_start=datetime(2026, 9, 30, 15, 30, tzinfo=timezone.utc),
                ),
                row(sleep_type="rest", total_sleep_duration=99999),
            ]
        },
        [],
    )
    assert data["metrics"]["sleep.total_minutes"] == 390
    assert data["metrics"]["sleep.total_sleep_duration"] == 360
    assert data["metrics"]["sleep.average_hrv"] == 50
    assert data["metrics"]["sleep.nap_minutes"] == 30
    assert data["metrics"]["sleep.bedtime_minute"] == 1410


def test_zero_nutrients_are_observed_and_unknown_sugar_stays_missing():
    meal = row(
        analysis_status="completed",
        total_calories=0,
        total_protein=0,
        meal_time=HK_TZ.localize(datetime(2026, 10, 1, 19)),
        photo_path=None,
    )
    data = build_day(
        date(2026, 10, 1),
        {"meals": [meal]},
        [row(meal_id=meal["id"], sodium=0, sugar=None)],
    )
    assert data["metrics"]["nutrition.calories"] == 0
    assert data["metrics"]["nutrition.recorded_sodium"] == 0
    assert data["metrics"]["nutrition.recorded_sugar"] is None
    assert data["quality"]["nutrition"]["complete_day_confirmed"] is False
    assert data["quality"]["nutrition"]["missing_original_media"] == [str(meal["id"])]


def test_only_unique_strong_workout_matches_are_merged():
    start = HK_TZ.localize(datetime(2026, 10, 1, 10))
    polar = row(
        start_time=start,
        end_time=start + timedelta(hours=1),
        duration_sec=3600,
        zone2_sec=2700,
    )
    oura = row(start_datetime=start, end_datetime=start + timedelta(hours=1))
    unmatched, pairs, ambiguous = match_workouts([polar], [oura])
    assert not unmatched and len(pairs) == 1 and not ambiguous
    unmatched, pairs, ambiguous = match_workouts(
        [polar], [oura, dict(oura, id=uuid.uuid4())]
    )
    assert len(unmatched) == 2 and not pairs and ambiguous
    data = build_day(
        date(2026, 10, 1), {"polar_exercises": [polar], "oura_workouts": [oura]}, []
    )
    assert data["metrics"]["training.sessions"] == 1
    assert data["metrics"]["training.duration_minutes"] == 60


@pytest.mark.parametrize(
    "changes",
    [
        {"occurred_at": "2026-10-01T08:00:00"},
        {"measurements": [{"code": "weight", "value": 70, "unit": "lb"}]},
        {"measurements": [{"code": "weight", "value": float("nan"), "unit": "kg"}]},
        {"source": "oura"},
        {"ended_at": "2026-09-30T08:00:00+08:00"},
    ],
)
def test_journal_rejects_ambiguous_units_times_and_spoofed_sources(changes):
    payload = {
        "kind": "measurement",
        "occurred_at": "2026-10-01T08:00:00+08:00",
        "measurements": [{"code": "weight", "value": 70, "unit": "kg"}],
        **changes,
    }
    with pytest.raises(ValidationError):
        JournalEntryCreate(**payload)


@pytest.mark.asyncio
async def test_research_key_fail_closed_and_unicode_header(monkeypatch):
    monkeypatch.setattr(settings, "MCP_API_KEY", "")
    with pytest.raises(HTTPException) as exc:
        await verify_mcp_api_key(None, "")
    assert exc.value.status_code == 503
    monkeypatch.setattr(settings, "MCP_API_KEY", "test-key")
    assert await verify_mcp_api_key(None, "test-key")
    with pytest.raises(HTTPException) as exc:
        await verify_mcp_api_key(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="错误"), None
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_mcp_missing_key_cannot_bypass_middleware(monkeypatch):
    app = FastAPI()
    app.add_middleware(APIKeyAuthMiddleware)

    @app.get("/mcp")
    async def ok():
        return {"ok": True}

    monkeypatch.setattr(settings, "MCP_API_KEY", "")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get("/mcp")
        assert response.status_code == 503
        monkeypatch.setattr(settings, "MCP_API_KEY", "test-key")
        assert (await client.get("/mcp")).status_code == 401
        assert (
            await client.get("/mcp", headers={"X-API-Key": "test-key"})
        ).status_code == 200


class Result:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items

    def __iter__(self):
        return iter(self.items)


@pytest.mark.asyncio
async def test_lag_uses_calendar_dates_excludes_stale_and_unconfirmed_nutrition():
    start = date(2026, 8, 1)
    end = date(2026, 8, 30)
    rows = []
    for i in range(30):
        day = start + timedelta(days=i)
        rows.append(
            SimpleNamespace(
                day=day,
                revision=1,
                updated_at=None,
                evidence={},
                metrics={
                    "activity.steps": float(i),
                    "sleep.average_hrv": float(i * 2),
                    "nutrition.calories": float(i),
                },
                quality={
                    "partial_day": False,
                    "nutrition": {"complete_day_confirmed": False},
                },
            )
        )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[Result(rows), Result([start + timedelta(days=2)])]
        )
    )
    data = await ResearchService(db).association(
        uuid.uuid4(), start, end, "activity.steps", "sleep.average_hrv", lag=1
    )
    assert data["pairs"] == 27
    assert data["pearson_r"] == 1
    assert data["points"][0]["y_day"] == "2026-08-02"
    db.execute = AsyncMock(side_effect=[Result(rows), Result([])])
    data = await ResearchService(db).association(
        uuid.uuid4(), start, end, "nutrition.calories", "sleep.average_hrv"
    )
    assert data["pairs"] == 0 and data["pearson_r"] is None


def test_compaction_keeps_series_discoverable():
    assert (
        compact_payload({"samples": list(range(30))})["samples"]["sample_count"] == 30
    )
    assert len(compact_payload({"samples": list(range(30))}, True)["samples"]) == 30
    assert duration_minutes("PT1H2M30.5S") == 62.508


@pytest.mark.asyncio
async def test_provider_profiles_keep_email_out_and_noop_poll_does_not_dirty():
    db = SimpleNamespace(execute=AsyncMock())
    await save_provider_records(
        db,
        uuid.uuid4(),
        "oura",
        "physical_info",
        [{"id": "x", "weight": 70, "email": "private@example.test"}],
    )
    stmt = db.execute.call_args.args[0]
    assert "IS DISTINCT FROM" in str(stmt)
    assert "email" not in str(stmt.compile().params)
