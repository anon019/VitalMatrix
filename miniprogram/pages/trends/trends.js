// pages/trends/trends.js
const { getOuraSleep, getOuraSleepGrouped, getOuraReadiness, getOuraActivity, getOuraStress, getOuraSpo2, getTrainingTrends, getOuraHeartrateDetails, getDashboard } = require('../../utils/request.js')

Page({
  data: {
    loading: true,
    dateRange: '',

    // Polar 训练数据
    fatBurnData: [],
    avgFatBurn: 0,
    fatBurnAvgPercent: 50,
    fatBurnLabelBelow: false,
    zone2Data: [],
    avgZone2: 0,
    zone2AvgPercent: 50,
    zone2LabelBelow: false,
    hiData: [],  // Zone4-5高强度
    avgHi: 0,
    hiAvgPercent: 50,
    hiLabelBelow: false,
    caloriesData: [],
    avgCalories: 0,
    caloriesAvgPercent: 50,
    caloriesLabelBelow: false,

    // Oura 睡眠数据
    sleepScoreData: [],
    avgSleepScore: 0,
    sleepScoreAvgPercent: 50,
    sleepScoreLabelBelow: false,
    totalSleepData: [],
    avgTotalSleep: 0,
    totalSleepAvgPercent: 50,
    totalSleepLabelBelow: false,
    deepSleepData: [],
    avgDeepSleep: 0,
    deepSleepAvgPercent: 50,
    deepSleepLabelBelow: false,
    remSleepData: [],
    avgRemSleep: 0,
    remSleepAvgPercent: 50,
    remSleepLabelBelow: false,

    // Oura 准备度/活动数据
    readinessData: [],
    avgReadiness: 0,
    readinessAvgPercent: 50,
    readinessLabelBelow: false,
    hrvData: [],  // HRV心率变异性
    avgHrv: 0,
    hrvAvgPercent: 50,
    hrvLabelBelow: false,
    rhrData: [],  // 静息心率
    avgRhr: 0,
    rhrAvgPercent: 50,
    rhrLabelBelow: false,
    activityScoreData: [],
    avgActivityScore: 0,
    activityScoreAvgPercent: 50,
    activityScoreLabelBelow: false,
    stepsData: [],
    avgSteps: 0,
    stepsAvgPercent: 50,
    stepsLabelBelow: false,
    sedentaryData: [],
    avgSedentary: 0,
    sedentaryAvgPercent: 50,
    sedentaryLabelBelow: false,
    spo2Data: [],  // 血氧饱和度
    avgSpo2: 0,
    spo2AvgPercent: 50,
    spo2LabelBelow: false,
    breathData: [],  // 呼吸频率
    avgBreath: 0,
    breathAvgPercent: 50,
    breathLabelBelow: false,

    // Oura 压力数据
    stressedData: [],
    avgStressed: 0,
    stressedAvgPercent: 50,
    stressedLabelBelow: false,
    restoredData: [],
    avgRestored: 0,
    restoredAvgPercent: 50,
    restoredLabelBelow: false,

    // Oura 心率恢复数据
    hrPositionData: [],  // 最低心率出现位置百分比
    avgHrPosition: 0,
    hrPositionAvgPercent: 50,
    hrPositionLabelBelow: false,
  },

  onLoad() {
    console.log('趋势页面加载')
    this.setDateRange()

    const app = getApp()
    if (app.globalData.isLoggedIn) {
      this.loadData()
    }
  },

  onShow() {
    const lastRefresh = wx.getStorageSync('trendsLastRefresh')
    const now = Date.now()

    const app = getApp()
    if (app.globalData.isLoggedIn && (!lastRefresh || now - lastRefresh > 5 * 60 * 1000)) {
      this.loadData()
    }
  },

  onLoginSuccess() {
    console.log('趋势页面：收到登录成功通知')
    this.loadData()
  },

  onPullDownRefresh() {
    // 下拉刷新时强制跳过缓存
    const { clearAllCache } = require('../../utils/request.js')
    clearAllCache()
    this.loadData(true).then(() => {
      wx.stopPullDownRefresh()
    })
  },

  setDateRange() {
    const today = new Date()
    const weekAgo = new Date(today)
    weekAgo.setDate(weekAgo.getDate() - 6)

    const formatDate = (date) => {
      const month = date.getMonth() + 1
      const day = date.getDate()
      return `${month}/${day < 10 ? '0' + day : day}`
    }

    this.setData({
      dateRange: `${formatDate(weekAgo)} - ${formatDate(today)}`
    })
  },

  // 获取过去7天的日期列表（从6天前到今天）
  getLast7Days() {
    const days = []
    for (let i = 6; i >= 0; i--) {
      const date = new Date()
      date.setDate(date.getDate() - i)
      days.push(date.toISOString().split('T')[0])
    }
    return days
  },

  /**
   * 分层加载趋势数据（优化版）
   * 使用缓存减少请求，保持原有数据处理逻辑
   * @param {Boolean} forceRefresh 是否强制刷新（跳过缓存）
   */
  async loadData(forceRefresh = false) {
    this.setData({ loading: true })
    const startTime = Date.now()

    try {
      // 并行加载所有数据（缓存层会自动去重和复用）
      console.log('[Performance] 趋势页加载开始')
      const [sleepGroupedRes, sleepDetailRes, readinessRes, activityRes, stressRes, spo2Res, trainingRes, heartrateRes, dashboardRes] = await Promise.all([
        getOuraSleepGrouped(7).catch(err => { console.warn('分组睡眠数据获取失败:', err); return null }),
        getOuraSleep(7).catch(err => { console.warn('详细睡眠数据获取失败:', err); return null }),
        getOuraReadiness(7).catch(err => { console.warn('准备度数据获取失败:', err); return null }),
        getOuraActivity(7).catch(err => { console.warn('活动数据获取失败:', err); return null }),
        getOuraStress(7).catch(err => { console.warn('压力数据获取失败:', err); return null }),
        getOuraSpo2(7).catch(err => { console.warn('血氧数据获取失败:', err); return null }),
        getTrainingTrends(7).catch(err => { console.warn('训练数据获取失败:', err); return null }),
        getOuraHeartrateDetails(7).catch(err => { console.warn('心率详情获取失败:', err); return null }),
        getDashboard().catch(err => { console.warn('Dashboard数据获取失败:', err); return null })
      ])

      console.log(`[Performance] 趋势页API请求完成，耗时 ${Date.now() - startTime}ms`)

      // 组装数据格式（传入 dashboard 数据用于补充今天的睡眠评分）
      const trendsData = {
        sleep: this.transformSleepGroupedData(sleepGroupedRes?.records || [], dashboardRes),
        sleepDetail: this.transformSleepDetailData(sleepDetailRes?.records || []),
        readiness: this.transformReadinessData(readinessRes?.records || []),
        activity: this.transformActivityData(activityRes?.records || []),
        stress: this.transformStressData(stressRes?.records || []),
        spo2: this.transformSpo2Data(spo2Res?.records || []),
        training: this.transformTrainingData(trainingRes?.exercises || []),
        heartrate: this.transformHeartrateData(heartrateRes || [])
      }

      this.processAndSetData(trendsData)
      console.log(`[Performance] 趋势页加载完成，总耗时 ${Date.now() - startTime}ms`)

      wx.setStorageSync('trendsLastRefresh', Date.now())

    } catch (error) {
      console.error('加载趋势数据失败:', error)
      wx.showToast({
        title: '加载失败，请重试',
        icon: 'none'
      })
    } finally {
      this.setData({ loading: false })
    }
  },

  // 转换分组睡眠数据格式（支持主睡眠+午睡叠加）
  // dashboardRes 用于补充今天的睡眠评分（当 summary_score 为 null 时）
  transformSleepGroupedData(records, dashboardRes) {
    // 获取今天的日期（香港时间，用于匹配 dashboard 数据）
    const now = new Date()
    const hkOffset = 8 * 60  // 香港时区 UTC+8
    const hkTime = new Date(now.getTime() + (hkOffset + now.getTimezoneOffset()) * 60000)
    const today = hkTime.toISOString().split('T')[0]
    // dashboard 中的睡眠评分（oura_yesterday 是昨晚的睡眠，对应今天的日期）
    const dashboardSleepScore = dashboardRes?.oura_yesterday?.sleep_score

    return records.map(r => {
      // 过滤有效睡眠片段（sleep_score_delta 不为 null 的才计入，与 Oura App 一致）
      const validSegments = r.segments?.filter(s =>
        s.sleep_type === 'long_sleep' || s.sleep_score_delta !== null
      ) || []

      // 找到主睡眠片段（long_sleep类型）
      const mainSleep = validSegments.find(s => s.sleep_type === 'long_sleep')
      // 找到所有有效午休片段（非long_sleep类型）
      const napSegments = validSegments.filter(s => s.sleep_type !== 'long_sleep')

      // 计算午睡增量（summary_score - base_score）
      const napScoreBoost = r.summary_score - r.base_score

      // 计算有效片段的总时长（秒）
      const validTotalDuration = validSegments.reduce((sum, s) => sum + (s.total_sleep_duration || 0), 0)

      // 主睡眠时长
      const mainDuration = mainSleep?.total_sleep_duration || 0
      // 午睡时长
      const napDuration = validTotalDuration - mainDuration

      // 主睡眠的深睡眠和REM（秒转分钟）
      const mainDeepMin = Math.round((mainSleep?.deep_sleep_duration || 0) / 60)
      const mainRemMin = Math.round((mainSleep?.rem_sleep_duration || 0) / 60)

      // 计算有效午休的深睡眠和REM总和（秒转分钟）
      const napDeepSec = napSegments.reduce((sum, s) => sum + (s.deep_sleep_duration || 0), 0)
      const napRemSec = napSegments.reduce((sum, s) => sum + (s.rem_sleep_duration || 0), 0)
      const napDeepMin = Math.round(napDeepSec / 60)
      const napRemMin = Math.round(napRemSec / 60)

      // 睡眠评分：优先使用 summary_score，今天的数据回退到 dashboard 的 sleep_score
      let score = r.summary_score
      let baseScore = r.base_score
      if (score == null && r.day === today && dashboardSleepScore != null) {
        score = dashboardSleepScore
        // 趋势图使用 baseScore，也需要设置
        baseScore = dashboardSleepScore
      }

      return {
        date: r.day,
        // 评分数据（今天可能从 dashboard 获取）
        score: score,
        baseScore: baseScore,
        napScoreBoost: napScoreBoost > 0 ? napScoreBoost : 0,
        // 时长数据（小时）- 使用有效片段总时长
        total_hours: (validTotalDuration / 3600).toFixed(1),
        mainSleepHours: (mainDuration / 3600).toFixed(1),
        napHours: napDuration > 0 ? (napDuration / 3600).toFixed(1) : 0,
        // 深睡眠数据（分钟）- 支持叠加
        mainDeepMin: mainDeepMin,
        napDeepMin: napDeepMin,
        deep_min: mainDeepMin + napDeepMin, // 总计（兼容旧逻辑）
        // REM数据（分钟）- 支持叠加
        mainRemMin: mainRemMin,
        napRemMin: napRemMin,
        rem_min: mainRemMin + napRemMin, // 总计（兼容旧逻辑）
        // 是否有午睡（使用有效片段数）
        hasNap: validSegments.length > 1
      }
    }).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换睡眠数据格式（旧版，保留兼容）
  transformSleepData(records) {
    return records.map(r => ({
      date: r.day,
      score: r.score,
      total_hours: ((r.total_sleep_duration || 0) / 3600).toFixed(1),
      deep_min: Math.round((r.deep_sleep_duration || 0) / 60),
      rem_min: Math.round((r.rem_sleep_duration || 0) / 60)
    })).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换详细睡眠数据格式（提取HRV、静息心率、呼吸频率）
  // 注意：同一天可能有多条记录（主睡眠+午睡），需按日期聚合取主睡眠值
  transformSleepDetailData(records) {
    // 按日期分组，优先取 long_sleep 类型的数据
    const dailyMap = {}
    records.forEach(r => {
      const date = r.day
      if (!date) return
      // 优先保留主睡眠（long_sleep）的数据
      if (!dailyMap[date] || r.sleep_type === 'long_sleep') {
        dailyMap[date] = {
          date: date,
          hrv: r.average_hrv || null,  // 实际HRV毫秒值
          rhr: r.lowest_heart_rate || null,  // 实际静息心率（睡眠最低心率，单位bpm）
          breath: r.average_breath || null  // 呼吸频率（次/分钟）
        }
      }
    })
    return Object.values(dailyMap).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换准备度数据格式（支持午睡增量）
  // 注意：hrv_balance 和 resting_heart_rate 是贡献度评分(0-100)，不是实际值
  // 实际 HRV 和静息心率从 sleep API 获取
  transformReadinessData(records) {
    return records.map(r => ({
      date: r.day,
      score: r.score,
      baseScore: r.base_score || r.score,
      napBoost: r.nap_boost || 0,
      hasNap: (r.nap_boost || 0) > 0
    })).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换活动数据格式
  transformActivityData(records) {
    return records.map(r => ({
      date: r.day,
      score: r.score,
      steps: r.steps,
      sedentary_min: Math.round((r.sedentary_time || 0) / 60)
    })).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换压力数据格式
  transformStressData(records) {
    return records.map(r => ({
      date: r.day,
      stressed_min: r.stressed_minutes || 0,
      restored_min: r.restored_minutes || 0
    })).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换血氧SpO2数据格式（来自独立API /api/v1/oura/spo2）
  transformSpo2Data(records) {
    return records.map(r => ({
      date: r.day,
      // Oura SpO2 API返回的字段：spo2_percentage（直接是数值，如97.63）
      spo2: r.spo2_percentage || null
    })).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换心率详情数据格式（提取最低心率出现位置百分比）
  transformHeartrateData(records) {
    if (!records || !Array.isArray(records)) return []

    return records.map(r => ({
      date: r.day,
      // 最低心率出现位置百分比（0-100，越低越好表示在前半夜出现）
      hr_position: r.sleep_progress_percent || null,
      // 恢复质量
      recovery_quality: r.recovery_quality || null,
      // 最低心率值
      lowest_hr: r.lowest_hr || null
    })).sort((a, b) => a.date.localeCompare(b.date))
  },

  // 转换训练数据格式（按日期聚合）
  transformTrainingData(exercises) {
    // 按日期分组聚合
    const dailyMap = {}
    exercises.forEach(e => {
      const date = e.start_time?.split('T')[0]
      if (!date) return
      if (!dailyMap[date]) {
        dailyMap[date] = {
          date,
          fat_burn: 0,
          zone2_min: 0,
          hi_min: 0,  // Zone4+Zone5 高强度分钟数
          calories: 0,
          // 累计各zone秒数用于精确计算脂肪燃烧
          zone1_sec: 0, zone2_sec: 0, zone3_sec: 0, zone4_sec: 0, zone5_sec: 0
        }
      }
      dailyMap[date].zone2_min += e.zone2_min || 0
      dailyMap[date].calories += e.calories || 0
      dailyMap[date].zone1_sec += e.zone1_sec || 0
      dailyMap[date].zone2_sec += e.zone2_sec || 0
      dailyMap[date].zone3_sec += e.zone3_sec || 0
      dailyMap[date].zone4_sec += e.zone4_sec || 0
      dailyMap[date].zone5_sec += e.zone5_sec || 0
    })

    // 计算每日脂肪燃烧克数和高强度分钟数
    Object.values(dailyMap).forEach(day => {
      day.fat_burn = this.calculateFatBurn(
        day.calories,
        day.zone1_sec, day.zone2_sec, day.zone3_sec, day.zone4_sec, day.zone5_sec
      )
      // Zone4+Zone5 高强度分钟数
      day.hi_min = Math.round((day.zone4_sec + day.zone5_sec) / 60)
    })

    return Object.values(dailyMap).sort((a, b) => a.date.localeCompare(b.date))
  },

  /**
   * 计算脂肪燃烧克数（基于Polar/运动生理学方法）
   * 各Zone脂肪供能比例：Zone1=85%, Zone2=65%, Zone3=45%, Zone4=25%, Zone5=10%
   * 1克脂肪产生约7.7千卡能量
   */
  calculateFatBurn(calories, zone1Sec, zone2Sec, zone3Sec, zone4Sec, zone5Sec) {
    const totalZoneSec = zone1Sec + zone2Sec + zone3Sec + zone4Sec + zone5Sec
    if (!calories || calories <= 0 || totalZoneSec <= 0) return 0

    const weightedFatRatio = (
      zone1Sec * 0.85 + zone2Sec * 0.65 + zone3Sec * 0.45 + zone4Sec * 0.25 + zone5Sec * 0.10
    ) / totalZoneSec

    return Math.round((calories * weightedFatRatio) / 7.7)
  },

  processAndSetData(data) {
    // 处理 Polar 训练数据
    const trainingDays = data.training || []
    const fatBurnResult = this.processMetric(trainingDays, 'fat_burn')
    const zone2Result = this.processMetric(trainingDays, 'zone2_min')
    const hiResult = this.processMetric(trainingDays, 'hi_min')  // Zone4-5高强度
    const caloriesResult = this.processMetric(trainingDays, 'calories')

    // 处理 Oura 睡眠数据（使用叠加方式显示主睡眠+午睡）
    const sleepDays = data.sleep || []
    const sleepScoreResult = this.processStackedMetric(sleepDays, 'baseScore', 'napScoreBoost')
    const totalSleepResult = this.processStackedMetric(sleepDays, 'mainSleepHours', 'napHours', 1)
    const deepSleepResult = this.processStackedMetric(sleepDays, 'mainDeepMin', 'napDeepMin')
    const remSleepResult = this.processStackedMetric(sleepDays, 'mainRemMin', 'napRemMin')

    // 血氧SpO2从独立API获取
    const spo2Days = data.spo2 || []
    const spo2Result = this.processMetric(spo2Days, 'spo2', 1)

    // 处理 Oura 准备度数据（使用叠加方式显示基础分+午睡加分）
    const readinessDays = data.readiness || []
    const readinessResult = this.processStackedMetric(readinessDays, 'baseScore', 'napBoost')

    // HRV、静息心率、呼吸频率从详细睡眠数据获取
    // 注意：readiness API 的 resting_heart_rate 是贡献度评分(0-100)，不是实际心率
    // 实际静息心率使用 sleep API 的 lowest_heart_rate（睡眠期间最低心率）
    const sleepDetailDays = data.sleepDetail || []
    const hrvResult = this.processMetric(sleepDetailDays, 'hrv')
    const rhrResult = this.processMetric(sleepDetailDays, 'rhr')  // 实际静息心率 bpm
    const breathResult = this.processMetric(sleepDetailDays, 'breath', 1)

    // 处理 Oura 活动数据
    const activityDays = data.activity || []
    const activityScoreResult = this.processMetric(activityDays, 'score')
    const stepsResult = this.processMetric(activityDays, 'steps')
    const sedentaryResult = this.processMetric(activityDays, 'sedentary_min')

    // 处理 Oura 压力数据
    const stressDays = data.stress || []
    const stressedResult = this.processMetric(stressDays, 'stressed_min')
    const restoredResult = this.processMetric(stressDays, 'restored_min')

    // 处理 Oura 心率位置数据（最低心率出现的睡眠进度百分比）
    const heartrateDays = data.heartrate || []
    const hrPositionResult = this.processHrPositionMetric(heartrateDays)

    this.setData({
      // Polar 训练数据
      fatBurnData: fatBurnResult.data,
      avgFatBurn: fatBurnResult.avg,
      fatBurnAvgPercent: fatBurnResult.avgPercent,
      fatBurnLabelBelow: fatBurnResult.avgLabelBelow,
      zone2Data: zone2Result.data,
      avgZone2: zone2Result.avg,
      zone2AvgPercent: zone2Result.avgPercent,
      zone2LabelBelow: zone2Result.avgLabelBelow,
      hiData: hiResult.data,
      avgHi: hiResult.avg,
      hiAvgPercent: hiResult.avgPercent,
      hiLabelBelow: hiResult.avgLabelBelow,
      caloriesData: caloriesResult.data,
      avgCalories: caloriesResult.avg,
      caloriesAvgPercent: caloriesResult.avgPercent,
      caloriesLabelBelow: caloriesResult.avgLabelBelow,

      // Oura 睡眠数据
      sleepScoreData: sleepScoreResult.data,
      avgSleepScore: sleepScoreResult.avg,
      sleepScoreAvgPercent: sleepScoreResult.avgPercent,
      sleepScoreLabelBelow: sleepScoreResult.avgLabelBelow,
      totalSleepData: totalSleepResult.data,
      avgTotalSleep: totalSleepResult.avg,
      totalSleepAvgPercent: totalSleepResult.avgPercent,
      totalSleepLabelBelow: totalSleepResult.avgLabelBelow,
      deepSleepData: deepSleepResult.data,
      avgDeepSleep: deepSleepResult.avg,
      deepSleepAvgPercent: deepSleepResult.avgPercent,
      deepSleepLabelBelow: deepSleepResult.avgLabelBelow,
      remSleepData: remSleepResult.data,
      avgRemSleep: remSleepResult.avg,
      remSleepAvgPercent: remSleepResult.avgPercent,
      remSleepLabelBelow: remSleepResult.avgLabelBelow,

      // Oura 准备度/恢复数据
      readinessData: readinessResult.data,
      avgReadiness: readinessResult.avg,
      readinessAvgPercent: readinessResult.avgPercent,
      readinessLabelBelow: readinessResult.avgLabelBelow,
      hrvData: hrvResult.data,
      avgHrv: hrvResult.avg,
      hrvAvgPercent: hrvResult.avgPercent,
      hrvLabelBelow: hrvResult.avgLabelBelow,
      rhrData: rhrResult.data,
      avgRhr: rhrResult.avg,
      rhrAvgPercent: rhrResult.avgPercent,
      rhrLabelBelow: rhrResult.avgLabelBelow,

      // Oura 活动数据
      activityScoreData: activityScoreResult.data,
      avgActivityScore: activityScoreResult.avg,
      activityScoreAvgPercent: activityScoreResult.avgPercent,
      activityScoreLabelBelow: activityScoreResult.avgLabelBelow,
      stepsData: stepsResult.data,
      avgSteps: stepsResult.avg,
      stepsAvgPercent: stepsResult.avgPercent,
      stepsLabelBelow: stepsResult.avgLabelBelow,
      sedentaryData: sedentaryResult.data,
      avgSedentary: sedentaryResult.avg,
      sedentaryAvgPercent: sedentaryResult.avgPercent,
      sedentaryLabelBelow: sedentaryResult.avgLabelBelow,
      spo2Data: spo2Result.data,
      avgSpo2: spo2Result.avg,
      spo2AvgPercent: spo2Result.avgPercent,
      spo2LabelBelow: spo2Result.avgLabelBelow,
      breathData: breathResult.data,
      avgBreath: breathResult.avg,
      breathAvgPercent: breathResult.avgPercent,
      breathLabelBelow: breathResult.avgLabelBelow,

      // Oura 压力数据
      stressedData: stressedResult.data,
      avgStressed: stressedResult.avg,
      stressedAvgPercent: stressedResult.avgPercent,
      stressedLabelBelow: stressedResult.avgLabelBelow,
      restoredData: restoredResult.data,
      avgRestored: restoredResult.avg,
      restoredAvgPercent: restoredResult.avgPercent,
      restoredLabelBelow: restoredResult.avgLabelBelow,

      // Oura 心率恢复数据
      hrPositionData: hrPositionResult.data,
      avgHrPosition: hrPositionResult.avg,
      hrPositionAvgPercent: hrPositionResult.avgPercent,
      hrPositionLabelBelow: hrPositionResult.avgLabelBelow,

      loading: false
    })
  },

  /**
   * 处理叠加指标的数据（支持主值+增量值的叠加柱状图）
   * @param {Array} days 每日数据数组
   * @param {String} baseField 基础值字段名
   * @param {String} boostField 增量值字段名
   * @param {Number} decimals 小数位数（默认0）
   * @returns {Object} { data: Array, avg: Number, avgPercent: Number }
   */
  processStackedMetric(days, baseField, boostField, decimals = 0) {
    const last7Days = this.getLast7Days()

    // 创建日期到数据的映射
    const dataMap = {}
    days.forEach(day => {
      dataMap[day.date] = {
        base: day[baseField],
        boost: day[boostField] || 0
      }
    })

    // 提取7天的值
    const rawData = last7Days.map(date => {
      const item = dataMap[date]
      if (!item || item.base === null || item.base === undefined) {
        return { base: null, boost: 0, total: null }
      }
      const base = Number(item.base)
      const boost = Number(item.boost) || 0
      return { base, boost, total: base + boost }
    })

    // 计算平均值（使用总值，排除null和0）
    const validTotals = rawData.filter(d => d.total !== null && d.total > 0).map(d => d.total)
    const avg = validTotals.length > 0
      ? validTotals.reduce((a, b) => a + b, 0) / validTotals.length
      : 0

    // 计算最大值用于百分比
    const maxValue = Math.max(...rawData.map(d => d.total || 0), 1)

    // 计算均值百分比
    const avgPercent = Math.round((avg / maxValue) * 100)

    // 生成图表数据
    const data = last7Days.map((date, index) => {
      const item = rawData[index]
      const isEmpty = item.total === null || item.total === 0
      const basePercent = isEmpty ? 0 : Math.round((item.base / maxValue) * 100)
      const boostPercent = isEmpty ? 0 : Math.round((item.boost / maxValue) * 100)
      const totalPercent = isEmpty ? 0 : Math.max(basePercent + boostPercent, 15)

      return {
        date: date,
        dayLabel: this.getDayLabel(date),
        // 总值（显示用）
        value: isEmpty ? '-' : (decimals > 0 ? item.total.toFixed(decimals) : Math.round(item.total)),
        // 基础值
        baseValue: isEmpty ? 0 : (decimals > 0 ? item.base.toFixed(decimals) : Math.round(item.base)),
        basePercent: isEmpty ? 0 : Math.max(basePercent, 10),
        // 增量值
        boostValue: item.boost > 0 ? (decimals > 0 ? item.boost.toFixed(decimals) : Math.round(item.boost)) : 0,
        boostPercent: boostPercent,
        // 是否有增量（午睡）
        hasBoost: item.boost > 0,
        // 总百分比
        percent: totalPercent,
        isEmpty: isEmpty
      }
    })

    const avgLabelBelow = avgPercent > 50

    return {
      data,
      avg: decimals > 0 ? avg.toFixed(decimals) : Math.round(avg),
      avgPercent: avgPercent,
      avgLabelBelow: avgLabelBelow
    }
  },

  /**
   * 处理单个指标的数据
   * @param {Array} days 每日数据数组
   * @param {String} field 字段名
   * @param {Number} decimals 小数位数（默认0）
   * @returns {Object} { data: Array, avg: Number, avgPercent: Number }
   */
  processMetric(days, field, decimals = 0) {
    // 获取过去7天的日期
    const last7Days = this.getLast7Days()

    // 创建日期到数据的映射
    const dataMap = {}
    days.forEach(day => {
      dataMap[day.date] = day[field]
    })

    // 提取7天的值（保留 null/undefined 用于区分空数据）
    const rawValues = last7Days.map(date => {
      const value = dataMap[date]
      return value !== null && value !== undefined ? Number(value) : null
    })

    // 计算平均值（排除null和0值）
    const validValues = rawValues.filter(v => v !== null && v > 0)
    const avg = validValues.length > 0
      ? validValues.reduce((a, b) => a + b, 0) / validValues.length
      : 0

    // 计算最大值用于百分比（排除null）
    const numericValues = rawValues.map(v => v === null ? 0 : v)
    const maxValue = Math.max(...numericValues, 1)

    // 计算均值在图表中的百分比位置
    const avgPercent = Math.round((avg / maxValue) * 100)

    // 生成图表数据（固定7天）
    const data = last7Days.map((date, index) => {
      const rawValue = rawValues[index]
      const isEmpty = rawValue === null || rawValue === 0
      const value = isEmpty ? 0 : rawValue
      const percent = Math.round((value / maxValue) * 100)

      return {
        date: date,
        dayLabel: this.getDayLabel(date),
        value: isEmpty ? '-' : (decimals > 0 ? Number(value).toFixed(decimals) : Math.round(value)),
        percent: isEmpty ? 0 : Math.max(percent, 15), // 空数据用0，有数据最小15%
        isEmpty: isEmpty // 标记是否为空数据
      }
    })

    // 智能判断标签位置：均值在上半部分时标签在下方，否则在上方
    const avgLabelBelow = avgPercent > 50

    return {
      data,
      avg: decimals > 0 ? avg.toFixed(decimals) : Math.round(avg),
      avgPercent: avgPercent,
      avgLabelBelow: avgLabelBelow
    }
  },

  /**
   * 处理心率位置百分比数据（特殊：值越低越好，颜色动态变化）
   * @param {Array} days 每日数据数组
   * @returns {Object} { data: Array, avg: Number, avgPercent: Number }
   */
  processHrPositionMetric(days) {
    const last7Days = this.getLast7Days()

    // 创建日期到数据的映射
    const dataMap = {}
    days.forEach(day => {
      dataMap[day.date] = {
        position: day.hr_position,
        quality: day.recovery_quality
      }
    })

    // 提取7天的值
    const rawValues = last7Days.map(date => {
      const item = dataMap[date]
      return item && item.position !== null && item.position !== undefined
        ? { value: Number(item.position), quality: item.quality }
        : null
    })

    // 计算平均值（排除null）
    const validValues = rawValues.filter(v => v !== null).map(v => v.value)
    const avg = validValues.length > 0
      ? validValues.reduce((a, b) => a + b, 0) / validValues.length
      : 0

    // 对于百分比，最大值固定100
    const maxValue = 100
    const avgPercent = Math.round((avg / maxValue) * 100)

    // 生成图表数据
    const data = last7Days.map((date, index) => {
      const rawItem = rawValues[index]
      const isEmpty = rawItem === null
      const value = isEmpty ? 0 : rawItem.value
      const quality = isEmpty ? null : rawItem.quality
      const percent = Math.round((value / maxValue) * 100)

      // 颜色：<=50%为绿色（理想），>50%为橙色（次优）
      const colorClass = value <= 50 ? 'green' : 'orange'

      return {
        date: date,
        dayLabel: this.getDayLabel(date),
        value: isEmpty ? '-' : Math.round(value),
        percent: isEmpty ? 0 : Math.max(percent, 15),
        isEmpty: isEmpty,
        colorClass: colorClass,
        quality: quality === 'optimal' ? '理想' : (quality === 'suboptimal' ? '次优' : '')
      }
    })

    // 均值标签位置
    const avgLabelBelow = avgPercent > 50

    return {
      data,
      avg: Math.round(avg),
      avgPercent: avgPercent,
      avgLabelBelow: avgLabelBelow
    }
  },

  /**
   * 获取星期几标签
   */
  getDayLabel(dateStr) {
    if (!dateStr) return '-'

    const date = new Date(dateStr)
    const dayLabels = ['日', '一', '二', '三', '四', '五', '六']
    return dayLabels[date.getDay()]
  }
})
