"""
Prompt加载器 - 从YAML配置文件加载Prompt模板
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 获取项目根目录
BACKEND_ROOT = Path(__file__).parent.parent.parent
DEFAULT_CONFIG_PATH = BACKEND_ROOT / "config" / "prompts" / "recommendation.yaml"


class PromptLoader:
    """Prompt加载器"""

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._config: Optional[Dict[str, Any]] = None
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            logger.info(f"Prompt配置加载成功: {self.config_path}")
        except Exception as e:
            logger.error(f"Prompt配置加载失败: {str(e)}")
            self._config = {}

    def reload(self):
        """重新加载配置（支持热更新）"""
        self._load_config()

    @property
    def system_prompt(self) -> str:
        """获取系统Prompt"""
        return self._config.get("system_prompt", "")

    @property
    def user_prompt_template(self) -> str:
        """获取用户Prompt模板"""
        return self._config.get("user_prompt_template", "")

    @property
    def task_template(self) -> str:
        """获取任务要求模板"""
        return self._config.get("task_template", "")

    @property
    def response_schema(self) -> Dict[str, Any]:
        """获取响应Schema"""
        return self._config.get("response_schema", {})

    @property
    def risk_flags(self) -> Dict[str, Dict[str, str]]:
        """获取风险标记说明"""
        return self._config.get("risk_flags", {})

    def build_user_prompt(self, **kwargs) -> str:
        """
        构建用户Prompt（变量替换）

        Args:
            **kwargs: 模板变量

        Returns:
            填充后的Prompt
        """
        template = self.user_prompt_template

        # 设置默认值
        defaults = {
            "health_goal": self._config.get("health_goal_default", "降脂心血管健康优化"),
            "training_plan": self._config.get("training_plan_default", "Zone2 55分钟 + Zone4-5 2分钟"),
        }

        # 合并默认值和传入参数
        params = {**defaults, **kwargs}

        # 处理风险标记描述
        if "flags" in params and isinstance(params["flags"], dict):
            flags_description = self._format_flags_description(params["flags"])
            params["flags_description"] = flags_description

        try:
            # 使用format进行变量替换
            prompt = template.format(**params)
            return prompt
        except KeyError as e:
            logger.error(f"Prompt模板变量缺失: {str(e)}")
            return template

    def _format_flags_description(self, flags: Dict[str, bool]) -> str:
        """
        格式化风险标记描述

        Args:
            flags: 风险标记字典

        Returns:
            格式化的描述文本
        """
        if not flags:
            return "无风险标记"

        descriptions = []
        for flag_key, is_active in flags.items():
            if is_active and flag_key in self.risk_flags:
                flag_info = self.risk_flags[flag_key]
                descriptions.append(
                    f"- **{flag_info['name']}** ({flag_info['severity']}): {flag_info['description']}"
                )

        if not descriptions:
            return "无风险标记"

        return "\n".join(descriptions)


# 全局单例
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """获取Prompt加载器单例"""
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
