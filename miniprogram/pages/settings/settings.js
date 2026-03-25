// pages/settings/settings.js
const { getUserInfo, updateUserInfo, getPolarAuthStatus, syncPolarData, clearAllCache, clearCache } = require('../../utils/request.js')
const config = require('../../utils/config.js')

Page({
  data: {
    loading: true,
    userInfo: {},
    polarAuth: null,
    hrMax: null,
    restingHr: null,
    weight: null,
    vo2max: null,
    zoneRanges: {
      zone1: { min: 93, max: 111 },
      zone2: { min: 111, max: 130 },
      zone3: { min: 130, max: 148 },
      zone4: { min: 148, max: 167 },
      zone5: { min: 167, max: 185 }
    },
    apiUrl: config.API_BASE_URL
  },

  onLoad() {
    console.log('设置页面加载')
    this._hasShownOnce = false

    // 检查是否已登录
    const app = getApp()
    if (app.globalData.isLoggedIn) {
      this.loadData({ silent: true })
    }
  },

  onShow() {
    if (!this._hasShownOnce) {
      this._hasShownOnce = true
      return
    }

    const lastRefresh = wx.getStorageSync('settingsLastRefresh')
    const now = Date.now()
    const app = getApp()
    if (app.globalData.isLoggedIn && (!lastRefresh || now - lastRefresh > 5 * 60 * 1000)) {
      this.loadData({ silent: true })
    }
  },

  /**
   * 登录成功回调（由 app.js 调用）
   */
  onLoginSuccess() {
    console.log('设置页面：收到登录成功通知')
    this.loadData({ silent: true })
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    clearCache('/api/v1/user/info')
    clearCache('/api/v1/polar/status')
    this.loadData({ silent: false }).then(() => {
      wx.stopPullDownRefresh()
    })
  },

  /**
   * 加载数据
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

    try {
      // 获取本地用户信息
      const localUserInfo = wx.getStorageSync('userInfo')

      // 并行请求
      const [userInfo, polarAuth] = await Promise.all([
        getUserInfo().catch(err => {
          console.warn('获取用户信息失败:', err)
          return null
        }),
        getPolarAuthStatus().catch(err => {
          console.warn('获取Polar授权状态失败:', err)
          return null
        })
      ])

      console.log('设置数据加载完成:', { userInfo, polarAuth })

      const hrMax = userInfo?.hr_max || 185
      const zoneRanges = this.calculateZoneRanges(hrMax)

      this.setData({
        userInfo: userInfo || localUserInfo || {},
        polarAuth,
        hrMax,
        restingHr: userInfo?.resting_hr || null,
        weight: userInfo?.weight || null,
        vo2max: userInfo?.vo2max || null,
        zoneRanges,
        loading: false
      })
      this._hasLoadedOnce = true
      wx.setStorageSync('settingsLastRefresh', Date.now())
    } catch (error) {
      console.error('加载数据失败:', error)
      if (shouldShowLoading) {
        this.setData({ loading: false })
      }

      if (!silent || !this._hasLoadedOnce) {
        wx.showToast({
          title: '加载失败',
          icon: 'none'
        })
      }
    }
  },

  /**
   * 计算心率区间
   */
  calculateZoneRanges(hrMax) {
    return {
      zone1: {
        min: Math.round(hrMax * 0.5),
        max: Math.round(hrMax * 0.6)
      },
      zone2: {
        min: Math.round(hrMax * 0.6),
        max: Math.round(hrMax * 0.7)
      },
      zone3: {
        min: Math.round(hrMax * 0.7),
        max: Math.round(hrMax * 0.8)
      },
      zone4: {
        min: Math.round(hrMax * 0.8),
        max: Math.round(hrMax * 0.9)
      },
      zone5: {
        min: Math.round(hrMax * 0.9),
        max: hrMax
      }
    }
  },

  /**
   * 授权Polar
   */
  authorizePolar() {
    wx.showModal({
      title: 'Polar 授权',
      content: '当前版本暂不支持在小程序内直接发起 Polar 授权。请先在 Web 端完成授权，后续小程序会自动显示同步状态。',
      showCancel: false,
      confirmText: '我知道了'
    })

    // TODO: 实现Polar OAuth授权流程
    // 由于微信小程序限制，可能需要：
    // 1. 生成授权链接
    // 2. 复制链接到剪贴板
    // 3. 提示用户在浏览器中打开
  },

  /**
   * 同步Polar数据
   */
  async syncPolarData() {
    const result = await wx.showModal({
      title: '同步数据',
      content: '确定要立即同步Polar训练数据吗？这可能需要几秒钟。',
      confirmText: '同步',
      cancelText: '取消'
    })

    if (!result.confirm) {
      return
    }

    wx.showLoading({
      title: '同步中...',
      mask: true
    })

    try {
      const syncResult = await syncPolarData(7)

      console.log('Polar数据同步成功:', syncResult)
      clearCache('/api/v1/polar/status')
      clearCache('/api/v1/training')

      await this.loadData({ silent: true })
      wx.hideLoading()

      wx.showToast({
        title: `同步成功，新增${syncResult.new_count || 0}条记录`,
        icon: 'success',
        duration: 2000
      })
    } catch (error) {
      console.error('同步失败:', error)
      wx.hideLoading()

      wx.showToast({
        title: error.message || '同步失败，请重试',
        icon: 'none'
      })
    }
  },

  /**
   * 修改最大心率
   */
  async updateHrMax() {
    // 弹出输入框
    const result = await wx.showModal({
      title: '修改最大心率',
      content: `当前值: ${this.data.hrMax || 185} bpm`,
      editable: true,
      placeholderText: '请输入最大心率（如: 185）'
    })

    if (!result.confirm || !result.content) {
      return
    }

    const newHrMax = parseInt(result.content)

    if (isNaN(newHrMax) || newHrMax < 100 || newHrMax > 220) {
      wx.showToast({
        title: '请输入有效的心率值（100-220）',
        icon: 'none'
      })
      return
    }

    wx.showLoading({ title: '保存中...' })

    try {
      await updateUserInfo({ hr_max: newHrMax })

      console.log('最大心率更新成功:', newHrMax)
      clearCache('/api/v1/user/info')

      // 重新计算Zone区间
      const zoneRanges = this.calculateZoneRanges(newHrMax)

      this.setData({
        hrMax: newHrMax,
        zoneRanges
      })

      wx.hideLoading()

      wx.showToast({
        title: '保存成功',
        icon: 'success'
      })
    } catch (error) {
      console.error('保存失败:', error)
      wx.hideLoading()

      wx.showToast({
        title: '保存失败，请重试',
        icon: 'none'
      })
    }
  },

  /**
   * 清除本地缓存
   */
  async clearCache() {
    const result = await wx.showModal({
      title: '清除缓存',
      content: '确定要清除本地缓存吗？这不会影响服务器数据。',
      confirmText: '清除',
      confirmColor: '#C62828',
      cancelText: '取消'
    })

    if (!result.confirm) {
      return
    }

    try {
      // 保留token和用户信息
      const token = wx.getStorageSync('token')
      const userInfo = wx.getStorageSync('userInfo')
      clearAllCache()

      wx.clearStorageSync()

      // 恢复token和用户信息
      if (token) wx.setStorageSync('token', token)
      if (userInfo) wx.setStorageSync('userInfo', userInfo)

      wx.showToast({
        title: '缓存已清除',
        icon: 'success'
      })
    } catch (error) {
      console.error('清除缓存失败:', error)
      wx.showToast({
        title: '清除失败',
        icon: 'none'
      })
    }
  },

  /**
   * 刷新所有数据
   */
  async refreshAllData() {
    wx.showLoading({
      title: '刷新中...',
      mask: true
    })

    try {
      clearAllCache()
      await this.loadData({ silent: true })

      wx.hideLoading()

      wx.showToast({
        title: '刷新成功',
        icon: 'success'
      })
    } catch (error) {
      wx.hideLoading()

      wx.showToast({
        title: '刷新失败',
        icon: 'none'
      })
    }
  },

  /**
   * 退出登录
   */
  async logout() {
    const result = await wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      confirmText: '退出',
      confirmColor: '#C62828',
      cancelText: '取消'
    })

    if (!result.confirm) {
      return
    }

    try {
      // 清除登录信息
      const app = getApp()
      if (app && app.logout) {
        app.logout()
      }

      wx.showToast({
        title: '已退出登录',
        icon: 'success'
      })

      // 延迟后重新登录
      setTimeout(() => {
        if (app && app.autoLogin) {
          app.autoLogin()
        }
      }, 1500)
    } catch (error) {
      console.error('退出登录失败:', error)
    }
  }
})
