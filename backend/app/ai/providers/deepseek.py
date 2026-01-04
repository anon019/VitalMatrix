"""
DeepSeek AI Provider实现
"""
import json
import logging
from typing import List, Optional, Dict, Any
from openai import AsyncOpenAI

from app.ai.base import (
    AIProvider,
    UserContext,
    TrainingData,
    Recommendation,
    Message,
    ChatResponse
)
from app.ai.prompt_loader import get_prompt_loader
from app.config import settings

logger = logging.getLogger(__name__)


class DeepSeekProvider(AIProvider):
    """DeepSeek AI Provider"""

    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.base_url = settings.DEEPSEEK_BASE_URL
        self.model_name = settings.DEEPSEEK_MODEL

        # 使用OpenAI SDK（DeepSeek兼容OpenAI API）
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        self.prompt_loader = get_prompt_loader()

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def model(self) -> str:
        return self.model_name

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
            # 构建Prompt
            system_prompt = self.prompt_loader.system_prompt
            user_prompt = self._build_recommendation_prompt(
                user_context, training_data, date
            )

            logger.debug(f"系统Prompt长度: {len(system_prompt)}")
            logger.debug(f"用户Prompt长度: {len(user_prompt)}")

            logger.info(f"调用DeepSeek生成建议: user_id={user_context.user_id}, date={date}")

            # 调用DeepSeek API
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=2000,
            )

            # 解析响应
            content = response.choices[0].message.content
            recommendation_data = json.loads(content)

            # 提取Token使用量
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else None
            completion_tokens = usage.completion_tokens if usage else None
            total_tokens = usage.total_tokens if usage else None

            # 构建返回对象
            recommendation = Recommendation(
                summary=recommendation_data.get("summary", ""),
                yesterday_review=recommendation_data.get("yesterday_review", ""),
                today_recommendation=recommendation_data.get("today_recommendation", ""),
                health_education=recommendation_data.get("health_education", ""),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            logger.info(
                f"DeepSeek建议生成成功: tokens={total_tokens}, "
                f"summary={recommendation.summary[:50]}..."
            )

            return recommendation

        except json.JSONDecodeError as e:
            logger.error(f"DeepSeek响应JSON解析失败: {str(e)}")
            raise ValueError(f"AI响应格式错误: {str(e)}")
        except Exception as e:
            logger.error(f"DeepSeek建议生成失败: {str(e)}")
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
            system_content = self.prompt_loader.system_prompt
            if context:
                system_content += f"\n\n当前用户上下文:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

            # 转换消息格式
            api_messages = [{"role": "system", "content": system_content}]
            for msg in messages:
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

            logger.info(f"DeepSeek对话: messages={len(messages)}")

            # 调用API
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=api_messages,
                temperature=0.8,
                max_tokens=1000,
            )

            # 提取回复
            reply = response.choices[0].message.content

            # Token使用量
            usage = response.usage
            usage_dict = {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            }

            logger.info(f"DeepSeek对话成功: tokens={usage_dict['total_tokens']}")

            return ChatResponse(message=reply, usage=usage_dict)

        except Exception as e:
            logger.error(f"DeepSeek对话失败: {str(e)}")
            raise

    async def close(self):
        """关闭客户端连接"""
        await self.client.close()
        logger.info("DeepSeek客户端已关闭")

    def _build_recommendation_prompt(
        self,
        user_context: UserContext,
        training_data: TrainingData,
        date: str
    ) -> str:
        """
        构建建议生成Prompt（新版3段式结构）

        Args:
            user_context: 用户上下文
            training_data: 训练数据
            date: 日期

        Returns:
            Prompt文本
        """
        # 构建用户基本信息
        user_profile = self._build_user_profile(user_context)

        # 构建 Oura 数据部分
        oura_section = self._build_oura_data_section(training_data.oura_data)

        # 构建训练数据部分
        training_section = f"""## 昨日训练数据
- 总时长：{training_data.total_duration_min}分钟
- Zone2时长：{training_data.zone2_min}分钟
- 高强度（Zone4-5）：{training_data.hi_min}分钟
- 训练负荷（TRIMP）：{training_data.trimp}
- 平均心率：{training_data.avg_hr or 'N/A'}
- 运动类型：{training_data.sport_type or '未知'}

## 近7天训练汇总
- 总时长：{training_data.weekly_total}分钟
- Zone2累计：{training_data.weekly_zone2}分钟
- 高强度累计：{training_data.weekly_hi}分钟
- 周训练负荷：{training_data.weekly_trimp}
- 训练天数：{training_data.training_days}天
- 休息天数：{training_data.rest_days}天"""

        # 构建风险标记
        risk_flags = []
        if training_data.flags.get("zone2_low"):
            risk_flags.append("⚠️ Zone2不足")
        if training_data.flags.get("hi_excessive"):
            risk_flags.append("⚠️ 高强度过量")
        if training_data.flags.get("consecutive_high"):
            risk_flags.append("⚠️ 连续高强度")
        if training_data.flags.get("weekly_overload"):
            risk_flags.append("⚠️ 周负荷过大")

        risk_section = "## 风险提示\n" + "\n".join(risk_flags) if risk_flags else "## 风险提示\n无明显风险"

        # 从配置文件读取任务模板
        task_template = self.prompt_loader.task_template

        # 构建完整的prompt
        prompt = f"""# 用户信息
{user_profile}

# 健康目标
{user_context.health_goal}

# 训练计划
{user_context.training_plan}

{training_section}

{oura_section}

{risk_section}

{task_template.format(date=date)}"""

        return prompt

    def _build_user_profile(self, user_context: UserContext) -> str:
        """
        构建用户基本信息文本

        Args:
            user_context: 用户上下文

        Returns:
            格式化的用户信息文本
        """
        profile_lines = []

        if user_context.nickname:
            profile_lines.append(f"昵称：{user_context.nickname}")

        # 基本信息（年龄等）
        basic_info = []
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

    def _build_oura_data_section(self, oura_data) -> str:
        """
        构建 Oura 数据部分的文本

        Args:
            oura_data: OuraData 对象

        Returns:
            格式化的 Oura 数据文本
        """
        if not oura_data:
            return "暂无 Oura 数据"

        sections = []

        # 睡眠数据
        if oura_data.sleep_score is not None:
            sleep_lines = [f"### 睡眠"]
            sleep_lines.append(f"- 睡眠评分：{oura_data.sleep_score}/100")
            if oura_data.total_sleep_hours:
                sleep_lines.append(f"- 总睡眠时长：{oura_data.total_sleep_hours}小时")
            if oura_data.deep_sleep_min:
                sleep_lines.append(f"- 深睡时长：{oura_data.deep_sleep_min}分钟")
            if oura_data.rem_sleep_min:
                sleep_lines.append(f"- REM时长：{oura_data.rem_sleep_min}分钟")
            if oura_data.sleep_efficiency:
                sleep_lines.append(f"- 睡眠效率：{oura_data.sleep_efficiency}%")
            if oura_data.average_hrv:
                sleep_lines.append(f"- 睡眠HRV：{oura_data.average_hrv}ms")
            sections.append("\n".join(sleep_lines))

        # 准备度数据
        if oura_data.readiness_score is not None:
            readiness_lines = [f"### 准备度"]
            readiness_lines.append(f"- 准备度评分：{oura_data.readiness_score}/100")
            if oura_data.recovery_index:
                readiness_lines.append(f"- 恢复指数：{oura_data.recovery_index}")
            if oura_data.resting_heart_rate:
                readiness_lines.append(f"- 静息心率：{oura_data.resting_heart_rate}bpm")
            if oura_data.hrv_balance:
                readiness_lines.append(f"- HRV平衡：{oura_data.hrv_balance}")
            sections.append("\n".join(readiness_lines))

        # 压力数据
        if oura_data.stress_high_min is not None or oura_data.recovery_high_min is not None:
            stress_lines = [f"### 压力与恢复"]
            if oura_data.stress_high_min is not None:
                stress_lines.append(f"- 高压力时长：{oura_data.stress_high_min}分钟")
            if oura_data.recovery_high_min is not None:
                stress_lines.append(f"- 高恢复时长：{oura_data.recovery_high_min}分钟")
            if oura_data.day_summary:
                stress_lines.append(f"- 日间状态：{oura_data.day_summary}")
            sections.append("\n".join(stress_lines))

        # 活动数据
        if oura_data.activity_score is not None:
            activity_lines = [f"### 日常活动"]
            activity_lines.append(f"- 活动评分：{oura_data.activity_score}/100")
            if oura_data.steps:
                activity_lines.append(f"- 步数：{oura_data.steps}步")
            if oura_data.active_calories:
                activity_lines.append(f"- 活动消耗：{oura_data.active_calories}千卡")
            sections.append("\n".join(activity_lines))

        if not sections:
            return "暂无 Oura 数据"

        return "\n\n".join(sections)
