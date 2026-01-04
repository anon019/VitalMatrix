// pages/nutrition-detail/nutrition-detail.js
const { getMealDetail, deleteMeal } = require('../../utils/request.js')
const config = require('../../utils/config.js')

Page({
  data: {
    loading: true,
    mealId: '',
    meal: null,
    analysis: null,
    mealTypeLabel: '',
    mealTimeFormatted: '',
    aiModel: '',  // AI模型名称
    generatingPoster: false,  // 是否正在生成海报
    showPosterPreview: false, // 是否显示海报预览
    posterPath: '',  // 海报临时路径
    ratingBadgeColor: '',  // 评级徽章颜色
    ratingScoreColor: '',  // 评分数字颜色
    carbsRatingColor: '#10B981',   // 碳水评级颜色
    proteinRatingColor: '#10B981', // 蛋白质评级颜色
    fatRatingColor: '#10B981',     // 脂肪评级颜色
    carbsRatingClass: '',          // 碳水评级样式类
    proteinRatingClass: '',        // 蛋白质评级样式类
    fatRatingClass: '',            // 脂肪评级样式类
    formattedNextMealMenu: ''      // 格式化后的下一餐推荐
  },

  // 根据综合评级获取颜色
  getRatingColor(rating) {
    const colorMap = {
      '优秀': '#4CAF50',
      '良好': '#2196F3',
      '一般': '#FF9800',
      '需改善': '#FF9800',
      '较差': '#F44336'
    }
    return colorMap[rating] || '#4CAF50'
  },

  // 格式化下一餐推荐文本，添加换行（支持多餐推荐）
  formatNextMealMenu(text) {
    if (!text) return ''
    let formatted = text

    // 在多餐推荐标题前换行（如 "早餐推荐"、"午餐推荐" 等）
    formatted = formatted.replace(/([。！\s])([早午晚]餐推荐|加餐推荐)/g, '$1\n\n🍽️ $2')
    formatted = formatted.replace(/([。！\s])(下一餐推荐（[早午晚加]餐）)/g, '$1\n\n🍽️ $2')

    // 在数字序号前换行（如 "1." "2." 等）
    formatted = formatted.replace(/(\d+)\.\s*/g, '\n　$1. ')

    // 在 "主食建议:" 等关键词前换行
    formatted = formatted.replace(/(主食建议[:：])/g, '\n\n💡 $1')
    formatted = formatted.replace(/(蛋白质建议[:：])/g, '\n\n💡 $1')
    formatted = formatted.replace(/(注意[:：])/g, '\n\n⚠️ $1')
    formatted = formatted.replace(/(温馨提示[:：])/g, '\n\n💡 $1')

    // 去除开头可能产生的多余换行和空格
    return formatted.trim().replace(/^\n+/, '')
  },

  // 根据营养分析评级获取颜色
  getNutritionRatingColor(rating) {
    // 正面评级 - 绿色
    if (['适量', '适中', '合理', '正常', '充足', '均衡'].includes(rating)) {
      return '#10B981'
    }
    // 警告评级 - 橙色
    if (['偏高', '偏低', '过甜', '过咸', '过量', '稍高', '稍低'].includes(rating)) {
      return '#F59E0B'
    }
    // 危险评级 - 红色
    if (['严重偏高', '严重不足', '严重过量', '过高', '过低'].includes(rating)) {
      return '#EF4444'
    }
    // 提示评级 - 蓝色
    if (['不足', '缺乏'].includes(rating)) {
      return '#3B82F6'
    }
    // 默认橙色（未知评级按警告处理）
    return '#F59E0B'
  },

  // 根据营养分析评级获取样式类
  getNutritionRatingClass(rating) {
    // 正面评级 - 绿色
    if (['适量', '适中', '合理', '正常', '充足', '均衡'].includes(rating)) {
      return 'rating-good'
    }
    // 警告评级 - 橙色
    if (['偏高', '偏低', '过甜', '过咸', '过量', '稍高', '稍低'].includes(rating)) {
      return 'rating-warning'
    }
    // 危险评级 - 红色
    if (['严重偏高', '严重不足', '严重过量', '过高', '过低'].includes(rating)) {
      return 'rating-danger'
    }
    // 提示评级 - 蓝色
    if (['不足', '缺乏'].includes(rating)) {
      return 'rating-info'
    }
    // 默认橙色（未知评级按警告处理）
    return 'rating-warning'
  },

  onLoad(options) {
    const { mealId } = options
    console.log('Nutrition detail page loaded, mealId:', mealId)

    if (!mealId) {
      wx.showToast({
        title: '参数错误',
        icon: 'none'
      })
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
      return
    }

    this.setData({ mealId })
    this.loadMealDetail()
  },

  async loadMealDetail() {
    this.setData({ loading: true })

    try {
      const meal = await getMealDetail(this.data.mealId)

      // ===== 调试日志：API 返回的图片路径 =====
      console.log('[Detail] API photo_path:', meal.photo_path)
      console.log('[Detail] API thumbnail_path:', meal.thumbnail_path)

      const mealTypeMap = {
        breakfast: '早餐',
        lunch: '午餐',
        dinner: '晚餐',
        snack: '加餐'
      }

      let timeFormatted = ''
      if (meal.meal_time) {
        const date = new Date(meal.meal_time)
        const year = date.getFullYear()
        const month = date.getMonth() + 1
        const day = date.getDate()
        const hour = date.getHours()
        const minute = date.getMinutes()
        timeFormatted = year + '年' + month + '月' + day + '日 ' + hour.toString().padStart(2, '0') + ':' + minute.toString().padStart(2, '0')
      }

      // 处理图片路径 - 如果是相对路径，拼接为完整 URL
      const getFullImageUrl = (path) => {
        if (!path) {
          console.warn('[Detail] Image path is empty!')
          return ''
        }
        if (path.startsWith('http://') || path.startsWith('https://')) {
          return path
        }
        // 相对路径，拼接域名（确保路径以 / 开头）
        const normalizedPath = path.startsWith('/') ? path : '/' + path
        const fullUrl = config.API_BASE_URL + normalizedPath
        console.log('[Detail] Full image URL:', fullUrl)
        return fullUrl
      }

      // 获取AI模型名称（尝试多个可能的字段名）
      const aiModel = meal.model_name || meal.ai_model || meal.gemini_model ||
                      (meal.gemini_analysis && meal.gemini_analysis.model) ||
                      ''

      const photoPath = getFullImageUrl(meal.photo_path)
      const thumbnailPath = getFullImageUrl(meal.thumbnail_path)

      console.log('Final photo_path:', photoPath)
      console.log('Final thumbnail_path:', thumbnailPath)

      // 获取评级颜色
      const overallRating = meal.gemini_analysis?.nutrition_analysis?.overall_rating || '优秀'
      const ratingColor = this.getRatingColor(overallRating)

      // 获取营养分析各项评级颜色
      const nutritionAnalysis = meal.gemini_analysis?.nutrition_analysis
      const carbsRating = nutritionAnalysis?.carbs_analysis?.rating || ''
      const proteinRating = nutritionAnalysis?.protein_analysis?.rating || ''
      const fatRating = nutritionAnalysis?.fat_analysis?.rating || ''

      // 格式化下一餐推荐文本
      const nextMealMenu = meal.gemini_analysis?.recommendations?.next_meal_menu || ''
      const formattedNextMealMenu = this.formatNextMealMenu(nextMealMenu)

      this.setData({
        meal: {
          ...meal,
          total_calories: Math.round(meal.total_calories || 0),
          total_protein: (meal.total_protein || 0).toFixed(1),
          total_carbs: (meal.total_carbs || 0).toFixed(1),
          total_fat: (meal.total_fat || 0).toFixed(1),
          total_fiber: (meal.total_fiber || 0).toFixed(1),
          photo_path: photoPath,
          thumbnail_path: thumbnailPath
        },
        analysis: meal.gemini_analysis || null,
        mealTypeLabel: mealTypeMap[meal.meal_type] || meal.meal_type,
        mealTimeFormatted: timeFormatted,
        aiModel: aiModel,
        ratingBadgeColor: ratingColor,
        ratingScoreColor: ratingColor,
        carbsRatingColor: this.getNutritionRatingColor(carbsRating),
        proteinRatingColor: this.getNutritionRatingColor(proteinRating),
        fatRatingColor: this.getNutritionRatingColor(fatRating),
        carbsRatingClass: this.getNutritionRatingClass(carbsRating),
        proteinRatingClass: this.getNutritionRatingClass(proteinRating),
        fatRatingClass: this.getNutritionRatingClass(fatRating),
        formattedNextMealMenu: formattedNextMealMenu,
        loading: false
      })

      console.log('SetData complete, meal object:', this.data.meal)
    } catch (err) {
      console.error('Load meal detail error:', err)
      this.setData({ loading: false })

      wx.showModal({
        title: '加载失败',
        content: err.message || '请稍后重试',
        showCancel: false,
        success: () => {
          wx.navigateBack()
        }
      })
    }
  },

  deleteMeal() {
    wx.showModal({
      title: '确认删除',
      content: '删除后将无法恢复，确认删除这条记录吗？',
      confirmText: '删除',
      confirmColor: '#F44336',
      success: (res) => {
        if (res.confirm) {
          this.performDelete()
        }
      }
    })
  },

  async performDelete() {
    wx.showLoading({
      title: '删除中...',
      mask: true
    })

    try {
      await deleteMeal(this.data.mealId)
      console.log('Meal deleted successfully')

      wx.hideLoading()
      wx.showToast({
        title: '删除成功',
        icon: 'success'
      })

      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
    } catch (err) {
      console.error('Delete meal error:', err)
      wx.hideLoading()

      wx.showModal({
        title: '删除失败',
        content: err.message || '请稍后重试',
        showCancel: false
      })
    }
  },

  onImageLoad(e) {
    console.log('[Detail] ✅ Image loaded successfully')
  },

  onImageError(e) {
    console.error('[Detail] ❌ Image load failed:', e.detail.errMsg)
    console.error('[Detail] Failed URL:', this.data.meal.photo_path)
    wx.showToast({
      title: '图片加载失败',
      icon: 'none',
      duration: 2000
    })
  },

  /**
   * 生成分享海报
   */
  async generatePoster() {
    if (!this.data.meal || !this.data.analysis) {
      wx.showToast({
        title: '数据未加载完成',
        icon: 'none'
      })
      return
    }

    this.setData({ generatingPoster: true })

    try {
      const posterPath = await this.drawPoster()
      console.log('海报生成成功:', posterPath)

      this.setData({
        generatingPoster: false,
        showPosterPreview: true,
        posterPath
      })
    } catch (err) {
      console.error('生成海报失败:', err)
      this.setData({ generatingPoster: false })

      wx.showToast({
        title: '生成失败，请重试',
        icon: 'none'
      })
    }
  },

  /**
   * 预估海报总高度 - 与详情页UI一致（带渐变头部）
   */
  estimatePosterHeight(ctx, canvasWidth, padding) {
    const cardGap = 16
    const headerHeight = 40  // 渐变头部高度
    let totalHeight = 16  // 顶部留白

    // 1. 餐食照片区域
    if (this.data.meal?.photo_path) {
      totalHeight += 220 + cardGap
    }

    // 2. 营养成分卡片（绿色头部）
    totalHeight += 160 + cardGap

    // 3. 综合评价卡片（金黄色头部）
    if (this.data.analysis?.nutrition_analysis) {
      totalHeight += 120 + cardGap
    }

    // 4. 识别的食物卡片（蓝色头部）
    const foods = this.data.analysis?.identified_foods || []
    if (foods.length > 0) {
      totalHeight += headerHeight + 20 + foods.length * 97 + 20 + cardGap
    }

    // 5. 营养分析卡片（紫色头部）
    if (this.data.analysis?.nutrition_analysis) {
      totalHeight += headerHeight + 20 + 3 * 95 + 20 + cardGap
    }

    // 6. 健康洞察卡片（青色头部）
    const insights = this.data.analysis?.health_insights
    if (insights) {
      let insightHeight = headerHeight + 20  // 头部 + 间距
      const strengths = insights.strengths || []
      const weaknesses = insights.weaknesses || []
      const risks = insights.risk_factors || []
      ctx.font = '12px sans-serif'

      if (strengths.length > 0) {
        insightHeight += 25
        strengths.forEach(s => {
          const lines = this.wrapText(ctx, s, canvasWidth - padding * 2 - 60)
          insightHeight += lines.length * 18 + 12
        })
      }
      if (weaknesses.length > 0) {
        insightHeight += 25
        weaknesses.forEach(w => {
          const lines = this.wrapText(ctx, w, canvasWidth - padding * 2 - 60)
          insightHeight += lines.length * 18 + 12
        })
      }
      if (risks.length > 0) {
        insightHeight += 25
        risks.forEach(r => {
          const lines = this.wrapText(ctx, r, canvasWidth - padding * 2 - 60)
          insightHeight += lines.length * 18 + 12
        })
      }
      totalHeight += insightHeight + 20 + cardGap
    }

    // 7. 饮食建议卡片（绿色头部）
    const recommendations = this.data.analysis?.recommendations
    if (recommendations) {
      let recHeight = headerHeight + 20  // 头部 + 间距

      // 总结
      if (recommendations.summary) {
        ctx.font = '13px sans-serif'
        const lines = this.wrapText(ctx, recommendations.summary, canvasWidth - padding * 2 - 60)
        recHeight += lines.length * 18 + 30
      }

      // 行动清单
      const actionItems = recommendations.action_items || []
      if (actionItems.length > 0) {
        recHeight += 30
        actionItems.forEach(item => {
          ctx.font = '12px sans-serif'
          const lines = this.wrapText(ctx, item.rationale || '', canvasWidth - padding * 2 - 70)
          recHeight += 30 + lines.length * 16 + 20
        })
      }

      // 下一餐推荐
      const nextMeals = recommendations.next_meals || []
      if (nextMeals.length > 0) {
        recHeight += 30
        nextMeals.forEach(meal => {
          recHeight += 50
          const dishes = meal.dishes || []
          dishes.forEach(dish => {
            recHeight += 120
          })
          if (meal.reason) recHeight += 40
        })
      }

      totalHeight += recHeight + 16 + cardGap
    }

    // 底部留白
    totalHeight += 30

    return totalHeight + 100  // 额外余量
  },

  /**
   * Canvas绘制海报 - 与详情页UI风格一致
   */
  async drawPoster() {
    return new Promise((resolve, reject) => {
      const query = wx.createSelectorQuery()
      query.select('#posterCanvas')
        .fields({ node: true, size: true })
        .exec(async (res) => {
          if (!res || !res[0]) {
            reject(new Error('Canvas节点获取失败'))
            return
          }

          const canvas = res[0].node
          const ctx = canvas.getContext('2d')
          const dpr = wx.getSystemInfoSync().pixelRatio

          // 画布宽度
          const canvasWidth = 375
          const padding = 16
          const cardGap = 16

          // 设置Canvas尺寸
          canvas.width = canvasWidth * dpr

          // 预估总高度
          const estimatedHeight = this.estimatePosterHeight(ctx, canvasWidth, padding)
          canvas.height = estimatedHeight * dpr

          // 缩放上下文
          ctx.scale(dpr, dpr)

          // 背景色 - 自然餐桌主题温暖米色
          ctx.fillStyle = '#FAF7F2'
          ctx.fillRect(0, 0, canvasWidth, estimatedHeight)

          let currentY = 16
          const contentWidth = canvasWidth - padding * 2

          // ========== 1. 餐食照片 ==========
          if (this.data.meal.photo_path) {
            try {
              const photoUrl = this.data.meal.photo_path.startsWith('http')
                ? this.data.meal.photo_path
                : `${config.API_BASE_URL}${this.data.meal.photo_path}`

              const img = canvas.createImage()
              await new Promise((resolveImg, rejectImg) => {
                img.onload = resolveImg
                img.onerror = rejectImg
                img.src = photoUrl
              })

              const photoHeight = 220
              // 绘制圆角照片
              ctx.save()
              this.drawRoundRect(ctx, padding, currentY, contentWidth, photoHeight, 16, '#000')
              ctx.clip()

              const imgRatio = img.width / img.height
              const boxRatio = contentWidth / photoHeight
              let drawWidth, drawHeight, drawX, drawY

              if (imgRatio > boxRatio) {
                drawHeight = photoHeight
                drawWidth = photoHeight * imgRatio
                drawX = padding + (contentWidth - drawWidth) / 2
                drawY = currentY
              } else {
                drawWidth = contentWidth
                drawHeight = contentWidth / imgRatio
                drawX = padding
                drawY = currentY + (photoHeight - drawHeight) / 2
              }

              ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight)

              // 底部渐变遮罩
              const gradient = ctx.createLinearGradient(0, currentY + photoHeight - 60, 0, currentY + photoHeight)
              gradient.addColorStop(0, 'rgba(0,0,0,0)')
              gradient.addColorStop(1, 'rgba(0,0,0,0.7)')
              ctx.fillStyle = gradient
              ctx.fillRect(padding, currentY + photoHeight - 60, contentWidth, 60)

              // 餐食类型和时间
              ctx.fillStyle = '#fff'
              ctx.font = 'bold 20px sans-serif'
              ctx.fillText(this.data.mealTypeLabel, padding + 16, currentY + photoHeight - 28)
              ctx.font = '12px sans-serif'
              ctx.fillStyle = 'rgba(255,255,255,0.9)'
              ctx.textAlign = 'right'
              ctx.fillText(this.data.mealTimeFormatted, canvasWidth - padding - 16, currentY + photoHeight - 28)
              ctx.textAlign = 'left'

              ctx.restore()
              currentY += photoHeight + cardGap
            } catch (err) {
              console.error('图片加载失败:', err)
            }
          }

          // ========== 2. 营养成分卡片 - 绿色主题 ==========
          currentY = this.drawNutritionSummary(ctx, canvasWidth, padding, currentY)
          currentY += cardGap

          // ========== 3. 综合评价卡片 - 金黄色主题 ==========
          if (this.data.analysis?.nutrition_analysis) {
            currentY = this.drawOverallRating(ctx, canvasWidth, padding, currentY)
            currentY += cardGap
          }

          // ========== 4. 识别的食物卡片 - 蓝色主题 ==========
          currentY = this.drawFoodList(ctx, canvasWidth, padding, currentY)
          currentY += cardGap

          // ========== 5. 营养分析卡片 - 紫色主题 ==========
          currentY = this.drawNutritionAnalysis(ctx, canvasWidth, padding, currentY)
          currentY += cardGap

          // ========== 6. 健康洞察卡片 - 青色主题 ==========
          currentY = this.drawHealthInsights(ctx, canvasWidth, padding, currentY)
          currentY += cardGap

          // ========== 7. 饮食建议卡片 - 绿色主题 ==========
          currentY = this.drawRecommendations(ctx, canvasWidth, padding, currentY)

          // 底部留白
          currentY += 20

          const actualHeight = currentY
          console.log('海报实际高度:', actualHeight)

          // 导出图片
          wx.canvasToTempFilePath({
            canvas,
            x: 0,
            y: 0,
            width: canvasWidth,
            height: actualHeight,
            destWidth: canvasWidth * dpr,
            destHeight: actualHeight * dpr,
            success: (res) => {
              console.log('海报导出成功')
              resolve(res.tempFilePath)
            },
            fail: (err) => {
              console.error('海报导出失败:', err)
              reject(err)
            }
          })
        })
    })
  },

  // 辅助函数：绘制圆角矩形
  drawRoundRect(ctx, x, y, width, height, radius, fillColor, strokeColor) {
    ctx.beginPath()
    ctx.moveTo(x + radius, y)
    ctx.lineTo(x + width - radius, y)
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
    ctx.lineTo(x + width, y + height - radius)
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
    ctx.lineTo(x + radius, y + height)
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
    ctx.lineTo(x, y + radius)
    ctx.quadraticCurveTo(x, y, x + radius, y)
    ctx.closePath()

    if (fillColor) {
      ctx.fillStyle = fillColor
      ctx.fill()
    }
    if (strokeColor) {
      ctx.strokeStyle = strokeColor
      ctx.lineWidth = 2
      ctx.stroke()
    }
  },

  // 绘制营养成分 - 绿色主题
  drawNutritionSummary(ctx, canvasWidth, padding, startY) {
    const meal = this.data.meal
    let currentY = startY
    const contentWidth = canvasWidth - padding * 2

    // 卡片背景
    const cardHeight = 160
    const headerHeight = 40

    // 绘制圆角卡片背景
    this.drawRoundRect(ctx, padding, currentY, contentWidth, cardHeight, 16, '#ffffff')

    // 绘制渐变头部（绿色主题）
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(padding + 16, currentY)
    ctx.lineTo(padding + contentWidth - 16, currentY)
    ctx.quadraticCurveTo(padding + contentWidth, currentY, padding + contentWidth, currentY + 16)
    ctx.lineTo(padding + contentWidth, currentY + headerHeight)
    ctx.lineTo(padding, currentY + headerHeight)
    ctx.lineTo(padding, currentY + 16)
    ctx.quadraticCurveTo(padding, currentY, padding + 16, currentY)
    ctx.closePath()

    // 绿色渐变
    const gradient = ctx.createLinearGradient(padding, currentY, padding + contentWidth, currentY + headerHeight)
    gradient.addColorStop(0, '#10B981')
    gradient.addColorStop(1, '#059669')
    ctx.fillStyle = gradient
    ctx.fill()
    ctx.restore()

    // 白色标题
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 16px sans-serif'
    ctx.fillText('营养成分', padding + 16, currentY + 26)
    currentY += headerHeight + 20

    // 4个营养卡片（确保不溢出）
    const innerWidth = contentWidth - 32  // 左右各16padding
    const gap = 6
    const itemWidth = Math.floor((innerWidth - gap * 3) / 4)  // 向下取整

    // 营养数据配置 - 自然餐桌主题颜色
    const nutrients = [
      { value: meal.total_calories, label: '热量', unit: 'kcal', color: '#E85D04', bgColor: 'rgba(232, 93, 4, 0.08)' },
      { value: meal.total_protein, label: '蛋白', unit: 'g', color: '#9D4EDD', bgColor: 'rgba(157, 78, 221, 0.08)' },
      { value: meal.total_carbs, label: '碳水', unit: 'g', color: '#C59545', bgColor: 'rgba(233, 196, 106, 0.12)' },
      { value: meal.total_fat, label: '脂肪', unit: 'g', color: '#52B788', bgColor: 'rgba(82, 183, 136, 0.08)' }
    ]

    nutrients.forEach((nutrient, index) => {
      const x = padding + 16 + index * (itemWidth + gap)

      // 小卡片背景（使用语义化浅色）
      this.drawRoundRect(ctx, x, currentY, itemWidth, 70, 8, nutrient.bgColor)

      // 数值（居中，使用语义化颜色）
      ctx.fillStyle = nutrient.color
      ctx.font = 'bold 16px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'

      // 处理数值显示，避免溢出
      let displayValue = String(nutrient.value)
      const valueMetrics = ctx.measureText(displayValue)
      if (valueMetrics.width > itemWidth - 4) {
        // 数值太长，缩小字号
        ctx.font = 'bold 14px sans-serif'
      }
      ctx.fillText(displayValue, x + itemWidth / 2, currentY + 22)

      // 单位（较小）
      ctx.font = '10px sans-serif'
      ctx.fillStyle = '#9C8E7C'
      ctx.fillText(nutrient.unit, x + itemWidth / 2, currentY + 40)

      // 标签
      ctx.fillStyle = '#6B5E4C'
      ctx.font = '10px sans-serif'
      ctx.fillText(nutrient.label, x + itemWidth / 2, currentY + 58)

      ctx.textAlign = 'left'
      ctx.textBaseline = 'alphabetic'
    })

    return startY + cardHeight + 4
  },

  // 绘制综合评分 - 金黄色主题
  drawOverallRating(ctx, canvasWidth, padding, startY) {
    const nutrition = this.data.analysis.nutrition_analysis
    if (!nutrition) return startY

    let currentY = startY
    const contentWidth = canvasWidth - padding * 2

    // 卡片背景
    const cardHeight = 120
    const headerHeight = 40
    this.drawRoundRect(ctx, padding, currentY, contentWidth, cardHeight, 16, '#ffffff')

    // 绘制渐变头部（金黄色主题）
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(padding + 16, currentY)
    ctx.lineTo(padding + contentWidth - 16, currentY)
    ctx.quadraticCurveTo(padding + contentWidth, currentY, padding + contentWidth, currentY + 16)
    ctx.lineTo(padding + contentWidth, currentY + headerHeight)
    ctx.lineTo(padding, currentY + headerHeight)
    ctx.lineTo(padding, currentY + 16)
    ctx.quadraticCurveTo(padding, currentY, padding + 16, currentY)
    ctx.closePath()

    const gradient = ctx.createLinearGradient(padding, currentY, padding + contentWidth, currentY + headerHeight)
    gradient.addColorStop(0, '#F59E0B')
    gradient.addColorStop(1, '#D97706')
    ctx.fillStyle = gradient
    ctx.fill()
    ctx.restore()

    // 白色标题
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 16px sans-serif'
    ctx.fillText('综合评价', padding + 16, currentY + 26)

    // 计算内容区域的垂直中心点
    const contentAreaTop = currentY + headerHeight
    const contentAreaHeight = cardHeight - headerHeight  // 80px
    const contentCenterY = contentAreaTop + contentAreaHeight / 2  // 垂直居中位置

    // 评级徽章（优化颜色方案，避免与营养数据蓝色冲突）
    const ratingColors = {
      '优秀': '#10B981',     // 绿色 - 最好
      '良好': '#14B8A6',     // 青色 - 良好（避免与营养数据蓝色冲突）
      '一般': '#F59E0B',     // 橙色 - 中等
      '需改善': '#F97316',   // 深橙色 - 需要改进
      '较差': '#EF4444'      // 红色 - 最差
    }
    const rating = nutrition.overall_rating || '一般'
    const ratingColor = ratingColors[rating] || '#999999'

    const badgeWidth = 80
    const badgeHeight = 32
    // 徽章垂直居中
    this.drawRoundRect(ctx, padding + 16, contentCenterY - badgeHeight / 2, badgeWidth, badgeHeight, 16, ratingColor)

    // 评级文字（白色，居中）
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 15px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(rating, padding + 16 + badgeWidth / 2, contentCenterY)

    // 分数（右侧，大字号，垂直居中）
    ctx.fillStyle = ratingColor
    ctx.font = 'bold 32px sans-serif'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(`${nutrition.overall_score || 0}`, canvasWidth - padding - 50, contentCenterY)

    // "分" 字（小一点）
    ctx.font = '16px sans-serif'
    ctx.fillStyle = '#999'
    ctx.fillText('分', canvasWidth - padding - 16, contentCenterY)

    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'

    return startY + cardHeight + 4
  },

  // 绘制食物列表 - 蓝色主题
  drawFoodList(ctx, canvasWidth, padding, startY) {
    const foods = this.data.analysis?.identified_foods
    if (!foods || foods.length === 0) return startY

    let currentY = startY
    const contentWidth = canvasWidth - padding * 2

    // 卡片背景
    const itemHeight = 85
    const headerHeight = 40
    const cardHeight = headerHeight + 20 + foods.length * (itemHeight + 12) + 10
    this.drawRoundRect(ctx, padding, currentY, contentWidth, cardHeight, 16, '#ffffff')

    // 绘制渐变头部（蓝色主题）
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(padding + 16, currentY)
    ctx.lineTo(padding + contentWidth - 16, currentY)
    ctx.quadraticCurveTo(padding + contentWidth, currentY, padding + contentWidth, currentY + 16)
    ctx.lineTo(padding + contentWidth, currentY + headerHeight)
    ctx.lineTo(padding, currentY + headerHeight)
    ctx.lineTo(padding, currentY + 16)
    ctx.quadraticCurveTo(padding, currentY, padding + 16, currentY)
    ctx.closePath()

    const gradient = ctx.createLinearGradient(padding, currentY, padding + contentWidth, currentY + headerHeight)
    gradient.addColorStop(0, '#3B82F6')
    gradient.addColorStop(1, '#2563EB')
    ctx.fillStyle = gradient
    ctx.fill()
    ctx.restore()

    // 白色标题
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 16px sans-serif'
    ctx.fillText('识别的食物', padding + 16, currentY + 26)
    currentY += headerHeight + 20

    foods.forEach((food, index) => {
      // 食物卡片背景（淡绿色 - 自然餐桌主题）
      this.drawRoundRect(ctx, padding + 16, currentY, canvasWidth - padding * 2 - 32, itemHeight, 10, '#F0FDF4')

      // 左侧绿色条
      ctx.fillStyle = '#22C55E'
      ctx.fillRect(padding + 16, currentY, 4, itemHeight)

      // 食物名称（自然餐桌主题深色）
      ctx.fillStyle = '#2C2417'
      ctx.font = 'bold 15px sans-serif'
      ctx.fillText(food.name, padding + 32, currentY + 25)

      // 重量（右上）
      ctx.fillStyle = '#9C8E7C'
      ctx.font = '12px sans-serif'
      ctx.textAlign = 'right'
      ctx.fillText(`约 ${food.weight_g}g`, canvasWidth - padding - 30, currentY + 25)
      ctx.textAlign = 'left'

      // 热量（使用热量橙色）
      ctx.fillStyle = '#E85D04'
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText(`${food.calories} kcal`, padding + 32, currentY + 50)

      // 三大营养素（使用自然餐桌主题色）
      ctx.fillStyle = '#6B5E4C'
      ctx.font = '12px sans-serif'
      ctx.fillText(`蛋白 ${food.protein}g`, padding + 32, currentY + 68)
      ctx.fillText(`碳水 ${food.carbs}g`, padding + 120, currentY + 68)
      ctx.fillText(`脂肪 ${food.fat}g`, padding + 208, currentY + 68)

      currentY += itemHeight + 12
    })

    return startY + cardHeight + 4
  },

  // 绘制营养分析 - 紫色主题
  drawNutritionAnalysis(ctx, canvasWidth, padding, startY) {
    const nutrition = this.data.analysis?.nutrition_analysis
    if (!nutrition) return startY

    const cardStartY = startY
    let currentY = startY
    const contentWidth = canvasWidth - padding * 2
    const headerHeight = 40

    const items = [
      { label: '碳水化合物', data: nutrition.carbs_analysis, emoji: '🍚' },
      { label: '蛋白质', data: nutrition.protein_analysis, emoji: '🥩' },
      { label: '脂肪', data: nutrition.fat_analysis, emoji: '🥑' }
    ]

    // 预计算总高度
    currentY += headerHeight + 20  // 头部 + 间距
    ctx.font = '12px sans-serif'
    items.forEach(item => {
      if (item.data) {
        const lines = this.wrapText(ctx, item.data.comment || '', contentWidth - 56)
        const itemHeight = Math.max(80, 47 + lines.length * 16 + 10)
        currentY += itemHeight + 5
      }
    })

    const cardHeight = currentY - cardStartY + 15
    this.drawRoundRect(ctx, padding, cardStartY, contentWidth, cardHeight, 16, '#ffffff')

    // 绘制渐变头部（紫色主题）
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(padding + 16, cardStartY)
    ctx.lineTo(padding + contentWidth - 16, cardStartY)
    ctx.quadraticCurveTo(padding + contentWidth, cardStartY, padding + contentWidth, cardStartY + 16)
    ctx.lineTo(padding + contentWidth, cardStartY + headerHeight)
    ctx.lineTo(padding, cardStartY + headerHeight)
    ctx.lineTo(padding, cardStartY + 16)
    ctx.quadraticCurveTo(padding, cardStartY, padding + 16, cardStartY)
    ctx.closePath()

    const gradient = ctx.createLinearGradient(padding, cardStartY, padding + contentWidth, cardStartY + headerHeight)
    gradient.addColorStop(0, '#8B5CF6')
    gradient.addColorStop(1, '#7C3AED')
    ctx.fillStyle = gradient
    ctx.fill()
    ctx.restore()

    // 白色标题
    currentY = cardStartY
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 16px sans-serif'
    ctx.fillText('营养分析', padding + 16, currentY + 26)
    currentY += headerHeight + 20

    // 评级颜色方案（根据营养程度设计）
    const ratingColors = {
      // 绿色 - 理想状态
      '适量': '#10B981',
      '适中': '#10B981',
      '正常': '#10B981',
      '合理': '#10B981',
      '充足': '#10B981',
      '均衡': '#10B981',
      // 橙色 - 警告：偏高/偏多
      '偏高': '#F59E0B',
      '稍高': '#F59E0B',
      '过量': '#F59E0B',
      '过多': '#F59E0B',
      '过甜': '#F59E0B',
      '过咸': '#F59E0B',
      '稍多': '#F59E0B',
      // 蓝色 - 提示：偏低/不足
      '不足': '#3B82F6',
      '偏低': '#3B82F6',
      '稍低': '#3B82F6',
      '缺乏': '#3B82F6',
      '较少': '#3B82F6',
      // 红色 - 危险：严重超标
      '严重偏高': '#EF4444',
      '过高': '#EF4444',
      '超标': '#EF4444',
      // 紫色 - 严重缺乏
      '严重不足': '#7C3AED',
      '严重缺乏': '#7C3AED'
    }

    items.forEach(item => {
      if (!item.data) return

      // 计算item高度
      ctx.font = '12px sans-serif'
      const lines = this.wrapText(ctx, item.data.comment || '', canvasWidth - padding * 2 - 56)
      const itemHeight = Math.max(80, 47 + lines.length * 16 + 10)

      // item背景（使用自然餐桌主题浅色）
      this.drawRoundRect(ctx, padding + 16, currentY, canvasWidth - padding * 2 - 32, itemHeight, 10, '#F5F0E8')

      // Emoji + 标签（自然餐桌主题深色）
      ctx.fillStyle = '#2C2417'
      ctx.font = 'bold 14px sans-serif'
      ctx.fillText(`${item.emoji} ${item.label}`, padding + 28, currentY + 23)

      // 评级文字（右侧，彩色字体，无背景）
      const rating = item.data.rating || '一般'
      const ratingColor = ratingColors[rating] || '#9C8E7C'

      ctx.fillStyle = ratingColor
      ctx.font = 'bold 14px sans-serif'
      ctx.textAlign = 'right'
      ctx.fillText(rating, canvasWidth - padding - 28, currentY + 23)
      ctx.textAlign = 'left'

      // 评论（自然餐桌主题次要色）
      ctx.fillStyle = '#6B5E4C'
      ctx.font = '12px sans-serif'
      this.drawMultilineText(ctx, item.data.comment || '', padding + 28, currentY + 47, canvasWidth - padding * 2 - 56, 16)

      currentY += itemHeight + 5
    })

    return cardStartY + cardHeight + 4
  },

  // 绘制健康洞察 - 青色主题
  drawHealthInsights(ctx, canvasWidth, padding, startY) {
    const insights = this.data.analysis?.health_insights
    if (!insights) return startY

    const cardStartY = startY
    let currentY = startY
    const contentWidth = canvasWidth - padding * 2
    const headerHeight = 40

    const strengths = insights.strengths || []
    const weaknesses = insights.weaknesses || []
    const risks = insights.risk_factors || []

    // 先绘制临时背景以便测量
    currentY += headerHeight + 20  // 头部 + 间距

    // 优点
    if (strengths.length > 0) {
      currentY += 22  // 标题
      strengths.forEach(strength => {
        ctx.font = '12px sans-serif'
        const lines = this.wrapText(ctx, strength, canvasWidth - padding * 2 - 54)
        currentY += lines.length * 18 + 4
      })
      currentY += 6
    }

    // 需改进
    if (weaknesses.length > 0) {
      currentY += 22  // 标题
      weaknesses.forEach(weakness => {
        ctx.font = '12px sans-serif'
        const lines = this.wrapText(ctx, weakness, canvasWidth - padding * 2 - 54)
        currentY += lines.length * 18 + 4
      })
      currentY += 6
    }

    // 风险提示
    if (risks.length > 0) {
      currentY += 22  // 标题
      risks.forEach(risk => {
        ctx.font = '12px sans-serif'
        const lines = this.wrapText(ctx, risk, canvasWidth - padding * 2 - 54)
        currentY += lines.length * 18 + 4
      })
    }

    const contentHeight = currentY - cardStartY + 20

    // 绘制白色卡片背景
    this.drawRoundRect(ctx, padding, cardStartY, contentWidth, contentHeight, 16, '#ffffff')

    // 绘制渐变头部（青色主题）
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(padding + 16, cardStartY)
    ctx.lineTo(padding + contentWidth - 16, cardStartY)
    ctx.quadraticCurveTo(padding + contentWidth, cardStartY, padding + contentWidth, cardStartY + 16)
    ctx.lineTo(padding + contentWidth, cardStartY + headerHeight)
    ctx.lineTo(padding, cardStartY + headerHeight)
    ctx.lineTo(padding, cardStartY + 16)
    ctx.quadraticCurveTo(padding, cardStartY, padding + 16, cardStartY)
    ctx.closePath()

    const gradient = ctx.createLinearGradient(padding, cardStartY, padding + contentWidth, cardStartY + headerHeight)
    gradient.addColorStop(0, '#06B6D4')
    gradient.addColorStop(1, '#0891B2')
    ctx.fillStyle = gradient
    ctx.fill()
    ctx.restore()

    // 白色标题
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 16px sans-serif'
    ctx.fillText('健康洞察', padding + 16, cardStartY + 26)

    // 重新从头开始绘制内容
    currentY = cardStartY + headerHeight + 20

    // 优点 - 自然餐桌主题柔和绿色
    if (strengths.length > 0) {
      ctx.fillStyle = '#52B788'
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText('✅ 优点', padding + 16, currentY)
      currentY += 22

      strengths.forEach(strength => {
        ctx.fillStyle = '#52B788'
        ctx.fillText('•', padding + 26, currentY)
        ctx.fillStyle = '#2C2417'
        ctx.font = '12px sans-serif'
        const lines = this.drawMultilineText(ctx, strength, padding + 38, currentY, canvasWidth - padding * 2 - 54, 18)
        currentY += lines * 18 + 4
      })
      currentY += 6
    }

    // 需改进 - 自然餐桌主题琥珀色
    if (weaknesses.length > 0) {
      ctx.fillStyle = '#C59545'
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText('💡 需改进', padding + 16, currentY)
      currentY += 22

      weaknesses.forEach(weakness => {
        ctx.fillStyle = '#C59545'
        ctx.fillText('•', padding + 26, currentY)
        ctx.fillStyle = '#2C2417'
        ctx.font = '12px sans-serif'
        const lines = this.drawMultilineText(ctx, weakness, padding + 38, currentY, canvasWidth - padding * 2 - 54, 18)
        currentY += lines * 18 + 4
      })
      currentY += 6
    }

    // 风险提示 - 自然餐桌主题柔和红色
    if (risks.length > 0) {
      ctx.fillStyle = '#D9534F'
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText('🚨 风险提示', padding + 16, currentY)
      currentY += 22

      risks.forEach(risk => {
        ctx.fillStyle = '#D9534F'
        ctx.fillText('•', padding + 26, currentY)
        ctx.fillStyle = '#2C2417'
        ctx.font = '12px sans-serif'
        const lines = this.drawMultilineText(ctx, risk, padding + 38, currentY, canvasWidth - padding * 2 - 54, 18)
        currentY += lines * 18 + 4
      })
    }

    return cardStartY + contentHeight + 4
  },

  // 绘制饮食建议 - 绿色主题
  drawRecommendations(ctx, canvasWidth, padding, startY) {
    const recommendations = this.data.analysis?.recommendations
    if (!recommendations) return startY

    const cardStartY = startY
    const contentWidth = canvasWidth - padding * 2
    const headerHeight = 40

    // 第一遍：计算实际内容高度
    let measureY = startY + headerHeight + 20  // 头部 + 间距

    // 总结
    if (recommendations.summary) {
      ctx.font = '13px sans-serif'
      const lines = this.wrapText(ctx, recommendations.summary, canvasWidth - padding * 2 - 56)
      const boxHeight = lines.length * 18 + 30
      measureY += boxHeight + 20
    }

    // 行动清单（放在下一餐推荐之前）
    if (recommendations.action_items && recommendations.action_items.length > 0) {
      measureY += 30
      ctx.font = '11px sans-serif'
      recommendations.action_items.forEach(item => {
        const rationaleLines = this.wrapText(ctx, item.rationale, canvasWidth - padding * 2 - 78)
        const itemHeight = 38 + rationaleLines.length * 16 + 12
        measureY += itemHeight + 8
      })
    }

    // 下一餐推荐食谱（新版本：数组格式）
    const nextMeals = recommendations.next_meals || []
    if (nextMeals.length > 0) {
      measureY += 35  // 标题
      nextMeals.forEach(meal => {
        measureY += 45  // 餐次标题
        const dishes = meal.dishes || []
        dishes.forEach(dish => {
          ctx.font = '12px sans-serif'
          const ingredientsLines = this.wrapText(ctx, dish.ingredients || '', canvasWidth - padding * 2 - 80)
          const methodLines = this.wrapText(ctx, dish.method || '', canvasWidth - padding * 2 - 80)
          const benefitLines = this.wrapText(ctx, dish.benefit || '', canvasWidth - padding * 2 - 80)
          const dishHeight = 30 + ingredientsLines.length * 16 + methodLines.length * 16 + benefitLines.length * 16 + 30
          measureY += dishHeight + 10
        })
        if (meal.reason) {
          ctx.font = '11px sans-serif'
          const reasonLines = this.wrapText(ctx, meal.reason, canvasWidth - padding * 2 - 56)
          measureY += reasonLines.length * 16 + 20
        }
        measureY += 15
      })
    }

    // 下一餐推荐食谱（旧版本兼容：字符串格式）
    if (nextMeals.length === 0 && recommendations.next_meal_menu) {
      measureY += 30
      ctx.font = '13px sans-serif'
      const menuLines = this.wrapText(ctx, recommendations.next_meal_menu, canvasWidth - padding * 2 - 56)
      const menuBoxHeight = menuLines.length * 20 + 32
      measureY += menuBoxHeight + 20
    }

    // 下一餐建议（旧版本兼容）
    if (nextMeals.length === 0 && !recommendations.next_meal_menu && recommendations.next_meal_tips && recommendations.next_meal_tips.length > 0) {
      measureY += 30
      ctx.font = '12px sans-serif'
      recommendations.next_meal_tips.forEach(tip => {
        const suggestionLines = this.wrapText(ctx, tip.suggestion, canvasWidth - padding * 2 - 56)
        const itemHeight = 38 + suggestionLines.length * 16 + 12
        measureY += itemHeight + 8
      })
      measureY += 10
    }

    const contentHeight = measureY - cardStartY + 12

    // 白色卡片背景
    this.drawRoundRect(ctx, padding, cardStartY, contentWidth, contentHeight, 16, '#ffffff')

    // 绘制渐变头部（绿色主题）
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(padding + 16, cardStartY)
    ctx.lineTo(padding + contentWidth - 16, cardStartY)
    ctx.quadraticCurveTo(padding + contentWidth, cardStartY, padding + contentWidth, cardStartY + 16)
    ctx.lineTo(padding + contentWidth, cardStartY + headerHeight)
    ctx.lineTo(padding, cardStartY + headerHeight)
    ctx.lineTo(padding, cardStartY + 16)
    ctx.quadraticCurveTo(padding, cardStartY, padding + 16, cardStartY)
    ctx.closePath()

    const gradient = ctx.createLinearGradient(padding, cardStartY, padding + contentWidth, cardStartY + headerHeight)
    gradient.addColorStop(0, '#22C55E')
    gradient.addColorStop(1, '#16A34A')
    ctx.fillStyle = gradient
    ctx.fill()
    ctx.restore()

    // 白色标题
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 16px sans-serif'
    ctx.fillText('饮食建议', padding + 16, cardStartY + 26)

    // 第二遍：实际绘制内容
    let currentY = cardStartY + headerHeight + 20

    // 总结 - 自然餐桌主题米白底色
    if (recommendations.summary) {
      ctx.font = '13px sans-serif'
      const lines = this.wrapText(ctx, recommendations.summary, canvasWidth - padding * 2 - 56)
      const boxHeight = lines.length * 18 + 30
      this.drawRoundRect(ctx, padding + 16, currentY, canvasWidth - padding * 2 - 32, boxHeight, 10, '#F5F0E8')

      ctx.fillStyle = '#2C2417'
      lines.forEach((line, index) => {
        ctx.fillText(line, padding + 28, currentY + 20 + index * 18)
      })
      currentY += boxHeight + 20
    }

    // 行动清单（放在下一餐推荐之前）- 自然餐桌主题
    if (recommendations.action_items && recommendations.action_items.length > 0) {
      ctx.fillStyle = '#52B788'  // 柔和绿色 - 代表行动执行
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText('📝 行动清单', padding + 16, currentY)
      currentY += 25

      recommendations.action_items.forEach((item, index) => {
        ctx.font = '11px sans-serif'
        const rationaleLines = this.wrapText(ctx, item.rationale, canvasWidth - padding * 2 - 78)
        const itemHeight = 38 + rationaleLines.length * 16 + 12

        this.drawRoundRect(ctx, padding + 16, currentY, canvasWidth - padding * 2 - 32, itemHeight, 10, '#F5F0E8')

        // 左侧绿色条
        ctx.fillStyle = '#52B788'
        ctx.fillRect(padding + 16, currentY, 3, itemHeight)

        // 序号
        ctx.fillStyle = '#52B788'  // 柔和绿色 - 与标题呼应
        ctx.font = 'bold 14px sans-serif'
        ctx.fillText(`${index + 1}`, padding + 28, currentY + 20)

        // 行动
        ctx.fillStyle = '#52B788'  // 柔和绿色 - 强调行动
        ctx.font = 'bold 13px sans-serif'
        ctx.fillText(item.action, padding + 45, currentY + 20)

        // 原因
        ctx.fillStyle = '#6B5E4C'  // 暖灰色
        ctx.font = '11px sans-serif'
        this.drawMultilineText(ctx, item.rationale, padding + 45, currentY + 38, canvasWidth - padding * 2 - 78, 16)

        currentY += itemHeight + 8
      })
      currentY += 10
    }

    // 下一餐推荐食谱（新版本：数组格式）- 自然餐桌主题
    const nextMealsForDraw = recommendations.next_meals || []
    if (nextMealsForDraw.length > 0) {
      ctx.fillStyle = '#8B7355'  // 暖棕色
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText('🍽️ 下一餐推荐食谱', padding + 16, currentY)
      currentY += 25

      nextMealsForDraw.forEach((meal, mealIndex) => {
        // 餐次标题背景 - 暖棕色
        const mealHeaderHeight = 36
        this.drawRoundRect(ctx, padding + 16, currentY, canvasWidth - padding * 2 - 32, mealHeaderHeight, 8, '#8B7355')

        // 餐次标题文字
        ctx.fillStyle = '#fff'
        ctx.font = 'bold 14px sans-serif'
        ctx.fillText(meal.meal || '推荐', padding + 28, currentY + 22)

        // 热量标签
        ctx.font = '11px sans-serif'
        ctx.textAlign = 'right'
        ctx.fillText(`共 ${meal.total_calories || 0} 千卡`, canvasWidth - padding - 28, currentY + 22)
        ctx.textAlign = 'left'

        currentY += mealHeaderHeight + 10

        // 菜品列表
        const dishes = meal.dishes || []
        dishes.forEach((dish, dishIndex) => {
          ctx.font = '12px sans-serif'
          const ingredientsLines = this.wrapText(ctx, dish.ingredients || '', canvasWidth - padding * 2 - 80)
          const methodLines = this.wrapText(ctx, dish.method || '', canvasWidth - padding * 2 - 80)
          const benefitLines = this.wrapText(ctx, dish.benefit || '', canvasWidth - padding * 2 - 80)
          const dishHeight = 30 + ingredientsLines.length * 16 + methodLines.length * 16 + benefitLines.length * 16 + 30

          // 菜品卡片背景 - 温暖米白
          this.drawRoundRect(ctx, padding + 20, currentY, canvasWidth - padding * 2 - 40, dishHeight, 8, '#F5F0E8')

          // 菜名和热量
          ctx.fillStyle = '#2C2417'
          ctx.font = 'bold 13px sans-serif'
          ctx.fillText(dish.name || '', padding + 32, currentY + 20)

          ctx.fillStyle = '#E85D04'  // 热量橙色
          ctx.font = '11px sans-serif'
          ctx.textAlign = 'right'
          ctx.fillText(`${dish.calories || 0} kcal`, canvasWidth - padding - 32, currentY + 20)
          ctx.textAlign = 'left'

          let dishY = currentY + 38

          // 食材
          ctx.fillStyle = '#8B7355'  // 标签用暖棕色
          ctx.font = '11px sans-serif'
          ctx.fillText('食材', padding + 32, dishY)
          ctx.fillStyle = '#2C2417'
          ingredientsLines.forEach((line, i) => {
            ctx.fillText(line, padding + 68, dishY + i * 16)
          })
          dishY += ingredientsLines.length * 16 + 6

          // 做法
          ctx.fillStyle = '#8B7355'
          ctx.fillText('做法', padding + 32, dishY)
          ctx.fillStyle = '#2C2417'
          methodLines.forEach((line, i) => {
            ctx.fillText(line, padding + 68, dishY + i * 16)
          })
          dishY += methodLines.length * 16 + 6

          // 益处
          ctx.fillStyle = '#52B788'  // 益处用绿色
          ctx.fillText('💚', padding + 32, dishY)
          benefitLines.forEach((line, i) => {
            ctx.fillText(line, padding + 52, dishY + i * 16)
          })

          currentY += dishHeight + 10
        })

        // 搭配原因
        if (meal.reason) {
          ctx.font = '11px sans-serif'
          const reasonLines = this.wrapText(ctx, meal.reason, canvasWidth - padding * 2 - 56)

          ctx.fillStyle = '#6B5E4C'  // 暖灰色
          ctx.font = 'italic 11px sans-serif'
          reasonLines.forEach((line, i) => {
            ctx.fillText(line, padding + 28, currentY + i * 16)
          })
          currentY += reasonLines.length * 16 + 15
        }

        currentY += 10
      })
    }

    // 下一餐推荐食谱（旧版本兼容：字符串格式）- 自然餐桌主题
    if (nextMealsForDraw.length === 0 && recommendations.next_meal_menu) {
      ctx.fillStyle = '#8B7355'  // 暖棕色 - 代表未来计划
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText('🍽️ 下一餐推荐食谱', padding + 16, currentY)
      currentY += 25

      ctx.font = '13px sans-serif'
      const menuLines = this.wrapText(ctx, recommendations.next_meal_menu, canvasWidth - padding * 2 - 56)
      const menuBoxHeight = menuLines.length * 20 + 32

      // 温暖米白背景
      this.drawRoundRect(ctx, padding + 16, currentY, canvasWidth - padding * 2 - 32, menuBoxHeight, 10, '#F5F0E8')

      // 左侧暖棕色条
      ctx.fillStyle = '#8B7355'
      ctx.fillRect(padding + 16, currentY, 4, menuBoxHeight)

      // 绘制食谱文字
      ctx.fillStyle = '#2C2417'
      ctx.font = '13px sans-serif'
      menuLines.forEach((line, index) => {
        ctx.fillText(line, padding + 32, currentY + 22 + index * 20)
      })

      currentY += menuBoxHeight + 20
    }

    // 下一餐建议（旧版本兼容）- 自然餐桌主题
    if (nextMealsForDraw.length === 0 && !recommendations.next_meal_menu && recommendations.next_meal_tips && recommendations.next_meal_tips.length > 0) {
      ctx.fillStyle = '#8B7355'  // 暖棕色 - 代表未来计划
      ctx.font = 'bold 13px sans-serif'
      ctx.fillText('💡 下一餐建议', padding + 16, currentY)
      currentY += 25

      recommendations.next_meal_tips.forEach(tip => {
        ctx.font = '12px sans-serif'
        const suggestionLines = this.wrapText(ctx, tip.suggestion, canvasWidth - padding * 2 - 56)
        const itemHeight = 38 + suggestionLines.length * 16 + 12

        this.drawRoundRect(ctx, padding + 16, currentY, canvasWidth - padding * 2 - 32, itemHeight, 10, '#F5F0E8')

        ctx.fillStyle = '#8B7355'  // 暖棕色 - 与标题呼应
        ctx.font = 'bold 13px sans-serif'
        ctx.fillText(tip.meal, padding + 28, currentY + 20)

        ctx.fillStyle = '#6B5E4C'  // 暖灰色
        ctx.font = '12px sans-serif'
        this.drawMultilineText(ctx, tip.suggestion, padding + 28, currentY + 38, canvasWidth - padding * 2 - 56, 16)

        currentY += itemHeight + 8
      })
      currentY += 10
    }

    return cardStartY + contentHeight + 4
  },

  // 辅助函数：文本换行
  wrapText(ctx, text, maxWidth) {
    const words = text.split('')
    const lines = []
    let currentLine = ''

    for (let i = 0; i < words.length; i++) {
      const testLine = currentLine + words[i]
      const metrics = ctx.measureText(testLine)

      if (metrics.width > maxWidth && i > 0) {
        lines.push(currentLine)
        currentLine = words[i]
      } else {
        currentLine = testLine
      }
    }
    lines.push(currentLine)

    return lines
  },

  // 绘制多行文本（返回实际占用的行数）
  drawMultilineText(ctx, text, x, y, maxWidth, lineHeight) {
    const lines = this.wrapText(ctx, text, maxWidth)
    lines.forEach((line, index) => {
      ctx.fillText(line, x, y + index * lineHeight)
    })
    return lines.length
  },

  /**
   * 保存海报到相册
   */
  async savePoster() {
    try {
      await wx.saveImageToPhotosAlbum({
        filePath: this.data.posterPath
      })

      wx.showToast({
        title: '已保存到相册',
        icon: 'success'
      })

      this.closePosterPreview()
    } catch (err) {
      console.error('保存失败:', err)

      if (err.errMsg.includes('auth deny')) {
        wx.showModal({
          title: '需要相册权限',
          content: '请在设置中允许访问相册',
          confirmText: '去设置',
          success: (res) => {
            if (res.confirm) {
              wx.openSetting()
            }
          }
        })
      } else {
        wx.showToast({
          title: '保存失败',
          icon: 'none'
        })
      }
    }
  },

  /**
   * 关闭海报预览
   */
  closePosterPreview() {
    this.setData({
      showPosterPreview: false,
      posterPath: ''
    })
  },

  /**
   * 阻止点击事件冒泡
   */
  onPreviewTap() {
    // 阻止事件冒泡到mask
  },

  onShareAppMessage() {
    const meal = this.data.meal || {}
    const calories = meal.total_calories || 0
    return {
      title: '我的' + this.data.mealTypeLabel + ' - ' + calories + '千卡',
      path: '/pages/nutrition-detail/nutrition-detail?mealId=' + this.data.mealId
    }
  }
})
