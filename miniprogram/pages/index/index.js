// pages/index/index.js
const { getTodayTraining, getWeeklyTraining, getTrainingHistory, getOuraSleepGrouped, getOuraReadiness, getOuraActivity, getOuraSpo2, getOuraStress, getOuraHeartrateDetail, getDashboard } = require('../../utils/request.js')
const { formatLocalDate } = require('../../utils/date.js')

Page({
  data: {
    loading: true,
    todayDate: '',
    todayDateFull: '',  // 完整日期显示
    todayDateISO: '',   // ISO格式今日日期，用于比较 YYYY-MM-DD

    // 问候语
    greeting: '早上好',
    greetingEmoji: '🌅',
    healthSummary: '',  // 健康状态一句话总结

    // 日期显示
    trainingDate: '',
    sleepDate: '',
    spo2Date: '',
    stressDate: '',
    stressDateDisplay: '',  // 压力数据的友好日期显示
    readinessDate: '',
    activityDate: '',
    weeklyDateRange: '',

    // 训练数据 - Polar
    trainingData: null,

    // 睡眠数据 - Oura
    sleepData: null,

    // 准备度数据 - Oura
    readinessData: null,

    // 活动数据 - Oura
    activityData: null,

    // 压力数据 - Oura
    stressData: null,

    // 心率详情数据 - Oura
    heartrateDetail: null,

    // 本周训练总结 - Polar
    weeklyData: null,

    // 数据异常提醒
    alerts: [],

    // 晨间检查 - 行动信号 (Oura官方分档: Optimal/Good/Pay Attention)
    readinessLevel: 'level-medium',  // level-high, level-medium, level-low
    actionAdvice: {
      title: '良好',
      desc: '状态良好，按计划进行'
    },
    sleepLevel: 'level-medium',  // level-high, level-medium, level-low
    sleepAdvice: {
      title: '良好',
      desc: '睡眠质量正常'
    },
    alertType: '',  // danger, warning, info

    // 核心四指标警报
    hrvAlert: false,
    rhrAlert: false,
    deepAlert: false,

    // 核心指标差值（与昨天对比）
    hrvDelta: null,   // { value: 5, direction: 'up' }  方向：up=好，down=差
    rhrDelta: null,   // { value: 2, direction: 'down' } 注意：RHR下降是好事
    deepDelta: null,  // { value: 10, direction: 'up' }
    remDelta: null,   // { value: 5, direction: 'up' }

    // 晨间警报（最重要的一条）
    morningAlert: null,

    // 名词解释弹窗
    showGlossaryModal: false,

    // 卡片展开状态
    expandedCards: {
      training: false,
      sleep: false,
      readiness: false,
      activity: false,
      weekly: false
    }
  },

  onLoad() {
    console.log('今日页面加载')
    this._hasShownOnce = false
    this.setDates()

    // 检查是否已登录
    const app = getApp()
    if (app.globalData.isLoggedIn) {
      console.log('已登录，加载数据')
      this.loadData({ silent: true })
    } else {
      console.log('等待登录完成...')
    }
  },

  onShow() {
    if (!this._hasShownOnce) {
      this._hasShownOnce = true
      return
    }

    // 每次显示页面时，检查是否需要刷新
    const lastRefresh = wx.getStorageSync('lastRefreshTime')
    const now = Date.now()

    const app = getApp()
    if (app.globalData.isLoggedIn && (!lastRefresh || now - lastRefresh > 10 * 60 * 1000)) {
      this.loadData({ silent: true })
    }
  },

  /**
   * 登录成功回调（由 app.js 调用）
   */
  onLoginSuccess() {
    console.log('收到登录成功通知，重新加载数据')
    this.loadData({ silent: true })
  },

  onPullDownRefresh() {
    // 下拉刷新时清除缓存
    const { clearAllCache } = require('../../utils/request.js')
    clearAllCache()
    this.loadData({ silent: false }).then(() => {
      wx.stopPullDownRefresh()
    })
  },

  /**
   * 切换卡片展开/收起状态
   */
  toggleCard(e) {
    const cardName = e.currentTarget.dataset.card
    const key = `expandedCards.${cardName}`
    const isExpanding = !this.data.expandedCards[cardName]

    this.setData({
      [key]: isExpanding
    }, () => {
      // 展开时延迟绘制雷达图（等待canvas创建）
      if (isExpanding) {
        setTimeout(() => {
          this.drawRadarForCard(cardName)
        }, 100)
      }
    })
  },

  /**
   * 为指定卡片绘制雷达图
   * 注意：过滤掉 null 值的维度，避免显示异常
   */
  drawRadarForCard(cardName) {
    const { sleepData, readinessData, activityData } = this.data

    if (cardName === 'sleep' && sleepData) {
      // 睡眠雷达图：优先使用 contributors，如果没有则不绘制
      if (sleepData.contributors && Object.keys(sleepData.contributors).length > 0) {
        const sleepRadarData = [
          { label: '深睡', value: sleepData.contributors.deep_sleep },
          { label: '时长', value: sleepData.contributors.total_sleep },
          { label: '时机', value: sleepData.contributors.timing },
          { label: '延迟', value: sleepData.contributors.latency },
          { label: '安稳度', value: sleepData.contributors.restfulness },
          { label: '效率', value: sleepData.contributors.efficiency },
          { label: 'REM', value: sleepData.contributors.rem_sleep }
        ].filter(item => item.value != null)  // 过滤掉 null/undefined

        if (sleepRadarData.length >= 3) {
          this.drawRadar('sleepRadar', sleepRadarData)
        }
      }
    } else if (cardName === 'readiness' && readinessData) {
      // 准备度雷达图：过滤掉 null 值的维度（如 body_temperature）
      const readinessRadarData = [
        { label: '活动平衡', value: readinessData.activity_balance },
        { label: '睡眠规律', value: readinessData.sleep_regularity },
        { label: '睡眠平衡', value: readinessData.sleep_balance },
        { label: '静息心率', value: readinessData.resting_heart_rate },
        { label: '恢复指数', value: readinessData.recovery_index },
        { label: '前晚睡眠', value: readinessData.previous_night },
        { label: '前日活动', value: readinessData.previous_day_activity },
        { label: 'HRV平衡', value: readinessData.hrv_balance },
        { label: '体温', value: readinessData.body_temperature }
      ].filter(item => item.value != null)  // 过滤掉 null/undefined（如体温缺失）

      if (readinessRadarData.length >= 3) {
        this.drawRadar('readinessRadar', readinessRadarData)
      }
    } else if (cardName === 'activity' && activityData && activityData.contributors) {
      const activityRadarData = [
        { label: '保持活跃', value: activityData.contributors.stay_active },
        { label: '每小时活动', value: activityData.contributors.move_every_hour },
        { label: '恢复时间', value: activityData.contributors.recovery_time },
        { label: '达成目标', value: activityData.contributors.meet_daily_targets },
        { label: '训练频率', value: activityData.contributors.training_frequency },
        { label: '训练量', value: activityData.contributors.training_volume }
      ].filter(item => item.value != null)

      if (activityRadarData.length >= 3) {
        this.drawRadar('activityRadar', activityRadarData)
      }
    }
  },

  /**
   * 显示名词解释弹窗
   */
  showGlossary() {
    this.setData({ showGlossaryModal: true })
  },

  /**
   * 隐藏名词解释弹窗
   */
  hideGlossary() {
    this.setData({ showGlossaryModal: false })
  },

  /**
   * 阻止事件冒泡
   */
  stopPropagation() {
    // 空函数，用于阻止冒泡
  },

  setDates() {
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    // 格式化今日日期
    const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    const todayDateStr = `${today.getMonth() + 1}月${today.getDate()}日 ${weekDays[today.getDay()]}`
    const todayDateFull = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日 ${weekDays[today.getDay()]}`

    // 计算本周日期范围
    const weekStart = new Date(today)
    weekStart.setDate(today.getDate() - today.getDay() + 1) // 周一
    const weekEnd = new Date(weekStart)
    weekEnd.setDate(weekStart.getDate() + 6) // 周日

    // 根据时间设置问候语
    const hour = today.getHours()
    let greeting = '早上好'
    let greetingEmoji = '🌅'
    if (hour >= 5 && hour < 9) {
      greeting = '早上好'
      greetingEmoji = '🌅'
    } else if (hour >= 9 && hour < 12) {
      greeting = '上午好'
      greetingEmoji = '☀️'
    } else if (hour >= 12 && hour < 14) {
      greeting = '中午好'
      greetingEmoji = '🌞'
    } else if (hour >= 14 && hour < 18) {
      greeting = '下午好'
      greetingEmoji = '🌤️'
    } else if (hour >= 18 && hour < 22) {
      greeting = '晚上好'
      greetingEmoji = '🌙'
    } else {
      greeting = '夜深了'
      greetingEmoji = '🌃'
    }

    this.setData({
      todayDate: todayDateStr,
      todayDateFull: todayDateFull,
      todayDateISO: this.formatDateShort(today),  // YYYY-MM-DD格式
      greeting: greeting,
      greetingEmoji: greetingEmoji,
      trainingDate: this.formatDateShort(yesterday),
      sleepDate: this.formatDateShort(today),
      readinessDate: this.formatDateShort(today),
      activityDate: this.formatDateShort(today),
      weeklyDateRange: `${this.formatDateRange(weekStart)} ~ ${this.formatDateRange(weekEnd)}`
    })
  },

  formatDateShort(date) {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  },

  formatDateRange(date) {
    const month = date.getMonth() + 1
    const day = date.getDate()
    return `${month}.${day < 10 ? '0' + day : day}`
  },

  /**
   * 将ISO日期字符串(YYYY-MM-DD)格式化为友好显示格式(M月D日)
   */
  formatDateFriendly(isoDateStr) {
    if (!isoDateStr) return ''
    const [year, month, day] = isoDateStr.split('-')
    return `${parseInt(month)}月${parseInt(day)}日`
  },

  /**
   * 分层加载数据（优化版）
   * - 第一层：关键数据（Dashboard + 训练）→ 首屏显示
   * - 第二层：核心数据（睡眠 + 准备度 + 活动）
   * - 第三层：增强数据（周报 + 压力 + 血氧 + 心率详情）
   */
  loadData(options = {}) {
    if (this._loadPromise) {
      return this._loadPromise
    }

    const loadPromise = this.performLoadData(options).finally(() => {
      if (this._loadPromise === loadPromise) {
        this._loadPromise = null
      }
    })

    this._loadPromise = loadPromise
    return loadPromise
  },

  async performLoadData(options = {}) {
    const { silent = false } = options
    const shouldShowLoading = !this._hasLoadedOnce || !silent

    if (shouldShowLoading) {
      this.setData({ loading: true })
    }

    const startTime = Date.now()

    try {
      const today = new Date()
      const todayStr = formatLocalDate(today)

      // ========== 第一层：关键数据（首屏） ==========
      console.log('[Performance] 第一层加载开始')
      const [dashboardResult, todayTrainingResult, trainingHistoryResult] = await Promise.all([
        getDashboard().catch(err => {
          console.warn('获取Dashboard数据失败:', err)
          return null
        }),
        getTodayTraining().catch(err => {
          console.warn('获取今日训练数据失败:', err)
          return null
        }),
        getTrainingHistory({ days: 14 }).catch(err => {
          console.warn('获取训练历史数据失败:', err)
          return null
        })
      ])

      // 处理并显示第一层数据
      const trainingData = this.processTrainingHistoryData(trainingHistoryResult, todayTrainingResult)
      let trainingDate = this.data.trainingDate
      if (trainingData && trainingData.actualDate) {
        trainingDate = trainingData.actualDate
      }

      // 第一次 setData：首屏可见
      this.setData({
        loading: false,
        trainingData,
        trainingDate
      })
      console.log(`[Performance] 第一层完成，耗时 ${Date.now() - startTime}ms`)

      // ========== 第二层：核心+增强数据 ==========
      console.log('[Performance] 第二层加载开始')
      const [sleepResult, readinessResult, activityResult, spo2Result, weeklyResult, stressResult, heartrateDetailResult] = await Promise.all([
        getOuraSleepGrouped(7).catch(err => {
          console.warn('获取睡眠数据失败:', err)
          return null
        }),
        getOuraReadiness(7).catch(err => {
          console.warn('获取准备度数据失败:', err)
          return null
        }),
        getOuraActivity(7).catch(err => {
          console.warn('获取活动数据失败:', err)
          return null
        }),
        getOuraSpo2(7).catch(err => {
          console.warn('获取血氧数据失败:', err)
          return null
        }),
        getWeeklyTraining().catch(err => {
          console.warn('获取本周训练数据失败:', err)
          return null
        }),
        getOuraStress(7).catch(err => {
          console.warn('获取压力数据失败:', err)
          return null
        }),
        getOuraHeartrateDetail(todayStr).catch(err => {
          console.warn('获取心率详情数据失败:', err)
          return null
        })
      ])

      // 处理所有数据
      const sleepData = this.processSleepData(sleepResult, spo2Result, dashboardResult)
      const spo2Data = this.processSpo2Data(spo2Result)
      const readinessData = this.processReadinessData(readinessResult, sleepData)
      const activityData = this.processActivityData(activityResult)
      const stressData = this.processStressData(stressResult, readinessData?.day)
      const heartrateDetail = this.processHeartrateDetail(heartrateDetailResult, sleepResult)
      const weeklyData = this.processWeeklyData(weeklyResult, trainingHistoryResult)
      const morningCheckData = this.computeMorningCheckData(sleepData, readinessData, sleepResult, readinessResult)

      const sleepDate = sleepData && sleepData.day ? sleepData.day : this.data.sleepDate
      const spo2Date = spo2Data && spo2Data.day ? spo2Data.day : this.data.spo2Date
      const readinessDate = readinessData && readinessData.day ? readinessData.day : this.data.readinessDate
      const activityDate = activityData && activityData.day ? activityData.day : this.data.activityDate
      const stressDate = stressData && stressData.day ? stressData.day : this.data.stressDate
      const stressDateDisplay = stressDate ? this.formatDateFriendly(stressDate) : ''

      const healthSummary = this.generateHealthSummary(sleepData, readinessData, activityData, trainingData)
      const alerts = this.generateAlerts(sleepData, readinessData, activityData, trainingData, stressData)

      // 一次性 setData（合并原来的第二次和第三次）
      this.setData({
        // 核心数据
        sleepData,
        sleepDate,
        spo2Date,
        readinessData,
        readinessDate,
        activityData,
        activityDate,
        readinessLevel: morningCheckData.readinessLevel,
        actionAdvice: morningCheckData.actionAdvice,
        sleepLevel: morningCheckData.sleepLevel,
        sleepAdvice: morningCheckData.sleepAdvice,
        // 增强数据
        stressData,
        stressDate,
        stressDateDisplay,
        weeklyData,
        heartrateDetail,
        healthSummary,
        alerts,
        alertType: morningCheckData.alertType,
        hrvAlert: morningCheckData.hrvAlert,
        rhrAlert: morningCheckData.rhrAlert,
        deepAlert: morningCheckData.deepAlert,
        hrvDelta: morningCheckData.hrvDelta,
        rhrDelta: morningCheckData.rhrDelta,
        deepDelta: morningCheckData.deepDelta,
        remDelta: morningCheckData.remDelta,
        morningAlert: morningCheckData.morningAlert
      })
      this._hasLoadedOnce = true
      console.log(`[Performance] 第二层完成，总耗时 ${Date.now() - startTime}ms`)

      // 绘制图表（只绘制已展开的卡片的雷达图）
      setTimeout(() => {
        const { expandedCards } = this.data
        if (expandedCards.sleep || expandedCards.readiness || expandedCards.activity) {
          this.drawRadarCharts()
        }
      }, 300)

      wx.setStorageSync('lastRefreshTime', Date.now())

      if (!silent) {
        wx.showToast({
          title: '刷新成功',
          icon: 'success',
          duration: 1000
        })
      }
    } catch (error) {
      console.error('加载数据失败:', error)
      if (shouldShowLoading) {
        this.setData({ loading: false })
      }

      if (!silent || !this._hasLoadedOnce) {
        wx.showToast({
          title: '加载失败，请重试',
          icon: 'none'
        })
      }
    }
  },

  /**
   * 处理训练历史数据 - 获取最新的训练数据
   * 优先显示最近一天有训练的数据（可能是今天或之前）
   * @param {Object} historyData 训练历史数据
   * @param {Object} todaySummary 今日训练汇总（包含后端计算的TRIMP）
   * @returns {Object} 训练数据对象，包含 actualDate 字段
   */
  processTrainingHistoryData(historyData, todaySummary) {
    if (!historyData || !historyData.exercises || historyData.exercises.length === 0) return null

    // 从后端获取的TRIMP值（如果有）
    const backendTrimp = todaySummary ? todaySummary.trimp : null

    // 按日期分组训练记录，找出最新有数据的那天
    const exercisesByDate = {}
    historyData.exercises.forEach(ex => {
      const exDate = ex.start_time ? ex.start_time.split('T')[0] : ''
      if (exDate) {
        if (!exercisesByDate[exDate]) {
          exercisesByDate[exDate] = []
        }
        exercisesByDate[exDate].push(ex)
      }
    })

    // 获取最新的日期（日期字符串排序，最大的就是最新的）
    const dates = Object.keys(exercisesByDate).sort().reverse()
    if (dates.length === 0) return null

    const latestDate = dates[0]
    const latestExercises = exercisesByDate[latestDate]

    // 处理最新一天的训练数据
    if (latestExercises.length === 1) {
      const result = this.processExerciseData(latestExercises[0], 1, backendTrimp)
      if (result) {
        result.actualDate = latestDate
      }
      return result
    }

    // 如果当天有多条训练记录，合并它们
    const result = this.mergeExercises(latestExercises, backendTrimp)
    if (result) {
      result.actualDate = latestDate
    }
    return result
  },

  /**
   * 处理单条训练记录
   * @param {Object} data 训练记录数据
   * @param {Number} sessions 训练次数
   * @param {Number} backendTrimp 后端计算的TRIMP值
   */
  processExerciseData(data, sessions = 1, backendTrimp = null) {
    if (!data) return null

    // 先用秒计算，保证精度
    const durationSec = data.duration_sec || 0
    const zone1Sec = data.zone1_sec || 0
    const zone2Sec = data.zone2_sec || 0
    const zone3Sec = data.zone3_sec || 0
    const zone4Sec = data.zone4_sec || 0
    const zone5Sec = data.zone5_sec || 0
    const hiSec = zone4Sec + zone5Sec
    const totalZoneSec = zone1Sec + zone2Sec + zone3Sec + zone4Sec + zone5Sec

    // 最后转换为分钟显示
    const durationMin = Math.round(durationSec / 60)
    const zone1Min = Math.round(zone1Sec / 60)
    const zone2Min = Math.round(zone2Sec / 60)
    const zone3Min = Math.round(zone3Sec / 60)
    const zone4Min = Math.round(zone4Sec / 60)
    const zone5Min = Math.round(zone5Sec / 60)
    const hiMin = Math.round(hiSec / 60)

    // 运动类型映射
    const sportTypeMap = {
      'running': '跑步',
      'cycling': '骑行',
      'swimming': '游泳',
      'walking': '步行',
      'strength_training': '力量训练',
      'other': '其他',
      'RUNNING': '跑步',
      'CYCLING': '骑行',
      'SWIMMING': '游泳',
      'WALKING': '步行',
      'STRENGTH_TRAINING': '力量训练',
      'OTHER': '其他'
    }

    // 优先使用Polar的cardio_load，其次后端TRIMP，最后自己计算
    const trimp = data.cardio_load || backendTrimp || this.calculateTrimp(data)

    // 计算脂肪燃烧克数（基于Polar/运动生理学方法）
    const fatBurnGrams = this.calculateFatBurn(data.calories || 0, zone1Sec, zone2Sec, zone3Sec, zone4Sec, zone5Sec, totalZoneSec)

    // 根据Polar返回的心率区间边界值，判断平均心率所属区间
    const avgHr = data.avg_hr || 0
    const maxHr = data.max_hr || 0
    const zoneLimits = data.zone_limits || null
    const avgHrColor = this.getHrZoneColorByLimits(avgHr, zoneLimits, zone1Sec, zone2Sec, zone3Sec, zone4Sec, zone5Sec)

    return {
      // 脂肪燃烧（克）- 基于卡路里和心率区间的专业估算
      fat_burn: fatBurnGrams,
      sport_type: data.sport_type || 'running',
      sport_type_display: sportTypeMap[data.sport_type] || '跑步',
      duration_min: durationMin,
      avg_hr: avgHr,
      avgHrColor: avgHrColor,
      max_hr: maxHr,
      calories: data.calories || 0,
      trimp: trimp ? trimp.toFixed(1) : 0,
      distance: data.distance_meters || data.distance || 0,
      sessions: sessions,
      zone2_min: zone2Min,
      // 用秒计算比例，保证精度
      zone2_ratio: durationSec > 0 ? Math.round((zone2Sec / durationSec) * 100) : 0,
      zone2_goal_percent: Math.round((zone2Sec / 3300) * 100), // 以55分钟(3300秒)为Zone2目标
      zone1_min: zone1Min,
      zone3_min: zone3Min,
      zone4_min: zone4Min,
      zone5_min: zone5Min,
      zone1_percent: totalZoneSec > 0 ? Math.round((zone1Sec / totalZoneSec) * 100) : 0,
      zone2_percent: totalZoneSec > 0 ? Math.round((zone2Sec / totalZoneSec) * 100) : 0,
      zone3_percent: totalZoneSec > 0 ? Math.round((zone3Sec / totalZoneSec) * 100) : 0,
      zone4_percent: totalZoneSec > 0 ? Math.round((zone4Sec / totalZoneSec) * 100) : 0,
      zone5_percent: totalZoneSec > 0 ? Math.round((zone5Sec / totalZoneSec) * 100) : 0,
      hi_min: hiMin,
      hi_ratio: durationSec > 0 ? Math.round((hiSec / durationSec) * 100) : 0,
      start_time: data.start_time ? this.formatTime(data.start_time) : '--',
      end_time: data.end_time ? this.formatTime(data.end_time) : '--'
    }
  },

  /**
   * 合并多条训练记录
   * @param {Array} exercises 训练记录数组
   * @param {Number} backendTrimp 后端计算的TRIMP值
   */
  mergeExercises(exercises, backendTrimp = null) {
    const merged = {
      duration_sec: 0,
      zone1_sec: 0,
      zone2_sec: 0,
      zone3_sec: 0,
      zone4_sec: 0,
      zone5_sec: 0,
      calories: 0,
      distance_meters: 0,
      avg_hr: 0,
      max_hr: 0,
      start_time: exercises[0].start_time,
      end_time: exercises[exercises.length - 1].end_time,
      sport_type: exercises[0].sport_type
    }

    let totalAvgHr = 0
    exercises.forEach(ex => {
      merged.duration_sec += ex.duration_sec || 0
      merged.zone1_sec += ex.zone1_sec || 0
      merged.zone2_sec += ex.zone2_sec || 0
      merged.zone3_sec += ex.zone3_sec || 0
      merged.zone4_sec += ex.zone4_sec || 0
      merged.zone5_sec += ex.zone5_sec || 0
      merged.calories += ex.calories || 0
      merged.distance_meters += ex.distance_meters || 0
      merged.max_hr = Math.max(merged.max_hr, ex.max_hr || 0)
      totalAvgHr += (ex.avg_hr || 0) * (ex.duration_sec || 0)
    })

    if (merged.duration_sec > 0) {
      merged.avg_hr = Math.round(totalAvgHr / merged.duration_sec)
    }

    return this.processExerciseData(merged, exercises.length, backendTrimp)
  },

  /**
   * 计算 TRIMP（训练冲量）
   */
  calculateTrimp(data) {
    const zoneWeights = [1.0, 1.25, 1.5, 1.75, 2.0]
    const zones = [
      data.zone1_sec || 0,
      data.zone2_sec || 0,
      data.zone3_sec || 0,
      data.zone4_sec || 0,
      data.zone5_sec || 0
    ]

    let trimp = 0
    zones.forEach((zoneSec, i) => {
      trimp += (zoneSec / 60) * zoneWeights[i]
    })

    return trimp
  },

  /**
   * 计算脂肪燃烧克数（基于Polar/运动生理学方法）
   *
   * 原理：不同心率区间的脂肪供能比例不同
   * - Zone 1 (50-60% HRmax): 85% 脂肪供能（恢复区）
   * - Zone 2 (60-70% HRmax): 65% 脂肪供能（燃脂区）
   * - Zone 3 (70-80% HRmax): 45% 脂肪供能（有氧区）
   * - Zone 4 (80-90% HRmax): 25% 脂肪供能（乳酸阈值区）
   * - Zone 5 (90-100% HRmax): 10% 脂肪供能（最大摄氧区）
   *
   * 1克脂肪产生约7.7千卡能量
   */
  calculateFatBurn(calories, zone1Sec, zone2Sec, zone3Sec, zone4Sec, zone5Sec, totalZoneSec) {
    if (!calories || calories <= 0 || totalZoneSec <= 0) return 0

    // 各Zone脂肪供能比例（基于运动生理学研究）
    const fatRatios = {
      zone1: 0.85,  // 恢复区 - 85%脂肪供能
      zone2: 0.65,  // 燃脂区 - 65%脂肪供能
      zone3: 0.45,  // 有氧区 - 45%脂肪供能
      zone4: 0.25,  // 乳酸阈值区 - 25%脂肪供能
      zone5: 0.10   // 最大摄氧区 - 10%脂肪供能
    }

    // 计算加权平均脂肪供能比例
    const weightedFatRatio = (
      zone1Sec * fatRatios.zone1 +
      zone2Sec * fatRatios.zone2 +
      zone3Sec * fatRatios.zone3 +
      zone4Sec * fatRatios.zone4 +
      zone5Sec * fatRatios.zone5
    ) / totalZoneSec

    // 脂肪燃烧卡路里 = 总卡路里 × 脂肪供能比例
    const fatCalories = calories * weightedFatRatio

    // 脂肪燃烧克数 = 脂肪卡路里 / 7.7 (1g脂肪约产生7.7kcal)
    const fatGrams = fatCalories / 7.7

    return Math.round(fatGrams)
  },

  /**
   * 根据Polar返回的心率区间边界值判断平均心率所属区间
   *
   * 优先使用Polar API返回的zone_limits边界值（基于用户个人信息）
   * 如果没有边界值数据，则回退到使用各区间时间分布判断
   *
   * @param {Number} avgHr 平均心率
   * @param {Object} zoneLimits 区间边界值 {zone1: {lower, upper}, zone2: {...}, ...}
   * @param {Number} zone1Sec - zone5Sec 各区间时间（秒）
   */
  getHrZoneColorByLimits(avgHr, zoneLimits, zone1Sec, zone2Sec, zone3Sec, zone4Sec, zone5Sec) {
    if (!avgHr || avgHr <= 0) return ''

    // 优先使用Polar返回的心率区间边界值
    if (zoneLimits && Object.keys(zoneLimits).length > 0) {
      for (let i = 1; i <= 5; i++) {
        const zoneKey = `zone${i}`
        const limits = zoneLimits[zoneKey]
        if (limits && limits.lower !== undefined && limits.upper !== undefined) {
          // 检查平均心率是否在此区间内
          if (avgHr >= limits.lower && avgHr < limits.upper) {
            return `zone${i}-color`
          }
          // Zone5 的上限检查（心率可能超过上限）
          if (i === 5 && avgHr >= limits.lower) {
            return 'zone5-color'
          }
        }
      }
    }

    // 回退方案：使用各区间时间分布判断
    const zones = [
      { zone: 1, sec: zone1Sec || 0 },
      { zone: 2, sec: zone2Sec || 0 },
      { zone: 3, sec: zone3Sec || 0 },
      { zone: 4, sec: zone4Sec || 0 },
      { zone: 5, sec: zone5Sec || 0 }
    ]

    // 找出时间最长的区间
    const maxZone = zones.reduce((max, current) =>
      current.sec > max.sec ? current : max
    , zones[0])

    // 如果没有任何区间数据，返回空
    if (maxZone.sec <= 0) return ''

    return `zone${maxZone.zone}-color`
  },

  /**
   * 处理睡眠数据 - 使用分组API返回的数据，支持主睡眠+午睡显示
   * 如果当天没有数据，返回最近有数据的那天
   * @param {Object} sleepResponse 睡眠数据响应（分组版）
   * @param {Object} spo2Response 血氧数据响应（独立API）
   */
  processSleepData(sleepResponse, spo2Response, dashboardResponse) {
    if (!sleepResponse) return null

    // 查找最近有有效数据的记录（有segments且segments不为空）
    let dayData = null
    if (sleepResponse.records && sleepResponse.records.length > 0) {
      dayData = sleepResponse.records.find(r =>
        r.segments && r.segments.length > 0
      ) || sleepResponse.records[0]
    } else {
      dayData = sleepResponse
    }
    if (!dayData) return null

    // 过滤有效睡眠片段（sleep_score_delta 不为 null 的才计入每日睡眠，与 Oura App 一致）
    const validSegments = dayData.segments?.filter(s =>
      s.sleep_type === 'long_sleep' || s.sleep_score_delta !== null
    ) || []
    const validSegmentsCount = validSegments.length

    // 检查是否有主睡眠（long_sleep类型）
    const longSleep = validSegments.find(s => s.sleep_type === 'long_sleep')
    const hasMainSleep = !!longSleep

    // 如果没有主睡眠，找时长最长的有效片段作为代表
    let mainSleep = longSleep
    if (!mainSleep && validSegments.length > 0) {
      mainSleep = validSegments.reduce((longest, current) => {
        const longestMin = longest?.total_sleep_minutes || 0
        const currentMin = current?.total_sleep_minutes || 0
        return currentMin > longestMin ? current : longest
      }, validSegments[0])
    }
    if (!mainSleep && !validSegments.length) return null

    // 使用主睡眠/最长片段的详细数据
    const data = mainSleep || {}

    // 计算午睡增量并提取午睡时间和时长
    let napScoreBoost = 0
    const baseScore = dayData.base_score || 0
    let napBedtime = null
    let napWakeTime = null
    let napTotalMin = 0
    let secondLongestSegment = null

    if (validSegments.length > 1) {
      // 累加所有非主睡眠段的评分增量、时长（只计算有效片段）
      validSegments.forEach(segment => {
        if (segment !== mainSleep) {
          if (segment.sleep_score_delta) {
            napScoreBoost += segment.sleep_score_delta
          }
          // 累加时长
          napTotalMin += segment.total_sleep_minutes || 0
          // 记录第二长的片段（用于无主睡眠时显示）
          if (!secondLongestSegment || (segment.total_sleep_minutes || 0) > (secondLongestSegment.total_sleep_minutes || 0)) {
            secondLongestSegment = segment
          }
        }
      })
      // 记录午睡/第二段的时间
      if (hasMainSleep) {
        // 有主睡眠时，找第一个非主睡眠的有效片段
        const firstNap = validSegments.find(s => s.sleep_type !== 'long_sleep')
        if (firstNap) {
          napBedtime = firstNap.bedtime_start
          napWakeTime = firstNap.bedtime_end
        }
      } else if (secondLongestSegment) {
        // 无主睡眠时，用第二长的片段
        napBedtime = secondLongestSegment.bedtime_start
        napWakeTime = secondLongestSegment.bedtime_end
      }
    }

    // 判断是否有午睡/多段睡眠（使用有效片段数）
    const hasNap = hasMainSleep && validSegmentsCount > 1 && napScoreBoost > 0
    const hasMultipleSegments = !hasMainSleep && validSegmentsCount > 1

    // 主睡眠/最长片段时长
    const mainSleepMin = data.total_sleep_minutes || (data.total_sleep_duration ? Math.round(data.total_sleep_duration / 60) : 0)

    // 总时长（只计算有效片段，与 Oura App 一致）
    const totalMin = validSegments.reduce((sum, s) => sum + (s.total_sleep_minutes || 0), 0)

    // 格式化主睡眠时长
    const mainHours = Math.floor(mainSleepMin / 60)
    const mainMins = mainSleepMin % 60
    const mainSleepDuration = mainHours > 0 ? `${mainHours}h${mainMins}m` : `${mainMins}m`

    // 格式化午睡时长
    const napHours = Math.floor(napTotalMin / 60)
    const napMins = napTotalMin % 60
    const napDuration = napHours > 0 ? `${napHours}h${napMins}m` : `${napMins}m`

    // 格式化总时长（用于其他地方显示）
    const totalHours = Math.floor(totalMin / 60)
    const totalMins = totalMin % 60
    const totalDuration = `${totalHours}小时${totalMins}分`

    // 从独立的血氧API获取数据（匹配相同日期）
    let spo2Value = '--'
    let breathingDisturbance = '--'
    if (spo2Response && spo2Response.records) {
      const spo2Record = spo2Response.records.find(r => r.day === dayData.day)
      if (spo2Record) {
        spo2Value = spo2Record.spo2_percentage ? spo2Record.spo2_percentage.toFixed(1) : '--'
        breathingDisturbance = spo2Record.breathing_disturbance_index || '--'
      }
    }

    // 计算各指标的值（从主睡眠获取）
    const latencyMin = data.latency ? Math.round(data.latency / 60) : 0
    const restlessPeriods = data.restless_periods || 0
    const efficiency = data.efficiency || 0
    const hrv = data.average_hrv || null
    const hrAverage = data.average_heart_rate || null
    const hrLowest = data.lowest_heart_rate || null
    const breathingRate = data.average_breath || null

    // 睡眠阶段时长（只累加有效片段，与 Oura App 一致）
    let deepMin = 0
    let remMin = 0
    let lightMin = 0
    let awakeMin = 0

    if (validSegments.length > 0) {
      validSegments.forEach(segment => {
        // 分组API返回的是分钟数(deep_sleep_minutes)和秒数(deep_sleep_duration)
        deepMin += segment.deep_sleep_minutes || (segment.deep_sleep_duration ? Math.round(segment.deep_sleep_duration / 60) : 0)
        remMin += segment.rem_sleep_minutes || (segment.rem_sleep_duration ? Math.round(segment.rem_sleep_duration / 60) : 0)
        lightMin += segment.light_sleep_minutes || (segment.light_sleep_duration ? Math.round(segment.light_sleep_duration / 60) : 0)
        awakeMin += segment.awake_minutes || (segment.awake_time ? Math.round(segment.awake_time / 60) : 0)
      })
    }

    // 计算各阶段百分比（用于时间条展示）
    const totalSleepMin = deepMin + remMin + lightMin + awakeMin
    const deepPercent = totalSleepMin > 0 ? Math.round((deepMin / totalSleepMin) * 100) : 0
    const remPercent = totalSleepMin > 0 ? Math.round((remMin / totalSleepMin) * 100) : 0
    const lightPercent = totalSleepMin > 0 ? Math.round((lightMin / totalSleepMin) * 100) : 0
    const awakePercent = totalSleepMin > 0 ? Math.round((awakeMin / totalSleepMin) * 100) : 0

    // 睡眠阶段颜色（基于Oura官方建议范围）
    const deepColor = deepMin >= 60 ? 'green' : (deepMin >= 45 ? '' : 'orange')
    const remColor = remMin >= 90 ? 'green' : (remMin >= 60 ? '' : 'orange')
    const lightColor = ''
    const awakeColor = awakeMin <= 15 ? 'green' : (awakeMin <= 30 ? '' : 'orange')

    // 根据数值范围确定颜色类
    const latencyColor = latencyMin <= 15 ? 'green' : (latencyMin <= 30 ? 'orange' : 'red')
    const restlessColor = restlessPeriods < 10 ? 'green' : (restlessPeriods <= 20 ? 'orange' : 'red')
    const efficiencyColor = efficiency >= 85 ? 'green' : (efficiency >= 75 ? '' : 'orange')
    const hrvColor = hrv ? (hrv >= 40 ? 'green' : (hrv >= 20 ? '' : 'orange')) : ''
    const hrAverageColor = hrAverage ? (hrAverage < 55 ? 'green' : (hrAverage <= 65 ? '' : 'orange')) : ''
    const hrLowestColor = hrLowest ? (hrLowest < 50 ? 'green' : (hrLowest <= 60 ? '' : 'orange')) : ''
    const breathingColor = breathingRate ?
      (breathingRate >= 12 && breathingRate <= 16 ? 'green' :
       (breathingRate >= 10 && breathingRate <= 20 ? '' : 'orange')) : ''

    // 获取 dashboard 的睡眠评分（Oura App 综合评分）
    const dashboardSleepScore = dashboardResponse?.oura_yesterday?.sleep_score

    // 计算第二段睡眠时长（用于无主睡眠时显示）
    const secondSleepMin = secondLongestSegment?.total_sleep_minutes || 0
    const secondHours = Math.floor(secondSleepMin / 60)
    const secondMins = secondSleepMin % 60
    const secondSleepDuration = secondHours > 0 ? `${secondHours}h${secondMins}m` : `${secondMins}m`

    return {
      // 基本数据
      day: dayData.day || '--',
      // 优先使用 dashboard 的 sleep_score（Oura App 综合评分），
      // 回退到 summary_score、base_score、最长片段 score
      score: dashboardSleepScore ?? dayData.summary_score ?? dayData.base_score ?? (mainSleep?.score || 0),
      baseScore: baseScore,
      napScoreBoost: napScoreBoost > 0 ? napScoreBoost : 0,
      hasNap: hasNap,
      hasMainSleep: hasMainSleep,
      hasMultipleSegments: hasMultipleSegments,
      segmentsCount: validSegmentsCount,
      total_duration: totalDuration,
      efficiency: efficiency,
      efficiencyColor: efficiencyColor,

      // 睡眠阶段（秒转分钟，带颜色标识和百分比）
      deep_min: deepMin,
      deepColor: deepColor,
      deepPercent: deepPercent,
      rem_min: remMin,
      remColor: remColor,
      remPercent: remPercent,
      light_min: lightMin,
      lightColor: lightColor,
      lightPercent: lightPercent,
      awake_min: awakeMin,
      awakeColor: awakeColor,
      awakePercent: awakePercent,

      // 心率与HRV（带颜色标识）
      hrv: hrv || '--',
      hrvColor: hrvColor,
      hr_average: hrAverage || '--',
      hrAverageColor: hrAverageColor,
      hr_lowest: hrLowest || '--',
      hrLowestColor: hrLowestColor,

      // 呼吸（带颜色标识）
      breathing_rate: breathingRate ? breathingRate.toFixed(2) : '--',
      breathingColor: breathingColor,

      // 主睡眠/最长片段时间和时长
      bedtime: data.bedtime_start ? this.formatTime(data.bedtime_start) : '--',
      wake_time: data.bedtime_end ? this.formatTime(data.bedtime_end) : '--',
      main_sleep_duration: mainSleepDuration,

      // 午睡/第二段时间和时长（如果有）
      nap_bedtime: napBedtime ? this.formatTime(napBedtime) : null,
      nap_wake_time: napWakeTime ? this.formatTime(napWakeTime) : null,
      nap_duration: napDuration,
      second_sleep_duration: secondSleepDuration,

      // 睡眠质量指标（带颜色标识，来自主睡眠/最长片段）
      latency_min: latencyMin,
      latencyColor: latencyColor,
      time_in_bed: data.time_in_bed ? Math.round(data.time_in_bed / 60) : 0,
      restless_periods: restlessPeriods,
      restlessColor: restlessColor,

      // 睡眠类型（区分正常睡眠和碎片化睡眠，使用有效片段数）
      sleep_type: hasMainSleep
        ? (hasNap ? '主睡眠+午休' : '主睡眠')
        : `${validSegmentsCount}段碎片睡眠`,

      // 血氧与呼吸紊乱（从独立的spo2 API获取）
      spo2: spo2Value,
      breathing_disturbance: breathingDisturbance,

      // 体温偏差（从主睡眠数据中获取）
      temperature_deviation: data.embedded_readiness?.temperature_deviation,

      // 贡献因子 - 优先使用 dashboard API 的 daily_sleep 贡献度（Oura App 综合评分）
      contributors: this._getContributors(data, sleepResponse, dashboardResponse),

      // 标记 contributors 数据来源
      contributorsSource: this._getContributorsSource(data, dashboardResponse),

      // 内嵌准备度数据
      embedded_readiness: data.embedded_readiness || null
    }
  },

  /**
   * 获取睡眠贡献因子 - 优先 dashboard daily_sleep 数据
   */
  _getContributors(currentData, sleepResponse, dashboardResponse) {
    // 优先使用 dashboard API 的 daily_sleep 贡献度（Oura App 综合评分）
    const ouraYesterday = dashboardResponse?.oura_yesterday
    if (ouraYesterday?.sleep_contributor_deep_sleep != null) {
      return {
        deep_sleep: ouraYesterday.sleep_contributor_deep_sleep,
        efficiency: ouraYesterday.sleep_contributor_efficiency,
        latency: ouraYesterday.sleep_contributor_latency,
        rem_sleep: ouraYesterday.sleep_contributor_rem_sleep,
        restfulness: ouraYesterday.sleep_contributor_restfulness,
        timing: ouraYesterday.sleep_contributor_timing,
        total_sleep: ouraYesterday.sleep_contributor_total_sleep
      }
    }

    // 回退：使用当天睡眠数据的 contributors（long_sleep 才有）
    if (currentData.contributors && Object.keys(currentData.contributors).length > 0) {
      return currentData.contributors
    }

    // 最后回退：从历史记录中查找最近的 long_sleep 获取 contributors
    if (sleepResponse?.records) {
      for (const record of sleepResponse.records) {
        if (record.segments) {
          const longSleep = record.segments.find(s =>
            s.sleep_type === 'long_sleep' && s.contributors
          )
          if (longSleep?.contributors) {
            return longSleep.contributors
          }
        }
      }
    }

    return null
  },

  /**
   * 获取 contributors 数据来源
   */
  _getContributorsSource(currentData, dashboardResponse) {
    const ouraYesterday = dashboardResponse?.oura_yesterday
    if (ouraYesterday?.sleep_contributor_deep_sleep != null) {
      return 'daily'  // 每日综合评分
    }
    if (currentData.contributors && Object.keys(currentData.contributors).length > 0) {
      return 'main'   // 主睡眠
    }
    return 'history'  // 历史数据
  },

  /**
   * 处理准备度数据 - 支持午睡增量显示
   * 如果当天没有数据，返回最近有数据的那天
   */
  processReadinessData(response, sleepData) {
    if (!response) return null

    // 查找最近有有效数据的记录（有score值）
    let data = null
    if (response.records && response.records.length > 0) {
      data = response.records.find(r => r.score !== null && r.score !== undefined) || response.records[0]
    } else {
      data = response
    }
    if (!data) return null

    // 处理体温偏差显示和颜色
    let tempDevDisplay = '--'
    let tempDevColor = ''
    if (typeof data.temperature_deviation === 'number') {
      tempDevDisplay = (data.temperature_deviation >= 0 ? '+' : '') + data.temperature_deviation.toFixed(2)
      // 体温偏差: ±0.2内正常(绿), ±0.5内一般, 超出警告
      const absTempDev = Math.abs(data.temperature_deviation)
      tempDevColor = absTempDev <= 0.2 ? 'green' : (absTempDev <= 0.5 ? '' : 'orange')
    }

    // 处理体温趋势偏差显示
    let tempTrendDisplay = '--'
    if (typeof data.temperature_trend_deviation === 'number') {
      tempTrendDisplay = (data.temperature_trend_deviation >= 0 ? '+' : '') + data.temperature_trend_deviation.toFixed(2)
    }

    // 从睡眠数据获取实际的心率和HRV值（而非贡献因子评分）
    const actualRestingHr = sleepData?.hr_lowest || '--'
    const actualHrv = sleepData?.hrv || '--'

    // 准备度评分和午睡增量
    const score = data.score || 0
    const baseScore = data.base_score || score
    const napBoost = data.nap_boost || 0
    const hasNap = napBoost > 0

    // 准备度评分颜色: ≥85好, 70-85正常, <70偏低
    const scoreColor = score >= 85 ? 'green' : (score >= 70 ? '' : 'orange')

    // 恢复指数颜色 (0-100评分): ≥80好, 60-80正常, <60偏低
    const recoveryIndex = data.recovery_index || 0
    const recoveryColor = recoveryIndex >= 80 ? 'green' : (recoveryIndex >= 60 ? '' : 'orange')

    // 各贡献因子颜色 (0-100评分): ≥80好, 60-80正常, <60偏低
    const getContributorColor = (value) => {
      if (!value || value === '--') return ''
      return value >= 80 ? 'green' : (value >= 60 ? '' : 'orange')
    }

    return {
      // 基本数据
      day: data.day || '--',
      score: score,
      baseScore: baseScore,
      napBoost: napBoost,
      hasNap: hasNap,
      scoreColor: scoreColor,

      // 核心指标 - 直接使用API字段（贡献因子评分 0-100）
      temperature_deviation: tempDevDisplay,
      tempDevColor: tempDevColor,
      temperature_trend_deviation: tempTrendDisplay,
      activity_balance: data.activity_balance || '--',
      activityBalanceColor: getContributorColor(data.activity_balance),
      body_temperature: data.body_temperature,  // 保持 null，不转为 '--'，便于雷达图过滤
      bodyTempColor: getContributorColor(data.body_temperature),
      hrv_balance: data.hrv_balance || '--',
      hrvBalanceColor: getContributorColor(data.hrv_balance),
      previous_day_activity: data.previous_day_activity || '--',
      prevActivityColor: getContributorColor(data.previous_day_activity),
      previous_night: data.previous_night || '--',
      prevNightColor: getContributorColor(data.previous_night),
      recovery_index: recoveryIndex,
      recoveryColor: recoveryColor,
      resting_heart_rate: data.resting_heart_rate || '--',
      restingHrColor: getContributorColor(data.resting_heart_rate),
      sleep_balance: data.sleep_balance || '--',
      sleepBalanceColor: getContributorColor(data.sleep_balance),
      sleep_regularity: data.sleep_regularity || '--',
      sleepRegularityColor: getContributorColor(data.sleep_regularity),

      // 实际数值（来自睡眠数据）
      resting_hr: actualRestingHr,
      hrv: actualHrv
    }
  },

  /**
   * 处理活动数据 - 直接使用API返回的所有字段
   * 如果当天没有数据，返回最近有数据的那天
   */
  processActivityData(response) {
    if (!response) return null

    // 查找最近有有效数据的记录（有score值或steps值）
    let data = null
    if (response.records && response.records.length > 0) {
      data = response.records.find(r =>
        (r.score !== null && r.score !== undefined) || (r.steps !== null && r.steps > 0)
      ) || response.records[0]
    } else {
      data = response
    }
    if (!data) return null

    // 活动时间（秒转分钟）
    const highMin = data.high_activity_time ? Math.round(data.high_activity_time / 60) : 0
    const mediumMin = data.medium_activity_time ? Math.round(data.medium_activity_time / 60) : 0
    const lowMin = data.low_activity_time ? Math.round(data.low_activity_time / 60) : 0
    // 总活动时间：只计算中高强度（与Oura App一致）
    const totalActivityMin = highMin + mediumMin

    // 久坐时间（秒转分钟）
    const sedentaryMin = data.sedentary_time ? Math.round(data.sedentary_time / 60) : 0

    // 计算各指标颜色
    // 活动评分: ≥85好, 70-85正常, <70偏低
    const score = data.score || 0
    const scoreColor = score >= 85 ? 'green' : (score >= 70 ? '' : 'orange')

    // 步数: ≥10000好, 5000-10000正常, <5000偏少
    const steps = data.steps || 0
    const stepsColor = steps >= 10000 ? 'green' : (steps >= 5000 ? '' : 'orange')

    // 活动卡路里: 达到或超过目标为好
    const activeCalories = data.active_calories || 0
    const targetCalories = data.target_calories || 500
    const caloriesColor = activeCalories >= targetCalories ? 'green' : (activeCalories >= targetCalories * 0.7 ? '' : 'orange')

    // 中高强度活动: ≥60分钟优秀, 30-60正常, <30不足
    const totalActivityColor = totalActivityMin >= 60 ? 'green' : (totalActivityMin >= 30 ? '' : 'orange')

    // 高强度活动: ≥30分钟好, 15-30正常
    const highColor = highMin >= 30 ? 'green' : (highMin >= 15 ? '' : '')

    // 中强度活动: ≥30分钟好
    const mediumColor = mediumMin >= 30 ? 'green' : ''

    // 久坐时间: <300分钟(5小时)好, 300-480(5-8小时)正常, >480(8小时)偏多
    const sedentaryColor = sedentaryMin < 300 ? 'green' : (sedentaryMin <= 480 ? '' : 'orange')

    // 不活跃警告: 0次好, 1-3次正常, >3次偏多
    const inactivityAlerts = data.inactivity_alerts || 0
    const alertsColor = inactivityAlerts === 0 ? 'green' : (inactivityAlerts <= 3 ? '' : 'orange')

    // 平均MET: ≥1.5好(较活跃), 1.2-1.5正常, <1.2久坐为主
    const avgMet = data.average_met_minutes || 0
    const metColor = avgMet >= 1.5 ? 'green' : (avgMet >= 1.2 ? '' : 'orange')

    // 步数进度（相对于10000步目标）
    const stepsProgress = Math.round(Math.min((steps / 10000) * 100, 100))

    // 久坐小时
    const sedentaryHours = Math.round(sedentaryMin / 60 * 10) / 10

    // 步数显示格式（简化大数字）
    let stepsDisplay = steps.toString()
    let stepsUnit = ''
    if (steps >= 10000) {
      stepsDisplay = (steps / 10000).toFixed(1)
      stepsUnit = '万'
    } else if (steps >= 1000) {
      stepsDisplay = (steps / 1000).toFixed(1)
      stepsUnit = 'k'
    }

    return {
      // 基本数据
      day: data.day || '--',
      score: score,
      scoreColor: scoreColor,

      // 步数与距离
      steps: steps,
      stepsColor: stepsColor,
      stepsProgress: stepsProgress,
      stepsDisplay: stepsDisplay,
      stepsUnit: stepsUnit,
      distance: data.equivalent_walking_distance || 0,

      // 卡路里
      active_calories: activeCalories,
      caloriesColor: caloriesColor,
      target_calories: targetCalories,
      total_calories: data.total_calories || 0,

      // 活动强度分布（秒转分钟）
      total_activity_min: totalActivityMin,
      totalActivityColor: totalActivityColor,
      high_min: highMin,
      highColor: highColor,
      medium_min: mediumMin,
      mediumColor: mediumColor,
      low_min: lowMin,

      // 时间分配（秒转分钟）
      sedentary_min: sedentaryMin,
      sedentary_hours: sedentaryHours,
      sedentaryColor: sedentaryColor,
      rest_min: data.resting_time ? Math.round(data.resting_time / 60) : 0,
      non_wear_min: data.non_wear_time ? Math.round(data.non_wear_time / 60) : 0,

      // 全天指标
      inactivity_alerts: inactivityAlerts,
      alertsColor: alertsColor,
      average_met: avgMet ? avgMet.toFixed(2) : '--',
      metColor: metColor,

      // 目标
      target_meters: data.target_meters || 10000,
      meters_to_target: data.meters_to_target || 0,

      // 贡献因子 - 直接使用API返回的contributors对象
      contributors: data.contributors || {}
    }
  },

  /**
   * 处理血氧数据 - 查找最近有效数据
   * @param {Object} response 血氧数据响应
   */
  processSpo2Data(response) {
    if (!response || !response.records || response.records.length === 0) return null

    // 查找最近有有效数据的记录（血氧值不为null）
    const validRecord = response.records.find(r =>
      r.spo2_percentage !== null && r.spo2_percentage !== undefined
    )

    if (!validRecord) return null

    return {
      day: validRecord.day,
      spo2: validRecord.spo2_percentage ? validRecord.spo2_percentage.toFixed(1) : '--',
      breathing_disturbance: validRecord.breathing_disturbance_index || '--'
    }
  },

  /**
   * 处理压力数据 - 与准备度日期保持一致
   * @param {Object} response 压力数据响应
   * @param {string} referenceDay 参考日期（通常是准备度的日期），确保显示一致
   */
  processStressData(response, referenceDay) {
    if (!response || !response.records || response.records.length === 0) return null

    // 优先使用参考日期对应的记录（与准备度保持一致）
    // 如果没有参考日期或找不到对应记录，再查找最近有有效数据的记录
    let validRecord = null
    if (referenceDay) {
      validRecord = response.records.find(r => r.day === referenceDay)
    }

    // 如果没找到参考日期的记录，回退到查找有效数据的记录
    if (!validRecord) {
      validRecord = response.records.find(r =>
        r.day_summary !== null || r.stressed_minutes > 0 || r.restored_minutes > 0
      )
    }

    if (!validRecord) return null

    // 压力/恢复分钟数
    const stressedMin = validRecord.stressed_minutes || 0
    const restoredMin = validRecord.restored_minutes || 0

    // 格式化时间显示（如果没有分钟数则不显示）
    const formatDuration = (totalMin) => {
      const hours = Math.floor(totalMin / 60)
      const mins = totalMin % 60
      if (hours > 0 && mins > 0) {
        return `${hours}h${mins}m`
      } else if (hours > 0) {
        return `${hours}h`
      } else {
        return `${mins}m`
      }
    }

    // 日总结映射和颜色
    const summaryMap = {
      'normal': '正常',
      'stressful': '压力大',
      'restored': '已恢复'
    }
    const summaryColorMap = {
      'normal': '',
      'stressful': 'orange',
      'restored': 'green'
    }

    // 计算压力和恢复的百分比（用于平衡条展示）
    const totalMin = stressedMin + restoredMin
    const stressPercent = totalMin > 0 ? Math.round((stressedMin / totalMin) * 100) : 50
    const recoveryPercent = totalMin > 0 ? Math.round((restoredMin / totalMin) * 100) : 50

    return {
      day: validRecord.day,
      stressed_min: stressedMin,
      restored_min: restoredMin,
      stressed_display: formatDuration(stressedMin),
      restored_display: formatDuration(restoredMin),
      stress_percent: stressPercent,
      recovery_percent: recoveryPercent,
      day_summary: summaryMap[validRecord.day_summary] || validRecord.day_summary || '--',
      summaryColor: summaryColorMap[validRecord.day_summary] || ''
    }
  },

  /**
   * 处理本周数据 - 直接使用API返回的所有字段
   * @param {Object} data 本周数据（来自 /api/v1/training/weekly）
   * @param {Object} historyData 训练历史数据（用于计算上一周）
   */
  processWeeklyData(data, historyData) {
    // 如果本周有数据，直接使用
    if (data) {
      return this._buildWeeklyResult(data, false)
    }

    // 本周没有数据，尝试从历史数据计算上一周
    if (historyData?.exercises?.length > 0) {
      const lastWeekData = this._calculateLastWeekFromHistory(historyData.exercises)
      if (lastWeekData) {
        return this._buildWeeklyResult(lastWeekData, true)
      }
    }

    return null
  },

  /**
   * 从历史训练记录计算上一周数据
   */
  _calculateLastWeekFromHistory(exercises) {
    // 计算上周的日期范围（周一到周日）
    const now = new Date()
    const hkOffset = 8 * 60
    const hkTime = new Date(now.getTime() + (hkOffset + now.getTimezoneOffset()) * 60000)

    // 本周一
    const thisWeekMonday = new Date(hkTime)
    thisWeekMonday.setDate(hkTime.getDate() - hkTime.getDay() + 1)
    thisWeekMonday.setHours(0, 0, 0, 0)

    // 上周一
    const lastWeekMonday = new Date(thisWeekMonday)
    lastWeekMonday.setDate(lastWeekMonday.getDate() - 7)

    // 上周日
    const lastWeekSunday = new Date(lastWeekMonday)
    lastWeekSunday.setDate(lastWeekSunday.getDate() + 6)
    lastWeekSunday.setHours(23, 59, 59, 999)

    // 过滤上一周的训练记录
    const lastWeekExercises = exercises.filter(e => {
      if (!e.start_time) return false
      const exerciseDate = new Date(e.start_time)
      return exerciseDate >= lastWeekMonday && exerciseDate <= lastWeekSunday
    })

    if (lastWeekExercises.length === 0) return null

    // 计算汇总数据
    let totalMin = 0
    let zone2Min = 0
    let hiMin = 0
    const trainingDays = new Set()

    lastWeekExercises.forEach(e => {
      const duration = e.duration_sec ? Math.round(e.duration_sec / 60) : 0
      totalMin += duration
      zone2Min += e.zone2_min || Math.round((e.zone2_sec || 0) / 60)
      hiMin += e.hi_min || Math.round(((e.zone4_sec || 0) + (e.zone5_sec || 0)) / 60)

      // 记录训练日期
      if (e.start_time) {
        trainingDays.add(e.start_time.split('T')[0])
      }
    })

    return {
      zone2_min: zone2Min,
      training_days: trainingDays.size,
      total_min: totalMin,
      hi_min: hiMin,
      weekly_trimp: 0,  // 历史数据无法计算TRIMP
      week_start_date: formatLocalDate(lastWeekMonday),
      isLastWeek: true
    }
  },

  /**
   * 构建周数据结果对象
   */
  _buildWeeklyResult(data, isLastWeek = false) {
    const zone2Min = data.zone2_min || 0
    const trainingDays = data.training_days || 0
    const totalMin = data.total_duration_min || data.total_min || 0
    const hiMin = data.hi_min || 0
    const weeklyTrimp = data.weekly_trimp || 0

    // 估算脂肪燃烧克数
    const estimatedCalories = totalMin * 8
    const zone2Ratio = totalMin > 0 ? zone2Min / totalMin : 0.8
    const hiRatio = totalMin > 0 ? hiMin / totalMin : 0.05
    const otherRatio = 1 - zone2Ratio - hiRatio
    const avgFatRatio = zone2Ratio * 0.65 + hiRatio * 0.20 + otherRatio * 0.50
    const weeklyFatBurn = Math.round((estimatedCalories * avgFatRatio) / 7.7)

    // Zone2目标进度（250分钟为目标）
    const zone2Progress = Math.round(Math.min((zone2Min / 250) * 100, 100) * 10) / 10

    return {
      week_start_date: data.week_start_date || '--',
      fat_burn: weeklyFatBurn,
      training_days: trainingDays,
      rest_days: data.rest_days || (7 - trainingDays),
      total_min: totalMin,
      zone2_min: zone2Min,
      zone2_progress: zone2Progress,
      hi_min: hiMin,
      weekly_trimp: typeof weeklyTrimp === 'number' ? weeklyTrimp.toFixed(1) : weeklyTrimp,
      avg_trimp: trainingDays > 0 ? (weeklyTrimp / trainingDays).toFixed(1) : 0,
      isLastWeek: isLastWeek  // 标记是否为上一周数据
    }
  },

  /**
   * 格式化时间
   */
  formatTime(isoString) {
    if (!isoString) return '--'
    try {
      const date = new Date(isoString)
      const hours = date.getHours().toString().padStart(2, '0')
      const minutes = date.getMinutes().toString().padStart(2, '0')
      return `${hours}:${minutes}`
    } catch (e) {
      return '--'
    }
  },

  /**
   * 计算晨间检查数据
   * 基于Oura使用方法论，确定行动信号和警报
   * @param {Object} sleepData 今天的睡眠数据
   * @param {Object} readinessData 今天的准备度数据
   * @param {Object} sleepResponse 7天睡眠原始响应（用于计算差值）
   * @param {Object} readinessResponse 7天准备度原始响应（用于计算差值）
   */
  computeMorningCheckData(sleepData, readinessData, sleepResponse, readinessResponse) {
    const result = {
      readinessLevel: 'level-medium',
      actionAdvice: { title: '良好', desc: '状态良好，按计划进行' },
      sleepLevel: 'level-medium',
      sleepAdvice: { title: '良好', desc: '睡眠质量正常' },
      alertType: '',
      hrvAlert: false,
      rhrAlert: false,
      deepAlert: false,
      hrvDelta: null,
      rhrDelta: null,
      deepDelta: null,
      remDelta: null,
      morningAlert: null
    }

    if (!readinessData) return result

    const score = readinessData.score || 0
    const hrv = typeof readinessData.hrv === 'number' ? readinessData.hrv : null
    const rhr = typeof readinessData.resting_hr === 'number' ? readinessData.resting_hr : null
    const deepMin = sleepData?.deep_min || 0
    const remMin = sleepData?.rem_min || 0
    const tempDev = typeof readinessData.temperature_deviation === 'string'
      ? parseFloat(readinessData.temperature_deviation)
      : null

    // 1. 确定准备度等级和行动建议
    // 基于Oura官方分档: ≥85 Optimal, 70-84 Good, <70 Pay Attention
    if (score >= 85) {
      result.readinessLevel = 'level-high'
      result.actionAdvice = {
        title: '最佳',
        desc: '状态极佳，适合高强度训练'
      }
    } else if (score >= 70) {
      result.readinessLevel = 'level-medium'
      result.actionAdvice = {
        title: '良好',
        desc: '状态良好，按计划进行'
      }
    } else {
      result.readinessLevel = 'level-low'
      result.actionAdvice = {
        title: '需注意',
        desc: '建议轻度活动或休息'
      }
    }

    // 1.5 确定睡眠等级和评价
    // 基于Oura官方分档: ≥85 Optimal, 70-84 Good, <70 Pay Attention
    const sleepScore = sleepData?.score || 0
    if (sleepScore >= 85) {
      result.sleepLevel = 'level-high'
      result.sleepAdvice = {
        title: '最佳',
        desc: '睡眠充足，恢复良好'
      }
    } else if (sleepScore >= 70) {
      result.sleepLevel = 'level-medium'
      result.sleepAdvice = {
        title: '良好',
        desc: '睡眠质量正常'
      }
    } else if (sleepScore > 0) {
      result.sleepLevel = 'level-low'
      result.sleepAdvice = {
        title: '需注意',
        desc: '建议改善睡眠习惯'
      }
    }

    // 2. 检测核心指标警报
    // HRV警报：低于20ms表示恢复不佳
    if (hrv !== null && hrv < 20) {
      result.hrvAlert = true
    }

    // RHR警报：高于65bpm（个体差异较大，这里用通用阈值）
    // 更重要的是与个人基线相比的变化，暂时用绝对值
    if (rhr !== null && rhr > 65) {
      result.rhrAlert = true
    }

    // 深睡眠警报：低于45分钟
    if (deepMin < 45) {
      result.deepAlert = true
    }

    // 3. 生成最重要的晨间警报（只显示一条最关键的）
    const criticalAlerts = []

    // 体温异常（最高优先级 - 可能生病）
    if (tempDev !== null && Math.abs(tempDev) > 0.5) {
      criticalAlerts.push({
        priority: 1,
        type: 'danger',
        icon: '🌡️',
        message: `体温偏差${tempDev > 0 ? '+' : ''}${tempDev.toFixed(2)}°，注意身体状况`
      })
    }

    // HRV过低（第二优先级）
    if (hrv !== null && hrv < 15) {
      criticalAlerts.push({
        priority: 2,
        type: 'danger',
        icon: '💓',
        message: `HRV仅${hrv}ms，身体恢复不佳，建议休息`
      })
    }

    // 准备度极低
    if (score < 60) {
      criticalAlerts.push({
        priority: 3,
        type: 'warning',
        icon: '🔋',
        message: `准备度${score}分偏低，建议今日减少强度`
      })
    }

    // 深睡眠严重不足
    if (deepMin < 30) {
      criticalAlerts.push({
        priority: 4,
        type: 'warning',
        icon: '🌙',
        message: `深睡眠仅${deepMin}分钟，睡眠质量需关注`
      })
    }

    // 选择最高优先级的警报
    if (criticalAlerts.length > 0) {
      criticalAlerts.sort((a, b) => a.priority - b.priority)
      const topAlert = criticalAlerts[0]
      result.morningAlert = {
        icon: topAlert.icon,
        message: topAlert.message
      }
      result.alertType = topAlert.type
    }

    // 4. 计算与昨天的差值
    const yesterdayData = this.extractYesterdayData(sleepResponse, readinessResponse)

    if (yesterdayData) {
      // HRV差值：增加是好事
      if (hrv !== null && yesterdayData.hrv !== null) {
        const delta = hrv - yesterdayData.hrv
        if (delta !== 0) {
          result.hrvDelta = {
            value: Math.abs(delta),
            direction: delta > 0 ? 'up' : 'down'  // up=好（HRV增加），down=差
          }
        }
      }

      // RHR差值：减少是好事（方向相反）
      if (rhr !== null && yesterdayData.rhr !== null) {
        const delta = rhr - yesterdayData.rhr
        if (delta !== 0) {
          result.rhrDelta = {
            value: Math.abs(delta),
            direction: delta < 0 ? 'up' : 'down'  // up=好（RHR减少），down=差
          }
        }
      }

      // 深睡眠差值：增加是好事
      if (deepMin > 0 && yesterdayData.deepMin !== null) {
        const delta = deepMin - yesterdayData.deepMin
        if (delta !== 0) {
          result.deepDelta = {
            value: Math.abs(delta),
            direction: delta > 0 ? 'up' : 'down'
          }
        }
      }

      // REM差值：增加是好事
      if (remMin > 0 && yesterdayData.remMin !== null) {
        const delta = remMin - yesterdayData.remMin
        if (delta !== 0) {
          result.remDelta = {
            value: Math.abs(delta),
            direction: delta > 0 ? 'up' : 'down'
          }
        }
      }
    }

    return result
  },

  /**
   * 从7天数据中提取昨天的核心指标
   */
  extractYesterdayData(sleepResponse, readinessResponse) {
    // 从睡眠数据获取昨天的深睡眠、REM、HRV、RHR
    let yesterdayHrv = null
    let yesterdayRhr = null
    let yesterdayDeepMin = null
    let yesterdayRemMin = null

    // 睡眠数据：找到第二条有效记录（今天是第一条，昨天是第二条）
    if (sleepResponse && sleepResponse.records && sleepResponse.records.length >= 2) {
      // 找到今天的日期
      const todayRecord = sleepResponse.records.find(r => r.segments && r.segments.length > 0)
      if (todayRecord) {
        const todayDate = todayRecord.day
        // 找到日期不同的下一条有效记录
        const yesterdayRecord = sleepResponse.records.find(r =>
          r.day !== todayDate && r.segments && r.segments.length > 0
        )

        if (yesterdayRecord) {
          // 找主睡眠片段
          const mainSleep = yesterdayRecord.segments?.find(s => s.sleep_type === 'long_sleep')
                          || yesterdayRecord.segments?.[0]
          if (mainSleep) {
            yesterdayHrv = mainSleep.average_hrv || null
            yesterdayRhr = mainSleep.lowest_heart_rate || null
            // 分组API返回的是分钟数(deep_min/rem_min)，老API返回秒数
            yesterdayDeepMin = mainSleep.deep_min ||
                              (mainSleep.deep_sleep_duration ? Math.round(mainSleep.deep_sleep_duration / 60) : null)
            yesterdayRemMin = mainSleep.rem_min ||
                             (mainSleep.rem_sleep_duration ? Math.round(mainSleep.rem_sleep_duration / 60) : null)
          }
        }
      }
    }

    // 如果有任何数据，返回结果
    if (yesterdayHrv !== null || yesterdayRhr !== null ||
        yesterdayDeepMin !== null || yesterdayRemMin !== null) {
      return {
        hrv: yesterdayHrv,
        rhr: yesterdayRhr,
        deepMin: yesterdayDeepMin,
        remMin: yesterdayRemMin
      }
    }

    return null
  },

  /**
   * 生成健康状态一句话总结
   * 综合考虑关键指标（深睡眠、HRV、恢复指数），而不仅依赖评分
   */
  generateHealthSummary(sleepData, readinessData, activityData, trainingData) {
    const summaries = []

    // 睡眠评估 - 综合评分和深睡眠时长
    if (sleepData) {
      const score = sleepData.score || 0
      const deepMin = sleepData.deep_min || 0

      // 深睡眠是睡眠质量的核心指标，优先判断
      if (deepMin < 45) {
        summaries.push('深睡眠严重不足')
      } else if (deepMin < 60) {
        summaries.push('深睡眠偏少')
      } else if (score >= 85) {
        summaries.push('睡眠质量优秀')
      } else if (score >= 70) {
        summaries.push('睡眠状态尚可')
      } else {
        summaries.push('睡眠需要关注')
      }
    }

    // 准备度评估 - 综合评分和恢复指数
    if (readinessData) {
      const score = readinessData.score || 0
      const recoveryIndex = readinessData.recovery_index || 0
      const hrv = typeof readinessData.hrv === 'number' ? readinessData.hrv : 0

      // 恢复指数和HRV是恢复状态的核心指标
      if (recoveryIndex < 50 || (hrv > 0 && hrv < 20)) {
        summaries.push('恢复欠佳')
      } else if (recoveryIndex < 60 || (hrv > 0 && hrv < 30)) {
        summaries.push('恢复一般')
      } else if (score >= 85 && recoveryIndex >= 80) {
        summaries.push('身体状态极佳')
      } else if (score >= 70 && recoveryIndex >= 60) {
        summaries.push('恢复正常')
      } else {
        summaries.push('建议多休息')
      }
    }

    // 活动评估
    if (activityData && activityData.score) {
      if (activityData.score >= 85) {
        summaries.push('活动达标')
      } else if (activityData.score < 60) {
        summaries.push('活动量偏少')
      }
    }

    // 训练评估
    if (trainingData) {
      if (trainingData.zone2_min >= 45) {
        summaries.push('Zone2训练充足')
      }
    }

    if (summaries.length === 0) {
      return '数据加载中，请稍候...'
    }

    return summaries.slice(0, 2).join('，')
  },

  /**
   * 绘制核心评分圆环
   */
  drawScoreRings() {
    const { sleepData, readinessData, activityData } = this.data

    // 睡眠评分圆环 - 靛蓝色（夜晚、深睡眠的意象）
    if (sleepData && sleepData.score) {
      this.drawRing('sleepRing', sleepData.score, '#7986CB')
    }

    // 准备度评分圆环 - 琥珀金色（能量、电池的意象，高对比度）
    if (readinessData && readinessData.score) {
      this.drawRing('readinessRing', readinessData.score, '#FFD54F')
    }

    // 活动评分圆环 - 青绿色（运动、健康的意象）
    if (activityData && activityData.score) {
      this.drawRing('activityRing', activityData.score, '#4DB6AC')
    }
  },

  /**
   * 绘制单个圆环（大号版本）
   * @param {string} canvasId Canvas ID
   * @param {number} score 分数 (0-100)
   * @param {string} color 圆环颜色
   */
  drawRing(canvasId, score, color) {
    const ctx = wx.createCanvasContext(canvasId, this)
    // 180rpx ≈ 90px
    const centerX = 45
    const centerY = 45
    const radius = 38
    const lineWidth = 8
    const percent = Math.min(score, 100) / 100

    // 清除画布
    ctx.clearRect(0, 0, 90, 90)

    // 绘制背景圆环
    ctx.setLineWidth(lineWidth)
    ctx.setStrokeStyle('rgba(255, 255, 255, 0.3)')
    ctx.setLineCap('round')
    ctx.beginPath()
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI)
    ctx.stroke()

    // 绘制进度圆环（带渐变效果模拟）
    if (percent > 0) {
      ctx.setLineWidth(lineWidth)
      ctx.setStrokeStyle(color)
      ctx.setLineCap('round')
      ctx.setShadow(0, 0, 8, color)  // 添加发光效果
      ctx.beginPath()
      // 从顶部开始绘制（-90度）
      const startAngle = -Math.PI / 2
      const endAngle = startAngle + (2 * Math.PI * percent)
      ctx.arc(centerX, centerY, radius, startAngle, endAngle)
      ctx.stroke()
    }

    ctx.draw()
  },

  /**
   * 绘制雷达图
   */
  drawRadarCharts() {
    const { sleepData, readinessData, activityData } = this.data

    // 绘制睡眠贡献因子雷达图
    if (sleepData && sleepData.contributors) {
      this.drawRadar('sleepRadar', [
        { label: '深睡', value: sleepData.contributors.deep_sleep || 0 },
        { label: '时长', value: sleepData.contributors.total_sleep || 0 },
        { label: '时机', value: sleepData.contributors.timing || 0 },
        { label: '延迟', value: sleepData.contributors.latency || 0 },
        { label: '安稳度', value: sleepData.contributors.restfulness || 0 },
        { label: '效率', value: sleepData.contributors.efficiency || 0 },
        { label: 'REM', value: sleepData.contributors.rem_sleep || 0 }
      ])
    }

    // 绘制准备度贡献因子雷达图（过滤 null 值，如体温缺失）
    if (readinessData) {
      const readinessRadarData = [
        { label: '活动平衡', value: readinessData.activity_balance },
        { label: '睡眠规律', value: readinessData.sleep_regularity },
        { label: '睡眠平衡', value: readinessData.sleep_balance },
        { label: '静息心率', value: readinessData.resting_heart_rate },
        { label: '恢复指数', value: readinessData.recovery_index },
        { label: '前晚睡眠', value: readinessData.previous_night },
        { label: '前日活动', value: readinessData.previous_day_activity },
        { label: 'HRV平衡', value: readinessData.hrv_balance },
        { label: '体温', value: readinessData.body_temperature }
      ].filter(item => item.value != null)

      if (readinessRadarData.length >= 3) {
        this.drawRadar('readinessRadar', readinessRadarData)
      }
    }

    // 绘制活动贡献因子雷达图（过滤 null 值）
    if (activityData && activityData.contributors) {
      const activityRadarData = [
        { label: '保持活跃', value: activityData.contributors.stay_active },
        { label: '每小时活动', value: activityData.contributors.move_every_hour },
        { label: '恢复时间', value: activityData.contributors.recovery_time },
        { label: '达成目标', value: activityData.contributors.meet_daily_targets },
        { label: '训练频率', value: activityData.contributors.training_frequency },
        { label: '训练量', value: activityData.contributors.training_volume }
      ].filter(item => item.value != null)

      if (activityRadarData.length >= 3) {
        this.drawRadar('activityRadar', activityRadarData)
      }
    }
  },

  /**
   * 绘制单个雷达图
   */
  drawRadar(canvasId, data) {
    if (!data || data.length === 0) return

    const ctx = wx.createCanvasContext(canvasId, this)
    const centerX = 145
    const centerY = 145
    const radius = 85
    const count = data.length
    const angleStep = (2 * Math.PI) / count

    // 清除画布
    ctx.clearRect(0, 0, 290, 290)

    // 绘制多层网格（白灰交替填充）- 5层更精细
    const gridColors = [
      'rgba(255,255,255,0.9)',
      'rgba(245,245,245,0.7)',
      'rgba(255,255,255,0.9)',
      'rgba(245,245,245,0.7)',
      'rgba(255,255,255,0.9)'
    ]

    // 从外到内绘制填充区域
    for (let level = 5; level >= 1; level--) {
      const levelRadius = (radius * level) / 5
      ctx.beginPath()
      for (let i = 0; i <= count; i++) {
        const angle = i * angleStep - Math.PI / 2
        const x = centerX + levelRadius * Math.cos(angle)
        const y = centerY + levelRadius * Math.sin(angle)
        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      }
      ctx.closePath()
      ctx.setFillStyle(gridColors[level - 1])
      ctx.fill()
    }

    // 绘制网格边线（只绘制最外层和中间层）
    ctx.setStrokeStyle('rgba(200, 200, 200, 0.4)')
    ctx.setLineWidth(0.5)
    for (let level of [3, 5]) {
      const levelRadius = (radius * level) / 5
      ctx.beginPath()
      for (let i = 0; i <= count; i++) {
        const angle = i * angleStep - Math.PI / 2
        const x = centerX + levelRadius * Math.cos(angle)
        const y = centerY + levelRadius * Math.sin(angle)
        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      }
      ctx.closePath()
      ctx.stroke()
    }

    // 绘制轴线
    ctx.setStrokeStyle('rgba(200, 200, 200, 0.3)')
    for (let i = 0; i < count; i++) {
      const angle = i * angleStep - Math.PI / 2
      const x = centerX + radius * Math.cos(angle)
      const y = centerY + radius * Math.sin(angle)
      ctx.beginPath()
      ctx.moveTo(centerX, centerY)
      ctx.lineTo(x, y)
      ctx.stroke()
    }

    // 绘制数据区域 - 使用Oura品牌色
    ctx.beginPath()
    ctx.setFillStyle('rgba(47, 74, 115, 0.2)')
    ctx.setStrokeStyle('#2F4A73')
    ctx.setLineWidth(2)

    for (let i = 0; i <= count; i++) {
      const index = i % count
      const value = Math.min(data[index].value, 100) / 100
      const angle = index * angleStep - Math.PI / 2
      const x = centerX + radius * value * Math.cos(angle)
      const y = centerY + radius * value * Math.sin(angle)
      if (i === 0) {
        ctx.moveTo(x, y)
      } else {
        ctx.lineTo(x, y)
      }
    }
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    // 绘制数据点
    ctx.setFillStyle('#2F4A73')
    for (let i = 0; i < count; i++) {
      const value = Math.min(data[i].value, 100) / 100
      const angle = i * angleStep - Math.PI / 2
      const x = centerX + radius * value * Math.cos(angle)
      const y = centerY + radius * value * Math.sin(angle)
      ctx.beginPath()
      ctx.arc(x, y, 4, 0, 2 * Math.PI)
      ctx.fill()
    }

    // 绘制维度标签和数值（合并显示，避免重叠）
    ctx.setTextAlign('center')
    ctx.setTextBaseline('middle')

    for (let i = 0; i < count; i++) {
      const angle = i * angleStep - Math.PI / 2
      const labelRadius = radius + 22
      const x = centerX + labelRadius * Math.cos(angle)
      const y = centerY + labelRadius * Math.sin(angle)

      // 绘制标签
      ctx.setFillStyle('#666666')
      ctx.setFontSize(10)
      ctx.fillText(data[i].label, x, y - 6)

      // 绘制数值（品牌色，加粗效果）
      ctx.setFillStyle('#2F4A73')
      ctx.setFontSize(12)
      ctx.fillText(data[i].value.toString(), x, y + 7)
    }

    ctx.draw()
  },

  /**
   * 生成数据异常提醒
   */
  generateAlerts(sleepData, readinessData, activityData, trainingData, stressData) {
    const alerts = []

    // 睡眠评分过低
    if (sleepData && sleepData.score < 60) {
      alerts.push({
        type: 'warning',
        icon: '😴',
        message: `睡眠评分仅${sleepData.score}分，建议早睡或改善睡眠环境`
      })
    }

    // 深睡眠不足
    if (sleepData && sleepData.deep_min < 45) {
      alerts.push({
        type: 'warning',
        icon: '🌙',
        message: `深睡眠${sleepData.deep_min}分钟偏少，建议减少睡前蓝光`
      })
    }

    // 准备度低
    if (readinessData && readinessData.score < 60) {
      alerts.push({
        type: 'warning',
        icon: '🔋',
        message: `准备度${readinessData.score}分，身体需要更多休息`
      })
    }

    // 体温偏差大
    if (readinessData && readinessData.temperature_deviation) {
      const tempDev = parseFloat(readinessData.temperature_deviation)
      if (Math.abs(tempDev) > 0.5) {
        alerts.push({
          type: 'danger',
          icon: '🌡️',
          message: `体温偏差${readinessData.temperature_deviation}°较大，注意身体状况`
        })
      }
    }

    // 步数不足
    if (activityData && activityData.steps < 3000) {
      alerts.push({
        type: 'info',
        icon: '👟',
        message: `今日步数仅${activityData.steps}步，记得多活动`
      })
    }

    // 久坐时间长
    if (activityData && activityData.sedentary_min > 600) {
      alerts.push({
        type: 'warning',
        icon: '🪑',
        message: `久坐${activityData.sedentary_hours}小时，建议每小时起身活动`
      })
    }

    // 压力过高
    if (stressData && stressData.day_summary === '压力大') {
      alerts.push({
        type: 'warning',
        icon: '😰',
        message: `今日压力较大（${stressData.stressed_display}），建议放松`
      })
    }

    // 训练高强度过多
    if (trainingData && trainingData.hi_min > 10) {
      alerts.push({
        type: 'info',
        icon: '💪',
        message: `高强度训练${trainingData.hi_min}分钟，注意恢复`
      })
    }

    // 最多显示3条提醒
    return alerts.slice(0, 3)
  },

  /**
   * 处理心率详情数据
   * @param {Object} data API返回的心率详情数据
   */
  processHeartrateDetail(data, sleepData) {
    if (!data) return null

    // 格式化时间显示（只显示时:分）
    const formatTimeOnly = (isoString) => {
      if (!isoString) return '--'
      try {
        const date = new Date(isoString)
        const hours = date.getHours().toString().padStart(2, '0')
        const minutes = date.getMinutes().toString().padStart(2, '0')
        return `${hours}:${minutes}`
      } catch (e) {
        return '--'
      }
    }

    // 睡眠心率数据
    const lowestHr = data.lowest_hr || '--'
    const lowestHrTime = formatTimeOnly(data.lowest_hr_time)
    const sleepPhase = data.sleep_phase === 'first_half' ? '上半段' : '下半段'
    const sleepProgressPercent = data.sleep_progress_percent || 0
    const hrRange = data.hr_range || {}
    const recoveryQuality = data.recovery_quality
    const recoveryNote = data.recovery_note || ''

    // 恢复质量颜色和文本
    let recoveryQualityText = ''
    let recoveryQualityColor = ''
    if (recoveryQuality === 'optimal') {
      recoveryQualityText = '理想'
      recoveryQualityColor = 'green'
    } else if (recoveryQuality === 'suboptimal') {
      recoveryQualityText = '次优'
      recoveryQualityColor = 'orange'
    }

    // 日间心率数据
    const daytimeHr = data.daytime_hr || {}
    const daytimeLowestAvg = daytimeHr.daytime_lowest_avg || '--'
    const daytimeLowestAvgTime = formatTimeOnly(daytimeHr.daytime_lowest_avg_time)
    const activityHrMin = daytimeHr.activity_hr_min || '--'
    const activityHrMax = daytimeHr.activity_hr_max || '--'
    const activityHrAvg = daytimeHr.activity_hr_avg || '--'
    const dataPointsCount = daytimeHr.data_points_count || 0

    // 计算日间时间跨度（24小时 - 总睡眠时长）
    let daytimeSpan = '--'
    if (sleepData && sleepData.records && sleepData.records.length > 0) {
      // 查找最新的有效睡眠记录
      const latestSleep = sleepData.records.find(r => r.total_duration_minutes > 0) || sleepData.records[0]
      if (latestSleep && latestSleep.total_duration_minutes) {
        // 日间时长 = 24小时(1440分钟) - 总睡眠时长
        const daytimeMinutes = 1440 - latestSleep.total_duration_minutes
        const hours = Math.floor(daytimeMinutes / 60)
        const minutes = daytimeMinutes % 60

        if (hours > 0 && minutes > 0) {
          daytimeSpan = `${hours}小时${minutes}分`
        } else if (hours > 0) {
          daytimeSpan = `${hours}小时`
        } else {
          daytimeSpan = `${minutes}分钟`
        }
      }
    }

    // 睡眠进度条颜色：前50%绿色（理想），后50%橙色（次优）
    const progressColor = sleepProgressPercent <= 50 ? 'green' : 'orange'

    return {
      // 睡眠心率
      lowest_hr: lowestHr,
      lowest_hr_time: lowestHrTime,
      sleep_phase: sleepPhase,
      sleep_progress_percent: sleepProgressPercent,
      progress_color: progressColor,
      hr_min: hrRange.min || '--',
      hr_avg: hrRange.avg || '--',
      hr_max: hrRange.max || '--',
      recovery_quality: recoveryQualityText,
      recovery_quality_color: recoveryQualityColor,
      recovery_note: recoveryNote,

      // 日间心率
      daytime_lowest_avg: daytimeLowestAvg,
      daytime_lowest_avg_time: daytimeLowestAvgTime,
      activity_hr_min: activityHrMin,
      activity_hr_max: activityHrMax,
      activity_hr_avg: activityHrAvg,
      data_points_count: dataPointsCount,
      daytime_span: daytimeSpan
    }
  }
})
