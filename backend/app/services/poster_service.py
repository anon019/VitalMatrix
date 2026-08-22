"""按需生成餐食分享海报。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.ai.providers.gemini_client import get_client
from app.config import settings
from app.models.nutrition import MealRecord, MealType
from app.services.file_storage import get_file_storage
from app.utils.datetime_helper import format_hk, now_hk
from app.utils.redis_client import RedisClient

logger = logging.getLogger(__name__)


class MealPosterService:
    """用 Nano Banana 2 将餐食照片和结构化内容生成固定比例海报。"""

    STYLE_VERSION = "nutrition-poster-v9"
    INPUT_MAX_DIMENSION = 1600
    JPEG_QUALITY = 90
    _generation_locks: dict[str, asyncio.Lock] = {}
    MEAL_LABELS = {
        MealType.BREAKFAST: "早餐",
        MealType.LUNCH: "午餐",
        MealType.DINNER: "晚餐",
        MealType.SNACK: "加餐",
    }

    def __init__(self) -> None:
        self.client = get_client()
        self.storage = get_file_storage()
        self.model_name = settings.GEMINI_POSTER_MODEL

    @staticmethod
    def _number(value: Any, digits: int = 0) -> float | int | None:
        if value is None:
            return None
        number = round(float(value), digits)
        return int(number) if digits == 0 else number

    def _verified_metrics(self, meal: MealRecord) -> Dict[str, Any]:
        analysis = meal.gemini_analysis or {}
        nutrition = analysis.get("nutrition_summary") or {}
        quality = analysis.get("analysis_quality") or {}
        return {
            "calories_kcal": self._number(meal.total_calories),
            "protein_g": self._number(meal.total_protein, 1),
            "carbs_g": self._number(meal.total_carbs, 1),
            "fat_g": self._number(meal.total_fat, 1),
            "fiber_g": self._number(meal.total_fiber, 1),
            "calorie_range_low": self._number(nutrition.get("calorie_range_low")),
            "calorie_range_high": self._number(nutrition.get("calorie_range_high")),
            "confidence": quality.get("overall_confidence"),
        }

    @staticmethod
    def _first_complete_sentence(value: Any) -> str:
        """保留完整的第一句话，避免按字符数截出半句话。"""
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return ""
        match = re.match(r"^.*?[。！？!?][”’\"']?", text)
        return match.group(0).strip() if match else text

    def _build_content_template(self, meal: MealRecord) -> Dict[str, Any]:
        analysis = meal.gemini_analysis or {}
        nutrition_analysis = analysis.get("nutrition_analysis") or {}
        recommendations = analysis.get("recommendations") or {}

        future_meals = []
        for menu in (recommendations.get("next_meal_recipes") or [])[:3]:
            dish_names = [
                str(dish.get("name")).strip()
                for dish in (menu.get("dishes") or [])[:3]
                if dish.get("name")
            ]
            if dish_names:
                future_meals.append({
                    "meal": menu.get("meal_name"),
                    "timing": menu.get("timing"),
                    "calories_kcal": self._number(menu.get("total_calories")),
                    "recommended_foods": dish_names,
                    "visual_brief": "生成一份真实、自然、可日常复刻的完整餐盘，只出现 recommended_foods 中列出的食物",
                })

        return {
            "poster_title": "本餐饮食健康报告",
            "meal": {
                "type": self.MEAL_LABELS.get(meal.meal_type, meal.meal_type.value),
                "time": format_hk(meal.meal_time, "%Y年%m月%d日 %H:%M"),
            },
            "verified_metrics": self._verified_metrics(meal),
            "rating": {
                "score": nutrition_analysis.get("overall_score"),
                "label": nutrition_analysis.get("overall_rating"),
            },
            "one_sentence_conclusion": self._first_complete_sentence(
                recommendations.get("summary")
                or nutrition_analysis.get("overall_comment")
                or ""
            ),
            "next_24_hours": future_meals,
        }

    def _build_prompt(self, content: Dict[str, Any]) -> str:
        exact_json = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        return f"""你是 Nano Banana 2 的资深健康生活方式摄影指导。请以输入的真实餐食照片作为“本餐”主视觉，创作一张固定 3:4 竖版、无任何文字的健康杂志式餐食拼贴底图。后端会在固定区域排版全部中文和营养数字，因此你只负责照片、色彩、光影和背景。

核心视觉叙事：
- 上方 34% 使用原始餐食照片作为本餐的大幅主视觉，允许自然裁切、局部放大、景深延展和柔和色彩统一，但不得改变食物种类与数量。
- 画布 34%–59% 区域使用安静、低细节、与主色协调的编辑式背景，不放食物主体；系统会在此覆盖本餐四项营养和一句话结论。
- 下方 59%–86% 是未来三餐照片区：严格按照 next_24_hours 数组顺序从左到右生成 3 幅等宽、等高、尽量铺满单元的真实餐盘照片。三幅照片必须有清楚边界，不得重叠、错位或缩成小图标。
- 下方 86%–100% 使用与三幅餐图分别对应的低细节色块，不放食物主体；系统会在此覆盖餐名、时间和菜名。
- 每幅未来餐画面只表现对应 recommended_foods，呈现自然、可日常复刻的完整餐盘。
- 未来三餐图片是“推荐示意”，必须与本餐主照片在视觉上有明确区分，可用胶片切片、编辑式拼贴、柔边窗口或错落画框；不要把推荐菜伪装成当前已经吃过的食物。

视觉风格：
- 从原始照片提取主色，再加入牛油果绿、奶油白、番茄珊瑚橙或莓果紫中的 1–2 个活力强调色；避免全黑、全白或单一墨绿造成过于素淡。
- 使用细腻渐变、半透明色块、自然阴影、纸张纹理、手绘营养线条或小型植物图形增加层次，但装饰不能盖过食物。
- 严禁在图片任何位置生成文字、字母、数字、标点、标签、标题、网址、二维码、品牌水印、虚构 logo 或人物。即使事实简报包含文字，也只能理解其视觉含义，绝不能把它画进图片。
- 不生成深色底部页脚或额外安全区；画布必须完整铺满到最底边。

以下事实简报只用于理解本餐和三顿推荐餐的视觉内容：
{exact_json}
"""

    @classmethod
    def _prepare_model_input(cls, image_bytes: bytes) -> bytes:
        """用适合图片模型的分辨率发送原图，避免上传无效的超大像素。"""
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail(
            (cls.INPUT_MAX_DIMENSION, cls.INPUT_MAX_DIMENSION),
            Image.Resampling.LANCZOS,
        )
        output = BytesIO()
        image.save(output, "JPEG", quality=88)
        return output.getvalue()

    @staticmethod
    def _available_font(*candidates: str) -> Path:
        for candidate in candidates:
            path = Path(candidate)
            if path.is_file():
                return path
        raise RuntimeError("服务器缺少海报排版所需字体")

    @classmethod
    def _font_paths(cls) -> tuple[Path, Path]:
        regular = cls._available_font(
            "/usr/share/fonts/google-droid/DroidSansFallback.ttf",
            "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
        bold = cls._available_font(
            "/usr/share/fonts/google-droid/DroidSansFallback.ttf",
            "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
        return regular, bold

    @staticmethod
    def _wrap_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        for character in str(text):
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current.rstrip())
                current = character.lstrip()
            else:
                current = candidate
        if current:
            lines.append(current.rstrip())
        return lines or [""]

    @classmethod
    def _fit_wrapped_text(
        cls,
        draw: ImageDraw.ImageDraw,
        text: str,
        font_path: Path,
        preferred_size: int,
        minimum_size: int,
        max_width: int,
        max_height: int,
    ) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
        for size in range(preferred_size, minimum_size - 1, -1):
            font = ImageFont.truetype(str(font_path), size)
            lines = cls._wrap_text(draw, text, font, max_width)
            line_height = max(1, round(size * 1.28))
            if len(lines) * line_height <= max_height:
                return font, lines, line_height
        font = ImageFont.truetype(str(font_path), minimum_size)
        return font, cls._wrap_text(draw, text, font, max_width), round(minimum_size * 1.2)

    @staticmethod
    def _draw_lines(
        draw: ImageDraw.ImageDraw,
        position: tuple[int, int],
        lines: list[str],
        font: ImageFont.FreeTypeFont,
        line_height: int,
        fill: tuple[int, int, int, int],
    ) -> None:
        x, y = position
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += line_height

    @staticmethod
    def _metric_text(value: Any) -> str:
        return f"{value:g}" if isinstance(value, (int, float)) else "—"

    @classmethod
    def _compose_poster(cls, image_bytes: bytes, content: Dict[str, Any]) -> bytes:
        """在无文字底图上确定性排版关键内容，避免模型漏字、错字或截断。"""
        with Image.open(BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
        width, height = image.size
        canvas = image.convert("RGBA")
        draw = ImageDraw.Draw(canvas, "RGBA")
        regular_path, bold_path = cls._font_paths()
        margin = max(20, round(width * 0.032))
        radius = max(14, round(width * 0.022))
        inner = max(12, round(width * 0.018))

        # 主图标题：只加局部渐变，不缩小原始餐食画面。
        gradient_bottom = round(height * 0.20)
        for y in range(gradient_bottom):
            alpha = round(175 * (1 - y / gradient_bottom))
            draw.line((0, y, width, y), fill=(7, 24, 19, alpha))
        title_font = ImageFont.truetype(str(bold_path), max(30, round(height * 0.040)))
        meal_font = ImageFont.truetype(str(bold_path), max(18, round(height * 0.021)))
        time_font = ImageFont.truetype(str(regular_path), max(13, round(height * 0.014)))
        draw.text((margin, round(height * 0.027)), content["poster_title"], font=title_font, fill=(255, 255, 252, 255))
        meal_y = round(height * 0.090)
        draw.text((margin, meal_y), str(content["meal"].get("type") or ""), font=meal_font, fill=(218, 243, 224, 255))
        draw.text((margin, meal_y + round(height * 0.031)), str(content["meal"].get("time") or ""), font=time_font, fill=(245, 245, 238, 235))

        # 本餐营养：固定四列，所有数值由数据库字段绘制。
        metrics_top = round(height * 0.340)
        metrics_bottom = round(height * 0.448)
        draw.rounded_rectangle(
            (margin, metrics_top, width - margin, metrics_bottom),
            radius=radius,
            fill=(250, 247, 238, 244),
            outline=(255, 255, 255, 210),
            width=max(1, round(width * 0.002)),
        )
        metrics = content["verified_metrics"]
        metric_items = (
            ("热量", metrics.get("calories_kcal"), "kcal"),
            ("蛋白质", metrics.get("protein_g"), "g"),
            ("碳水", metrics.get("carbs_g"), "g"),
            ("脂肪", metrics.get("fat_g"), "g"),
        )
        metric_width = (width - 2 * margin) / 4
        label_font = ImageFont.truetype(str(regular_path), max(13, round(height * 0.014)))
        value_font = ImageFont.truetype(str(bold_path), max(24, round(height * 0.030)))
        unit_font = ImageFont.truetype(str(regular_path), max(11, round(height * 0.012)))
        for index, (label, value, unit) in enumerate(metric_items):
            left = round(margin + index * metric_width + inner)
            if index:
                separator_x = round(margin + index * metric_width)
                draw.line(
                    (separator_x, metrics_top + inner, separator_x, metrics_bottom - inner),
                    fill=(49, 77, 65, 55),
                    width=max(1, round(width * 0.0015)),
                )
            draw.text((left, metrics_top + round(height * 0.014)), label, font=label_font, fill=(55, 76, 67, 255))
            value_text = cls._metric_text(value)
            value_y = metrics_top + round(height * 0.043)
            draw.text((left, value_y), value_text, font=value_font, fill=(15, 49, 38, 255))
            value_width = draw.textlength(value_text, font=value_font)
            draw.text((left + value_width + max(4, round(width * 0.005)), value_y + round(height * 0.015)), unit, font=unit_font, fill=(72, 91, 83, 255))

        # 完整的一句话结论：先按语义取完整首句，再动态换行和缩放。
        conclusion_top = round(height * 0.458)
        conclusion_bottom = round(height * 0.548)
        draw.rounded_rectangle(
            (margin, conclusion_top, width - margin, conclusion_bottom),
            radius=radius,
            fill=(13, 48, 37, 238),
        )
        conclusion_label_font = ImageFont.truetype(str(bold_path), max(14, round(height * 0.015)))
        label_width = round(width * 0.19)
        draw.text(
            (margin + inner, conclusion_top + inner),
            "一句话结论",
            font=conclusion_label_font,
            fill=(174, 222, 185, 255),
        )
        conclusion = str(content.get("one_sentence_conclusion") or "")
        conclusion_x = margin + label_width
        max_conclusion_height = conclusion_bottom - conclusion_top - 2 * inner
        conclusion_font, conclusion_lines, conclusion_line_height = cls._fit_wrapped_text(
            draw,
            conclusion,
            regular_path,
            preferred_size=max(17, round(height * 0.020)),
            minimum_size=max(12, round(height * 0.012)),
            max_width=width - margin - inner - conclusion_x,
            max_height=max_conclusion_height,
        )
        cls._draw_lines(
            draw,
            (conclusion_x, conclusion_top + inner),
            conclusion_lines,
            conclusion_font,
            conclusion_line_height,
            (255, 255, 250, 255),
        )

        # 未来三餐占据海报下半部分；图片区域保持无遮挡，文字统一落在底部卡片。
        future_header_top = round(height * 0.558)
        image_top = round(height * 0.606)
        image_bottom = round(height * 0.852)
        label_bottom = round(height * 0.990)
        draw.rounded_rectangle(
            (margin, future_header_top, width - margin, image_top - round(height * 0.008)),
            radius=round(radius * 0.7),
            fill=(250, 247, 238, 235),
        )
        future_title_font = ImageFont.truetype(str(bold_path), max(20, round(height * 0.024)))
        future_note_font = ImageFont.truetype(str(regular_path), max(11, round(height * 0.012)))
        header_y = future_header_top + round(height * 0.008)
        draw.text((margin + inner, header_y), "未来三餐", font=future_title_font, fill=(15, 49, 38, 255))
        note = "推荐示意 · 按时间顺序"
        note_width = draw.textlength(note, font=future_note_font)
        draw.text((width - margin - inner - note_width, header_y + round(height * 0.011)), note, font=future_note_font, fill=(79, 96, 88, 255))

        gap = max(8, round(width * 0.012))
        card_width = (width - 2 * margin - 2 * gap) / 3
        future_meals = content.get("next_24_hours") or []
        for index, menu in enumerate(future_meals[:3]):
            left = round(margin + index * (card_width + gap))
            right = round(left + card_width)
            draw.rounded_rectangle(
                (left, image_top, right, label_bottom),
                radius=radius,
                outline=(255, 255, 255, 220),
                width=max(2, round(width * 0.003)),
            )
            draw.rounded_rectangle(
                (left, image_bottom, right, label_bottom),
                radius=radius,
                fill=(249, 246, 237, 248),
            )
            # 覆盖卡片上圆角之外的连接处，使图片与文字卡片无缝衔接。
            draw.rectangle((left, image_bottom, right, image_bottom + radius), fill=(249, 246, 237, 248))
            text_left = left + inner
            text_width = right - left - 2 * inner
            menu_name = str(menu.get("meal") or "推荐餐")
            timing = str(menu.get("timing") or "")
            calories = menu.get("calories_kcal")
            meal_name_font = ImageFont.truetype(str(bold_path), max(15, round(height * 0.017)))
            small_font = ImageFont.truetype(str(regular_path), max(10, round(height * 0.011)))
            draw.text((text_left, image_bottom + round(height * 0.010)), menu_name, font=meal_name_font, fill=(14, 48, 37, 255))
            calorie_text = f"{cls._metric_text(calories)} kcal" if calories is not None else ""
            calorie_width = draw.textlength(calorie_text, font=small_font)
            draw.text((right - inner - calorie_width, image_bottom + round(height * 0.013)), calorie_text, font=small_font, fill=(70, 91, 82, 255))
            timing_y = image_bottom + round(height * 0.039)
            draw.text((text_left, timing_y), timing, font=small_font, fill=(89, 103, 96, 255))
            foods = " · ".join(str(item) for item in (menu.get("recommended_foods") or []))
            foods_top = image_bottom + round(height * 0.061)
            foods_font, foods_lines, foods_line_height = cls._fit_wrapped_text(
                draw,
                foods,
                regular_path,
                preferred_size=max(12, round(height * 0.014)),
                minimum_size=max(9, round(height * 0.010)),
                max_width=text_width,
                max_height=label_bottom - foods_top - inner,
            )
            cls._draw_lines(
                draw,
                (text_left, foods_top),
                foods_lines,
                foods_font,
                foods_line_height,
                (35, 55, 47, 255),
            )

        output = BytesIO()
        canvas.convert("RGB").save(
            output,
            "JPEG",
            quality=cls.JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        return output.getvalue()

    async def _check_daily_limit(self, user_id: Any) -> None:
        key = f"nutrition:poster:daily:{user_id}:{now_hk().date().isoformat()}"
        try:
            count = await RedisClient.increment_with_expiry(key, int(timedelta(days=2).total_seconds()))
        except Exception as exc:
            logger.warning("Poster limiter unavailable, continuing with digest cache: %s", exc)
            return
        if count > settings.POSTER_DAILY_LIMIT:
            raise ValueError(f"今日海报生成次数已达 {settings.POSTER_DAILY_LIMIT} 次，请明天再试")

    async def generate(self, meal: MealRecord, force: bool = False) -> Dict[str, Any]:
        if not meal.photo_path:
            raise ValueError("餐次没有可用照片")

        source_path = self.storage.get_absolute_path(meal.photo_path)
        if not source_path.is_file():
            raise ValueError("餐次原图不存在")

        content = self._build_content_template(meal)
        if any(
            content["verified_metrics"].get(key) is None
            for key in ("calories_kcal", "protein_g", "carbs_g", "fat_g")
        ):
            raise ValueError("餐次缺少完整核心营养数据，暂时无法生成海报")
        if len(content["next_24_hours"]) != 3:
            raise ValueError("未来三餐建议尚未完整生成，请稍后再生成海报")
        digest_source = json.dumps(
            {
                "style": self.STYLE_VERSION,
                "model": self.model_name,
                "image_size": settings.POSTER_IMAGE_SIZE,
                "input_max_dimension": self.INPUT_MAX_DIMENSION,
                "content": content,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        digest = hashlib.sha256(digest_source).hexdigest()[:12]
        poster_path = source_path.with_name(f"{meal.id}_poster_{digest}.jpg")
        poster_url = meal.photo_path.rsplit("/", 1)[0] + "/" + poster_path.name

        lock = self._generation_locks.setdefault(digest, asyncio.Lock())
        async with lock:
            if poster_path.is_file() and not force:
                return {
                    "poster_url": poster_url,
                    "generated": False,
                    "model": self.model_name,
                    "verified_metrics": content["verified_metrics"],
                    "content_digest": digest,
                    "layout_version": self.STYLE_VERSION,
                }

            await self._check_daily_limit(meal.user_id)
            prompt = self._build_prompt(content)
            source_bytes = await asyncio.to_thread(source_path.read_bytes)
            image_bytes = await asyncio.to_thread(self._prepare_model_input, source_bytes)

            async with asyncio.timeout(settings.POSTER_REQUEST_TIMEOUT_SECONDS):
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                        candidate_count=1,
                        image_config=types.ImageConfig(
                            aspect_ratio="3:4",
                            image_size=settings.POSTER_IMAGE_SIZE,
                            output_mime_type="image/jpeg",
                        ),
                    ),
                )

            parts = response.candidates[0].content.parts if response.candidates else []
            generated_bytes = next(
                (part.inline_data.data for part in parts if part.inline_data and part.inline_data.data),
                None,
            )
            if not generated_bytes:
                raise ValueError("海报模型未返回图片，请稍后重试")

            composed_bytes = await asyncio.to_thread(
                self._compose_poster,
                generated_bytes,
                content,
            )
            temp_path = poster_path.with_suffix(".tmp")
            await asyncio.to_thread(temp_path.write_bytes, composed_bytes)
            await asyncio.to_thread(temp_path.replace, poster_path)
        logger.info(
            "Meal poster generated: meal_id=%s model=%s digest=%s",
            meal.id,
            self.model_name,
            digest,
        )
        return {
            "poster_url": poster_url,
            "generated": True,
            "model": self.model_name,
            "verified_metrics": content["verified_metrics"],
            "content_digest": digest,
            "layout_version": self.STYLE_VERSION,
        }


_poster_service: MealPosterService | None = None


def get_poster_service() -> MealPosterService:
    global _poster_service
    if _poster_service is None:
        _poster_service = MealPosterService()
    return _poster_service
