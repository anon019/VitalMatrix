# Polar & Oura API数据完整性分析报告

**生成时间**: 2025-11-21（香港时间）
**分析范围**: Polar AccessLink API v3 + Oura Ring API v2

---

> 注意：本文件是阶段性能力分析材料，不是当前 `main` 分支的接口真相来源。
> 当前 API 以 `backend/app/api/v1/` 与根目录 `README.md` 为准。

## 📊 总体评估

| 平台 | 已实现端点 | 可用端点 | 完整度 | 重要缺失 |
|------|-----------|---------|--------|---------|
| **Oura** | 8 | 18+ | 44% | 心血管年龄、韧性、VO2 Max |
| **Polar** | 3 | 12+ | 25% | 睡眠、恢复、连续心率 |

---

## 🔵 Oura Ring API v2 数据完整性分析

### ✅ 已实现的端点（8个）

| 端点 | 用途 | 数据粒度 | 前端API |
|------|------|---------|---------|
| **Personal Info** | 用户基本信息 | 一次性 | ❌ |
| **Daily Sleep** | 睡眠评分 | 每日汇总 | ✅ `/api/v1/oura/sleep` |
| **Sleep** (详细) | 睡眠阶段详情 | 每段睡眠 | ✅ (合并到sleep) |
| **Daily Readiness** | 准备度评分 | 每日 | ✅ `/api/v1/oura/readiness` |
| **Daily Activity** | 活动统计 | 每日 | ✅ `/api/v1/oura/activity` |
| **Daily Stress** | 压力与恢复 | 每日 | ✅ `/api/v1/oura/stress` |
| **Daily SPO2** | 血氧饱和度 | 每日 | ✅ `/api/v1/oura/spo2` |
| **Heart Rate** | 连续心率 | 5分钟间隔 | ❌ |

### ❌ 缺失的重要端点（10个）

#### 🔴 高优先级（健康关键指标）

1. **Daily Cardiovascular Age** ⭐⭐⭐
   - **用途**: 心血管年龄评估（基于静息心率、HRV等）
   - **重要性**: 核心健康指标，反映心血管系统实际年龄
   - **AI价值**: 可用于长期健康趋势分析
   - **前端展示**: 适合在Today页面显示
   - **API路径**: `/v2/usercollection/daily_cardiovascular_age`

2. **Daily Resilience** ⭐⭐⭐
   - **用途**: 韧性/恢复力评分（身体对压力的应对能力）
   - **重要性**: 评估训练恢复能力和压力管理
   - **AI价值**: 结合训练负荷判断是否需要休息
   - **前端展示**: 今日恢复状态卡片
   - **API路径**: `/v2/usercollection/daily_resilience`

3. **VO2 Max** ⭐⭐⭐
   - **用途**: 最大摄氧量（心肺功能核心指标）
   - **重要性**: Zone2训练的终极目标指标
   - **AI价值**: 训练效果评估、进展追踪
   - **前端展示**: 趋势页面月度VO2 Max变化曲线
   - **API路径**: `/v2/usercollection/vo2_max`

#### 🟡 中优先级（完善功能）

4. **Sleep Time** ⭐⭐
   - **用途**: 推荐入睡时间（基于昼夜节律）
   - **重要性**: 优化睡眠质量
   - **API路径**: `/v2/usercollection/sleep_time`

5. **Workout** ⭐⭐
   - **用途**: Oura记录的训练活动
   - **重要性**: 可与Polar训练数据互补
   - **API路径**: `/v2/usercollection/workout`

6. **Enhanced Tag** ⭐
   - **用途**: 用户自定义标签（如"生病"、"饮酒"等）
   - **重要性**: 帮助AI理解异常数据
   - **API路径**: `/v2/usercollection/enhanced_tag`

#### 🟢 低优先级（锦上添花）

7. **Session** - 冥想/呼吸练习记录
8. **Rest Mode Period** - 休息模式时段
9. **Ring Configuration** - 戒指配置信息

### 📋 已存储但未充分利用的字段

当前Oura数据模型已存储但前端未完全展示：

**OuraSleep 模型**:
- `light_sleep_duration` - 浅睡时长 ⚠️
- `awake_time` - 清醒时长 ⚠️
- `average_heart_rate` - 睡眠平均心率 ⚠️
- `average_breath` - 平均呼吸频率 ⚠️
- `temperature_deviation` - 体温偏差 ⚠️

**OuraDailyReadiness 模型**:
- `temperature_deviation` - 体温偏差 ⚠️
- `activity_balance` - 活动平衡分数 ⚠️
- `sleep_balance` - 睡眠平衡分数 ⚠️
- `previous_night` - 前夜睡眠分数 ⚠️

**OuraDailyActivity 模型**:
- `high_activity_time` - 高强度活动时长 ⚠️
- `medium_activity_time` - 中强度活动时长 ⚠️
- `low_activity_time` - 低强度活动时长 ⚠️
- `sedentary_time` - 久坐时长 ⚠️
- `resting_time` - 休息时长 ⚠️
- `target_calories` - 目标卡路里 ⚠️
- `target_meters` - 目标距离 ⚠️

---

## ⚫ Polar AccessLink API v3 数据完整性分析

### ✅ 已实现的端点（3个）

| 端点 | 用途 | 数据粒度 | 前端API |
|------|------|---------|---------|
| **Exercises** | 训练记录 | 每次训练 | ✅ `/api/v1/training/*` |
| **Physical Info** | 身体信息 | 变更追踪 | ❌ |
| **Daily Activity** | 日常活动 | 每日 | ❌ |

### ❌ 缺失的重要端点（9个）

#### 🔴 高优先级（健康关键指标）

1. **Sleep** ⭐⭐⭐
   - **用途**: Polar设备记录的睡眠数据
   - **重要性**: 与Oura睡眠数据互补验证
   - **API路径**: `/v3/users/sleep`

2. **Nightly Recharge** ⭐⭐⭐
   - **用途**: 夜间恢复评分（心血管恢复 + 自主神经系统恢复）
   - **重要性**: 核心恢复指标，与Oura准备度互补
   - **API路径**: `/v3/users/nightly-recharge`

3. **Continuous Heart Rate** ⭐⭐⭐
   - **用途**: 连续心率监测（5分钟间隔）
   - **重要性**: 全天心率变化趋势
   - **数据粒度**: 5分钟/点
   - **API路径**: `/v3/users/continuous-heart-rate`

4. **Cardio Load** ⭐⭐⭐
   - **用途**: 训练冲量（TRIMP）历史数据
   - **重要性**: 长期训练负荷趋势
   - **API路径**: `/v3/users/cardio-load`

#### 🟡 中优先级（完善功能）

5. **SleepWise™** ⭐⭐
   - **用途**: 警觉性预测、昼夜节律入睡建议
   - **重要性**: 优化睡眠时间
   - **API路径**: `/v3/users/sleepwise`

6. **Body Temperature** ⭐
   - **用途**: 体温追踪
   - **重要性**: 疾病预警、女性健康追踪
   - **API路径**: `/v3/users/body-temperature`

#### 🟢 低优先级（锦上添花）

7. **Sleep Skin Temperature** - 睡眠皮肤温度
8. **SpO2 Results** - 血氧饱和度测试
9. **Wrist ECG Results** - 手腕心电图测试

### 📋 已获取但存储不完整的数据

**PolarExercise 模型缺失字段**:
- `ascent` - 累计爬升 ⚠️
- `descent` - 累计下降 ⚠️
- `sport_profile_id` - 运动配置ID ⚠️
- `training_load` - Polar官方训练负荷 ⚠️
- `running_index` - 跑步指数 ⚠️
- `training_benefit` - 训练收益类型 ⚠️

---

## 🎯 改进建议

### 立即实施（1周内）

#### Oura API增强

1. **添加心血管年龄端点**
   ```python
   # app/integrations/oura/client.py
   async def get_daily_cardiovascular_age(
       self, access_token: str, start_date: date, end_date: date
   ) -> List[Dict[str, Any]]:
       """获取心血管年龄数据"""
       params = {
           "start_date": start_date.isoformat(),
           "end_date": end_date.isoformat(),
       }
       response = await self._make_request(
           "GET", "/usercollection/daily_cardiovascular_age",
           access_token, params=params
       )
       return response.get("data", [])
   ```

2. **添加韧性端点**
   ```python
   async def get_daily_resilience(...) -> List[Dict[str, Any]]:
       """获取韧性/恢复力数据"""
       # 类似实现
   ```

3. **添加VO2 Max端点**
   ```python
   async def get_vo2_max(...) -> List[Dict[str, Any]]:
       """获取最大摄氧量数据"""
       # 类似实现
   ```

4. **创建数据库模型**
   ```python
   # app/models/oura.py
   class OuraCardiovascularAge(Base):
       """Oura心血管年龄"""
       __tablename__ = "oura_cardiovascular_age"

       id: Mapped[uuid.UUID] = mapped_column(...)
       user_id: Mapped[uuid.UUID] = mapped_column(...)
       day: Mapped[date] = mapped_column(...)
       vascular_age: Mapped[Optional[int]] = mapped_column(...)  # 血管年龄
       vo2_max: Mapped[Optional[float]] = mapped_column(...)  # VO2 Max
       raw_json: Mapped[Optional[dict]] = mapped_column(JSONB)

   class OuraResilience(Base):
       """Oura韧性数据"""
       __tablename__ = "oura_resilience"

       day: Mapped[date]
       resilience_score: Mapped[Optional[int]]  # 韧性评分
       sleep_recovery: Mapped[Optional[int]]  # 睡眠恢复贡献
       daytime_recovery: Mapped[Optional[int]]  # 日间恢复贡献
       stress_load: Mapped[Optional[int]]  # 压力负荷
   ```

5. **前端API暴露**
   ```python
   # app/api/v1/oura.py
   @router.get("/cardiovascular-age")
   async def get_cardiovascular_age(...):
       """获取心血管年龄数据"""

   @router.get("/resilience")
   async def get_resilience(...):
       """获取韧性数据"""

   @router.get("/vo2-max")
   async def get_vo2_max(...):
       """获取VO2 Max数据"""
   ```

#### Polar API增强

1. **添加Nightly Recharge端点**
   ```python
   # app/integrations/polar/client.py
   async def get_nightly_recharge(
       self, access_token: str, start_date: date, end_date: date
   ) -> List[Dict[str, Any]]:
       """获取夜间恢复数据"""
       # 实现Polar Nightly Recharge API调用
   ```

2. **添加连续心率端点**
   ```python
   async def get_continuous_heart_rate(
       self, access_token: str, date: date
   ) -> Dict[str, Any]:
       """获取连续心率数据（5分钟间隔）"""
       # 实现Polar CHR API调用
   ```

3. **创建数据库模型**
   ```python
   # app/models/polar.py (新建)
   class PolarNightlyRecharge(Base):
       """Polar夜间恢复"""
       __tablename__ = "polar_nightly_recharge"

       ans_charge: Mapped[Optional[int]]  # 自主神经系统恢复
       hrv_avg: Mapped[Optional[int]]  # 平均HRV
       breathing_rate: Mapped[Optional[float]]  # 呼吸频率

   class PolarContinuousHeartRate(Base):
       """Polar连续心率"""
       __tablename__ = "polar_continuous_heart_rate"

       timestamp: Mapped[datetime]  # 时间戳
       heart_rate: Mapped[int]  # 心率BPM
   ```

### 中期优化（1个月内）

1. **前端数据可视化增强**
   - 心血管年龄趋势图
   - VO2 Max进展曲线
   - 韧性/恢复力日历热图
   - 连续心率24小时曲线

2. **AI建议优化**
   - 整合心血管年龄到健康评估
   - 使用韧性数据优化训练强度建议
   - 基于VO2 Max进展调整训练计划

3. **数据完整性检查**
   - 定时任务检查空字段
   - 日志记录缺失原因
   - 用户提醒授权不足的scope

### 长期规划（3个月+）

1. **Polar睡眠数据集成** - 与Oura睡眠数据对比分析
2. **训练负荷历史** - 长期TRIMP趋势
3. **体温追踪** - 疾病预警、月经周期追踪
4. **标签系统** - 用户自定义标签（饮酒、生病、旅行等）

---

## 📊 前端API暴露情况汇总

### ✅ 已暴露的API端点

**Oura数据**:
- `GET /api/v1/oura/sleep?days=7` - 睡眠数据
- `GET /api/v1/oura/readiness?days=7` - 准备度数据
- `GET /api/v1/oura/activity?days=7` - 活动数据
- `GET /api/v1/oura/stress?days=7` - 压力数据
- `GET /api/v1/oura/spo2?days=7` - 血氧数据
- `GET /api/v1/oura/status` - 连接状态
- `POST /api/v1/oura/sync` - 手动同步

**Polar数据**:
- `GET /api/v1/training/weekly` - 训练总结
- `GET /api/v1/training/history` - 训练历史
- `GET /api/v1/polar/status` - 连接状态
- `POST /api/v1/polar/sync` - 手动同步

**AI建议**:
- `GET /api/v1/ai/recommendation/today` - 今日建议
- `GET /api/v1/ai/recommendation/{date}` - 指定日期建议

**Dashboard汇总**:
- `GET /api/v1/dashboard/today` - 今日仪表盘（聚合所有数据）

### ⚠️ 仍建议补充或继续增强的API能力

当前 Oura 相关能力（如心率详情、心血管年龄、韧性、VO2 Max）在现有版本中已经暴露。
仍建议后续补充或增强的主要是 Polar 恢复侧能力：

1. `GET /api/v1/polar/nightly-recharge?days=7` - 夜间恢复
2. `GET /api/v1/polar/cardio-load?days=30` - 训练负荷历史

---

## 🔍 数据字段完整性检查清单

### Oura Sleep字段检查

| 字段 | 已存储 | API暴露 | 前端展示 | 建议 |
|------|-------|---------|---------|------|
| sleep_score | ✅ | ✅ | ✅ | - |
| total_sleep_duration | ✅ | ✅ | ✅ | - |
| deep_sleep_duration | ✅ | ✅ | ✅ | - |
| rem_sleep_duration | ✅ | ✅ | ✅ | - |
| light_sleep_duration | ✅ | ✅ | ❌ | 添加到Today页面 |
| awake_time | ✅ | ✅ | ❌ | 显示清醒次数 |
| average_heart_rate | ✅ | ✅ | ❌ | 睡眠心率趋势图 |
| lowest_heart_rate | ✅ | ✅ | ✅ | - |
| average_hrv | ✅ | ✅ | ✅ | - |
| average_breath | ✅ | ✅ | ❌ | 呼吸频率异常提示 |
| efficiency | ✅ | ✅ | ✅ | - |
| temperature_deviation | ✅ | ✅ | ❌ | 体温异常警告 |

### Oura Activity字段检查

| 字段 | 已存储 | API暴露 | 前端展示 | 建议 |
|------|-------|---------|---------|------|
| score | ✅ | ✅ | ✅ | - |
| steps | ✅ | ✅ | ✅ | - |
| active_calories | ✅ | ✅ | ✅ | - |
| high_activity_time | ✅ | ✅ | ❌ | 活动时长分布饼图 |
| medium_activity_time | ✅ | ✅ | ❌ | 同上 |
| low_activity_time | ✅ | ✅ | ❌ | 同上 |
| sedentary_time | ✅ | ✅ | ❌ | **重要**: 久坐提醒 |
| resting_time | ✅ | ✅ | ❌ | - |
| target_calories | ✅ | ✅ | ❌ | 目标达成进度条 |
| target_meters | ✅ | ✅ | ❌ | 同上 |

### Polar Exercise字段检查

| 字段 | 已存储 | API暴露 | 前端展示 | 建议 |
|------|-------|---------|---------|------|
| zone1_sec ~ zone5_sec | ✅ | ✅ | 部分 | Zone分布柱状图 |
| avg_hr | ✅ | ✅ | ✅ | - |
| max_hr | ✅ | ✅ | ✅ | - |
| calories | ✅ | ✅ | ✅ | - |
| distance | ✅ | ✅ | ✅ | - |
| ascent | ❌ | ❌ | ❌ | 从TCX获取 |
| descent | ❌ | ❌ | ❌ | 从TCX获取 |
| training_load | ❌ | ❌ | ❌ | Polar官方负荷 |

---

## 💡 实施优先级矩阵

```
高影响 & 低成本 (立即实施)
├─ Oura心血管年龄 API
├─ Oura韧性 API
├─ 前端展示久坐时长
└─ 前端展示体温偏差警告

高影响 & 中成本 (1-2周)
├─ Oura VO2 Max API
├─ Polar Nightly Recharge API
└─ 连续心率可视化

中影响 & 低成本 (随时可做)
├─ 暴露所有已存储字段到API
├─ 前端展示活动时长分布
└─ 前端展示睡眠阶段详情

低影响 & 高成本 (3个月+)
├─ Polar睡眠数据集成
├─ 体温追踪系统
└─ 标签系统
```

---

## 📝 结论

当前系统已实现**核心基础功能**，但在**高级健康指标**和**数据细粒度**方面有较大提升空间：

**优势**:
- Oura睡眠、准备度、活动数据完整
- Polar训练心率区间数据精准
- 所有核心数据已暴露API供前端使用

**需改进**:
- **Oura**: 缺失心血管年龄、韧性、VO2 Max等关键健康指标
- **Polar**: 缺失睡眠、恢复、连续心率等完整数据
- **前端**: 许多已存储字段未展示（久坐时长、体温、活动分布等）

**建议**:
1. 优先实现心血管年龄、韧性、VO2 Max端点（对Zone2训练效果评估最重要）
2. 完善前端展示所有已存储字段
3. 长期规划Polar恢复数据集成

---

**报告生成**: VitalMatrix v0.3
**分析基准**: Oura API v2 + Polar AccessLink API v3
**文档参考**:
- https://cloud.ouraring.com/v2/docs
- https://www.polar.com/accesslink-api/
