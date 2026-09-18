"""Calendar boundaries, evidence coverage and history-to-prompt integration."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import uuid

import pytest

from app.ai.base import NutritionData, NutritionDayRecord, OuraData, OuraDailyContext, UserContext
from app.ai.context_summary import metric_summary, meal_history_summary, build_health_history
from app.ai.providers.codex import CodexProvider
from app.models.nutrition import MealType
from app.services.ai_service import AIService
from app.services.nutrition_service import NutritionService
from test_ai_prompt_context import _QueuedDB, _ScalarResult, _training_data


def test_windows_preserve_zero_missing_dates_and_exclude_future():
    end = date(2026, 9, 18)
    result = metric_summary([(end, 0), (end - timedelta(days=7), 20),
                             (end + timedelta(days=1), 1000),
                             (end - timedelta(days=90), 1000),
                             (end - timedelta(days=1), None)], end, "g")
    assert result["windows"]["recent_7"]["mean"] == 0
    assert result["windows"]["recent_7"]["observed_days"] == 1
    assert result["windows"]["previous_7"]["mean"] == 20
    assert result["windows"]["recent_90"]["observed_days"] == 2
    assert result["comparisons"]["7_vs_previous_7"]["mean_change"] is None


def test_calendar_slope_and_non_overlapping_comparisons():
    end = date(2026, 9, 18)
    points = [(end - timedelta(days=offset), 100 - offset) for offset in range(90)]
    result = metric_summary(points, end, "分")
    assert result["windows"]["recent_7"]["slope_per_day"] == 1
    assert result["windows"]["recent_30"]["observed_days"] == 30
    assert result["comparisons"]["7_vs_previous_7"]["mean_change"] == 7
    assert result["comparisons"]["30_vs_previous_30"]["mean_change"] == 30
    zero = metric_summary([(day, 0) for day, _ in points], end, "分")
    assert zero["comparisons"]["7_vs_previous_7"]["change_percent"] is None


def test_today_recovery_included_but_partial_day_nutrition_and_activity_excluded():
    target = date(2026, 9, 18)
    oura = OuraData(recent_days=[OuraDailyContext(date=str(target), sleep_score=80, steps=999)])
    nutrition = NutritionData(days=[
        NutritionDayRecord(date=str(target), total_calories=999, meals_count=1),
        NutritionDayRecord(date="2026-09-17", total_calories=600, meals_count=1),
    ])
    context = build_health_history(oura, nutrition, [], target)["metrics"]
    assert context["sleep_score"]["windows"]["recent_7"]["mean"] == 80
    assert context["steps"]["windows"]["recent_7"]["mean"] is None
    assert context["recorded_nutrition_total_calories"]["windows"]["recent_7"]["mean"] == 600


def meal(when, *foods):
    return SimpleNamespace(id=uuid.uuid4(), meal_time=when, meal_type=MealType.DINNER,
                           food_items=[SimpleNamespace(food_name=f) for f in foods],
                           ai_analysis={}, total_calories=600, total_protein=20)


def test_food_history_counts_meals_not_duplicate_foods_and_uses_local_dates():
    end = date(2026, 9, 18)
    meals = [meal(datetime(2026, 9, 17, 16, tzinfo=timezone.utc), "豆腐", "豆腐"),
             meal(datetime(2026, 8, 30, 12, tzinfo=timezone.utc), "鱼"),
             meal(datetime(2026, 7, 20, 12, tzinfo=timezone.utc), "燕麦")]
    windows = meal_history_summary(meals, end)["windows"]
    assert windows["7"]["recorded_meals"] == 1
    assert windows["7"]["top_dishes"] == [{"name": "豆腐", "meal_count": 1, "last_eaten": "2026-09-18"}]
    assert windows["30"]["recorded_meals"] == 2
    assert windows["90"]["recorded_meals"] == 3


@pytest.mark.asyncio
async def test_older_foods_survive_missing_daily_summaries_and_reach_prompt():
    old_meal = meal(datetime(2026, 8, 1, 12, tzinfo=timezone.utc), "番茄炖牛肉")
    service = AIService(_QueuedDB([_ScalarResult(), _ScalarResult(items=[old_meal])]))
    nutrition = await service._get_nutrition_data(uuid.uuid4(), date(2026, 9, 18))
    assert nutrition is not None
    assert not nutrition.recent_meals
    text = CodexProvider._build_nutrition_section(nutrition, "2026-09-18")
    assert "番茄炖牛肉" in text
    assert "昨日各餐热量" not in text


@pytest.mark.asyncio
async def test_long_context_reaches_actual_provider_call_without_changing_response_contract():
    target = date(2026, 9, 18)
    nutrition = NutritionData(days=[NutritionDayRecord(date="2026-09-01", total_fiber=0, meals_count=1)],
                              food_history={"windows": {"90": {"top_dishes": [{"name": "燕麦"}]}}})
    history = build_health_history(None, nutrition, [], target)
    provider = CodexProvider()
    provider.runner = SimpleNamespace(run_json=AsyncMock(return_value={
        "summary": "按恢复状态安排活动",
        "yesterday_review": {"title": "趋势", "emoji": "📊", "items": ["数据不足"]},
        "today_recommendation": {"title": "建议", "emoji": "🥗", "items": ["搭配蔬菜"]},
        "health_education": {"title": "知识", "emoji": "📚", "sections": [
            {"subtitle": "恢复", "items": [{"label": "实践", "content": "规律作息"}]}]},
    }))
    result = await provider.generate_recommendation(
        UserContext(user_id="test", health_goal="健康", training_plan="适量活动"),
        _training_data(nutrition_data=nutrition, trend_summary=json.dumps(history, ensure_ascii=False)),
        str(target),
    )
    prompt = provider.runner.run_json.call_args.args[0]
    assert "recent_90" in prompt and "previous_30" in prompt
    assert "燕麦" in prompt and "recorded_nutrition_total_fiber" in prompt
    assert result.yesterday_review["items"] == ["数据不足"]


@pytest.mark.asyncio
async def test_followup_meal_plans_receive_long_history_but_keep_timestamp_cutoff():
    class DB(_QueuedDB):
        async def execute(self, query):
            if "meal_records.meal_time <" in str(query):
                self.history_query = query
            return await super().execute(query)

    user = SimpleNamespace(birth_year=None, gender=None, weight=None, height=None,
                           health_goal=None, training_plan=None)
    db = DB([_ScalarResult(scalar=user), _ScalarResult(items=[
        meal(datetime(2026, 8, 1, 12, tzinfo=timezone.utc), "鱼")]), _ScalarResult(items=[{}])])
    cutoff = datetime(2026, 9, 18, 4, tzinfo=timezone.utc)
    context = await NutritionService()._get_user_context(db, uuid.uuid4(), before_time=cutoff)
    assert context["food_history"]["windows"]["90"]["recorded_meals"] == 1
    parameters = db.history_query.compile().params
    assert cutoff in parameters.values()
    assert cutoff - timedelta(days=90) in parameters.values()
    assert "meal_records.meal_time <" in str(db.history_query)
