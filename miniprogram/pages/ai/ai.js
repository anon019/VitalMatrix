const {
  getTodayRecommendation,
  regenerateRecommendation,
  clearCache
} = require('../../utils/request.js')
const { formatLocalDate } = require('../../utils/date.js')
const { showPageAuthFailure, loadPageAfterAuthentication, retryPageAuthentication } = require('../../utils/page-auth.js')

const SECTION_DEFINITIONS = [
  {
    key: 'nutrition',
    order: '01',
    title: '饮食',
    subtitle: '今天怎么吃更合适',
    keywords: ['饮食', '营养', '早餐', '午餐', '晚餐', '加餐', '热量', '蛋白', '碳水', '脂肪', '蔬菜', '水分', '补水']
  },
  {
    key: 'recovery',
    order: '02',
    title: '睡眠恢复',
    subtitle: '根据睡眠、HRV 与身体状态',
    keywords: ['睡眠', '恢复', 'hrv', '静息', '压力', '疲劳', '休息', '就寝', '起床']
  },
  {
    key: 'activity',
    order: '03',
    title: '活动训练',
    subtitle: '安排今天的活动与训练强度',
    keywords: ['活动', '训练', '运动', '步数', '心率', 'zone', '跑步', '有氧', '力量', '拉伸']
  }
]

Page({
  data: {
    loading: true,
    authError: '',
    regenerating: false,
    loadError: '',
    todayDate: '',
    dataDate: '',
    isDataToday: true,
    requestedDate: '',
    sourceDate: '',
    isStale: false,
    promptVersion: '',
    dataCompleteness: [],
    summary: '',
    aiProvider: '',
    aiModel: '',
    generatedTime: '',
    recommendationSections: [],
    knowledgeSections: []
  },

  onLoad() {
    this._isActive = true
    this._hasShownOnce = false
    this.setDates()
    loadPageAfterAuthentication(this, () => this.loadData({ silent: true }))
  },

  onUnload() {
    this._isActive = false
  },

  onShow() {
    if (!this._hasShownOnce) {
      this._hasShownOnce = true
      return
    }

    const lastRefresh = wx.getStorageSync('aiLastRefresh')
    const app = getApp()
    if (app.globalData.isLoggedIn && (!lastRefresh || Date.now() - lastRefresh > 15 * 60 * 1000)) {
      this.loadData({ silent: true })
    }
  },

  onLoginSuccess() {
    if (this._isActive) this.setData({ authError: '' })
    this.loadData({ silent: true })
  },

  onAuthFailure(error) {
    showPageAuthFailure(this, error)
  },

  retryAuthentication() {
    return retryPageAuthentication(this, () => this.loadData({ silent: true }))
  },

  onPullDownRefresh() {
    const app = getApp()
    if (!app.globalData.isLoggedIn || app.globalData.isLoggingIn) {
      wx.stopPullDownRefresh()
      wx.showToast({ title: '正在登录，请稍后', icon: 'none' })
      return
    }

    clearCache('/api/v1/ai/recommendation')
    this.loadData({ silent: false }).finally(() => wx.stopPullDownRefresh())
  },

  setDates() {
    const today = new Date()
    const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    this.setData({
      todayDate: `${String(today.getMonth() + 1).padStart(2, '0')}月${String(today.getDate()).padStart(2, '0')}日 ${weekDays[today.getDay()]}`
    })
  },

  loadData(options = {}) {
    if (this._loadPromise) return this._loadPromise

    const loadPromise = this.performLoadData(options).finally(() => {
      if (this._loadPromise === loadPromise) this._loadPromise = null
    })
    this._loadPromise = loadPromise
    return loadPromise
  },

  async performLoadData({ silent = false } = {}) {
    const shouldShowLoading = !this._hasLoadedOnce || !silent
    if (shouldShowLoading) this.setData({ loading: true, loadError: '' })

    try {
      const today = new Date()
      const todayStr = formatLocalDate(today)
      const recommendation = await getTodayRecommendation()
      const view = this.buildRecommendationView(recommendation || {})
      if (!recommendation || !(recommendation.summary || view.recommendationSections.length || view.knowledgeSections.length)) {
        throw new Error('AI 建议暂时不可用，请稍后重试')
      }
      const sourceDate = recommendation.source_date || recommendation.requested_date || todayStr
      const isStale = recommendation.is_stale === true
      const metadata = recommendation.generation_metadata || {}
      if (!this._isActive) return
      this.setData({
        summary: recommendation.summary || '',
        aiProvider: recommendation.provider || '',
        aiModel: recommendation.model || '',
        generatedTime: this.formatGeneratedTime(recommendation.created_at),
        dataDate: this.formatDateDisplay(sourceDate),
        isDataToday: !isStale,
        requestedDate: recommendation.requested_date || todayStr,
        sourceDate,
        isStale,
        promptVersion: metadata.prompt_version || '',
        dataCompleteness: this.buildDataCompleteness(metadata.data_completeness),
        recommendationSections: view.recommendationSections,
        knowledgeSections: view.knowledgeSections,
        loading: false,
        loadError: ''
      })
      this._hasLoadedOnce = true
      wx.setStorageSync('aiLastRefresh', Date.now())

      if (!silent) wx.showToast({ title: '已更新', icon: 'success' })
    } catch (error) {
      console.error('加载 AI 建议失败:', error)
      if (!this._isActive) return
      this.setData({
        loading: false,
        loadError: error.message || 'AI 建议暂时不可用，请稍后重试'
      })
    }
  },

  buildDataCompleteness(source = {}) {
    source = source || {}
    const definitions = [
      ['饮食记录天数', source.nutrition_recorded_days ?? source.recorded_days, '天'],
      ['最近餐食', source.recent_meals_count ?? source.recent_meals, '餐'],
      ['睡眠', source.sleep_available ?? source.sleep, 'boolean'],
      ['准备度', source.readiness_available ?? source.readiness, 'boolean'],
      ['活动', source.activity_available ?? source.activity, 'boolean'],
      ['训练', source.training_available ?? source.training, 'boolean']
    ]
    return definitions
      .filter(([, value]) => value !== undefined && value !== null)
      .map(([label, value, unit]) => ({
        label,
        value: unit === 'boolean' ? (value ? '已纳入' : '暂无') : `${value}${unit}`,
        available: unit === 'boolean' ? Boolean(value) : Number(value) > 0
      }))
  },

  getSourceItems(source) {
    if (!source) return []
    if (Array.isArray(source)) return source
    if (Array.isArray(source.items)) return source.items
    if (Array.isArray(source.recommendations)) return source.recommendations
    return []
  },

  normalizeItem(item, sourceLabel = '') {
    if (typeof item === 'string') return { label: sourceLabel, text: item }
    return {
      label: item.label || item.title || sourceLabel,
      text: item.text || item.content || item.suggestion || item.description || ''
    }
  },

  buildRecommendationView(data) {
    const explicitSources = {
      nutrition: data.nutrition || data.diet || data.dietary_recommendations || data.today_recommendation?.nutrition,
      recovery: data.sleep_recovery || data.recovery || data.today_recommendation?.sleep_recovery,
      activity: data.activity_training || data.activity || data.training || data.today_recommendation?.activity_training
    }
    const buckets = { nutrition: [], recovery: [], activity: [] }

    SECTION_DEFINITIONS.forEach(definition => {
      buckets[definition.key] = this.getSourceItems(explicitSources[definition.key])
        .map(item => this.normalizeItem(item))
        .filter(item => item.text)
    })

    const legacyItems = [
      ...this.getSourceItems(data.yesterday_review).map(item => this.normalizeItem(item, '昨日回顾')),
      ...this.getSourceItems(data.today_recommendation).map(item => this.normalizeItem(item))
    ]

    legacyItems.forEach(item => {
      if (!item.text) return
      const haystack = `${item.label} ${item.text}`.toLowerCase()
      const match = SECTION_DEFINITIONS.find(definition =>
        definition.keywords.some(keyword => haystack.includes(keyword))
      )
      const targetKey = match?.key || 'activity'
      const isDuplicate = buckets[targetKey].some(existing => existing.text === item.text)
      if (!isDuplicate) buckets[targetKey].push(item)
    })

    const recommendationSections = SECTION_DEFINITIONS
      .map(definition => ({ ...definition, items: buckets[definition.key] }))
      .filter(section => section.items.length)

    const knowledgeSource = data.health_knowledge || data.health_education || {}
    let knowledgeSections = []
    if (Array.isArray(knowledgeSource.sections)) {
      knowledgeSections = knowledgeSource.sections.map(section => ({
        title: section.subtitle || section.title || '健康知识',
        items: this.getSourceItems(section).map(item => this.normalizeItem(item)).filter(item => item.text)
      })).filter(section => section.items.length)
    } else {
      const items = this.getSourceItems(knowledgeSource).map(item => this.normalizeItem(item)).filter(item => item.text)
      if (items.length) knowledgeSections = [{ title: '健康知识', items }]
    }

    return { recommendationSections, knowledgeSections }
  },

  async regenerate() {
    if (this.data.regenerating) return
    const confirmation = await new Promise(resolve => {
      wx.showModal({
        title: '重新生成今日建议？',
        content: '会根据最新健康数据重新整理建议，可能需要一点时间。',
        confirmText: '重新生成',
        success: resolve,
        fail: () => resolve({ confirm: false })
      })
    })
    if (!confirmation.confirm) return

    this.setData({ regenerating: true, loadError: '' })
    try {
      await regenerateRecommendation(formatLocalDate(new Date()))
      clearCache('/api/v1/ai/recommendation')
      await this.loadData({ silent: true })
      if (!this._isActive) return
      wx.showToast({ title: '建议已重新生成', icon: 'success' })
    } catch (error) {
      console.error('重新生成 AI 建议失败:', error)
      if (this._isActive) this.setData({ loadError: error.message || '重新生成失败，请稍后重试' })
    } finally {
      if (this._isActive) this.setData({ regenerating: false })
    }
  },

  retryLoad() {
    clearCache('/api/v1/ai/recommendation')
    this.loadData({ silent: false })
  },

  formatGeneratedTime(value) {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    const today = new Date()
    const sameDay = formatLocalDate(date) === formatLocalDate(today)
    const hour = String(date.getHours()).padStart(2, '0')
    const minute = String(date.getMinutes()).padStart(2, '0')
    return sameDay ? `今天 ${hour}:${minute}` : `${date.getMonth() + 1}月${date.getDate()}日 ${hour}:${minute}`
  },

  formatDateDisplay(value) {
    if (!value || !String(value).includes('-')) return value || ''
    const parts = value.split('-')
    return `${parts[1]}月${parts[2]}日`
  }
})
