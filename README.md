# VitalMatrix
<p align="center">
<img width="2816" height="1536" alt="Gemini_Generated_Image_q7znusq7znusq7zn" src="https://github.com/user-attachments/assets/a1d3df14-2c21-4d2f-8a91-5ba16aa34c30" />
</p>

<p align="center">
  <strong>🏃 运动 · 😴 睡眠 · 💪 恢复 · 🍎 营养 — 全方位个人健康管理</strong>
</p>

<p align="center">
  基于 <b>Polar（训练数据）+ Oura（恢复数据）+ AI 智能分析</b> 的健康助理系统
</p>


---

## ✨ 核心功能

### 📊 数据集成
| 数据源 | 采集内容 |
|--------|----------|
| **Polar** | 训练记录、心率区间（Zone1-5）、训练负荷、夜间恢复 |
| **Oura** | 睡眠质量、HRV、准备度、压力、活动、血氧 |
| **营养** | 拍照识别食物，AI 分析营养成分和热量 |

### 🤖 AI 智能分析
- **每日健康建议** — 综合训练+恢复数据，生成个性化训练建议
- **风险评估** — 9 种风险标记（Zone2 不足、高强度过量、周负荷过载等）
- **趋势分析** — 7 天训练时长、Zone2、TRIMP、HRV 趋势图表

### 📱 多端支持
- **微信小程序** — 移动端查看和管理
- **Web 应用** — Apple Health 风格 UI

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│               用户端 (小程序 / Web)                           │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────────┐
│                    FastAPI Backend                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   API Layer: /polar /oura /training /ai /nutrition   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   AI Providers: DeepSeek / Qwen / Gemini Vision      │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Data Layer: PostgreSQL + Redis + APScheduler       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │              │              │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │  Polar  │    │  Oura   │    │ Gemini  │
    │   API   │    │   API   │    │ Vision  │
    └─────────┘    └─────────┘    └─────────┘
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | FastAPI + Python 3.10 (异步) |
| **数据库** | PostgreSQL + SQLAlchemy + Alembic |
| **缓存** | Redis |
| **Web 前端** | React + Vite + TailwindCSS + Recharts |
| **小程序** | 微信原生小程序 + 原生 Canvas |
| **AI 服务** | DeepSeek / Qwen（文本）、Gemini Vision（图像） |
| **定时任务** | APScheduler |
| **部署** | Nginx + systemd + Let's Encrypt |

---

## 📁 项目结构

```
VitalMatrix/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/          # API 路由
│   │   ├── models/          # 数据库模型
│   │   ├── services/        # 业务逻辑
│   │   ├── ai/              # AI 提供者
│   │   └── integrations/    # Polar/Oura 集成
│   ├── alembic/             # 数据库迁移
│   └── config/prompts/      # AI 提示词
├── web/                     # React Web 前端
│   └── src/
│       ├── pages/           # 页面组件
│       └── components/      # UI 组件
├── miniprogram/             # 微信小程序
│   ├── pages/
│   │   ├── index/           # 首页
│   │   ├── trends/          # 趋势
│   │   ├── ai/              # AI 建议
│   │   ├── nutrition/       # 营养
│   │   └── settings/        # 设置
│   ├── CHANGELOG.md         # 小程序版本记录
│   └── README.md            # 小程序本地开发说明
├── mcp-server/              # Claude Code MCP 集成
└── deploy/                  # 部署配置
```

---

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/anon019/VitalMatrix.git
cd VitalMatrix
```

### 2. 后端配置

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Keys
```

### 3. 数据库初始化

```bash
createdb health_db
alembic upgrade head
```

### 4. 启动服务

```bash
# 开发模式
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 访问 API 文档
open http://localhost:8000/docs
```

### 5. Web 前端

```bash
cd web
npm install
npm run dev
```

### 6. 微信小程序

```bash
cd miniprogram
# 使用微信开发者工具打开当前目录
```

- 仓库中的 `miniprogram/project.config.json` 保持占位 AppID，用于安全共享
- 本地开发请参考 `miniprogram/project.config.json.example` 或直接在开发者工具中配置自己的 AppID
- 小程序当前同步版本为 `0.2.1`，详细变更见 `miniprogram/CHANGELOG.md`

---

## 📱 小程序说明

- 当前小程序版本：`0.2.1`
- 已包含最近一轮性能与体验优化：
  - 页面首屏加载去重
  - 登录失效后的自动重登保护
  - 本地时区日期修正
  - 趋势页心率恢复数据延后加载
  - 饮食页汇总与缓存刷新修复
- 小程序详细开发说明见 `miniprogram/README.md`

---

## ⚙️ 环境变量

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/health_db
REDIS_URL=redis://localhost:6379/0

# Polar OAuth
POLAR_CLIENT_ID=your-client-id
POLAR_CLIENT_SECRET=your-client-secret

# Oura OAuth
OURA_CLIENT_ID=your-client-id
OURA_CLIENT_SECRET=your-client-secret

# AI 服务
DEEPSEEK_API_KEY=your-api-key
GOOGLE_API_KEY=your-api-key  # Gemini
```

---

## 📡 API 端点

| 模块 | 端点 | 说明 |
|------|------|------|
| **Dashboard** | `GET /api/v1/dashboard/today` | 今日综合数据 |
| **Polar** | `POST /api/v1/polar/sync` | 同步训练数据 |
| **Oura** | `POST /api/v1/oura/sync` | 同步恢复数据 |
| **Training** | `GET /api/v1/training/weekly` | 周训练汇总 |
| **AI** | `GET /api/v1/ai/recommendation/today` | 今日 AI 建议 |
| **Nutrition** | `POST /api/v1/nutrition/upload` | 上传餐食照片分析 |
| **Trends** | `GET /api/v1/trends/overview` | 趋势数据 |

---

## 📊 AI 建议结构

AI 生成的健康建议包含：

- **昨日评价** — 训练评分、睡眠评分、恢复评分
- **今日建议** — 建议强度、时长、具体理由
- **风险评估** — 过度训练、休息不足等风险标记
- **行动项** — 具体可执行的健康建议

---

## 🔒 隐私说明

- 所有健康数据仅存储在你的私有服务器
- 不收集或分享任何用户数据
- API Keys 通过环境变量安全管理

---

## 📜 License

MIT License

---

## 🙏 致谢

- [Polar](https://www.polar.com/) — 专业运动数据
- [Oura](https://ouraring.com/) — 睡眠与恢复追踪
- [DeepSeek](https://www.deepseek.com/) — AI 模型服务
- [FastAPI](https://fastapi.tiangolo.com/) — 现代 Python Web 框架
