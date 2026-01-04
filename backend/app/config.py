"""
应用配置管理
"""
from typing import Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    APP_NAME: str = "Health Assistant"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据库
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # Polar配置
    POLAR_CLIENT_ID: str
    POLAR_CLIENT_SECRET: str
    POLAR_REDIRECT_URI: str
    POLAR_BASE_URL: str = "https://www.polaraccesslink.com"

    # Oura配置
    OURA_CLIENT_ID: str = ""
    OURA_CLIENT_SECRET: str = ""
    OURA_REDIRECT_URI: str = ""  # 从环境变量读取

    # AI配置
    AI_PROVIDER: str = "qwen"  # qwen | deepseek | openai | claude

    # 通义千问 Qwen
    QWEN_API_KEY: str = ""

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # OpenAI (备选)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4-turbo-preview"

    # Claude (备选)
    CLAUDE_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-3-5-sonnet-20241022"

    # MCP API配置
    MCP_API_KEY: str = ""  # 用于本地MCP服务器访问

    # 微信小程序
    WECHAT_APP_ID: str
    WECHAT_APP_SECRET: str

    # 训练目标配置
    TARGET_ZONE2_MIN: int = 55
    TARGET_ZONE2_MIN_RANGE: int = 45
    TARGET_ZONE2_MAX_RANGE: int = 60
    TARGET_HI_MIN: int = 2
    TARGET_HI_MIN_RANGE: int = 1
    TARGET_HI_MAX_RANGE: int = 5
    TARGET_WEEKLY_ZONE2_MIN: int = 200
    TARGET_WEEKLY_ZONE2_MAX: int = 300
    TARGET_WEEKLY_HI_MAX: int = 30

    # 服务器环境配置
    TZ: str = "Asia/Hong_Kong"
    NO_PROXY: str = "localhost,127.0.0.1,::1,169.254.0.0/16,.tencentyun.com,*.tencentyun.com"

    # CORS配置 (从环境变量 ALLOWED_ORIGINS 读取，JSON 格式)
    ALLOWED_ORIGINS: list = [
        "https://servicewechat.com",  # 微信小程序
    ]

    # Web 前端访问密码（空字符串表示不需要密码）
    WEB_ACCESS_PASSWORD: str = ""

    # 日志配置
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"  # 忽略额外的环境变量
    )

    @property
    def target_zone2_range(self) -> Tuple[int, int]:
        """Zone2目标范围"""
        return (self.TARGET_ZONE2_MIN_RANGE, self.TARGET_ZONE2_MAX_RANGE)

    @property
    def target_hi_range(self) -> Tuple[int, int]:
        """高强度目标范围"""
        return (self.TARGET_HI_MIN_RANGE, self.TARGET_HI_MAX_RANGE)

    @property
    def target_weekly_zone2_range(self) -> Tuple[int, int]:
        """周Zone2目标范围"""
        return (self.TARGET_WEEKLY_ZONE2_MIN, self.TARGET_WEEKLY_ZONE2_MAX)


settings = Settings()
