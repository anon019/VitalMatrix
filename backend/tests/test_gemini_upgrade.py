"""Gemini 3.7 Flash migration and nutrition contract tests."""
from io import BytesIO
from pathlib import Path

import yaml
from google.genai import types
from PIL import Image, ImageDraw

from app.services.gemini_service import GeminiNutritionService
from app.services.poster_service import MealPosterService


def _nutrition_prompt_config():
    config_path = Path(__file__).parents[1] / "config" / "prompts" / "nutrition_core.yaml"
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def _recommendation_prompt_config():
    config_path = (
        Path(__file__).parents[1]
        / "config"
        / "prompts"
        / "nutrition_recommendations.yaml"
    )
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def test_nutrition_prompt_uses_uncertainty_aware_contract():
    config = _nutrition_prompt_config()
    schema = config["response_schema"]

    assert "analysis_quality" in schema["required"]
    assert "confidence" in schema["properties"]["identified_foods"]["items"]["properties"]
    assert "calorie_range_low" in schema["properties"]["nutrition_summary"]["properties"]
    assert "正常单人食量" in config["system_prompt"]
    assert "不得向用户追问" in config["system_prompt"]
    assert "recommendations" not in schema["properties"]

    recommendations = _recommendation_prompt_config()
    plans = recommendations["response_schema"]["properties"]["next_meal_recipes"]
    assert plans["minItems"] == plans["maxItems"] == 3
    assert "flavor_profile" in plans["items"]["required"]
    dish_schema = plans["items"]["properties"]["dishes"]["items"]
    assert "ingredients" in dish_schema["required"]
    assert "cooking_steps" in dish_schema["required"]
    assert dish_schema["properties"]["ingredients"]["maxItems"] == 5
    assert dish_schema["properties"]["cooking_steps"]["maxItems"] == 3
    assert "近7天" in recommendations["system_prompt"]
    assert "只能引用" in recommendations["system_prompt"]
    assert "不得把“小菜”臆测" in recommendations["system_prompt"]
    assert "禁止向用户提问" in recommendations["json_instruction"]


def test_vertex_nutrition_config_enforces_json_schema():
    service = object.__new__(GeminiNutritionService)
    service.config = _nutrition_prompt_config()

    generation_config = service._build_google_config(enable_search=False)

    assert generation_config.response_mime_type == "application/json"
    assert generation_config.response_json_schema["required"][-1] == "analysis_quality"
    assert generation_config.max_output_tokens == 4096
    assert generation_config.tools is None
    assert generation_config.temperature is None
    assert generation_config.thinking_config is None

    recommendation_config = service._build_google_config(
        prompt_config=_recommendation_prompt_config(),
        thinking_level=types.ThinkingLevel.LOW,
    )
    assert recommendation_config.thinking_config.thinking_level.value == "LOW"


def test_nutrition_contract_validation_requires_quality_metadata():
    service = object.__new__(GeminiNutritionService)
    result = {
        "identified_foods": [],
        "nutrition_summary": {},
        "nutrition_analysis": {},
        "health_insights": {},
        "recommendations": {},
    }

    assert service.validate_analysis_result(result) is False
    result["analysis_quality"] = {
        "overall_confidence": "low",
        "portion_assumption": "按单人正常午餐份量估算",
    }
    assert service.validate_analysis_result(result) is False

    result.update({
        "identified_foods": [{
            "name": "鸡胸肉", "category": "protein", "weight_g": 150,
            "calories": 250, "protein": 45, "carbs": 0, "fat": 7,
        }],
        "nutrition_summary": {
            "total_calories": 250, "total_protein": 45, "total_carbs": 0,
            "total_fat": 7, "total_fiber": 0, "total_weight": 150,
            "calorie_range_low": 220, "calorie_range_high": 300,
        },
        "nutrition_analysis": {
            "carbs_analysis": {"score": 40},
            "protein_analysis": {"score": 90},
            "fat_analysis": {"score": 80},
            "overall_score": 75,
        },
    })
    assert service.validate_analysis_result(result) is True


def test_poster_prompt_requires_exact_data_and_future_meal_visuals():
    service = object.__new__(MealPosterService)
    prompt = service._build_prompt({
        "poster_title": "本餐饮食健康报告",
        "verified_metrics": {"calories_kcal": 538, "protein_g": 32.4},
        "next_24_hours": [
            {"meal": "午餐", "recommended_foods": ["鸡胸肉", "糙米饭"]},
            {"meal": "晚餐", "recommended_foods": ["清蒸鱼", "青菜"]},
            {"meal": "次日早餐", "recommended_foods": ["鸡蛋", "燕麦"]},
        ],
    })

    assert "固定 3:4 竖版" in prompt
    assert '"calories_kcal":538' in prompt
    assert "无任何文字" in prompt
    assert "下方 59%–86%" in prompt
    assert "3 幅等宽、等高、尽量铺满单元" in prompt
    assert "推荐示意" in prompt
    assert "严禁在图片任何位置生成文字" in prompt
    assert "不生成深色底部页脚" in prompt
    assert "VERIFIED NUTRITION" not in prompt


def test_poster_conclusion_uses_a_complete_sentence_instead_of_character_slice():
    summary = "早餐以牛奶和甜面包为主，蛋白质与膳食纤维不足。结合今日恢复状态，午餐优先补充蔬菜。"

    conclusion = MealPosterService._first_complete_sentence(summary)

    assert conclusion == "早餐以牛奶和甜面包为主，蛋白质与膳食纤维不足。"
    assert not conclusion.endswith("...")


def test_poster_input_is_downscaled_and_encoded_as_jpeg():
    source = Image.new("RGB", (2400, 1200), "white")
    source_bytes = BytesIO()
    source.save(source_bytes, "PNG")

    prepared = MealPosterService._prepare_model_input(source_bytes.getvalue())

    with Image.open(BytesIO(prepared)) as result:
        assert result.format == "JPEG"
        assert result.size == (1600, 800)


def test_poster_compositor_draws_verified_content_without_a_footer():
    source = Image.new("RGB", (600, 800), (74, 112, 150))
    draw = ImageDraw.Draw(source)
    draw.rectangle((0, 0, 600, 270), fill=(180, 70, 45))
    source_bytes = BytesIO()
    source.save(source_bytes, "PNG")

    result_bytes = MealPosterService._compose_poster(
        source_bytes.getvalue(),
        {
            "poster_title": "本餐饮食健康报告",
            "meal": {"type": "早餐", "time": "2026年08月22日 09:34"},
            "verified_metrics": {
                "calories_kcal": 538,
                "protein_g": 32.4,
                "carbs_g": 61.2,
                "fat_g": 18.7,
            },
            "one_sentence_conclusion": "本餐蛋白质充足，下一餐注意补充蔬菜与全谷物。",
            "next_24_hours": [
                {
                    "meal": "午餐",
                    "timing": "12:30",
                    "calories_kcal": 650,
                    "recommended_foods": ["彩椒牛肉", "蒜蓉菜心", "糙米饭"],
                },
                {
                    "meal": "晚餐",
                    "timing": "18:30",
                    "calories_kcal": 580,
                    "recommended_foods": ["鲜虾煲", "白玉豆腐", "玉米"],
                },
                {
                    "meal": "次日早餐",
                    "timing": "08:00",
                    "calories_kcal": 480,
                    "recommended_foods": ["菠菜蛋饼", "五谷豆浆", "全麦吐司"],
                },
            ],
        },
    )

    with Image.open(BytesIO(result_bytes)) as result:
        assert result.format == "JPEG"
        assert result.size == (600, 800)
        # 三餐图片区仍保留底图，不再被全宽营养页脚覆盖。
        red, green, blue = result.getpixel((300, 560))
        assert blue > red and blue > green
        # 最底边也不再被旧版深色 VERIFIED NUTRITION 条覆盖。
        red, green, blue = result.getpixel((5, 790))
        assert blue > red and blue > green
