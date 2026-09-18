"""Concurrency, retry deadlines and stale-write regressions for meal analysis."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from app.ai.codex_cli import CodexCLIRunner, CodexCLIUnavailableError, CodexCLIError
from app.config import settings
from app.models.nutrition import MealType
from app.services.codex_nutrition_service import CodexNutritionService
from app.services.file_storage import FileStorageService
from app.services.nutrition_errors import InvalidMealImageError, MealAnalysisBusyError
from app.services.nutrition_service import NutritionService


@pytest.mark.asyncio
async def test_background_waiters_leave_capacity_for_foreground():
    runner = CodexCLIRunner()
    runner._semaphore = asyncio.Semaphore(2)
    runner._background_semaphore = asyncio.Semaphore(1)
    queued_started = asyncio.Event()

    async def queued():
        queued_started.set()
        async with runner._slot(1, background=True):
            pass

    async with runner._slot(1, background=True):
        waiter = asyncio.create_task(queued())
        await queued_started.wait()
        async with runner._slot(0.1):
            assert runner._semaphore.locked()
            assert not waiter.done()
    await waiter
    async with runner._slot(1, background=True):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [FileNotFoundError(), InvalidMealImageError(), CodexCLIUnavailableError()])
async def test_permanent_errors_are_not_retried(error):
    service = CodexNutritionService()
    service.analyze_meal_photo = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await service.analyze_meal_photo_with_retry("missing", "lunch", "2026-09-18")
    assert service.analyze_meal_photo.await_count == 1


@pytest.mark.asyncio
async def test_total_deadline_includes_backoff(monkeypatch):
    monkeypatch.setattr(settings, "NUTRITION_CORE_TOTAL_TIMEOUT_SECONDS", 0.03)
    service = CodexNutritionService()
    service.analyze_meal_photo = AsyncMock(side_effect=CodexCLIError("temporary"))
    with pytest.raises(TimeoutError):
        await service.analyze_meal_photo_with_retry("test", "lunch", "2026-09-18")
    assert service.analyze_meal_photo.await_count == 1


@pytest.mark.asyncio
async def test_invalid_model_output_can_retry_successfully(monkeypatch):
    monkeypatch.setattr("app.services.codex_nutrition_service.RETRY_DELAY_SECONDS", 0)
    service = CodexNutritionService()
    service.analyze_meal_photo = AsyncMock(side_effect=[ValueError("bad output"), {"ok": True}])
    result = await service.analyze_meal_photo_with_retry("test", "lunch", "2026-09-18")
    assert result == {"ok": True}
    assert service.analyze_meal_photo.await_count == 2


@pytest.mark.asyncio
async def test_identical_inflight_upload_only_starts_one_analysis(monkeypatch):
    held = set()

    @asynccontextmanager
    async def lock(key, ttl_seconds):
        acquired = key not in held
        if acquired:
            held.add(key)
        try:
            yield acquired
        finally:
            if acquired:
                held.remove(key)

    monkeypatch.setattr("app.services.nutrition_service.distributed_lock", lock)
    service = NutritionService()
    entered, release = asyncio.Event(), asyncio.Event()

    async def analyze(*args):
        entered.set()
        await release.wait()
        return {"meal_id": "one"}

    service._analyze_and_save_meal_unlocked = AsyncMock(side_effect=analyze)
    args = (None, uuid.uuid4(), MealType.LUNCH, datetime.now(timezone.utc), b"same photo")
    first = asyncio.create_task(service.analyze_and_save_meal(*args))
    await entered.wait()
    with pytest.raises(MealAnalysisBusyError):
        await service.analyze_and_save_meal(*args)
    release.set()
    assert await first == {"meal_id": "one"}
    assert service._analyze_and_save_meal_unlocked.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_old_recommendation_cannot_overwrite_reanalyzed_meal(monkeypatch, fail):
    @asynccontextmanager
    async def lock(*args, **kwargs):
        yield True

    monkeypatch.setattr("app.services.nutrition_service.distributed_lock", lock)
    meal = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), ai_analysis={"core": "old"},
        meal_type=MealType.LUNCH, meal_time=datetime.now(timezone.utc),
        analysis_completed_at=datetime.now(timezone.utc),
        recommendation_status="pending", recommendation_attempts=0,
    )

    class DB:
        commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, query):
            return SimpleNamespace(scalar_one_or_none=lambda: meal)

    db = DB()
    monkeypatch.setattr("app.database.session.AsyncSessionLocal", lambda: db)
    service = NutritionService()
    service._get_user_context = AsyncMock(return_value={})

    async def generate(**kwargs):
        meal.analysis_completed_at += timedelta(seconds=1)
        meal.ai_analysis = {"core": "new"}
        meal.recommendation_status = "pending"
        if fail:
            raise ValueError("old request failed")
        return {"status": "completed"}

    service.ai_service = SimpleNamespace(generate_recommendations=generate)
    assert not await service.generate_recommendations_for_meal(meal.id, meal.user_id)
    assert meal.ai_analysis == {"core": "new"}
    assert meal.recommendation_status == "pending"
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_invalid_image_fails_before_model_and_leaves_no_files(tmp_path):
    storage = FileStorageService(str(tmp_path))
    with pytest.raises(InvalidMealImageError):
        await storage.save_meal_photo("test", "meal", b"not an image", datetime.now())
    assert not list(tmp_path.rglob("*.jpg"))


@pytest.mark.asyncio
async def test_partial_file_write_is_cleaned_up(tmp_path, monkeypatch):
    storage = FileStorageService(str(tmp_path))

    def fail_after_original(content, original, thumbnail):
        original.write_bytes(b"partial")
        raise OSError("disk failure")

    monkeypatch.setattr(storage, "_normalize_and_save_images_sync", fail_after_original)
    with pytest.raises(OSError):
        await storage.save_meal_photo("test", "meal", b"data", datetime.now())
    assert not list(tmp_path.rglob("*.jpg"))


@pytest.mark.asyncio
async def test_cancelled_upload_waits_for_image_writer_before_cleanup(tmp_path, monkeypatch):
    from threading import Event

    storage = FileStorageService(str(tmp_path))
    started, finish = Event(), Event()

    def slow_writer(content, original, thumbnail):
        started.set()
        finish.wait(2)
        original.write_bytes(b"image")
        thumbnail.write_bytes(b"thumb")

    monkeypatch.setattr(storage, "_normalize_and_save_images_sync", slow_writer)
    task = asyncio.create_task(storage.save_meal_photo("test", "meal", b"data", datetime.now()))
    await asyncio.to_thread(started.wait, 1)
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not list(tmp_path.rglob("*.jpg"))


@pytest.mark.asyncio
async def test_resume_failure_does_not_starve_later_meals(monkeypatch):
    pending = [(uuid.uuid4(), uuid.uuid4()), (uuid.uuid4(), uuid.uuid4())]

    class DB:
        commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, query):
            return SimpleNamespace(all=lambda: pending)

    monkeypatch.setattr("app.database.session.AsyncSessionLocal", DB)
    service = NutritionService()
    service.generate_recommendations_for_meal = AsyncMock(side_effect=[RuntimeError("db"), True])
    assert await service.resume_pending_recommendations() == 1
    assert service.generate_recommendations_for_meal.await_count == 2


@pytest.mark.asyncio
async def test_processing_recommendation_request_does_not_queue_duplicate(monkeypatch):
    from fastapi import BackgroundTasks
    from app.api.v1 import nutrition

    monkeypatch.setattr(nutrition, "enforce_rate_limit", AsyncMock())
    monkeypatch.setattr(nutrition.nutrition_service, "get_meal_analysis_status", AsyncMock(return_value={
        "analysis_status": "completed", "recommendation_status": "processing", "recommendation_attempts": 1,
    }))
    tasks = BackgroundTasks()
    response = await nutrition.generate_meal_recommendations(
        uuid.uuid4(), tasks, force=True, current_user=SimpleNamespace(id=uuid.uuid4()), db=None,
    )
    assert response["recommendation_status"] == "processing"
    assert not tasks.tasks
