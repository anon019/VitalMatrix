# Health Assistant - 系统架构设计

## 1. 系统概述

个人健康助理系统，专注于降脂心血管健康、睡眠和饮食管理。基于 Polar 训练数据驱动的 AI 智能分析系统。

**当前训练方案**: Zone2 55分钟 + Zone4-5 2分钟（心血管健康优化）

## 2. 设计原则

- **模块化**: 各模块独立，低耦合高内聚
- **可扩展**: 易于添加新数据源（Oura、Apple Health等）
- **可配置**: AI模型、训练目标、健康指标均可配置
- **单一职责**: 每个模块只负责特定功能
- **依赖倒置**: 面向接口编程，而非具体实现
- **健康档案长期保留**: 餐食原图、缩略图和结构化分析属于个人数据资产，不按文件年龄自动删除

饮食识图采用“核心识图同步返回、未来三餐异步生成”的两阶段链路；媒体保留、状态合同和前端缓存要求见 [`2026-08-21-nutrition-pipeline-and-media-retention.md`](2026-08-21-nutrition-pipeline-and-media-retention.md)。

## 3. 技术栈

### 后端服务
- **框架**: FastAPI 0.104+ (异步、高性能、自动API文档)
- **数据库**: PostgreSQL 14+ (支持JSON、时序数据)
- **缓存**: Redis 7+ (会话、数据缓存、任务队列)
- **ORM**: SQLAlchemy 2.0 (异步支持)
- **迁移**: Alembic
- **认证**: JWT (python-jose)
- **任务调度**: APScheduler 3.10+
- **HTTP客户端**: httpx (异步)

### AI服务
- **主力模型**: DeepSeek (经济、高性能)
- **备选**: OpenAI GPT-4, Claude 3.5
- **抽象层**: 统一 Provider 接口

### 前端
- **微信小程序**: 原生开发
- **图表**: ECharts (echarts-for-weixin)

### 部署
- **服务器**: Linux Server
- **反向代理**: Nginx
- **进程管理**: Supervisor / systemd
- **SSL**: 域名证书

## 4. 系统架构图

交互式最新版图表：

- [VitalMatrix 系统架构](diagrams/vitalmatrix-system-architecture.html)
- [营养分析与海报生成流程](diagrams/nutrition-poster-workflow.html)

HTML 图表是当前架构与关键流程的视觉基线；下面的文本图保留用于纯文本阅读。

```
┌─────────────────────────────────────────────────────────────┐
│                        WeChat Mini Program                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Today   │  │  Trends  │  │   AI     │  │ Settings │   │
│  │  Page    │  │  Page    │  │  Advice  │  │  Page    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS/REST API
┌────────────────────────▼────────────────────────────────────┐
│                      FastAPI Backend                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              API Layer (Routes)                       │  │
│  │  /auth  /polar  /training  /ai  /health              │  │
│  └──────────────────┬───────────────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────────────┐  │
│  │           Business Logic Layer                        │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐     │  │
│  │  │  Training  │  │   Health   │  │    Risk    │     │  │
│  │  │  Metrics   │  │  Analytics │  │ Assessment │     │  │
│  │  └────────────┘  └────────────┘  └────────────┘     │  │
│  └──────────────────┬───────────────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────────────┐  │
│  │              AI Service Layer                         │  │
│  │  ┌──────────────────────────────────────────┐        │  │
│  │  │      AI Provider (Abstract Interface)     │        │  │
│  │  └──────────┬───────────┬──────────┬─────────┘        │  │
│  │    ┌────────▼──┐  ┌─────▼────┐  ┌─▼────────┐        │  │
│  │    │ DeepSeek  │  │  OpenAI  │  │  Claude  │        │  │
│  │    └───────────┘  └──────────┘  └──────────┘        │  │
│  └──────────────────┬───────────────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────────────┐  │
│  │         Data Collection Layer                         │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐     │  │
│  │  │   Polar    │  │   Oura     │  │   Apple    │     │  │
│  │  │ AccessLink │  │    API     │  │   Health   │     │  │
│  │  └────────────┘  └────────────┘  └────────────┘     │  │
│  │      (v0.2)         (v0.3)          (Future)         │  │
│  └──────────────────┬───────────────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────────────┐  │
│  │           Data Storage Layer                          │  │
│  │  ┌────────────────┐      ┌─────────────────┐        │  │
│  │  │  PostgreSQL    │      │     Redis       │        │  │
│  │  │  (Main Store)  │      │  (Cache/Queue)  │        │  │
│  │  └────────────────┘      └─────────────────┘        │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │          Task Scheduler (APScheduler)                  │  │
│  │  • Polar数据同步 (每15分钟)                            │  │
│  │  • 指标计算 (每天 01:00)                               │  │
│  │  • AI建议生成 (每天 01:30)                             │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼────┐     ┌────▼────┐     ┌────▼────┐
   │  Polar  │     │DeepSeek │     │  Redis  │
   │   API   │     │   API   │     │  Server │
   └─────────┘     └─────────┘     └─────────┘
```

## 5. 模块详细设计

### 5.1 Data Collection Layer（数据采集层）

#### Polar Module (v0.2)
```python
# app/integrations/polar/
├── __init__.py
├── client.py           # Polar API客户端
├── oauth.py            # OAuth 2.0 流程
├── models.py           # Polar数据模型
└── constants.py        # Zone定义、API端点
```

**关键功能**:
- OAuth 2.0 授权流程
- AccessLink API集成
- 数据端点:
  - `/exercises` - 训练详情（含zone时长）
  - `/physical-information` - 体能基础（HR_max等）
  - `/daily-activity` - 日常活动数据

**扩展性设计**:
```python
# app/integrations/base.py
class DataSourceProvider(ABC):
    @abstractmethod
    async def authorize(self, user_id: str) -> AuthResult

    @abstractmethod
    async def fetch_training_data(self, start_date, end_date) -> List[TrainingSession]

    @abstractmethod
    async def fetch_sleep_data(self, start_date, end_date) -> List[SleepSession]
```

#### Future Extensions
- **Oura Module (v0.3)**: 睡眠数据采集
- **Apple Health Module (v0.4)**: 饮食、心率、步数等

### 5.2 Data Storage Layer（数据存储层）

#### 数据库设计

**核心表结构**:

```sql
-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    openid VARCHAR(64) UNIQUE NOT NULL,
    nickname VARCHAR(100),
    hr_max INTEGER,  -- 可手动覆盖Polar值
    resting_hr INTEGER,
    weight DECIMAL(5,2),
    height INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Polar训练记录（原始数据）
CREATE TABLE polar_exercises (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    exercise_id VARCHAR(100) UNIQUE NOT NULL,  -- Polar唯一ID
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    sport_type VARCHAR(50),
    duration_sec INTEGER NOT NULL,
    avg_hr INTEGER,
    max_hr INTEGER,
    zone1_sec INTEGER DEFAULT 0,
    zone2_sec INTEGER DEFAULT 0,
    zone3_sec INTEGER DEFAULT 0,
    zone4_sec INTEGER DEFAULT 0,
    zone5_sec INTEGER DEFAULT 0,
    calories INTEGER,
    cardio_load INTEGER,
    distance_meters DECIMAL(10,2),
    raw_json JSONB,  -- 完整原始数据
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_user_start_time (user_id, start_time DESC)
);

-- 日训练总结（聚合数据）
CREATE TABLE daily_training_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    date DATE NOT NULL,
    total_duration_min INTEGER,
    zone2_min INTEGER,
    hi_min INTEGER,  -- Zone4 + Zone5
    trimp DECIMAL(10,2),  -- 训练负荷
    sessions_count INTEGER,
    total_calories INTEGER,
    avg_hr INTEGER,
    flags JSONB,  -- {zone2_low: true, hi_excessive: false, ...}
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- 周训练总结
CREATE TABLE weekly_training_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    week_start_date DATE NOT NULL,
    total_duration_min INTEGER,
    zone2_min INTEGER,
    hi_min INTEGER,
    weekly_trimp DECIMAL(10,2),
    training_days INTEGER,
    rest_days INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, week_start_date)
);

-- AI建议记录
CREATE TABLE ai_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    date DATE NOT NULL,
    provider VARCHAR(50),  -- 'deepseek', 'openai', 'claude'
    summary TEXT,  -- 一句话总结
    training_advice JSONB,  -- {intensity: 'zone2', duration_min: 45-60}
    risk_assessment JSONB,  -- {level: 'low', warnings: [...]}
    action_items JSONB,  -- [{task: '晚间拉伸10分钟', completed: false}]
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- Polar授权信息
CREATE TABLE polar_auth (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) UNIQUE,
    polar_user_id VARCHAR(100),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 未来扩展：睡眠数据表
CREATE TABLE sleep_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    source VARCHAR(50),  -- 'oura', 'apple_health'
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    total_sleep_min INTEGER,
    deep_sleep_min INTEGER,
    rem_sleep_min INTEGER,
    light_sleep_min INTEGER,
    sleep_score INTEGER,
    raw_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Redis缓存策略
```
# 缓存键设计
user:session:{openid}           # 用户会话 (TTL: 7天)
polar:token:{user_id}           # Polar访问令牌 (TTL: 与token过期时间同步)
training:daily:{user_id}:{date} # 每日训练摘要 (TTL: 24小时)
ai:advice:{user_id}:{date}      # AI建议 (TTL: 24小时)
```

### 5.3 Business Logic Layer（业务逻辑层）

#### Training Metrics Engine
```python
# app/services/training_metrics.py

class TrainingMetricsService:
    """训练指标计算引擎"""

    async def calculate_zone_metrics(self, exercise: PolarExercise) -> ZoneMetrics:
        """计算Zone指标"""
        return ZoneMetrics(
            zone2_min=exercise.zone2_sec / 60,
            zone2_ratio=exercise.zone2_sec / exercise.duration_sec,
            hi_min=(exercise.zone4_sec + exercise.zone5_sec) / 60,
            hi_ratio=(exercise.zone4_sec + exercise.zone5_sec) / exercise.duration_sec,
        )

    async def calculate_trimp(self, exercise: PolarExercise) -> float:
        """计算TRIMP训练负荷"""
        if exercise.cardio_load:
            return exercise.cardio_load

        zone_weights = [1.0, 1.25, 1.5, 1.75, 2.0]
        zones = [
            exercise.zone1_sec, exercise.zone2_sec, exercise.zone3_sec,
            exercise.zone4_sec, exercise.zone5_sec
        ]
        return sum(z * w for z, w in zip(zones, zone_weights)) / 60

    async def calculate_daily_summary(self, user_id: UUID, date: date) -> DailySummary:
        """计算日训练总结"""
        # 聚合当日所有训练
        # 计算总时长、Zone2、HI、TRIMP
        # 生成风险标记
        pass

    async def calculate_weekly_summary(self, user_id: UUID, week_start: date) -> WeeklySummary:
        """计算周训练总结"""
        # 聚合7天数据
        # 计算趋势
        pass

    async def assess_training_status(self, daily: DailySummary, weekly: WeeklySummary) -> dict:
        """评估训练状态（规则引擎）"""
        flags = {}

        # 规则1: Zone2不足
        if daily.zone2_min < 40:
            flags['zone2_low'] = True

        # 规则2: 高强度过量
        if daily.hi_min > 10:
            flags['hi_excessive'] = True

        # 规则3: 周训练量低
        if weekly.total_duration_min < 150:
            flags['weekly_low'] = True

        # 规则4: 周训练量过载
        if weekly.total_duration_min > 350:
            flags['weekly_overload'] = True

        return flags
```

#### Health Analytics Service
```python
# app/services/health_analytics.py

class HealthAnalyticsService:
    """健康分析服务 - 降脂心血管专项"""

    async def calculate_cardiovascular_score(self, user_id: UUID) -> CVScore:
        """计算心血管健康得分"""
        # 基于Zone2训练量、静息心率趋势、HRV等
        pass

    async def analyze_fat_burning_efficiency(self, exercise: PolarExercise) -> float:
        """分析燃脂效率（Zone2占比）"""
        return exercise.zone2_sec / exercise.duration_sec

    async def track_resting_hr_trend(self, user_id: UUID, days: int = 30) -> Trend:
        """追踪静息心率趋势（心血管健康指标）"""
        pass
```

### 5.4 AI Service Layer（AI服务层）

#### 抽象Provider接口
```python
# app/ai/base.py

class AIProvider(ABC):
    """AI服务提供商抽象接口"""

    @abstractmethod
    async def generate_recommendation(
        self,
        user_context: UserContext,
        training_data: TrainingData,
        health_metrics: HealthMetrics
    ) -> Recommendation:
        """生成健康建议"""
        pass

    @abstractmethod
    async def chat(self, messages: List[Message]) -> ChatResponse:
        """对话接口"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""
        pass
```

#### DeepSeek实现
```python
# app/ai/providers/deepseek.py

class DeepSeekProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def generate_recommendation(self, user_context, training_data, health_metrics):
        prompt = self._build_prompt(user_context, training_data, health_metrics)

        response = await self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": HEALTH_ASSISTANT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )

        return self._parse_response(response)

    def _build_prompt(self, user_context, training_data, health_metrics):
        """构建Prompt（可配置化）"""
        return f"""
用户健康目标：降脂心血管健康优化
当前训练方案：Zone2 55分钟 + Zone4-5 2分钟

昨日训练数据：
- Zone2时长: {training_data.zone2_min}分钟 (目标: 45-60分钟)
- Zone4-5时长: {training_data.hi_min}分钟 (目标: 1-5分钟)
- 总训练负荷: {training_data.trimp}

最近7天汇总：
- Zone2累计: {training_data.weekly_zone2}分钟 (目标: 200-300分钟)
- 高强度累计: {training_data.weekly_hi}分钟 (建议: <30分钟)
- 训练天数: {training_data.training_days}天

风险标记：{training_data.flags}

请生成今日训练建议，JSON格式：
{{
    "summary": "一句话总结",
    "training_advice": {{
        "intensity": "rest|zone2|zone4-5",
        "duration_min": "建议时长范围",
        "rationale": "建议理由"
    }},
    "risk_assessment": {{
        "level": "low|medium|high",
        "warnings": ["风险提示1", "风险提示2"]
    }},
    "action_items": [
        {{"task": "具体行动1", "priority": "high|medium|low"}},
        {{"task": "具体行动2", "priority": "high|medium|low"}},
        {{"task": "具体行动3", "priority": "high|medium|low"}}
    ],
    "cardiovascular_insights": "心血管健康分析"
}}
"""

    @property
    def name(self) -> str:
        return "deepseek"
```

#### AI Provider工厂
```python
# app/ai/factory.py

class AIProviderFactory:
    _providers = {
        'deepseek': DeepSeekProvider,
        'openai': OpenAIProvider,
        'claude': ClaudeProvider,
    }

    @classmethod
    def create(cls, provider_name: str, config: dict) -> AIProvider:
        """根据配置创建AI提供商实例"""
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")
        return provider_class(**config)
```

### 5.5 API Layer（API层）

#### 路由结构
```python
# app/api/v1/
├── __init__.py
├── auth.py           # 微信登录、JWT
├── polar.py          # Polar OAuth、数据刷新
├── training.py       # 训练数据查询
├── ai.py             # AI建议获取、对话
├── health.py         # 健康指标
└── user.py           # 用户设置
```

#### 关键端点
```python
# app/api/v1/training.py

@router.get("/training/today")
async def get_today_training(current_user: User):
    """获取今日训练数据"""
    pass

@router.get("/training/weekly")
async def get_weekly_summary(current_user: User):
    """获取周汇总"""
    pass

@router.get("/training/history")
async def get_training_history(
    current_user: User,
    start_date: date,
    end_date: date,
    limit: int = 50
):
    """获取训练历史"""
    pass

# app/api/v1/ai.py

@router.get("/ai/recommendation/today")
async def get_today_recommendation(current_user: User):
    """获取今日AI建议"""
    pass

@router.post("/ai/chat")
async def chat_with_ai(request: ChatRequest, current_user: User):
    """AI对话"""
    pass

@router.post("/ai/regenerate")
async def regenerate_recommendation(
    date: date,
    current_user: User
):
    """重新生成建议（切换模型或重试）"""
    pass
```

### 5.6 Task Scheduler（任务调度）

```python
# app/scheduler/jobs.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('cron', hour=1, minute=0)
async def sync_polar_data():
    """每天01:00同步Polar数据"""
    users = await get_all_active_users()
    for user in users:
        await polar_service.sync_exercises(user.id, days=2)
        await polar_service.sync_physical_info(user.id)

@scheduler.scheduled_job('cron', hour=1, minute=15)
async def calculate_metrics():
    """每天01:15计算指标"""
    yesterday = date.today() - timedelta(days=1)
    users = await get_all_active_users()
    for user in users:
        await metrics_service.calculate_daily_summary(user.id, yesterday)
        await metrics_service.calculate_weekly_summary(user.id)

@scheduler.scheduled_job('cron', hour=1, minute=30)
async def generate_ai_recommendations():
    """每天01:30生成AI建议"""
    today = date.today()
    users = await get_all_active_users()
    for user in users:
        await ai_service.generate_daily_recommendation(user.id, today)

@scheduler.scheduled_job('interval', minutes=15)
async def poll_polar_notifications():
    """每15分钟轮询Polar新数据"""
    users = await get_users_with_polar_auth()
    for user in users:
        if await polar_service.has_new_data(user.id):
            await polar_service.sync_exercises(user.id, days=1)
```

## 6. 配置管理

### 环境配置
```python
# app/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "Health Assistant"
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False

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

    # AI配置
    AI_PROVIDER: str = "deepseek"  # deepseek | openai | claude

    # DeepSeek
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # OpenAI (备选)
    OPENAI_API_KEY: str = ""

    # Claude (备选)
    CLAUDE_API_KEY: str = ""

    # 微信小程序
    WECHAT_APP_ID: str
    WECHAT_APP_SECRET: str

    # 训练目标配置（可通过数据库覆盖）
    TARGET_ZONE2_MIN: int = 55
    TARGET_ZONE2_RANGE: tuple = (45, 60)
    TARGET_HI_MIN: int = 2
    TARGET_HI_RANGE: tuple = (1, 5)
    TARGET_WEEKLY_ZONE2: tuple = (200, 300)
    TARGET_WEEKLY_HI_MAX: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
```

### AI Prompt配置文件
```yaml
# config/prompts/health_assistant.yaml

system_prompt: |
  你是一个专业的个人健康助理，专注于心血管健康和降脂训练指导。
  基于用户的训练数据（心率区间、训练负荷等），提供科学的运动建议。

  核心原则：
  1. Zone2训练是有氧基础和燃脂的关键
  2. 高强度训练(Zone4-5)应适量，避免过度应激
  3. 重视训练负荷管理，防止过度训练
  4. 结合静息心率等指标评估心血管适应性

user_prompt_template: |
  用户健康目标：{health_goal}
  当前训练方案：{training_plan}

  昨日训练数据：
  - Zone2时长: {zone2_min}分钟 (目标: {target_zone2_range})
  - Zone4-5时长: {hi_min}分钟 (目标: {target_hi_range})
  - 总训练负荷: {trimp}

  最近7天汇总：
  - Zone2累计: {weekly_zone2}分钟 (目标: {target_weekly_zone2})
  - 高强度累计: {weekly_hi}分钟 (建议: <{target_weekly_hi_max}分钟)
  - 训练天数: {training_days}天

  风险标记：{flags}

  请生成今日训练建议...

response_schema:
  type: object
  required: [summary, training_advice, risk_assessment, action_items]
  properties:
    summary:
      type: string
      description: 一句话总结
    training_advice:
      type: object
      properties:
        intensity: {type: string, enum: [rest, zone2, zone4-5]}
        duration_min: {type: string}
        rationale: {type: string}
    risk_assessment:
      type: object
      properties:
        level: {type: string, enum: [low, medium, high]}
        warnings: {type: array, items: {type: string}}
    action_items:
      type: array
      items:
        type: object
        properties:
          task: {type: string}
          priority: {type: string, enum: [high, medium, low]}
    cardiovascular_insights: {type: string}
```

## 7. 扩展性设计

### 7.1 新数据源接入
```python
# 添加Oura睡眠数据源（v0.3）
# app/integrations/oura/client.py

class OuraProvider(DataSourceProvider):
    async def authorize(self, user_id: str) -> AuthResult:
        # Oura OAuth流程
        pass

    async def fetch_sleep_data(self, start_date, end_date) -> List[SleepSession]:
        # 调用Oura Sleep API
        pass
```

### 7.2 新AI模型接入
```python
# 添加Claude支持
# app/ai/providers/claude.py

class ClaudeProvider(AIProvider):
    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate_recommendation(self, user_context, training_data, health_metrics):
        # Claude API调用
        pass
```

### 7.3 新健康指标
```python
# 添加睡眠分析（v0.3）
# app/services/sleep_analytics.py

class SleepAnalyticsService:
    async def calculate_sleep_score(self, sleep_data: SleepSession):
        pass

    async def analyze_recovery(self, sleep_data: SleepSession, training_data: DailySummary):
        """分析睡眠恢复与训练负荷的关系"""
        pass
```

## 8. 安全性设计

- **认证**: JWT + 微信登录
- **授权**: 基于用户ID的资源隔离
- **API限流**: 防止滥用
- **敏感数据**: Polar token加密存储
- **HTTPS**: 全链路加密（已配置域名证书）
- **环境变量**: 敏感配置不进入代码仓库

## 9. 性能优化

- **数据库索引**: user_id + 时间范围查询优化
- **Redis缓存**: 每日数据、AI建议缓存
- **异步IO**: FastAPI + httpx全异步
- **连接池**: 数据库连接池、Redis连接池
- **分页查询**: 历史数据分页加载

## 10. 监控与日志

```python
# app/middleware/logging.py

import logging
from app.config import settings

# 结构化日志
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

# 关键指标监控
- Polar API调用成功率
- AI生成成功率、耗时
- 数据同步延迟
- API响应时间
```

## 11. 部署架构

```
┌─────────────────────────────────────────┐
│         Nginx (反向代理 + SSL)           │
│         your-domain.com                 │
└────────────┬────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
┌───▼────┐      ┌────▼────┐
│FastAPI │      │  Redis  │
│ (uvicorn) │      └─────────┘
│Supervisor│
└───┬────┘
    │
┌───▼─────────┐
│ PostgreSQL  │
└─────────────┘
```

**部署清单**:
- Nginx配置SSL和反向代理
- Supervisor管理FastAPI进程
- PostgreSQL数据库初始化
- Redis服务启动
- 环境变量配置
- 定时任务配置（cron或systemd timer）

## 12. 开发阶段规划

### Phase 1: 基础设施（1-2天）
- [x] 项目结构搭建
- [ ] 数据库设计与迁移
- [ ] FastAPI基础框架
- [ ] 配置管理

### Phase 2: Polar集成（2-3天）
- [ ] Polar OAuth流程
- [ ] AccessLink API客户端
- [ ] 数据同步服务
- [ ] 训练指标计算

### Phase 3: AI服务（2天）
- [ ] AI Provider抽象层
- [ ] DeepSeek集成
- [ ] Prompt工程
- [ ] 建议生成服务

### Phase 4: API开发（2天）
- [ ] 认证API
- [ ] 训练数据API
- [ ] AI建议API
- [ ] 用户设置API

### Phase 5: 小程序开发（3-4天）
- [ ] 今日页面
- [ ] 趋势页面
- [ ] AI建议页面
- [ ] 设置页面

### Phase 6: 任务调度（1天）
- [ ] 数据同步任务
- [ ] 指标计算任务
- [ ] AI生成任务

### Phase 7: 部署上线（1-2天）
- [ ] 服务器配置
- [ ] 数据库部署
- [ ] 应用部署
- [ ] 小程序发布

总计：**12-16天**完成MVP
