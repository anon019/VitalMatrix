// pages/ai/ai.js
const { getTodayRecommendation, getRecommendation } = require('../../utils/request.js')

Page({
  data: {
    loading: true,
    todayDate: '',
    dataDate: '',  // 实际数据的日期（用于显示）
    isDataToday: true,  // 标识数据是否是今天的

    // AI建议数据（结构化格式）
    summary: '',
    aiProvider: '',
    aiModel: '',
    generatedTime: '',

    // 昨日评价
    yesterdayReview: null,

    // 今日建议
    todayRecommendation: null,

    // 健康科普
    healthEducation: null
  },

  onLoad() {
    console.log('AI页面加载')
    this.setDates()

    const app = getApp()
    if (app.globalData.isLoggedIn) {
      this.loadData()
    }
  },

  onShow() {
    const lastRefresh = wx.getStorageSync('aiLastRefresh')
    const now = Date.now()

    const app = getApp()
    if (app.globalData.isLoggedIn && (!lastRefresh || now - lastRefresh > 5 * 60 * 1000)) {
      this.loadData()
    }
  },

  onLoginSuccess() {
    console.log('AI页面：收到登录成功通知')
    this.loadData()
  },

  onPullDownRefresh() {
    // 下拉刷新：先检查登录状态
    const app = getApp()

    // 如果未登录或正在登录中，等待登录完成
    if (!app.globalData.isLoggedIn || app.globalData.isLoggingIn) {
      console.log('等待登录完成...')
      wx.stopPullDownRefresh()
      wx.showToast({
        title: '正在登录，请稍后',
        icon: 'none',
        duration: 2000
      })
      return
    }

    // 下拉刷新时清除缓存
    const { clearCache } = require('../../utils/request.js')
    clearCache('/api/v1/ai/recommendation')

    this.loadData().then(() => {
      wx.stopPullDownRefresh()
    }).catch(() => {
      wx.stopPullDownRefresh()
    })
  },

  setDates() {
    const today = new Date()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    const day = String(today.getDate()).padStart(2, '0')
    const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    const weekDay = weekDays[today.getDay()]

    this.setData({
      todayDate: `${month}月${day}日 ${weekDay}`
    })
  },

  async loadData() {
    this.setData({ loading: true })

    try {
      // 智能获取AI建议：并行请求今日和昨日，优先使用今日数据
      const today = new Date()
      const yesterday = new Date(today)
      yesterday.setDate(yesterday.getDate() - 1)
      const todayStr = this.formatDateISO(today)
      const yesterdayStr = this.formatDateISO(yesterday)

      // 并行请求今日和昨日的AI建议（现在都很快：今日0.6秒，昨日1秒）
      const [todayResult, yesterdayResult] = await Promise.all([
        getTodayRecommendation().catch(err => {
          console.warn('获取今日AI建议失败:', err)
          return null
        }),
        getRecommendation(yesterdayStr).catch(err => {
          console.warn('获取昨日AI建议失败:', err)
          return null
        })
      ])

      // 优先使用今日数据（如果有效）
      let data = null
      let dataDate = todayStr
      let isDataToday = true

      if (todayResult && this.hasValidData(todayResult)) {
        data = todayResult
        dataDate = todayStr
        isDataToday = true
        console.log('使用今日AI建议')
      } else if (yesterdayResult && this.hasValidData(yesterdayResult)) {
        data = yesterdayResult
        dataDate = yesterdayStr
        isDataToday = false
        console.log('今日无数据，使用昨日AI建议')
      }

      // 如果都没有有效数据，显示错误
      if (!data) {
        this.setData({ loading: false })

        wx.showToast({
          title: 'AI服务暂时不可用',
          icon: 'none',
          duration: 3000
        })
        return
      }

      console.log('AI建议数据:', data, '日期:', dataDate, '是否今日数据:', isDataToday)

      // 提取并显示数据
      const aiProvider = data.provider || 'AI'
      const aiModel = data.model || ''
      let generatedTime = ''
      if (data.created_at) {
        generatedTime = this.formatGeneratedTime(data.created_at)
      }

      this.setData({
        summary: data.summary || '',
        aiProvider,
        aiModel,
        generatedTime,
        dataDate: this.formatDateDisplay(dataDate),
        isDataToday,
        yesterdayReview: data.yesterday_review || null,
        todayRecommendation: data.today_recommendation || null,
        healthEducation: data.health_education || null,
        loading: false
      })

      wx.setStorageSync('aiLastRefresh', Date.now())

      wx.showToast({
        title: '刷新成功',
        icon: 'success',
        duration: 1500
      })
    } catch (error) {
      console.error('加载数据失败:', error)
      this.setData({ loading: false })

      wx.showToast({
        title: 'AI服务暂时不可用',
        icon: 'none',
        duration: 3000
      })
    }
  },


  /**
   * 格式化生成时间
   */
  formatGeneratedTime(isoString) {
    try {
      const date = new Date(isoString)
      const now = new Date()

      // 计算时间差（分钟）
      const diffMs = now - date
      const diffMins = Math.floor(diffMs / (1000 * 60))
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

      // 如果是今天
      if (diffDays === 0) {
        if (diffMins < 1) {
          return '刚刚'
        } else if (diffMins < 60) {
          return `${diffMins}分钟前`
        } else {
          return `${diffHours}小时前`
        }
      }
      // 如果是昨天
      else if (diffDays === 1) {
        const hours = String(date.getHours()).padStart(2, '0')
        const minutes = String(date.getMinutes()).padStart(2, '0')
        return `昨天 ${hours}:${minutes}`
      }
      // 更早的日期
      else {
        const month = date.getMonth() + 1
        const day = date.getDate()
        const hours = String(date.getHours()).padStart(2, '0')
        const minutes = String(date.getMinutes()).padStart(2, '0')
        return `${month}月${day}日 ${hours}:${minutes}`
      }
    } catch (error) {
      console.error('时间格式化失败:', error)
      return ''
    }
  },

  /**
   * 判断AI数据是否有效
   */
  hasValidData(data) {
    if (!data) return false
    // 至少要有一个有效的内容
    return !!(
      (data.yesterday_review && data.yesterday_review.items && data.yesterday_review.items.length > 0) ||
      (data.today_recommendation && data.today_recommendation.items && data.today_recommendation.items.length > 0) ||
      (data.health_education && data.health_education.sections && data.health_education.sections.length > 0)
    )
  },

  /**
   * 格式化日期为 ISO 格式 (YYYY-MM-DD)
   */
  formatDateISO(date) {
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  },

  /**
   * 格式化日期显示 (MM-DD)
   */
  formatDateDisplay(isoDateStr) {
    const [year, month, day] = isoDateStr.split('-')
    return `${month}-${day}`
  }
})
