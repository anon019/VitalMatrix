"""
Backend regression tests for recently fixed hotspots.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta

import pytest

from app.services.ai_service import AIService
from app.services.file_storage import FileStorageService
from app.services.sleep_metrics_service import SleepMetricsService
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

    fake_db = _FakeDB([None, fallback_record])
    service = AIService(fake_db)

    recommendation = await service.get_recommendation(
        user_id=test_user,
        target_date=target,
        allow_fallback=True,
    )

    assert recommendation is fallback_record
    assert len(fake_db.calls) == 2


def test_file_storage_absolute_and_cleanup(monkeypatch, tmp_path):
    base_dir = tmp_path / "uploads"
    storage = FileStorageService(base_dir=str(base_dir))

    assert storage.get_absolute_path("/uploads/nutrition/u1/20260101/test.jpg") == (
        base_dir / "u1" / "20260101" / "test.jpg"
    )
    assert storage.get_absolute_path("uploads/nutrition/u1/20260101/test.jpg") == (
        base_dir / "uploads" / "nutrition" / "u1" / "20260101" / "test.jpg"
    )

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

    monkeypatch.setattr(
        "app.services.file_storage.now_hk",
        lambda: datetime(2026, 3, 12, 12, 0, tzinfo=HK_TZ),
    )
    deleted = storage.cleanup_old_photos(days=5)

    assert deleted == 1
    assert not old_date.exists()
    assert keep_date.exists()
    assert skip_dir.exists()
