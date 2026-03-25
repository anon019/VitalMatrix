# VitalMatrix

个人健康数据与 AI 分析系统，整合 Polar 训练数据、Oura 恢复数据、营养记录，并提供 Web Dashboard、微信小程序和 MCP 接入能力。

## 功能概览

- Polar 训练数据同步与训练指标汇总
- Oura 睡眠、准备度、活动、压力等恢复数据同步
- AI 每日建议、风险标记、趋势分析
- 营养照片上传、识别与每日营养汇总
- Web Dashboard 与微信小程序双端展示
- 内嵌 MCP 服务，支持外部 Agent / Client 通过 SSE 接入

## 仓库结构

```text
backend/        FastAPI 后端服务，包含 API、数据同步、AI、MCP、定时任务
web/            React + TypeScript Dashboard
miniprogram/    微信小程序前端
config/         提示词与配置模板
deploy/         部署示例与 Nginx 配置
docs/           架构与集成文档
```

## 系统架构

- `backend/` 是核心服务，提供 REST API、定时同步、AI 生成和 MCP。
- `web/` 提供桌面/移动浏览器可访问的可视化 Dashboard。
- `miniprogram/` 提供微信小程序端体验。
- MCP 已内嵌在后端中，不再单独维护独立 `mcp-server/` 服务。

主要访问入口：

- REST API: `/api/v1/*`
- Dashboard: 由 Nginx 托管 `web/dist`
- MCP SSE: `/mcp/sse`
- MCP REST-style data endpoints: `/api/v1/mcp/*`

## 技术栈

- Backend: FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler
- AI: DeepSeek / Qwen / Gemini（按配置启用）
- Web: React, TypeScript, Vite
- Mini Program: WeChat Mini Program
- Deploy: Linux, Nginx, systemd / supervisor

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/anon019/VitalMatrix.git
cd VitalMatrix
```

### 2. 初始化后端环境

```bash
bash scripts/setup_env.sh
```

该脚本会：

- 创建 `backend/venv`
- 安装 `backend/requirements.txt`
- 在缺失时创建 `backend/.env`

### 3. 配置环境变量

编辑 `backend/.env`，填入：

- 数据库连接
- Redis
- Polar OAuth
- Oura OAuth
- AI Provider Key
- `MCP_API_KEY`

可参考模板文件：

- `backend/.env.example`

### 4. 初始化数据库

```bash
cd backend
alembic upgrade head
```

### 5. 启动开发环境

后端：

```bash
bash scripts/start_dev.sh
```

Web：

```bash
cd web
npm install
npm run dev
```

## MCP 集成

MCP 服务已内嵌在后端中，默认随 FastAPI 一起启动。

- MCP 挂载入口：`/mcp`
- SSE transport：`/mcp/sse`
- API Key：使用 `MCP_API_KEY`

更详细的客户端接入方式见：

- `docs/openclaw-integration.md`

## 部署说明

- `deploy/nginx-health.conf` 提供公开仓库可用的 Nginx 模板，需要按你的域名、代码路径和证书路径调整。
- 生产环境建议通过 systemd 或 supervisor 启动后端服务。
- Web 构建产物默认由 Nginx 直接托管。

## 安全说明

以下内容不要提交到公开仓库：

- `backend/.env`
- `backend/uploads/`
- 本地证书文件
- OAuth token、API Key、数据库备份

仓库内保留的 `*.example`、部署模板和文档均为非敏感示例。
