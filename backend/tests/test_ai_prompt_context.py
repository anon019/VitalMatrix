"""AI recommendation prompt context regression tests."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
import yaml

from app.ai.base import ExerciseSession, OuraDailyContext, OuraData, TrainingData
from app.ai.prompt_sections import build_oura_data_section, build_training_section
from app.services.ai_service import AIService


class _ScalarResult:
    def __init__(self, *, scalar=None, items=None):
        self.scalar = scalar
        self.items = items or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return self

    def all(self):
        return self.items


class _QueuedDB:
    def __init__(self, results):
        self.results = list(results)

    async def execute(self, _query):
        return self.results.pop(0)


def _training_data(**overrides) -> TrainingData:
    values = {
        "zone2_min": 28,
        "hi_min": 8,
        "total_duration_min": 52,
        "trimp": 61.0,
        "avg_hr": 142,
        "sport_type": "RUNNING、STRENGTH_TRAINING",
        "weekly_zone2": 95,
        "weekly_hi": 22,
        "weekly_total": 210,
        "weekly_trimp": 248.0,
        "training_days": 4,
        "rest_days": 3,
        "flags": {},
    }
    values.update(overrides)
    return TrainingData(**values)


def test_training_prompt_includes_each_sport_time_and_intensity_structure():
    training = _training_data(sessions=[
        ExerciseSession(
            date="2026-08-22",
            start_time="07:10",
            end_time="07:52",
            sport_type="RUNNING",
            duration_min=42,
            avg_hr=145,
            max_hr=174,
            zone1_min=4,
            zone2_min=21,
            zone3_min=10,
            zone4_min=6,
            zone5_min=1,
            cardio_load=58.5,
            distance_km=7.2,
        ),
        ExerciseSession(
            date="2026-08-20",
            start_time="18:30",
            end_time="19:15",
            sport_type="STRENGTH_TRAINING",
            duration_min=45,
        ),
    ])

    prompt = build_training_section(training)

    assert "2026-08-22 07:10-07:52；RUNNING；42分钟" in prompt
    assert "Z1/Z2/Z3/Z4/Z5 4/21/10/6/1分钟" in prompt
    assert "2026-08-20 18:30-19:15；STRENGTH_TRAINING；45分钟" in prompt
    assert "不同类型分开评估" in prompt
    assert "## 本周训练汇总" in prompt


@pytest.mark.asyncio
async def test_training_data_pipeline_preserves_session_type_time_and_metrics():
    daily = SimpleNamespace(
        zone2_min=21,
        hi_min=7,
        total_duration_min=42,
        trimp=Decimal("58.5"),
        avg_hr=145,
        flags={},
    )
    weekly = SimpleNamespace(
        zone2_min=95,
        hi_min=22,
        total_duration_min=210,
        weekly_trimp=Decimal("248"),
        training_days=4,
        rest_days=3,
    )
    exercises = [SimpleNamespace(
        start_time=datetime(2026, 8, 21, 23, 10, tzinfo=timezone.utc),
        end_time=datetime(2026, 8, 21, 23, 52, tzinfo=timezone.utc),
        sport_type="RUNNING",
        duration_sec=2520,
        avg_hr=145,
        max_hr=174,
        zone1_sec=240,
        zone2_sec=1260,
        zone3_sec=600,
        zone4_sec=360,
        zone5_sec=60,
        calories=410,
        cardio_load=Decimal("58.5"),
        distance_meters=Decimal("7200"),
    )]
    db = _QueuedDB([
        _ScalarResult(scalar=daily),
        _ScalarResult(scalar=weekly),
        _ScalarResult(items=exercises),
    ])
    service = AIService(db)
    service._get_oura_data = AsyncMock(return_value=None)
    service._get_nutrition_data = AsyncMock(return_value=None)
    service._get_trend_summary = AsyncMock(return_value=None)

    result = await service._get_training_data(uuid.uuid4(), date(2026, 8, 23))

    assert result.sport_type == "RUNNING"
    assert len(result.sessions) == 1
    session = result.sessions[0]
    assert (session.date, session.start_time, session.end_time) == (
        "2026-08-22",
        "07:10",
        "07:52",
    )
    assert session.duration_min == 42
    assert session.max_hr == 174
    assert session.distance_km == 7.2


def test_oura_prompt_includes_recent_activity_sedentary_stress_and_recovery():
    oura = OuraData(
        sleep_score=82,
        readiness_score=76,
        activity_score=71,
        steps=8540,
        sedentary_min=615,
        inactivity_alerts=4,
        recent_days=[
            OuraDailyContext(
                date="2026-08-22",
                sleep_score=82,
                total_sleep_hours=7.4,
                readiness_score=76,
                activity_score=71,
                steps=8540,
                active_calories=430,
                high_activity_min=12,
                medium_activity_min=38,
                low_activity_min=205,
                sedentary_min=615,
                inactivity_alerts=4,
                stress_high_min=96,
                recovery_high_min=54,
                day_summary="restored",
            )
        ],
    )

    prompt = build_oura_data_section(oura)

    assert "久坐615分钟" in prompt
    assert "高/中/低强度活动12/38/205分钟" in prompt
    assert "活动消耗430kcal" in prompt
    assert "高压力/高恢复96/54分钟" in prompt
    assert "同一时间轴上综合判断" in prompt


@pytest.mark.asyncio
async def test_oura_pipeline_builds_seven_day_activity_and_sedentary_context():
    target = date(2026, 8, 23)
    yesterday = date(2026, 8, 22)
    sleep = SimpleNamespace(
        day=target,
        sleep_type="long_sleep",
        total_sleep_duration=7 * 3600,
        deep_sleep_duration=70 * 60,
        rem_sleep_duration=95 * 60,
        light_sleep_duration=255 * 60,
        sleep_score=82,
        efficiency=88,
        average_hrv=44,
        lowest_heart_rate=52,
    )
    readiness = SimpleNamespace(
        day=target,
        score=76,
        recovery_index=71,
        hrv_balance=73,
    )
    activity = SimpleNamespace(
        day=yesterday,
        score=71,
        steps=8540,
        active_calories=430,
        high_activity_time=12,
        medium_activity_time=38,
        low_activity_time=205,
        sedentary_time=615,
        inactivity_alerts=4,
    )
    stress = SimpleNamespace(
        day=yesterday,
        stress_high=96 * 60,
        recovery_high=54 * 60,
        day_summary="restored",
    )
    service = AIService(_QueuedDB([
        _ScalarResult(items=[sleep]),
        _ScalarResult(items=[readiness]),
        _ScalarResult(items=[activity]),
        _ScalarResult(items=[stress]),
    ]))

    result = await service._get_oura_data(uuid.uuid4(), target)

    assert result is not None
    assert result.sedentary_min == 615
    assert result.inactivity_alerts == 4
    assert len(result.recent_days) == 2
    activity_day = next(day for day in result.recent_days if day.date == "2026-08-22")
    assert activity_day.steps == 8540
    assert activity_day.high_activity_min == 12
    assert activity_day.stress_high_min == 96


def test_health_education_excludes_record_completeness_as_a_topic():
    prompt_path = Path(__file__).parents[1] / "config/prompts/recommendation.yaml"
    config = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
    task_template = config["task_template"]

    assert config["version"] == "recommendation-v3.0"
    assert "绝不能作为健康知识主题" in task_template
    assert "运动营养学、运动生理学、运动学" in task_template
    assert '"label": "循证依据"' in task_template
