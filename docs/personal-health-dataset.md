# 个人健康数据集与本地云服务

定位：服务器持续沉淀个人健康事实、来源和研究特征，让现有应用及外部 agent 使用同一份数据。本文对应 `health-research-v1`，文档更新于 2026-10-16。

## 1. 本轮后端范围

- 20 个查询数据集，覆盖 Oura、Polar、餐食、补充设备记录和个人健康日志。
- 确定性每日研究数据，提供指标单位、来源记录 ID、质量说明、缺失值和过时标记。计算不调用 AI。
- Oura 增加 session 采集，设备能力每 24 小时重新探测，保留同步状态。
- Polar 修正身体资料、活动、睡眠和夜间恢复的官方接口；采集运动 samples，以及活动、身体资料、日间心率、训练负荷、SleepWise、支持设备的温度/皮肤接触/ECG/血氧测试。可用性以实际返回为准。
- 测量、体检、用药、补剂、症状、生活事件、饮食记录完整确认的结构化入口。
- 密钥保护的只读 REST 与 Streamable HTTP MCP；应用前端继续使用已有登录 JWT。

本轮不实现导出、迁移、备份或 OAuth 授权服务。Apple Health、Garmin 等额外渠道可通过标准化日志入口提交测量/事件，目前没有自动同步这些渠道的适配器。

## 2. 数据如何沉淀

原有设备及餐食表继续保存原始记录。新增四张表：

| 表 | 含义 |
|---|---|
| `health_source_records` | 补充设备渠道的原始 JSON 与规范化数据；来源、类型、原始 ID、日期、采集/更新时间 |
| `health_journal_entries` | 带时区的测量和生活事件；追加保存，修正使用 `supersedes_id`，保留旧记录 |
| `health_daily_features` | 每用户每日期的研究指标、证据、质量、schema 版本、内容指纹、当前修订号 |
| `health_dirty_days` | 待重新整理的日期队列 |

源表的新增、修改、删除会在同一数据库事务中标记旧/新日期。食物明细的变化也会标记其餐次日期；跨日事件标记整个受影响区间。源事务回滚时，队列也回滚。

后端每分钟处理最多 31 个待整理日期。处理时锁住队列行，多个进程不会重复消费同一日期；处理期间的新数据仍会重新排队。正常情况下新上传的研究数据约一分钟内更新，但这不是实时延迟承诺。任务失败时队列保留，下一轮重试。启动和跨日时整理昨天、今天，避免昨天永久显示为未完成日。

初始化历史数据使用 `scripts/build_research_dataset.py`。每日研究表是可重算的当前视图，不是原始数据备份，也不保存每次重算的完整历史快照。原有餐食重新识别/旧 AI 建议的历史版本不在本轮补建范围内。

## 3. 日期、单位与质量口径

- 时区固定 `Asia/Hong_Kong`（UTC+8）。时间输入必须带时区，不能依赖服务器默认时区。
- Oura 睡眠/准备度使用设备提供的日期，作为起床日；活动、训练、饮食按发生日。分析前一日行为对翌日恢复时，使用 `lag=1`。
- 主睡眠优先 `long_sleep`，同类取最长记录；其 HRV、心率、睡眠阶段单独保留。其他有效睡眠段作为午睡合计；`rest` 不计入睡眠。
- Oura 日评分与睡眠段指标分别保留。`readiness.resting_heart_rate` 是贡献评分，单位 `score`；`sleep.lowest_heart_rate` 才是 bpm。
- 库内睡眠、压力等部分字段为秒，研究指标转换为分钟；Oura 活动时长在原有表已经是分钟，不能再次除以 60。原始记录查询仍使用原字段单位，见字段说明。
- 未记录保留 `null`。零是真实零；没训练记录不代表休息，没餐食记录不代表没吃。
- 营养为已记录餐食的 AI 估算，不代表全天摄入。只有当天的 `nutrition_coverage` 日志明确 `complete=true` 才标为确认完整；这不改变营养估算的不确定性。
- 钠/糖合计只统计有值食物项，质量字段注明有值食物项数量；不能把其余食物项的缺失当成零。
- 午睡、运动会保留来源记录 ID。跨设备运动仅在时段重叠至少 80%、开始相差不超过 10 分钟且双方候选唯一时关联。疑义保留原记录并标记；Zone 和区间加权负荷仅基于 Polar。
- 研究层的 `training.zone_weighted_load` 是固定区间权重分钟数，独立于设备 cardio load，不混称为同一算法的 TRIMP。
- 稀疏心率采样只给样本统计，不据此推断连续佩戴覆盖。大序列按需读取。
- 实际媒体缺失、睡眠算法版本、分析未完成、运动时长不完整等会进入 `quality`。
- `stale=true` 表示源数据已变化但研究视图尚未更新；`materialized=false` 表示尚未整理。趋势和 pattern 不使用 stale 日。
- 当前 `profile` 是当前配置；设备身体资料快照与历史测量分开，不将今天的体重回填到过去。
- 本轮之后的资料修改会保存 `profile_snapshot`；此前被覆盖的资料无法由此恢复。补充设备资料缺少原始日期时标记 `_date_basis=collection_day_only`，不能当作当天测量事实。

## 4. 接口契约

基础地址用自己的后端 HTTPS 地址替换，例如 `https://health.example.com`。前缀 `/api/v1/research`。

### 读取

读取支持 `Authorization: Bearer <MCP_API_KEY>` 或 `X-API-Key: <MCP_API_KEY>`；已有应用也可以使用 `Authorization: Bearer <登录JWT>`。所有读取绑定固定主用户，不接受调用者指定其他用户 ID。密钥不能用于写入日志。

| 方法与路径 | 用途 |
|---|---|
| `GET /catalog` | 数据目录、各类记录数量/日期覆盖、字段说明、指标字典、设备能力与研究队列状态 |
| `GET /profile` | 当前用户目标和身体资料、设备资料 |
| `GET /records/{dataset}?start=YYYY-MM-DD&end=YYYY-MM-DD` | 原始域表的结构化明细；餐食包含食物明细 |
| `GET /days?start=...&end=...&metrics=activity.steps,sleep.average_hrv` | 每日研究特征；省略 metrics 时返回全部指标 |
| `GET /context?target_date=YYYY-MM-DD` | 最近 8 个日期及 7/30/90 天统计、个人资料与质量说明 |
| `GET /patterns?start=...&end=...&x=activity.steps&y=sleep.average_hrv&lag=1` | 单个假设的探索性相关与有效日对 |
| `GET /openapi.json` | 公开的只读接口描述，供 GPT Actions 导入；不包含健康数据和写接口 |

日期范围首尾均包含，每次最多 366 天；可分窗查询更长历史。`records` 支持 `limit=1..1000`、`offset=0..1000000`，按时间与 ID 排序，返回 `next_offset`；没有下一页时为 null。边查询边写入可能影响 offset 翻页，完整研究时选已结束日期并避免同时重整同一段记录。

默认排除大样本字段与完整 AI 分析，避免一次返回大量序列。`include_raw=true` 获取原始 JSON/AI 分析，`include_samples=true` 获取样本与编码序列；任一为 true 时每页最多 25 条。大列表在未请求 samples 时返回省略标记，不能将省略理解为没有数据。

数据集名称：`sleep`、`sleep_scores`、`readiness`、`activity`、`stress`、`spo2`、`cardiovascular_age`、`resilience`、`vo2_max`、`sleep_time`、`oura_workouts`、`tags`、`rest_mode`、`heart_rate`、`polar_exercises`、`polar_sleep`、`polar_recharge`、`meals`、`journal`、`provider_records`。补充设备记录使用 `source` 和 `kind` 区分渠道，完整字段通过 catalog 查看。

`context` 的恢复窗口截至目标日，行为窗口截至前一天；不是将所有数据都错移一天。统计均值只按有效记录日计算，并给出 `observed_days/expected_days`，低覆盖均值不得当成完整基线。实际当天行为可查看 recent_days 或 records。

### Pattern 探索

`lag=0..14`，表示 x(D) 对 y(D+lag)。默认至少 20 个有效日对，可设置 `min_pairs=20..100`。排除过时日、当天未完成日；营养指标进一步要求确认全天记录完整。日期按日历对齐，不以行号错位配对。

返回状态：`insufficient_pairs`、`constant_series` 或 `exploratory`，无可计算结果时 `pearson_r=null`。保留每个参与比较的日期和值。分钟钟点是循环变量，接口拒绝直接对其做 Pearson；可读取原记录后使用循环统计方法。

这是研究工具，不自动给数据贴“健康/不健康”的医学标签。个体时间序列存在自相关、混杂和多重比较问题；结果只是探索线索，不提供因果或显著性结论。

### 写入健康日志

`POST /journal` 必须使用现有主用户登录 JWT，研究密钥无写权限。

```json
{
  "source": "manual",
  "external_id": "scale-2026-10-11-morning",
  "kind": "measurement",
  "occurred_at": "2026-10-11T08:00:00+08:00",
  "measurements": [
    {"code": "weight", "value": 70.2, "unit": "kg", "method": "measured"}
  ],
  "notes": "起床后测量"
}
```

- `kind`：`measurement`、`lab`、`medication`、`supplement`、`symptom`、`lifestyle`、`nutrition_coverage`。
- 测量包含 `code/value/unit/method`。method 为 `measured/self_reported/estimated/lab`。已知 code 必须使用 catalog 中定义的单位；不隐式换算 mg/dL 和 mmol/L。其他体检 code 可用下划线名称和明确单位保存，在 journal 明细查询中可研究。
- 事件填写 `label`，可选 `tags/notes/severity`（0..10）；用药可填 `dose/dose_unit`。这些是记录，不是自动推荐用药。
- 区间事件可填 `ended_at`，最多 366 天。没有结束时间时按发生日事件处理，不擅自假定持续用药。事件、测量开始时间不允许在未来。
- 饮食确认例：`kind="nutrition_coverage"`、`complete=true`，occurred_at 使用要确认的日期。true 仅表示本人确认当天所有摄入已记录。之后补录/删除餐食时应由前端提醒重新确认。
- 后端将饮食确认绑定当时的餐次/食物事实指纹；之后新增、删除、重新识别或修改营养后，旧确认自动失效，`quality.nutrition.confirmation_outdated=true`。单纯餐后建议状态变化不会使确认失效。
- 相同 `source+external_id` 重试且内容相同返回同一 ID、`reused=true`；内容不同返回 409。前端一次用户操作生成一次 external_id，重试复用。
- 修正使用新的 external_id，并填写原记录的 `supersedes_id`。旧记录保留；普通 journal 查询只返回有效最新记录。应修正当前版本，已被修正的旧版本再次提交返回 409。跨日修正会重算原日与新日。
- 查看 journal 修正历史时使用 `include_superseded=true`，来源仍限定为当前主用户。
- 返回 201：`id/day/reused/research_status`。新记录状态为 queued，不要求前端等待研究重算才报告保存成功。

## 5. 服务器初始化与维护

在 backend 目录执行，使用已有环境配置：

```bash
venv/bin/alembic upgrade head
venv/bin/python scripts/build_research_dataset.py --sync-devices
```

第二步先补采当前上游能提供的数据，再整理已有完整历史。设备接口具有历史窗口和硬件/授权限制，不能承诺找回从未采集且已经不再开放的历史采样。没有权限或记录的渠道保留状态，不造数，不清空已有数据。Oura session 会尝试补读已有历史；Polar 最近 28 天运动会重读以补充 samples。

只重整本地数据可去掉 `--sync-devices`；指定窗口：

```bash
venv/bin/python scripts/build_research_dataset.py --start 2026-09-01 --end 2026-09-30
```

配置沿用 `backend/.env` 的 `MCP_API_KEY`、`PRIMARY_USER_ID`（兼容 DEFAULT_USER_ID）。未配置密钥时外部 MCP 拒绝访问，不开放匿名健康数据。密钥只放在密码管理器或客户端私有认证设置中，不放在 URL、前端源码、截图或 prompt。轮换密钥后重启后端，旧密钥失效。

已有部署的服务密钥可从服务器 `backend/.env` 安全取得 `MCP_API_KEY` 的值，再填入客户端认证设置；本文和前端 prompt 不包含真实密钥。

使用 catalog 查看 dirty_days、已整理范围、设备最后同步与能力。检查失败的设备渠道时查询 provider_records 中 `kind=sync_status` 的记录；对暂无数据的渠道区分“未佩戴/无记录”和“上游不可用/授权失败”，不能仅凭空表下结论。

### 部署后验证

- 确认迁移版本为 `4e5f60718293`，执行初始化后使用 catalog 检查覆盖范围与 dirty_days。
- 检查设备授权、最后同步和各接口能力；单个扩展接口不可用不等于整个设备断开。
- 检查 `/health`、`/ready`、catalog、context、records、patterns 和 MCP 研究工具。
- 使用登录 JWT 验证日志录入；研究密钥只读，缺少凭证时健康接口应拒绝访问。
- `.env` 只在服务器保存；维护脚本加载该环境文件以正确读取加密设备令牌。

## 6. Mac / 手机接入步骤

### Oura 重新授权

当前网页没有 Oura 设置入口。可以在服务器使用已配置主用户和 Oura 应用配置生成授权链接，再由本人在浏览器打开，登录戒指对应的 Oura 账号并允许所需权限。授权成功会回到后端 `/api/v1/oura/callback`，显示“Oura 授权成功”。链接包含公开的 OAuth client_id、回调地址和档案关联 state，不应包含 client_secret、访问 token 或 MCP 密钥。

授权回调只保存连接信息，不立即全量补采；完成后由后端检查连接并执行同步。Mac 前端待实现的连接卡片应使用登录 JWT 调用 `GET /api/v1/oura/auth-url`、`GET /api/v1/oura/status` 和 `POST /api/v1/oura/sync`，不能用研究密钥替代用户登录。

### 先验证 REST

在终端安全读入服务密钥：

```bash
export HEALTH_BASE_URL='https://health.example.com'
read -s HEALTH_DATA_KEY
export HEALTH_DATA_KEY
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${HEALTH_DATA_KEY}" \
  "${HEALTH_BASE_URL}/api/v1/research/catalog"
```

然后调用 context、records 或 days。401 表示凭证无效，503 可能为未配置密钥/主用户，422 表示参数或单位不合法，409 表示日志重试内容冲突/修正版本冲突。不会要求提供设备 OAuth token 给外部 agent。

### ChatGPT：使用 GPT Actions + API Key

1. 打开自己的自定义 GPT 配置，添加 Action。
2. 从 `https://你的后端/api/v1/research/openapi.json` 导入只读 schema。
3. Authentication 选择 API Key，Auth Type 选择 Bearer，填入服务的 MCP_API_KEY。
4. 先测试 catalog，再测试 context。若界面提示 schema/网络/套餐限制，按平台实际报错排查，不将服务改为匿名。
5. 保存为私有 GPT；在账号支持的 Mac、浏览器或手机中打开它使用。

这条路径不需要新增 OAuth 服务。ChatGPT 的自定义 MCP 插件接入与 GPT Actions 是不同入口；本轮选择 API Key 的 Actions 路径。[OpenAI Actions 认证文档](https://developers.openai.com/api/docs/actions/authentication)

### Claude：远程 MCP + 固定请求头

在支持自定义 connector 的账号中，添加远程 MCP 地址 `https://你的后端/mcp`。在 Request headers 中配置 `Authorization: Bearer <服务密钥>` 或 `X-API-Key: <服务密钥>`。若当前客户端没有该设置，先在其支持的网页/桌面配置入口完成；手机是否复用连接以账号和客户端实际能力为准。[Claude 官方接入文档](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)

Claude Code 可使用 HTTP MCP 的 header 配置；避免将真实密钥提交到项目配置仓库。

### Grok：自定义 connector 或 xAI API

Grok 官方支持自定义 MCP connector。在当前界面支持设置固定请求头时，配置同一个 `/mcp` 地址和密钥。若界面只接受 OAuth，本轮服务不提供 OAuth；使用支持认证 header 的 MCP 客户端，或 xAI API 的 remote MCP（`authorization`/`headers`）入口，不将密钥拼在 URL。

[Grok connectors](https://docs.x.ai/grok/connectors)、[xAI remote MCP 文档](https://docs.x.ai/developers/tools/remote-mcp)。平台连接需要在用户自己的账号中完成，服务器验证不等于已完成各平台账号联调。

### 通用 MCP 客户端

选择 Streamable HTTP，地址 `/mcp`，配置 Bearer 或 X-API-Key。新研究工具均为只读：

`get_research_catalog`、`get_research_profile`、`get_research_context`、`get_research_days`、`query_health_records`、`explore_health_pattern`。

深度研究优先使用这些统一工具。历史的 get_health_overview 等工具保留兼容，其旧口径不应混入新研究表做跨日统计。

### 可复制给研究 agent 的指令

```text
请通过已配置的个人健康数据服务研究我的数据。
先读取 catalog 和 profile，确认数据类别、单位、时间范围、源数据新鲜度和缺失情况。
再读取研究 context，必要时用 records 查询食物、运动、生活事件或样本证据。
所有日期按服务的 UTC+8 口径；睡眠/准备度为起床日，活动/饮食/运动为发生日。
不要把未记录当成零，不把已记录营养当成完整全天摄入，不把设备贡献评分当成真实 bpm。
排除过时和未完成日，比较时报告有效记录覆盖。先提出具体假设，再按日历对齐比较。
用 patterns 时报告日对数量和滞后方向；把相关性表述为探索线索，解释混杂和其他可能原因。
引用具体日期、数据集和来源记录 ID；分别陈述观察事实、推测和待验证问题。
如某维度缺失，告诉我需要补录什么；不要推测不存在的症状、用药或体检结果。
```

## 7. 前端配合

见 [Mac 前端契约与可复制 prompt](personal-health-dataset-frontend.md)，微信小程序优先执行 [小程序接入说明](personal-health-dataset-miniprogram.md) 中的第一批：连接状态、数据质量、结构化补录和饮食完整确认，研究图表后续实现。后端自动同步和数据整理不依赖这些页面发布。服务器后端与前端保持边界：本仓库当前工作区不改 web，不启动前端开发服务。

设备接口依据：[Polar AccessLink 官方文档](https://www.polar.com/accesslink-api/)、[Oura 官方 API 文档](https://cloud.ouraring.com/v2/docs)。接入步骤核对日期为 2026-10-12，平台界面可能变化。
