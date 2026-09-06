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
    OURA_REDIRECT_URI: str = "https://your-domain.example.com/api/v1/oura/callback"
    OURA_TOKEN_REFRESH_THRESHOLD_DAYS: int = 3
    OURA_DATA_STALE_ALERT_DAYS: int = 1
    SERVER_ALERT_SCRIPT: str = ""

    # AI配置：所有文本、视觉和图片任务统一经 Codex CLI 调用。
    AI_PROVIDER: str = "codex"
    CODEX_CLI_PATH: str = "codex"
    CODEX_MODEL: str = "gpt-5.6-luna"
    CODEX_REASONING_EFFORT: str = "medium"
    CODEX_VISION_REASONING_EFFORT: str = "medium"
    CODEX_TEXT_REASONING_EFFORT: str = "low"
    CODEX_IMAGE_AGENT_REASONING_EFFORT: str = "low"
    CODEX_IMAGE_MODEL: str = "gpt-image-2"
    CODEX_MAX_CONCURRENCY: int = Field(2, ge=1, le=8)
    # 1K 足以满足手机端分享，同时显著降低图片模型耗时和海报传输体积；
    # 如需印刷级导出可通过环境变量切回 2K。
    POSTER_IMAGE_SIZE: str = "1K"

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

    # CORS配置
    ALLOWED_ORIGINS: list = [
        "https://servicewechat.com",  # 微信小程序
        "https://your-domain.example.com",
    ]

    # Web 前端访问密码（空字符串表示不需要密码）
    WEB_ACCESS_PASSWORD: str = ""
    PRIMARY_USER_ID: str = ""
    # 兼容旧部署；新部署应只配置 PRIMARY_USER_ID。
    DEFAULT_USER_ID: str = ""
    REQUIRE_WEB_ACCESS_PASSWORD: bool = True

    # 私有媒体与生成任务
    MEDIA_URL_TTL_SECONDS: int = 3600
    CODEX_REQUEST_TIMEOUT_SECONDS: int = Field(130, gt=0)
    NUTRITION_CORE_TIMEOUT_SECONDS: int = Field(60, gt=0)
    NUTRITION_CORE_TOTAL_TIMEOUT_SECONDS: int = Field(130, gt=0)
    NUTRITION_RECOMMENDATION_TIMEOUT_SECONDS: int = Field(180, gt=0)
    POSTER_REQUEST_TIMEOUT_SECONDS: int = Field(110, gt=0)
    POSTER_DAILY_LIMIT: int = 5

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
