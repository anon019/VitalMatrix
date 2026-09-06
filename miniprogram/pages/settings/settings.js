// pages/settings/settings.js
const { getUserInfo, updateUserInfo, getPolarAuthStatus, syncPolarData, clearAllCache, clearCache } = require('../../utils/request.js')
const config = require('../../utils/config.js')
const { clearPersistentBusinessCache } = require('../../utils/auth.js')
const { showPageAuthFailure, loadPageAfterAuthentication, retryPageAuthentication } = require('../../utils/page-auth.js')

Page({
  data: {
    loading: true,
    authError: '',
    userInfo: {},
    polarAuth: null,
    hrMax: null,
    restingHr: null,
    weight: null,
    vo2max: null,
    genderOptions: ['男', '女', '其他'],
    genderIndex: -1,
    profileGender: '',
    profileBirthDate: '',
    maxBirthDate: '',
    profileAgeText: '',
    profileWeight: '',
    editingProfile: false,
    savingProfile: false,
    healthGoal: '降脂心血管健康优化',
    trainingPlan: 'Zone2 55分钟 + Zone4-5 2分钟',
    goalDraft: '',
    planDraft: '',
    editingGoal: false,
    savingGoal: false,
    zoneRanges: {
      zone1: { min: 93, max: 111 },
      zone2: { min: 111, max: 130 },
      zone3: { min: 130, max: 148 },
      zone4: { min: 148, max: 167 },
      zone5: { min: 167, max: 185 }
    },
    apiUrl: config.API_BASE_URL,
    appVersion: config.APP_VERSION
  },

  onLoad() {
    console.log('设置页面加载')
    this._isActive = true
    this._hasShownOnce = false
    const now = new Date()
    this.setData({ maxBirthDate: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}` })

    loadPageAfterAuthentication(this, () => this.loadData({ silent: true }))
  },

  onShow() {
    if (!this._hasShownOnce) {
      this._hasShownOnce = true
      const app = getApp()
      if (!this._hasLoadedOnce && app.globalData.isLoggedIn) {
        this.loadData({ silent: true })
      }
      return
    }

    const lastRefresh = wx.getStorageSync('settingsLastRefresh')
    const now = Date.now()
    const app = getApp()
    if (app.globalData.isLoggedIn && (!lastRefresh || now - lastRefresh > 5 * 60 * 1000)) {
      this.loadData({ silent: true })
    }
  },

  onUnload() {
    this._isActive = false
  },

  /**
   * 登录成功回调（由 app.js 调用）
   */
  onLoginSuccess() {
    console.log('设置页面：收到登录成功通知')
    if (this._isActive) this.setData({ authError: '' })
    this.loadData({ silent: true })
  },

  onAuthFailure(error) {
    showPageAuthFailure(this, error)
  },

  retryAuthentication() {
    return retryPageAuthentication(this, () => this.loadData({ silent: true }))
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    clearCache('/api/v1/user/profile')
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
      // 并行请求
      const [userInfo, polarAuth] = await Promise.all([
        // 用户资料是设置页的核心数据，失败时不能用默认值伪装成真实配置。
        getUserInfo(),
        getPolarAuthStatus().catch(err => {
          console.warn('获取Polar授权状态失败:', err)
          return null
        })
      ])

      console.log('设置数据加载完成')

      const hrMax = userInfo?.hr_max || 185
      const zoneRanges = this.calculateZoneRanges(hrMax)
      const gender = userInfo?.gender || ''
      const birthDate = userInfo?.birth_year && userInfo?.birth_month
        ? `${userInfo.birth_year}-${String(userInfo.birth_month).padStart(2, '0')}`
        : ''
      const healthGoal = userInfo?.health_goal || '降脂心血管健康优化'
      const trainingPlan = userInfo?.training_plan || 'Zone2 55分钟 + Zone4-5 2分钟'

      if (!this._isActive) return
      this.setData({
        userInfo: userInfo || {},
        polarAuth,
        hrMax,
        restingHr: userInfo?.resting_hr || null,
        weight: userInfo?.weight || null,
        vo2max: userInfo?.vo2max || null,
        genderIndex: this.data.genderOptions.indexOf(gender),
        profileGender: gender,
        profileBirthDate: birthDate,
        profileAgeText: this.calculateAgeText(userInfo?.birth_year, userInfo?.birth_month),
        profileWeight: userInfo?.weight != null ? String(userInfo.weight) : '',
        healthGoal,
        trainingPlan,
        goalDraft: healthGoal,
        planDraft: trainingPlan,
        zoneRanges,
        loading: false
      })
      this._hasLoadedOnce = true
      wx.setStorageSync('settingsLastRefresh', Date.now())
    } catch (error) {
      console.error('加载数据失败:', error)
      if (!this._isActive) return
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

  calculateAgeText(year, month) {
    if (!year || !month) return ''
    const now = new Date()
    let age = now.getFullYear() - Number(year)
    if (now.getMonth() + 1 < Number(month)) age -= 1
    return age >= 0 ? `${age} 岁` : ''
  },

  startProfileEdit() {
    this.setData({ editingProfile: true })
  },

  cancelProfileEdit() {
    const userInfo = this.data.userInfo || {}
    const gender = userInfo.gender || ''
    this.setData({
      editingProfile: false,
      genderIndex: this.data.genderOptions.indexOf(gender),
      profileGender: gender,
      profileBirthDate: userInfo.birth_year && userInfo.birth_month
        ? `${userInfo.birth_year}-${String(userInfo.birth_month).padStart(2, '0')}`
        : '',
      profileWeight: userInfo.weight != null ? String(userInfo.weight) : ''
    })
  },

  onGenderChange(event) {
    const genderIndex = Number(event.detail.value)
    this.setData({
      genderIndex,
      profileGender: this.data.genderOptions[genderIndex] || ''
    })
  },

  onBirthDateChange(event) {
    this.setData({ profileBirthDate: event.detail.value })
  },

  onWeightInput(event) {
    this.setData({ profileWeight: event.detail.value })
  },

  async saveProfile() {
    if (this.data.savingProfile) return
    const weight = Number(this.data.profileWeight)
    if (!this.data.profileGender || !this.data.profileBirthDate || !weight) {
      wx.showToast({ title: '请完整填写个人资料', icon: 'none' })
      return
    }
    if (weight < 20 || weight > 300) {
      wx.showToast({ title: '请输入 20–300 kg 的体重', icon: 'none' })
      return
    }

    const [birthYear, birthMonth] = this.data.profileBirthDate.split('-').map(Number)
    this.setData({ savingProfile: true })
    try {
      await updateUserInfo({
        gender: this.data.profileGender,
        birth_year: birthYear,
        birth_month: birthMonth,
        weight
      })
      clearCache('/api/v1/user/profile')
      const userInfo = {
        ...this.data.userInfo,
        gender: this.data.profileGender,
        birth_year: birthYear,
        birth_month: birthMonth,
        weight
      }
      this.setData({
        userInfo,
        weight,
        profileAgeText: this.calculateAgeText(birthYear, birthMonth),
        editingProfile: false,
        savingProfile: false
      })
      wx.showToast({ title: '资料已保存', icon: 'success' })
    } catch (error) {
      console.error('保存个人资料失败:', error)
      this.setData({ savingProfile: false })
      wx.showToast({ title: error.message || '保存失败，请重试', icon: 'none' })
    }
  },

  startGoalEdit() {
    this.setData({
      editingGoal: true,
      goalDraft: this.data.healthGoal,
      planDraft: this.data.trainingPlan
    })
  },

  cancelGoalEdit() {
    this.setData({
      editingGoal: false,
      goalDraft: this.data.healthGoal,
      planDraft: this.data.trainingPlan
    })
  },

  onGoalInput(event) {
    this.setData({ goalDraft: event.detail.value })
  },

  onPlanInput(event) {
    this.setData({ planDraft: event.detail.value })
  },

  async saveGoalSettings() {
    if (this.data.savingGoal) return

    const healthGoal = String(this.data.goalDraft || '').trim()
    const trainingPlan = String(this.data.planDraft || '').trim()
    if (!healthGoal || !trainingPlan) {
      wx.showToast({ title: '请填写健康目标和训练方案', icon: 'none' })
      return
    }

    this.setData({ savingGoal: true })
    try {
      await updateUserInfo({ health_goal: healthGoal, training_plan: trainingPlan })
      clearCache('/api/v1/user/profile')
      this.setData({
        healthGoal,
        trainingPlan,
        editingGoal: false,
        savingGoal: false,
        userInfo: {
          ...this.data.userInfo,
          health_goal: healthGoal,
          training_plan: trainingPlan
        }
      })
      wx.showToast({ title: '目标已同步', icon: 'success' })
    } catch (error) {
      console.error('保存健康目标失败:', error)
      this.setData({ savingGoal: false })
      wx.showToast({ title: error.message || '保存失败，请重试', icon: 'none' })
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

      console.log('Polar数据同步成功')
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
      clearCache('/api/v1/user/profile')

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
      clearAllCache()
      clearPersistentBusinessCache()

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
  }
})
