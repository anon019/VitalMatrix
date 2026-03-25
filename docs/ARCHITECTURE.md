# VitalMatrix 架构说明

## 1. 总体结构

VitalMatrix 由三个对外模块组成：

- `backend/`: FastAPI 后端，负责数据接入、业务逻辑、AI、MCP、定时任务
- `web/`: React + TypeScript Dashboard
- `miniprogram/`: 微信小程序端

其中 `backend/` 是系统核心。

## 2. 后端分层

`backend/app/` 主要分为：

- `api/`: REST 路由与依赖注入
- `models/`: SQLAlchemy 数据模型
- `services/`: 训练、恢复、营养、文件存储等业务服务
- `integrations/`: Polar / Oura 等第三方数据源接入
- `ai/`: Provider 抽象、提示词、建议生成
- `mcp/`: 内嵌 MCP 服务与工具定义
- `scheduler/`: 定时同步与自动任务

## 3. 数据流

### Polar

1. 用户完成 OAuth 授权
2. 后端定时或手动拉取训练数据
3. 原始训练写入数据库
4. 汇总服务计算日/周训练指标
5. AI 建议服务消费训练与恢复数据

### Oura

1. 用户完成 OAuth 授权
2. 后端同步睡眠、准备度、活动、压力等指标
3. 数据落库后供 Dashboard、MCP 和 AI 使用

### Nutrition

1. 客户端上传餐食图片
2. 后端保存文件并调用视觉模型识别
3. 写入餐次记录与日汇总
4. Dashboard / 小程序读取聚合结果

## 4. 对外接口

### REST API

- 业务主入口：`/api/v1/*`
- MCP 数据接口：`/api/v1/mcp/*`

### MCP

MCP 已内嵌到 FastAPI 进程中：

- 挂载入口：`/mcp`
- SSE endpoint：`/mcp/sse`

这种结构避免了独立 MCP 服务与主业务服务之间的数据和部署漂移。

## 5. 部署建议

- PostgreSQL 用于核心业务数据
- Redis 用于缓存和部分异步场景
- Nginx 提供 HTTPS、静态资源托管、API 与 MCP 反向代理
- 后端进程建议由 systemd 或 supervisor 管理

## 6. 公开仓库约束

公开仓库只保留代码、模板与文档。
以下内容必须留在部署环境或私有存储中：

- `.env`
- 上传资产
- OAuth token
- API Key
- 私有证书与备份
