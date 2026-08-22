"""
Backend regression tests for recently fixed hotspots.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from PIL import Image

from app.api.dependencies import get_current_user
from app.config import settings
from app.services.ai_service import AIService
from app.services.file_storage import FileStorageService
from app.services.nutrition_service import NutritionService
from app.services.oura_sync import OuraSyncService, _user_sync_locks
from app.services.sleep_metrics_service import SleepMetricsService
from app.services.training_metrics import TrainingMetricsService
from app.scheduler.jobs import MAX_CONCURRENT_USER_TASKS, _run_user_tasks
from app.utils.datetime_helper import HK_TZ, end_of_day_hk, start_of_day_hk, today_hk


class _FakeDBResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, returns):
        self.returns = iter(returns)
        self.calls = []

    async def execute(self, statement):
        self.calls.append(statement)
        try:
            return _FakeDBResult(next(self.returns))
        except StopIteration as e:
            raise AssertionError("Unexpected extra DB call") from e


class _FakeSleepRecord:
    def __init__(self, day, sleep_type, total_sleep_duration):
        self.day = day
        self.sleep_type = sleep_type
        self.total_sleep_duration = total_sleep_duration


@pytest.mark.asyncio
async def test_invalid_uuid_token_subject_returns_401():
    token = jwt.encode(
        {"sub": "not-a-uuid"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=credentials, db=_FakeDB([]))

    assert exc_info.value.status_code == 401


def test_datetime_helpers_and_day_boundaries():
    today = today_hk()
    now = datetime.now(HK_TZ)
    assert today == now.date()
    assert start_of_day_hk(today).tzinfo is not None
    assert end_of_day_hk(today).tzinfo is not None
    assert end_of_day_hk(today) - start_of_day_hk(today) == timedelta(
        hours=23,
        minutes=59,
        seconds=59,
    )


def test_sleep_dedupe_prefers_long_sleep_and_longer_duration():
    records = [
        _FakeSleepRecord(date(2026, 3, 12), "short_sleep", 200 * 60),
        _FakeSleepRecord(date(2026, 3, 12), "long_sleep", 300 * 60),
        _FakeSleepRecord(date(2026, 3, 11), "short_sleep", 350 * 60),
        _FakeSleepRecord(date(2026, 3, 11), "long_sleep", 250 * 60),
        _FakeSleepRecord(date(2026, 3, 11), "long_sleep", 400 * 60),
        _FakeSleepRecord(date(2026, 3, 10), None, 500 * 60),
        _FakeSleepRecord(None, "long_sleep", 999 * 60),
    ]

    deduped = SleepMetricsService._dedupe_daily_records(records)

    assert [r.day for r in deduped] == [
        date(2026, 3, 12),
        date(2026, 3, 11),
        date(2026, 3, 10),
    ]
    assert deduped[0].sleep_type == "long_sleep"
    assert deduped[0].total_sleep_duration == 300 * 60
    assert deduped[1].sleep_type == "long_sleep"
    assert deduped[1].total_sleep_duration == 400 * 60
    assert deduped[2].sleep_type is None


@pytest.mark.asyncio
async def test_run_user_tasks_respects_max_concurrency():
    running = 0
    max_running = 0
    lock = asyncio.Lock()

    async def task_handler(_user):
        nonlocal running, max_running
        async with lock:
            running += 1
            max_running = max(max_running, running)
        await asyncio.sleep(0.01)
        async with lock:
            running -= 1
        return "ok"

    users = list(range(20))
    results = await _run_user_tasks(users, task_handler)

    assert len(results) == len(users)
    assert max_running == MAX_CONCURRENT_USER_TASKS


@pytest.mark.asyncio
async def test_ai_recommendation_getter_no_fallback():
    test_user = uuid.uuid4()
    target = today_hk()

    fake_db = _FakeDB([None])
    service = AIService(fake_db)

    recommendation = await service.get_recommendation(
        user_id=test_user,
        target_date=target,
        allow_fallback=False,
    )

    assert recommendation is None
    assert len(fake_db.calls) == 1


@pytest.mark.asyncio
async def test_ai_recommendation_fallback_query():
    test_user = uuid.uuid4()
    target = today_hk()
    fallback_record = object()

    # The query orders the target date first and the newest fallback second,
    # so the database resolves both cases in one round trip.
    fake_db = _FakeDB([fallback_record])
    service = AIService(fake_db)

    recommendation = await service.get_recommendation(
        user_id=test_user,
        target_date=target,
        allow_fallback=True,
    )

    assert recommendation is fallback_record
    assert len(fake_db.calls) == 1


def test_file_storage_absolute_path_and_permanent_retention(tmp_path):
    base_dir = tmp_path / "uploads"
    storage = FileStorageService(base_dir=str(base_dir))

    assert storage.get_absolute_path("/uploads/nutrition/u1/20260101/test.jpg") == (
        base_dir / "u1" / "20260101" / "test.jpg"
    )
    assert storage.get_absolute_path("uploads/nutrition/u1/20260101/test.jpg") == (
        base_dir / "u1" / "20260101" / "test.jpg"
    )
    with pytest.raises(ValueError, match="超出允许目录"):
        storage.get_absolute_path("../../etc/passwd")

    user_dir = base_dir / "u1"
    old_date = user_dir / "20260201"
    keep_date = user_dir / "20260325"
    skip_dir = user_dir / "bad_date"
    old_date.mkdir(parents=True)
    keep_date.mkdir(parents=True)
    skip_dir.mkdir()
    (old_date / "old.txt").write_text("x")
    (keep_date / "keep.txt").write_text("x")
    (skip_dir / "bad.txt").write_text("x")

    deleted = storage.cleanup_old_photos(days=5)

    assert deleted == 0
    assert old_date.exists()
    assert keep_date.exists()
    assert skip_dir.exists()


@pytest.mark.asyncio
async def test_file_storage_writes_original_and_thumbnail_from_one_decode(tmp_path):
    source = BytesIO()
    Image.new("RGB", (1200, 800), "orange").save(source, "PNG")
    storage = FileStorageService(base_dir=str(tmp_path / "uploads"))

    _, _, original_path, thumbnail_path = await storage.save_meal_photo(
        user_id="u1",
        meal_id="meal1",
        file_content=source.getvalue(),
        meal_time=datetime(2026, 8, 21, 12, 0),
    )

    with Image.open(original_path) as original:
        assert original.format == "JPEG"
        assert original.size == (1200, 800)
    with Image.open(thumbnail_path) as thumbnail:
        assert thumbnail.format == "JPEG"
        assert max(thumbnail.size) == 200


@pytest.mark.asyncio
async def test_nutrition_core_context_skips_unused_history_query():
    user = SimpleNamespace(
        gender="male",
        birth_year=1990,
        birth_month=1,
        weight=82,
        height=180,
        health_goal="maintain",
        training_plan="zone2",
    )
    db = _FakeDB([user])

    context = await NutritionService()._get_user_context(
        db,
        uuid.uuid4(),
        include_history=False,
    )

    assert len(db.calls) == 1
    assert context["weight"] == 82.0
    assert "recent_meals" not in context


@pytest.mark.asyncio
async def test_analysis_status_query_does_not_load_json_or_food_items():
    class StatusResult:
        def one_or_none(self):
            return SimpleNamespace(
                id=uuid.uuid4(),
                analysis_status="completed",
                recommendation_status="processing",
                recommendation_attempts=1,
                analysis_error=None,
                analysis_completed_at=None,
                recommendation_updated_at=None,
            )

    class CaptureDB:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            return StatusResult()

    db = CaptureDB()
    status_result = await NutritionService().get_meal_analysis_status(
        db,
        uuid.uuid4(),
        uuid.uuid4(),
    )

    sql = str(db.statement.compile()).lower()
    assert status_result["analysis_status"] == "completed"
    assert "gemini_analysis" not in sql
    assert "food_items" not in sql


def test_nutrition_flags_empty_when_no_meals():
    assert NutritionService._calculate_nutrition_flags(0, 0, 0, 0) == {}


def test_nutrition_flags_detect_clear_outliers():
    flags = NutritionService._calculate_nutrition_flags(
        total_calories=2600,
        total_protein=45,
        total_carbs=360,
        total_fat=25,
    )

    assert flags["calorie_high"] is True
    assert flags["protein_low"] is True
    assert flags["carbs_high"] is True
    assert flags["fat_low"] is True
    assert flags["calorie_low"] is False


def test_partial_day_does_not_claim_nutrient_deficiency():
    flags = NutritionService._calculate_nutrition_flags(440, 13, 50, 20, meals_count=1)
    assert flags["partial_day"] is True
    assert flags["calorie_low"] is False
    assert flags["protein_low"] is False


@pytest.mark.asyncio
async def test_weekly_summary_aggregate_has_no_invalid_order_by():
    class CaptureDB:
        statement = None

        async def execute(self, statement):
            self.statement = statement
            raise RuntimeError("captured")

    db = CaptureDB()
    service = TrainingMetricsService(db)

    with pytest.raises(RuntimeError, match="captured"):
        await service.calculate_weekly_summary(
            uuid.uuid4(),
            week_start_date=date(2026, 7, 27),
        )

    sql = str(db.statement.compile())
    assert "ORDER BY" not in sql.upper()


@pytest.mark.asyncio
async def test_oura_sync_serializes_same_user(monkeypatch):
    _user_sync_locks.clear()
    running = 0
    max_running = 0

    async def fake_sync(self, **kwargs):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.01)
        running -= 1
        return {"ok": 1}

    monkeypatch.setattr(OuraSyncService, "_sync_user_data_unlocked", fake_sync)
    first = object.__new__(OuraSyncService)
    second = object.__new__(OuraSyncService)
    user_id = uuid.uuid4()

    results = await asyncio.gather(
        first.sync_user_data(user_id),
        second.sync_user_data(user_id),
    )

    assert results == [{"ok": 1}, {"ok": 1}]
    assert max_running == 1
