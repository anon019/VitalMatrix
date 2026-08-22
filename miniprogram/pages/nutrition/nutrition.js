// pages/nutrition/nutrition.js
const {
  uploadMeal,
  getMeals,
  getNutritionDailySummary,
  getNutritionWeekly,
  resolveApiUrl,
  clearCache
} = require('../../utils/request.js')
const { formatLocalDate } = require('../../utils/date.js')

Page({
  data: {
    loading: true,
    submittingPhoto: false,
    uploadStatusText: '正在上传并识别食物…',
    selectedMealType: '', // 将根据时间自动选择
    todaySummary: null,
    meals: [],
    currentPage: 1,
    pageSize: 10,
    hasMore: true,
    // 新增：页面日期显示
    currentDay: '',
    currentWeekday: '',
    // 新增：营养进度数据
    calorieProgress: 0,
    proteinProgress: 0,
    carbsProgress: 0,
    fatProgress: 0,
    recordedDays: 0,
    expectedDays: 7,
    summaryLabel: '已记录摄入',
    showDailyTargetProgress: false
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad(options) {
    console.log('Nutrition page loaded')
    this._isActive = true
    const unavailableMealImages = getApp().globalData.unavailableMealImages || {}
    this._unavailableMealImages = new Set(
      Object.keys(unavailableMealImages).filter(mealId => unavailableMealImages[mealId])
    )
    this._hasShownOnce = false
    this.initPage()
  },

  onUnload() {
    this._isActive = false
  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow() {
    if (!this._hasShownOnce) {
      this._hasShownOnce = true
      return
    }

    const needsRefresh = wx.getStorageSync('nutritionNeedsRefresh')
    const lastRefresh = wx.getStorageSync('nutritionLastRefresh')
    const now = Date.now()

    if (needsRefresh) {
      wx.removeStorageSync('nutritionNeedsRefresh')
      clearCache('/api/v1/nutrition')
      this.loadData({ silent: true })
      return
    }

    if (!lastRefresh || now - lastRefresh > 10 * 60 * 1000) {
      this.loadData({ silent: true })
    }
  },

  /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh() {
    console.log('Pull down refresh')
    // 下拉刷新时清除营养相关缓存
    clearCache('/api/v1/nutrition')

    this.loadData({ silent: false }).then(() => {
      wx.stopPullDownRefresh()
    }).catch(() => {
      wx.stopPullDownRefresh()
    })
  },

  /**
   * 页面上拉触底事件的处理函数
   */
  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.loadMoreMeals()
    }
  },

  /**
   * 初始化页面
   */
  async initPage() {
    // 初始化日期显示
    this.initDateDisplay()

    // 根据当前时间自动选择餐次
    this.autoSelectMealType()

    await this.loadData({ silent: true })
  },

  /**
   * 初始化日期显示
   */
  initDateDisplay() {
    const now = new Date()
    const day = now.getDate()
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    const weekday = weekdays[now.getDay()]

    this.setData({
      currentDay: day.toString(),
      currentWeekday: weekday
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
      await Promise.all([
        this.loadTodaySummary(),
        this.loadRecentMeals(),
        this.loadWeeklyCoverage()
      ])
      this._hasLoadedOnce = true
      wx.setStorageSync('nutritionLastRefresh', Date.now())
    } catch (err) {
      console.error('Load data error:', err)
      if (!silent || !this._hasLoadedOnce) {
        wx.showToast({
          title: '加载失败',
          icon: 'none'
        })
      }
    } finally {
      if (shouldShowLoading && this._isActive) {
        this.setData({ loading: false })
      }
    }
  },

  /**
   * 加载今日营养汇总
   */
  async loadTodaySummary() {
    try {
      const today = this.formatDate(new Date())
      const summary = await getNutritionDailySummary(today)

      if (!summary) {
        if (this._isActive) {
          this.setData({
            todaySummary: null,
            calorieProgress: 0,
            proteinProgress: 0,
            carbsProgress: 0,
            fatProgress: 0,
            summaryLabel: '暂无已记录摄入',
            showDailyTargetProgress: false
          })
        }
        return
      }

      console.log('[Summary] API response:', summary)
      console.log('[Summary] meal_count field:', summary.meal_count)

      const totalCalories = Math.round(summary.total_calories || 0)
      const totalProtein = summary.total_protein || 0
      const totalCarbs = summary.total_carbs || 0
      const totalFat = summary.total_fat || 0

      // 计算营养进度（基于推荐摄入量）
      // 热量目标：2000 kcal，蛋白质：60g，碳水：250g，脂肪：65g
      const calorieTarget = 2000
      const proteinTarget = 60
      const carbsTarget = 250
      const fatTarget = 65

      // 热量进度（环形图角度，最大360度）
      const calorieProgress = Math.min(360, (totalCalories / calorieTarget) * 360)
      // 宏量元素进度（柱状图百分比，最大100%）
      const proteinProgress = Math.min(100, (totalProtein / proteinTarget) * 100)
      const carbsProgress = Math.min(100, (totalCarbs / carbsTarget) * 100)
      const fatProgress = Math.min(100, (totalFat / fatTarget) * 100)

      const mealCount = summary.meals_count != null
        ? summary.meals_count
        : (summary.meal_count != null ? summary.meal_count : 0)

      if (!this._isActive) return
      this.setData({
        todaySummary: {
          ...summary,
          meals_count: mealCount,
          meal_count: mealCount,
          total_calories: totalCalories,
          total_protein: totalProtein.toFixed(1),
          total_carbs: totalCarbs.toFixed(1),
          total_fat: totalFat.toFixed(1)
        },
        calorieProgress: calorieProgress,
        proteinProgress: proteinProgress,
        carbsProgress: carbsProgress,
        fatProgress: fatProgress,
        summaryLabel: summary.flags?.partial_day ? '已记录摄入（记录未满三餐）' : '已记录摄入',
        showDailyTargetProgress: summary.flags?.partial_day !== true
      })

      console.log('[Summary] Final todaySummary:', this.data.todaySummary)
    } catch (err) {
      console.warn('Load today summary error:', err)
      // 今日没有数据时不显示汇总卡片
      if (this._isActive) this.setData({
        todaySummary: null,
        calorieProgress: 0,
        proteinProgress: 0,
        carbsProgress: 0,
        fatProgress: 0,
        showDailyTargetProgress: false
      })
    }
  },

  async loadWeeklyCoverage() {
    try {
      const weekly = await getNutritionWeekly()
      if (!this._isActive) return
      this.setData({
        recordedDays: Number(weekly?.recorded_days) || 0,
        expectedDays: Number(weekly?.expected_days) || 7
      })
    } catch (error) {
      console.warn('Load nutrition coverage error:', error)
    }
  },

  /**
   * 加载最近餐食记录
   */
  async loadRecentMeals(forceRefresh = false) {
    try {
      const result = await getMeals({
        page: 1,
        page_size: this.data.pageSize
      }, forceRefresh)

      const rawMeals = Array.isArray(result?.meals) ? result.meals : []
      const meals = rawMeals.map(meal => this.formatMealItem(meal))

      if (!this._isActive) return
      this.setData({
        meals,
        currentPage: 1,
        hasMore: Number(result?.total) > this.data.pageSize
      })
      return { rawMeals, meals }
    } catch (err) {
      console.error('Load recent meals error:', err)
      if (forceRefresh) throw err
      if (this._isActive) this.setData({ meals: [] })
    }
  },

  /**
   * 加载更多餐食记录
   */
  async loadMoreMeals() {
    const nextPage = this.data.currentPage + 1

    try {
      const result = await getMeals({
        page: nextPage,
        page_size: this.data.pageSize
      })

      const rawMeals = Array.isArray(result?.meals) ? result.meals : []
      const moreMeals = rawMeals.map(meal => this.formatMealItem(meal))

      if (!this._isActive) return
      this.setData({
        meals: [...this.data.meals, ...moreMeals],
        currentPage: nextPage,
        hasMore: Number(result?.total) > nextPage * this.data.pageSize
      })
    } catch (err) {
      console.error('Load more meals error:', err)
      if (!this._isActive) return
      wx.showToast({
        title: '加载失败',
        icon: 'none'
      })
    }
  },

  /**
   * 格式化餐食项数据
   */
  formatMealItem(meal) {
    const mealTypeMap = {
      breakfast: '早餐',
      lunch: '午餐',
      dinner: '晚餐',
      snack: '加餐'
    }

    // 格式化时间
    let timeFormatted = ''
    if (meal.meal_time) {
      const date = new Date(meal.meal_time)
      const month = date.getMonth() + 1
      const day = date.getDate()
      const hour = date.getHours()
      const minute = date.getMinutes()
      timeFormatted = `${month}月${day}日 ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`
    }

    // 根据评分等级计算颜色类
    const getRatingColorClass = (rating) => {
      if (!rating) return ''
      const ratingLower = rating.toLowerCase()
      // 优秀/很好 - 绿色
      if (ratingLower.includes('优秀') || ratingLower.includes('excellent') || ratingLower.includes('很好')) {
        return 'rating-excellent'
      }
      // 良好/好 - 蓝色
      if (ratingLower.includes('良好') || ratingLower.includes('good') || ratingLower === '好') {
        return 'rating-good'
      }
      // 一般/中等/需改善 - 橙色
      if (ratingLower.includes('一般') || ratingLower.includes('fair') || ratingLower.includes('average') || ratingLower.includes('中等') || ratingLower.includes('需改善') || ratingLower.includes('待改善')) {
        return 'rating-fair'
      }
      // 较差/差/不佳 - 红色
      if (ratingLower.includes('较差') || ratingLower.includes('差') || ratingLower.includes('poor') || ratingLower.includes('bad') || ratingLower.includes('不佳') || ratingLower.includes('不健康')) {
        return 'rating-poor'
      }
      return ''
    }

    const nutritionAnalysis = meal.nutrition_analysis
      || meal.gemini_analysis?.nutrition_analysis
      || meal.analysis?.nutrition_analysis
      || {}
    const overallRating = nutritionAnalysis.overall_rating
      || meal.gemini_analysis?.nutrition_analysis?.overall_rating
      || meal.analysis?.nutrition_analysis?.overall_rating
      || ''
    const ratingColorClass = getRatingColorClass(overallRating)

    const mealId = meal.id || meal.meal_id
    const imageUnavailable = Boolean(this._unavailableMealImages?.has(String(mealId)))

    return {
      ...meal,
      id: mealId,
      meal_type_label: mealTypeMap[meal.meal_type] || meal.meal_type,
      meal_time_formatted: timeFormatted,
      total_calories: Math.round(meal.total_calories || 0),
      total_protein: (meal.total_protein || 0).toFixed(1),
      total_carbs: (meal.total_carbs || 0).toFixed(1),
      total_fat: (meal.total_fat || 0).toFixed(1),
      thumbnail_path: imageUnavailable ? '' : resolveApiUrl(meal.thumbnail_path),
      photo_path: resolveApiUrl(meal.photo_path),
      image_unavailable: imageUnavailable,
      overall_rating: overallRating,
      overall_score: nutritionAnalysis.overall_score,
      ratingColorClass: ratingColorClass  // 评分颜色类
    }
  },

  onMealImageError(event) {
    const mealId = event.currentTarget.dataset.mealId
    const mealKey = String(mealId)
    if (this._unavailableMealImages?.has(mealKey)) return

    const mealIndex = this.data.meals.findIndex(meal => String(meal.id) === mealKey)
    if (mealIndex < 0) return

    this._unavailableMealImages.add(mealKey)
    const app = getApp()
    if (!app.globalData.unavailableMealImages) app.globalData.unavailableMealImages = {}
    app.globalData.unavailableMealImages[mealKey] = true
    this.setData({
      [`meals[${mealIndex}].thumbnail_path`]: '',
      [`meals[${mealIndex}].image_unavailable`]: true
    })
  },

  /**
   * 根据当前时间自动选择餐次（仅早中晚，不包括加餐）
   */
  autoSelectMealType() {
    const now = new Date()
    const hour = now.getHours()

    let mealType = 'lunch' // 默认午餐

    if (hour >= 5 && hour < 10) {
      mealType = 'breakfast'  // 5:00 - 10:00 早餐
    } else if (hour >= 10 && hour < 15) {
      mealType = 'lunch'      // 10:00 - 15:00 午餐
    } else {
      mealType = 'dinner'     // 15:00 - 5:00 晚餐
    }

    console.log(`[Auto Select] Current hour: ${hour}, selected: ${mealType}`)
    this.setData({ selectedMealType: mealType })
  },

  /**
   * 选择餐次类型
   */
  selectMealType(e) {
    if (this.data.submittingPhoto) return
    const { type } = e.currentTarget.dataset
    console.log('Select meal type:', type)
    this.setData({ selectedMealType: type })
  },

  /**
   * 拍照上传
   */
  takePhoto() {
    if (this._uploadPromise || this.data.submittingPhoto) return
    const that = this
    this._mealIdsBeforeUpload = new Set(this.data.meals.map(meal => String(meal.id)))
    this.setData({ submittingPhoto: true, uploadStatusText: '正在选择图片…' })

    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      camera: 'back',
      sizeType: ['compressed'], // 使用压缩图
      success(res) {
        console.log('Choose image success:', res)
        const tempFiles = Array.isArray(res.tempFiles) ? res.tempFiles : []
        const tempFile = tempFiles[0]
        if (!tempFile?.tempFilePath) {
          if (that._isActive) that.setData({ submittingPhoto: false })
          wx.showToast({ title: '没有读取到图片', icon: 'none' })
          return
        }
        const filePath = tempFile.tempFilePath
        const fileSize = Number(tempFile.size) || 0
        const fileType = tempFile.fileType || 'image'

        console.log('Original image size:', fileSize, 'bytes (', (fileSize / 1024 / 1024).toFixed(2), 'MB)')
        console.log('File type:', fileType)

        // 检查文件大小，超过 10MB 拒绝（与后端限制一致）
        const maxSize = 10 * 1024 * 1024 // 10MB
        if (fileSize > maxSize) {
          const sizeMB = (fileSize / 1024 / 1024).toFixed(2)
          wx.showModal({
            title: '图片过大',
            content: `图片大小 ${sizeMB}MB 超过限制（10MB）`,
            showCancel: false
          })
          if (that._isActive) that.setData({ submittingPhoto: false })
          return
        }

        // 所有图片都先压缩以确保格式正确（转为标准 JPG）
        console.log('Converting and compressing image to JPG format...')
        that.setData({ uploadStatusText: '正在准备图片…' })
        that.compressImage(filePath, fileSize)
      },
      fail(err) {
        console.error('Choose image error:', err)
        if (that._isActive) that.setData({ submittingPhoto: false })
        if (err.errMsg !== 'chooseMedia:fail cancel') {
          wx.showToast({
            title: '选择照片失败',
            icon: 'none'
          })
        }
      }
    })
  },

  /**
   * 压缩图片 - 确保转换为标准 JPG 格式
   */
  compressImage(filePath, originalSize) {
    const that = this

    wx.showLoading({
      title: '处理中...',
      mask: true
    })

    // 先获取图片信息
    wx.getImageInfo({
      src: filePath,
      success(imgInfo) {
        console.log('Image info:', imgInfo)

        // 使用 wx.compressImage 压缩并转换格式
        wx.compressImage({
          src: filePath,
          quality: 80, // 提高质量到 80，确保图片清晰
          compressedWidth: imgInfo.width > 1920 ? 1920 : undefined, // 限制最大宽度
          compressedHeight: imgInfo.height > 1920 ? 1920 : undefined,
          success(res) {
            console.log('Compress success:', res.tempFilePath)

            wx.getFileInfo({
              filePath: res.tempFilePath,
              success(fileInfo) {
                const compressedSize = fileInfo.size
                const originalMB = (originalSize / 1024 / 1024).toFixed(2)
                const compressedMB = (compressedSize / 1024 / 1024).toFixed(2)
                console.log(`Processed: ${originalMB}MB -> ${compressedMB}MB`)

                wx.hideLoading()
                if (!that._isActive) return
                that.uploadImage(res.tempFilePath)
              },
              fail(err) {
                console.error('Get compressed file info error:', err)
                wx.hideLoading()
                // 获取文件信息失败，仍然使用压缩后的文件
                if (!that._isActive) return
                that.uploadImage(res.tempFilePath)
              }
            })
          },
          fail(err) {
            console.error('Compress error:', err)
            wx.hideLoading()
            if (that._isActive) that.setData({ submittingPhoto: false })

            // 压缩失败，显示错误
            wx.showModal({
              title: '处理失败',
              content: '图片处理失败，请重新选择或使用相机拍照',
              showCancel: false
            })
          }
        })
      },
      fail(err) {
        console.error('Get image info error:', err)
        wx.hideLoading()
        if (that._isActive) that.setData({ submittingPhoto: false })

        wx.showModal({
          title: '读取失败',
          content: '无法读取图片信息，请重新选择',
          showCancel: false
        })
      }
    })
  },

  /**
   * 上传图片
   */
  uploadImage(filePath) {
    if (this._uploadPromise) return this._uploadPromise

    const mealType = this.data.selectedMealType
    this._uploadStartedAt = Date.now()
    this.setData({ submittingPhoto: true, uploadStatusText: '正在上传并识别食物…' })

    const uploadPromise = uploadMeal(filePath, mealType, {
      mealTime: new Date(this._uploadStartedAt).toISOString(),
      notes: ''
    })
      .then(result => {
        if (!this._isActive) return result
        console.log('Upload meal success:', result)

        this.setData({ submittingPhoto: false })

        wx.showToast({
          title: '识图完成',
          icon: 'success'
        })

        clearCache('/api/v1/nutrition')
        wx.setStorageSync('nutritionNeedsRefresh', true)
        this.openUploadedMeal(result)
        return result
      })
      .catch(async err => {
        if (!this._isActive) return null
        console.error('Upload meal error:', err)

        if (err.code === 'TIMEOUT') {
          const recoveredMeal = await this.recoverMealAfterUploadTimeout(mealType)
          if (this._isActive) this.setData({ submittingPhoto: false })
          if (recoveredMeal) {
            this.openUploadedMeal(recoveredMeal)
            return recoveredMeal
          }
          if (!this._isActive) return null
          wx.showModal({
            title: '识图响应较慢',
            content: '识图响应较慢，系统可能仍在处理，请稍后刷新饮食记录。',
            showCancel: false
          })
          return null
        }

        this.setData({ submittingPhoto: false })

        let errorMessage = err.message || '请稍后重试'

        // 针对不同错误码提供友好提示
        if (err.code === -1) {
          // 网络错误
          errorMessage = err.message || '网络请求失败'
          if (err.detail) {
            console.error('Network error detail:', err.detail)
          }
        } else if (err.code === 413) {
          errorMessage = '图片文件过大（限制 10MB）'
        } else if (err.code === 500) {
          // 500 错误可能是图片格式问题
          if (err.message && err.message.includes('cannot identify')) {
            errorMessage = '图片格式不支持\n建议：\n1. 使用相机重新拍照\n2. 或选择 JPG/PNG 格式图片'
          } else {
            errorMessage = '服务器处理失败\n' + (err.message || '请稍后重试')
          }
        } else if (err.code === 401) {
          errorMessage = '登录已过期，请重新登录'
        } else if (err.code === 422) {
          errorMessage = '请求参数错误'
        }

        wx.showModal({
          title: '上传失败',
          content: errorMessage,
          showCancel: false
        })
        return null
      })
      .finally(() => {
        if (this._uploadPromise === uploadPromise) this._uploadPromise = null
      })

    this._uploadPromise = uploadPromise
    return uploadPromise
  },

  openUploadedMeal(meal) {
    const mealId = meal?.id || meal?.meal_id
    if (!mealId || !this._isActive) return

    const app = getApp()
    if (!app.globalData.pendingMealRecords) app.globalData.pendingMealRecords = {}
    app.globalData.pendingMealRecords[String(mealId)] = meal

    wx.navigateTo({
      url: `/pages/nutrition-detail/nutrition-detail?mealId=${mealId}`
    })
  },

  async recoverMealAfterUploadTimeout(mealType) {
    clearCache('/api/v1/nutrition')
    try {
      const { rawMeals = [] } = await this.loadRecentMeals(true)
      const beforeIds = this._mealIdsBeforeUpload || new Set()
      const recentThreshold = (this._uploadStartedAt || Date.now()) - 2 * 60 * 1000
      const recovered = rawMeals.find(meal => {
        const isNew = !beforeIds.has(String(meal.id || meal.meal_id))
        const sameType = !mealType || meal.meal_type === mealType
        const mealTime = new Date(meal.created_at || meal.meal_time || 0).getTime()
        return isNew && sameType && (!mealTime || mealTime >= recentThreshold)
      })

      if (recovered) {
        wx.setStorageSync('nutritionNeedsRefresh', true)
        return recovered
      }

      await Promise.all([
        this.loadTodaySummary().catch(() => null),
        this.loadWeeklyCoverage().catch(() => null)
      ])
      return null
    } catch (error) {
      console.warn('上传超时后检查餐食记录失败:', error)
      return null
    }
  },

  /**
   * 查看餐食详情
   */
  viewMealDetail(e) {
    const { mealId } = e.currentTarget.dataset
    console.log('View meal detail:', mealId)

    wx.navigateTo({
      url: `/pages/nutrition-detail/nutrition-detail?mealId=${mealId}`
    })
  },


  /**
   * 格式化日期为 YYYY-MM-DD
   */
  formatDate(date) {
    return formatLocalDate(date)
  }
})
