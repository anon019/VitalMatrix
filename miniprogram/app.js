// app.js
const { get, clearAllCache } = require('./utils/request.js')
const {
  migrateAuthStorage,
  ensureAuthenticated: ensureSilentAuthentication,
  clearAuthSession,
  clearPersistentBusinessCache
} = require('./utils/auth.js')

App({
  globalData: {
    userInfo: null,
    token: null,
    isLoggedIn: false,
    isLoggingIn: false,
    authError: ''
  },

  onLaunch() {
    console.log('Health Assistant 启动')
    const migrated = migrateAuthStorage()
    if (migrated) clearAllCache()
    // 分析字段升级后仅清理业务缓存，保留认证和待上传图片草稿。
    if (wx.getStorageSync('mealAnalysisSchemaVersion') !== 1) {
      clearPersistentBusinessCache()
      clearAllCache()
      wx.setStorageSync('mealAnalysisSchemaVersion', 1)
    }

    // 页面统一等待这个 Promise，认证完成前不发业务请求。
    this.authReadyPromise = this.initializeAuthentication()
    // 标记启动 Promise 的拒绝已被观察；页面仍可通过原 Promise得到错误。
    this.authReadyPromise.catch(() => {})
  },

  initializeAuthentication() {
    return this.ensureAuthenticated()
      .then(session => {
        this.notifyLoginSuccess()
        return session
      })
      .catch(error => {
        this.notifyAuthFailure(error)
        throw error
      })
  },

  /**
   * 应用内唯一认证入口。底层 Promise 由 utils/auth.js 全局去重。
   */
  ensureAuthenticated(options = {}) {
    this.globalData.isLoggingIn = true
    this.globalData.authError = ''

    return ensureSilentAuthentication(options)
      .then(session => {
        this.applyAuthSession(session)
        return session
      })
      .catch(error => {
        this.applyAuthSession(null)
        this.globalData.authError = error.message || '数据连接失败，请稍后重试'
        throw error
      })
      .finally(() => {
        this.globalData.isLoggingIn = false
      })
  },

  whenAuthenticated() {
    if (this.globalData.isLoggedIn) return this.ensureAuthenticated()
    return this.authReadyPromise || this.ensureAuthenticated()
  },

  retryAuthentication() {
    clearAuthSession()
    clearAllCache()
    clearPersistentBusinessCache()
    this.applyAuthSession(null)

    this.authReadyPromise = this.ensureAuthenticated({ force: true })
      .then(session => {
        this.notifyLoginSuccess()
        return session
      })
      .catch(error => {
        this.notifyAuthFailure(error)
        throw error
      })
    this.authReadyPromise.catch(() => {})
    return this.authReadyPromise
  },

  applyAuthSession(session) {
    if (!session) {
      this.globalData.token = null
      this.globalData.userInfo = null
      this.globalData.isLoggedIn = false
      return
    }

    this.globalData.token = session.accessToken
    this.globalData.userInfo = session.userId
      ? { userId: session.userId, isNewUser: session.isNewUser === true }
      : null
    this.globalData.isLoggedIn = true
    this.globalData.authError = ''
  },

  clearLoginState() {
    clearAuthSession()
    clearAllCache()
    clearPersistentBusinessCache()
    this.applyAuthSession(null)
    console.log('[Auth] 数据连接状态已清除')
  },

  notifyLoginSuccess() {
    getCurrentPages().forEach(page => {
      if (page.onLoginSuccess && typeof page.onLoginSuccess === 'function') {
        page.onLoginSuccess()
      }
    })
    this.preloadData()
  },

  notifyAuthFailure(error) {
    getCurrentPages().forEach(page => {
      if (page.onAuthFailure && typeof page.onAuthFailure === 'function') {
        page.onAuthFailure(error)
      }
    })
  },

  preloadData() {
    console.log('[Preload] 开始预加载关键数据')
    Promise.all([
      get('/api/v1/dashboard/today').catch(() => null),
      get('/api/v1/oura/sleep/grouped', { days: 7 }).catch(() => null),
      get('/api/v1/training/today').catch(() => null)
    ]).then(() => {
      console.log('[Preload] 关键数据预加载完成')
    })
  }
})
