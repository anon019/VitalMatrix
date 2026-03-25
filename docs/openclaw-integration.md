# VitalMatrix MCP / OpenClaw 集成指南

## 1. 接入方式

VitalMatrix 的 MCP 服务已内嵌在后端中。

- MCP 挂载入口：`https://your-domain.example.com/mcp`
- SSE endpoint：`https://your-domain.example.com/mcp/sse`
- REST 数据接口：`https://your-domain.example.com/api/v1/mcp`

如果客户端使用 `mcp-remote`，通常连接 MCP 挂载入口即可。

## 2. OpenClaw 配置示例

编辑 `~/.openclaw/openclaw.json`：

```json
{
  "mcpServers": {
    "vitalmatrix": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-domain.example.com/mcp",
        "--header",
        "X-API-Key:${VITALMATRIX_API_KEY}"
      ],
      "env": {
        "VITALMATRIX_API_KEY": "your_api_key"
      }
    }
  }
}
```

## 3. 可用能力

常见工具 / 数据能力包括：

- `get_health_overview`
- `get_training_data`
- `get_sleep_analysis`
- `get_readiness_score`
- `get_weekly_trends`
- `get_risk_assessment`
- `get_ai_recommendation`
- `get_nutrition_data`

具体以当前后端暴露的 MCP 工具为准。

## 4. REST API 示例

基础 URL：`https://your-domain.example.com/api/v1/mcp`

```bash
curl -s "https://your-domain.example.com/api/v1/mcp/health-overview"   -H "Authorization: Bearer YOUR_API_KEY"

curl -s "https://your-domain.example.com/api/v1/mcp/training-summary?days=14"   -H "Authorization: Bearer YOUR_API_KEY"
```

## 5. 认证

二选一，取决于你的接入方式：

- MCP 请求头：`X-API-Key: YOUR_API_KEY`
- REST 请求头：`Authorization: Bearer YOUR_API_KEY`

对应服务端配置项：`MCP_API_KEY`

## 6. 排查建议

### MCP 无法连接

- 检查反向代理是否放通 `/mcp` 和 `/mcp/sse`
- 检查 `MCP_API_KEY` 是否配置正确
- 检查客户端请求头是否带上 API Key

### REST 返回空数据

- 检查 Polar / Oura 授权状态
- 检查最近同步任务是否成功
- 确认请求的时间范围内确实存在数据
