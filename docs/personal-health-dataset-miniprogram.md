# 小程序适配：个人健康数据集

更新日期：2026-10-16。实现位置为 Mac 上当前实际发布的小程序工程。后端接口已提供，服务器不修改小程序源码。

数据契约见 [个人健康数据集](personal-health-dataset.md)，通用规则见 [前端适配](personal-health-dataset-frontend.md)。本说明补充小程序的实施顺序和授权交互。

## 第一批：连接、数据质量、补录

设备自动同步、餐食结构化、跨设备匹配、每日特征整理都在后端执行。现有上传流程继续使用原接口，无需让小程序重新上传 Oura/Polar 数据。设备是否已连接以各部署的接口返回为准。

| 位置 | 要做的交互 | 后端接口 |
| --- | --- | --- |
| 我的 → 数据来源 | Oura/Polar 连接状态、最后同步、Oura 重新连接和手动同步 | `GET /api/v1/research/catalog`；Oura 专用接口见下文 |
| 首页轻量状态卡 → 数据质量页 | 数据类别、记录量、覆盖日期、缺口、整理状态 | `GET /api/v1/research/catalog`、`GET /api/v1/research/days` |
| 首页/我的 → 健康记录 | 测量、用药/补剂、症状、生活事件及历史修正 | `POST /api/v1/research/journal`；`GET /api/v1/research/records/journal` |
| 饮食页 | 已记录摄入、全天完整确认、餐食变更后提醒重新确认 | `POST /api/v1/research/journal`，`kind=nutrition_coverage` |

数据质量页面先展示 catalog 的 `datasets[]` 中 `name/source/description/records/recorded_days/first_day/last_day`、`connections.oura/polar` 和 `materialization.dirty_days`。指标定义从 `metrics` 取得。面向用户显示友好的中文名称、来源和单位，不直接堆数据库字段或存储类型。

`connections.oura.active` 表示本地授权记录启用，不是刚刚通过上游检查；需要实时验证时使用 Oura `/status`。`capabilities` 中单个接口 `available=false` 不代表整个设备断开。恢复力、VO₂ Max、心血管年龄等扩展接口不可用时，显示“此数据暂不可获取”，不能据此要求用户反复授权。

## Oura 在小程序里的流程

所有调用携带现有登录 JWT：

1. 进入数据来源页读取 `GET /api/v1/oura/status`，响应为 `{connected, message}`。
2. 用户点击连接/重新连接时调用 `GET /api/v1/oura/auth-url`，响应为 `{auth_url, state}`。不要固定写死链接或 state。
3. 第一版提供“复制授权链接”，用户主动点击后用 `wx.setClipboardData` 复制返回的 `auth_url`，引导在手机浏览器中打开并完成授权。
4. 返回小程序时在页面 `onShow` 刷新状态，另提供“已完成授权，检查连接”按钮。必须等 `/status` 返回 `connected=true` 才展示成功，复制链接本身不代表授权完成。
5. 用户主动点击同步调用 `POST /api/v1/oura/sync?days=7&force=false`；如需补近一个月，`days` 最大为 30。禁用重复点击，完成后刷新 catalog 和当前日期的 days。

授权回调已在后端处理，不需要小程序提交授权码，也不需要小程序接收 OAuth token。普通 `onShow` 不自动触发手动同步；定时同步由服务器负责。同步响应的 `stats` 是各类处理数量，不应全部显示为“新增记录”。

第一版不依赖内嵌 Oura 授权网页。若后续增加 `web-view`，Mac 开发方需另行核对账号能力、业务域名以及整个 OAuth 跳转链在真机上的可用性；不能仅以开发工具中能打开为上线验收依据。平台入口供核对：[web-view](https://developers.weixin.qq.com/miniprogram/dev/component/web-view.html)、[剪贴板 API](https://developers.weixin.qq.com/miniprogram/dev/api/device/clipboard/wx.setClipboardData.html)。本次无法读取上述官方页面，未确认当前小程序账号是否具备相应内嵌网页能力。

## 结构化补录

第一版先做体重、血压、饮水、咖啡因、疲劳、症状和用药/补剂。旅行、熬夜、饮酒等事件使用 `kind=lifestyle`，填写 label、tags 和备注。体检表单可以后续补充，不要求第一版开放全部自由输入字段。

统一调用 `POST /api/v1/research/journal`。例如体重记录：

```json
{
  "source": "manual",
  "external_id": "一次保存操作生成的唯一ID",
  "kind": "measurement",
  "occurred_at": "2026-10-12T08:00:00+08:00",
  "measurements": [
    {"code": "weight", "value": 70, "unit": "kg", "method": "measured"}
  ]
}
```

以上为虚构示例，实际时间必须由用户选择，不能提交未来事实。血压在同一条 measurement 的 measurements 内提交 `blood_pressure_systolic`、`blood_pressure_diastolic`，单位均为 `mmHg`。饮水使用 `water/mL`，咖啡因使用 `caffeine/mg`，疲劳使用 `fatigue/score_0_10`；method 可选 `measured/self_reported/estimated/lab`，根据实际来源设置。用药/补剂使用 `kind=medication/supplement`，填写 label，剂量填写时 dose 与 dose_unit 必须同时提供。表单应查阅后端完整定义，不自行发明同义 code。

成功返回 HTTP 201：

```json
{
  "id": "后端日志UUID",
  "day": "2026-10-12",
  "reused": false,
  "research_status": "queued"
}
```

显示“已保存，数据整理中”。保存成功与研究整理完成是两个状态。网络超时重试保持相同 external_id 和完全相同内容；用户改变内容是新操作，使用新 ID。修正日志时提交新 external_id 和旧记录的 supersedes_id；遇到 409 刷新最新版本再编辑。当前无日志删除接口，不添加假删除功能。

读取日志通过 `GET /api/v1/research/records/journal?start=YYYY-MM-DD&end=YYYY-MM-DD&limit=50&offset=0`，响应记录位于 `records[]`，业务内容位于记录 `data` 中；按 `next_offset` 继续加载。默认只显示未被替代的记录；版本历史可使用 `include_superseded=true`。

## 饮食完整确认和整理状态

饮食页增加用户主动确认“这一天的餐食、零食、饮料均已记录”。发送 journal 的 `kind=nutrition_coverage`、`complete=true`，occurred_at 必须落在被确认的 UTC+8 日期内且不晚于当前时间。不要用“有三餐”自动认定全天完整，也不要将当日尚未结束的记录描述为已观测完整一天。

后端将确认绑定到当天具体餐食内容；后续新增、删除或修改餐食会自动使旧确认失效。前端餐食变更成功后立即撤去已确认提示并刷新数据，等待用户重新确认；无需为使确认失效强行再调用一次 journal。用户主动撤销确认时可以提交 complete=false 的新记录。

`GET /api/v1/research/days?start=YYYY-MM-DD&end=YYYY-MM-DD` 的 `days[]`：

- `materialized=false`：尚未整理。
- `stale=true`：整理中，旧结果暂不用于正式比较。
- `quality.partial_day=true`：今天尚未完成。
- `quality.nutrition.confirmation_outdated=true`：餐食变化，需重新确认。
- `quality.nutrition.complete_day_confirmed=true`：该日的记录完整确认有效。
- `quality.missing_datasets` 和 `quality.warnings`：缺失类别和质量提醒。

每次上传/补录成功后可以局部刷新 days。整理中只在相关页面可见时有限轮询，例如每 5 秒一次、最多 1 分钟；离开页面停止，超时保留“整理中”并提供手动刷新，不重新提交事实，也不重复触发设备同步。catalog 较重，进入数据质量页、同步后或主动刷新时请求，避免全局频繁轮询。

所有营养汇总标注“已记录摄入 / AI 估算”。null 显示暂无记录，0 保留为 0；缺少运动记录不等于休息日。这里的 `quality.partial_day` 与旧营养接口 `flags.partial_day` 不是同一口径，应在各自页面按各自契约使用。

## 第二批：档案与研究

每日档案使用 days 的 `metrics/quality/evidence`，明细使用 `/records/{dataset}`；先做近期日期窗口和来源查看。来源原始字段的单位可能与研究指标不同，汇总以 catalog 中的研究指标单位为准，不能直接套用原始记录的单位。

研究页使用 `GET /api/v1/research/patterns?start=...&end=...&x=...&y=...&lag=1`。x/y 从 catalog.metrics 选取，例如 `activity.steps` 与 `sleep.average_hrv`。lag 表示比较 D 日 x 与 D+lag 日 y，范围 0–14；显示有效 pairs、expected_pairs、相关系数和接口状态。最低有效样本为 20 对；不足时显示“数据不足”。不把相关性描述为因果、诊断或健康/不健康结论。第一批不必实现复杂图表或新增 AI 分析按钮。

## Mac 前端可复制 Prompt

```text
请在 Mac 上当前实际发布的 Health 微信小程序工程中实现个人健康数据集适配。
先读工程 AGENTS.md，定位登录、API client、页面路由、饮食上传和当前组件风格。
以后端 personal-health-dataset.md、personal-health-dataset-miniprogram.md 为契约。
沿用现有 API 域名和微信 AppID，小范围集成；后端数据治理和算法已经完成。

本批实现：
1. 我的→数据来源：用登录 JWT 读取 /api/v1/research/catalog，展示 Oura/Polar
   的状态与最后同步；Oura 实时检查 /api/v1/oura/status。
   连接按钮读取 /api/v1/oura/auth-url，复制 auth_url 并提示在手机浏览器完成授权。
   页面 onShow 和“已授权，检查连接”按钮刷新状态；connected=true 才表示成功。
   手动同步 POST /api/v1/oura/sync?days=7&force=false，防重复点击，不在每次 onShow 自动同步。
2. 数据质量页：展示 datasets[] 覆盖和记录量、materialization.dirty_days、
   connections 的最后同步和单接口能力。设备整体连接与单个维度不可用分别展示。
3. 健康记录：先支持体重、血压、饮水、咖啡因、疲劳、症状、用药/补剂和生活事件。
   保存 POST /api/v1/research/journal，带时区 occurred_at；external_id 在保存前生成，
   同内容重试复用。201 queued 显示已保存、整理中，禁止重传已保存事实。
   修正用新 external_id + 当前 supersedes_id，409 刷新版本。
4. 饮食页增加用户主动的全天完整确认，kind=nutrition_coverage、complete=true。
   补录/修改/删除餐食后撤去已确认提示，刷新 days；后端会自动使旧确认失效。
5. 使用 /api/v1/research/days 展示尚未整理、整理中、当天未结束、确认已失效等状态。
   只在相关页面可见时有限轮询，页面退出清理定时器，禁止无限后台拉取。

约束：使用现有 POST /api/v1/auth/miniprogram-login 和 Bearer JWT。
小程序不保存 MCP_API_KEY、Oura token/client_secret，不调用 MCP，不重复上传设备数据。
不把 0 当缺失，不把无记录当健康结论，不将 AI 估算当实测。
不要从服务器恢复旧小程序目录，不改后端，不额外创建 AI 推理流程。
优先完成上述第一批；复杂研究图表先保留为后续任务。

在 Mac 微信开发工具和真机验证登录、授权返回、同步防重复、保存超时重试、版本修正、
全天确认失效、UTC+8日期边界、null与0、分页以及页面退出后无重复请求。
运行工程已有 lint/typecheck/build 等检查，输出修改文件与验收结果。
```
