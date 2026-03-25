// app.js
const { login, get, clearAllCache } = require('./utils/request.js')

App({
  globalData: {
    userInfo: null,
    token: null,
    isLoggedIn: false,
    isLoggingIn: false
  },

  onLaunch() {
    console.log('Health Assistant 启动')

    // 尝试从本地存储恢复登录状态
    this.restoreLoginState()
  },

  /**
   * 恢复登录状态
   */
  restoreLoginState() {
    const token = wx.getStorageSync('token')
    const userInfo = wx.getStorageSync('userInfo')

    if (token && userInfo) {
      this.globalData.token = token
      this.globalData.userInfo = userInfo
      this.globalData.isLoggedIn = true
      console.log('登录状态已恢复:', userInfo)
    } else {
      console.log('未找到登录信息，需要重新登录')
      // 自动登录
      this.autoLogin()
    }
  },

  /**
   * 自动登录（单用户简易模式）
   */
  async autoLogin() {
    if (this.loginPromise) {
      return this.loginPromise
    }

    this.globalData.isLoggingIn = true
    console.log('开始自动登录...')

    const loginPromise = login()
      .then(res => {
        // 保存登录信息
        this.globalData.token = res.access_token
        this.globalData.userInfo = {
          userId: res.user_id,
          isNewUser: res.is_new_user
        }
        this.globalData.isLoggedIn = true

        // 持久化存储
        wx.setStorageSync('token', res.access_token)
        wx.setStorageSync('userInfo', this.globalData.userInfo)

        console.log('✅ 自动登录成功!', {
          user_id: res.user_id,
          is_new_user: res.is_new_user,
          token: res.access_token.substring(0, 20) + '...'
        })

        // 登录成功后，通知所有页面刷新数据
        this.notifyLoginSuccess()

        return true
      })
      .catch(error => {
        console.error('自动登录失败:', error)
        wx.showToast({
          title: '登录失败，请重试',
          icon: 'none'
        })
        return false
      })
      .finally(() => {
        this.globalData.isLoggingIn = false
        this.loginPromise = null
      })

    this.loginPromise = loginPromise
    return loginPromise
  },

  clearLoginState() {
    this.globalData.token = null
    this.globalData.userInfo = null
    this.globalData.isLoggedIn = false
    this.globalData.isLoggingIn = false
    this.loginPromise = null

    wx.removeStorageSync('token')
    wx.removeStorageSync('userInfo')
    clearAllCache()

    console.log('登录状态已清除')
  },

  /**
   * 通知所有页面登录成功
   */
  notifyLoginSuccess() {
    // 获取所有页面
    const pages = getCurrentPages()

    // 通知每个页面重新加载数据
    pages.forEach(page => {
      if (page.onLoginSuccess && typeof page.onLoginSuccess === 'function') {
        console.log('通知页面刷新数据:', page.route)
        page.onLoginSuccess()
      }
    })

    // 登录成功后，后台预加载关键数据到缓存
    this.preloadData()
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
  },

  /**
   * 退出登录
   */
  logout() {
    this.clearLoginState()
    console.log('已退出登录')
  }
})
