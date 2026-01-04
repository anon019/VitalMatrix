"""
Gemini AI 营养分析服务 - 支持 Google REST API 和 OpenRouter
"""
import os
import json
import yaml
import logging
import base64
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

# API 端点
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class GeminiNutritionService:
    """Gemini营养分析服务类 - 支持 Google REST API 和 OpenRouter"""

    def __init__(self):
        """初始化Gemini服务"""
        # 从环境变量获取API配置（支持热重载）
        self.reload_config()

        # 加载prompt配置
        self.config = self._load_prompt_config()

        logger.info(f"Gemini service initialized: provider={self.api_provider}, model={self.model_name}")

    def reload_config(self):
        """重新加载配置（支持动态切换API，无需重启服务）"""
        from dotenv import load_dotenv

        # 重新加载 .env 文件（force=True 会覆盖已有环境变量）
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)

        # API 提供商选择：google 或 openrouter
        self.api_provider = os.getenv("VISION_API_PROVIDER", "google").lower()

        if self.api_provider == "openrouter":
            # OpenRouter 配置
            self.api_key = os.getenv("OPENROUTER_API_KEY")
            if not self.api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable not set")
            self.model_name = os.getenv("OPENROUTER_VISION_MODEL", "google/gemini-3-pro-preview")
        else:
            # Google 原生 API 配置
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not self.api_key:
                raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set")
            self.model_name = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash-exp")

        logger.info(f"Config reloaded: provider={self.api_provider}, model={self.model_name}")

    def _load_prompt_config(self) -> Dict[str, Any]:
        """加载prompt配置文件"""
        config_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "nutrition_assistant.yaml"

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
        user_context: Optional[Dict[str, Any]] = None
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
        system_prompt = self.config.get("system_prompt", "")

        # 餐次类型中文翻译
        meal_types = self.config.get("meal_types", {})
        meal_type_cn = meal_types.get(meal_type, meal_type)

        # 构建用户上下文字符串
        user_context_str = ""
        if user_context:
            template = self.config.get("user_context_template", "")
            if template:
                try:
                    user_context_str = template.format(**user_context)
                except KeyError as e:
                    logger.warning(f"Missing key in user_context: {e}")

        # 用户提示词模板
        user_prompt = self.config.get("user_prompt_template", "")
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

    async def _call_google_api(self, prompt: str, image_data: str, mime_type: str) -> str:
        """
        调用 Google Gemini REST API

        Args:
            prompt: 完整提示词
            image_data: Base64 编码的图片数据
            mime_type: 图片 MIME 类型

        Returns:
            API 响应文本
        """
        url = GEMINI_API_URL.format(model=self.model_name)

        # 构建 generationConfig
        generation_config = {"maxOutputTokens": 8192}

        # Gemini 3 模型支持 thinkingConfig
        if "gemini-3" in self.model_name:
            generation_config["thinkingConfig"] = {"thinkingLevel": "low"}

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": image_data}}
                ]
            }],
            "generationConfig": generation_config
        }

        logger.info(f"Calling Google Gemini REST API: {self.model_name}")

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key
                }
            )

            if response.status_code == 503:
                logger.warning("Gemini API 503: Model overloaded")
                raise ValueError("Gemini API 503: 模型过载，请稍后重试")

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"Gemini API error: {response.status_code} - {error_detail}")
                raise ValueError(f"Gemini API error: {response.status_code} - {error_detail[:500]}")

            result_data = response.json()

        # 解析 Google API 响应
        if "candidates" not in result_data or not result_data["candidates"]:
            raise ValueError("API returned no candidates")

        parts = result_data["candidates"][0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("API returned empty parts")

        return parts[0].get("text", "")

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

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": os.environ.get("APP_DOMAIN", "https://your-domain.com"),
                    "X-Title": "Health Assistant"
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

    async def analyze_meal_photo(
        self,
        image_path: str,
        meal_type: str,
        meal_time: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        分析餐食照片 - 使用 Google Gemini REST API

        Args:
            image_path: 图片文件路径
            meal_type: 餐次类型 (breakfast/lunch/dinner/snack)
            meal_time: 用餐时间（格式："2025-11-22 12:30"）
            user_context: 用户上下文信息（可选）

        Returns:
            结构化的营养分析结果（JSON）

        Raises:
            FileNotFoundError: 图片文件不存在
            ValueError: API调用失败
        """
        try:
            # 热加载配置（每次调用时重新读取 .env 文件和 prompt 配置）
            self.reload_config()
            self.config = self._load_prompt_config()  # 重新加载 prompt 配置

            # 验证图片文件存在
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")

            # 构建prompt
            prompt = self._build_prompt(meal_type, meal_time, user_context)

            # 从配置文件读取JSON格式说明（支持热加载）
            json_instruction = self.config.get("json_instruction", "")
            if json_instruction:
                json_instruction = "\n\n" + json_instruction

            full_prompt = prompt + json_instruction

            # 读取图片并转为 base64
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            mime_type = self._get_mime_type(image_path)

            # 根据 API 提供商调用不同的 API
            if self.api_provider == "openrouter":
                response_text = await self._call_openrouter_api(full_prompt, image_data, mime_type)
            else:
                response_text = await self._call_google_api(full_prompt, image_data, mime_type)

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
                logger.info(f"Nutrition analysis completed successfully with {self.model_name}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Response text: {response_text[:500]}")
                # 抛出异常而不是返回错误对象，让调用方可以重试
                raise ValueError(f"AI响应JSON解析失败: {str(e)}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling Gemini API: {str(e)}", exc_info=True)
            raise ValueError(f"Gemini API HTTP error: {str(e)}")
        except Exception as e:
            logger.error(f"Nutrition analysis failed: {str(e)}", exc_info=True)
            raise

    async def analyze_meal_photo_with_retry(
        self,
        image_path: str,
        meal_type: str,
        meal_time: str,
        user_context: Optional[Dict[str, Any]] = None,
        max_retries: int = MAX_RETRIES
    ) -> Dict[str, Any]:
        """
        带重试机制的餐食照片分析

        Args:
            image_path: 图片文件路径
            meal_type: 餐次类型
            meal_time: 用餐时间
            user_context: 用户上下文
            max_retries: 最大重试次数

        Returns:
            结构化的营养分析结果

        Raises:
            ValueError: 重试多次后仍失败
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"AI分析尝试 {attempt + 1}/{max_retries}")
                result = await self.analyze_meal_photo(
                    image_path=image_path,
                    meal_type=meal_type,
                    meal_time=meal_time,
                    user_context=user_context
                )
                return result
            except ValueError as e:
                last_error = e
                logger.warning(f"AI分析失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"等待 {RETRY_DELAY} 秒后重试...")
                    await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                last_error = e
                logger.error(f"AI分析异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(RETRY_DELAY)

        # 所有重试都失败
        raise ValueError(f"AI分析在{max_retries}次尝试后仍失败: {str(last_error)}")

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
            "recommendations"
        ]

        for key in required_keys:
            if key not in result:
                logger.warning(f"Missing required key in analysis result: {key}")
                return False

        return True


# 全局单例实例（可选）
_gemini_service_instance = None


def get_gemini_service() -> GeminiNutritionService:
    """获取Gemini服务单例"""
    global _gemini_service_instance
    if _gemini_service_instance is None:
        _gemini_service_instance = GeminiNutritionService()
    return _gemini_service_instance
