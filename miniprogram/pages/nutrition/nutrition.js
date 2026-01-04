// pages/nutrition/nutrition.js
const { uploadMeal, getMeals, getMealDetail, getNutritionDailySummary, deleteMeal } = require('../../utils/request.js')
const config = require('../../utils/config.js')

Page({
  data: {
    loading: true,
    analyzing: false,
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
    fatProgress: 0
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad(options) {
    console.log('Nutrition page loaded')
    this.initPage()
  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow() {
    // 从详情页返回时刷新列表
    if (this.data.meals.length > 0) {
      this.loadData()
    }
  },

  /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh() {
    console.log('Pull down refresh')
    // 下拉刷新时清除营养相关缓存
    const { clearCache } = require('../../utils/request.js')
    clearCache('/api/v1/nutrition')

    this.loadData().then(() => {
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

    await this.loadData()
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
  async loadData() {
    this.setData({ loading: true })

    try {
      await Promise.all([
        this.loadTodaySummary(),
        this.loadRecentMeals()
      ])

      // 前端计算今日餐数（确保准确）
      this.updateTodayMealCount()
    } catch (err) {
      console.error('Load data error:', err)
      wx.showToast({
        title: '加载失败',
        icon: 'none'
      })
    } finally {
      this.setData({ loading: false })
    }
  },

  /**
   * 加载今日营养汇总
   */
  async loadTodaySummary() {
    try {
      const today = this.formatDate(new Date())
      const summary = await getNutritionDailySummary(today)

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

      this.setData({
        todaySummary: {
          ...summary,
          total_calories: totalCalories,
          total_protein: totalProtein.toFixed(1),
          total_carbs: totalCarbs.toFixed(1),
          total_fat: totalFat.toFixed(1)
        },
        calorieProgress: calorieProgress,
        proteinProgress: proteinProgress,
        carbsProgress: carbsProgress,
        fatProgress: fatProgress
      })

      console.log('[Summary] Final todaySummary:', this.data.todaySummary)
    } catch (err) {
      console.warn('Load today summary error:', err)
      // 今日没有数据时不显示汇总卡片
      this.setData({
        todaySummary: null,
        calorieProgress: 0,
        proteinProgress: 0,
        carbsProgress: 0,
        fatProgress: 0
      })
    }
  },

  /**
   * 加载最近餐食记录
   */
  async loadRecentMeals() {
    try {
      const result = await getMeals({
        page: 1,
        page_size: this.data.pageSize
      })

      // 调试：显示 API 返回的图片路径
      if (result.meals && result.meals.length > 0) {
        console.log('[List] First meal photo_path:', result.meals[0].photo_path)
        console.log('[List] First meal thumbnail_path:', result.meals[0].thumbnail_path)
      }

      const meals = (result.meals || []).map(meal => this.formatMealItem(meal))

      this.setData({
        meals,
        currentPage: 1,
        hasMore: result.total > this.data.pageSize
      })
    } catch (err) {
      console.error('Load recent meals error:', err)
      this.setData({ meals: [] })
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

      const moreMeals = (result.meals || []).map(meal => this.formatMealItem(meal))

      this.setData({
        meals: [...this.data.meals, ...moreMeals],
        currentPage: nextPage,
        hasMore: result.total > nextPage * this.data.pageSize
      })
    } catch (err) {
      console.error('Load more meals error:', err)
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

    // 处理图片路径 - 如果是相对路径，拼接为完整 URL
    const getFullImageUrl = (path) => {
      if (!path) return ''
      if (path.startsWith('http://') || path.startsWith('https://')) {
        return path
      }
      // 相对路径，拼接域名（确保路径以 / 开头）
      const normalizedPath = path.startsWith('/') ? path : '/' + path
      const fullUrl = config.API_BASE_URL + normalizedPath
      console.log('[List] Full thumbnail URL:', fullUrl)
      return fullUrl
    }

    // 获取AI模型名称（尝试多个可能的字段名）
    const aiModel = meal.model_name || meal.ai_model || meal.gemini_model ||
                    (meal.gemini_analysis && meal.gemini_analysis.model) ||
                    ''

    // 调试：显示模型名称
    if (aiModel) {
      console.log('[List] Meal model:', aiModel)
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

    const overallRating = meal.gemini_analysis?.nutrition_analysis?.overall_rating || ''
    const ratingColorClass = getRatingColorClass(overallRating)

    return {
      ...meal,
      meal_type_label: mealTypeMap[meal.meal_type] || meal.meal_type,
      meal_time_formatted: timeFormatted,
      total_calories: Math.round(meal.total_calories || 0),
      total_protein: (meal.total_protein || 0).toFixed(1),
      total_carbs: (meal.total_carbs || 0).toFixed(1),
      total_fat: (meal.total_fat || 0).toFixed(1),
      thumbnail_path: getFullImageUrl(meal.thumbnail_path),
      photo_path: getFullImageUrl(meal.photo_path),
      model_name: aiModel,  // 统一使用 model_name 字段
      ratingColorClass: ratingColorClass  // 评分颜色类
    }
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
    const { type } = e.currentTarget.dataset
    console.log('Select meal type:', type)
    this.setData({ selectedMealType: type })
  },

  /**
   * 拍照上传
   */
  takePhoto() {
    const that = this

    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      camera: 'back',
      sizeType: ['compressed'], // 使用压缩图
      success(res) {
        console.log('Choose image success:', res)
        const tempFile = res.tempFiles[0]
        const filePath = tempFile.tempFilePath
        const fileSize = tempFile.size
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
          return
        }

        // 所有图片都先压缩以确保格式正确（转为标准 JPG）
        console.log('Converting and compressing image to JPG format...')
        that.compressImage(filePath, fileSize)
      },
      fail(err) {
        console.error('Choose image error:', err)
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
                that.uploadImage(res.tempFilePath)
              },
              fail(err) {
                console.error('Get compressed file info error:', err)
                wx.hideLoading()
                // 获取文件信息失败，仍然使用压缩后的文件
                that.uploadImage(res.tempFilePath)
              }
            })
          },
          fail(err) {
            console.error('Compress error:', err)
            wx.hideLoading()

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
    const that = this

    // 显示分析中弹窗
    that.setData({ analyzing: true })

    // 上传并分析
    uploadMeal(filePath, that.data.selectedMealType)
      .then(result => {
        console.log('Upload meal success:', result)

        // 关闭分析中弹窗
        that.setData({ analyzing: false })

        wx.showToast({
          title: '分析完成',
          icon: 'success'
        })

        // 刷新数据
        that.loadData()

        // 跳转到详情页查看完整分析结果
        setTimeout(() => {
          wx.navigateTo({
            url: `/pages/nutrition-detail/nutrition-detail?mealId=${result.id}`
          })
        }, 1000)
      })
      .catch(err => {
        console.error('Upload meal error:', err)
        that.setData({ analyzing: false })

        let errorMessage = err.message || '请稍后重试'

        // 针对不同错误码提供友好提示
        if (err.code === -1) {
          // 网络错误
          errorMessage = err.message || '网络请求失败'
          if (err.detail) {
            console.error('Network error detail:', err.detail)
          }
        } else if (err.code === 413) {
          errorMessage = '图片文件过大（限制 10MB）\n建议选择较小的图片'
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
          title: '分析失败',
          content: errorMessage,
          showCancel: false
        })
      })
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
   * 更新今日餐数统计
   */
  updateTodayMealCount() {
    if (!this.data.todaySummary) {
      return
    }

    const today = this.formatDate(new Date())

    // 统计今天的餐数
    const todayMeals = this.data.meals.filter(meal => {
      if (!meal.meal_time) return false
      const mealDate = this.formatDate(new Date(meal.meal_time))
      return mealDate === today
    })

    const mealCount = todayMeals.length

    console.log('[Summary] Today meals count:', mealCount)

    // 更新 todaySummary 中的 meals_count
    this.setData({
      'todaySummary.meals_count': mealCount
    })
  },

  /**
   * 格式化日期为 YYYY-MM-DD
   */
  formatDate(date) {
    const year = date.getFullYear()
    const month = (date.getMonth() + 1).toString().padStart(2, '0')
    const day = date.getDate().toString().padStart(2, '0')
    return `${year}-${month}-${day}`
  }
})
