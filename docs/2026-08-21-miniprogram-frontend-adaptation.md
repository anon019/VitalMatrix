# 小程序前端适配清单与 Mac 执行 Prompt

日期：2026-08-21

服务器仓库不包含当前权威小程序源码。本轮没有恢复或修改服务器上的历史小程序目录；请只在 Mac 上实际发布的小程序项目中执行本文。

## 1. 必须适配的后端契约

### 鉴权

- 小程序使用 `POST /api/v1/auth/miniprogram-login`，不要调用 Web 专用的 `/auth/simple-login`。旧 `/wechat-login` 暂时保留为同逻辑兼容别名，不再创建用户。
- 所有业务接口继续传 `Authorization: Bearer <token>`。
- Web 简易登录现在要求服务端配置访问密码；未配置时返回 503，不再允许无密码换取单用户 JWT。

### 私有餐食图片

`photo_path`、`thumbnail_path` 和 `poster_url` 现在返回短期签名相对 URL：

```text
/api/v1/nutrition/media?path=...&expires=...&signature=...
```

- 旧 `/uploads/nutrition/...` 公开路径已关闭并返回 404。
- 用统一的 `resolveApiUrl()` 补全 API 域名，必须保留完整 query string。
- 签名默认一小时过期。图片 403 时重新请求餐食列表/详情或海报接口获取新 URL，不要无限重试旧 URL。
- 不要把签名 URL 长期写入本地缓存；可缓存餐食 ID 和内容摘要。
- 微信公众平台需把当前 API 域名加入 `downloadFile` 合法域名。

### 餐食与模型版本

餐食响应新增：

```json
{
  "ai_model": "legacy-model-name",
  "current_ai_model": "gpt-5.6-luna",
  "ai_analysis": {},
  "analysis_is_legacy": true,
  "meal_time": "2026-08-21T07:34:32.715141+08:00"
}
```

- `ai_model` 是该条历史记录实际使用的模型，不应伪装成新模型。
- `analysis_is_legacy=true` 时显示“历史分析”，可提供用户主动点击的“升级分析”按钮，调用 `POST /api/v1/nutrition/meals/{meal_id}/reanalyze`。
- 页面顶部的“当前模型”读取 `current_ai_model` 或 AI 今日建议的 `model`，禁止写死模型名。
- 新识图与新建议均使用 Codex CLI `gpt-5.6-luna`；识图使用 Medium，纯文本建议使用 Low 以降低等待时间。
- 原 `gemini_analysis` 字段已更名为 `ai_analysis`；Mac 端类型、缓存映射和详情读取必须同步替换，不再读取旧字段。

### 营养汇总和趋势

- `GET /api/v1/nutrition/daily/{date}` 没有真实餐食时返回 `null`，不要渲染成 0 摄入。
- `flags.partial_day=true` 表示当天记录不足三餐；此时不能把合计解读为全天热量/蛋白质不足。
- `GET /api/v1/nutrition/weekly` 新增 `recorded_days`、`expected_days=7`；均值只按有记录的日期计算。
- `GET /api/v1/trends/overview` 新增 `nutrition.calories/protein_g/carbs_g/fat_g/meals_count` 五个数组。
- `activity.sedentary_min` 及 Oura 活动时长统一为“分钟”，前端不再除以 3600；显示小时只除以 60。

### 今日聚合与 AI 建议

`GET /api/v1/dashboard/today` 新增 `nutrition_today`、`nutrition_yesterday`。`oura_today`/`oura_yesterday` 内新增 `sleep_date`、`readiness_date`、`activity_date`、`stress_date`，页面应显示指标自己的来源日期。

AI 建议新增 `requested_date`、`source_date`、`is_stale` 和 `generation_metadata`。其中 `generation_metadata.prompt_version` 当前为 `recommendation-v3.0`，新增 `context_version=health-context-v1` 和 `context_lookback_days=90`；`data_completeness` 包含已载入历史的饮食记录天数、最近餐数、逐次训练数、Oura 上下文天数，以及睡眠/准备度/活动/训练是否可用。

- 指定历史日期接口不再回退到其他日期，缺失时为 `null`。
- 今日接口允许回退最近建议，但必须用 `is_stale` 和 `source_date` 显示“最近建议”，不能冒充今日生成。
- 内容顶层结构保持 `summary`、`yesterday_review`、`today_recommendation`、`health_education` 不变；展示优先级改为饮食、睡眠恢复、活动训练、健康知识。

### 按需海报 V9

```http
POST /api/v1/nutrition/meals/{meal_id}/poster
POST /api/v1/nutrition/meals/{meal_id}/poster?force=true
```

响应新增或确认：`poster_url`、`generated`、`model=gpt-image-2`、`layout_version=nutrition-poster-v9`、`verified_metrics`、`content_digest`。

- 只有用户点击“生成精美海报”才调用；上传、详情加载和普通分享入口都不得自动触发。
- `generated=false` 是服务端内容缓存命中，不是失败。
- 首次实际生成约 30–60 秒，客户端超时建议 120 秒；显示可取消等待提示，但不要重复发请求。
- 每位用户每天最多 5 次实际图片生成；缓存读取不计生成次数。
- `force=true` 只用于用户二次确认后的“重新生成”，会消耗额度。
- V9 为 3:4、默认 1K 的渐进式 JPEG 海报。GPT Image 2 只生成无文字视觉底图；本餐四项营养、完整一句话结论、未来三餐餐名/时间/菜名均由后端确定性绘制。未来三餐图片区已放大，底部不再显示重复的 `VERIFIED NUTRITION` 模块，核心数字以 `verified_metrics` 为准。

## 2. 页面和交互改造

- 今日页首屏顺序：今日饮食记录入口与已记录餐数 → AI 三个行动摘要 → 昨夜睡眠/恢复 → 活动/训练。
- 饮食列表首屏固定拍照入口和 `recorded_days / 7`；一餐记录只能写“已记录摄入”。
- 详情首屏显示热量范围、四项营养、结论和置信度；洞察与未来餐单分区折叠。一次性识图不展示或收集“几人分食”“吃了几根”等确认问题。
- 上传接口先返回识图与本餐核心营养结果；`recommendation_status=pending|processing` 时显示“饮食建议生成中”，用 `GET /api/v1/nutrition/meals/{meal_id}/analysis-status` 查询状态，完成后刷新餐食详情。不要为了等建议保持上传请求，也不要重复上传图片。
- 状态接口必须绕过请求缓存；完成后清除该餐次详情缓存并强制刷新。页面卸载时停止轮询，不能在旧页面继续 `setData`。
- `next_meal_recipes[].dishes[]` 必须保留并展示 `portion`、`calories`、`protein`、`ingredients` 和 `cooking_steps`。食材分行或使用标签，做法按编号逐条展示，不能用“、”或“→”拼成两条长文本。
- 餐食列表图片增加 `binderror`；详情图片失败后切换到“历史图片不可用”占位状态。签名 URL 最多刷新一次，404 不无限重试。
- 餐食照片是长期健康档案，前端不得提供或调用任何按时间批量清理图片的入口。完整保留策略见 `docs/2026-08-21-nutrition-pipeline-and-media-retention.md`。
- 新字段优先读取 `analysis_quality`、`calorie_range_low/high`、`uncertainty_notes`、`next_meal_recipes`；旧记录缺失字段时安全降级。
- `nutrition-v3.0` 的 `next_meal_recipes` 必须展示从当前餐后开始、按时间顺序覆盖未来 24 小时的三顿正餐；每项读取 `meal_name`、`timing`、`total_calories`、`dishes` 和 `why_this_menu`。标注“结合近期已记录餐食与长期饮食历史”，菜名不能在前端硬编码。
- 海报外层使用有明确高度的 `scroll-view scroll-y`；图片 `mode="widthFix"`，禁止固定图片高度和 `aspectFill`。
- 底部操作栏固定并处理 `env(safe-area-inset-bottom)`，滚动内容预留等高 padding。
- 保存流程：`wx.downloadFile` → `wx.getImageInfo` → 相册授权 → `wx.saveImageToPhotosAlbum`；403 时刷新签名 URL。

## 3. Mac 执行 Prompt A：完整实现

```text
你正在维护当前 Mac 上真正发布的微信小程序 Health 项目。请先阅读 AGENTS.md、package.json/project.config.json，定位鉴权、API client、今日页、趋势页、饮食列表、饮食详情、AI 建议和分享海报的真实文件；不要从服务器恢复历史 miniprogram 目录，也不要改域名和现有微信 AppID。

目标：按服务器 2026-08-21 最终契约完成一次可发布适配，信息优先级为饮食 > 睡眠/恢复 > 活动/训练。

必须实现：
1. 小程序登录只用 POST /api/v1/auth/miniprogram-login；业务请求继续 Bearer JWT，不用 /auth/simple-login。旧 /wechat-login 仅为兼容别名。
2. photo_path、thumbnail_path、poster_url 已是 1 小时有效的签名相对 URL /api/v1/nutrition/media?...。新增唯一的 resolveApiUrl 工具，补全域名并完整保留 query；图片 403 时刷新餐食/海报 URL，不长期缓存签名 URL。确认 downloadFile 合法域名配置。
3. 餐食响应使用 ai_analysis，并新增 current_ai_model 和 analysis_is_legacy。历史记录显示“历史分析 {ai_model}”，用户明确点击后才 POST /nutrition/meals/{id}/reanalyze；当前模型和 AI 页模型全部读后端，删除旧模型硬编码。
4. daily nutrition 可返回 null；flags.partial_day=true 时只显示“已记录摄入”，不判断全天不足。weekly 使用 recorded_days/expected_days。trends 新增 nutrition 五个数组。activity.sedentary_min 已是分钟，移除旧的 /3600，显示小时只 /60。
5. dashboard/today 使用 nutrition_today、nutrition_yesterday，并为 Oura 指标显示 sleep_date/readiness_date/activity_date/stress_date。今日首屏顺序改成饮食入口、AI 三个行动、睡眠恢复、活动训练。
6. AI 响应显示 model、source_date、is_stale、generation_metadata.data_completeness。is_stale=true 必须标注“最近建议”；指定日期 null 不回退。保留 summary/yesterday_review/today_recommendation/health_education 内容能力，视觉顺序改为饮食、睡眠恢复、活动训练、健康知识。
7. 海报只在用户点击“生成精美海报”时 POST /nutrition/meals/{id}/poster；上传、打开详情和普通分享都不得自动调用。generated=false 是缓存命中。重新生成二次确认后才加 force=true。生成按钮防重复点击，超时 120 秒，显示首次生成可能需要等待和每日 5 次实际生成限制。
8. 海报响应包含 layout_version=nutrition-poster-v9 和 verified_metrics。预览必须使用有明确高度的 scroll-view scroll-y，image mode=widthFix，不固定海报高度；固定底部操作栏处理 safe area，内容区预留操作栏高度。保存使用 downloadFile/getImageInfo/saveImageToPhotosAlbum，处理授权拒绝、403 刷新 URL、超时和重试。未来三餐图片是 AI 推荐示意，不能当作用户已经吃过的餐食照片；不再等待或校验底部 VERIFIED NUTRITION 模块。
9. 营养新字段优先：analysis_quality、calorie_range_low/high、uncertainty_notes、next_meal_recipes；兼容旧记录缺失字段，删除 next_meals/next_meal_menu 的主路径依赖。nutrition-v3.0 必须把 next_meal_recipes 三项渲染为“未来 24 小时三餐”，显示 meal_name/timing/total_calories/dishes/why_this_menu，来自后端近期明细与最多 90 天压缩历史上下文，不要硬编码菜名。
10. 图片上传成功后先渲染核心识图结果。当 recommendation_status 为 pending/processing，独立展示“饮食建议生成中”并轮询 GET /nutrition/meals/{meal_id}/analysis-status；completed 后只刷新详情，failed 时保留核心结果并提供 POST /nutrition/meals/{meal_id}/recommendations 重试。不重新上传图片，不展示 analysis_quality.questions。
11. 轮询和详情刷新必须绕过旧缓存；next_meal_recipes 的每道菜展示 portion/calories/protein、2-5 项 ingredients 和 2-3 条 cooking_steps，食材换行、步骤编号。历史图片 binderror 后显示占位，过期签名 URL 最多刷新一次。
12. 做小而清晰的组件拆分，避免重复请求；页面卸载后不 setData；图片使用懒加载；保留现有设计语言但提升信息层级、空态、错误态、加载态和无障碍点击区域。

完成后运行项目现有 lint/typecheck/test/build。输出修改文件、接口调用时机、字段兼容策略、仍需微信后台配置的事项，不能只给方案而不改代码。
```

## 4. Mac 执行 Prompt B：代码审查与补漏

```text
请对刚完成的 Health 小程序适配做一次只针对真实缺陷的 review 并直接修复。重点搜索：gemini_analysis/旧模型硬编码、/uploads/nutrition 直链、poster 自动调用、force=true 默认调用、next_meals/next_meal_menu、sedentary 除以 3600、固定高度海报图片、无高度 scroll-view、签名 URL 长期缓存、过期 URL 无限重试、页面卸载后 setData、重复提交和重复网络请求。

逐页检查今日、趋势、饮食列表、饮食详情、AI、海报预览。确认 null/空数组/旧记录/403/429/5xx/120 秒超时都有可理解状态，不白屏。修复后运行现有检查并给出发现清单和文件定位。
```

## 5. Mac 执行 Prompt C：开发者工具与真机验收

```text
请为当前 Health 微信小程序执行并记录验收，不做无关重构：
- iPhone 刘海屏、普通屏各测一次今日页、饮食详情、AI 页和海报预览。
- 未点击生成时网络中没有 /poster；第一次点击只有一个 POST；再次打开 generated=false 且快速返回；重新生成有二次确认。
- 海报从顶部到底部可滚动，本餐四项营养、完整一句话结论和未来三餐全部可见，操作栏不遮挡，保存到相册后尺寸完整无拉伸。
- 人为使用过期签名 URL 验证 403 后刷新 URL并恢复；拒绝相册权限后有引导而非死循环。
- 验证旧餐显示“历史分析”，新餐/今日 AI 显示 gpt-5.6-luna；is_stale 建议显示来源日期。
- 验证一餐记录只显示“已记录摄入”，周均值标注按记录日；久坐 697 分钟应约显示 11.6 小时，不得显示 0.2 或数百小时。
- 检查控制台无错误、请求无重复、页面返回后无 setData 警告。

输出通过/失败表、复现步骤、截图位置和仍需人工确认项；发现问题就先修复再重测。
```

## 6. 最终真机验收表

- [ ] 微信登录成功，token 过期可恢复；没有调用 simple-login。
- [ ] 旧公开图片 URL 不再使用；签名图片显示、过期可刷新。
- [ ] 今日页饮食优先，AI 建议显示真实模型与数据完整度。
- [ ] 旧餐不冒充当前模型，新餐与重新分析后为 `gpt-5.6-luna`。
- [ ] 一餐记录不会触发“全天营养不足”误报。
- [ ] 久坐单位正确，所有指标显示各自来源日期。
- [ ] 未点击不生成海报；缓存不重复计费；强制生成二次确认。
- [ ] 海报完整滚动和保存，安全区不遮挡，数字与 `verified_metrics` 一致。
- [ ] 旧营养 JSON 缺字段时不白屏，新字段正常展示。
- [ ] 上传返回核心结果后可立即查看；建议在后台完成，不阻塞上传，不重复上传。
- [ ] 界面不显示“需要我确认”或份量追问；多人餐照片仍返回单人正常摄入估算。
- [ ] 每道推荐菜都有食材用量和编号做法；长内容正确换行，不挤成单行。
- [ ] 历史图片缺失时显示明确占位，404/403 不无限重试。


## 2026-09-18 增量适配

当前模型仍是 Codex CLI `gpt-5.6-luna`（识图 Medium，文本 Low），没有切换到 Gemini。

- 每日回顾标题读取后端返回值，可为“近期趋势与昨日回顾”；完整展示趋势分析与较长的饮食建议，不写死旧标题或截断长度。
- `nutrition_recorded_days`、`oura_context_days` 不再固定表示近 7 天覆盖，不应直接除以 7 计算完整率。
- 上传/重识图 409 表示任务正在处理；上传 422 表示无效图片，504 表示识图超时。不要自动循环重传。
- 餐后建议已在 processing 时，接口返回真实状态且不重复排队；自动重试用尽后，用户主动重试才使用 `force=true`。
- 延续“核心识图先展示、后台三餐建议再刷新”的交互。状态以 `analysis-status` 顶层字段为准。

完整接口说明和测试记录见 [本轮优化文档](2026-09-18-ai-context-and-nutrition-performance.md)。
