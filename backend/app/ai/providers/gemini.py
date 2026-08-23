"""
Google Gemini AI Provider 实现
使用 google-genai SDK，支持 Vertex AI 和 API Key 双模式
"""
import json
import logging
import asyncio
from typing import List, Optional, Dict, Any

from google.genai import types

from app.ai.base import (
    AIProvider,
    UserContext,
    TrainingData,
    Recommendation,
    Message,
    ChatResponse
)
from app.ai.prompt_loader import get_prompt_loader
from app.ai.prompt_sections import build_oura_data_section, build_training_section
from app.ai.providers.gemini_client import get_client
from app.config import settings
from app.schemas.ai import HealthEducation, TodayRecommendation, YesterdayReview

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """Google Gemini AI Provider（基于 google-genai SDK）"""

    def __init__(self):
        # 创建 google-genai 客户端
        self._client = get_client()

        # 文本建议与对话统一使用 Vertex AI 上的 Gemini 模型。
        self.model_name = settings.GEMINI_MODEL

        self.prompt_loader = get_prompt_loader()
        logger.info(f"Gemini Provider initialized (google-genai SDK): model={self.model_name}")

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self.model_name

    async def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 3000
    ) -> Dict[str, Any]:
        """
        调用 Gemini API（使用 google-genai SDK）

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            json_mode: 是否要求 JSON 输出
            temperature: 温度参数
            max_tokens: 最大输出 token

        Returns:
            包含 text 和 usage 的字典
        """
        # 构建生成配置
        config_kwargs = {
            "max_output_tokens": max_tokens,
            "system_instruction": system_prompt,
        }

        # Gemini 3.x 由模型管理采样参数；3.7 Flash 默认使用 Medium 思考级别。
        # 旧的 temperature / thinking_budget 会降低迁移兼容性，因此只对旧模型保留温度。
        if not self.model_name.startswith("gemini-3"):
            config_kwargs["temperature"] = temperature

        # JSON 模式
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
            if self.prompt_loader.response_schema:
                config_kwargs["response_json_schema"] = self.prompt_loader.response_schema

        config = types.GenerateContentConfig(**config_kwargs)

        async with asyncio.timeout(settings.GEMINI_REQUEST_TIMEOUT_SECONDS):
            response = await self._client.aio.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )

        # 构建兼容的返回格式
        text = response.text
        usage = response.usage_metadata

        return {
            "text": text,
            "usage": {
                "prompt_tokens": usage.prompt_token_count if usage else None,
                "completion_tokens": usage.candidates_token_count if usage else None,
                "total_tokens": usage.total_token_count if usage else None,
            }
        }

    async def generate_recommendation(
        self,
        user_context: UserContext,
        training_data: TrainingData,
        date: str,
    ) -> Recommendation:
        """
        生成训练建议

        Args:
            user_context: 用户上下文
            training_data: 训练数据
            date: 日期

        Returns:
            AI建议
        """
        try:
            self.prompt_loader.reload()
            # 构建 Prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_recommendation_prompt(
                user_context, training_data, date
            )

            logger.info(f"调用 Gemini 生成建议: user_id={user_context.user_id}, date={date}")

            # 调用 Gemini API
            result = await self._call_api(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.7,
                max_tokens=3000
            )

            # 解析响应
            content = result["text"]
            if not content:
                raise ValueError("API 返回空内容")

            recommendation_data = json.loads(content)
            summary = str(recommendation_data.get("summary", "")).strip()
            if not summary or len(summary) > 120:
                raise ValueError("AI summary is missing or too long")
            yesterday_review = YesterdayReview.model_validate(
                recommendation_data.get("yesterday_review")
            ).model_dump()
            today_recommendation = TodayRecommendation.model_validate(
                recommendation_data.get("today_recommendation")
            ).model_dump()
            health_education = HealthEducation.model_validate(
                recommendation_data.get("health_education")
            ).model_dump()

            # 提取 Token 使用量
            usage = result["usage"]

            # 构建返回对象
            recommendation = Recommendation(
                summary=summary,
                yesterday_review=yesterday_review,
                today_recommendation=today_recommendation,
                health_education=health_education,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            )

            logger.info(
                f"Gemini 建议生成成功: tokens={usage.get('total_tokens')}, "
                f"summary={recommendation.summary[:50]}..."
            )

            return recommendation

        except json.JSONDecodeError as e:
            logger.error(f"Gemini 响应 JSON 解析失败: {str(e)}")
            raise ValueError(f"AI 响应格式错误: {str(e)}")
        except Exception as e:
            logger.error(f"Gemini 建议生成失败: {str(e)}")
            raise

    async def chat(
        self,
        messages: List[Message],
        context: Optional[Dict[str, Any]] = None
    ) -> ChatResponse:
        """
        对话接口

        Args:
            messages: 消息历史
            context: 上下文数据（可选）

        Returns:
            AI回复
        """
        try:
            # 构建系统消息（包含上下文）
            system_content = self._build_system_prompt()
            if context:
                system_content += f"\n\n当前用户上下文:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

            # 构建用户消息（合并历史）
            user_content = "\n".join([
                f"{'用户' if msg.role == 'user' else 'AI'}: {msg.content}"
                for msg in messages
            ])

            logger.info(f"Gemini 对话: messages={len(messages)}")

            # 调用 API
            result = await self._call_api(
                system_prompt=system_content,
                user_prompt=user_content,
                json_mode=False,
                temperature=0.8,
                max_tokens=2000
            )

            # 解析响应
            reply = result["text"] or ""
            usage = result["usage"]

            usage_dict = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

            logger.info(f"Gemini 对话成功: tokens={usage_dict['total_tokens']}")

            return ChatResponse(message=reply, usage=usage_dict)

        except Exception as e:
            logger.error(f"Gemini 对话失败: {str(e)}")
            raise

    async def close(self):
        """关闭客户端（google-genai SDK 无需显式关闭）"""
        logger.info("Gemini 客户端已关闭")

    def _build_system_prompt(self) -> str:
        """构建系统 Prompt（从配置文件读取）"""
        return self.prompt_loader.system_prompt

    def _build_recommendation_prompt(
        self,
        user_context: UserContext,
        training_data: TrainingData,
        date: str
    ) -> str:
        """
        构建建议生成 Prompt

        Args:
            user_context: 用户上下文
            training_data: 训练数据
            date: 日期

        Returns:
            Prompt 文本
        """
        # 构建用户基本信息
        user_profile = self._build_user_profile(user_context)

        # 构建 Oura 数据部分
        oura_section = build_oura_data_section(training_data.oura_data)

        # 构建训练数据部分
        training_section = build_training_section(training_data)

        # 构建风险标记
        risk_flags = []
        if training_data.flags.get("zone2_low"):
            risk_flags.append("Zone2不足")
        if training_data.flags.get("hi_excessive"):
            risk_flags.append("高强度过量")
        if training_data.flags.get("consecutive_high"):
            risk_flags.append("连续高强度")
        if training_data.flags.get("weekly_overload"):
            risk_flags.append("周负荷过大")

        risk_section = "## 风险提示\n" + "\n".join([f"- {f}" for f in risk_flags]) if risk_flags else "## 风险提示\n无明显风险"

        # 构建营养数据部分
        nutrition_section = self._build_nutrition_section(training_data.nutrition_data)

        # 构建趋势摘要部分
        if training_data.trend_summary:
            trend_section = f"## 近期趋势变化\n{training_data.trend_summary}"
        else:
            trend_section = "## 近期趋势变化\n数据不足，暂无趋势分析"

        # 从配置文件读取任务模板
        task_template = self.prompt_loader.task_template

        # 构建完整的 prompt
        prompt = f"""# 用户信息
{user_profile}

# 健康目标
{user_context.health_goal}

# 训练计划
{user_context.training_plan}

{training_section}

{oura_section}

{nutrition_section}

{risk_section}

{trend_section}

{task_template.format(date=date)}"""

        return prompt

    def _build_user_profile(self, user_context: UserContext) -> str:
        """构建用户基本信息文本"""
        profile_lines = []

        if user_context.nickname:
            profile_lines.append(f"昵称：{user_context.nickname}")

        # 基本信息
        basic_info = []
        if user_context.gender:
            basic_info.append(f"性别{user_context.gender}")
        if user_context.age:
            basic_info.append(f"{user_context.age}岁")
        if basic_info:
            profile_lines.append("基本信息：" + "，".join(basic_info))

        # 身体数据
        physical_info = []
        if user_context.height:
            physical_info.append(f"身高{user_context.height}cm")
        if user_context.weight:
            physical_info.append(f"体重{user_context.weight}kg")
        if user_context.hr_max:
            physical_info.append(f"最大心率{user_context.hr_max}bpm")
        if user_context.resting_hr:
            physical_info.append(f"静息心率{user_context.resting_hr}bpm")

        if physical_info:
            profile_lines.append("身体数据：" + "，".join(physical_info))

        if not profile_lines:
            return "暂无个人信息"

        return "\n".join(profile_lines)

    def _build_nutrition_section(self, nutrition_data) -> str:
        """构建营养数据部分的文本"""
        if not nutrition_data or (not nutrition_data.days and not nutrition_data.recent_meals):
            return "## 近7天营养数据\n暂无饮食记录（用户未上传饮食照片，不代表未进食）"

        days_count = len(nutrition_data.days)
        sections = [f"## 近7天营养数据（共记录{days_count}天，未记录的天数表示用户未上传，非未进食）"]

        for day in nutrition_data.days:
            parts = [f"{day.date}"]
            if day.total_calories:
                parts.append(f"{day.total_calories:.0f}kcal")
            if day.total_protein:
                parts.append(f"蛋白质{day.total_protein:.0f}g")
            if day.total_carbs:
                parts.append(f"碳水{day.total_carbs:.0f}g")
            if day.total_fat:
                parts.append(f"脂肪{day.total_fat:.0f}g")
            parts.append(f"{day.meals_count}餐")

            # 营养flags
            if day.flags:
                flag_labels = {
                    "calorie_high": "热量偏高",
                    "calorie_low": "热量不足",
                    "protein_low": "蛋白质不足",
                    "protein_high": "蛋白质过高",
                    "carbs_high": "碳水偏高",
                    "carbs_low": "碳水偏低",
                    "fat_high": "脂肪偏高",
                    "fat_low": "脂肪偏低",
                }
                active_flags = [flag_labels[k] for k, v in day.flags.items() if v and k in flag_labels]
                if active_flags:
                    parts.append(f"⚠️{'、'.join(active_flags)}")

            sections.append(f"- {', '.join(parts)}")

        # 昨日详细：各餐热量
        yesterday = nutrition_data.days[-1] if nutrition_data.days else None
        if yesterday and yesterday.total_calories:
            meal_parts = []
            if yesterday.breakfast_calories:
                meal_parts.append(f"早餐{yesterday.breakfast_calories:.0f}")
            if yesterday.lunch_calories:
                meal_parts.append(f"午餐{yesterday.lunch_calories:.0f}")
            if yesterday.dinner_calories:
                meal_parts.append(f"晚餐{yesterday.dinner_calories:.0f}")
            if yesterday.snack_calories:
                meal_parts.append(f"加餐{yesterday.snack_calories:.0f}")
            if meal_parts:
                sections.append(f"- 昨日各餐热量(kcal): {', '.join(meal_parts)}")

        if nutrition_data.recent_meals:
            meal_labels = {
                "breakfast": "早餐",
                "lunch": "午餐",
                "dinner": "晚餐",
                "snack": "加餐",
            }
            sections.append("## 最近实际菜品（用于营养轮换与避免机械重复，不要逐条复述）")
            for meal in nutrition_data.recent_meals[:20]:
                if not meal.foods:
                    continue
                short_date = meal.date[5:10] if len(meal.date) >= 10 else meal.date
                sections.append(
                    f"- {short_date}{meal_labels.get(meal.meal_type, meal.meal_type)}："
                    f"{'、'.join(meal.foods)}"
                )
            sections.append(
                "推荐策略：先补足近几天较少出现的食物类别，并轮换蛋白质/蔬菜/主食；"
                "不要为了去重牺牲可执行性，也不要把未记录餐次当作未进食。"
            )

        return "\n".join(sections)

    def _build_oura_data_section(self, oura_data) -> str:
        """构建 Oura 数据部分的文本"""
        if not oura_data:
            return "## Oura数据\n暂无数据"

        sections = ["## Oura数据"]

        # 睡眠数据
        if oura_data.sleep_score is not None:
            sleep_parts = [f"睡眠评分{oura_data.sleep_score}/100"]
            if oura_data.total_sleep_hours:
                sleep_parts.append(f"时长{oura_data.total_sleep_hours}小时")
            if oura_data.deep_sleep_min:
                sleep_parts.append(f"深睡{oura_data.deep_sleep_min}分钟")
            if oura_data.rem_sleep_min:
                sleep_parts.append(f"REM{oura_data.rem_sleep_min}分钟")
            if oura_data.sleep_efficiency:
                sleep_parts.append(f"效率{oura_data.sleep_efficiency}%")
            if oura_data.average_hrv:
                sleep_parts.append(f"HRV{oura_data.average_hrv}ms")
            sections.append(f"- 睡眠：{', '.join(sleep_parts)}")

        # 准备度数据
        if oura_data.readiness_score is not None:
            readiness_parts = [f"评分{oura_data.readiness_score}/100"]
            if oura_data.recovery_index:
                readiness_parts.append(f"恢复指数{oura_data.recovery_index}")
            if oura_data.resting_heart_rate:
                readiness_parts.append(f"静息心率{oura_data.resting_heart_rate}bpm")
            sections.append(f"- 准备度：{', '.join(readiness_parts)}")

        # 活动数据
        if oura_data.activity_score is not None:
            activity_parts = [f"评分{oura_data.activity_score}/100"]
            if oura_data.steps:
                activity_parts.append(f"步数{oura_data.steps}")
            if oura_data.active_calories:
                activity_parts.append(f"消耗{oura_data.active_calories}卡")
            sections.append(f"- 活动：{', '.join(activity_parts)}")

        # 压力数据
        if oura_data.stress_high_min is not None or oura_data.day_summary:
            stress_parts = []
            if oura_data.day_summary:
                stress_parts.append(f"状态{oura_data.day_summary}")
            if oura_data.stress_high_min is not None:
                stress_parts.append(f"高压力{oura_data.stress_high_min}分钟")
            if oura_data.recovery_high_min is not None:
                stress_parts.append(f"高恢复{oura_data.recovery_high_min}分钟")
            if stress_parts:
                sections.append(f"- 压力：{', '.join(stress_parts)}")

        if len(sections) == 1:
            return "## Oura数据\n暂无数据"

        return "\n".join(sections)
