"""Opt-in PostgreSQL integration tests in a disposable schema, never production rows.

RUN_RESEARCH_DB_TESTS=1 venv/bin/pytest tests/test_research_postgres.py -q
"""

import asyncio
from datetime import datetime, timedelta
import importlib.util
import os
from pathlib import Path
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database.base import Base
from app.models.nutrition import MealRecord, MealType
from app.models.research import HealthDirtyDay, HealthJournalEntry
from app.models.user import User
from app.api.v1.research import create_journal
from app.schemas.research import JournalEntryCreate
from app.services.research_service import process_dirty_days, ResearchService
from app.utils.datetime_helper import HK_TZ, today_hk

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RESEARCH_DB_TESTS") != "1",
    reason="disposable PostgreSQL schema requires explicit opt-in",
)


@pytest_asyncio.fixture
async def dataset_db():
    schema = "research_test_" + uuid.uuid4().hex
    engine = create_async_engine(
        settings.DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    research_tables = {
        "health_source_records",
        "health_journal_entries",
        "health_daily_features",
        "health_dirty_days",
    }
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.run_sync(
                lambda c: Base.metadata.create_all(
                    c,
                    tables=[
                        t
                        for t in Base.metadata.sorted_tables
                        if t.name not in research_tables
                    ],
                )
            )

            def migrate(c):
                path = (
                    Path(__file__).resolve().parents[1]
                    / "alembic/versions/4e5f60718293_health_research_data.py"
                )
                spec = importlib.util.spec_from_file_location(
                    "research_migration", path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with Operations.context(MigrationContext.configure(c)):
                    module.upgrade()

            await conn.run_sync(migrate)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            user = User(id=uuid.uuid4(), openid="test-" + uuid.uuid4().hex)
            db.add(user)
            await db.commit()
            yield db, sessions, user
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


@pytest.mark.asyncio
async def test_dirty_trigger_rebuild_move_delete_and_rollback(dataset_db):
    db, _, user = dataset_db
    day = today_hk() - timedelta(days=3)
    when = HK_TZ.localize(datetime.combine(day, datetime.min.time())) + timedelta(
        hours=12
    )
    meal = MealRecord(
        user_id=user.id, meal_type=MealType.LUNCH, meal_time=when, total_calories=500
    )
    db.add(meal)
    await db.commit()
    assert await db.scalar(select(func.count()).select_from(HealthDirtyDay)) == 1
    assert await process_dirty_days(db) == 1
    result = await ResearchService(db).days(user.id, day, day, ["nutrition.calories"])
    assert result["days"][0]["metrics"]["nutrition.calories"] == 500
    meal.total_calories = 600
    await db.flush()
    await db.rollback()
    await db.refresh(user)
    assert await db.scalar(select(func.count()).select_from(HealthDirtyDay)) == 0
    meal = (await db.execute(select(MealRecord))).scalar_one()
    meal.meal_time = when + timedelta(days=1)
    await db.commit()
    assert await process_dirty_days(db) == 2
    result = await ResearchService(db).days(
        user.id, day, day + timedelta(days=1), ["nutrition.calories"]
    )
    assert [r["metrics"]["nutrition.calories"] for r in result["days"]] == [None, 500]
    await db.delete(meal)
    await db.commit()
    await process_dirty_days(db)
    result = await ResearchService(db).days(
        user.id,
        day + timedelta(days=1),
        day + timedelta(days=1),
        ["nutrition.calories"],
    )
    assert result["days"][0]["metrics"]["nutrition.calories"] is None


@pytest.mark.asyncio
async def test_journal_idempotency_corrections_and_query_isolation(dataset_db):
    db, _, user = dataset_db
    day = today_hk() - timedelta(days=2)
    entry = JournalEntryCreate(
        kind="measurement",
        external_id="scale-1",
        occurred_at=f"{day}T08:00:00+08:00",
        measurements=[{"code": "weight", "value": 70, "unit": "kg"}],
    )
    first = await create_journal(entry, user, db)
    second = await create_journal(entry, user, db)
    assert first["id"] == second["id"] and second["reused"]
    correction = entry.model_copy(
        update={
            "external_id": "scale-1-fix",
            "supersedes_id": uuid.UUID(first["id"]),
            "measurements": [entry.measurements[0].model_copy(update={"value": 71})],
        }
    )
    await create_journal(correction, user, db)
    await process_dirty_days(db)
    result = await ResearchService(db).days(user.id, day, day, ["journal.weight"])
    assert result["days"][0]["metrics"]["journal.weight"] == 71
    assert await db.scalar(select(func.count()).select_from(HealthJournalEntry)) == 2
    history = await ResearchService(db).records(
        user.id, "journal", day, day, include_superseded=True
    )
    assert len(history["records"]) == 2
    records = await ResearchService(db).records(uuid.uuid4(), "journal", day, day)
    assert records["records"] == []


@pytest.mark.asyncio
async def test_nutrition_confirmation_is_bound_to_intake_facts(dataset_db):
    db, _, user = dataset_db
    day = today_hk() - timedelta(days=2)
    meal = MealRecord(
        user_id=user.id,
        meal_type=MealType.LUNCH,
        meal_time=HK_TZ.localize(datetime.combine(day, datetime.min.time()))
        + timedelta(hours=12),
        total_calories=500,
    )
    db.add(meal)
    await db.commit()
    confirmation = JournalEntryCreate(
        kind="nutrition_coverage",
        external_id="coverage-1",
        occurred_at=f"{day}T22:00:00+08:00",
        complete=True,
    )
    await create_journal(confirmation, user, db)
    await process_dirty_days(db)
    result = await ResearchService(db).days(user.id, day, day)
    assert result["days"][0]["quality"]["nutrition"]["complete_day_confirmed"] is True
    meal.total_calories = 600
    await db.commit()
    await process_dirty_days(db)
    result = await ResearchService(db).days(user.id, day, day)
    assert result["days"][0]["quality"]["nutrition"]["confirmation_outdated"] is True
    assert result["days"][0]["quality"]["nutrition"]["complete_day_confirmed"] is False


@pytest.mark.asyncio
async def test_source_write_during_materialization_requeues_without_lost_update(
    dataset_db,
):
    db, sessions, user = dataset_db
    day = today_hk() - timedelta(days=2)
    meal = MealRecord(
        user_id=user.id,
        meal_type=MealType.LUNCH,
        meal_time=HK_TZ.localize(datetime.combine(day, datetime.min.time()))
        + timedelta(hours=12),
        total_calories=500,
    )
    db.add(meal)
    await db.commit()
    await db.execute(select(HealthDirtyDay).with_for_update())

    async def write():
        async with sessions() as writer:
            record = (await writer.execute(select(MealRecord))).scalar_one()
            record.total_calories = 700
            await writer.commit()

    task = asyncio.create_task(write())
    try:
        await asyncio.sleep(0.1)
        assert not task.done()
        await ResearchService(db).refresh_range(user.id, day, day)
        await db.execute(delete(HealthDirtyDay))
        await db.commit()
        await asyncio.wait_for(task, 5)
        assert await db.scalar(select(func.count()).select_from(HealthDirtyDay)) == 1
        await process_dirty_days(db)
        result = await ResearchService(db).days(
            user.id, day, day, ["nutrition.calories"]
        )
        assert result["days"][0]["metrics"]["nutrition.calories"] == 700
    finally:
        if not task.done():
            task.cancel()
