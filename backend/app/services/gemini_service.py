"""
Gemini AI 营养分析服务 - 支持 google-genai SDK (Google) 和 OpenRouter (httpx)
"""
import os
import json
import yaml
import logging
import base64
import asyncio
import math
import time
from typing import Dict, Any, Optional
from pathlib import Path
import httpx

from google.genai import types

from app.ai.providers.gemini_client import get_client
from app.config import settings

logger = logging.getLogger(__name__)

# 重试配置
MAX_RETRIES = 2
RETRY_DELAY = 2  # 秒
CORE_PROMPT_FILE = "nutrition_core.yaml"
RECOMMENDATION_PROMPT_FILE = "nutrition_recommendations.yaml"

# OpenRouter API 端点（仅 OpenRouter 使用）
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class GeminiNutritionService:
    """Gemini营养分析服务类 - 支持 google-genai SDK (Google) 和 OpenRouter (httpx)"""

    def __init__(self):
        """初始化Gemini服务"""
        # 从环境变量获取API配置（支持热重载）
        self.reload_config()

        # 加载prompt配置
        self.config = self._load_prompt_config(CORE_PROMPT_FILE)

        logger.info(f"Gemini service initialized: provider={self.api_provider}, model={self.model_name}")

    def reload_config(self):
        """重新加载配置（支持动态切换API，无需重启服务）"""
        from dotenv import load_dotenv

        # 重新加载 .env 文件（force=True 会覆盖已有环境变量）
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)

        old_provider = getattr(self, 'api_provider', None)

        # API 提供商选择：google 或 openrouter
        self.api_provider = os.getenv("VISION_API_PROVIDER", "google").lower()

        if self.api_provider == "openrouter":
            # OpenRouter 配置
            self.api_key = os.getenv("OPENROUTER_API_KEY")
            if not self.api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable not set")
            self.model_name = os.getenv("OPENROUTER_VISION_MODEL", "google/gemini-3-pro-preview")
            # OpenRouter 使用 httpx 客户端（复用已有连接）
            if not hasattr(self, '_http_client') or self._http_client is None:
                self._http_client = httpx.AsyncClient(timeout=180.0)
        else:
            # Google 原生 API 配置（使用 google-genai SDK，模块级缓存）
            self.model_name = os.getenv("GEMINI_VISION_MODEL", "gemini-3.7-flash")
            self._genai_client = get_client()

            # 从 openrouter 切换到 google 时，标记旧 httpx 客户端待关闭
            if old_provider == "openrouter" and hasattr(self, '_http_client') and self._http_client:
                self._pending_close_http_client = self._http_client
                self._http_client = None

        logger.info(f"Config reloaded: provider={self.api_provider}, model={self.model_name}")

    def _load_prompt_config(self, filename: str = CORE_PROMPT_FILE) -> Dict[str, Any]:
        """加载prompt配置文件"""
        config_path = Path(__file__).parent.parent.parent / "config" / "prompts" / filename

        if not config_path.exists():
            logger.warning(f"Prompt config not found at {config_path}, using default prompts")
            return self._get_default_config()

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        logger.info(f"Loaded prompt config from {config_path}")
        return config

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置（当YAML文件不存在时使用）"""
        return {
            "system_prompt": "你是专业的营养分析AI助手。",
            "user_prompt_template": "请分析这张餐食照片。",
            "response_schema": {}
        }

    def _build_prompt(
        self,
        meal_type: str,
        meal_time: str,
        user_context: Optional[Dict[str, Any]] = None,
        prompt_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        构建完整的分析提示词

        Args:
            meal_type: 餐次类型 (breakfast/lunch/dinner/snack)
            meal_time: 用餐时间
            user_context: 用户上下文信息（可选）

        Returns:
            完整的prompt字符串
        """
        # 系统提示词
        prompt_config = prompt_config or self.config
        system_prompt = prompt_config.get("system_prompt", "")

        # 餐次类型中文翻译
        meal_types = prompt_config.get("meal_types", {})
        meal_type_cn = meal_types.get(meal_type, meal_type)

        # 构建用户上下文字符串
        user_context_str = ""
        if user_context:
            template = prompt_config.get("user_context_template", "")
            if template:
                try:
                    user_context_str = template.format(**user_context)
                except KeyError as e:
                    logger.warning(f"Missing key in user_context: {e}")

        # 用户提示词模板
        user_prompt = prompt_config.get("user_prompt_template", "")
        user_prompt = user_prompt.format(
            meal_type=meal_type_cn,
            meal_time=meal_time,
            user_context=user_context_str
        )

        # 组合完整prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        return full_prompt

    def _get_mime_type(self, image_path: str) -> str:
        """根据文件扩展名获取 MIME 类型"""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "image/jpeg")

    async def _call_google_api(
        self,
        prompt: str,
        image_data: str,
        mime_type: str,
        enable_search: bool = False,
        prompt_config: Optional[Dict[str, Any]] = None,
        max_output_tokens: int = 4096,
        timeout_seconds: Optional[int] = None,
    ) -> str:
        """
        调用 Google Gemini API（使用 google-genai SDK）

        Args:
            prompt: 完整提示词
            image_data: Base64 编码的图片数据
            mime_type: 图片 MIME 类型
            enable_search: 是否启用 Google Search grounding

        Returns:
            API 响应文本
        """
        # 将 base64 图片数据解码为字节
        image_bytes = base64.standard_b64decode(image_data)

        # 构建多模态内容
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ]

        config = self._build_google_config(
            enable_search=enable_search,
            prompt_config=prompt_config,
            max_output_tokens=max_output_tokens,
        )

        started_at = time.perf_counter()
        logger.info(
            "Calling Google Gemini SDK: model=%s stage=core max_output_tokens=%s",
            self.model_name,
            max_output_tokens,
        )

        async with asyncio.timeout(
            timeout_seconds or settings.NUTRITION_CORE_TIMEOUT_SECONDS
        ):
            response = await self._genai_client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

        text = response.text
        self._log_google_response(response, "core", started_at, text)
        if not text:
            raise ValueError("API 返回空内容")

        return text

    def _build_google_config(
        self,
        enable_search: bool = False,
        prompt_config: Optional[Dict[str, Any]] = None,
        max_output_tokens: int = 4096,
        thinking_level: Optional[types.ThinkingLevel] = None,
    ) -> types.GenerateContentConfig:
        """构建 Vertex Gemini 配置，集中管理结构化输出和可选工具。"""
        config_kwargs: Dict[str, Any] = {
            "max_output_tokens": max_output_tokens,
            "response_mime_type": "application/json",
        }

        # Vertex 结构化输出比在提示词里重复粘贴 JSON 示例更稳定、更省 token。
        prompt_config = prompt_config or self.config
        response_schema = prompt_config.get("response_schema")
        if response_schema:
            config_kwargs["response_json_schema"] = response_schema

        if thinking_level is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=thinking_level,
            )

        # 启用 Google Search grounding
        if enable_search:
            config_kwargs["tools"] = [
                types.Tool(google_search=types.GoogleSearch())
            ]
            logger.info("Google Search grounding enabled for recipe recommendations")

        return types.GenerateContentConfig(**config_kwargs)

    @staticmethod
    def _log_google_response(response, stage: str, started_at: float, text: Optional[str]) -> None:
        """记录外部模型耗时和停止原因，不记录用户图片或完整内容。"""
        finish_reason = None
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)
        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "Gemini response: stage=%s duration_ms=%.1f chars=%s finish_reason=%s "
            "prompt_tokens=%s output_tokens=%s total_tokens=%s",
            stage,
            (time.perf_counter() - started_at) * 1000,
            len(text or ""),
            finish_reason,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "total_token_count", None),
        )

    async def _call_google_text_api(
        self,
        prompt: str,
        prompt_config: Dict[str, Any],
        max_output_tokens: int = 4096,
    ) -> str:
        config = self._build_google_config(
            prompt_config=prompt_config,
            max_output_tokens=max_output_tokens,
            thinking_level=types.ThinkingLevel.LOW,
        )
        started_at = time.perf_counter()
        logger.info(
            "Calling Google Gemini SDK: model=%s stage=recommendations max_output_tokens=%s",
            self.model_name,
            max_output_tokens,
        )
        async with asyncio.timeout(settings.NUTRITION_RECOMMENDATION_TIMEOUT_SECONDS):
            response = await self._genai_client.aio.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=config,
            )
        text = response.text
        self._log_google_response(response, "recommendations", started_at, text)
        if not text:
            raise ValueError("API 返回空内容")
        return text

    async def _call_openrouter_api(self, prompt: str, image_data: str, mime_type: str) -> str:
        """
        调用 OpenRouter API (OpenAI 兼容格式)

        Args:
            prompt: 完整提示词
            image_data: Base64 编码的图片数据
            mime_type: 图片 MIME 类型

        Returns:
            API 响应文本
        """
        # OpenRouter 使用 OpenAI 兼容的 chat/completions 格式
        payload = {
            "model": self.model_name,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}"
                        }
                    }
                ]
            }],
            "max_tokens": 8192
        }

        logger.info(f"Calling OpenRouter API: {self.model_name}")

        async with asyncio.timeout(settings.GEMINI_REQUEST_TIMEOUT_SECONDS):
            response = await self._http_client.post(
                OPENROUTER_API_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": settings.OPENROUTER_HTTP_REFERER,
                    "X-Title": settings.OPENROUTER_APP_TITLE,
                }
            )

        if response.status_code == 503:
            logger.warning("OpenRouter API 503: Service unavailable")
            raise ValueError("OpenRouter API 503: 服务暂时不可用")

        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"OpenRouter API error: {response.status_code} - {error_detail}")
            raise ValueError(f"OpenRouter API error: {response.status_code} - {error_detail[:500]}")

        result_data = response.json()

        # 解析 OpenRouter (OpenAI 格式) 响应
        if "choices" not in result_data or not result_data["choices"]:
            raise ValueError("API returned no choices")

        return result_data["choices"][0].get("message", {}).get("content", "")

    async def _call_openrouter_text_api(self, prompt: str) -> str:
        """OpenRouter 文本调用，用于不再携带图片的扩展建议阶段。"""
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        async with asyncio.timeout(settings.NUTRITION_RECOMMENDATION_TIMEOUT_SECONDS):
            response = await self._http_client.post(
                OPENROUTER_API_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": settings.OPENROUTER_HTTP_REFERER,
                    "X-Title": settings.OPENROUTER_APP_TITLE,
                },
            )
        if response.status_code != 200:
            raise ValueError(
                f"OpenRouter API error: {response.status_code} - {response.text[:500]}"
            )
        data = response.json()
        if not data.get("choices"):
            raise ValueError("API returned no choices")
        return data["choices"][0].get("message", {}).get("content", "")

    async def analyze_meal_photo(
        self,
        image_path: str,
        meal_type: str,
        meal_time: str,
        user_context: Optional[Dict[str, Any]] = None,
        enable_recipe_search: bool = False
    ) -> Dict[str, Any]:
        """
        分析餐食照片 - 使用 Google Gemini SDK 或 OpenRouter

        Args:
            image_path: 图片文件路径
            meal_type: 餐次类型 (breakfast/lunch/dinner/snack)
            meal_time: 用餐时间（格式："2025-11-22 12:30"）
            user_context: 用户上下文信息（可选）
            enable_recipe_search: 是否启用联网搜索获取食谱（默认关闭，减少延迟并聚焦本餐分析）

        Returns:
            结构化的营养分析结果（JSON）

        Raises:
            FileNotFoundError: 图片文件不存在
            ValueError: API调用失败
        """
        try:
            # 热加载配置（每次调用时重新读取 .env 文件和 prompt 配置）
            self.reload_config()
            await self._cleanup_pending_clients()  # 清理 provider 切换遗留的客户端
            prompt_config = self._load_prompt_config(CORE_PROMPT_FILE)

            # 验证图片文件存在
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")

            # 构建prompt
            prompt = self._build_prompt(
                meal_type, meal_time, user_context, prompt_config=prompt_config
            )

            # 从配置文件读取JSON格式说明（支持热加载）
            json_instruction = prompt_config.get("json_instruction", "")
            if json_instruction:
                json_instruction = "\n\n" + json_instruction

            full_prompt = prompt + json_instruction

            # OpenRouter 没有使用上面的 Vertex response_json_schema，需要把结构契约写入提示词。
            if self.api_provider == "openrouter" and prompt_config.get("response_schema"):
                full_prompt += "\n\n必须符合以下 JSON Schema：\n" + json.dumps(
                    prompt_config["response_schema"], ensure_ascii=False
                )

            # 读取图片并转为 base64
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            mime_type = self._get_mime_type(image_path)

            # 根据 API 提供商调用不同的 API
            # 注意：Google Search grounding 仅在使用 Google 原生 API 时可用
            if self.api_provider == "openrouter":
                response_text = await self._call_openrouter_api(full_prompt, image_data, mime_type)
            else:
                response_text = await self._call_google_api(
                    full_prompt, image_data, mime_type,
                    enable_search=False,
                    prompt_config=prompt_config,
                    max_output_tokens=4096,
                )

            # 验证响应文本
            if not response_text:
                raise ValueError("API returned empty content")

            # 提取JSON
            json_text = self._extract_json(response_text)

            # 解析JSON
            try:
                result = json.loads(json_text)
                # 验证结果完整性
                if not self.validate_analysis_result(result):
                    raise ValueError("AI分析结果不完整，缺少必要字段")
                # 添加模型名称到返回结果
                result["_ai_model"] = self.model_name
                result["_schema_version"] = prompt_config.get("version", "nutrition-core-v1")
                result["_search_grounded"] = False
                quality = dict(result.get("analysis_quality") or {})
                # 保留旧前端字段，但一次性识图流程永远不向用户追问。
                quality["needs_user_confirmation"] = False
                quality["questions"] = []
                result["analysis_quality"] = quality
                result["recommendations"] = {
                    "status": "pending",
                    "summary": "本餐核心分析已完成，后续建议生成中",
                    "next_meal_tips": [],
                    "next_meal_recipes": [],
                    "action_items": [],
                }
                logger.info(f"Nutrition analysis completed successfully with {self.model_name}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Response text: {response_text[:500]}")
                # 抛出异常而不是返回错误对象，让调用方可以重试
                raise ValueError(f"AI响应JSON解析失败: {str(e)}")

        except Exception as e:
            logger.error(f"Nutrition analysis failed: {str(e)}", exc_info=True)
            raise

    async def analyze_meal_photo_with_retry(
        self,
        image_path: str,
        meal_type: str,
        meal_time: str,
        user_context: Optional[Dict[str, Any]] = None,
        max_retries: int = MAX_RETRIES,
        enable_recipe_search: bool = False
    ) -> Dict[str, Any]:
        """
        带重试机制的餐食照片分析

        Args:
            image_path: 图片文件路径
            meal_type: 餐次类型
            meal_time: 用餐时间
            user_context: 用户上下文
            max_retries: 最大重试次数
            enable_recipe_search: 是否启用联网搜索获取食谱（默认关闭）

        Returns:
            结构化的营养分析结果

        Raises:
            ValueError: 重试多次后仍失败
        """
        last_error = None
        retry_started = time.perf_counter()

        for attempt in range(max_retries):
            try:
                remaining = (
                    settings.NUTRITION_CORE_TOTAL_TIMEOUT_SECONDS
                    - (time.perf_counter() - retry_started)
                )
                if remaining <= 0:
                    raise TimeoutError("核心识图超过总耗时上限")
                logger.info(f"AI分析尝试 {attempt + 1}/{max_retries}")
                async with asyncio.timeout(remaining):
                    result = await self.analyze_meal_photo(
                        image_path=image_path,
                        meal_type=meal_type,
                        meal_time=meal_time,
                        user_context=user_context,
                        enable_recipe_search=enable_recipe_search
                    )
                return result
            except ValueError as e:
                last_error = e
                logger.warning(f"AI分析失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    logger.info(f"等待 {delay} 秒后重试...")
                    await asyncio.sleep(delay)
            except Exception as e:
                last_error = e
                logger.error(f"AI分析异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))

        # 所有重试都失败
        raise ValueError(f"AI分析在{max_retries}次尝试后仍失败: {str(last_error)}")

    async def generate_recommendations(
        self,
        core_analysis: Dict[str, Any],
        meal_type: str,
        meal_time: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """基于已保存的核心识图结果生成扩展建议，不再发送图片。"""
        self.reload_config()
        await self._cleanup_pending_clients()
        prompt_config = self._load_prompt_config(RECOMMENDATION_PROMPT_FILE)
        meal_type_cn = prompt_config.get("meal_types", {}).get(meal_type, meal_type)
        compact_core = {
            "identified_foods": [
                {
                    "name": item.get("name"),
                    "weight_g": item.get("weight_g"),
                    "calories": item.get("calories"),
                    "protein": item.get("protein"),
                }
                for item in (core_analysis.get("identified_foods") or [])[:12]
            ],
            "nutrition_summary": core_analysis.get("nutrition_summary") or {},
            "nutrition_analysis": core_analysis.get("nutrition_analysis") or {},
            "health_insights": core_analysis.get("health_insights") or {},
        }
        prompt = prompt_config.get("system_prompt", "") + "\n\n" + prompt_config.get(
            "user_prompt_template", ""
        ).format(
            meal_type=meal_type_cn,
            meal_time=meal_time,
            core_analysis=json.dumps(compact_core, ensure_ascii=False, separators=(",", ":")),
            user_context=json.dumps(user_context or {}, ensure_ascii=False, separators=(",", ":")),
        )
        instruction = prompt_config.get("json_instruction", "")
        if instruction:
            prompt += "\n\n" + instruction

        if self.api_provider == "openrouter":
            prompt += "\n\n必须符合以下 JSON Schema：\n" + json.dumps(
                prompt_config["response_schema"], ensure_ascii=False
            )
            response_text = await self._call_openrouter_text_api(prompt)
        else:
            response_text = await self._call_google_text_api(
                prompt,
                prompt_config=prompt_config,
                max_output_tokens=4096,
            )

        try:
            recommendations = json.loads(self._extract_json(response_text))
        except json.JSONDecodeError as exc:
            raise ValueError(f"扩展建议JSON解析失败: {exc}") from exc

        plans = recommendations.get("next_meal_recipes")
        if not isinstance(plans, list) or len(plans) != 3:
            raise ValueError("扩展建议必须包含未来三顿正餐")
        for plan in plans:
            dishes = plan.get("dishes") if isinstance(plan, dict) else None
            if not isinstance(dishes, list) or not 2 <= len(dishes) <= 3:
                raise ValueError("每顿推荐必须包含2至3道菜")
            for dish in dishes:
                ingredients = dish.get("ingredients") if isinstance(dish, dict) else None
                cooking_steps = dish.get("cooking_steps") if isinstance(dish, dict) else None
                if not isinstance(ingredients, list) or not 2 <= len(ingredients) <= 5:
                    raise ValueError("每道菜必须包含2至5项主要食材")
                if not isinstance(cooking_steps, list) or not 2 <= len(cooking_steps) <= 3:
                    raise ValueError("每道菜必须包含2至3条做法步骤")
        recommendations["next_meal_tips"] = [
            {
                "meal": plan.get("meal_name", ""),
                "suggestion": "、".join(
                    str(dish.get("name", "")) for dish in (plan.get("dishes") or [])
                    if dish.get("name")
                ),
                "health_benefit": plan.get("why_this_menu", ""),
            }
            for plan in plans
        ]
        recommendations["status"] = "completed"
        return recommendations

    def _extract_json(self, text: str) -> str:
        """
        从响应文本中提取JSON（更健壮的方式）

        处理可能的markdown代码块包裹：```json ... ```
        以及JSON后的额外文本

        Args:
            text: 原始响应文本

        Returns:
            提取的JSON字符串
        """
        text = text.strip()

        # 去除markdown代码块标记
        if text.startswith("```json"):
            text = text[7:]  # 移除 ```json
        elif text.startswith("```"):
            text = text[3:]  # 移除 ```

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        # 使用更robust的方式：找到第一个完整的JSON对象
        # 通过匹配花括号来提取
        try:
            # 找到第一个 {
            start = text.find('{')
            if start == -1:
                return text

            # 计数花括号来找到匹配的 }
            count = 0
            end = start
            for i, char in enumerate(text[start:], start):
                if char == '{':
                    count += 1
                elif char == '}':
                    count -= 1
                    if count == 0:
                        end = i + 1
                        break

            if end > start:
                return text[start:end]
        except Exception:
            pass  # 如果提取失败，返回原始text

        return text

    def validate_analysis_result(self, result: Dict[str, Any]) -> bool:
        """
        验证分析结果的完整性

        Args:
            result: 分析结果字典

        Returns:
            是否有效
        """
        required_keys = [
            "identified_foods",
            "nutrition_summary",
            "nutrition_analysis",
            "health_insights",
            "analysis_quality",
        ]

        for key in required_keys:
            if key not in result:
                logger.warning(f"Missing required key in analysis result: {key}")
                return False

        foods = result.get("identified_foods")
        summary = result.get("nutrition_summary")
        analysis = result.get("nutrition_analysis")
        quality = result.get("analysis_quality")
        if not isinstance(foods, list) or not 1 <= len(foods) <= 20:
            logger.warning("identified_foods must contain 1-20 items")
            return False
        if not all(
            isinstance(value, dict)
            for value in (summary, analysis, quality)
        ):
            return False

        def valid_number(value: Any, maximum: float) -> bool:
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and 0 <= float(value) <= maximum
            )

        food_limits = {
            "weight_g": 5000,
            "calories": 5000,
            "protein": 500,
            "carbs": 1000,
            "fat": 500,
        }
        for food in foods:
            if not isinstance(food, dict) or not str(food.get("name", "")).strip():
                return False
            if food.get("category") not in {
                "staple", "protein", "vegetable", "fruit", "dairy",
                "fat", "beverage", "snack", "other",
            }:
                return False
            if any(not valid_number(food.get(field), limit) for field, limit in food_limits.items()):
                return False

        summary_limits = {
            "total_calories": 10000,
            "total_protein": 1000,
            "total_carbs": 2000,
            "total_fat": 1000,
            "total_fiber": 500,
            "total_weight": 10000,
        }
        if any(not valid_number(summary.get(field), limit) for field, limit in summary_limits.items()):
            return False

        total_calories = float(summary["total_calories"])
        foods_calories = sum(float(food["calories"]) for food in foods)
        if abs(foods_calories - total_calories) > max(150, total_calories * 0.4):
            logger.warning("Food calories and summary are inconsistent")
            return False

        macro_calories = (
            float(summary["total_protein"]) * 4
            + float(summary["total_carbs"]) * 4
            + float(summary["total_fat"]) * 9
        )
        if abs(macro_calories - total_calories) > max(200, total_calories * 0.5):
            logger.warning("Macro calories and total calories are inconsistent")
            return False

        low = summary.get("calorie_range_low")
        high = summary.get("calorie_range_high")
        if low is not None or high is not None:
            if not valid_number(low, 10000) or not valid_number(high, 10000):
                return False
            if float(low) > total_calories or float(high) < total_calories or float(low) > float(high):
                return False

        for section_name in ("carbs_analysis", "protein_analysis", "fat_analysis"):
            section = analysis.get(section_name)
            if not isinstance(section, dict) or not valid_number(section.get("score"), 100):
                return False
        if not valid_number(analysis.get("overall_score"), 100):
            return False
        if quality.get("overall_confidence") not in {"high", "medium", "low"}:
            return False
        if not str(quality.get("portion_assumption", "")).strip():
            return False

        return True

    async def _cleanup_pending_clients(self):
        """关闭因 provider 切换而遗留的旧客户端"""
        if hasattr(self, '_pending_close_http_client') and self._pending_close_http_client:
            try:
                await self._pending_close_http_client.aclose()
                logger.info("已关闭旧的 httpx 客户端（provider 切换）")
            except Exception as e:
                logger.warning(f"关闭旧 httpx 客户端失败: {e}")
            finally:
                self._pending_close_http_client = None

    async def close(self):
        """关闭所有 HTTP 客户端连接"""
        if hasattr(self, '_http_client') and self._http_client:
            await self._http_client.aclose()
        await self._cleanup_pending_clients()
        logger.info("GeminiNutritionService 客户端已关闭")


# 全局单例实例（可选）
_gemini_service_instance = None


def get_gemini_service() -> GeminiNutritionService:
    """获取Gemini服务单例"""
    global _gemini_service_instance
    if _gemini_service_instance is None:
        _gemini_service_instance = GeminiNutritionService()
    return _gemini_service_instance
